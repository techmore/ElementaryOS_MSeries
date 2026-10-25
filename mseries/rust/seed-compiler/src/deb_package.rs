//! Native binary packaging for the documentation-only Elementary metapackages.

use crate::archive::{parse_control_stanzas, valid_package_name, valid_version, ControlFields};
use crate::deb_archive;
use crate::deb_relations;
use crate::metapackage::MetapackageMap;
use chrono::DateTime;
use md5::{Digest, Md5};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

const BINARY_FIELDS: &[&str] = &[
    "Package",
    "Architecture",
    "Maintainer",
    "Description",
    "Section",
    "Priority",
    "Homepage",
    "Origin",
    "Bugs",
    "Tag",
    "Multi-Arch",
    "Essential",
    "Protected",
    "Package-Type",
    "Pre-Depends",
    "Depends",
    "Recommends",
    "Suggests",
    "Enhances",
    "Conflicts",
    "Breaks",
    "Replaces",
    "Provides",
    "Built-Using",
    "Static-Built-Using",
];

#[derive(Debug, Clone, Copy, Default)]
pub struct BuildOptions {
    pub epoch: Option<u64>,
    pub full_changelog: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BuiltPackage {
    pub filename: String,
    pub bytes: Vec<u8>,
}

struct Changelog {
    source: String,
    version: String,
    entries: Vec<(String, i64)>,
}

impl Changelog {
    fn parse(input: &str) -> Result<Self, String> {
        let header = input.lines().next().ok_or("empty Debian changelog")?;
        if header.contains("binary-only=yes") {
            return Err("binary-only changelog entries are not supported yet".into());
        }
        let (source, rest) = header
            .split_once(" (")
            .ok_or("invalid Debian changelog header")?;
        let (version, _) = rest
            .split_once(") ")
            .ok_or("invalid Debian changelog version")?;
        if !valid_package_name(source) || !valid_version(version) {
            return Err("invalid changelog package/version".into());
        }
        let mut entries = Vec::new();
        let mut pending = String::new();
        for line in input.split_inclusive('\n') {
            pending.push_str(line);
            if let Some(signature) = line.trim_start().strip_prefix("-- ") {
                let (_, timestamp) = signature
                    .rsplit_once('>')
                    .ok_or("invalid changelog signature")?;
                let timestamp = timestamp.trim();
                let date = timestamp
                    .split_once(',')
                    .filter(|(weekday, _)| weekday.bytes().all(|byte| byte.is_ascii_alphabetic()))
                    .map_or(timestamp, |(_, date)| date.trim());
                let timestamp = DateTime::parse_from_str(date, "%d %b %Y %H:%M:%S %z")
                    .map_err(|error| format!("invalid changelog date: {error}"))?
                    .timestamp();
                entries.push((std::mem::take(&mut pending), timestamp));
            }
        }
        if entries.is_empty() {
            return Err("changelog has no dated entry".into());
        }
        Ok(Self {
            source: source.to_owned(),
            version: version.to_owned(),
            entries,
        })
    }

    fn document(&self, package: &str, full: bool) -> Vec<u8> {
        // Debhelper 13.31's documented cutoff/minimum-entry policy. The full
        // source remains an input; this matches only the installed changelog.
        const CUTOFF: i64 = 1_686_355_200; // 2023-06-10 00:00:00 UTC
        let mut output = String::new();
        for (index, (entry, timestamp)) in self.entries.iter().enumerate() {
            if !full && index >= 4 && *timestamp < CUTOFF {
                output.push_str(&format!("\n# Older entries have been removed from this changelog.\n# To read the complete changelog use `apt changelog {package}`.\n"));
                break;
            }
            output.push_str(entry);
        }
        output.into_bytes()
    }
}

fn canonical(fields: ControlFields) -> Result<ControlFields, String> {
    let known = BINARY_FIELDS
        .iter()
        .copied()
        .chain([
            "Source",
            "Version",
            "Installed-Size",
            "Build-Depends",
            "Build-Depends-Indep",
            "Build-Depends-Arch",
        ])
        .collect::<Vec<_>>();
    let mut seen = BTreeSet::new();
    let mut output = ControlFields::new();
    for (name, value) in fields {
        if !seen.insert(name.to_ascii_lowercase()) {
            return Err(format!("duplicate case-insensitive field `{name}`"));
        }
        let name = known
            .iter()
            .find(|known| known.eq_ignore_ascii_case(&name))
            .copied()
            .unwrap_or(&name)
            .to_owned();
        output.insert(name, value);
    }
    Ok(output)
}

fn read(path: &Path) -> Result<Vec<u8>, String> {
    fs::read(path).map_err(|error| format!("{}: {error}", path.display()))
}

fn read_text(path: &Path) -> Result<String, String> {
    fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))
}

fn source_layout(source: &Path, packages: &BTreeSet<String>) -> Result<(), String> {
    for build_file in [
        "meson.build",
        "Cargo.toml",
        "CMakeLists.txt",
        "configure",
        "Makefile",
        "setup.py",
        "pyproject.toml",
    ] {
        if source.join(build_file).exists() {
            return Err(format!(
                "metadata-only builder does not support `{build_file}`"
            ));
        }
    }
    for entry in fs::read_dir(source.join("debian")).map_err(|error| error.to_string())? {
        let entry = entry.map_err(|error| error.to_string())?;
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| "non-UTF-8 Debian packaging path")?;
        if [
            "control",
            "copyright",
            "changelog",
            "compat",
            "rules",
            "source",
        ]
        .contains(&name.as_str())
        {
            continue;
        }
        if packages.iter().any(|package| {
            name == format!("{package}.copyright") || name == format!("{package}.changelog")
        }) {
            continue;
        }
        return Err(format!(
            "metadata-only builder does not support debian/{name}"
        ));
    }
    let rules = source.join("debian/rules");
    if rules.is_file() {
        for line in read_text(&rules)?
            .lines()
            .map(str::trim)
            .filter(|line| !line.is_empty() && !line.starts_with('#'))
        {
            let words = line.split_whitespace().collect::<Vec<_>>();
            if line != "%:"
                && words != ["dh", "$@"]
                && words != ["dh", "--with", "germinate", "$@"]
                && words != ["dh", "$@", "--with", "germinate"]
                && words != ["dh", "--with=germinate", "$@"]
            {
                return Err(
                    "metadata-only builder does not support custom debian/rules hooks".into(),
                );
            }
        }
    }
    Ok(())
}

fn expand(input: &str, variables: &BTreeMap<String, String>) -> Result<String, String> {
    let mut value = input.to_owned();
    let mut seen = BTreeSet::new();
    for _ in 0..64 {
        if !seen.insert(value.clone()) {
            return Err("cyclic control substitution".into());
        }
        let mut result = String::new();
        let mut rest = value.as_str();
        let mut substituted = false;
        while let Some(index) = rest.find("${") {
            result.push_str(&rest[..index]);
            rest = &rest[index + 2..];
            let end = rest.find('}').ok_or("unclosed control substitution")?;
            let name = &rest[..end];
            if name.is_empty() {
                result.push_str("${}");
            } else {
                result.push_str(variables.get(name).ok_or_else(|| {
                    format!("unsupported/undefined control substitution `${{{name}}}`")
                })?);
                substituted = true;
            }
            rest = &rest[end + 1..];
        }
        result.push_str(rest);
        if !substituted {
            return Ok(result.replace("${}", "$"));
        }
        value = result;
    }
    Err("control substitution depth exceeded".into())
}

fn render(fields: &ControlFields) -> String {
    let mut output = String::new();
    for (name, value) in fields {
        let mut lines = value.split('\n');
        output.push_str(&format!("{name}: {}\n", lines.next().unwrap_or_default()));
        for line in lines {
            output.push_str(&format!(" {line}\n"));
        }
    }
    output
}

fn control(
    source: &ControlFields,
    template: &ControlFields,
    version: &str,
    host: &str,
    architecture: &str,
    size: u64,
    substitutions: &str,
) -> Result<String, String> {
    let package = &template["Package"];
    let mut fields = template.clone();
    fields.remove("Architecture");
    for key in ["Section", "Priority", "Maintainer", "Homepage"] {
        if let Some(value) = source.get(key) {
            fields.entry(key.into()).or_insert_with(|| value.clone());
        }
    }
    let source_name = &source["Source"];
    if source_name != package {
        fields.insert("Source".into(), source_name.clone());
    }
    fields.insert("Version".into(), version.to_owned());
    fields.insert("Architecture".into(), architecture.to_owned());
    fields.insert("Installed-Size".into(), size.to_string());
    let mut variables = BTreeMap::from([
        ("Arch".into(), host.to_owned()),
        ("source:Version".into(), version.to_owned()),
        (
            "source:Upstream-Version".into(),
            version
                .rsplit_once('-')
                .map_or(version, |(upstream, _)| upstream)
                .to_owned(),
        ),
        ("binary:Version".into(), version.to_owned()),
        ("Installed-Size".into(), size.to_string()),
        ("misc:Depends".into(), String::new()),
        ("misc:Pre-Depends".into(), String::new()),
        ("germinate:Depends".into(), String::new()),
        ("germinate:Recommends".into(), String::new()),
        ("Newline".into(), "\n".into()),
        ("Space".into(), " ".into()),
        ("Tab".into(), "\t".into()),
    ]);
    for (name, value) in source {
        variables.insert(format!("S:{name}"), value.clone());
    }
    if let Some(description) = source.get("Description") {
        let (summary, extended) = description.split_once('\n').unwrap_or((description, ""));
        variables.insert("source:Synopsis".into(), summary.to_owned());
        variables.insert("source:Extended-Description".into(), extended.to_owned());
    }
    for (name, value) in &fields {
        variables.insert(format!("F:{name}"), value.clone());
    }
    for line in substitutions.lines() {
        let (name, value) = line.split_once('=').ok_or("invalid generated substvars")?;
        variables.insert(name.to_owned(), value.to_owned());
    }
    for value in fields.values_mut() {
        *value = expand(value, &variables)?;
    }
    deb_relations::normalize(&mut fields, package, version, host)?;
    for name in ["Maintainer", "Description"] {
        if fields.get(name).is_none_or(|value| value.trim().is_empty()) {
            return Err(format!("{package} has no {name}"));
        }
    }
    fields.retain(|_, value| !value.trim().is_empty());
    Ok(render(&fields))
}

/// Build every eligible metadata-only metapackage into memory. This does not
/// invoke dpkg, Debhelper, ar, tar, gzip, or the source's rules file.
pub fn build(
    source_dir: &Path,
    lists: &Path,
    host: &str,
    options: BuildOptions,
) -> Result<Vec<BuiltPackage>, String> {
    if !["amd64", "arm64"].contains(&host) {
        return Err("metapackage host architecture must be amd64 or arm64".into());
    }
    let stanzas = parse_control_stanzas(&read_text(&source_dir.join("debian/control"))?)
        .map_err(|error| error.to_string())?
        .into_iter()
        .map(|stanza| canonical(stanza.fields))
        .collect::<Result<Vec<_>, _>>()?;
    let source = stanzas.first().ok_or("source control file is empty")?;
    let source_name = source
        .get("Source")
        .filter(|name| valid_package_name(name) && name.ends_with("-meta"))
        .ok_or("source name must be a valid -meta package")?;
    if source.keys().any(|name| {
        name.to_ascii_uppercase().starts_with("XB") || name.to_ascii_uppercase().starts_with("X-B")
    }) {
        return Err("source-level binary extension fields are not supported yet".into());
    }
    let changelog = Changelog::parse(&read_text(&source_dir.join("debian/changelog"))?)?;
    if &changelog.source != source_name {
        return Err("changelog source differs from debian/control".into());
    }
    let epoch = options.epoch.map(Ok).unwrap_or_else(|| {
        u64::try_from(changelog.entries[0].1)
            .map_err(|_| "negative source timestamp is not supported")
    })?;
    if epoch > 0o77_777_777_777 {
        return Err("source timestamp exceeds ustar format".into());
    }
    let map = MetapackageMap::parse(&read_text(&lists.join("metapackage-map"))?)
        .map_err(|error| error.to_string())?;
    let mut packages = BTreeSet::new();
    for template in &stanzas[1..] {
        for key in template.keys() {
            if !BINARY_FIELDS.contains(&key.as_str()) {
                return Err(format!("unsupported binary template field `{key}`"));
            }
        }
        let name = template
            .get("Package")
            .filter(|name| name.len() >= 2 && valid_package_name(name))
            .ok_or("invalid binary package name")?;
        if !packages.insert(name.clone()) {
            return Err(format!("duplicate binary package `{name}`"));
        }
    }
    source_layout(source_dir, &packages)?;
    let mut result = Vec::new();
    for template in &stanzas[1..] {
        let package = &template["Package"];
        if template
            .get("Package-Type")
            .is_some_and(|kind| kind != "deb")
        {
            return Err("only deb metapackages are supported".into());
        }
        let declared = template
            .get("Architecture")
            .ok_or("binary package has no Architecture")?;
        let patterns = declared.split_whitespace().collect::<Vec<_>>();
        if patterns.is_empty()
            || patterns.iter().any(|pattern| !valid_package_name(pattern))
            || (patterns.contains(&"all") && patterns.len() != 1)
        {
            return Err("invalid package Architecture field".into());
        }
        let architecture = if patterns == ["all"] {
            "all"
        } else if patterns
            .iter()
            .any(|pattern| deb_relations::architecture_matches(pattern, host))
        {
            host
        } else {
            continue;
        };
        let mut data = BTreeMap::new();
        let copyright_path = source_dir.join(format!("debian/{package}.copyright"));
        let copyright = read(&if copyright_path.is_file() {
            copyright_path
        } else {
            source_dir.join("debian/copyright")
        })?;
        if copyright.is_empty() {
            return Err(format!("{package} copyright is empty"));
        }
        data.insert(format!("usr/share/doc/{package}/copyright"), copyright);
        let package_changelog = source_dir.join(format!("debian/{package}.changelog"));
        let package_changelog = if package_changelog.is_file() {
            Changelog::parse(&read_text(&package_changelog)?)?
        } else {
            Changelog {
                source: changelog.source.clone(),
                version: changelog.version.clone(),
                entries: changelog.entries.clone(),
            }
        };
        let log_name = if changelog.version.contains('-') {
            "changelog.Debian.gz"
        } else {
            "changelog.gz"
        };
        data.insert(
            format!("usr/share/doc/{package}/{log_name}"),
            deb_archive::gzip(&package_changelog.document(package, options.full_changelog))?,
        );
        let substitutions = map.render_for(lists, architecture, package)?;
        let metadata = control(
            source,
            template,
            &changelog.version,
            host,
            architecture,
            deb_archive::installed_size(&data),
            &substitutions,
        )?;
        let checksums = data
            .iter()
            .map(|(name, data)| format!("{:x}  {name}\n", Md5::digest(data)))
            .collect::<String>();
        let control = BTreeMap::from([
            ("control".into(), metadata.into_bytes()),
            ("md5sums".into(), checksums.into_bytes()),
        ]);
        let filename_version = changelog
            .version
            .split_once(':')
            .map_or(changelog.version.as_str(), |(_, rest)| rest);
        result.push(BuiltPackage {
            filename: format!("{package}_{filename_version}_{architecture}.deb"),
            bytes: deb_archive::deb(&control, &data, epoch)?,
        });
    }
    if result.is_empty() {
        return Err(format!("no binary package is eligible for {host}"));
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn changelog_trim_and_full_output_preserve_entry_boundaries() {
        let input = (0..6).map(|index| format!("fixture-meta (1.{index}) unstable; urgency=low\n\n  * Entry {index}.\n\n -- Fixture <fixture@example.invalid>  Sat, 01 Jan 2022 00:00:00 +0000\n\n")).collect::<String>();
        let changelog = Changelog::parse(&input).unwrap();
        let trimmed = String::from_utf8(changelog.document("fixture", false)).unwrap();
        assert!(trimmed.contains("Entry 3"));
        assert!(!trimmed.contains("Entry 4"));
        assert!(trimmed.ends_with("`apt changelog fixture`.\n"));
        assert!(String::from_utf8(changelog.document("fixture", true))
            .unwrap()
            .contains("Entry 5"));
    }

    #[test]
    fn substitutions_resolve_nested_values_and_preserve_literal_dollar_escapes() {
        let variables = BTreeMap::from([
            ("first".into(), "${second}".into()),
            ("second".into(), "value".into()),
        ]);
        assert_eq!(
            expand("${first}: ${}{literal}", &variables).unwrap(),
            "value: ${literal}"
        );
        assert!(expand("${unknown}", &variables).is_err());
        assert!(expand(
            "${first}",
            &BTreeMap::from([("first".into(), "${first}".into())])
        )
        .is_err());
    }
}
