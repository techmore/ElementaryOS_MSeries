project('codexbar-wingpanel', 'vala', version: '0.1.0', meson_version: '>= 0.59.0')

libwingpanel_dep = dependency('wingpanel-9')
granite_dep = dependency('granite-7', version: '>= 7.7.0')
json_dep = dependency('json-glib-1.0')
indicators_dir = libwingpanel_dep.get_variable(pkgconfig: 'indicatorsdir')

indicator_sources = files(
  'Indicator.vala', 'JsonBoundary.vala', 'HelperProcess.vala', 'AccountDialog.vala',
  'PanelPreferences.vala', 'RefreshPolicy.vala', 'QuotaEta.vala', 'Presentation.vala',
)

libcodexbar = shared_module(
  'codexbar',
  indicator_sources,
  dependencies: [libwingpanel_dep, granite_dep, json_dep],
  install: true,
  install_dir: indicators_dir,
)

refresh_policy_test = executable(
  'test-refresh-policy',
  'RefreshPolicy.vala',
  'test-refresh-policy.vala',
  dependencies: dependency('gobject-2.0'),
)
test('refresh-policy', refresh_policy_test)

quota_eta_test = executable(
  'test-quota-eta',
  'QuotaEta.vala', 'JsonBoundary.vala',
  'test-quota-eta.vala',
  dependencies: [json_dep, dependency('gio-2.0')],
)
test('quota-eta', quota_eta_test)

# Headless render probe (not installed): see probe/run-probe.sh.
render_probe = executable(
  'render-probe',
  indicator_sources, 'probe/render-probe.vala',
  dependencies: [libwingpanel_dep, granite_dep, json_dep, meson.get_compiler('c').find_library('m')],
  build_by_default: false,
)

presentation_test = executable(
  'test-presentation',
  'QuotaEta.vala', 'JsonBoundary.vala',
  'Presentation.vala',
  'test-presentation.vala',
  dependencies: [json_dep, dependency('gio-2.0')],
)
test('presentation', presentation_test)

install_data(
  'icons/openai.svg',
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps'),
  rename: 'mseries-codexbar-openai-symbolic.svg',
)

foreach provider : ['claude', 'opencode', 'grok']
  install_data(
    'icons/@0@.svg'.format(provider),
    install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps'),
    rename: 'mseries-codexbar-@0@-symbolic.svg'.format(provider),
  )
endforeach

settings_model_test = executable(
  'test-settings-model',
  'settings/SettingsModel.vala',
  'settings/test-settings-model.vala',
  dependencies: json_dep,
)
test('settings-model', settings_model_test)

codexbar_settings = executable(
  'codexbar-settings',
  'settings/SettingsModel.vala',
  'settings/SettingsApp.vala',
  'PanelPreferences.vala',
  dependencies: [granite_dep, json_dep],
)

panel_preferences_test = executable(
  'test-panel-preferences',
  'PanelPreferences.vala',
  'test-panel-preferences.vala',
  dependencies: [json_dep, dependency('gio-2.0')],
)
test('panel-preferences', panel_preferences_test)

# Run under Xvfb with probe/run-live-preferences.sh; all backends and configuration are isolated.
live_preferences_probe = executable(
  'test-live-preferences',
  indicator_sources, 'probe/test-live-preferences.vala',
  dependencies: [libwingpanel_dep, granite_dep, json_dep, meson.get_compiler('c').find_library('m')],
  build_by_default: false,
)

switch_probe = executable(
  'test-switch',
  indicator_sources, 'probe/test-switch.vala',
  dependencies: [libwingpanel_dep, granite_dep, json_dep, meson.get_compiler('c').find_library('m')],
  build_by_default: false,
)

# These are isolated interactions, not screenshots: the pre-fix code SIGSEGVs after confirmation.
if find_program('xvfb-run', required: false).found() and find_program('dbus-run-session', required: false).found()
  foreach scenario : ['success', 'null', 'array', 'invalid', 'claude-failed-exit']
    test('switch-' + scenario, find_program('bash'),
      args: [join_paths(meson.current_source_dir(), 'probe/run-switch-probe.sh'), meson.current_build_dir(), scenario],
      depends: switch_probe,
      timeout: 30,
    )
  endforeach
endif

json_boundary_test = executable('test-json-boundary', 'JsonBoundary.vala', 'test-json-boundary.vala', dependencies: [json_dep, dependency('gio-2.0')])
test('json-boundary', json_boundary_test)

ingestion_probe = executable('test-ingestion',
  indicator_sources, 'probe/test-ingestion.vala',
  dependencies: [libwingpanel_dep, granite_dep, json_dep, meson.get_compiler('c').find_library('m')],
  build_by_default: false,
)
if find_program('xvfb-run', required: false).found() and find_program('dbus-run-session', required: false).found()
  test('malformed-ingestion', find_program('bash'),
    args: [join_paths(meson.current_source_dir(), 'probe/run-ingestion.sh'), meson.current_build_dir()],
    depends: ingestion_probe, timeout: 30)
endif

if find_program('xvfb-run', required: false).found() and find_program('dbus-run-session', required: false).found()
  test('local-token-panel', find_program('bash'),
    args: [join_paths(meson.current_source_dir(), 'probe/run-token-probe.sh'), meson.current_build_dir()],
    depends: render_probe, timeout: 30)
endif

# Guards against valac emitting a use-after-free for nested owned/unowned conditionals.
python = find_program('python3')
test('generated-c-temporaries', python,
  args: [join_paths(meson.current_source_dir(), 'probe/check-generated-c.py'), meson.current_build_dir()],
  depends: [libcodexbar, codexbar_settings], timeout: 30)

if find_program('xvfb-run', required: false).found() and find_program('dbus-run-session', required: false).found()
  test('grok-panel', find_program('bash'),
    args: [join_paths(meson.current_source_dir(), 'probe/run-grok-probe.sh'), meson.current_build_dir()],
    depends: render_probe, timeout: 30)
endif

helper_process_test = executable('test-helper-process', 'HelperProcess.vala', 'test-helper-process.vala', dependencies: dependency('gio-2.0'))
test('helper-process', helper_process_test, timeout: 10)

if find_program('xvfb-run', required: false).found() and find_program('dbus-run-session', required: false).found()
  test('cached-repaint-preferences', find_program('bash'),
    args: [join_paths(meson.current_source_dir(), 'probe/run-live-preferences.sh'), meson.current_build_dir()],
    depends: live_preferences_probe, timeout: 15)
endif
