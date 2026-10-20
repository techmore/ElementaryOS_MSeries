use std::env;
use std::error::Error;
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode, Output};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

const INPUT_SOURCES: &str = "org.gnome.desktop.input-sources";
const WM_KEYS: &str = "io.elementary.desktop.wm.keybindings";
const MEDIA_KEYS: &str = "org.gnome.settings-daemon.plugins.media-keys";
const CUSTOM_KEY_BASE: &str = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/";
const SHORTCUTS: [(&str, &str); 2] = [
    ("mseries-launcher0", "<Control>space"),
    ("mseries-launcher1", "<Super>space"),
];

fn main() -> ExitCode {
    match apply() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("error: {error}");
            ExitCode::FAILURE
        }
    }
}

fn apply() -> Result<()> {
    let home = PathBuf::from(env::var_os("HOME").ok_or("HOME is not set")?);
    let assets = assets_dir()?;

    let mut options = get_strv(INPUT_SOURCES, "xkb-options")?;
    if !options.iter().any(|value| value == "ctrl:swap_lwin_lctl") {
        options.push("ctrl:swap_lwin_lctl".into());
        set_strv(INPUT_SOURCES, "xkb-options", &options)?;
    }

    for (action, binding) in [
        ("screenshot", "<Control><Shift>3"),
        ("area-screenshot", "<Control><Shift>4"),
    ] {
        let mut existing = get_strv(WM_KEYS, action)?;
        if !existing.iter().any(|value| value == binding) {
            existing.push(binding.to_owned());
            set_strv(WM_KEYS, action, &existing)?;
        }
    }

    let launcher = home.join(".local/bin/mseries-launcher");
    copy_executable(&assets.join("mseries-launcher.py"), &launcher)?;
    let keys_helper = home.join(".local/libexec/mseries-launcher-keys");
    copy_executable(&launcher_keys_helper(&assets)?, &keys_helper)?;
    let keys_autostart = home.join(".config/autostart/mseries-launcher-keys.desktop");
    write_autostart(&keys_autostart, "M-series launcher shortcuts", &keys_helper)?;
    run(Command::new(&keys_helper).arg("--once"))?;

    let pictures = user_dir("PICTURES", &home.join("Pictures"));
    let downloads = user_dir("DOWNLOAD", &home.join("Downloads"));
    let target = downloads.join("Screenshots");
    fs::create_dir_all(&target)?;
    fs::create_dir_all(&pictures)?;
    let link = pictures.join("Screenshots");
    if !link.exists() && !is_symlink(&link) {
        symlink(&target, &link)?;
    } else if !same_resolved_path(&link, &target) {
        println!(
            "Existing screenshot folder preserved: {}. Move it manually to redirect saves.",
            link.display()
        );
    }

    set_string(
        "org.gnome.desktop.wm.preferences",
        "button-layout",
        "close,minimize,maximize:",
    )?;
    set_boolean("org.gnome.desktop.datetime", "automatic-timezone", false)?;
    set_boolean(
        "org.gnome.settings-daemon.plugins.power",
        "ambient-enabled",
        false,
    )?;
    set_boolean("org.gnome.settings-daemon.plugins.power", "idle-dim", false)?;
    set_boolean("org.gnome.mutter", "edge-tiling", true)?;
    set_strv(
        "org.gnome.mutter.keybindings",
        "toggle-tiled-left",
        &["<Super>Left".into()],
    )?;
    set_strv(
        "org.gnome.mutter.keybindings",
        "toggle-tiled-right",
        &["<Super>Right".into()],
    )?;

    bind_launcher_shortcuts(&launcher)?;
    let brightness_source = brightness_helper()?;
    let brightness = home.join(".local/libexec/mseries-brightness");
    copy_executable(&brightness_source, &brightness)?;
    let brightness_autostart = home.join(".config/autostart/mseries-brightness.desktop");
    write_autostart(
        &brightness_autostart,
        "M-series brightness keys",
        &brightness,
    )?;

    println!("Command acts as Ctrl; physical left Ctrl acts as Super. Command+Space opens the launcher. Brightness keys start at next login.");
    println!("To start now: {}", brightness.display());
    Ok(())
}

fn bind_launcher_shortcuts(launcher: &Path) -> Result<()> {
    for action in ["switch-input-source", "switch-input-source-backward"] {
        let current = get_strv(MEDIA_KEYS, action)?;
        let wanted: Vec<String> = current
            .iter()
            .filter(|binding| !binding.eq_ignore_ascii_case("<Super>space"))
            .cloned()
            .collect();
        if wanted != current {
            set_strv(MEDIA_KEYS, action, &wanted)?;
        }
    }

    let mut paths = Vec::new();
    for (name, binding) in SHORTCUTS {
        let path = format!("{CUSTOM_KEY_BASE}{name}/");
        for (key, value) in [
            ("name", "M-series launcher"),
            (
                "command",
                launcher.to_str().ok_or("launcher path is not UTF-8")?,
            ),
            ("binding", binding),
        ] {
            let existing = get_string_with_path(
                "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding",
                &path,
                key,
            )?;
            if existing != value {
                set_string_with_path(
                    "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding",
                    &path,
                    key,
                    value,
                )?;
            }
        }
        paths.push(path);
    }

    let mut existing = get_strv(MEDIA_KEYS, "custom-keybindings")?;
    let mut changed = false;
    for path in paths {
        if !existing.contains(&path) {
            existing.push(path);
            changed = true;
        }
    }
    if changed {
        set_strv(MEDIA_KEYS, "custom-keybindings", &existing)?;
    }
    Ok(())
}

fn assets_dir() -> Result<PathBuf> {
    if let Some(path) = env::var_os("MSERIES_SETTINGS_ASSET_DIR") {
        return Ok(PathBuf::from(path));
    }
    let source = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .map(|root| root.join("mseries"));
    if let Some(path) = source.filter(|path| path.join("mseries-launcher.py").is_file()) {
        return Ok(path);
    }
    let installed = PathBuf::from("/usr/share/elementary-mac/mseries");
    if installed.join("mseries-launcher.py").is_file() {
        return Ok(installed);
    }
    Err("could not find mseries-launcher.py; set MSERIES_SETTINGS_ASSET_DIR".into())
}

fn brightness_helper() -> Result<PathBuf> {
    let installed = PathBuf::from("/usr/libexec/mseries-brightness");
    if installed.is_file() {
        return Ok(installed);
    }
    let source = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .ok_or("could not locate repository root")?
        .join("mkosi.images/apple-silicon/mkosi.extra/usr/libexec/mseries-brightness");
    if source.is_file() {
        Ok(source)
    } else {
        Err(format!("brightness helper is missing: {}", source.display()).into())
    }
}

fn launcher_keys_helper(assets: &Path) -> Result<PathBuf> {
    let installed = PathBuf::from("/usr/libexec/mseries/launcher-keys");
    if installed.is_file() {
        return Ok(installed);
    }
    let reference = assets.join("mseries-launcher-keys.py");
    if reference.is_file() {
        Ok(reference)
    } else {
        Err(format!("launcher key helper is missing: {}", reference.display()).into())
    }
}

fn get_strv(schema: &str, key: &str) -> Result<Vec<String>> {
    let output = run(Command::new("gsettings").arg("get").arg(schema).arg(key))?;
    parse_strv(&String::from_utf8(output.stdout)?)
}

fn set_strv(schema: &str, key: &str, values: &[String]) -> Result<()> {
    run(Command::new("gsettings")
        .arg("set")
        .arg(schema)
        .arg(key)
        .arg(format_strv(values)))?;
    Ok(())
}

fn set_string(schema: &str, key: &str, value: &str) -> Result<()> {
    run(Command::new("gsettings")
        .arg("set")
        .arg(schema)
        .arg(key)
        .arg(format_gvariant_string(value)))?;
    Ok(())
}

fn set_boolean(schema: &str, key: &str, value: bool) -> Result<()> {
    run(Command::new("gsettings")
        .arg("set")
        .arg(schema)
        .arg(key)
        .arg(value.to_string()))?;
    Ok(())
}

fn get_string_with_path(schema: &str, path: &str, key: &str) -> Result<String> {
    let schema_path = format!("{schema}:{path}");
    let output = run(Command::new("gsettings")
        .arg("get")
        .arg(schema_path)
        .arg(key))?;
    parse_gvariant_string(&String::from_utf8(output.stdout)?)
}

fn set_string_with_path(schema: &str, path: &str, key: &str, value: &str) -> Result<()> {
    let schema_path = format!("{schema}:{path}");
    run(Command::new("gsettings")
        .arg("set")
        .arg(schema_path)
        .arg(key)
        .arg(format_gvariant_string(value)))?;
    Ok(())
}

fn parse_strv(input: &str) -> Result<Vec<String>> {
    let chars: Vec<char> = input.trim().chars().collect();
    let mut index = 0;
    skip_space(&chars, &mut index);
    expect(&chars, &mut index, '[')?;
    let mut values = Vec::new();
    loop {
        skip_space(&chars, &mut index);
        if chars.get(index) == Some(&']') {
            index += 1;
            break;
        }
        if !values.is_empty() {
            expect(&chars, &mut index, ',')?;
            skip_space(&chars, &mut index);
        }
        values.push(parse_quoted(&chars, &mut index)?);
        skip_space(&chars, &mut index);
        if chars.get(index) == Some(&']') {
            index += 1;
            break;
        }
    }
    skip_space(&chars, &mut index);
    if index != chars.len() {
        return Err("unexpected text after GVariant string array".into());
    }
    Ok(values)
}

fn parse_gvariant_string(input: &str) -> Result<String> {
    let chars: Vec<char> = input.trim().chars().collect();
    let mut index = 0;
    skip_space(&chars, &mut index);
    let value = parse_quoted(&chars, &mut index)?;
    skip_space(&chars, &mut index);
    if index != chars.len() {
        return Err("unexpected text after GVariant string".into());
    }
    Ok(value)
}

fn parse_quoted(chars: &[char], index: &mut usize) -> Result<String> {
    expect(chars, index, '\'')?;
    let mut value = String::new();
    loop {
        let character = *chars.get(*index).ok_or("unterminated GVariant string")?;
        *index += 1;
        match character {
            '\'' => return Ok(value),
            '\\' => {
                let escaped = *chars.get(*index).ok_or("unfinished GVariant escape")?;
                *index += 1;
                match escaped {
                    'a' => value.push('\x07'),
                    'b' => value.push('\x08'),
                    'f' => value.push('\x0c'),
                    'n' => value.push('\n'),
                    'r' => value.push('\r'),
                    't' => value.push('\t'),
                    'v' => value.push('\x0b'),
                    '\\' | '\'' | '"' | '?' => value.push(escaped),
                    'u' | 'U' => {
                        let digits = if escaped == 'u' { 4 } else { 8 };
                        let scalar = parse_hex_escape(chars, index, digits)?;
                        value.push(char::from_u32(scalar).ok_or("invalid Unicode escape")?);
                    }
                    'x' => {
                        let scalar = parse_hex_escape(chars, index, 2)?;
                        value.push(char::from_u32(scalar).ok_or("invalid hexadecimal escape")?);
                    }
                    '0'..='7' => {
                        let mut scalar = escaped.to_digit(8).ok_or("invalid octal escape")?;
                        for _ in 0..2 {
                            let Some(digit) = chars.get(*index).and_then(|value| value.to_digit(8))
                            else {
                                break;
                            };
                            scalar = scalar * 8 + digit;
                            *index += 1;
                        }
                        value.push(char::from_u32(scalar).ok_or("invalid octal escape")?);
                    }
                    other => return Err(format!("unsupported GVariant escape: \\{other}").into()),
                }
            }
            other => value.push(other),
        }
    }
}

fn parse_hex_escape(chars: &[char], index: &mut usize, digits: usize) -> Result<u32> {
    let end = index.checked_add(digits).ok_or("escape length overflow")?;
    let text: String = chars
        .get(*index..end)
        .ok_or("short GVariant escape")?
        .iter()
        .collect();
    *index = end;
    Ok(u32::from_str_radix(&text, 16)?)
}

fn format_strv(values: &[String]) -> String {
    format!(
        "[{}]",
        values
            .iter()
            .map(|value| format_gvariant_string(value))
            .collect::<Vec<_>>()
            .join(", ")
    )
}

fn format_gvariant_string(value: &str) -> String {
    let mut quoted = String::from("'");
    for character in value.chars() {
        match character {
            '\\' => quoted.push_str("\\\\"),
            '\'' => quoted.push_str("\\'"),
            '\n' => quoted.push_str("\\n"),
            '\r' => quoted.push_str("\\r"),
            '\t' => quoted.push_str("\\t"),
            '\0' => quoted.push_str("\\u0000"),
            other => quoted.push(other),
        }
    }
    quoted.push('\'');
    quoted
}

fn expect(chars: &[char], index: &mut usize, expected: char) -> Result<()> {
    if chars.get(*index) != Some(&expected) {
        return Err(format!("expected {expected:?} in GVariant value").into());
    }
    *index += 1;
    Ok(())
}

fn skip_space(chars: &[char], index: &mut usize) {
    while chars
        .get(*index)
        .is_some_and(|character| character.is_whitespace())
    {
        *index += 1;
    }
}

fn user_dir(kind: &str, fallback: &Path) -> PathBuf {
    Command::new("xdg-user-dir")
        .arg(kind)
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| fallback.to_path_buf())
}

fn copy_executable(source: &Path, destination: &Path) -> Result<()> {
    if !source.is_file() {
        return Err(format!("required file is missing: {}", source.display()).into());
    }
    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::copy(source, destination)?;
    fs::set_permissions(destination, fs::Permissions::from_mode(0o755))?;
    Ok(())
}

fn write_autostart(path: &Path, name: &str, executable: &Path) -> Result<()> {
    let parent = path
        .parent()
        .ok_or("autostart file has no parent directory")?;
    fs::create_dir_all(parent)?;
    let executable = executable.to_str().ok_or("autostart path is not UTF-8")?;
    fs::write(path, format!("[Desktop Entry]\nType=Application\nName={name}\nExec=\"{executable}\"\nOnlyShowIn=Pantheon;\nNoDisplay=true\n"))?;
    Ok(())
}

fn is_symlink(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok_and(|metadata| metadata.file_type().is_symlink())
}

#[cfg(unix)]
fn symlink(target: &Path, link: &Path) -> Result<()> {
    std::os::unix::fs::symlink(target, link)?;
    Ok(())
}

fn same_resolved_path(left: &Path, right: &Path) -> bool {
    match (fs::canonicalize(left), fs::canonicalize(right)) {
        (Ok(left), Ok(right)) => left == right,
        _ => false,
    }
}

fn run(command: &mut Command) -> Result<Output> {
    let shown = format!("{:?}", command);
    let output = command.output()?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("{shown} failed with {}: {}", output.status, stderr.trim()).into());
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::{format_strv, parse_gvariant_string, parse_strv};

    #[test]
    fn preserves_gsettings_string_arrays() {
        let existing = "['us', '<Control>space', 'ctrl:swap_lwin_lctl']";
        assert_eq!(
            parse_strv(existing).unwrap(),
            ["us", "<Control>space", "ctrl:swap_lwin_lctl"]
        );
        assert_eq!(parse_strv("[]").unwrap(), Vec::<String>::new());
    }

    #[test]
    fn gvariant_string_array_formatter_round_trips_escaped_values() {
        let values = vec![
            "<Control>space".into(),
            "quote' and slash\\".into(),
            "tab\tline\nbreak".into(),
            "café".into(),
        ];
        assert_eq!(parse_strv(&format_strv(&values)).unwrap(), values);
    }

    #[test]
    fn reads_gvariant_octal_and_unicode_escapes() {
        assert_eq!(
            parse_gvariant_string("'line\\n\u{00e9}\\141'").unwrap(),
            "line\néa"
        );
    }

    #[test]
    fn rejects_malformed_gsettings_arrays() {
        assert!(parse_strv("['one',]").is_err());
        assert!(parse_strv("['unterminated]").is_err());
        assert!(parse_strv("not a variant").is_err());
    }
}
