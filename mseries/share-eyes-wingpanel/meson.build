project('share-eyes-wingpanel', 'vala', version: '0.1.0', meson_version: '>= 0.59.0')

libwingpanel_dep = dependency('wingpanel-9')
granite_dep = dependency('granite-7', version: '>= 7.7.0')
json_dep = dependency('json-glib-1.0')
indicators_dir = libwingpanel_dep.get_variable(pkgconfig: 'indicatorsdir')

shared_module(
  'shareeyes',
  'Indicator.vala',
  'ShareState.vala',
  dependencies: [libwingpanel_dep, granite_dep, json_dep],
  install: true,
  install_dir: indicators_dir,
)

share_state_test = executable('test-share-state', 'ShareState.vala', 'test-share-state.vala', dependencies: json_dep)
test('share-state', share_state_test)

install_data(
  'icons/eyes.svg',
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps'),
  rename: 'mseries-share-eyes-symbolic.svg',
)

# Headless render probe (not installed): see probe/run-probe.sh.
executable(
  'render-probe',
  'Indicator.vala', 'ShareState.vala', 'probe/render-probe.vala',
  dependencies: [libwingpanel_dep, granite_dep, json_dep],
  build_by_default: false,
)
