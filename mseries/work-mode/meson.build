project('mseries-work-mode', 'vala', version: '0.1.0')

libdir = get_option('libdir')
switchboard = dependency('switchboard-3')
plugsdir = switchboard.get_variable(pkgconfig: 'plugsdir')

shared_module(
    'mseries-work-mode',
    'Plug.vala',
    dependencies: [
        dependency('glib-2.0'),
        dependency('gio-2.0'),
        dependency('gtk4'),
        dependency('libadwaita-1'),
        dependency('granite-7'),
        dependency('gee-0.8'),
        switchboard,
    ],
    install: true,
    install_dir: join_paths(plugsdir, 'personal'),
)

install_data('io.elementary.mseries.work-mode.gschema.xml',
    install_dir: join_paths(get_option('datadir'), 'glib-2.0', 'schemas'))

install_data(
    'work-mode-azure-bloom.png',
    'work-mode-blue-flow.png',
    'work-mode-blue-ribbons.png',
    'work-mode-violet-arc.png',
    'work-mode-forest-flow.png',
    install_dir: join_paths(get_option('datadir'), 'backgrounds', 'mseries'))
