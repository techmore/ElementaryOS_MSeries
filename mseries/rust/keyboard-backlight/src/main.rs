use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode, Output};
use std::thread;
use std::time::Duration;

const SENSOR_ROOT: &str = "/sys/bus/iio/devices";
const UPOWER: &str = "org.freedesktop.UPower";
const KBD_PATH: &str = "/org/freedesktop/UPower/KbdBacklight";
const KBD_IFACE: &str = "org.freedesktop.UPower.KbdBacklight";
const LOGIND: &str = "org.freedesktop.login1";
const LOGIND_PATH: &str = "/org/freedesktop/login1";
const LOGIND_MANAGER: &str = "org.freedesktop.login1.Manager";

#[derive(Debug, PartialEq)]
enum Cli {
    Run { once: bool },
    Step(i32),
}

fn parse_args(args: &[String]) -> Result<Cli, String> {
    let mut once = false;
    let mut step = None;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--once" => once = true,
            "--step" => {
                index += 1;
                step = Some(match args.get(index).map(String::as_str) {
                    Some("up") => 1,
                    Some("down") => -1,
                    _ => {
                        return Err(
                            "argument --step: invalid choice (choose from 'up', 'down')".into()
                        );
                    }
                });
            }
            value if value.starts_with('-') => {
                return Err(format!("unrecognized arguments: {value}"));
            }
            value => return Err(format!("unrecognized arguments: {value}")),
        }
        index += 1;
    }
    if let Some(direction) = step {
        Ok(Cli::Step(direction))
    } else {
        Ok(Cli::Run { once })
    }
}

fn percent(lux: f64) -> i32 {
    py_round(100.0 * (180.0 - lux) / 172.0).clamp(0, 100)
}

fn py_round(value: f64) -> i32 {
    let floor = value.floor();
    let fraction = value - floor;
    if fraction < 0.5 {
        floor as i32
    } else if fraction > 0.5 || (floor as i64) % 2 != 0 {
        (floor + 1.0) as i32
    } else {
        floor as i32
    }
}

fn illuminance(root: &Path) -> Result<f64, String> {
    let entries =
        fs::read_dir(root).map_err(|_| "No readable ambient illuminance sensor".to_owned())?;
    let mut devices: Vec<PathBuf> = entries
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| {
            path.file_name()
                .and_then(|n| n.to_str())
                .is_some_and(|n| n.starts_with("iio:device"))
        })
        .collect();
    devices.sort();
    for device in devices {
        let name = match fs::read_to_string(device.join("name")) {
            Ok(name) => name,
            Err(_) => continue,
        };
        if !name.trim().ends_with("-als") {
            continue;
        }
        let value = match fs::read_to_string(device.join("in_illuminance_input"))
            .ok()
            .and_then(|s| s.trim().parse::<f64>().ok())
        {
            Some(value) if value.is_finite() && value >= 0.0 => value,
            _ => continue,
        };
        return Ok(value);
    }
    Err("No readable ambient illuminance sensor".into())
}

fn run_output(program: &str, args: &[&str]) -> Result<Output, String> {
    Command::new(program)
        .args(args)
        .output()
        .map_err(|error| format!("{program}: {error}"))
}

fn successful(program: &str, args: &[&str]) -> Result<String, String> {
    let output = run_output(program, args)?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_owned());
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

fn busctl_get(
    service: &str,
    path: &str,
    interface: &str,
    property: &str,
) -> Result<String, String> {
    successful(
        "busctl",
        &[
            "--system",
            "--timeout=2s",
            "get-property",
            service,
            path,
            interface,
            property,
        ],
    )
}

fn busctl_call(
    service: &str,
    path: &str,
    interface: &str,
    method: &str,
    signature: &str,
    value: Option<i32>,
) -> Result<String, String> {
    let mut args = vec![
        "--system",
        "--timeout=2s",
        "call",
        service,
        path,
        interface,
        method,
    ];
    if !signature.is_empty() {
        args.push(signature);
    }
    let value_string = value.map(|v| v.to_string());
    if let Some(value) = value_string.as_deref() {
        args.push(value);
    }
    successful("busctl", &args)
}

fn bus_int(output: &str) -> Result<i32, String> {
    output
        .split_whitespace()
        .last()
        .and_then(|value| value.parse().ok())
        .ok_or_else(|| format!("unexpected busctl integer response: {output}"))
}

fn keyboard_maximum() -> Result<i32, String> {
    let maximum = bus_int(&busctl_call(
        UPOWER,
        KBD_PATH,
        KBD_IFACE,
        "GetMaxBrightness",
        "",
        None,
    )?)?;
    if maximum <= 0 {
        return Err("Keyboard backlight unavailable".into());
    }
    Ok(maximum)
}

fn brightness(method: &str, value: Option<i32>) -> Result<i32, String> {
    let output = busctl_call(
        UPOWER,
        KBD_PATH,
        KBD_IFACE,
        method,
        if value.is_some() { "i" } else { "" },
        value,
    )?;
    if value.is_some() {
        Ok(0)
    } else {
        bus_int(&output)
    }
}

fn lid_closed() -> bool {
    busctl_get(LOGIND, LOGIND_PATH, LOGIND_MANAGER, "LidClosed")
        .map(|output| output.split_whitespace().last() == Some("true"))
        .unwrap_or(false)
}

fn session_active() -> Result<bool, String> {
    let uid = successful("id", &["-u"])?;
    let sessions = successful("loginctl", &["list-sessions", "--no-legend", "--no-pager"])?;
    for line in sessions.lines() {
        let mut fields = line.split_whitespace();
        let Some(session_id) = fields.next() else {
            continue;
        };
        let Some(session_uid) = fields.next() else {
            continue;
        };
        if session_uid != uid {
            continue;
        }
        let output = successful(
            "loginctl",
            &[
                "show-session",
                session_id,
                "--property=Type",
                "--property=Active",
                "--property=LockedHint",
            ],
        )?;
        let mut session_type = "";
        let mut active = false;
        let mut locked = true;
        for property in output.lines() {
            if let Some(value) = property.strip_prefix("Type=") {
                session_type = value;
            }
            if let Some(value) = property.strip_prefix("Active=") {
                active = value == "yes";
            }
            if let Some(value) = property.strip_prefix("LockedHint=") {
                locked = value == "yes";
            }
        }
        if matches!(session_type, "wayland" | "x11") && active && !locked {
            return Ok(true);
        }
    }
    Ok(false)
}

fn step(maximum: i32, direction: i32) -> i32 {
    py_round(maximum as f64 * 0.1).max(1) * direction
}

#[derive(Default)]
struct AutoState {
    last: Option<i32>,
    paused_lux: Option<f64>,
}

fn run_once(root: &Path, maximum: i32, state: &mut AutoState) -> Result<String, String> {
    let lux = illuminance(root)?;
    let current = brightness("GetBrightness", None)?;
    let target = auto_target(lux, current, maximum, state);
    if let Some(target) = target {
        if !lid_closed() && session_active()? {
            brightness("SetBrightness", Some(target))?;
            state.last = Some(brightness("GetBrightness", None)?);
        }
    }
    Ok(format!(
        "Ambient {lux} lx; keyboard {}/{maximum}",
        state.last.unwrap_or(current)
    ))
}

fn auto_target(lux: f64, current: i32, maximum: i32, state: &mut AutoState) -> Option<i32> {
    if state.last.is_some_and(|last| current != last) {
        state.paused_lux = Some(lux);
    }
    state.last = Some(current);
    if state
        .paused_lux
        .is_some_and(|paused| (lux - paused).abs() >= 20.0_f64.max(paused * 0.4))
    {
        state.paused_lux = None;
    }
    if state.paused_lux.is_some() {
        return None;
    }
    let target = py_round(maximum as f64 * percent(lux) as f64 / 100.0);
    ((current - target).abs() as f64 >= (maximum as f64 * 0.04).max(1.0)).then_some(target)
}

fn main() -> ExitCode {
    let cli = match parse_args(&env::args().skip(1).collect::<Vec<_>>()) {
        Ok(cli) => cli,
        Err(error) => {
            eprintln!("{error}");
            return ExitCode::from(2);
        }
    };
    let result = match cli {
        Cli::Step(direction) => (|| {
            let maximum = keyboard_maximum()?;
            let current = brightness("GetBrightness", None)?;
            let target = (current + step(maximum, direction)).clamp(0, maximum);
            brightness("SetBrightness", Some(target)).map(|_| String::new())
        })(),
        Cli::Run { once } => (|| {
            let maximum = keyboard_maximum()?;
            if once {
                run_once(Path::new(SENSOR_ROOT), maximum, &mut AutoState::default())
            } else {
                let mut state = AutoState::default();
                loop {
                    match run_once(Path::new(SENSOR_ROOT), maximum, &mut state) {
                        Ok(message) => {
                            let _ = message;
                        }
                        Err(error) => eprintln!("Keyboard lighting: {error}"),
                    }
                    thread::sleep(Duration::from_secs(5));
                }
            }
        })(),
    };
    match result {
        Ok(message) => {
            if !message.is_empty() {
                println!("{message}");
            }
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            ExitCode::from(1)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn ambient_percentage_clamps_and_interpolates_like_python() {
        assert_eq!(percent(0.0), 100);
        assert_eq!(percent(8.0), 100);
        assert_eq!(percent(94.0), 50);
        assert_eq!(percent(180.0), 0);
        assert_eq!(percent(500.0), 0);
        assert_eq!(py_round(2.5), 2);
        assert_eq!(py_round(3.5), 4);
    }

    #[test]
    fn ignores_lid_sensor_and_invalid_als_values() {
        let root = std::env::temp_dir().join(format!("mseries-als-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("iio:device0")).unwrap();
        fs::create_dir_all(root.join("iio:device1")).unwrap();
        fs::write(root.join("iio:device0/name"), "aop-sensors-las\n").unwrap();
        fs::write(root.join("iio:device0/in_illuminance_input"), "999\n").unwrap();
        fs::write(root.join("iio:device1/name"), "aop-sensors-als\n").unwrap();
        fs::write(root.join("iio:device1/in_illuminance_input"), "12.5\n").unwrap();
        assert_eq!(illuminance(&root).unwrap(), 12.5);
        fs::write(root.join("iio:device1/in_illuminance_input"), "nan\n").unwrap();
        assert!(illuminance(&root).is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn manual_step_matches_python_rounding() {
        assert_eq!(step(255, 1), 26);
        assert_eq!(step(1, 1), 1);
        assert_eq!(step(255, -1), -26);
    }

    #[test]
    fn step_takes_precedence_when_once_is_also_passed() {
        let args = vec!["--step".into(), "up".into(), "--once".into()];
        assert_eq!(parse_args(&args), Ok(Cli::Step(1)));
    }

    #[test]
    fn manual_override_pauses_until_the_ambient_change_threshold() {
        let mut state = AutoState {
            last: Some(194),
            ..AutoState::default()
        };
        assert_eq!(auto_target(50.0, 100, 255, &mut state), None);
        assert_eq!(state.paused_lux, Some(50.0));
        assert_eq!(auto_target(69.0, 100, 255, &mut state), None);
        assert_eq!(auto_target(70.0, 100, 255, &mut state), Some(163));
        assert_eq!(state.paused_lux, None);
    }

    #[test]
    fn deadband_suppresses_small_adjustments() {
        let mut state = AutoState::default();
        assert_eq!(auto_target(94.0, 124, 255, &mut state), None);
        assert_eq!(
            auto_target(94.0, 117, 255, &mut AutoState::default()),
            Some(128)
        );
    }
}
