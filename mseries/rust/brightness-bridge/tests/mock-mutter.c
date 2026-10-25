#include <gio/gio.h>
#include <stdlib.h>

#define NAME "org.gnome.Mutter.DisplayConfig"
#define PATH "/org/gnome/Mutter/DisplayConfig"
#define IFACE "org.gnome.Mutter.DisplayConfig"
#define MOCK_IFACE "org.example.MockDisplay"

static guint32 serial = 41;
static gint brightness = 315;
static GDBusConnection *connection;
static GMainLoop *loop;

static const gchar xml[] =
    "<node>"
    "<interface name='org.gnome.Mutter.DisplayConfig'>"
    "<method name='SetBacklight'><arg type='u' direction='in'/>"
    "<arg type='s' direction='in'/><arg type='i' direction='in'/></method>"
    "<property name='Backlight' type='(uaa{sv})' access='read'/>"
    "</interface>"
    "<interface name='org.example.MockDisplay'>"
    "<method name='Ping'/>"
    "<method name='GetValue'><arg type='i' direction='out'/></method>"
    "<method name='ExternalSet'><arg type='i' direction='in'/></method>"
    "</interface>"
    "</node>";

static GVariant *backlight_value(void) {
    GVariantBuilder panel;
    GVariantBuilder panels;
    g_variant_builder_init(&panel, G_VARIANT_TYPE("a{sv}"));
    g_variant_builder_add(&panel, "{sv}", "connector", g_variant_new_string("eDP-1"));
    g_variant_builder_add(&panel, "{sv}", "active", g_variant_new_boolean(TRUE));
    g_variant_builder_add(&panel, "{sv}", "min", g_variant_new_int32(5));
    g_variant_builder_add(&panel, "{sv}", "max", g_variant_new_int32(500));
    g_variant_builder_add(&panel, "{sv}", "value", g_variant_new_int32(brightness));
    g_variant_builder_init(&panels, G_VARIANT_TYPE("aa{sv}"));
    g_variant_builder_add_value(&panels, g_variant_builder_end(&panel));
    return g_variant_new("(u@aa{sv})", serial, g_variant_builder_end(&panels));
}

static void emit_backlight_changed(void) {
    GVariantBuilder changed;
    GVariantBuilder invalidated;
    GError *error = NULL;
    g_variant_builder_init(&changed, G_VARIANT_TYPE("a{sv}"));
    g_variant_builder_add(&changed, "{sv}", "Backlight", backlight_value());
    g_variant_builder_init(&invalidated, G_VARIANT_TYPE("as"));
    g_dbus_connection_emit_signal(connection, NULL, PATH,
        "org.freedesktop.DBus.Properties", "PropertiesChanged",
        g_variant_new("(s@a{sv}@as)", IFACE,
            g_variant_builder_end(&changed), g_variant_builder_end(&invalidated)),
        &error);
    if (error) {
        g_printerr("could not emit Backlight change: %s\n", error->message);
        g_error_free(error);
    }
}

static GVariant *get_property(GDBusConnection *bus, const gchar *sender,
    const gchar *path, const gchar *interface, const gchar *property,
    GError **error, gpointer user_data) {
    (void)bus; (void)sender; (void)path; (void)user_data;
    if (g_str_equal(interface, IFACE) && g_str_equal(property, "Backlight"))
        return backlight_value();
    g_set_error(error, G_IO_ERROR, G_IO_ERROR_NOT_SUPPORTED, "unknown property");
    return NULL;
}

static void method_call(GDBusConnection *bus, const gchar *sender,
    const gchar *path, const gchar *interface, const gchar *method,
    GVariant *parameters, GDBusMethodInvocation *invocation, gpointer user_data) {
    (void)bus; (void)sender; (void)path; (void)user_data;
    if (g_str_equal(interface, IFACE) && g_str_equal(method, "SetBacklight")) {
        guint32 requested_serial;
        const gchar *connector;
        gint value;
        g_variant_get(parameters, "(u&si)", &requested_serial, &connector, &value);
        if (requested_serial != serial || !g_str_equal(connector, "eDP-1")) {
            g_dbus_method_invocation_return_dbus_error(invocation,
                "org.gnome.Mutter.DisplayConfig.Error", "stale serial or connector");
            return;
        }
        brightness = CLAMP(value, 5, 500);
        emit_backlight_changed();
        g_dbus_method_invocation_return_value(invocation, g_variant_new("()"));
        return;
    }
    if (g_str_equal(interface, MOCK_IFACE) && g_str_equal(method, "Ping")) {
        g_dbus_method_invocation_return_value(invocation, g_variant_new("()"));
        return;
    }
    if (g_str_equal(interface, MOCK_IFACE) && g_str_equal(method, "GetValue")) {
        g_dbus_method_invocation_return_value(invocation, g_variant_new("(i)", brightness));
        return;
    }
    if (g_str_equal(interface, MOCK_IFACE) && g_str_equal(method, "ExternalSet")) {
        g_variant_get(parameters, "(i)", &brightness);
        emit_backlight_changed();
        g_dbus_method_invocation_return_value(invocation, g_variant_new("()"));
        return;
    }
    g_dbus_method_invocation_return_dbus_error(invocation,
        "org.freedesktop.DBus.Error.UnknownMethod", method);
}

int main(void) {
    GError *error = NULL;
    GDBusNodeInfo *node = g_dbus_node_info_new_for_xml(xml, &error);
    if (!node) {
        g_printerr("invalid mock interface: %s\n", error->message);
        g_error_free(error);
        return 1;
    }
    connection = g_bus_get_sync(G_BUS_TYPE_SESSION, NULL, &error);
    if (!connection) {
        g_printerr("session bus unavailable: %s\n", error->message);
        g_error_free(error);
        return 1;
    }
    static const GDBusInterfaceVTable vtable = { method_call, get_property, NULL, { NULL } };
    const gchar *interfaces[] = { IFACE, MOCK_IFACE };
    for (guint i = 0; i < G_N_ELEMENTS(interfaces); i++) {
        GDBusInterfaceInfo *info = g_dbus_node_info_lookup_interface(node, interfaces[i]);
        if (!g_dbus_connection_register_object(connection, PATH, info, &vtable,
                NULL, NULL, &error)) {
            g_printerr("could not register mock interface: %s\n", error->message);
            g_error_free(error);
            return 1;
        }
    }
    guint owner = g_bus_own_name_on_connection(connection, NAME,
        G_BUS_NAME_OWNER_FLAGS_NONE, NULL, NULL, NULL, NULL);
    if (!owner) return 1;
    loop = g_main_loop_new(NULL, FALSE);
    g_main_loop_run(loop);
    return 0;
}
