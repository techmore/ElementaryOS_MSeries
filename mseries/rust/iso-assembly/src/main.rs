use mseries_iso_label::volume_label;
use std::env;
use std::fs;
use std::io;
use std::path::Path;
use std::process::{Command, ExitCode};

const CONTAINER_IMAGE: &str = "ghcr.io/elementary/xorriso:tanit";
const CONTAINER_SCRIPT: &str = r#"set -eu
KERNEL_VERSION=$(ls "$BASE_NAME/lib/modules" | head -n 1)
test -n "$KERNEL_VERSION"
chroot "$BASE_NAME" update-initramfs -u -k "$KERNEL_VERSION"
cp "$BASE_NAME/boot/vmlinuz-$KERNEL_VERSION" iso_root/casper/vmlinuz
cp "$BASE_NAME/boot/initrd.img-$KERNEL_VERSION" iso_root/casper/initrd
rm -f iso_root/casper/filesystem.squashfs
mksquashfs "$BASE_NAME" iso_root/casper/filesystem.squashfs -comp zstd -Xcompression-level "$SQUASHFS_LEVEL"
echo 'Squashing raw image...'
mksquashfs "$RAW_IMAGE" "iso_root/extra/$RAW_BASENAME.squashfs" -comp zstd -Xcompression-level "$SQUASHFS_LEVEL"
grub-mkrescue -o "$OUT_ISO" -iso-level 3 -volid "$ISO_LABEL" -appid 'elementary OS' iso_root/
echo 'Live environment generated!'"#;

fn main() -> ExitCode {
    match assemble() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("error: {error}");
            ExitCode::FAILURE
        }
    }
}

fn assemble() -> Result<(), Box<dyn std::error::Error>> {
    let repo_root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .ok_or("could not locate repository root")?;
    let output = repo_root.join("mkosi.output");
    if !output.is_dir() {
        return Err("mkosi.output is missing; run just do-daily or do-stable first".into());
    }

    let date = read_single_line(&output.join("mkosi.version"))?;
    let profile = env::var("PROFILE").unwrap_or_else(|_| "unknown".to_owned());
    let arch = native_architecture()?;
    let squashfs_level = match env::var("SQUASHFS_LEVEL") {
        Ok(value) if !value.is_empty() => value,
        _ if profile == "proposed" => "3".to_owned(),
        _ => "15".to_owned(),
    };
    if !squashfs_level.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err("SQUASHFS_LEVEL must be a non-negative integer".into());
    }

    let deb_arch = match arch.as_str() {
        "arm64" | "aarch64" => "arm64",
        "x86-64" | "amd64" => "amd64",
        _ => return Err(format!("Unsupported installer architecture: {arch}").into()),
    };
    let base_name = format!("liveiso_{date}");
    let base = output.join(&base_name);
    let raw_name = format!("elementary_{date}.raw");
    let raw_image = output.join(&raw_name);
    let source_iso_root = base.join("iso_root");
    let base_release = output.join(format!("base_{date}/usr/lib/os-release"));
    for required in [&base, &source_iso_root, &raw_image, &base_release] {
        if !required.exists() {
            return Err(format!("required build output is missing: {}", required.display()).into());
        }
    }

    let out_iso = format!("elementaryos-9.0-{profile}-{arch}.{date}.iso");
    let label = volume_label(&profile, &arch);
    let iso_root = output.join("iso_root");
    remove_if_exists(&iso_root)?;
    run(
        Command::new("rsync")
            .arg("-a")
            .arg("--delete")
            .arg(format!("{}/", source_iso_root.display()))
            .arg(&iso_root),
        &output,
    )?;

    println!("Writing minimal APT disc structure for apt-cdrom...");
    let packages_dir = iso_root.join(format!("dists/stable/main/binary-{deb_arch}"));
    fs::create_dir_all(&packages_dir)?;
    let packages = packages_dir.join("Packages");
    touch(&packages)?;
    run(Command::new("gzip").arg("-kf").arg(&packages), &output)?;
    fs::create_dir_all(iso_root.join("pool"))?;

    println!("Detected release target: {base_name}");
    let pretty_name = read_os_release_pretty_name(&base_release)?;
    replace_in_file(
        &iso_root.join("boot/grub/grub.cfg"),
        "%PLACEHOLDER_VERSION%",
        &pretty_name,
    )?;
    replace_in_file(
        &iso_root.join(".disk/info"),
        "%PLACEHOLDER_VERSION%",
        &pretty_name,
    )?;
    replace_in_file(
        &iso_root.join(".disk/info"),
        "%PLACEHOLDER_ARCH%",
        &format!("{arch})"),
    )?;
    fs::create_dir_all(iso_root.join("extra"))?;

    println!("Creating casper liveiso (zstd level {squashfs_level})...");
    run_podman(
        &output,
        &base_name,
        &raw_name,
        &out_iso,
        &squashfs_level,
        &label,
    )?;
    remove_if_exists(&output.join("custom_ubuntu_live.iso"))?;
    println!("Success! Your live ISO is at: mkosi.output/{out_iso}");
    Ok(())
}

fn native_architecture() -> Result<String, Box<dyn std::error::Error>> {
    let output = Command::new("systemd-analyze")
        .arg("architectures")
        .output()?;
    if !output.status.success() {
        return Err(format!(
            "systemd-analyze architectures failed with {}",
            output.status
        )
        .into());
    }
    let text = String::from_utf8(output.stdout)?;
    text.lines()
        .find(|line| line.contains("native"))
        .and_then(|line| line.split_whitespace().next())
        .map(str::to_owned)
        .ok_or_else(|| "systemd-analyze did not report a native architecture".into())
}

fn run_podman(
    output: &Path,
    base_name: &str,
    raw_name: &str,
    out_iso: &str,
    squashfs_level: &str,
    label: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let mount = format!("{}:/workspace:Z", output.display());
    let envs = [
        ("BASE_NAME", base_name),
        ("RAW_IMAGE", raw_name),
        (
            "RAW_BASENAME",
            raw_name.strip_suffix(".raw").unwrap_or(raw_name),
        ),
        ("OUT_ISO", out_iso),
        ("SQUASHFS_LEVEL", squashfs_level),
        ("ISO_LABEL", label),
    ];
    let mut command = Command::new("sudo");
    command
        .arg("podman")
        .arg("run")
        .arg("--rm")
        .arg("-it")
        .arg("--network")
        .arg("host")
        .arg("--dns")
        .arg("8.8.8.8")
        .arg("-v")
        .arg(mount)
        .arg("-w")
        .arg("/workspace");
    for (name, value) in envs {
        command.arg("--env").arg(format!("{name}={value}"));
    }
    command
        .arg(CONTAINER_IMAGE)
        .arg("sh")
        .arg("-c")
        .arg(CONTAINER_SCRIPT);
    run(&mut command, output)
}

fn read_single_line(path: &Path) -> Result<String, io::Error> {
    let value = fs::read_to_string(path)?;
    let value = value.trim();
    if value.is_empty() || value.contains(['\n', '\r', '/', '\0']) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("invalid value in {}", path.display()),
        ));
    }
    Ok(value.to_owned())
}

fn read_os_release_pretty_name(path: &Path) -> Result<String, io::Error> {
    let content = fs::read_to_string(path)?;
    for line in content.lines() {
        if let Some(value) = line.strip_prefix("PRETTY_NAME=") {
            return Ok(unquote(value.trim()));
        }
    }
    Err(io::Error::new(
        io::ErrorKind::InvalidData,
        "PRETTY_NAME is missing from os-release",
    ))
}

fn unquote(value: &str) -> String {
    let Some(unquoted) = value
        .strip_prefix('"')
        .and_then(|value| value.strip_suffix('"'))
    else {
        return value.trim_matches('\'').to_owned();
    };
    let mut result = String::new();
    let mut escaped = false;
    for character in unquoted.chars() {
        if escaped {
            result.push(character);
            escaped = false;
        } else if character == '\\' {
            escaped = true;
        } else {
            result.push(character);
        }
    }
    if escaped {
        result.push('\\');
    }
    result
}

fn replace_in_file(path: &Path, needle: &str, replacement: &str) -> Result<(), io::Error> {
    let content = fs::read_to_string(path)?;
    fs::write(path, content.replace(needle, replacement))
}

fn remove_if_exists(path: &Path) -> Result<(), io::Error> {
    if !path.exists() {
        return Ok(());
    }
    if path.is_dir() {
        fs::remove_dir_all(path)
    } else {
        fs::remove_file(path)
    }
}

fn touch(path: &Path) -> Result<(), io::Error> {
    if !path.exists() {
        fs::File::create(path)?;
    }
    Ok(())
}

fn run(command: &mut Command, cwd: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let shown = command.get_program().to_string_lossy().into_owned();
    let status = command.current_dir(cwd).status()?;
    if !status.success() {
        return Err(format!("{shown} exited with {status}").into());
    }
    Ok(())
}
