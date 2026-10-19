project('share-eyes-wingpanel', 'vala', version: '0.2.0', meson_version: '>= 0.59.0')

# The share section lives inside the (patched) Quick Settings popover: install-quick-settings-brightness.sh
# copies these sources in. This project only builds and tests them standalone.
json_dep = dependency('json-glib-1.0')
soup_dep = dependency('libsoup-3.0')
gtk_dep = dependency('gtk4')
granite_dep = dependency('granite-7')

share_state_test = executable('test-share-state', 'ShareState.vala', 'test-share-state.vala', dependencies: json_dep)
test('share-state', share_state_test)

executable(
  'render-probe',
  'SharePanel.vala', 'ShareState.vala', 'ShareClient.vala', 'probe/render-probe.vala',
  dependencies: [gtk_dep, granite_dep, json_dep, soup_dep],
  build_by_default: false,
)

install_data(
  'icons/eyes.svg',
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps'),
  rename: 'mseries-share-eyes-symbolic.svg',
)

executable(
  'mseries-share-eyes',
  'app/ShareApp.vala', 'SharePanel.vala', 'ShareState.vala', 'ShareClient.vala',
  dependencies: [gtk_dep, granite_dep, json_dep, soup_dep],
  install: true,
  install_dir: join_paths(get_option('prefix'), 'bin'),
)
install_data('io.github.techmore.ShareEyes.desktop', install_dir: join_paths(get_option('datadir'), 'applications'))
