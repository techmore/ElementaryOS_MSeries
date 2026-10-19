project('airdrop-probe', 'vala', version: '0.1.0', meson_version: '>= 0.59.0')
# Standalone build of the Quick Settings AirDrop section for headless tests (run-probe.sh); the real one is built into the patched Quick Settings plugin.
executable('airdrop-probe', 'AirDropPanel.vala', 'airdrop-probe.vala',
  dependencies: [dependency('gtk4'), dependency('granite-7'), dependency('json-glib-1.0')])
