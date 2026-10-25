use std::env;
use std::error::Error;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Command, ExitCode, Stdio};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

const MEDIA: &str = "org.gnome.settings-daemon.plugins.media-keys";
const BASE: &str = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/";
const SHORTCUTS: [(&str, &str); 2] = [
    ("mseries-launcher0", "<Control>space"),
    ("mseries-launcher1", "<Super>space"),
];

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("mseries-launcher-keys: {error}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<()> {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.iter().any(|arg| arg != "--once") || args.len() > 1 {
        return Err("usage: mseries-launcher-keys [--once]".into());
    }
    bind()?;
    if args.iter().any(|arg| arg == "--once") {
        return Ok(());
    }

    let mut monitor = Command::new("gsettings")
        .arg("monitor")
        .arg(MEDIA)
        .arg("custom-keybindings")
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()?;
    let stdout = monitor
        .stdout
        .take()
        .ok_or("gsettings monitor has no stdout")?;
    for line in BufReader::new(stdout).lines() {
        line?;
        bind()?;
    }
    let status = monitor.wait()?;
    if !status.success() {
        return Err(format!("gsettings monitor exited with {status}").into());
    }
    Ok(())
}

fn bind() -> Result<()> {
    let launcher = PathBuf::from(env::var_os("HOME").ok_or("HOME is not set")?)
        .join(".local/bin/mseries-launcher");
    let launcher = launcher.to_str().ok_or("launcher path is not UTF-8")?;
    let keys = "io.elementary.desktop.wm.keybindings";
    for action in ["switch-input-source", "switch-input-source-backward"] {
        let current = get_strv(keys, action)?;
        let wanted: Vec<String> = current
            .iter()
            .filter(|binding| !binding.eq_ignore_ascii_case("<Super>space"))
            .cloned()
            .collect();
        if current != wanted {
            set_strv(keys, action, &wanted)?;
        }
    }

    let mut paths = Vec::new();
    for (name, binding) in SHORTCUTS {
        let path = format!("{BASE}{name}/");
        let schema = format!("{MEDIA}.custom-keybinding:{path}");
        for (key, value) in [
            ("name", "M-series launcher"),
            ("command", launcher),
            ("binding", binding),
        ] {
            let current = get_string(&schema, key)?;
            if current != value {
                set_string(&schema, key, value)?;
            }
        }
        paths.push(path);
    }

    let existing = get_strv(MEDIA, "custom-keybindings")?;
    let mut missing = Vec::new();
    for path in paths {
        if !existing.contains(&path) {
            missing.push(path);
        }
    }
    if !missing.is_empty() {
        let mut combined = existing;
        combined.extend(missing);
        set_strv(MEDIA, "custom-keybindings", &combined)?;
    }
    Ok(())
}

fn get_strv(schema: &str, key: &str) -> Result<Vec<String>> {
    let output = Command::new("gsettings")
        .arg("get")
        .arg(schema)
        .arg(key)
        .output()?;
    check_output(&output, "gsettings get")?;
    parse_strv(&String::from_utf8(output.stdout)?)
}

fn set_strv(schema: &str, key: &str, values: &[String]) -> Result<()> {
    let value = format!(
        "[{}]",
        values
            .iter()
            .map(|value| quote_gvariant(value))
            .collect::<Vec<_>>()
            .join(", ")
    );
    let output = Command::new("gsettings")
        .arg("set")
        .arg(schema)
        .arg(key)
        .arg(value)
        .output()?;
    check_output(&output, "gsettings set")
}

fn get_string(schema: &str, key: &str) -> Result<String> {
    let output = Command::new("gsettings")
        .arg("get")
        .arg(schema)
        .arg(key)
        .output()?;
    check_output(&output, "gsettings get")?;
    parse_string(&String::from_utf8(output.stdout)?)
}

fn set_string(schema: &str, key: &str, value: &str) -> Result<()> {
    let output = Command::new("gsettings")
        .arg("set")
        .arg(schema)
        .arg(key)
        .arg(quote_gvariant(value))
        .output()?;
    check_output(&output, "gsettings set")
}

fn check_output(output: &std::process::Output, operation: &str) -> Result<()> {
    if output.status.success() {
        return Ok(());
    }
    Err(format!(
        "{operation} failed with {}: {}",
        output.status,
        String::from_utf8_lossy(&output.stderr).trim()
    )
    .into())
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
        return Err("unexpected trailing text in GVariant string array".into());
    }
    Ok(values)
}

fn parse_string(input: &str) -> Result<String> {
    let chars: Vec<char> = input.trim().chars().collect();
    let mut index = 0;
    skip_space(&chars, &mut index);
    let value = parse_quoted(&chars, &mut index)?;
    skip_space(&chars, &mut index);
    if index != chars.len() {
        return Err("unexpected trailing text in GVariant string".into());
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
                    'x' | 'u' | 'U' => {
                        let digits = match escaped {
                            'x' => 2,
                            'u' => 4,
                            _ => 8,
                        };
                        let end = index.checked_add(digits).ok_or("escape overflow")?;
                        let hex: String = chars
                            .get(*index..end)
                            .ok_or("short GVariant escape")?
                            .iter()
                            .collect();
                        *index = end;
                        let scalar = u32::from_str_radix(&hex, 16)?;
                        value.push(char::from_u32(scalar).ok_or("invalid Unicode escape")?);
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

fn quote_gvariant(value: &str) -> String {
    let mut quoted = String::from("'");
    for character in value.chars() {
        match character {
            '\\' => quoted.push_str("\\\\"),
            '\'' => quoted.push_str("\\'"),
            '\n' => quoted.push_str("\\n"),
            '\r' => quoted.push_str("\\r"),
            '\t' => quoted.push_str("\\t"),
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

#[cfg(test)]
mod tests {
    use super::{parse_string, parse_strv, quote_gvariant};

    #[test]
    fn preserves_existing_custom_shortcuts_and_filters_super_space() {
        let current = parse_strv("['<Alt>F2', '<Super>space', '<Control>space']").unwrap();
        let wanted: Vec<String> = current
            .iter()
            .filter(|binding| !binding.eq_ignore_ascii_case("<Super>space"))
            .cloned()
            .collect();
        assert_eq!(wanted, ["<Alt>F2", "<Control>space"]);
    }

    #[test]
    fn quoted_custom_values_round_trip() {
        let value = "M-series launcher: \"Finder\"\\apps";
        assert_eq!(parse_string(&quote_gvariant(value)).unwrap(), value);
    }

    #[test]
    fn rejects_malformed_variant_values() {
        assert!(parse_strv("['broken]").is_err());
        assert!(parse_string("not a string").is_err());
    }
}
