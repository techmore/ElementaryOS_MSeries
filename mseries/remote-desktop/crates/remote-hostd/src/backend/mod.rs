//! Desktop backends: where frames come from and where input goes.

use remote_core::capture::{CaptureError, FrameSource, TestPattern};
use remote_core::input::{InputError, InputSink, RecordingSink};

#[cfg(feature = "mutter")]
pub mod mutter;

/// One viewer's capture + input pair (opened when its peer starts).
pub struct Streams {
    pub source: Box<dyn FrameSource>,
    pub input: Box<dyn InputSink>,
}

#[derive(Debug, thiserror::Error)]
pub enum BackendError {
    #[error(transparent)]
    Capture(#[from] CaptureError),
    #[error(transparent)]
    Input(#[from] InputError),
    #[error("{0}")]
    Other(String),
}

pub trait Backend: Send + Sync {
    fn name(&self) -> &'static str;
    /// `max_width` caps the encoded width; `fps` is the capture rate.
    fn open(&self, max_width: u32, fps: u32) -> Result<Streams, BackendError>;
}

/// Synthetic desktop for headless tests and demos; input is recorded, not injected.
#[derive(Default)]
pub struct TestBackend {
    pub sink: RecordingSink,
}

impl Backend for TestBackend {
    fn name(&self) -> &'static str {
        "test"
    }

    fn open(&self, _max_width: u32, _fps: u32) -> Result<Streams, BackendError> {
        Ok(Streams {
            source: Box::new(TestPattern::new(640, 360)),
            input: Box::new(self.sink.clone()),
        })
    }
}

/// Even output size at most `max_width` wide, keeping the aspect ratio.
pub fn fit(width: u32, height: u32, max_width: u32) -> (u32, u32) {
    let (w, h) = if width > max_width {
        (max_width, (height as u64 * max_width as u64 / width as u64) as u32)
    } else {
        (width, height)
    };
    (w & !1, h & !1)
}

#[cfg(test)]
mod tests {
    use super::fit;

    #[test]
    fn fit_scales_down_and_evens() {
        assert_eq!(fit(3024, 1964, 1920), (1920, 1246));
        assert_eq!(fit(1280, 720, 1920), (1280, 720));
        assert_eq!(fit(1281, 721, 1920), (1280, 720));
    }
}
