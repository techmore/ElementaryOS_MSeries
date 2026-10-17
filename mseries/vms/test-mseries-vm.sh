#!/usr/bin/env bash
# Hermetic tests for mseries/vms/mseries-vm.
#
# Stubs qemu-system-aarch64, swtpm, qemu-img, gh, curl, aria2c, git and the UUP
# conversion tools via PATH, so the whole create/start/wait/stop/fetch flow runs
# without KVM, without a network, and without root.
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cli=$here/mseries-vm

work=$(mktemp -d "${TMPDIR:-/tmp}/mseries-vm-test.XXXXXX")
cleanup() {
  pkill -f "$work/stubs/" >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

checks=0
failures=0
pass() { checks=$((checks + 1)); printf 'ok   %s\n' "$1"; }
fail() { checks=$((checks + 1)); failures=$((failures + 1)); printf 'FAIL %s\n' "$1" >&2; }
run() { # run DESC COMMAND... — expects exit 0
  local desc=$1
  shift
  if "$@" >/dev/null 2>&1; then pass "$desc"; else fail "$desc"; fi
}
run_fail() { # run_fail DESC COMMAND... — expects non-zero exit
  local desc=$1
  shift
  if "$@" >/dev/null 2>&1; then fail "$desc"; else pass "$desc"; fi
}
grep_ok() { # grep_ok DESC PATTERN FILE
  if grep -q -- "$2" "$3" 2>/dev/null; then pass "$1"; else fail "$1"; fi
}
grep_not() { # grep_not DESC PATTERN FILE
  if grep -q -- "$2" "$3" 2>/dev/null; then fail "$1"; else pass "$1"; fi
}
exists() { if [[ -e $2 ]]; then pass "$1"; else fail "$1"; fi; }
missing() { if [[ ! -e $2 ]]; then pass "$1"; else fail "$1"; fi; }

# ------------------------------------------------------------------ fixtures

stubs=$work/stubs
mkdir -p "$stubs" "$work/aavmf"
for fw in AAVMF_CODE.no-secboot.fd AAVMF_VARS.fd AAVMF_CODE.ms.fd AAVMF_VARS.ms.fd; do
  printf 'firmware' > "$work/aavmf/$fw"
done

export MSERIES_VM_DIR=$work/vms
export AAVMF_DIR=$work/aavmf
export STUB_LOG=$work
export MSERIES_VM_ALLOW_NO_KVM=1
export MSERIES_REPO_SLUG=test/repo
export PATH=$stubs:$PATH

# qemu stub: records argv, writes a banner to the -serial file, then idles.
cat > "$stubs/qemu-system-aarch64" <<'STUB'
#!/usr/bin/env bash
log=${STUB_LOG:?}
if [[ ${1:-} == "--version" ]]; then
  echo "QEMU emulator version 10.2.1 (mseries-vm test stub)"
  exit 0
fi
printf '%s\n' "$@" > "$log/qemu-invocation"
serial=""
prev=""
for arg in "$@"; do
  if [[ $prev == "-serial" ]]; then serial=${arg#file:}; fi
  prev=$arg
done
if [[ -n $serial ]]; then
  printf 'stub-qemu: starting\nBANNER-MARKER-OK\n' >> "$serial"
fi
trap 'exit 0' TERM INT
while :; do sleep 0.2; done
STUB
chmod +x "$stubs/qemu-system-aarch64"

# swtpm stub: honours --daemon and --pid file=...
cat > "$stubs/swtpm" <<'STUB'
#!/usr/bin/env bash
pid_file=""
prev=""
for arg in "$@"; do
  if [[ $prev == "--pid" ]]; then pid_file=${arg#file=}; fi
  prev=$arg
done
echo "$*" >> "$STUB_LOG/swtpm-invocations"
if [[ -n $pid_file ]]; then
  ( trap 'exit 0' TERM INT; while :; do sleep 0.2; done ) &
  echo $! > "$pid_file"
fi
exit 0
STUB
chmod +x "$stubs/swtpm"

# qemu-img stub: create touches the file; info reports qcow2.
cat > "$stubs/qemu-img" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "$STUB_LOG/qemu-img-invocations"
case ${1:-} in
  create) touch "${5:?}" ;;
  info)
    if [[ " $* " == *" --output=json "* ]]; then
      echo '{"format": "qcow2"}'
    else
      echo "virtual size: 8 GiB (8589934592 bytes)"
    fi
    ;;
esac
exit 0
STUB
chmod +x "$stubs/qemu-img"

# gh stub: serves one successful daily run with one arm64 artifact.
cat > "$stubs/gh" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "$STUB_LOG/gh-invocations"
case ${1:-} in
  run)
    case ${2:-} in
      list) echo 12345 ;;
      view) echo os9-mseries-arm64-12345 ;;
      download)
        shift 2
        dir=""
        while (( $# )); do
          case $1 in
            -D) dir=$2; shift 2 ;;
            *) shift ;;
          esac
        done
        mkdir -p "$dir"
        printf 'fake iso body' > "$dir/elementaryos-9.0-daily-arm64.test.iso"
        (cd "$dir" && sha256sum elementaryos-9.0-daily-arm64.test.iso > INSTALLER-SHA256SUMS)
        ;;
    esac
    ;;
esac
exit 0
STUB
chmod +x "$stubs/gh"

# curl stub: serves UUP dump listid/get.php fixtures (honouring -o).
cat > "$stubs/curl" <<'STUB'
#!/usr/bin/env bash
url=""
out=""
prev=""
for arg in "$@"; do
  if [[ $prev == "-o" ]]; then out=$arg; fi
  case $arg in http*) url=$arg ;; esac
  prev=$arg
done
echo "$*" >> "$STUB_LOG/curl-invocations"
emit() { if [[ -n $out ]]; then cat > "$out"; else cat; fi; }
case $url in
  *listid*) emit < "$STUB_LOG/uup-listid.json" ;;
  *get.php*) emit < "$STUB_LOG/uup-files.json" ;;
esac
exit 0
STUB
chmod +x "$stubs/curl"

cat > "$work/uup-listid.json" <<'JSON'
{"response":{"builds":{"1":{"title":"Windows 11, version 24H2 (test)","arch":"arm64","build":"26100.0","created":1,"uuid":"test-uuid"}}}}
JSON
acab_sha=$(printf 'aaaa' | sha256sum | cut -d' ' -f1)
besd_sha=$(printf 'bb' | sha256sum | cut -d' ' -f1)
cat > "$work/uup-files.json" <<JSON
{"response":{"updateName":"Windows 11, version 24H2 (test)","arch":"arm64","build":"26100.0",
"files":{"a.cab":{"url":"https://example.test/a.cab","sha256":"$acab_sha","size":"4"},
         "b.esd":{"url":"https://example.test/b.esd","sha256":"$besd_sha","size":"2"}}}}
JSON

# aria2c stub: materialises one file per "  out=" line in the input list, with
# content matching the sizes/sha-256s in the fixture above.
cat > "$stubs/aria2c" <<'STUB'
#!/usr/bin/env bash
input=""
dir=""
prev=""
for arg in "$@"; do
  if [[ $prev == "-i" ]]; then input=$arg; fi
  if [[ $prev == "-d" ]]; then dir=$arg; fi
  prev=$arg
done
echo "$*" >> "$STUB_LOG/aria2-invocations"
while IFS= read -r line; do
  case $line in
    "  out="*)
      name=${line#  out=}
      case $name in
        a.cab) printf 'aaaa' > "$dir/$name" ;;
        b.esd) printf 'bb' > "$dir/$name" ;;
        *) : > "$dir/$name" ;;
      esac
      ;;
    "  checksum="*) ;; # checksum verification is aria2's job, not the stub's
  esac
done < "$input"
exit 0
STUB
chmod +x "$stubs/aria2c"

# git stub: clone creates a stub converter; -C (fetch/checkout) is a no-op.
cat > "$stubs/git" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "$STUB_LOG/git-invocations"
case ${1:-} in
  clone)
    dest=${!#}
    mkdir -p "$dest"
    cat > "$dest/convert.sh" <<'INNER'
#!/usr/bin/env bash
set -euo pipefail
echo "stub converter: $*"
touch stub-windows-arm64.iso
INNER
    ;;
esac
exit 0
STUB
chmod +x "$stubs/git"

# Mark the UUP conversion dependencies as present so apt is never consulted.
for dep in cabextract wimlib-imagex chntpw genisoimage; do
  printf '#!/usr/bin/env bash\nexit 0\n' > "$stubs/$dep"
  chmod +x "$stubs/$dep"
done
# If anything still tries to call sudo, fail loudly instead of touching the system.
printf '#!/usr/bin/env bash\necho "unexpected sudo $*" >&2\nexit 1\n' > "$stubs/sudo"
chmod +x "$stubs/sudo"

# ------------------------------------------------------------- info / create

if out=$("$cli" info 2>&1); then pass "info runs" ; else fail "info runs"; fi
case $out in *AAVMF_VARS.ms.fd*) pass "info lists Secure Boot firmware" ;;
               *) fail "info lists Secure Boot firmware" ;; esac

fake_iso=$work/fake-elementary.iso
printf 'iso' > "$fake_iso"

run "create elementary" "$cli" create elementary --iso "$fake_iso" --memory 2048
conf=$work/vms/elementary/vm.conf
exists "elementary directory" "$work/vms/elementary"
grep_ok "elementary GUEST" '^GUEST=elementary$' "$conf"
grep_ok "elementary ISO recorded" "^ISO=$fake_iso$" "$conf"
grep_ok "elementary memory override" '^MEMORY_MB=2048$' "$conf"
grep_ok "elementary boots ISO" '^BOOT=iso$' "$conf"
grep_ok "elementary user networking" '^NET=user$' "$conf"
grep_ok "elementary default TPM off" '^TPM=off$' "$conf"
exists "elementary disk" "$work/vms/elementary/disk.qcow2"
exists "elementary vars" "$work/vms/elementary/vars.fd"
run_fail "refuses duplicate name" "$cli" create elementary --iso "$fake_iso"

# -------------------------------------------------- start / wait / stop flow

run "start elementary headless" "$cli" start elementary --headless
run "status reports running" bash -c "\"$cli\" status elementary | grep -q '^running'"
grep_ok "serial banner recorded" 'BANNER-MARKER-OK' "$work/vms/elementary/serial.log"
run "wait matches serial pattern" "$cli" wait elementary --pattern BANNER-MARKER-OK --timeout 30
exists "qemu args captured" "$work/vms/elementary/qemu.args"
grep_ok "qemu uses no-secboot firmware" 'AAVMF_CODE.no-secboot.fd' "$work/qemu-invocation"
grep_ok "qemu uses user networking" 'user,model=virtio-net-pci' "$work/qemu-invocation"
grep_ok "qemu uses virtio disk" 'if=virtio' "$work/qemu-invocation"
grep_not "no TPM device without TPM" 'tpm-tis-device' "$work/qemu-invocation"

# Fake QMP server: covers key/screenshot without real QEMU.
cat > "$work/qmp-stub.py" <<'PY'
import json, os, socket, sys
sock_path, log_path = sys.argv[1], sys.argv[2]
if os.path.exists(sock_path):
    os.unlink(sock_path)
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(sock_path)
server.listen(4)
while True:
    conn, _ = server.accept()
    conn.sendall(b'{"QMP": {"version": {"qemu": {"major": 10, "minor": 2, "micro": 1}}}}\n')
    buf = b""
    while True:
        try:
            chunk = conn.recv(65536)
        except ConnectionError:
            break
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            with open(log_path, "a") as log:
                log.write(line.decode() + "\n")
            command = msg.get("execute", "")
            if command == "screendump":
                with open(msg["arguments"]["filename"], "w") as shot:
                    shot.write("png")
            if not command:
                continue
            conn.sendall(b'{"return": {}}\n')
    conn.close()
PY
qmp_sock=$work/vms/elementary/qmp.sock
python3 "$work/qmp-stub.py" "$qmp_sock" "$work/qmp-log.jsonl" &
qmp_pid=$!
for _ in $(seq 1 50); do [[ -S $qmp_sock ]] && break; sleep 0.1; done
run "key sends QMP send-key" "$cli" key elementary ret
grep_ok "send-key captured" '"data": "ret"' "$work/qmp-log.jsonl"
run_fail "key validates codes" "$cli" key elementary 'bad code'
run "screenshot writes a file" "$cli" screenshot elementary "$work/shot.png"
exists "screenshot file" "$work/shot.png"
kill "$qmp_pid" 2>/dev/null || true
rm -f "$qmp_sock"

run "stop elementary" "$cli" stop elementary
run "status reports stopped" bash -c "\"$cli\" status elementary | grep -q '^stopped'"
missing "pid file removed" "$work/vms/elementary/qemu.pid"

run "set BOOT disk" "$cli" set elementary BOOT disk
grep_ok "BOOT updated" '^BOOT=disk$' "$conf"
run_fail "set rejects bad BOOT" "$cli" set elementary BOOT floppy

run "snapshot save" "$cli" snapshot elementary save pre-test
grep_ok "snapshot command" 'snapshot -c pre-test' "$work/qemu-img-invocations"
run "snapshot list" "$cli" snapshot elementary list

# ---------------------------------------------------------- windows with TPM

run "create windows" "$cli" create windows --iso "$fake_iso" --memory 3072
wconf=$work/vms/windows/vm.conf
grep_ok "windows GUEST" '^GUEST=windows$' "$wconf"
grep_ok "windows TPM on" '^TPM=on$' "$wconf"
grep_ok "windows SMM on" '^SMM=on$' "$wconf"
grep_ok "windows NVMe disk" '^DISK_BUS=nvme$' "$wconf"
grep_ok "windows Secure Boot firmware" '^FIRMWARE=AAVMF_CODE.ms.fd$' "$wconf"
run "start windows headless" "$cli" start windows --headless
exists "swtpm launched" "$work/vms/windows/swtpm.pid"
grep_ok "qemu TPM device" 'tpm-tis-device' "$work/qemu-invocation"
grep_ok "qemu NVMe device" 'nvme,serial=mseries-windows' "$work/qemu-invocation"
run "wait matches windows serial" "$cli" wait windows --pattern BANNER-MARKER-OK --timeout 30
run "stop windows" "$cli" stop windows
missing "swtpm pid cleaned up" "$work/vms/windows/swtpm.pid"

if out=$("$cli" list 2>&1); then
  case $out in *elementary*windows*) pass "list shows both VMs" ;; *) fail "list shows both VMs" ;; esac
else
  fail "list runs"
fi

# ------------------------------------------------------------ fetch (stubbed)

if out=$("$cli" fetch elementary 2>&1); then
  pass "fetch elementary runs"
  case $out in *"Verified INSTALLER-SHA256SUMS"*) pass "fetch verifies checksums" ;;
                 *) fail "fetch verifies checksums" ;; esac
else
  fail "fetch elementary runs"
fi
grep_ok "gh download invoked" 'run download 12345' "$work/gh-invocations"
run "create elementary autodetects fetched ISO" "$cli" create elementary autofetch
grep_ok "autodetected ISO recorded" '^ISO=.*elementaryos-9.0-daily-arm64.test.iso$' "$work/vms/autofetch/vm.conf"

run "fetch windows downloads UUP set" "$cli" fetch windows
exists "aria2 input generated" "$work/vms/downloads/windows-uup/aria2-input.txt"
exists "UUP file a.cab" "$work/vms/downloads/windows-uup/UUPs/a.cab"
exists "UUP file b.esd" "$work/vms/downloads/windows-uup/UUPs/b.esd"
exists "converter checked out" "$work/vms/downloads/windows-uup/converter/convert.sh"
grep_ok "aria2 received checksums" "checksum=sha-256=$acab_sha" "$work/vms/downloads/windows-uup/aria2-input.txt"
run "fetch windows --convert" "$cli" fetch windows --convert
exists "converter produced an ISO" "$work/vms/downloads/windows-uup/stub-windows-arm64.iso"

# verify-first: a second fetch must not hand verified files back to aria2
n_aria=$(wc -l < "$work/aria2-invocations")
if out=$("$cli" fetch windows 2>&1); then
  pass "second fetch windows runs"
  case $out in *"sha-256 verified"*) pass "second fetch windows verifies locally" ;;
                 *) fail "second fetch windows verifies locally" ;; esac
else
  fail "second fetch windows runs"
fi
[[ $(wc -l < "$work/aria2-invocations") == "$n_aria" ]] \
  && pass "aria2 not re-invoked for verified files" || fail "aria2 not re-invoked for verified files"

# a corrupted file is detected and re-fetched on its own
printf 'zzzz' > "$work/vms/downloads/windows-uup/UUPs/a.cab"
run "fetch windows repairs a corrupted file" "$cli" fetch windows
[[ $(wc -l < "$work/aria2-invocations") -gt $n_aria ]] \
  && pass "aria2 re-invoked for the corrupted file" || fail "aria2 re-invoked for the corrupted file"
grep_ok "repair list includes a.cab" 'out=a.cab' "$work/vms/downloads/windows-uup/aria2-input.txt"
grep_not "repair list excludes verified b.esd" 'out=b.esd' "$work/vms/downloads/windows-uup/aria2-input.txt"
if out=$("$cli" fetch windows 2>&1); then
  case $out in *"sha-256 verified"*) pass "repaired set verifies clean again" ;;
                 *) fail "repaired set verifies clean again" ;; esac
else
  fail "repaired set verifies clean again"
fi

# -------------------------------------------------------------------- delete

run "delete windows" "$cli" delete windows --force
missing "windows directory removed" "$work/vms/windows"
run_fail "delete refuses without --force" bash -c "\"$cli\" delete autofetch </dev/null"

if out=$("$cli" macos 2>&1); then
  case $out in *"not possible"*) pass "macos explains the limitation" ;;
                 *) fail "macos explains the limitation" ;; esac
else
  fail "macos command runs"
fi
run "help prints usage" bash -c "'$cli' --help | grep -q 'import-omarchy'"

# --------------------------------------------------------------- final sweep

run "delete elementary" "$cli" delete elementary --force
run "delete autofetch" "$cli" delete autofetch --force
run "delete fails for missing VM" bash -c "! '$cli' delete windows --force 2>/dev/null"

echo
echo "mseries-vm tests: $checks checks, $failures failures"
if (( failures > 0 )); then
  echo "mseries-vm tests: FAILED" >&2
  exit 1
fi
echo "mseries-vm tests: ok"
