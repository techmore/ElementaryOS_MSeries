project('mseries-t3-wingpanel', 'vala', 'c', version: '0.1.0', meson_version: '>= 0.59.0')
wingpanel = dependency('wingpanel-9')
deps = [wingpanel, dependency('granite-7', version: '>= 7.7.0'), dependency('json-glib-1.0'), meson.get_compiler('c').find_library('m')]
python = find_program('python3')
source_paths = ['Indicator.vala', '../dock-taskbar/TaskbarT3RPopover.vala',
  '../codexbar-wingpanel/JsonBoundary.vala', '../codexbar-wingpanel/HelperProcess.vala',
  '../codexbar-wingpanel/AccountDialog.vala', '../codexbar-wingpanel/PanelPreferences.vala',
  '../codexbar-wingpanel/RefreshPolicy.vala', '../codexbar-wingpanel/QuotaEta.vala',
  '../codexbar-wingpanel/Presentation.vala']
sources = []
foreach path : source_paths
  sources += configure_file(input: path, output: path.split('/')[-1], copy: true)
endforeach
foreach component : ['codexbar', 'repobar']
  sources += custom_target(component + '-embedded', input: '../' + component + '-wingpanel/Indicator.vala',
    output: component + '.vala', command: [python, files('embedded-source.py'), '@INPUT@', '@OUTPUT@'])
endforeach
shared_module('mseries-t3', sources, dependencies: deps, install: true,
  install_dir: wingpanel.get_variable(pkgconfig: 'indicatorsdir') / '../mseries-pending-indicators')
probe = executable('probe', sources, 'probe.vala', dependencies: deps)

# Keep native account/repository settings available in both local and Debian installs.
settings_model = configure_file(input: '../codexbar-wingpanel/settings/SettingsModel.vala', output: 'SettingsModel.vala', copy: true)
codex_settings = configure_file(input: '../codexbar-wingpanel/settings/SettingsApp.vala', output: 'CodexSettings.vala', copy: true)
panel_preferences = meson.current_build_dir() / 'PanelPreferences.vala'
executable('codexbar-settings', settings_model, codex_settings, panel_preferences, dependencies: deps, install: true)
repo_settings = configure_file(input: '../repobar-wingpanel/settings/SettingsApp.vala', output: 'RepoSettings.vala', copy: true)
executable('mseries-repobar-settings', repo_settings, dependencies: deps, install: true)
foreach mark : ['openai', 'claude', 'opencode', 'grok']
  install_data('../codexbar-wingpanel/icons/' + mark + '.svg',
    install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps',
    rename: 'mseries-codexbar-' + mark + '-symbolic.svg')
endforeach
foreach icon : ['github-symbolic', 'mseries-repobar-globe-symbolic', 'mseries-repobar-commit-symbolic', 'mseries-repobar-issue-symbolic', 'mseries-repobar-pull-symbolic']
  install_data('../repobar-wingpanel/icons/' + icon + '.svg', install_dir: get_option('datadir') / 'icons/hicolor/symbolic/apps')
endforeach
