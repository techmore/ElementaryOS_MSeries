// SPDX-License-Identifier: GPL-3.0-or-later
#![forbid(unsafe_code)]

use std::io::{self, Write};
use std::process::{Command, Output, Stdio};

fn command(program: &str) -> Command {
    let mut command = Command::new(program);
    command.env("LC_ALL", "C");
    command
}

fn output(program: &str, args: &[&str], quiet_stderr: bool) -> io::Result<Output> {
    let mut command = command(program);
    command.args(args);
    if quiet_stderr {
        command.stderr(Stdio::null());
    }
    command.output()
}

fn command_status(program: &str, args: &[&str]) -> Result<(), i32> {
    match command(program).args(args).status() {
        Ok(status) if status.success() => Ok(()),
        Ok(status) => Err(status.code().unwrap_or(1)),
        Err(error) => {
            let _ = writeln!(io::stderr(), "{program}: {error}");
            Err(127)
        }
    }
}

fn captured_stdout(program: &str, args: &[&str]) -> Option<String> {
    output(program, args, true)
        .ok()
        .map(|result| String::from_utf8_lossy(&result.stdout).into_owned())
}

fn supported_platform() -> bool {
    let Some(arch) = captured_stdout("uname", &["-m"]) else {
        return false;
    };
    if arch.trim() != "aarch64" {
        return false;
    }
    output("lspci", &["-nn"], true).is_ok_and(|result| {
        result.status.success() && {
            let devices = String::from_utf8_lossy(&result.stdout);
            devices.contains("14e4:4425") || devices.contains("14e4:4433")
        }
    })
}

fn radio_enabled() -> bool {
    captured_stdout("nmcli", &["radio", "wifi"]).is_some_and(|state| state.trim() == "enabled")
}

fn rejection_count() -> String {
    let Some(log) = captured_stdout(
        "journalctl",
        &[
            "-b",
            "-u",
            "wpa_supplicant",
            "-u",
            "NetworkManager",
            "--no-pager",
        ],
    ) else {
        return "0".into();
    };
    log.lines()
        .filter(|line| {
            line.find("ASSOC-REJECT")
                .is_some_and(|index| line[index..].contains("status_code=16"))
                || line.contains("status 16")
        })
        .count()
        .to_string()
}

fn wifi_down() -> bool {
    captured_stdout("nmcli", &["-t", "-f", "TYPE,STATE", "device", "status"]).is_some_and(
        |status| {
            status
                .lines()
                .any(|line| line == "wifi:disconnected" || line.starts_with("wifi:connecting"))
        },
    )
}

fn log_reload(before: &str, after: &str) {
    let _ = command("logger")
        .args([
            "-t",
            "mseries-wifi-resume-fix",
            &format!("reloading brcmfmac after resume (rejections {before}->{after})"),
        ])
        .status();
}

fn module_holders() -> Result<Vec<String>, i32> {
    let result = output("lsmod", &[], false).map_err(|error| {
        let _ = writeln!(io::stderr(), "lsmod: {error}");
        127
    })?;
    if !result.status.success() {
        return Err(result.status.code().unwrap_or(1));
    }
    let text = String::from_utf8_lossy(&result.stdout);
    Ok(text
        .lines()
        .find_map(|line| {
            let mut fields = line.split_whitespace();
            if fields.next()? != "brcmfmac" {
                return None;
            }
            let holders = fields.nth(2).unwrap_or_default();
            Some(
                holders
                    .split(',')
                    .filter(|name| !name.is_empty())
                    .map(str::to_owned)
                    .collect(),
            )
        })
        .unwrap_or_default())
}

fn driver_loaded() -> bool {
    let Ok(result) = output("lsmod", &[], false) else {
        return false;
    };
    result.status.success()
        && String::from_utf8_lossy(&result.stdout)
            .lines()
            .any(|line| line.split_whitespace().next() == Some("brcmfmac"))
}

fn recover() -> Result<(), i32> {
    if !radio_enabled() {
        return Ok(());
    }
    let before = rejection_count();
    command_status("sleep", &["15"])?;
    if !radio_enabled() {
        return Ok(());
    }
    let after = rejection_count();
    if after == before && !wifi_down() {
        return Ok(());
    }

    log_reload(&before, &after);
    let holders = module_holders()?;
    if driver_loaded() {
        command_status("modprobe", &["-r", "--remove-holders", "brcmfmac"])?;
    }
    command_status("modprobe", &["brcmfmac"])?;
    if !holders.is_empty() {
        let args = holders;
        let borrowed = args.iter().map(String::as_str).collect::<Vec<_>>();
        command_status("modprobe", &borrowed)?;
    }
    Ok(())
}

fn main() {
    // Match the shell helper's architecture/device gates: unsupported hardware
    // exits successfully and performs no recovery actions.
    if !supported_platform() {
        return;
    }
    if let Err(code) = recover() {
        std::process::exit(code);
    }
}
