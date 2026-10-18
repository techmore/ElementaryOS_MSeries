project('mseries-snapping', 'vala', 'c', version: '0.1.0')
add_project_arguments('--vapidir=' + get_option('vapidir'),
  '--pkg=mutter-clutter-18', '--pkg=mutter-cogl-18', '--pkg=mutter-mtk-18',
  '--define=HAS_MUTTER47', '--define=HAS_MUTTER48', '--define=HAS_MUTTER49',
  '--define=HAS_MUTTER50', language: 'vala')
shared_library('mseries-snapping', 'Main.vala',
  dependencies: [dependency('gala'), dependency('gio-unix-2.0'), dependency('gee-0.8')],
  install: true, install_dir: get_option('plugindir'))
