project('mseries-remote-desktop-native', 'vala', 'c', version: '0.1.0', meson_version: '>= 0.59.0')

gtk_dep = dependency('gtk4', version: '>= 4.12')
granite_dep = dependency('granite-7', version: '>= 7.7.0')
json_dep = dependency('json-glib-1.0')
gio_dep = dependency('gio-2.0')
m_dep = meson.get_compiler('c').find_library('m')

add_project_arguments('-DGETTEXT_PACKAGE="mseries-remote"', language: 'c')

model = files('src/Model.vala')
service = files('src/Service.vala')
ui = files('src/UiUtil.vala', 'src/QrArea.vala', 'src/ConsentPrompt.vala', 'src/MainWindow.vala')


test_model = executable('test-model', model, 'tests/test-model.vala', dependencies: [json_dep, gio_dep])
test('remote-model', test_model)

executable(
  'mseries-remote',
  model, service, ui, 'src/Application.vala',
  dependencies: [gtk_dep, granite_dep, json_dep, gio_dep, m_dep],
  install: true,
)

# Headless render probe (not installed): see probe/run-probe.sh.
executable(
  'render-probe',
  model, service, ui, 'probe/render-probe.vala',
  dependencies: [gtk_dep, granite_dep, json_dep, gio_dep, m_dep],
  build_by_default: false,
)

wingpanel_dep = dependency('wingpanel-9', required: false)
if wingpanel_dep.found()
  indicators_dir = wingpanel_dep.get_variable(pkgconfig: 'indicatorsdir')
  shared_module(
    'remote',
    model, service, 'src/UiUtil.vala', 'indicator/Indicator.vala',
    dependencies: [wingpanel_dep, gtk_dep, granite_dep, json_dep, gio_dep],
    install: true,
    install_dir: indicators_dir,
  )
endif

icon_dir = join_paths(get_option('datadir'), 'icons', 'hicolor', 'symbolic', 'apps')
install_data(
  'data/mseries-remote-symbolic.svg',
  'data/mseries-remote-sharing-symbolic.svg',
  install_dir: icon_dir,
)
install_data('data/io.github.techmore.RemoteDesktop.desktop', install_dir: join_paths(get_option('datadir'), 'applications'))
install_data('data/io.github.techmore.RemoteDesktop.autostart.desktop',
  install_dir: join_paths(get_option('sysconfdir'), 'xdg', 'autostart'),
  rename: 'io.github.techmore.RemoteDesktop.desktop')
