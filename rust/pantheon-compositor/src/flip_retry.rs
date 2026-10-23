//! Recovery policy for a page flip the kernel refuses with `EBUSY`.
//!
//! Right after an output is mapped, the `link-status` reset (a modeset on that
//! CRTC) can still be in flight when the first page flip is queued, and a
//! non-blocking commit may not overtake the previous one on the same CRTC.
//! Smithay's damage tracker has already accepted the frame by then, so without
//! help the output would stay black until something else damaged it. The
//! compositor therefore forces a full redraw and retries a few milliseconds
//! later. This module only classifies the error and bounds the retries.

use std::time::Duration;

/// `EBUSY`.
const EBUSY: i32 = 16;

/// Wait between retries; a modeset's flip completes within about one 60 Hz frame.
pub const RETRY_DELAY: Duration = Duration::from_millis(5);
/// Consecutive busy passes tolerated (about one second) before the failure is
/// reported like any other render error.
pub const MAX_BUSY_PASSES: u32 = 200;

/// Whether `error`, or anything in its source chain, is an OS `EBUSY`.
pub fn is_busy(error: &(dyn std::error::Error + 'static)) -> bool {
    let mut current = Some(error);
    while let Some(error) = current {
        if error
            .downcast_ref::<std::io::Error>()
            .is_some_and(|io| io.raw_os_error() == Some(EBUSY))
        {
            return true;
        }
        current = error.source();
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{error::Error, fmt, io};

    #[derive(Debug)]
    struct Wrapper(Box<dyn Error + 'static>);

    impl fmt::Display for Wrapper {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            write!(f, "wrapper")
        }
    }

    impl Error for Wrapper {
        fn source(&self) -> Option<&(dyn Error + 'static)> {
            Some(self.0.as_ref())
        }
    }

    #[test]
    fn busy_is_found_directly_and_through_wrappers() {
        let busy = io::Error::from_raw_os_error(EBUSY);
        assert!(is_busy(&busy));
        let nested = Wrapper(Box::new(Wrapper(Box::new(busy))));
        assert!(is_busy(&nested));
    }

    #[test]
    fn other_errors_are_not_busy() {
        assert!(!is_busy(&io::Error::from_raw_os_error(22)));
        assert!(!is_busy(&io::Error::other("busy")));
        assert!(!is_busy(&Wrapper(Box::new(io::Error::from_raw_os_error(
            13
        )))));
    }

    #[test]
    fn the_retry_budget_covers_about_a_second() {
        let total = RETRY_DELAY * MAX_BUSY_PASSES;
        assert!(total >= Duration::from_millis(900) && total <= Duration::from_millis(1100));
    }
}
