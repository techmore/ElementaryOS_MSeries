#!/usr/bin/env python3
"""Wire UsageWidget into a freshly patched elementary panel-network checkout."""

from pathlib import Path
import sys


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text()
    if new in source:
        return
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"Expected one wiring point in {path}, found {count}: {old!r}")
    path.write_text(source.replace(old, new, 1))


root = Path(sys.argv[1])
meson = root / "meson.build"
popover = root / "src/Widgets/PopoverWidget.vala"

replace_once(
    meson,
    "    'src/Widgets/ThroughputWidget.vala',\n",
    "    'src/Widgets/ThroughputWidget.vala',\n"
    "    'src/Widgets/UsageWidget.vala',\n",
)
replace_once(
    meson,
    "        polkit_dep,\n",
    "        polkit_dep,\n"
    "        dependency('sqlite3'),\n"
    "        meson.get_compiler('vala').find_library('sqlite3'),\n",
)
replace_once(
    popover,
    "    private Gtk.Revealer toggle_revealer;\n",
    "    private Gtk.Revealer toggle_revealer;\n"
    "    private UsageWidget usage_widget;\n",
)
replace_once(
    popover,
    "        append (throughput_separator);\n",
    "        append (throughput_separator);\n"
    "        // Per-app, per-host and DNS totals from the local usage logger.\n"
    "        usage_widget = new UsageWidget ();\n"
    "        append (usage_widget);\n",
)
replace_once(
    popover,
    "    public void opened () {\n",
    "    public void opened () {\n"
    "        usage_widget.opened ();\n",
)
replace_once(
    popover,
    "    public void closed () {\n",
    "    public void closed () {\n"
    "        usage_widget.closed ();\n",
)
