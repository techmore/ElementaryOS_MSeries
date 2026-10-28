project('mseries-tailscale-wingpanel', 'vala', 'c', version: '0.1.0', meson_version: '>= 0.59.0')

wingpanel = dependency('wingpanel-9')
deps = [wingpanel, dependency('granite-7', version: '>= 7.4.0'), dependency('json-glib-1.0'), dependency('gtk4')]

shared_module('mseries-tailscale', 'Indicator.vala', 'TailscalePanel.vala',
  dependencies: deps, install: true,
  install_dir: wingpanel.get_variable(pkgconfig: 'indicatorsdir'))

install_data('mseries-tailscale-symbolic.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/symbolic/apps')

# Standalone window with the same menu, for screenshots and checks without the panel.
executable('tailscale-panel-probe', 'probe.vala', 'TailscalePanel.vala', dependencies: deps)

test('device-parsing', executable('test-device', 'test-device.vala', 'TailscalePanel.vala', dependencies: deps))
