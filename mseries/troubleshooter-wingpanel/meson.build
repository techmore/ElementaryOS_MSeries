project('mseries-troubleshooter-wingpanel', 'vala', version: '0.1.0', meson_version: '>= 0.59.0')
wingpanel_dep = dependency('wingpanel-9')
shared_module('mseries-troubleshooter', 'Indicator.vala',
  dependencies: [wingpanel_dep, dependency('json-glib-1.0'), dependency('gio-unix-2.0')],
  install: true, install_dir: wingpanel_dep.get_variable(pkgconfig: 'indicatorsdir'))

install_data('mseries-robot-symbolic.svg', install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps'))
