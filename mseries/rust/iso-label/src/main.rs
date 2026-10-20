use std::env;
use std::process::ExitCode;

fn volume_label(profile: &str, arch: &str) -> String {
    let mut label = String::with_capacity(32);
    for byte in format!("ELEMENTARY_{profile}_{arch}").bytes() {
        let normalized = match byte {
            b'a'..=b'z' => byte.to_ascii_uppercase(),
            b'-' => b'_',
            _ => byte,
        };
        if normalized.is_ascii_uppercase() || normalized.is_ascii_digit() || normalized == b'_' {
            label.push(normalized as char);
            if label.len() == 32 {
                break;
            }
        }
    }
    label
}

fn main() -> ExitCode {
    let mut args = env::args().skip(1);
    let (Some(profile), Some(arch), None) = (args.next(), args.next(), args.next()) else {
        eprintln!("usage: mseries-iso-label PROFILE ARCH");
        return ExitCode::from(2);
    };
    println!("{}", volume_label(&profile, &arch));
    ExitCode::SUCCESS
}

#[cfg(test)]
mod tests {
    use super::volume_label;

    #[test]
    fn preserves_existing_iso_label_cases() {
        assert_eq!(volume_label("daily", "arm64"), "ELEMENTARY_DAILY_ARM64");
        assert_eq!(
            volume_label("daily-proposed", "x86-64"),
            "ELEMENTARY_DAILY_PROPOSED_X86_64"
        );
        assert_eq!(
            volume_label("abcdefghijklmnopqrstuvwx", "arm64"),
            "ELEMENTARY_ABCDEFGHIJKLMNOPQRSTU"
        );
    }

    #[test]
    fn matches_c_locale_filtering_and_truncates_after_normalization() {
        assert_eq!(volume_label("é A.b", "arm-64"), "ELEMENTARY_AB_ARM_64");
        assert_eq!(volume_label("", ""), "ELEMENTARY__");
        assert!(volume_label("x".repeat(40).as_str(), "arm64").len() == 32);
    }
}
