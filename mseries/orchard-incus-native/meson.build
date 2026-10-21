project('orchard-incus', ['vala', 'c'],
  version: '0.1.0',
  meson_version: '>= 0.59.0')


app_sources = files(
'src/IncusClient.vala',
  'src/ConfigText.vala',
  'src/Instance.vala',
  'src/MainWindow.vala',
  'src/Preferences.vala',
  'src/InstanceDetails.vala',
  'src/ResourceBrowser.vala',
  'src/Dashboard.vala',
  'src/Sparkline.vala',
  'src/DeviceEditor.vala',
  'src/CommandPalette.vala',
  'src/ModelService.vala',
  'src/ModelBridge.vala',
  'src/SandboxesWindow.vala',
  'src/SystemWindow.vala',
  'src/ImagePullWindow.vala',
  'src/MountsWindow.vala',
  'src/LogViewer.vala',
  'src/PodmanClient.vala',
  'src/PodmanPage.vala'
)
app_dependencies = [
dependency('gtk4'),
    dependency('granite-7'),
    dependency('libsecret-1'),
    dependency('libsoup-3.0'),
    dependency('json-glib-1.0'),
    dependency('gio-unix-2.0'),
]
executable('com.github.techmore.orchard-incus', 'src/Application.vala', app_sources,
  dependencies: app_dependencies, install: true)

install_data('data/com.github.techmore.orchard-incus.desktop',
  install_dir: get_option('datadir') / 'applications')

install_data('data/icons/com.github.techmore.orchard-incus.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps')
install_data('data/icons/orchard-incus-symbolic.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/status')

# Optional: the manager also builds on desktops without Wingpanel.
wingpanel = dependency('wingpanel-9', required: get_option('wingpanel'))
if wingpanel.found()
  indicator_module = shared_module('orchard-incus',
    'src/Indicator.vala', 'src/Sparkline.vala', 'src/IncusClient.vala', 'src/Instance.vala', 'src/Preferences.vala',
    dependencies: [wingpanel, dependency('libsoup-3.0'), dependency('json-glib-1.0'), dependency('gio-unix-2.0')],
    install: true,
    install_dir: wingpanel.get_variable(pkgconfig: 'indicatorsdir'))

  indicator_smoke = executable('orchard-indicator-smoke',
    'tests/indicator-smoke.vala', dependencies: [wingpanel])
  test('panel-count', find_program('python3'),
    args: [files('tests/test-indicator.py'), indicator_smoke.full_path(), indicator_module.full_path()],
    timeout: 20)
endif

client_smoke = executable('orchard-client-smoke',
  'tests/client-smoke.vala', 'src/ConfigText.vala', 'src/IncusClient.vala', 'src/Instance.vala', 'src/Preferences.vala',
  dependencies: [dependency('libsoup-3.0'), dependency('json-glib-1.0'), dependency('gio-unix-2.0')])
test('incus-client', find_program('python3'),
  args: [files('tests/test-client.py'), client_smoke.full_path()], timeout: 25)

model_smoke = executable('orchard-model-smoke',
  'tests/model-smoke.vala', 'src/ModelService.vala', 'src/ModelBridge.vala', 'src/Preferences.vala', 'src/IncusClient.vala', 'src/Instance.vala',
  dependencies: [dependency('gtk4'), dependency('libsecret-1'), dependency('libsoup-3.0'), dependency('json-glib-1.0'), dependency('gio-unix-2.0')])
test('model-client', find_program('python3'),
  args: [files('tests/test-model.py'), model_smoke.full_path()], timeout: 25)

ui_smoke = executable('orchard-ui-smoke', 'tests/ui-smoke.vala', app_sources, dependencies: app_dependencies)
test('native-windows', find_program('python3'), args: [files('tests/test-ui.py'), ui_smoke.full_path()], timeout: 25)

restart_smoke = executable('orchard-restart-smoke',
  'tests/restart-smoke.vala', 'src/IncusClient.vala', 'src/Instance.vala', 'src/Preferences.vala',
  dependencies: [dependency('libsoup-3.0'), dependency('json-glib-1.0'), dependency('gio-unix-2.0')])
test('restart-config', find_program('python3'), args: [files('tests/test-restart.py'), restart_smoke.full_path()], timeout: 25)

podman_smoke = executable('orchard-podman-smoke',
  'tests/podman-smoke.vala', 'src/PodmanClient.vala',
  dependencies: [dependency('json-glib-1.0'), dependency('gio-unix-2.0')])
test('podman-client', find_program('python3'), args: [files('tests/test-podman.py'), podman_smoke.full_path()], timeout: 25)
