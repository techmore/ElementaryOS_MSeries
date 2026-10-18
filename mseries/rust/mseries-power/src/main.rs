// SPDX-License-Identifier: GPL-3.0-or-later
#![forbid(unsafe_code)]

use std::env;
use std::fs::{self, OpenOptions};
use std::io::{self, BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

const USAGE: &str = "usage: mseries-power status|limit 80|100|apply|cap|follow";

#[derive(Debug, Clone)]
struct Config {
    charge_limit: u32,
    charge_start: u32,
    battery_profile: String,
    ac_profile: String,
    battery_cap_khz: u64,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            charge_limit: 80,
            charge_start: 75,
            battery_profile: "power-saver".into(),
            ac_profile: "balanced".into(),
            battery_cap_khz: 2_400_000,
        }
    }
}

struct Paths {
    sys: PathBuf,
    conf: PathBuf,
}

impl Paths {
    fn from_env() -> Self {
        Self {
            sys: env::var_os("MSERIES_SYS")
                .map(PathBuf::from)
                .unwrap_or_else(|| "/sys".into()),
            conf: env::var_os("MSERIES_CONF")
                .map(PathBuf::from)
                .unwrap_or_else(|| "/etc/mseries/power.conf".into()),
        }
    }

    fn battery(&self) -> PathBuf {
        self.sys.join("class/power_supply/macsmc-battery")
    }

    fn ac_online(&self) -> PathBuf {
        self.sys.join("class/power_supply/macsmc-ac/online")
    }

    fn cpu_policies(&self) -> io::Result<Vec<PathBuf>> {
        let root = self.sys.join("devices/system/cpu/cpufreq");
        let mut policies = match fs::read_dir(root) {
            Ok(entries) => entries
                .filter_map(Result::ok)
                .map(|entry| entry.path())
                .filter(|path| {
                    path.file_name()
                        .is_some_and(|n| n.to_string_lossy().starts_with("policy"))
                })
                .collect::<Vec<_>>(),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Vec::new(),
            Err(error) => return Err(error),
        };
        policies.sort();
        Ok(policies)
    }
}

fn read_trimmed(path: &Path) -> io::Result<String> {
    fs::read_to_string(path).map(|value| value.trim().to_owned())
}

fn read_best_effort(path: &Path) -> String {
    read_trimmed(path).unwrap_or_else(|_| "unknown".into())
}

fn load_config(path: &Path) -> Result<Config, String> {
    let mut config = Config::default();
    let contents = match fs::read_to_string(path) {
        Ok(contents) => contents,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(config),
        Err(error) => return Err(format!("could not read {}: {error}", path.display())),
    };
    for (index, line) in contents.lines().enumerate() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        let value = value
            .trim()
            .split('#')
            .next()
            .unwrap_or_default()
            .trim()
            .trim_matches(['\'', '"']);
        let invalid = || format!("invalid {} at {}:{}", key.trim(), path.display(), index + 1);
        match key.trim() {
            "CHARGE_LIMIT" => config.charge_limit = value.parse().map_err(|_| invalid())?,
            "CHARGE_START" => config.charge_start = value.parse().map_err(|_| invalid())?,
            "BATTERY_PROFILE" => config.battery_profile = value.to_owned(),
            "AC_PROFILE" => config.ac_profile = value.to_owned(),
            "BATTERY_CAP_KHZ" => config.battery_cap_khz = value.parse().map_err(|_| invalid())?,
            _ => {}
        }
    }
    Ok(config)
}

fn write_value(path: &Path, value: &str) -> Result<(), String> {
    let result = OpenOptions::new()
        .write(true)
        .truncate(true)
        .open(path)
        .and_then(|mut file| file.write_all(value.as_bytes()));
    result.map_err(|_| format!("could not write {value} to {}", path.display()))
}

fn apply_limit(paths: &Paths, config: &Config) -> Result<(), String> {
    let battery = paths.battery();
    if config.charge_limit >= 100 {
        write_value(&battery.join("charge_control_end_threshold"), "100")?;
        write_value(&battery.join("charge_control_start_threshold"), "95")?;
    } else {
        write_value(
            &battery.join("charge_control_start_threshold"),
            &config.charge_start.to_string(),
        )?;
        write_value(
            &battery.join("charge_control_end_threshold"),
            &config.charge_limit.to_string(),
        )?;
    }
    Ok(())
}

fn command_output(program: &str, args: &[&str]) -> Option<String> {
    Command::new(program)
        .args(args)
        .output()
        .ok()
        .filter(|out| out.status.success())
        .map(|out| String::from_utf8_lossy(&out.stdout).trim().to_owned())
}

fn wanted_cap(paths: &Paths, config: &Config) -> u64 {
    let on_ac = read_trimmed(&paths.ac_online()).unwrap_or_else(|_| "1".into());
    let profile = command_output("powerprofilesctl", &["get"]).unwrap_or_else(|| "unknown".into());
    if on_ac == "1" || profile != "power-saver" {
        0
    } else {
        config.battery_cap_khz
    }
}

fn apply_cap(paths: &Paths, config: &Config) -> Result<(), String> {
    let cap = wanted_cap(paths, config);
    for policy in paths
        .cpu_policies()
        .map_err(|error| format!("could not list CPU policies: {error}"))?
    {
        let max_path = policy.join("cpuinfo_max_freq");
        let min_path = policy.join("cpuinfo_min_freq");
        let max = read_trimmed(&max_path)
            .ok()
            .and_then(|v| v.parse::<u64>().ok());
        let min = read_trimmed(&min_path)
            .ok()
            .and_then(|v| v.parse::<u64>().ok());
        let (Some(max), Some(min)) = (max, min) else {
            return Err(format!(
                "invalid CPU frequency policy: {}",
                policy.display()
            ));
        };
        let mut target = max;
        if max > 2_500_000 && cap > 0 {
            target = cap.min(max).max(min);
        }
        write_value(&policy.join("scaling_max_freq"), &target.to_string())?;
    }
    Ok(())
}

fn apply_source(paths: &Paths, config: &Config) -> Result<(), String> {
    let on_ac = read_trimmed(&paths.ac_online()).unwrap_or_else(|_| "1".into());
    let profile = if on_ac == "1" {
        &config.ac_profile
    } else {
        &config.battery_profile
    };
    let result = Command::new("powerprofilesctl")
        .args(["set", profile])
        .status()
        .map_err(|error| format!("could not run powerprofilesctl: {error}"))?;
    if !result.success() {
        return Err(format!("powerprofilesctl set {profile} failed"));
    }
    apply_cap(paths, config)
}

fn persist_limit(path: &Path, limit: u32) -> Result<(), String> {
    let old = fs::read_to_string(path).unwrap_or_default();
    let mut lines = Vec::new();
    let mut replaced = false;
    for line in old.lines() {
        if line.starts_with("CHARGE_LIMIT=") {
            if !replaced {
                lines.push(format!("CHARGE_LIMIT={limit}"));
                replaced = true;
            }
        } else {
            lines.push(line.to_owned());
        }
    }
    if !replaced {
        lines.push(format!("CHARGE_LIMIT={limit}"));
    }
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent)
        .map_err(|error| format!("could not create {}: {error}", parent.display()))?;
    let temp = path.with_extension(format!("tmp.{}", std::process::id()));
    fs::write(&temp, format!("{}\n", lines.join("\n")))
        .map_err(|error| format!("could not write {}: {error}", temp.display()))?;
    fs::rename(&temp, path)
        .map_err(|error| format!("could not replace {}: {error}", path.display()))
}

fn status(paths: &Paths) -> io::Result<()> {
    let battery = paths.battery();
    let full = read_trimmed(&battery.join("energy_full"))
        .ok()
        .and_then(|v| v.parse::<u64>().ok());
    let design = read_trimmed(&battery.join("energy_full_design"))
        .ok()
        .and_then(|v| v.parse::<u64>().ok());
    let health = match (full, design) {
        (Some(f), Some(d)) if d > 0 => (f.saturating_mul(100) / d).to_string(),
        _ => "unknown".into(),
    };
    println!(
        "battery: {}% ({}), health {}%, {} cycles",
        read_best_effort(&battery.join("capacity")),
        read_best_effort(&battery.join("status")),
        health,
        read_best_effort(&battery.join("cycle_count"))
    );
    println!(
        "charge limit: stop at {}%, resume at {}%",
        read_best_effort(&battery.join("charge_control_end_threshold")),
        read_best_effort(&battery.join("charge_control_start_threshold"))
    );
    let ac = read_best_effort(&paths.ac_online());
    let profile = command_output("powerprofilesctl", &["get"]).unwrap_or_else(|| "unknown".into());
    println!("power source online: {ac}; profile: {profile}");
    for policy in paths.cpu_policies()? {
        let name = policy.file_name().unwrap_or_default().to_string_lossy();
        println!(
            "cpus {}: max {} kHz (hardware {})",
            read_best_effort(&policy.join("related_cpus")),
            read_best_effort(&policy.join("scaling_max_freq")),
            read_best_effort(&policy.join("cpuinfo_max_freq"))
        );
        let _ = name;
    }
    Ok(())
}

fn follow(paths: &Paths, config: &Config) -> Result<(), String> {
    apply_cap(paths, config)?;
    let mut child = Command::new("gdbus")
        .args([
            "monitor",
            "--system",
            "--dest",
            "net.hadess.PowerProfiles",
            "--object-path",
            "/net/hadess/PowerProfiles",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("could not run gdbus monitor: {error}"))?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "could not read gdbus output".to_owned())?;
    for line in BufReader::new(stdout).lines() {
        let line = line.map_err(|error| format!("could not read gdbus output: {error}"))?;
        if line.contains("ActiveProfile") || line.contains("is owned by") {
            apply_cap(paths, config)?;
        }
    }
    let result = child
        .wait()
        .map_err(|error| format!("could not wait for gdbus: {error}"))?;
    if !result.success() {
        return Err("gdbus monitor disconnected".into());
    }
    Err("gdbus monitor disconnected".into())
}

fn run() -> Result<(), String> {
    let args = env::args().skip(1).collect::<Vec<_>>();
    let command = args.first().map(String::as_str).unwrap_or("status");
    let paths = Paths::from_env();
    let mut config = load_config(&paths.conf)?;
    match command {
        "apply" => {
            apply_limit(&paths, &config)?;
            apply_source(&paths, &config)
        }
        "cap" => apply_cap(&paths, &config),
        "follow" => follow(&paths, &config),
        "limit" if args.len() >= 2 && (args[1] == "80" || args[1] == "100") => {
            config.charge_limit = args[1].parse().map_err(|_| USAGE.to_owned())?;
            apply_limit(&paths, &config)?;
            persist_limit(&paths.conf, config.charge_limit)
        }
        "limit" => Err("usage: mseries-power limit 80|100".into()),
        "status" => status(&paths).map_err(|error| format!("could not read status: {error}")),
        _ => Err(USAGE.into()),
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
