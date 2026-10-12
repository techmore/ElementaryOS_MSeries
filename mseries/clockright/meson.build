project('clockright', 'vala', version: '0.1.0', meson_version: '>= 0.59.0')

wingpanel_dep = dependency('wingpanel-9')
indicators_dir = wingpanel_dep.get_variable(pkgconfig: 'indicatorsdir')

shared_module(
  'clockright',
  'Indicator.vala',
  dependencies: [wingpanel_dep],
  install: true,
  install_dir: indicators_dir,
)
