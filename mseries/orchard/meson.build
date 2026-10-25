# GTK on this Mac: renderer, CSD shadow, cursor blink and animation rules in ../GTK-PERFORMANCE-ASAHI.md
project('orchard', ['vala', 'c'],
  version: '1.0.0',
  meson_version: '>= 1.0.0',
  default_options: ['warning_level=2']
)

gtk = dependency('gtk4', version: '>= 4.12')
granite = dependency('granite-7', version: '>= 7.0')
json = dependency('json-glib-1.0')
soup = dependency('libsoup-3.0')
secret = dependency('libsecret-1')
gio_unix = dependency('gio-unix-2.0')

gnome = import('gnome')
resources = gnome.compile_resources('orchard-resources',
  'data/orchard.gresource.xml',
  source_dir: 'data'
)

add_project_arguments(['--pkg', 'posix'], language: 'vala')

config = configure_file(
  input: 'src/config.vala.in',
  output: 'config.vala',
  configuration: {'VERSION': meson.project_version(), 'MACOS_CHECK_SOURCE': meson.current_source_dir() / 'launcher/macos-check.py'}
)

# Machines (QEMU/KVM): Machine Lab's code.
machine_sources = files(
  'src/machine.vala', 'src/page.vala', 'src/viewer.vala', 'src/macexp.vala', 'src/clipsync.vala',
  'src/clipboard.vala', 'src/display.vala', 'src/snapshots.vala', 'src/images.vala', 'src/unattend.vala',
  'src/virtiowin.vala', 'src/windows-ui.vala'
)
# Incus and Podman: Orchard for Incus's clients and windows.
incus_sources = files(
  'src/IncusClient.vala', 'src/ConfigText.vala', 'src/Instance.vala', 'src/Preferences.vala',
  'src/ResourceBrowser.vala', 'src/Dashboard.vala', 'src/Sparkline.vala', 'src/DeviceEditor.vala',
  'src/CommandPalette.vala', 'src/ModelService.vala', 'src/ModelBridge.vala', 'src/SandboxesWindow.vala',
  'src/SystemWindow.vala', 'src/ImagePullWindow.vala', 'src/MountsWindow.vala', 'src/LogViewer.vala',
  'src/PodmanClient.vala', 'src/PodmanDetails.vala', 'src/PodmanPage.vala'
)
# The merged window: sidebar sections and the Incus pages in the Machines style.
app_sources = files('src/main.vala', 'src/sidebar.vala', 'src/incus-page.vala')
entry_source = files('src/entry.vala')
app_dependencies = [gtk, granite, json, soup, secret, gio_unix]

executable('orchard',
  entry_source, app_sources, machine_sources, incus_sources, config, resources,
  dependencies: app_dependencies,
  install: true
)

install_data('data/com.github.techmore.orchard.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps')
install_data('data/orchard-incus-symbolic.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/status')
install_data('data/com.github.techmore.orchard.metainfo.xml',
  install_dir: get_option('datadir') / 'metainfo')
install_data('data/com.github.techmore.orchard.desktop',
  install_dir: get_option('datadir') / 'applications')
install_data('launcher/run-vm.sh',
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
  rename: 'machine-lab-run-vm')
install_data('launcher/prepare-latest-omarchy.py',
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
  rename: 'machine-lab-prepare-omarchy')
install_data('launcher/macos-check.py',
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
  rename: 'machine-lab-macos-check')

# ---- Machines tests (Machine Lab) ----

test_exe = executable('test-machine',
  'tests/test-machine.vala', 'src/machine.vala', 'src/IncusClient.vala', 'src/Instance.vala', 'src/Preferences.vala', 'src/snapshots.vala', 'src/images.vala', 'src/unattend.vala', 'src/virtiowin.vala',
  dependencies: [gtk, gio_unix, json, soup],
  install: false
)
test('machine logic', test_exe,
  env: {'FAKE_QMP': meson.current_source_dir() / 'tests/fake-qmp.py'},
  timeout: 60
)

test('QMP fixture reaping and output EOF', find_program('python3'),
  args: [files('tests/test-qmp-teardown.py'), test_exe, files('tests/fake-qmp.py')],
  timeout: 30
)

unattend_test_exe = executable('test-unattend',
  'tests/test-unattend.vala', 'src/machine.vala', 'src/unattend.vala', 'src/virtiowin.vala',
  dependencies: [gtk, gio_unix, json],
  install: false
)
test('windows answer file and virtio-win policy', unattend_test_exe, timeout: 120)

clipboard_test_exe = executable('test-clipboard',
  'tests/test-clipboard.vala', 'src/clipsync.vala',
  dependencies: [dependency('gio-2.0'), gio_unix],
  install: false
)
test('clipboard sync against a fake QEMU peer', clipboard_test_exe, timeout: 120)

display_test_exe = executable('test-display',
  'tests/test-display.vala', 'src/display.vala',
  dependencies: [dependency('gio-2.0'), gio_unix],
  install: false
)
test('display stream and resize against a fake QEMU peer', display_test_exe, timeout: 120)

test('macOS readiness', find_program('python3'),
  args: [meson.current_source_dir() / 'tests/test-macos-check.py'])

# ---- Incus and Podman tests (Orchard for Incus) ----

client_smoke = executable('orchard-client-smoke',
  'tests/client-smoke.vala', 'src/ConfigText.vala', 'src/IncusClient.vala', 'src/Instance.vala', 'src/Preferences.vala',
  dependencies: [soup, json, gio_unix])
test('incus-client', find_program('python3'),
  args: [files('tests/test-client.py'), client_smoke.full_path()], timeout: 25)

model_smoke = executable('orchard-model-smoke',
  'tests/model-smoke.vala', 'src/ModelService.vala', 'src/ModelBridge.vala', 'src/Preferences.vala', 'src/IncusClient.vala', 'src/Instance.vala',
  dependencies: [gtk, secret, soup, json, gio_unix])
test('model-client', find_program('python3'),
  args: [files('tests/test-model.py'), model_smoke.full_path()], timeout: 25)

restart_smoke = executable('orchard-restart-smoke',
  'tests/restart-smoke.vala', 'src/IncusClient.vala', 'src/Instance.vala', 'src/Preferences.vala',
  dependencies: [soup, json, gio_unix])
test('restart-config', find_program('python3'), args: [files('tests/test-restart.py'), restart_smoke.full_path()], timeout: 25)

podman_smoke = executable('orchard-podman-smoke',
  'tests/podman-smoke.vala', 'src/PodmanClient.vala',
  dependencies: [json, gio_unix])
test('podman-client', find_program('python3'), args: [files('tests/test-podman.py'), podman_smoke.full_path()], timeout: 25)

# The whole window against a fake Incus socket and a fake podman: sidebar sections, the Incus
# and Podman pages, every secondary window, and the GSK capture path used for the docs.
ui_smoke = executable('orchard-ui-smoke',
  'tests/ui-smoke.vala', app_sources, machine_sources, incus_sources, config, resources,
  dependencies: app_dependencies)
test('native-windows', find_program('python3'), args: [files('tests/test-ui.py'), ui_smoke.full_path()], timeout: 40)

# Optional: the Wingpanel indicator (installs under /usr/lib, so it needs root; off for a ~/.local install).
wingpanel = dependency('wingpanel-9', required: get_option('wingpanel'))
if wingpanel.found()
  indicator_module = shared_module('orchard-incus',
    'src/Indicator.vala', 'src/Sparkline.vala', 'src/IncusClient.vala', 'src/Instance.vala', 'src/Preferences.vala',
    dependencies: [wingpanel, soup, json, gio_unix],
    install: true,
    install_dir: wingpanel.get_variable(pkgconfig: 'indicatorsdir'))

  indicator_smoke = executable('orchard-indicator-smoke',
    'tests/indicator-smoke.vala', dependencies: [wingpanel])
  test('panel-count', find_program('python3'),
    args: [files('tests/test-indicator.py'), indicator_smoke.full_path(), indicator_module.full_path()],
    timeout: 20)
endif
