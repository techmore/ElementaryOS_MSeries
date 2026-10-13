/* Keep automatic panel-open refreshes bounded independently of wall-clock changes. */
namespace MSeries {
    internal class RefreshPolicy : GLib.Object {
        private int64 last_request_us = 0;

        public void requested (int64 monotonic_us) {
            last_request_us = monotonic_us;
        }

        public bool should_refresh_on_open (bool busy, int64 oldest_update_unix,
                                            int64 now_unix, int64 monotonic_us) {
            if (busy || (last_request_us != 0 && monotonic_us - last_request_us < 60 * GLib.TimeSpan.SECOND)) {
                return false;
            }
            var age_seconds = now_unix - oldest_update_unix;
            return oldest_update_unix == 0 || age_seconds < 0 || age_seconds >= 30;
        }
    }
}
