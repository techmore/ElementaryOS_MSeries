project('signal-wingpanel', 'vala', version: '0.1.0', meson_version: '>= 0.59.0')

wingpanel_dep = dependency('wingpanel-9')
gtk_dep = dependency('gtk4')
gee_dep = dependency('gee-0.8')
indicators_dir = wingpanel_dep.get_variable(pkgconfig: 'indicatorsdir')

shared_module(
  'signaltray',
  'Indicator.vala',
  dependencies: [wingpanel_dep, gtk_dep, gee_dep],
  vala_args: ['--pkg=posix'],
  install: true,
  install_dir: indicators_dir,
)

install_data(
  'resources/org.signal.Signal.png',
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', '64x64', 'apps'),
)
