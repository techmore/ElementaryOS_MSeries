use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

const DEFAULT_PINS: &str = "/usr/share/mseries/panel-factory-pins.json";
const EXPECTED_PLUGIN_DIR: &str = "usr/lib/aarch64-linux-gnu/wingpanel-9";

fn usage() -> &'static str {
    "Usage:\n  mseries-panel-provenance-rs verify --root ROOT [--pins FILE] [--only NAME ...] [--skip-plugins]\n  mseries-panel-provenance-rs record --root ROOT --pins FILE --name NAME --commit SHA"
}

fn fail_with_code(message: impl AsRef<str>, code: u8) -> ExitCode {
    eprintln!("{}", message.as_ref());
    ExitCode::from(code)
}

struct CliArgs {
    command: String,
    root: PathBuf,
    pins: PathBuf,
    only: Vec<String>,
    skip_plugins: bool,
    name: String,
    commit: String,
}

fn parse_args(args: &[String]) -> Result<CliArgs, String> {
    let Some(command) = args.first() else {
        return Err(usage().into());
    };
    if command != "verify" && command != "record" {
        return Err(usage().into());
    }
    let mut root = None;
    let mut pins = PathBuf::from(DEFAULT_PINS);
    let mut only = Vec::new();
    let mut skip_plugins = false;
    let mut name = String::new();
    let mut commit = String::new();
    let mut index = 1;
    while index < args.len() {
        match args[index].as_str() {
            "--root" | "--pins" | "--name" | "--commit" => {
                let option = args[index].as_str();
                index += 1;
                let value = args
                    .get(index)
                    .ok_or_else(|| format!("{option} requires a value"))?;
                match option {
                    "--root" => root = Some(PathBuf::from(value)),
                    "--pins" => pins = PathBuf::from(value),
                    "--name" => name.clone_from(value),
                    "--commit" => commit.clone_from(value),
                    _ => unreachable!(),
                }
            }
            "--only" => {
                index += 1;
                while index < args.len() && !args[index].starts_with("--") {
                    only.push(args[index].clone());
                    index += 1;
                }
                if only.is_empty() {
                    return Err("--only requires at least one indicator name".into());
                }
                continue;
            }
            "--skip-plugins" => skip_plugins = true,
            unknown => return Err(format!("unrecognized argument: {unknown}\n{}", usage())),
        }
        index += 1;
    }
    let root = root.ok_or_else(|| "--root is required".to_owned())?;
    if command == "record" && (name.is_empty() || commit.is_empty()) {
        return Err("record requires --name and --commit".into());
    }
    if command == "record" && !only.is_empty() {
        return Err("--only is only valid for verify".into());
    }
    if command == "record" && skip_plugins {
        return Err("--skip-plugins is only valid for verify".into());
    }
    Ok(CliArgs {
        command: command.clone(),
        root,
        pins,
        only,
        skip_plugins,
        name,
        commit,
    })
}

fn load_pins(path: &Path) -> Result<Value, String> {
    let bytes = fs::read(path).map_err(|e| format!("cannot read {}: {e}", path.display()))?;
    let pins: Value =
        serde_json::from_slice(&bytes).map_err(|e| format!("invalid pin JSON: {e}"))?;
    if pins.get("schema").and_then(Value::as_u64) != Some(1) {
        return Err("Unsupported panel pin schema".into());
    }
    if !pins.get("indicators").is_some_and(Value::is_array) {
        return Err("Panel pin table has no indicators array".into());
    }
    Ok(pins)
}

fn entries(pins: &Value) -> Result<Vec<&Value>, String> {
    pins["indicators"]
        .as_array()
        .map(|v| v.iter().collect())
        .ok_or_else(|| "Panel pin table has no indicators array".into())
}

fn entry_name(entry: &Value) -> Result<&str, String> {
    entry
        .get("name")
        .and_then(Value::as_str)
        .ok_or_else(|| "Pin entry has no name".into())
}

fn valid_version(version: &str, expected: &str) -> bool {
    let version = version.trim();
    let value = if let Some((epoch, rest)) = version.split_once(':') {
        if epoch.is_empty() || !epoch.bytes().all(|b| b.is_ascii_digit()) {
            return false;
        }
        rest
    } else {
        version
    };
    let Some(suffix) = value.strip_prefix(expected) else {
        return false;
    };
    suffix.is_empty() || suffix.starts_with(['+', '~', '.', '-'])
}

fn get_string<'a>(entry: &'a Value, key: &str) -> Result<&'a str, String> {
    entry
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("pin entry is missing {key}"))
}

fn sha256(path: &Path) -> Result<String, String> {
    let bytes = fs::read(path).map_err(|e| format!("cannot read {}: {e}", path.display()))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn verify(
    root: &Path,
    pins_path: &Path,
    only: &[String],
    skip_plugins: bool,
) -> Result<String, String> {
    let pins = load_pins(pins_path)?;
    let mut all = entries(&pins)?;
    if !only.is_empty() {
        let known: Vec<&str> = all
            .iter()
            .filter_map(|e| e.get("name").and_then(Value::as_str))
            .collect();
        let unknown: Vec<&String> = only
            .iter()
            .filter(|name| !known.contains(&name.as_str()))
            .collect();
        if !unknown.is_empty() {
            let mut names: Vec<&str> = unknown.into_iter().map(String::as_str).collect();
            names.sort_unstable();
            return Err(format!("Unknown indicators: {}", names.join(", ")));
        }
        all.retain(|entry| {
            entry
                .get("name")
                .and_then(Value::as_str)
                .is_some_and(|name| only.iter().any(|item| item == name))
        });
    }

    let mut errors = Vec::new();
    for entry in all {
        let name = entry_name(entry)?;
        let package = get_string(entry, "package")?;
        let expected_version = get_string(entry, "version")?;
        let result = Command::new("dpkg-query")
            .arg(format!(
                "--admindir={}",
                root.join("var/lib/dpkg").display()
            ))
            .args(["-W", "-f=${db:Status-Status}\t${Version}", package])
            .output()
            .map_err(|e| format!("cannot run dpkg-query: {e}"))?;
        let stdout = String::from_utf8_lossy(&result.stdout);
        let clean = stdout.trim();
        let (status, version) = clean.split_once('\t').unwrap_or((clean, ""));
        if !result.status.success()
            || status != "installed"
            || !valid_version(version, expected_version)
        {
            errors.push(format!(
                "{package}: expected installed {expected_version} with packaging suffix; found {}",
                if clean.is_empty() { "missing" } else { clean }
            ));
        }

        let plugin = PathBuf::from(get_string(entry, "plugin")?);
        if plugin.parent() != Some(Path::new(EXPECTED_PLUGIN_DIR)) || plugin.is_absolute() {
            errors.push(format!(
                "{name}: unexpected Wingpanel ABI path {}",
                plugin.display()
            ));
        } else if !skip_plugins {
            let artifact = root.join(&plugin);
            let metadata = fs::metadata(&artifact);
            if !metadata.as_ref().is_ok_and(|m| m.is_file() && m.len() > 0) {
                errors.push(format!(
                    "{name}: missing or empty plugin {}",
                    artifact.display()
                ));
            } else {
                let record_path = root
                    .join("usr/share/mseries/panel-artifacts")
                    .join(format!("{name}.json"));
                let verify_record = || -> Result<(), String> {
                    let record: Value =
                        serde_json::from_slice(&fs::read(&record_path).map_err(|e| e.to_string())?)
                            .map_err(|e| e.to_string())?;
                    if !record.is_object()
                        || record.get("schema").and_then(Value::as_u64) != Some(1)
                    {
                        return Err("unsupported artifact record".into());
                    }
                    for key in [
                        "name",
                        "package",
                        "version",
                        "repository",
                        "commit",
                        "plugin",
                    ] {
                        if record.get(key) != entry.get(key) {
                            return Err(format!("pin metadata mismatch: {key}"));
                        }
                    }
                    let digest = sha256(&artifact)?;
                    if record.get("sha256").and_then(Value::as_str) != Some(&digest) {
                        return Err("plugin SHA256 mismatch".into());
                    }
                    Ok(())
                };
                if let Err(error) = verify_record() {
                    errors.push(format!(
                        "{name}: invalid artifact provenance {}: {error}",
                        record_path.display()
                    ));
                }
            }
        }
    }
    if errors.is_empty() {
        Ok(format!(
            "Factory panel package versions{} match pinned requirements.",
            if skip_plugins { "" } else { " and plugins" }
        ))
    } else {
        Err(format!(
            "Factory panel compatibility check failed:\n{}",
            errors.join("\n")
        ))
    }
}

fn record(root: &Path, pins_path: &Path, name: &str, commit: &str) -> Result<String, String> {
    let pins = load_pins(pins_path)?;
    let entry = entries(&pins)?
        .into_iter()
        .find(|entry| entry.get("name").and_then(Value::as_str) == Some(name))
        .ok_or_else(|| format!("Unknown indicator: {name}"))?;
    if get_string(entry, "commit")? != commit {
        return Err("Built source commit does not match pin table".into());
    }
    let plugin = PathBuf::from(get_string(entry, "plugin")?);
    if plugin.is_absolute() || plugin.parent() != Some(Path::new(EXPECTED_PLUGIN_DIR)) {
        return Err("Unexpected Wingpanel ABI path".into());
    }
    let artifact = root.join(&plugin);
    if !fs::metadata(&artifact).is_ok_and(|m| m.is_file() && m.len() > 0) {
        return Err(format!(
            "Missing or empty built plugin: {}",
            artifact.display()
        ));
    }

    let mut value = serde_json::Map::new();
    for key in [
        "name",
        "package",
        "version",
        "repository",
        "commit",
        "plugin",
    ] {
        value.insert(
            key.to_owned(),
            entry
                .get(key)
                .ok_or_else(|| format!("pin entry is missing {key}"))?
                .clone(),
        );
    }
    value.insert("schema".into(), json!(1));
    value.insert("sha256".into(), json!(sha256(&artifact)?));
    let destination = root
        .join("usr/share/mseries/panel-artifacts")
        .join(format!("{name}.json"));
    fs::create_dir_all(destination.parent().expect("fixed parent path"))
        .map_err(|e| e.to_string())?;
    let mut rendered =
        serde_json::to_string_pretty(&Value::Object(value)).map_err(|e| e.to_string())?;
    rendered.push('\n');
    fs::write(&destination, rendered).map_err(|e| e.to_string())?;
    Ok(destination.display().to_string())
}

fn main() -> ExitCode {
    let mut args: Vec<String> = env::args().skip(1).collect();
    let invoked_as = env::args()
        .next()
        .and_then(|path| {
            PathBuf::from(path)
                .file_name()
                .map(|name| name.to_string_lossy().into_owned())
        })
        .unwrap_or_default();
    if invoked_as == "verify-panel-packages" {
        args.insert(0, "verify".into());
    } else if invoked_as == "record-panel-artifact" {
        args.insert(0, "record".into());
    }
    let parsed = match parse_args(&args) {
        Ok(value) => value,
        Err(error) => return fail_with_code(error, 2),
    };
    let result = if parsed.command == "verify" {
        verify(
            &parsed.root,
            &parsed.pins,
            &parsed.only,
            parsed.skip_plugins,
        )
    } else {
        record(&parsed.root, &parsed.pins, &parsed.name, &parsed.commit)
    };
    match result {
        Ok(message) => {
            println!("{message}");
            ExitCode::SUCCESS
        }
        Err(error) => {
            let usage_error = error == "Unsupported panel pin schema"
                || error.starts_with("Unknown indicators:")
                || error.starts_with("Unknown indicator:")
                || error == "Built source commit does not match pin table"
                || error == "Unexpected Wingpanel ABI path"
                || error.starts_with("Missing or empty built plugin:");
            fail_with_code(error, if usage_error { 2 } else { 1 })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn package_version_accepts_epoch_and_packaging_suffixes() {
        for version in ["8.0.1", "8.0.1-1", "8.0.1~daily", "2:8.0.1+git"] {
            assert!(valid_version(version, "8.0.1"), "{version}");
        }
        for version in ["8.0.10", "7:8.0.0", "8.0.1bad"] {
            assert!(!valid_version(version, "8.0.1"), "{version}");
        }
    }

    #[test]
    fn verifies_path_is_the_expected_abi_directory() {
        assert_eq!(
            Path::new("usr/lib/aarch64-linux-gnu/wingpanel-9/libnetwork.so").parent(),
            Some(Path::new(EXPECTED_PLUGIN_DIR))
        );
        assert_ne!(
            Path::new("usr/lib/other/libnetwork.so").parent(),
            Some(Path::new(EXPECTED_PLUGIN_DIR))
        );
        assert!(Path::new("/usr/lib/aarch64-linux-gnu/wingpanel-9/libnetwork.so").is_absolute());
    }
}
