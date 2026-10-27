//! Journal-friendly log lines for the systemd user service.

use std::fmt;

use tracing::{Event, Level, Subscriber};
use tracing_subscriber::{
    fmt::{
        FmtContext, FormatEvent, FormatFields,
        format::{Format, Full, Writer},
    },
    registry::LookupSpan,
};

/// The default compact line without a timestamp (journald stamps every line)
/// and without colour, prefixed with the sd-daemon priority (`<3>` error,
/// `<4>` warning, `<6>` info, `<7>` debug) that journald turns into PRIORITY.
pub struct JournalFormat(Format<Full, ()>);

impl JournalFormat {
    pub fn new() -> Self {
        Self(
            tracing_subscriber::fmt::format()
                .without_time()
                .with_ansi(false),
        )
    }
}

pub fn priority(level: &Level) -> u8 {
    match *level {
        Level::ERROR => 3,
        Level::WARN => 4,
        Level::INFO => 6,
        Level::DEBUG | Level::TRACE => 7,
    }
}

impl<S, N> FormatEvent<S, N> for JournalFormat
where
    S: Subscriber + for<'a> LookupSpan<'a>,
    N: for<'a> FormatFields<'a> + 'static,
{
    fn format_event(
        &self,
        ctx: &FmtContext<'_, S, N>,
        mut writer: Writer<'_>,
        event: &Event<'_>,
    ) -> fmt::Result {
        write!(writer, "<{}>", priority(event.metadata().level()))?;
        self.0.format_event(ctx, writer, event)
    }
}

/// `JOURNAL_STREAM` is `<device>:<inode>` of the journal socket systemd gave
/// the service; it is inherited by children whose stderr may be elsewhere.
pub fn journal_stream_matches(value: &str, dev: u64, ino: u64) -> bool {
    let Some((stream_dev, stream_ino)) = value.split_once(':') else {
        return false;
    };
    stream_dev.parse() == Ok(dev) && stream_ino.parse() == Ok(ino)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn priorities_follow_sd_daemon() {
        assert_eq!(priority(&Level::ERROR), 3);
        assert_eq!(priority(&Level::WARN), 4);
        assert_eq!(priority(&Level::INFO), 6);
        assert_eq!(priority(&Level::DEBUG), 7);
        assert_eq!(priority(&Level::TRACE), 7);
    }

    #[test]
    fn journal_lines_carry_priority_and_no_time_or_colour() {
        use std::sync::{Arc, Mutex};
        #[derive(Clone, Default)]
        struct Buffer(Arc<Mutex<Vec<u8>>>);
        impl std::io::Write for Buffer {
            fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
                self.0.lock().unwrap().extend_from_slice(bytes);
                Ok(bytes.len())
            }
            fn flush(&mut self) -> std::io::Result<()> {
                Ok(())
            }
        }
        let buffer = Buffer::default();
        let writer = buffer.clone();
        let subscriber = tracing_subscriber::fmt()
            .with_ansi(false)
            .with_writer(move || writer.clone())
            .event_format(JournalFormat::new())
            .finish();
        tracing::subscriber::with_default(subscriber, || {
            tracing::error!(target: "pantheon_test", code = 7, "broke");
            tracing::info!(target: "pantheon_test", "fine");
        });
        let output = String::from_utf8(buffer.0.lock().unwrap().clone()).unwrap();
        let lines = output.lines().collect::<Vec<_>>();
        assert_eq!(
            lines,
            [
                "<3>ERROR pantheon_test: broke code=7",
                "<6> INFO pantheon_test: fine"
            ]
        );
    }

    #[test]
    fn journal_stream_must_name_our_stderr() {
        assert!(journal_stream_matches("8:12345", 8, 12345));
        assert!(!journal_stream_matches("8:12345", 8, 1));
        assert!(!journal_stream_matches("garbage", 8, 12345));
        assert!(!journal_stream_matches("", 0, 0));
    }
}
