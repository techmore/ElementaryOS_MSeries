// SPDX-License-Identifier: GPL-3.0-or-later
use std::cell::RefCell;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT: AtomicUsize = AtomicUsize::new(0);

struct Fixture {
    root: PathBuf,
    calls: PathBuf,
    journal_count: PathBuf,
    last_calls: RefCell<String>,
}

impl Fixture {
    fn new() -> Self {
        let n = NEXT.fetch_add(1, Ordering::Relaxed);
        let root =
            std::env::temp_dir().join(format!("wifi-resume-parity-{}-{n}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let calls = root.join("modprobe.calls");
        let journal_count = root.join("journal-count");
        write_command(&root, "uname", "echo \"${ARCH:-aarch64}\"");
        write_command(
            &root,
            "lspci",
            "echo \"${PCI:-Network controller [14e4:4425]}\"",
        );
        write_command(
            &root,
            "nmcli",
            r#"
if [ "$1" = radio ]; then
  echo "${RADIO:-enabled}"
elif [ -n "${DEVICE_STATUS:-}" ]; then
  printf '%b' "$DEVICE_STATUS"
else
  printf '%s\n' 'ethernet:connected' 'wifi:disconnected'
fi
"#,
        );
        write_command(
            &root,
            "journalctl",
            r#"
count=0
[ -f "$JOURNAL_COUNT" ] && count=$(cat "$JOURNAL_COUNT")
echo $((count + 1)) > "$JOURNAL_COUNT"
if [ "$count" = 0 ]; then printf '%s\n' "${REJECTIONS_BEFORE:-}"; else printf '%s\n' "${REJECTIONS_AFTER:-}"; fi
"#,
        );
        write_command(&root, "sleep", "exit \"${SLEEP_STATUS:-0}\"");
        write_command(&root, "logger", "exit 0");
        write_command(
            &root,
            "lsmod",
            r#"
echo 'Module Size Used by'
if [ "${LOADED:-yes}" = yes ]; then
  holders=${HOLDERS:-brcmfmac_wcc}
  if [ -n "$holders" ]; then echo "brcmfmac 1 1 $holders"; else echo 'brcmfmac 1 0'; fi
fi
"#,
        );
        write_command(
            &root,
            "modprobe",
            r#"
echo "$*" >> "$MODPROBE_CALLS"
if [ "${FAIL_UNLOAD:-0}" = 1 ] && [ "$1" = -r ]; then exit 7; fi
if [ "${FAIL_LOAD:-0}" = 1 ] && [ "$1" = brcmfmac ]; then exit 8; fi
exit 0
"#,
        );
        Self {
            root,
            calls,
            journal_count,
            last_calls: RefCell::new(String::new()),
        }
    }

    fn run_pair(&self, vars: &[(&str, &str)]) -> (Output, Output) {
        let rust_bin = env!("CARGO_BIN_EXE_mseries-wifi-resume-rs");
        let original = Path::new(env!("CARGO_MANIFEST_DIR")).join(
            "../../../mkosi.images/apple-silicon/mkosi.extra/usr/sbin/mseries-wifi-resume-fix",
        );
        let mut shell = Command::new("/bin/bash");
        shell.arg(original);
        let mut rust = Command::new(rust_bin);
        let path = format!("{}:/usr/bin:/bin", self.root.display());
        for cmd in [&mut shell, &mut rust] {
            cmd.env("PATH", &path)
                .env("MODPROBE_CALLS", &self.calls)
                .env("JOURNAL_COUNT", &self.journal_count);
            for (key, value) in vars {
                cmd.env(key, value);
            }
        }
        let shell_output = shell.output().unwrap();
        let shell_calls = self.read_calls();
        let _ = fs::remove_file(&self.calls);
        let _ = fs::remove_file(&self.journal_count);
        let rust_output = rust.output().unwrap();
        let rust_calls = self.read_calls();
        assert_eq!(shell_calls, rust_calls, "modprobe calls differ");
        *self.last_calls.borrow_mut() = rust_calls;
        (shell_output, rust_output)
    }

    fn calls(&self) -> String {
        self.last_calls.borrow().clone()
    }

    fn read_calls(&self) -> String {
        fs::read_to_string(&self.calls).unwrap_or_default()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

fn write_command(root: &Path, name: &str, body: &str) {
    let path = root.join(name);
    fs::write(&path, format!("#!/bin/sh\n{body}\n")).unwrap();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = fs::metadata(&path).unwrap().permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(path, permissions).unwrap();
    }
}

fn assert_same(shell: Output, rust: Output) {
    assert_eq!(
        shell.status.code(),
        rust.status.code(),
        "shell stderr: {}; Rust stderr: {}",
        String::from_utf8_lossy(&shell.stderr),
        String::from_utf8_lossy(&rust.stderr)
    );
    assert_eq!(shell.stdout, rust.stdout);
}

#[test]
fn disabled_radio_is_respected() {
    let f = Fixture::new();
    let (shell, rust) = f.run_pair(&[
        ("RADIO", "disabled"),
        ("DEVICE_STATUS", "wifi:disconnected\\n"),
    ]);
    assert_same(shell, rust);
    assert!(f.calls().is_empty());
}

#[test]
fn connected_wifi_is_left_untouched() {
    let f = Fixture::new();
    let (shell, rust) = f.run_pair(&[("DEVICE_STATUS", "ethernet:connected\\nwifi:connected\\n")]);
    assert_same(shell, rust);
    assert!(f.calls().is_empty());
}

#[test]
fn ethernet_does_not_hide_disconnected_wifi() {
    let f = Fixture::new();
    let (shell, rust) =
        f.run_pair(&[("DEVICE_STATUS", "ethernet:connected\\nwifi:disconnected\\n")]);
    assert_same(shell, rust);
    assert_eq!(
        f.calls(),
        "-r --remove-holders brcmfmac\nbrcmfmac\nbrcmfmac_wcc\n"
    );
}

#[test]
fn failed_unload_stops_recovery_with_the_same_status() {
    let f = Fixture::new();
    let (shell, rust) = f.run_pair(&[
        ("DEVICE_STATUS", "wifi:disconnected\\n"),
        ("FAIL_UNLOAD", "1"),
    ]);
    assert_same(shell, rust);
    assert_eq!(f.calls(), "-r --remove-holders brcmfmac\n");
}

#[test]
fn sleep_failure_aborts_before_inspecting_or_reloading_the_driver() {
    let f = Fixture::new();
    let (shell, rust) = f.run_pair(&[
        ("DEVICE_STATUS", "wifi:disconnected\\n"),
        ("SLEEP_STATUS", "19"),
    ]);
    assert_same(shell, rust);
    assert_eq!(f.calls(), "");
}

#[test]
fn missing_driver_is_loaded_without_an_unload_attempt() {
    let f = Fixture::new();
    let (shell, rust) = f.run_pair(&[("DEVICE_STATUS", "wifi:disconnected\\n"), ("LOADED", "no")]);
    assert_same(shell, rust);
    assert_eq!(f.calls(), "brcmfmac\n");
}

#[test]
fn unsupported_architecture_or_chip_exits_without_actions() {
    for vars in [
        vec![("ARCH", "x86_64")],
        vec![("PCI", "Network controller [14e4:4434]")],
    ] {
        let f = Fixture::new();
        let (shell, rust) = f.run_pair(&vars);
        assert_same(shell, rust);
        assert!(f.calls().is_empty());
    }
}

#[test]
fn a_new_association_rejection_triggers_recovery() {
    let f = Fixture::new();
    let (shell, rust) = f.run_pair(&[
        ("DEVICE_STATUS", "wifi:connected\\n"),
        ("REJECTIONS_BEFORE", "wlan0: connected"),
        ("REJECTIONS_AFTER", "wlan0: ASSOC-REJECT status_code=16"),
    ]);
    assert_same(shell, rust);
    assert_eq!(
        f.calls(),
        "-r --remove-holders brcmfmac\nbrcmfmac\nbrcmfmac_wcc\n"
    );
}

#[test]
fn unchanged_rejection_count_and_connected_wifi_do_not_reload() {
    let f = Fixture::new();
    let (shell, rust) = f.run_pair(&[
        ("DEVICE_STATUS", "wifi:connected\\n"),
        ("REJECTIONS_BEFORE", "wlan0: ASSOC-REJECT status_code=16"),
        ("REJECTIONS_AFTER", "wlan0: ASSOC-REJECT status_code=16"),
    ]);
    assert_same(shell, rust);
    assert!(f.calls().is_empty());
}

#[test]
fn connecting_wifi_is_treated_as_down() {
    let f = Fixture::new();
    let (shell, rust) = f.run_pair(&[(
        "DEVICE_STATUS",
        "wifi:connecting (getting IP configuration)\\n",
    )]);
    assert_same(shell, rust);
    assert_eq!(
        f.calls(),
        "-r --remove-holders brcmfmac\nbrcmfmac\nbrcmfmac_wcc\n"
    );
}

#[test]
fn multiple_module_holders_are_reloaded_together() {
    let f = Fixture::new();
    let (shell, rust) = f.run_pair(&[
        ("DEVICE_STATUS", "wifi:disconnected\\n"),
        ("HOLDERS", "brcmfmac_wcc,brcmfmac_bus"),
    ]);
    assert_same(shell, rust);
    assert_eq!(
        f.calls(),
        "-r --remove-holders brcmfmac\nbrcmfmac\nbrcmfmac_wcc brcmfmac_bus\n"
    );
}

#[test]
fn failed_driver_reload_aborts_before_reloading_holders() {
    let f = Fixture::new();
    let (shell, rust) = f.run_pair(&[
        ("DEVICE_STATUS", "wifi:disconnected\\n"),
        ("FAIL_LOAD", "1"),
    ]);
    assert_same(shell, rust);
    assert_eq!(f.calls(), "-r --remove-holders brcmfmac\nbrcmfmac\n");
}
