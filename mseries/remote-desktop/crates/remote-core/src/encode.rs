//! H.264 (Annex B) encode/decode with OpenH264, software only: Apple GPUs on
//! Asahi expose no usable video encoder yet. Screen-content mode, bitrate rate
//! control with frame skipping: a skipped frame yields an empty access unit and
//! the sender simply writes nothing for it.

use openh264::decoder::Decoder;
use openh264::encoder::{
    BitRate, Encoder, EncoderConfig, FrameRate, IntraFramePeriod, RateControlMode, UsageType,
};
use openh264::formats::YUVSource;
use openh264::OpenH264API;

use crate::capture::Frame;

#[derive(Debug, thiserror::Error)]
pub enum CodecError {
    #[error("encoder: {0}")]
    Encode(String),
    #[error("decoder: {0}")]
    Decode(String),
    #[error("frame size {got:?} does not match encoder {want:?}")]
    Size { want: (u32, u32), got: (u32, u32) },
}

/// Contiguous I420 view for OpenH264.
struct I420View<'a>(&'a Frame);

impl YUVSource for I420View<'_> {
    fn dimensions(&self) -> (usize, usize) {
        (self.0.width as usize, self.0.height as usize)
    }
    fn strides(&self) -> (usize, usize, usize) {
        let w = self.0.width as usize;
        (w, w / 2, w / 2)
    }
    fn y(&self) -> &[u8] {
        &self.0.i420[..self.0.width as usize * self.0.height as usize]
    }
    fn u(&self) -> &[u8] {
        let n = self.0.width as usize * self.0.height as usize;
        &self.0.i420[n..n + n / 4]
    }
    fn v(&self) -> &[u8] {
        let n = self.0.width as usize * self.0.height as usize;
        &self.0.i420[n + n / 4..]
    }
}

pub struct H264Encoder {
    enc: Encoder,
    size: (u32, u32),
}

impl H264Encoder {
    pub fn new(width: u32, height: u32, fps: u32, bitrate_bps: u32) -> Result<Self, CodecError> {
        let cfg = EncoderConfig::new()
            .bitrate(BitRate::from_bps(bitrate_bps))
            .max_frame_rate(FrameRate::from_hz(fps as f32))
            .usage_type(UsageType::ScreenContentRealTime)
            .rate_control_mode(RateControlMode::Bitrate)
            .skip_frames(true)
            .intra_frame_period(IntraFramePeriod::from_num_frames(fps.saturating_mul(5)));
        let enc = Encoder::with_api_config(OpenH264API::from_source(), cfg)
            .map_err(|e| CodecError::Encode(e.to_string()))?;
        Ok(Self {
            enc,
            size: (width, height),
        })
    }

    pub fn force_keyframe(&mut self) {
        self.enc.force_intra_frame();
    }

    /// One access unit in Annex B (start-code delimited NALs).
    pub fn encode(&mut self, frame: &Frame) -> Result<Vec<u8>, CodecError> {
        if (frame.width, frame.height) != self.size {
            return Err(CodecError::Size {
                want: self.size,
                got: (frame.width, frame.height),
            });
        }
        let bits = self
            .enc
            .encode(&I420View(frame))
            .map_err(|e| CodecError::Encode(e.to_string()))?;
        Ok(bits.to_vec())
    }
}

pub struct H264Decoder {
    dec: Decoder,
}

impl H264Decoder {
    pub fn new() -> Result<Self, CodecError> {
        Ok(Self {
            dec: Decoder::new().map_err(|e| CodecError::Decode(e.to_string()))?,
        })
    }

    /// Feed one access unit; returns a frame once the decoder has one.
    pub fn decode(&mut self, annexb: &[u8]) -> Result<Option<Frame>, CodecError> {
        let out = self
            .dec
            .decode(annexb)
            .map_err(|e| CodecError::Decode(e.to_string()))?;
        Ok(out.map(|yuv| {
            let (w, h) = yuv.dimensions();
            let (sy, su, sv) = yuv.strides();
            let mut i420 = Vec::with_capacity(w * h * 3 / 2);
            for row in 0..h {
                i420.extend_from_slice(&yuv.y()[row * sy..row * sy + w]);
            }
            for row in 0..h / 2 {
                i420.extend_from_slice(&yuv.u()[row * su..row * su + w / 2]);
            }
            for row in 0..h / 2 {
                i420.extend_from_slice(&yuv.v()[row * sv..row * sv + w / 2]);
            }
            Frame {
                width: w as u32,
                height: h as u32,
                i420,
            }
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::capture::{FrameSource, TestPattern};

    #[test]
    fn encode_decode_preserves_the_frame_counter() {
        let mut src = TestPattern::new(640, 360);
        let mut enc = H264Encoder::new(640, 360, 30, 1_500_000).unwrap();
        let mut dec = H264Decoder::new().unwrap();
        let mut seen = Vec::new();
        for _ in 0..20 {
            let bits = enc.encode(&src.next_frame().unwrap()).unwrap();
            assert!(!bits.is_empty());
            if let Some(f) = dec.decode(&bits).unwrap() {
                seen.push(TestPattern::read_counter(&f));
            }
        }
        assert!(seen.len() >= 18, "decoded {} of 20", seen.len());
        assert!(
            seen.windows(2).all(|w| w[1] > w[0]),
            "counters not increasing: {seen:?}"
        );
    }

    #[test]
    fn rejects_wrong_size() {
        let mut enc = H264Encoder::new(640, 360, 30, 1_000_000).unwrap();
        let f = TestPattern::render(320, 240, 0);
        assert!(matches!(enc.encode(&f), Err(CodecError::Size { .. })));
    }
}
