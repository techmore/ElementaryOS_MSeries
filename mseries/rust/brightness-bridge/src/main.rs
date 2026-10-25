use std::ffi::{CStr, CString, c_char, c_int, c_void};
use std::process::ExitCode;
use std::ptr;

const XML: &CStr = c"<node><interface name='org.gnome.Shell.Brightness'>\
<method name='SetDimming'><arg type='b' direction='in'/></method>\
<method name='SetAutoBrightnessTarget'><arg type='d' direction='in'/></method>\
<property name='HasBrightnessControl' type='b' access='read'/>\
<signal name='BrightnessChanged'/>\
</interface></node>";

#[repr(C)]
struct GError {
    domain: u32,
    code: c_int,
    message: *mut c_char,
}

#[repr(C)]
struct GVariant(c_void);
#[repr(C)]
struct GDBusConnection(c_void);
#[repr(C)]
struct GDBusProxy(c_void);
#[repr(C)]
struct GDBusNodeInfo(c_void);
#[repr(C)]
struct GDBusInterfaceInfo(c_void);
#[repr(C)]
struct GDBusMethodInvocation(c_void);
#[repr(C)]
struct GSettings(c_void);
#[repr(C)]
struct GMainLoop(c_void);

type MethodCall = unsafe extern "C" fn(
    *mut GDBusConnection,
    *const c_char,
    *const c_char,
    *const c_char,
    *const c_char,
    *mut GVariant,
    *mut GDBusMethodInvocation,
    *mut c_void,
);
type GetProperty = unsafe extern "C" fn(
    *mut GDBusConnection,
    *const c_char,
    *const c_char,
    *const c_char,
    *const c_char,
    *mut c_void,
    *mut *mut GError,
) -> *mut GVariant;

#[repr(C)]
struct GDBusInterfaceVTable {
    method_call: Option<MethodCall>,
    get_property: Option<GetProperty>,
    set_property: *const c_void,
    padding: [*const c_void; 8],
}

unsafe extern "C" {
    fn g_bus_get_sync(
        bus_type: c_int,
        cancellable: *mut c_void,
        error: *mut *mut GError,
    ) -> *mut GDBusConnection;
    fn g_dbus_proxy_new_sync(
        connection: *mut GDBusConnection,
        flags: c_int,
        info: *mut c_void,
        name: *const c_char,
        object_path: *const c_char,
        interface_name: *const c_char,
        cancellable: *mut c_void,
        error: *mut *mut GError,
    ) -> *mut GDBusProxy;
    fn g_dbus_proxy_get_connection(proxy: *mut GDBusProxy) -> *mut GDBusConnection;
    fn g_dbus_proxy_call_sync(
        proxy: *mut GDBusProxy,
        method: *const c_char,
        parameters: *mut GVariant,
        flags: c_int,
        timeout_msec: c_int,
        cancellable: *mut c_void,
        error: *mut *mut GError,
    ) -> *mut GVariant;
    fn g_dbus_node_info_new_for_xml(
        xml: *const c_char,
        error: *mut *mut GError,
    ) -> *mut GDBusNodeInfo;
    fn g_dbus_node_info_lookup_interface(
        info: *mut GDBusNodeInfo,
        name: *const c_char,
    ) -> *mut GDBusInterfaceInfo;
    fn g_dbus_node_info_unref(info: *mut GDBusNodeInfo);
    fn g_dbus_connection_register_object(
        connection: *mut GDBusConnection,
        path: *const c_char,
        info: *mut GDBusInterfaceInfo,
        vtable: *const GDBusInterfaceVTable,
        user_data: *mut c_void,
        user_data_free_func: *mut c_void,
        error: *mut *mut GError,
    ) -> u32;
    fn g_bus_own_name_on_connection(
        connection: *mut GDBusConnection,
        name: *const c_char,
        flags: c_int,
        name_acquired_handler: *mut c_void,
        name_lost_handler: *mut c_void,
        user_data: *mut c_void,
        user_data_free_func: *mut c_void,
    ) -> u32;
    fn g_signal_connect_data(
        instance: *mut c_void,
        detailed_signal: *const c_char,
        handler: *const c_void,
        data: *mut c_void,
        destroy_data: *mut c_void,
        flags: c_int,
    ) -> u64;
    fn g_dbus_connection_call_sync(
        connection: *mut GDBusConnection,
        bus_name: *const c_char,
        object_path: *const c_char,
        interface_name: *const c_char,
        method_name: *const c_char,
        parameters: *mut GVariant,
        reply_type: *const c_void,
        flags: c_int,
        timeout_msec: c_int,
        cancellable: *mut c_void,
        error: *mut *mut GError,
    ) -> *mut GVariant;
    fn g_dbus_connection_emit_signal(
        connection: *mut GDBusConnection,
        destination: *const c_char,
        object_path: *const c_char,
        interface_name: *const c_char,
        signal_name: *const c_char,
        parameters: *mut GVariant,
        error: *mut *mut GError,
    ) -> c_int;
    fn g_dbus_method_invocation_return_value(
        invocation: *mut GDBusMethodInvocation,
        value: *mut GVariant,
    );
    fn g_dbus_method_invocation_return_dbus_error(
        invocation: *mut GDBusMethodInvocation,
        name: *const c_char,
        message: *const c_char,
    );
    fn g_settings_new(schema_id: *const c_char) -> *mut GSettings;
    fn g_settings_get_boolean(settings: *mut GSettings, key: *const c_char) -> c_int;
    fn g_settings_get_int(settings: *mut GSettings, key: *const c_char) -> c_int;
    fn g_main_loop_new(context: *mut c_void, is_running: c_int) -> *mut GMainLoop;
    fn g_main_loop_run(loop_: *mut GMainLoop);
    fn g_variant_new(format: *const c_char, ...) -> *mut GVariant;
    fn g_variant_get_child_value(value: *mut GVariant, index: usize) -> *mut GVariant;
    fn g_variant_get_variant(value: *mut GVariant) -> *mut GVariant;
    fn g_variant_get_uint32(value: *mut GVariant) -> u32;
    fn g_variant_get_boolean(value: *mut GVariant) -> c_int;
    fn g_variant_get_double(value: *mut GVariant) -> f64;
    fn g_variant_n_children(value: *mut GVariant) -> usize;
    fn g_variant_lookup(
        dictionary: *mut GVariant,
        key: *const c_char,
        format: *const c_char,
        ...
    ) -> c_int;
    fn g_variant_lookup_value(
        dictionary: *mut GVariant,
        key: *const c_char,
        expected: *const c_void,
    ) -> *mut GVariant;
    fn g_variant_unref(value: *mut GVariant);
    fn g_error_free(error: *mut GError);
}

#[derive(Clone, Debug, PartialEq)]
struct Panel {
    serial: u32,
    connector: String,
    minimum: Option<i32>,
    maximum: Option<i32>,
    value: Option<i32>,
}

#[derive(Default, Debug)]
struct BridgeState {
    saved: Option<i32>,
    last_set: Option<i32>,
    last_seen: Option<i32>,
}

impl BridgeState {
    fn dim_allowed(&self, enable: bool, idle_dim_enabled: bool) -> bool {
        if enable {
            idle_dim_enabled
        } else {
            self.saved.is_some()
        }
    }

    fn auto_allowed(&self, target: f64, ambient_enabled: bool) -> Result<bool, String> {
        Self::validate_auto(target)?;
        Ok(ambient_enabled && self.saved.is_none())
    }

    fn dim_target(
        &mut self,
        enable: bool,
        current: i32,
        maximum: i32,
        percent: i32,
    ) -> Option<f64> {
        if enable {
            let saved = *self.saved.get_or_insert(current);
            Some((maximum as f64 * percent as f64 / 100.0).min(saved as f64))
        } else {
            (Some(current) == self.last_set).then_some(self.saved.unwrap_or(current) as f64)
        }
    }

    fn validate_auto(target: f64) -> Result<(), String> {
        if !target.is_finite() || !(0.0..=1.0).contains(&target) {
            Err("Auto brightness target must be between zero and one".into())
        } else {
            Ok(())
        }
    }

    fn auto_value(&self, target: f64, panel: &Panel) -> Result<f64, String> {
        let minimum = panel
            .minimum
            .ok_or("Internal panel has no minimum brightness")?;
        let maximum = panel
            .maximum
            .ok_or("Internal panel has no maximum brightness")?;
        Ok(minimum as f64 + target * (maximum - minimum) as f64)
    }

    fn record_set(&mut self, value: i32) {
        self.last_set = Some(value);
        self.last_seen = Some(value);
    }

    fn observe(&mut self, current: i32) -> bool {
        let changed = Some(current) != self.last_seen && Some(current) != self.last_set;
        if changed {
            self.saved = None;
        }
        self.last_seen = Some(current);
        changed
    }
}

struct Bridge {
    connection: *mut GDBusConnection,
    display: *mut GDBusProxy,
    settings: *mut GSettings,
    state: BridgeState,
}

impl Bridge {
    fn settings_bool(&self, key: &CStr) -> bool {
        unsafe { g_settings_get_boolean(self.settings, key.as_ptr()) != 0 }
    }

    fn panel(&self) -> Result<Panel, String> {
        unsafe { read_internal_panel(self.connection) }
    }

    fn set_value(&mut self, panel: &Panel, requested: f64) -> Result<(), String> {
        let minimum = panel
            .minimum
            .ok_or_else(|| "Internal panel has no minimum brightness".to_owned())?;
        let maximum = panel
            .maximum
            .ok_or_else(|| "Internal panel has no maximum brightness".to_owned())?;
        let target = (requested.round_ties_even() as i32)
            .min(maximum)
            .max(minimum);
        let connector = CString::new(panel.connector.as_str()).map_err(|e| e.to_string())?;
        let method = c"SetBacklight";
        let params =
            unsafe { g_variant_new(c"(usi)".as_ptr(), panel.serial, connector.as_ptr(), target) };
        let mut error = ptr::null_mut();
        let result = unsafe {
            g_dbus_proxy_call_sync(
                self.display,
                method.as_ptr(),
                params,
                0,
                3000,
                ptr::null_mut(),
                &mut error,
            )
        };
        if result.is_null() {
            return Err(unsafe { take_error(error, "Mutter SetBacklight failed") });
        }
        unsafe {
            g_variant_unref(result);
        }
        self.state.record_set(target);
        Ok(())
    }

    fn dim(&mut self, enable: bool) -> Result<(), String> {
        if !self
            .state
            .dim_allowed(enable, self.settings_bool(c"idle-dim"))
        {
            return Ok(());
        }
        let panel = self.panel()?;
        let value = panel
            .value
            .ok_or_else(|| "Internal panel has no current brightness".to_owned())?;
        let maximum = panel.maximum.unwrap_or(0);
        let percent = unsafe { g_settings_get_int(self.settings, c"idle-brightness".as_ptr()) };
        if let Some(target) = self.state.dim_target(enable, value, maximum, percent) {
            self.set_value(&panel, target)?;
        }
        if !enable {
            self.state.saved = None;
        }
        Ok(())
    }

    fn auto(&mut self, target: f64) -> Result<(), String> {
        if !self
            .state
            .auto_allowed(target, self.settings_bool(c"ambient-enabled"))?
        {
            return Ok(());
        }
        let panel = self.panel()?;
        self.set_value(&panel, self.state.auto_value(target, &panel)?)
    }

    fn changed(&mut self, changed: *mut GVariant) {
        let value = unsafe { g_variant_lookup_value(changed, c"Backlight".as_ptr(), ptr::null()) };
        if value.is_null() {
            return;
        }
        unsafe {
            g_variant_unref(value);
        }
        if let Ok(panel) = self.panel() {
            if let Some(current) = panel.value {
                if self.state.observe(current) {
                    let mut error = ptr::null_mut();
                    let ok = unsafe {
                        g_dbus_connection_emit_signal(
                            self.connection,
                            ptr::null(),
                            c"/org/gnome/Shell/Brightness".as_ptr(),
                            c"org.gnome.Shell.Brightness".as_ptr(),
                            c"BrightnessChanged".as_ptr(),
                            ptr::null_mut(),
                            &mut error,
                        )
                    };
                    if ok == 0 {
                        let _ = unsafe { take_error(error, "Could not emit BrightnessChanged") };
                    }
                }
                self.state.last_seen = Some(current);
            }
        }
    }
}

unsafe fn dict_string(dictionary: *mut GVariant, name: &CStr) -> Option<String> {
    let format = c"&s";
    let mut value: *const c_char = ptr::null();
    if unsafe { g_variant_lookup(dictionary, name.as_ptr(), format.as_ptr(), &mut value) } == 0
        || value.is_null()
    {
        return None;
    }
    Some(
        unsafe { CStr::from_ptr(value) }
            .to_string_lossy()
            .into_owned(),
    )
}

unsafe fn dict_i32(dictionary: *mut GVariant, name: &CStr) -> Option<i32> {
    let format = c"i";
    let mut value = 0i32;
    (unsafe { g_variant_lookup(dictionary, name.as_ptr(), format.as_ptr(), &mut value) } != 0)
        .then_some(value)
}

unsafe fn dict_bool(dictionary: *mut GVariant, name: &CStr) -> Option<bool> {
    let format = c"b";
    let mut value = 0i32;
    (unsafe { g_variant_lookup(dictionary, name.as_ptr(), format.as_ptr(), &mut value) } != 0)
        .then_some(value != 0)
}

unsafe fn read_internal_panel(connection: *mut GDBusConnection) -> Result<Panel, String> {
    let parameters = unsafe {
        g_variant_new(
            c"(ss)".as_ptr(),
            c"org.gnome.Mutter.DisplayConfig".as_ptr(),
            c"Backlight".as_ptr(),
        )
    };
    let mut error = ptr::null_mut();
    let reply = unsafe {
        g_dbus_connection_call_sync(
            connection,
            c"org.gnome.Mutter.DisplayConfig".as_ptr(),
            c"/org/gnome/Mutter/DisplayConfig".as_ptr(),
            c"org.freedesktop.DBus.Properties".as_ptr(),
            c"Get".as_ptr(),
            parameters,
            ptr::null(),
            0,
            3000,
            ptr::null_mut(),
            &mut error,
        )
    };
    if reply.is_null() {
        return Err(unsafe { take_error(error, "Could not read Mutter Backlight") });
    }
    let wrapped = unsafe { g_variant_get_child_value(reply, 0) };
    let value = unsafe { g_variant_get_variant(wrapped) };
    let serial_value = unsafe { g_variant_get_child_value(value, 0) };
    let panels = unsafe { g_variant_get_child_value(value, 1) };
    let serial = unsafe { g_variant_get_uint32(serial_value) };
    let mut found = None;
    for index in 0..unsafe { g_variant_n_children(panels) } {
        let panel = unsafe { g_variant_get_child_value(panels, index) };
        let connector = unsafe { dict_string(panel, c"connector") };
        let active = unsafe { dict_bool(panel, c"active") }.unwrap_or(false);
        if let Some(connector) = connector.filter(|c| c.starts_with("eDP-") && active) {
            found = Some(Panel {
                serial,
                connector,
                minimum: unsafe { dict_i32(panel, c"min") },
                maximum: unsafe { dict_i32(panel, c"max") },
                value: unsafe { dict_i32(panel, c"value") },
            });
            unsafe {
                g_variant_unref(panel);
            }
            break;
        }
        unsafe {
            g_variant_unref(panel);
        }
    }
    unsafe {
        g_variant_unref(panels);
        g_variant_unref(serial_value);
        g_variant_unref(value);
        g_variant_unref(wrapped);
        g_variant_unref(reply);
    }
    found.ok_or_else(|| "No active internal backlight".to_owned())
}

unsafe fn take_error(error: *mut GError, fallback: &str) -> String {
    if error.is_null() {
        return fallback.to_owned();
    }
    let message = unsafe { CStr::from_ptr((*error).message) }
        .to_string_lossy()
        .into_owned();
    unsafe {
        g_error_free(error);
    }
    message
}

unsafe extern "C" fn method_call(
    _connection: *mut GDBusConnection,
    _sender: *const c_char,
    _object_path: *const c_char,
    _interface_name: *const c_char,
    method_name: *const c_char,
    parameters: *mut GVariant,
    invocation: *mut GDBusMethodInvocation,
    user_data: *mut c_void,
) {
    if user_data.is_null() {
        return;
    }
    let bridge = unsafe { &mut *(user_data.cast::<Bridge>()) };
    let method = unsafe { CStr::from_ptr(method_name) }.to_string_lossy();
    let argument = unsafe { g_variant_get_child_value(parameters, 0) };
    let result = match method.as_ref() {
        "SetDimming" => bridge.dim(unsafe { g_variant_get_boolean(argument) != 0 }),
        "SetAutoBrightnessTarget" => bridge.auto(unsafe { g_variant_get_double(argument) }),
        _ => Err(format!("Unknown method {method}")),
    };
    unsafe {
        g_variant_unref(argument);
    }
    match result {
        Ok(()) => unsafe {
            g_dbus_method_invocation_return_value(invocation, g_variant_new(c"()".as_ptr()))
        },
        Err(message) => {
            let message = CString::new(message)
                .unwrap_or_else(|_| CString::new("brightness bridge error").unwrap());
            unsafe {
                g_dbus_method_invocation_return_dbus_error(
                    invocation,
                    c"org.gnome.Shell.Brightness.Error".as_ptr(),
                    message.as_ptr(),
                );
            }
        }
    }
}

unsafe extern "C" fn get_property(
    connection: *mut GDBusConnection,
    _sender: *const c_char,
    _object_path: *const c_char,
    _interface_name: *const c_char,
    property_name: *const c_char,
    _user_data: *mut c_void,
    _error: *mut *mut GError,
) -> *mut GVariant {
    let property = unsafe { CStr::from_ptr(property_name) };
    if property != c"HasBrightnessControl" {
        return ptr::null_mut();
    }
    let available = unsafe { read_internal_panel(connection) }.is_ok();
    unsafe { g_variant_new(c"b".as_ptr(), i32::from(available)) }
}

unsafe extern "C" fn properties_changed(
    _proxy: *mut GDBusProxy,
    changed: *mut GVariant,
    _invalidated: *mut *mut c_char,
    user_data: *mut c_void,
) {
    if !user_data.is_null() {
        unsafe {
            (&mut *user_data.cast::<Bridge>()).changed(changed);
        }
    }
}

fn new_bridge() -> Result<*mut Bridge, String> {
    unsafe {
        let mut error = ptr::null_mut();
        let connection = g_bus_get_sync(2, ptr::null_mut(), &mut error);
        if connection.is_null() {
            return Err(take_error(error, "Could not connect to session bus"));
        }
        let display = g_dbus_proxy_new_sync(
            connection,
            0,
            ptr::null_mut(),
            c"org.gnome.Mutter.DisplayConfig".as_ptr(),
            c"/org/gnome/Mutter/DisplayConfig".as_ptr(),
            c"org.gnome.Mutter.DisplayConfig".as_ptr(),
            ptr::null_mut(),
            &mut error,
        );
        if display.is_null() {
            return Err(take_error(error, "Could not create Mutter display proxy"));
        }
        let settings = g_settings_new(c"org.gnome.settings-daemon.plugins.power".as_ptr());
        if settings.is_null() {
            return Err("Could not load power settings schema".into());
        }
        Ok(Box::into_raw(Box::new(Bridge {
            connection: g_dbus_proxy_get_connection(display),
            display,
            settings,
            state: BridgeState::default(),
        })))
    }
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            ExitCode::from(1)
        }
    }
}

fn run() -> Result<(), String> {
    let bridge = new_bridge()?;
    unsafe {
        let mut error = ptr::null_mut();
        let node = g_dbus_node_info_new_for_xml(XML.as_ptr(), &mut error);
        if node.is_null() {
            return Err(take_error(
                error,
                "Invalid brightness bridge introspection XML",
            ));
        }
        let interface =
            g_dbus_node_info_lookup_interface(node, c"org.gnome.Shell.Brightness".as_ptr());
        let vtable = GDBusInterfaceVTable {
            method_call: Some(method_call),
            get_property: Some(get_property),
            set_property: ptr::null(),
            padding: [ptr::null(); 8],
        };
        let registration = g_dbus_connection_register_object(
            (*bridge).connection,
            c"/org/gnome/Shell/Brightness".as_ptr(),
            interface,
            &vtable,
            bridge.cast(),
            ptr::null_mut(),
            &mut error,
        );
        g_dbus_node_info_unref(node);
        if registration == 0 {
            return Err(take_error(
                error,
                "Could not register brightness bridge object",
            ));
        }
        let owner = g_bus_own_name_on_connection(
            (*bridge).connection,
            c"org.gnome.Shell.Brightness".as_ptr(),
            0,
            ptr::null_mut(),
            ptr::null_mut(),
            ptr::null_mut(),
            ptr::null_mut(),
        );
        if owner == 0 {
            return Err("Could not own GNOME brightness D-Bus name".into());
        }
        let handler: unsafe extern "C" fn() = std::mem::transmute::<
            unsafe extern "C" fn(*mut GDBusProxy, *mut GVariant, *mut *mut c_char, *mut c_void),
            unsafe extern "C" fn(),
        >(properties_changed);
        g_signal_connect_data(
            (*bridge).display.cast(),
            c"g-properties-changed".as_ptr(),
            handler as *const c_void,
            bridge.cast(),
            ptr::null_mut(),
            0,
        );
        let main_loop = g_main_loop_new(ptr::null_mut(), 0);
        g_main_loop_run(main_loop);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn panel(value: i32) -> Panel {
        Panel {
            serial: 3,
            connector: "eDP-1".into(),
            minimum: Some(5),
            maximum: Some(500),
            value: Some(value),
        }
    }

    #[test]
    fn dim_restores_saved_level_when_no_manual_change_occurs() {
        let mut state = BridgeState::default();
        let target = state.dim_target(true, 315, 500, 30).unwrap();
        assert_eq!(target.round_ties_even() as i32, 150);
        state.record_set(150);
        assert_eq!(state.last_set, Some(150));
        assert_eq!(state.dim_target(true, 150, 500, 30), Some(150.0));
        assert_eq!(state.saved, Some(315));
        let restored = state.dim_target(false, 150, 500, 30);
        assert_eq!(restored, Some(315.0));
        state.record_set(315);
        state.saved = None;
        assert_eq!(state.saved, None);
    }

    #[test]
    fn manual_change_while_dimmed_is_preserved() {
        let mut state = BridgeState::default();
        assert_eq!(state.dim_target(true, 315, 500, 30), Some(150.0));
        state.record_set(150);
        assert_eq!(state.dim_target(false, 250, 500, 30), None);
        state.saved = None;
        assert_eq!(state.saved, None);
    }

    #[test]
    fn disabled_dimming_and_auto_do_not_change_display() {
        let state = BridgeState::default();
        assert!(!state.dim_allowed(true, false));
        assert!(!state.auto_allowed(0.8, false).unwrap());
        assert_eq!(state.saved, None);
    }

    #[test]
    fn auto_target_validation_and_panel_clamp_match_contract() {
        let mut state = BridgeState::default();
        for target in [-1.0, 1.1, f64::NAN, f64::INFINITY] {
            assert!(state.auto_allowed(target, true).is_err());
        }
        assert_eq!(state.auto_value(1.0, &panel(315)).unwrap(), 500.0);
        assert_eq!(state.auto_value(0.0, &panel(315)).unwrap(), 5.0);
        state.record_set(500);
        assert_eq!(state.last_seen, Some(500));
    }

    #[test]
    fn auto_is_ignored_during_dimming_and_user_brightness_clears_saved_value() {
        let mut state = BridgeState::default();
        state.dim_target(true, 315, 500, 30);
        assert!(!state.auto_allowed(0.9, true).unwrap());
        assert_eq!(state.auto_value(0.9, &panel(150)).unwrap(), 450.5);
        assert!(state.observe(250));
        assert_eq!(state.saved, None);
        assert!(!state.observe(250));
    }
}
