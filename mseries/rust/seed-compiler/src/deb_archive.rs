//! Deterministic Debian 2.0 ar/ustar containers; no host archive tools are used.

use flate2::{Compression, GzBuilder};
use std::collections::{BTreeMap, BTreeSet};
use std::io::Write;

pub(crate) fn gzip(input: &[u8]) -> Result<Vec<u8>, String> {
    let mut encoder = GzBuilder::new()
        .mtime(0)
        .operating_system(3)
        .write(Vec::new(), Compression::best());
    encoder
        .write_all(input)
        .map_err(|error| error.to_string())?;
    encoder.finish().map_err(|error| error.to_string())
}

pub(crate) fn directories(files: &BTreeMap<String, Vec<u8>>) -> BTreeSet<String> {
    let mut result = BTreeSet::new();
    for name in files.keys() {
        let mut current = name.as_str();
        while let Some((parent, _)) = current.rsplit_once('/') {
            result.insert(parent.to_owned());
            current = parent;
        }
    }
    result
}

pub(crate) fn installed_size(files: &BTreeMap<String, Vec<u8>>) -> u64 {
    // dpkg-gencontrol scans the staging root and the empty DEBIAN directory;
    // dh_md5sums and the generated control file come after that size scan.
    2 + directories(files).len() as u64
        + files
            .values()
            .map(|data| (data.len() as u64).div_ceil(1024))
            .sum::<u64>()
}

fn text(field: &mut [u8], value: &[u8]) -> Result<(), String> {
    if value.len() > field.len() {
        return Err("ustar field exceeds its format limit".into());
    }
    field[..value.len()].copy_from_slice(value);
    Ok(())
}

fn octal(field: &mut [u8], value: u64) -> Result<(), String> {
    let width = field.len() - 1;
    let value = format!("{value:0width$o}");
    if value.len() != width {
        return Err("ustar numeric field exceeds its format limit".into());
    }
    field[..width].copy_from_slice(value.as_bytes());
    Ok(())
}

fn tar_entry(
    archive: &mut Vec<u8>,
    name: &str,
    data: &[u8],
    directory: bool,
    epoch: u64,
) -> Result<(), String> {
    let name = if directory {
        name.trim_end_matches('/')
    } else {
        name
    };
    if name.starts_with('/') || name.split('/').any(|part| part == "..") {
        return Err("invalid package archive path".into());
    }
    let mut header = [0_u8; 512];
    if name.len() <= 100 {
        text(&mut header[..100], name.as_bytes())?;
    } else {
        let (prefix, base) = name.rsplit_once('/').ok_or("ustar path is too long")?;
        text(&mut header[..100], base.as_bytes())?;
        text(&mut header[345..500], prefix.as_bytes())?;
    }
    octal(&mut header[100..108], if directory { 0o755 } else { 0o644 })?;
    octal(&mut header[108..116], 0)?;
    octal(&mut header[116..124], 0)?;
    octal(&mut header[124..136], data.len() as u64)?;
    octal(&mut header[136..148], epoch)?;
    header[148..156].fill(b' ');
    header[156] = if directory { b'5' } else { b'0' };
    text(&mut header[257..263], b"ustar\0")?;
    text(&mut header[263..265], b"00")?;
    text(&mut header[265..297], b"root")?;
    text(&mut header[297..329], b"root")?;
    let checksum: u64 = header.iter().map(|byte| u64::from(*byte)).sum();
    text(
        &mut header[148..156],
        format!("{checksum:06o}\0 ").as_bytes(),
    )?;
    archive.extend_from_slice(&header);
    archive.extend_from_slice(data);
    archive.resize(archive.len().div_ceil(512) * 512, 0);
    Ok(())
}

fn tar(files: &BTreeMap<String, Vec<u8>>, epoch: u64) -> Result<Vec<u8>, String> {
    let mut result = Vec::new();
    tar_entry(&mut result, "./", &[], true, epoch)?;
    for directory in directories(files) {
        tar_entry(&mut result, &format!("./{directory}/"), &[], true, epoch)?;
    }
    for (name, bytes) in files {
        tar_entry(&mut result, &format!("./{name}"), bytes, false, epoch)?;
    }
    result.resize(result.len() + 1024, 0);
    Ok(result)
}

pub(crate) fn deb(
    control: &BTreeMap<String, Vec<u8>>,
    data: &BTreeMap<String, Vec<u8>>,
    epoch: u64,
) -> Result<Vec<u8>, String> {
    let members = [
        ("debian-binary", b"2.0\n".to_vec()),
        ("control.tar.gz", gzip(&tar(control, epoch)?)?),
        ("data.tar.gz", gzip(&tar(data, epoch)?)?),
    ];
    let mut result = b"!<arch>\n".to_vec();
    for (name, bytes) in members {
        if bytes.len() > 9_999_999_999 {
            return Err("ar member exceeds its format limit".into());
        }
        let header = format!(
            "{name:<16}{epoch:<12}{:<6}{:<6}{:<8}{:<10}`\n",
            0,
            0,
            "100644",
            bytes.len()
        );
        if header.len() != 60 {
            return Err("ar metadata exceeds its format limit".into());
        }
        result.extend_from_slice(header.as_bytes());
        result.extend_from_slice(&bytes);
        if bytes.len() % 2 != 0 {
            result.push(b'\n');
        }
    }
    Ok(result)
}
