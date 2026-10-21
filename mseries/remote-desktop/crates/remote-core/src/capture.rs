//! Frame sources. A source yields tightly packed I420 frames; pacing is the
//! caller's job. Frames live only in memory: nothing here writes them to disk.

use std::io::Read;
use std::process::{Child, ChildStdout, Command, Stdio};

#[derive(Debug, thiserror::Error)]
pub enum CaptureError {
    #[error("capture ended")]
    Ended,
    #[error("capture failed: {0}")]
    Failed(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Frame {
    pub width: u32,
    pub height: u32,
    /// Y plane, then U, then V; no padding. Length `w*h*3/2`.
    pub i420: Vec<u8>,
}

impl Frame {
    pub fn i420_len(width: u32, height: u32) -> usize {
        (width as usize * height as usize * 3) / 2
    }

    pub fn y_plane(&self) -> &[u8] {
        &self.i420[..(self.width * self.height) as usize]
    }
}

pub trait FrameSource: Send {
    fn dimensions(&self) -> (u32, u32);
    /// Blocks until the next frame.
    fn next_frame(&mut self) -> Result<Frame, CaptureError>;
}

/// Width of the frame-counter strip in bits; the loopback test reads it back
/// from the decoded video to prove ordering and measure loss.
pub const COUNTER_BITS: u32 = 16;

/// Deterministic synthetic desktop: colour bars, a moving square and a
/// frame-counter strip along the top that survives lossy H.264.
pub struct TestPattern {
    w: u32,
    h: u32,
    n: u32,
}

impl TestPattern {
    pub fn new(w: u32, h: u32) -> Self {
        assert!(w >= 256 && h >= 128 && w % 2 == 0 && h % 2 == 0, "pattern needs even dimensions >= 256x128");
        Self { w, h, n: 0 }
    }

    pub fn render(w: u32, h: u32, n: u32) -> Frame {
        let (wu, hu) = (w as usize, h as usize);
        let mut buf = vec![0u8; Frame::i420_len(w, h)];
        let (y_plane, rest) = buf.split_at_mut(wu * hu);
        let (u_plane, v_plane) = rest.split_at_mut(wu * hu / 4);
        // Background: vertical luma ramp with colour bars in chroma.
        for y in 0..hu {
            for x in 0..wu {
                y_plane[y * wu + x] = 40 + ((y * 120) / hu) as u8;
            }
        }
        for cy in 0..hu / 2 {
            for cx in 0..wu / 2 {
                let bar = (cx * 8) / (wu / 2);
                u_plane[cy * (wu / 2) + cx] = [128, 90, 170, 60, 200, 128, 100, 160][bar];
                v_plane[cy * (wu / 2) + cx] = [128, 200, 60, 150, 90, 128, 180, 70][bar];
            }
        }
        // Neutral chroma under the counter strip so RGB readers (a browser
        // canvas) see the same black/white as the luma plane.
        for cy in 0..12.min(hu / 2) {
            for cx in 0..wu / 2 {
                u_plane[cy * (wu / 2) + cx] = 128;
                v_plane[cy * (wu / 2) + cx] = 128;
            }
        }
        // Moving square, 32x32.
        let sx = (n as usize * 8) % (wu - 32 - 8).max(1);
        let sy = hu / 3 + ((n as usize * 3) % (hu / 3));
        for y in sy..(sy + 32).min(hu) {
            for x in sx..(sx + 32).min(wu) {
                y_plane[y * wu + x] = 235;
            }
        }
        // Counter strip: 16 cells, white=1 / black=0, MSB first, 24px tall.
        let cell = wu / COUNTER_BITS as usize;
        for bit in 0..COUNTER_BITS as usize {
            let on = (n >> (COUNTER_BITS as usize - 1 - bit)) & 1 == 1;
            let luma = if on { 235 } else { 16 };
            for y in 0..24.min(hu) {
                for x in bit * cell..(bit + 1) * cell {
                    y_plane[y * wu + x] = luma;
                }
            }
        }
        Frame { width: w, height: h, i420: buf }
    }

    /// Read the counter strip back from a (possibly decoded/lossy) frame.
    pub fn read_counter(frame: &Frame) -> u32 {
        let wu = frame.width as usize;
        let cell = wu / COUNTER_BITS as usize;
        let y = frame.y_plane();
        let mut n = 0u32;
        for bit in 0..COUNTER_BITS as usize {
            // Sample the cell centre, 12 rows down.
            let v = y[12 * wu + bit * cell + cell / 2];
            n = (n << 1) | u32::from(v > 125);
        }
        n
    }
}

impl FrameSource for TestPattern {
    fn dimensions(&self) -> (u32, u32) {
        (self.w, self.h)
    }

    fn next_frame(&mut self) -> Result<Frame, CaptureError> {
        let f = Self::render(self.w, self.h, self.n);
        self.n = self.n.wrapping_add(1) & ((1 << COUNTER_BITS) - 1);
        Ok(f)
    }
}

/// Reads raw I420 from a `gst-launch-1.0` child that captures a PipeWire node
/// (a portal / Mutter ScreenCast stream). The child is killed on drop.
pub struct GstPipeSource {
    child: Child,
    out: ChildStdout,
    w: u32,
    h: u32,
}

impl GstPipeSource {
    pub fn spawn(node_id: u32, w: u32, h: u32, fps: u32) -> Result<Self, CaptureError> {
        if w % 2 != 0 || h % 2 != 0 || w == 0 || h == 0 || fps == 0 || fps > 120 {
            return Err(CaptureError::Failed("invalid capture geometry".into()));
        }
        let caps = format!("video/x-raw,format=I420,width={w},height={h},framerate={fps}/1");
        let mut child = Command::new("gst-launch-1.0")
            .args(["-q", "pipewiresrc", &format!("path={node_id}"), "do-timestamp=true"])
            .args(["!", "videoconvert", "!", "videoscale", "!", "videorate", "!", &caps])
            .args(["!", "fdsink", "fd=1", "sync=false"])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| CaptureError::Failed(format!("gst-launch-1.0: {e}")))?;
        let out = child.stdout.take().ok_or_else(|| CaptureError::Failed("no pipe".into()))?;
        Ok(Self { child, out, w, h })
    }
}

impl FrameSource for GstPipeSource {
    fn dimensions(&self) -> (u32, u32) {
        (self.w, self.h)
    }

    fn next_frame(&mut self) -> Result<Frame, CaptureError> {
        let mut buf = vec![0u8; Frame::i420_len(self.w, self.h)];
        self.out.read_exact(&mut buf).map_err(|e| match e.kind() {
            std::io::ErrorKind::UnexpectedEof => CaptureError::Ended,
            _ => CaptureError::Failed(e.to_string()),
        })?;
        Ok(Frame { width: self.w, height: self.h, i420: buf })
    }
}

impl Drop for GstPipeSource {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn counter_roundtrips_and_frames_differ() {
        let mut p = TestPattern::new(640, 360);
        let a = p.next_frame().unwrap();
        let b = p.next_frame().unwrap();
        assert_ne!(a, b);
        assert_eq!(a.i420.len(), Frame::i420_len(640, 360));
        assert_eq!(TestPattern::read_counter(&a), 0);
        assert_eq!(TestPattern::read_counter(&b), 1);
        let f = TestPattern::render(640, 360, 0xABCD);
        assert_eq!(TestPattern::read_counter(&f), 0xABCD);
    }

    #[test]
    fn gst_rejects_bad_geometry() {
        assert!(GstPipeSource::spawn(1, 641, 360, 30).is_err());
        assert!(GstPipeSource::spawn(1, 640, 360, 0).is_err());
    }
}
