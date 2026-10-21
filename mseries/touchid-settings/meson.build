project('mseries-touchid-settings', 'vala', 'c', version: '0.1.0')

switchboard = dependency('switchboard-3')
plugsdir = switchboard.get_variable(pkgconfig: 'plugsdir')

deps = [
    dependency('glib-2.0'),
    dependency('gio-2.0'),
    dependency('gobject-2.0'),
    dependency('gtk4'),
    dependency('libadwaita-1', version: '>= 1.6'),
    dependency('gee-0.8'),
    meson.get_compiler('c').find_library('m', required: false),
]

page_sources = files(
    'Fprint.vala',
    'FingerprintArt.vala',
    'EnrollDialog.vala',
    'TouchIdPage.vala',
)

shared_module(
    'mseries-touchid',
    'Plug.vala',
    page_sources,
    dependencies: deps + [switchboard],
    install: true,
    install_dir: join_paths(plugsdir, 'personal'),
)

# Development host for screenshots and the fake-fprintd tests; never installed.
executable(
    'mseries-touchid-preview',
    'Preview.vala',
    page_sources,
    dependencies: deps,
    install: false,
)

install_data(
    '../aurora-sep/mseries-aurora-touchid-apply-pam',
    install_dir: '/usr/local/sbin',
    install_mode: 'rwxr-xr-x',
)

install_data(
    'org.mseries.touchid.policy',
    install_dir: join_paths(get_option('datadir'), 'polkit-1', 'actions'),
)
