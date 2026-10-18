project(
    'gala-drawers',
    'vala', 'c',
    version: '0.1.0',
    meson_version: '>= 0.59.0'
)

gala_dep = dependency('gala')
glib_dep = dependency('glib-2.0', version: '>= 2.74')
gio_unix_dep = dependency('gio-unix-2.0')
gee_dep = dependency('gee-0.8')

# Gala ships its mutter/clutter/cogl/mtk vapi files in its own source tree
# (vapi/), they are not installed. Point -Dvapidir= at a Gala checkout's vapi
# directory, e.g. the one mseries/install-gala-screen-corners.sh already clones.
vapidir = get_option('vapidir')
vala_args = ['--target-glib=2.74', '--pkg=mutter-clutter-' + get_option('mutter_version'),
             '--pkg=mutter-cogl-' + get_option('mutter_version'),
             '--pkg=mutter-mtk-' + get_option('mutter_version')]
if vapidir != ''
    vala_args += '--vapidir=' + vapidir
endif
add_project_arguments(vala_args, language: 'vala')

# Install into the running compositor's PLUGINDIR. On Ubuntu/Debian the libdir
# is multiarch (lib/aarch64-linux-gnu), which matches Gala's Config.PLUGINDIR.
# Override with -Dplugindir=... when targeting the patched Gala under
# /usr/local/lib/mseries/gala.
plugindir = get_option('plugindir')
if plugindir == ''
    plugindir = join_paths(get_option('libdir'), 'gala', 'plugins')
endif

shared_library(
    'gala-drawers',
    'Main.vala',
    dependencies: [gala_dep, glib_dep, gio_unix_dep, gee_dep],
    install: true,
    install_dir: plugindir
)

install_data(
    'org.pantheon.gala.plugins.drawers.gschema.xml',
    install_dir: join_paths(get_option('datadir'), 'glib-2.0', 'schemas')
)

meson.add_install_script('glib-compile-schemas', join_paths(get_option('prefix'), get_option('datadir'), 'glib-2.0', 'schemas'))
