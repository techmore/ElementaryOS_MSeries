/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Pure decisions for the Dock & Taskbar page. No GTK, no GSettings: this file
 * is compiled into the unit test as well, so every state the page can show is
 * testable without a display. */
namespace MSeriesDockSwitcher {
    public enum Style {
        TASKBAR,
        DOCK
    }

    /* What the page can honestly offer, from what was found on this machine. */
    public enum Availability {
        READY,
        /* The dock schema has no taskbar-mode key: a stock elementary dock. */
        NO_TASKBAR_SUPPORT,
        /* io.elementary.dock is not installed at all. */
        NO_DOCK,
        /* The owner's opt-out marker keeps the dock from starting. */
        DOCK_OFF
    }

    public Availability availability (bool schema_found, bool has_taskbar_key, bool opt_out_marker) {
        if (!schema_found) {
            return Availability.NO_DOCK;
        }
        if (opt_out_marker) {
            return Availability.DOCK_OFF;
        }
        if (!has_taskbar_key) {
            return Availability.NO_TASKBAR_SUPPORT;
        }
        return Availability.READY;
    }

    /* Whether picking a style can be offered. The elementary dock itself is
     * always selectable when the dock is installed; only the taskbar needs the
     * patched build. DOCK_OFF is read-only: turning the dock back on is the
     * owner's deliberate action (removing the marker), not a switch here. */
    public bool can_choose (Availability availability) {
        return availability == Availability.READY;
    }

    public string banner_for (Availability availability) {
        switch (availability) {
            case Availability.NO_TASKBAR_SUPPORT:
                return "This dock build has no Windows 11 taskbar. Install the M-Series dock to enable the choice.";
            case Availability.NO_DOCK:
                return "The elementary dock isn't installed on this system.";
            case Availability.DOCK_OFF:
                return "The dock is turned off on this account. Remove ~/.config/mseries/dock/user-disabled to bring it back.";
            default:
                return "";
        }
    }

    public string style_name (Style style) {
        return style == Style.TASKBAR ? "Windows 11 taskbar" : "elementary dock";
    }

    /* Order and wording of Hide automatically. The nicks are the dock schema's
     * HideMode enum; the labels follow elementary's own Desktop page. */
    public const string[] AUTOHIDE_NICKS = {
        "never",
        "maximized-focus-window",
        "overlapping-focus-window",
        "overlapping-window",
        "always"
    };

    public const string[] AUTOHIDE_LABELS = {
        "Never",
        "Focused window maximized",
        "Focused window overlaps",
        "Any window overlaps",
        "Always"
    };

    /* Index of nick in the list above; -1 for a value this page doesn't know,
     * so the row can show it as unchanged instead of guessing. */
    public int autohide_index (string nick) {
        for (var i = 0; i < AUTOHIDE_NICKS.length; i++) {
            if (AUTOHIDE_NICKS[i] == nick) {
                return i;
            }
        }
        return -1;
    }

    public string? autohide_nick_at (int index) {
        if (index < 0 || index >= AUTOHIDE_NICKS.length) {
            return null;
        }
        return AUTOHIDE_NICKS[index];
    }

    /* Wording of the confirmation toast; empty undo text when nothing changed. */
    public string switched_message (Style style) {
        return "Switched to the %s".printf (style_name (style));
    }
}
