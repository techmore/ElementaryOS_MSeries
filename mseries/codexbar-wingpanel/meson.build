project('codexbar-wingpanel', 'vala', version: '0.1.0', meson_version: '>= 0.59.0')

libwingpanel_dep = dependency('wingpanel-9')
granite_dep = dependency('granite-7')
json_dep = dependency('json-glib-1.0')
indicators_dir = libwingpanel_dep.get_variable(pkgconfig: 'indicatorsdir')

shared_module(
  'codexbar',
  'Indicator.vala',
  dependencies: [libwingpanel_dep, granite_dep, json_dep],
  install: true,
  install_dir: indicators_dir,
)

install_data(
  'icons/openai.svg',
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps'),
  rename: 'mseries-codexbar-openai.svg',
)
