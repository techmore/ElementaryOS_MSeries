# shellcheck shell=bash
# Source this from an install-*.sh script that compiles C or Vala (meson/cmake).
#
#   mseries_ccache_enable [meson|cmake]   route C/C++ compiles through ccache
#
# ccache is optional. Without it, or with MSERIES_CCACHE=0, this does nothing and
# the build is exactly what it was. It never installs ccache and never fails a
# build: a compile that ccache cannot cache just runs the compiler.
#
# What it can and cannot save: ccache caches the C compile of the C that valac
# generates, not valac itself. A first build on a fresh machine has a cold cache
# and gains nothing; a second build of the same pinned source (a retry after a
# failed install step, a reinstall, the next run of the same installer) is
# where the saving is. (#47)
#
# meson reads CC/CXX when it first configures a build directory, so call this
# before `meson setup`. cmake gets the compiler launcher variables instead of a
# wrapped CC, which is the form it documents.
mseries_ccache_enable() {
  local kind=${1:-meson}
  [[ ${MSERIES_CCACHE:-auto} == 0 ]] && return 0
  command -v ccache >/dev/null 2>&1 || return 0
  case $kind in
    cmake)
      export CMAKE_C_COMPILER_LAUNCHER=ccache CMAKE_CXX_COMPILER_LAUNCHER=ccache
      ;;
    *)
      case ${CC:-} in ccache*) ;; *) export CC="ccache ${CC:-cc}" ;; esac
      case ${CXX:-} in ccache*) ;; *) export CXX="ccache ${CXX:-c++}" ;; esac
      ;;
  esac
  echo "ccache: compiling through ccache ($kind)"
}
