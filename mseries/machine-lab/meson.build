project('machine-lab', 'vala',
  version: '0.8.0',
  meson_version: '>= 1.0.0',
  default_options: ['warning_level=2']
)

gtk = dependency('gtk4', version: '>= 4.12')
granite = dependency('granite-7', version: '>= 7.0')
json = dependency('json-glib-1.0')

gnome = import('gnome')
resources = gnome.compile_resources('machine-lab-resources',
  'data/machine-lab.gresource.xml',
  source_dir: 'data'
)

add_project_arguments(['--pkg', 'posix'], language: 'vala')

config = configure_file(
  input: 'src/config.vala.in',
  output: 'config.vala',
  configuration: {'VERSION': meson.project_version(), 'MACOS_CHECK_SOURCE': meson.current_source_dir() / 'launcher/macos-check.py'}
)

executable('machine-lab',
  'src/main.vala', 'src/machine.vala', 'src/page.vala', 'src/viewer.vala', 'src/macexp.vala', 'src/clipboard.vala', 'src/incus-model.vala', 'src/incus-ui.vala', 'src/snapshots.vala', 'src/images.vala', config,
  resources,
  dependencies: [gtk, granite, json],
  install: true
)

install_data('data/io.github.mseries.MachineLab.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps')
install_data('data/io.github.mseries.MachineLab.metainfo.xml',
  install_dir: get_option('datadir') / 'metainfo')
install_data('data/io.github.mseries.MachineLab.desktop',
  install_dir: get_option('datadir') / 'applications')
install_data('launcher/run-vm.sh',
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
  rename: 'machine-lab-run-vm')
install_data('launcher/prepare-latest-omarchy.py',
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
  rename: 'machine-lab-prepare-omarchy')

test_exe = executable('test-machine',
  'tests/test-machine.vala', 'src/machine.vala', 'src/incus-model.vala', 'src/snapshots.vala', 'src/images.vala',
  dependencies: [gtk, dependency('gio-unix-2.0'), json],
  install: false
)
test('machine logic', test_exe,
  env: {'FAKE_QMP': meson.current_source_dir() / 'tests/fake-qmp.py'},
  timeout: 60
)

install_data('launcher/macos-check.py',
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
  rename: 'machine-lab-macos-check')

test('macOS readiness', find_program('python3'),
  args: [meson.current_source_dir() / 'tests/test-macos-check.py'])
