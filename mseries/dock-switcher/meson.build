# GTK on this Mac: renderer, CSD shadow, cursor blink and animation rules in ../GTK-PERFORMANCE-ASAHI.md
project('mseries-dock-switcher', 'vala', 'c', version: '0.1.0')

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

state_sources = files('State.vala', 'DockModel.vala')
page_sources = files('Style.vala', 'Illustration.vala', 'DockPage.vala')

shared_module(
    'mseries-dock-taskbar',
    'Plug.vala',
    state_sources,
    page_sources,
    dependencies: deps + [switchboard],
    install: true,
    install_dir: join_paths(plugsdir, 'personal'),
)

# Development host for screenshots; never installed.
executable(
    'mseries-dock-switcher-preview',
    'Preview.vala',
    state_sources,
    page_sources,
    dependencies: deps,
    install: false,
)

# Logic and settings tests; no display needed. The test compiles its own
# fixture schemas into a temporary directory.
tests = executable(
    'test-dock-switcher',
    'tests/test-dock-switcher.vala',
    state_sources,
    dependencies: deps,
    install: false,
)
test('dock-switcher', tests,
    env: {'GSETTINGS_BACKEND': 'memory'},
)
