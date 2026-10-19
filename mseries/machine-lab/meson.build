project('machine-lab', 'vala',
  version: '0.2.0',
  meson_version: '>= 1.0.0',
  default_options: ['warning_level=2']
)

gtk = dependency('gtk4', version: '>= 4.12')
granite = dependency('granite-7', version: '>= 7.0')

gnome = import('gnome')
resources = gnome.compile_resources('machine-lab-resources',
  'data/machine-lab.gresource.xml',
  source_dir: 'data'
)

add_project_arguments(['--pkg', 'posix'], language: 'vala')

executable('machine-lab',
  'src/main.vala', 'src/machine.vala', 'src/page.vala', 'src/viewer.vala', 'src/macexp.vala',
  resources,
  dependencies: [gtk, granite],
  install: true
)

install_data('data/io.github.mseries.MachineLab.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps')
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
