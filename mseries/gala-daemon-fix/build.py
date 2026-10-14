#!/usr/bin/python3
"""Build only Gala's GTK4 helper; never replace the window manager or Mutter."""
from pathlib import Path
import subprocess
import sys

source, output = (Path(arg).resolve() for arg in sys.argv[1:])
output.mkdir(parents=True, exist_ok=True)
config = (source / 'config.vala.in').read_text()
for key, value in {'GETTEXT_PACKAGE': 'gala', 'LOCALEDIR': '/usr/share/locale',
                   'VERSION': '8.6.2', 'PLUGINDIR': '/usr/lib/aarch64-linux-gnu/gala/plugins'}.items():
    config = config.replace('@' + key + '@', value)
(output / 'config.vala').write_text(config)
for xml, directory, name in [('gala.gresource.xml', 'data', 'resources.c'),
                              ('gala-osk-layouts.gresource.xml', 'data/osk-layouts', 'osk-resources.c')]:
    subprocess.run(['glib-compile-resources', str(source / 'data' / xml),
                    '--sourcedir=' + str(source / directory), '--generate-source',
                    '--target=' + str(output / name)], check=True)
args = ['valac', '--directory', str(output), '--pkg', 'gtk4', '--pkg', 'granite-7',
        '--pkg', 'ibus-1.0', '--pkg', 'json-glib-1.0', '--pkg', 'gio-2.0',
        '-X', '-DGETTEXT_PACKAGE="gala"', '-X', '-lm', '-o', str(output / 'gala-daemon'),
        str(output / 'config.vala'), str(output / 'resources.c'), str(output / 'osk-resources.c')]
subprocess.run(args + sorted(str(path) for path in (source / 'daemon').rglob('*.vala')), check=True)
