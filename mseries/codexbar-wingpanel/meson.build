project('codexbar-wingpanel', 'vala', version: '0.1.0', meson_version: '>= 0.59.0')

libwingpanel_dep = dependency('wingpanel-9')
granite_dep = dependency('granite-7', version: '>= 7.7.0')
json_dep = dependency('json-glib-1.0')
indicators_dir = libwingpanel_dep.get_variable(pkgconfig: 'indicatorsdir')

shared_module(
  'codexbar',
  'Indicator.vala',
  'RefreshPolicy.vala',
  'QuotaEta.vala',
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
  'QuotaEta.vala',
  'test-quota-eta.vala',
  dependencies: json_dep,
)
test('quota-eta', quota_eta_test)

install_data(
  'icons/openai.svg',
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps'),
  rename: 'mseries-codexbar-openai-symbolic.svg',
)
