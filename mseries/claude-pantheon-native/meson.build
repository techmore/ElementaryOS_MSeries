project('claude-pantheon', ['vala', 'c'],
  version: '0.1.0',
  meson_version: '>= 0.59.0')

app_sources = files(
  'src/Application.vala',
  'src/MainWindow.vala',
  'src/SessionIndex.vala',
  'src/Transcript.vala',
  'src/Markdown.vala',
  'src/ChatView.vala',
  'src/ClaudeRunner.vala'
)

app_dependencies = [
  dependency('gtk4'),
  dependency('granite-7'),
  dependency('json-glib-1.0'),
  dependency('gio-unix-2.0'),
  meson.get_compiler('vala').find_library('posix'),
]

add_project_arguments('-DGETTEXT_PACKAGE="claude-pantheon"', language: 'c')

executable('claude-pantheon', app_sources,
  dependencies: app_dependencies,
  install: true)

dump = executable('transcript-dump', 'tests/transcript-dump.vala',
  'src/Transcript.vala', 'src/Markdown.vala',
  dependencies: [dependency('glib-2.0'), dependency('gobject-2.0'), dependency('json-glib-1.0'), dependency('gio-2.0')])
test('transcript-dump', dump, args: [files('tests/sample.jsonl')])

install_data('data/io.github.techmore.ClaudePantheon.desktop',
  install_dir: get_option('datadir') / 'applications')
install_data('data/icons/io.github.techmore.ClaudePantheon.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps')
