project('claude-pantheon-indicator', 'vala', 'c', version: '0.1.0', meson_version: '>= 0.59.0')

libwingpanel_dep = dependency('wingpanel-9')
granite_dep = dependency('granite-7', version: '>= 7.7.0')
json_dep = dependency('json-glib-1.0')
gee_dep = dependency('gee-0.8')
indicators_dir = libwingpanel_dep.get_variable(pkgconfig: 'indicatorsdir')

deps = [libwingpanel_dep, granite_dep, json_dep, gee_dep, dependency('gio-unix-2.0')]
shared_view_sources = [
    configure_file(input: '../../../mseries/dock-taskbar/TaskbarT3RPopover.vala',
                   output: 'TaskbarT3RPopover.vala', copy: true),
    configure_file(input: '../../../mseries/codexbar-wingpanel/JsonBoundary.vala',
                   output: 'JsonBoundary.vala', copy: true),
    configure_file(input: '../../../mseries/codexbar-wingpanel/HelperProcess.vala',
                   output: 'HelperProcess.vala', copy: true),
]

shared_module(
    'claude-pantheon',
    'src/Indicator.vala',
    shared_view_sources,
    dependencies: deps,
    install: true,
    install_dir: indicators_dir,
)

# Headless probe: the indicator built from a fixture, texts checked, optional PNG (see probe/probe.vala).
probe = executable('probe', 'src/Indicator.vala', 'probe/probe.vala', shared_view_sources, dependencies: deps)
test('indicator-probe', probe, args: [meson.current_source_dir() / 'probe/status-fixture.json'],
     env: ['GDK_BACKEND=x11', 'GSETTINGS_BACKEND=memory'], workdir: meson.current_source_dir())
