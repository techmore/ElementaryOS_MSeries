// SPDX-License-Identifier: GPL-3.0-or-later
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT: AtomicUsize = AtomicUsize::new(0);

struct Fixture {
    root: PathBuf,
    sys: PathBuf,
    conf: PathBuf,
    bindir: PathBuf,
}

impl Fixture {
    fn new(on_ac: Option<u8>, profile: &str, cap: u64) -> Self {
        let id = NEXT.fetch_add(1, Ordering::Relaxed);
        let root =
            std::env::temp_dir().join(format!("mseries-power-parity-{}-{id}", std::process::id()));
        let sys = root.join("sys");
        let ac = sys.join("class/power_supply/macsmc-ac");
        fs::create_dir_all(&ac).unwrap();
        if let Some(on_ac) = on_ac {
            fs::write(ac.join("online"), format!("{on_ac}\n")).unwrap();
        }
        let cpu = sys.join("devices/system/cpu/cpufreq");
        for (name, max) in [
            ("policy0", 2_064_000),
            ("policy2", 3_036_000),
            ("policy6", 3_036_000),
        ] {
            let policy = cpu.join(name);
            fs::create_dir_all(&policy).unwrap();
            fs::write(policy.join("cpuinfo_min_freq"), "600000\n").unwrap();
            fs::write(policy.join("cpuinfo_max_freq"), format!("{max}\n")).unwrap();
            fs::write(policy.join("scaling_max_freq"), format!("{max}\n")).unwrap();
            fs::write(policy.join("related_cpus"), "0-3\n").unwrap();
        }
        let bindir = root.join("bin");
        fs::create_dir_all(&bindir).unwrap();
        let profile_tool = bindir.join("powerprofilesctl");
        let profile_state = root.join("profile.state");
        fs::write(&profile_state, format!("{profile}\n")).unwrap();
        fs::write(&profile_tool, "#!/bin/sh\ncase \"$1\" in\n  get) cat \"$MSERIES_PROFILE_STATE\" ;;\n  set) echo \"$2\" > \"$MSERIES_PROFILE_STATE\"; echo \"$2\" >> \"$MSERIES_PROFILE_LOG\" ;;\nesac\n").unwrap();
        make_executable(&profile_tool);
        let gdbus = bindir.join("gdbus");
        fs::write(
            &gdbus,
            "#!/bin/sh\nprintf 'PropertiesChanged ActiveProfile\\n'\n",
        )
        .unwrap();
        make_executable(&gdbus);
        let conf = root.join("power.conf");
        fs::write(&conf, format!("BATTERY_CAP_KHZ={cap}\n")).unwrap();
        Self {
            root,
            sys,
            conf,
            bindir,
        }
    }

    fn env(&self) -> Vec<(&'static str, String)> {
        let old_path = std::env::var("PATH").unwrap_or_default();
        vec![
            ("MSERIES_SYS", self.sys.display().to_string()),
            ("MSERIES_CONF", self.conf.display().to_string()),
            (
                "MSERIES_PROFILE_STATE",
                self.root.join("profile.state").display().to_string(),
            ),
            (
                "MSERIES_PROFILE_LOG",
                self.root.join("profiles.log").display().to_string(),
            ),
            ("PATH", format!("{}:{old_path}", self.bindir.display())),
        ]
    }

    fn run_pair(&self, args: &[&str]) -> (Output, Output) {
        let rust_bin = env!("CARGO_BIN_EXE_mseries-power-rs");
        let old_script = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../power/mseries-power");
        let mut shell = Command::new("bash");
        shell.arg(old_script).args(args);
        let mut rust = Command::new(rust_bin);
        rust.args(args);
        for (key, value) in self.env() {
            shell.env(key, &value);
            rust.env(key, value);
        }
        (shell.output().unwrap(), rust.output().unwrap())
    }

    fn policy_max(&self, name: &str) -> String {
        fs::read_to_string(self.sys.join(format!(
            "devices/system/cpu/cpufreq/{name}/scaling_max_freq"
        )))
        .unwrap()
        .trim()
        .into()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

#[cfg(unix)]
fn make_executable(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let mut permissions = fs::metadata(path).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(path, permissions).unwrap();
}

#[cfg(not(unix))]
fn make_executable(_path: &Path) {}

fn assert_same_result(shell: &Output, rust: &Output) {
    assert_eq!(
        shell.status.success(),
        rust.status.success(),
        "shell stderr: {}; rust stderr: {}",
        String::from_utf8_lossy(&shell.stderr),
        String::from_utf8_lossy(&rust.stderr)
    );
    assert_eq!(shell.stdout, rust.stdout);
}

#[test]
fn battery_power_saver_caps_only_performance_clusters() {
    let fixture = Fixture::new(Some(0), "power-saver", 2_208_000);
    let (shell, rust) = fixture.run_pair(&["cap"]);
    assert_same_result(&shell, &rust);
    assert!(shell.status.success());
    assert_eq!(fixture.policy_max("policy0"), "2064000");
    assert_eq!(fixture.policy_max("policy2"), "2208000");
    assert_eq!(fixture.policy_max("policy6"), "2208000");
}

#[test]
fn balanced_profile_and_ac_restore_the_hardware_ceiling() {
    for (on_ac, profile) in [
        (Some(0), "balanced"),
        (Some(1), "power-saver"),
        (Some(1), "balanced"),
    ] {
        let fixture = Fixture::new(on_ac, profile, 2_208_000);
        let (shell, rust) = fixture.run_pair(&["cap"]);
        assert_same_result(&shell, &rust);
        assert!(shell.status.success());
        assert_eq!(fixture.policy_max("policy2"), "3036000");
    }
}

#[test]
fn cap_is_clamped_to_hardware_minimum_and_maximum() {
    for (cap, expected) in [(9_999_999, "3036000"), (1, "600000")] {
        let fixture = Fixture::new(Some(0), "power-saver", cap);
        let (shell, rust) = fixture.run_pair(&["cap"]);
        assert_same_result(&shell, &rust);
        assert_eq!(fixture.policy_max("policy2"), expected);
    }
}

#[test]
fn a_zero_cap_restores_the_hardware_maximum() {
    let fixture = Fixture::new(Some(0), "power-saver", 0);
    let (shell, rust) = fixture.run_pair(&["cap"]);
    assert_same_result(&shell, &rust);
    assert_eq!(fixture.policy_max("policy2"), "3036000");
}

#[test]
fn charge_limit_writes_thresholds_then_persists_the_selected_value() {
    let fixture = Fixture::new(Some(1), "balanced", 2_208_000);
    let battery = fixture.sys.join("class/power_supply/macsmc-battery");
    fs::create_dir_all(&battery).unwrap();
    fs::write(battery.join("charge_control_start_threshold"), "75\n").unwrap();
    fs::write(battery.join("charge_control_end_threshold"), "80\n").unwrap();
    let (shell, rust) = fixture.run_pair(&["limit", "100"]);
    assert_same_result(&shell, &rust);
    assert!(shell.status.success());
    assert_eq!(
        fs::read_to_string(battery.join("charge_control_end_threshold"))
            .unwrap()
            .trim(),
        "100"
    );
    assert_eq!(
        fs::read_to_string(battery.join("charge_control_start_threshold"))
            .unwrap()
            .trim(),
        "95"
    );
    assert_eq!(
        fs::read_to_string(&fixture.conf)
            .unwrap()
            .matches("CHARGE_LIMIT=100")
            .count(),
        1
    );
}

#[test]
fn charge_limit_80_uses_the_configured_resume_threshold() {
    let fixture = Fixture::new(Some(1), "balanced", 2_208_000);
    let battery = fixture.sys.join("class/power_supply/macsmc-battery");
    fs::create_dir_all(&battery).unwrap();
    fs::write(battery.join("charge_control_start_threshold"), "75\n").unwrap();
    fs::write(battery.join("charge_control_end_threshold"), "80\n").unwrap();
    fs::write(&fixture.conf, "CHARGE_START=70 # customized resume point\n").unwrap();
    let (shell, rust) = fixture.run_pair(&["limit", "80"]);
    assert_same_result(&shell, &rust);
    assert!(shell.status.success());
    assert_eq!(
        fs::read_to_string(battery.join("charge_control_start_threshold"))
            .unwrap()
            .trim(),
        "70"
    );
    assert_eq!(
        fs::read_to_string(battery.join("charge_control_end_threshold"))
            .unwrap()
            .trim(),
        "80"
    );
}

#[test]
fn apply_sets_the_source_profile_and_charge_thresholds() {
    for (on_ac, expected_profile) in [(Some(0), "power-saver"), (Some(1), "balanced")] {
        let fixture = Fixture::new(on_ac, "balanced", 2_208_000);
        let battery = fixture.sys.join("class/power_supply/macsmc-battery");
        fs::create_dir_all(&battery).unwrap();
        fs::write(battery.join("charge_control_start_threshold"), "75\n").unwrap();
        fs::write(battery.join("charge_control_end_threshold"), "80\n").unwrap();
        let (shell, rust) = fixture.run_pair(&["apply"]);
        assert_same_result(&shell, &rust);
        assert!(shell.status.success());
        let profiles = fs::read_to_string(fixture.root.join("profiles.log")).unwrap();
        assert_eq!(
            profiles.lines().collect::<Vec<_>>(),
            [expected_profile, expected_profile]
        );
        assert_eq!(
            fs::read_to_string(battery.join("charge_control_start_threshold"))
                .unwrap()
                .trim(),
            "75"
        );
        assert_eq!(
            fs::read_to_string(battery.join("charge_control_end_threshold"))
                .unwrap()
                .trim(),
            "80"
        );
        assert_eq!(
            fixture.policy_max("policy2"),
            if on_ac == Some(0) {
                "2208000"
            } else {
                "3036000"
            }
        );
    }
}

#[test]
fn follow_reapplies_the_cap_and_fails_after_the_monitor_disconnects() {
    let fixture = Fixture::new(Some(0), "power-saver", 2_208_000);
    let (shell, rust) = fixture.run_pair(&["follow"]);
    assert_same_result(&shell, &rust);
    assert!(!rust.status.success());
    assert_eq!(fixture.policy_max("policy2"), "2208000");
}

#[test]
fn status_and_usage_match_the_existing_command() {
    let fixture = Fixture::new(Some(1), "balanced", 2_208_000);
    let battery = fixture.sys.join("class/power_supply/macsmc-battery");
    fs::create_dir_all(&battery).unwrap();
    for (name, value) in [
        ("capacity", "63"),
        ("status", "Discharging"),
        ("energy_full", "910"),
        ("energy_full_design", "1000"),
        ("cycle_count", "125"),
        ("charge_control_end_threshold", "80"),
        ("charge_control_start_threshold", "75"),
    ] {
        fs::write(battery.join(name), format!("{value}\n")).unwrap();
    }
    let (shell_status, rust_status) = fixture.run_pair(&["status"]);
    assert_same_result(&shell_status, &rust_status);
    let (shell_bad, rust_bad) = fixture.run_pair(&["no-such-command"]);
    assert_same_result(&shell_bad, &rust_bad);
}

#[test]
fn invalid_commands_and_limit_values_are_rejected_like_the_existing_cli() {
    let fixture = Fixture::new(Some(1), "balanced", 2_208_000);
    for args in [&["limit"][..], &["limit", "90"], &["invalid"]] {
        let (shell, rust) = fixture.run_pair(args);
        assert_same_result(&shell, &rust);
        assert!(!rust.status.success());
    }
}

#[test]
fn a_failed_charge_limit_write_does_not_create_the_config_file() {
    let fixture = Fixture::new(Some(1), "balanced", 2_208_000);
    fs::remove_file(&fixture.conf).unwrap();
    let (shell, rust) = fixture.run_pair(&["limit", "80"]);
    assert_same_result(&shell, &rust);
    assert!(!rust.status.success());
    assert!(!fixture.conf.exists());
}

#[test]
fn missing_sensor_status_is_best_effort_and_matches() {
    let id = NEXT.fetch_add(1, Ordering::Relaxed);
    let root =
        std::env::temp_dir().join(format!("mseries-power-empty-{id}-{}", std::process::id()));
    fs::create_dir_all(&root).unwrap();
    let rust_bin = env!("CARGO_BIN_EXE_mseries-power-rs");
    let old_script = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../power/mseries-power");
    let envs = [
        ("MSERIES_SYS", root.join("no-sys").display().to_string()),
        ("MSERIES_CONF", root.join("no.conf").display().to_string()),
    ];
    let mut shell = Command::new("bash");
    shell.arg(old_script).arg("status");
    let mut rust = Command::new(rust_bin);
    rust.arg("status");
    for (key, value) in envs {
        shell.env(key, &value);
        rust.env(key, &value);
    }
    let shell_out = shell.output().unwrap();
    let rust_out = rust.output().unwrap();
    assert_same_result(&shell_out, &rust_out);
    let _ = fs::remove_dir_all(root);
}

#[test]
fn a_failed_sysfs_write_fails_in_both_implementations() {
    let fixture = Fixture::new(Some(0), "power-saver", 2_208_000);
    let path = fixture
        .sys
        .join("devices/system/cpu/cpufreq/policy0/scaling_max_freq");
    fs::remove_file(&path).unwrap();
    fs::create_dir(&path).unwrap();
    let (shell, rust) = fixture.run_pair(&["cap"]);
    assert_same_result(&shell, &rust);
    assert!(!rust.status.success());
}
