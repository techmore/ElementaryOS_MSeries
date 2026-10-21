/* SPDX-License-Identifier: GPL-3.0-or-later
 * Session-bus client for the Remote Desktop host daemon
 * (`io.elementary.mseries.Remote`). Shared by the app and the panel indicator. */
namespace MSeries.Remote {
    [DBus (name = "io.elementary.mseries.Remote1")]
    interface RemoteBus : Object {
        public abstract async string get_status () throws Error;
        public abstract async void set_enabled (bool enabled) throws Error;
        public abstract async string create_invite (bool allow_control) throws Error;
        public abstract async void decide (string request_id, bool allow, bool control) throws Error;
        public abstract async void set_control (bool control) throws Error;
        public abstract async void stop () throws Error;
        public signal void status_changed (string status_json);
        public signal void consent_requested (string request_json);
    }

    public const string BUS_NAME = "io.elementary.mseries.Remote";
    public const string OBJECT_PATH = "/io/elementary/mseries/Remote";

    public class Service : Object {
        public Status status { get; protected set; default = Status.unavailable (); }
        /* True after the first answer (or the first confirmed absence), so the
         * UI can tell "still looking" from "not running". */
        public bool settled { get; protected set; default = false; }

        public signal void changed ();
        public signal void consent_requested (PendingRequest request);
        /* An action failed; the message is fit to show the owner. */
        public signal void failed (string message);

        private RemoteBus? bus = null;
        private uint watch_id = 0;

        public Service () {
        }

        /* Start watching the bus name. Call once. */
        public virtual void start () {
            watch_id = Bus.watch_name (BusType.SESSION, BUS_NAME, BusNameWatcherFlags.NONE,
                () => { connect_bus.begin (); }, () => { lost (); });
        }

        private async void connect_bus () {
            try {
                bus = yield Bus.get_proxy<RemoteBus> (BusType.SESSION, BUS_NAME, OBJECT_PATH);
                bus.status_changed.connect (on_status_json);
                bus.consent_requested.connect (on_request_json);
                yield refresh ();
            } catch (Error e) {
                warning ("cannot reach %s: %s", BUS_NAME, e.message);
                lost ();
            }
        }

        private void lost () {
            bus = null;
            status = Status.unavailable ();
            settled = true;
            changed ();
        }

        private void on_status_json (string json) {
            var s = Status.parse (json);
            if (s == null) return;
            status = s;
            settled = true;
            changed ();
        }

        private void on_request_json (string json) {
            var parser = new Json.Parser ();
            try {
                parser.load_from_data (json);
            } catch (Error e) {
                return;
            }
            var o = parser.get_root ().get_object ();
            if (o == null) return;
            consent_requested (new PendingRequest () {
                id = o.get_string_member_with_default ("id", ""),
                device = o.get_string_member_with_default ("device", ""),
                control_offered = o.get_boolean_member_with_default ("control_offered", false),
                requested_ms = o.get_int_member_with_default ("requested_ms", 0),
                expires_ms = o.get_int_member_with_default ("expires_ms", 0)
            });
        }

        public virtual async void refresh () {
            if (bus == null) return;
            try {
                on_status_json ((yield bus.get_status ()));
            } catch (Error e) {
                failed (e.message);
            }
        }

        /* D-Bus activation starts the user service if it is installed. */
        public virtual async void start_service () {
            try {
                var conn = yield Bus.get (BusType.SESSION);
                yield conn.call ("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                    "StartServiceByName", new Variant ("(su)", BUS_NAME, 0), null, DBusCallFlags.NONE, 5000);
            } catch (Error e) {
                failed (_("Could not start the Remote Desktop service: %s").printf (e.message));
            }
        }

        public virtual async void set_enabled (bool on) {
            if (bus == null) return;
            try {
                yield bus.set_enabled (on);
            } catch (Error e) {
                failed (e.message);
            }
            yield refresh ();
        }

        public virtual async Invite? create_invite (bool allow_control) {
            if (bus == null) return null;
            try {
                return Invite.parse ((yield bus.create_invite (allow_control)));
            } catch (Error e) {
                failed (e.message);
                return null;
            }
        }

        public virtual async void decide (string request_id, bool allow, bool control) {
            if (bus == null) return;
            try {
                yield bus.decide (request_id, allow, control);
            } catch (Error e) {
                failed (e.message);
            }
        }

        public virtual async void set_control (bool control) {
            if (bus == null) return;
            try {
                yield bus.set_control (control);
            } catch (Error e) {
                failed (e.message);
            }
        }

        public virtual async void end_session () {
            if (bus == null) return;
            try {
                yield bus.stop ();
            } catch (Error e) {
                failed (e.message);
            }
        }

        ~Service () {
            if (watch_id != 0) Bus.unwatch_name (watch_id);
        }
    }
}
