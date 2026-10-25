#!/usr/bin/env bash
# Source-only desktop update. Never boot, repartition or install system packages.
set -euo pipefail
package=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -f $package/preflight.py && ! -f $package/manifest.json ]]; then
  echo 'Use the generated release archive, not this source template.' >&2
  exit 2
fi
preflight=$package/mseries/releases/v0.0.1/preflight.py
usage() {
  cat <<'HELP'
English F5 v0.0.1 — update an already configured M1 Pro 32 GB desktop
  ./install.sh --check
  ./install.sh --install --model-source /path/to/pinned-Q8_0.gguf
  ./install.sh --install --download-model
  ./install.sh --rollback
  ./install.sh --enable-chatgpt
HELP
}
action=${1:---help}
shift || true
case $action in
  --check)
    [[ $# == 0 ]] || { usage; exit 2; }
    exec /usr/bin/python3 -B "$preflight" --package-root "$package" --check
    ;;
  --install)
    args=()
    while (( $# )); do
      case $1 in
        --download-model) args+=(--download-model); shift ;;
        --model-source)
          [[ $# -ge 2 && -n $2 ]] || { usage; exit 2; }
          args+=(--model-source "$2"); shift 2 ;;
        *) usage; exit 2 ;;
      esac
    done
    /usr/bin/python3 -B "$preflight" --package-root "$package" --check
    exec /usr/bin/python3 -B "$package/mseries/install-dictation-english.py" --activate nemotron --speech-only "${args[@]}"
    ;;
  --rollback)
    [[ $# == 0 ]] || { usage; exit 2; }
    /usr/bin/python3 -B "$preflight" --package-root "$package" --verify-package
    exec /usr/bin/python3 -B "$package/mseries/install-dictation-english.py" --speech-only --rollback
    ;;
  --enable-chatgpt)
    [[ $# == 0 ]] || { usage; exit 2; }
    /usr/bin/python3 -B "$preflight" --package-root "$package" --verify-package
    exec /usr/bin/python3 -B "$package/mseries/dictation/enable-app-input.py" --app chatgpt --stage
    ;;
  --help|-h) usage ;;
  *) usage; exit 2 ;;
esac
