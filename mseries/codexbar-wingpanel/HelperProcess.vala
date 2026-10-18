/* Bounded, asynchronous reads from disposable helpers. Never use for sign-in/switch actions. */
namespace MSeries {
    public class HelperProcess : GLib.Object {
        public static async string read (string[] command, uint timeout_ms = 30000,
                                         size_t max_bytes = 4 * 1024 * 1024) throws Error {
            var process = new Subprocess.newv (command,
                SubprocessFlags.STDOUT_PIPE | SubprocessFlags.STDERR_SILENCE);
            var cancel = new Cancellable ();
            bool timed_out = false;
            uint deadline = Timeout.add (timeout_ms, () => {
                timed_out = true;
                cancel.cancel ();
                process.force_exit ();
                return Source.REMOVE;
            });
            var output = new StringBuilder ();
            try {
                while (true) {
                    var bytes = yield process.get_stdout_pipe ().read_bytes_async (65536,
                        Priority.DEFAULT, cancel);
                    var data = bytes.get_data ();
                    if (data.length == 0) break;
                    if (bytes.get_size () > max_bytes - output.len) {
                        throw new IOError.NO_SPACE ("Helper response exceeds the size limit");
                    }
                    foreach (var value in data) {
                        if (value == 0) throw new IOError.INVALID_DATA ("Helper response contains NUL bytes");
                    }
                    output.append_len ((string) data, (ssize_t) bytes.get_size ());
                }
                yield process.wait_async (cancel);
                if (!process.get_successful ()) throw new IOError.FAILED ("Helper did not complete successfully");
                if (!output.str.validate ()) throw new IOError.INVALID_DATA ("Helper response is not UTF-8");
                return output.str;
            } catch (Error e) {
                process.force_exit ();
                // Reap only our disposable read process; account actions never pass through here.
                yield process.wait_async (null);
                if (timed_out) throw new IOError.TIMED_OUT ("Helper response timed out");
                throw e;
            } finally {
                if (!timed_out) Source.remove (deadline);
            }
        }
    }
}
