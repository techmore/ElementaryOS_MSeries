project('mseries-image-studio', ['vala', 'c'],
  version: '0.1.0',
  meson_version: '>= 0.59.0',
  default_options: ['warning_level=2'])

gtk = dependency('gtk4', version: '>= 4.12')
granite = dependency('granite-7', version: '>= 7.7.0')
json = dependency('json-glib-1.0')
soup = dependency('libsoup-3.0')
pixbuf = dependency('gdk-pixbuf-2.0')

app_sources = files(
  'src/Application.vala',
  'src/MainWindow.vala',
  'src/HostCapabilities.vala',
  'src/PromptAssistant.vala',
  'src/GenerationRecipe.vala',
  'src/GenerationOutputStore.vala',
  'src/RecipeStore.vala',
  'src/GenerationGate.vala'
)

executable('mseries-image-studio', app_sources,
  dependencies: [gtk, granite, json, soup, pixbuf],
  install: true)

install_data('data/org.elementary.mseries.ImageStudio.desktop',
  install_dir: get_option('datadir') / 'applications')
install_data('data/org.elementary.mseries.ImageStudio.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps')

core_test = executable('test-image-studio-core',
  'tests/test-core.vala',
  'src/HostCapabilities.vala',
  'src/GenerationRecipe.vala',
  'src/GenerationOutputStore.vala',
  'src/GenerationGate.vala',
  'src/RecipeStore.vala',
  dependencies: [json, dependency('gio-2.0')],
  install: false)
test('image-studio core', core_test, timeout: 30)
