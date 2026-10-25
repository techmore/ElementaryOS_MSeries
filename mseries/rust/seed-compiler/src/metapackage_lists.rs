//! Deterministic metapackage map/list generation from explicitly supplied inputs.
//! This is the seed-planting stage; dependency closure is a separate operation.

use crate::archive::{parse_control_stanzas, PackageCatalog};
use crate::metapackage::{safe_component, MetapackageMap};
use crate::{EntryKind, SeedDocument, Structure};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdatePlan {
    pub distribution: String,
    pub seeds: Vec<String>,
    pub output_seeds: Vec<String>,
    pub architectures: Vec<String>,
    pub package_prefix: String,
    pub seed_maps: BTreeMap<String, Vec<String>>,
    pub metapackage_maps: BTreeMap<String, String>,
}

impl UpdatePlan {
    pub fn parse(control: &str, config: &str, distribution: Option<&str>) -> Result<Self, String> {
        let stanzas = parse_control_stanzas(control).map_err(|error| error.to_string())?;
        let source = stanzas
            .first()
            .and_then(|stanza| stanza.fields.get("Source"))
            .ok_or("debian/control has no source stanza")?;
        let prefix = source
            .strip_suffix("-meta")
            .filter(|prefix| !prefix.is_empty())
            .ok_or("source package name must end in -meta")?;
        if !safe_component(prefix) {
            return Err("invalid source package name".into());
        }
        let config = IniConfig::parse(config)?;
        let distribution = distribution
            .map(str::to_owned)
            .map(Ok)
            .unwrap_or_else(|| config.required("DEFAULT", "dist"))?;
        if !config.sections.contains_key(&distribution) {
            return Err(format!("update.cfg has no section [{distribution}]"));
        }
        let seeds = names(&config.required(&distribution, "seeds")?, "seeds")?;
        let output_seeds = config
            .value(&distribution, "output_seeds")?
            .map(|value| names(&value, "output_seeds"))
            .transpose()?
            .unwrap_or_else(|| seeds.clone());
        let architectures = names(
            &config.required(&distribution, "architectures")?,
            "architectures",
        )?;
        let mut seed_maps = BTreeMap::new();
        let mut metapackage_maps = BTreeMap::new();
        let keys = config.sections["DEFAULT"]
            .keys()
            .chain(config.sections[&distribution].keys())
            .cloned()
            .collect::<BTreeSet<_>>();
        for key in keys {
            if let Some(seed) = key.strip_prefix("seed_map/") {
                if !safe_component(seed) {
                    return Err(format!("invalid seed map key `{seed}`"));
                }
                seed_maps.insert(
                    seed.to_owned(),
                    names(&config.required(&distribution, &key)?, &key)?,
                );
            } else if let Some(seed) = key.strip_prefix("metapackage_map/") {
                let package = config.required(&distribution, &key)?;
                if !safe_component(seed) || !safe_component(&package) {
                    return Err(format!("invalid metapackage map `{key}`"));
                }
                metapackage_maps.insert(seed.to_owned(), package);
            }
        }
        Ok(Self {
            distribution,
            seeds,
            output_seeds,
            architectures,
            package_prefix: prefix.to_owned(),
            seed_maps,
            metapackage_maps,
        })
    }

    /// Produce all configured architectures as a complete in-memory file set.
    /// No outputs are written until every supplied input has been validated.
    pub fn render_files(
        &self,
        structure: &Structure,
        documents: &BTreeMap<String, SeedDocument>,
        catalogs: &BTreeMap<String, PackageCatalog>,
        debootstrap: &BTreeMap<String, BTreeSet<String>>,
    ) -> Result<BTreeMap<String, String>, String> {
        let mut order = Vec::new();
        for seed in &self.seeds {
            for inherited in structure.inheritance_order(seed)? {
                if !order.contains(&inherited) {
                    order.push(inherited);
                }
            }
        }
        let mut map = String::new();
        let mut mappings = BTreeMap::new();
        for seed in &self.output_seeds {
            if !order.contains(seed) {
                return Err(format!("output seed `{seed}` is not selected"));
            }
            let document = documents
                .get(seed)
                .ok_or_else(|| format!("seed file `{seed}` was not supplied"))?;
            let package = self
                .metapackage_maps
                .get(seed)
                .cloned()
                .or_else(|| header(document, "Task-Metapackage").map(str::to_owned))
                .unwrap_or_else(|| format!("{}-{seed}", self.package_prefix));
            if !safe_component(&package) {
                return Err(format!("invalid metapackage name `{package}`"));
            }
            map.push_str(&format!("{seed} {package}\n"));
            let mapped = if let Some(mapped) = self.seed_maps.get(seed) {
                mapped.clone()
            } else {
                let mut mapped = header(document, "Task-Seeds")
                    .filter(|value| !value.trim().is_empty())
                    .map(|value| names(value, "Task-Seeds"))
                    .transpose()?
                    .unwrap_or_default();
                if !mapped.contains(seed) {
                    mapped.push(seed.clone());
                }
                mapped
            };
            for name in &mapped {
                if !order.contains(name) {
                    return Err(format!("mapped seed `{name}` is not selected"));
                }
            }
            mappings.insert(seed.clone(), (package, mapped));
        }
        MetapackageMap::parse(&map).map_err(|error| error.to_string())?;
        let mut files = BTreeMap::from([("metapackage-map".into(), map)]);
        for architecture in &self.architectures {
            let catalog = catalogs
                .get(architecture)
                .ok_or_else(|| format!("Packages metadata was not supplied for {architecture}"))?;
            if !catalog.has_source_index() {
                return Err(format!(
                    "Sources metadata was not supplied for {architecture}"
                ));
            }
            let bootstrap = debootstrap.get(architecture).ok_or_else(|| {
                format!("debootstrap package set was not supplied for {architecture}")
            })?;
            let planted = plant_entries(&order, structure, documents, catalog, architecture)?;
            for seed in &self.output_seeds {
                let (package, mapped) = &mappings[seed];
                let mut depends = BTreeSet::new();
                let mut recommends = BTreeSet::new();
                let mut alternatives = BTreeMap::new();
                for name in mapped {
                    let entries = &planted[name];
                    depends.extend(entries.depends.iter().cloned());
                    recommends.extend(entries.recommends.iter().cloned());
                    for (name, values) in &entries.alternatives {
                        if alternatives.insert(name.clone(), values.clone()).is_some() {
                            return Err(format!(
                                "cannot merge alternatives for `{name}` from multiple mapped seeds"
                            ));
                        }
                    }
                }
                let render = |packages: BTreeSet<String>, required: bool| {
                    let mut lines = BTreeSet::new();
                    for name in packages {
                        if &name == package
                            || (seed == "minimal" && !bootstrap.contains(&name))
                            || (required && catalog.is_essential(&name, architecture))
                        {
                            continue;
                        }
                        let mut relationship = name.clone();
                        if let Some(values) = alternatives.get(&name) {
                            relationship.push_str(" | ");
                            relationship.push_str(&values.join(" | "));
                        }
                        lines.insert(relationship);
                    }
                    lines
                        .into_iter()
                        .map(|line| format!("{line}\n"))
                        .collect::<String>()
                };
                files.insert(format!("{seed}-{architecture}"), render(depends, true));
                files.insert(
                    format!("{seed}-recommends-{architecture}"),
                    render(recommends, false),
                );
            }
        }
        Ok(files)
    }
}

#[derive(Default)]
struct PlantedEntries {
    depends: BTreeSet<String>,
    recommends: BTreeSet<String>,
    alternatives: BTreeMap<String, Vec<String>>,
}

fn plant_entries(
    order: &[String],
    structure: &Structure,
    documents: &BTreeMap<String, SeedDocument>,
    catalog: &PackageCatalog,
    architecture: &str,
) -> Result<BTreeMap<String, PlantedEntries>, String> {
    let mut planted: BTreeMap<String, PlantedEntries> = BTreeMap::new();
    for seed in order {
        let document = documents
            .get(seed)
            .ok_or_else(|| format!("seed file `{seed}` was not supplied"))?;
        let mut inherited = BTreeSet::new();
        for ancestor in structure
            .inheritance_order(seed)?
            .iter()
            .filter(|name| *name != seed)
        {
            let entries = planted
                .get(ancestor)
                .ok_or_else(|| format!("seed `{ancestor}` was not planted"))?;
            inherited.extend(entries.depends.iter().chain(&entries.recommends).cloned());
        }
        let entries = document
            .entries
            .iter()
            .filter(|entry| entry.architectures.applies_to(architecture))
            .collect::<Vec<_>>();
        let mut recommendations = BTreeSet::new();
        for entry in &entries {
            if entry.kind == EntryKind::Package && entry.recommended {
                recommendations.extend(catalog.seed_entry_binaries(entry, architecture));
            }
        }
        let mut result = PlantedEntries::default();
        for entry in entries {
            let binaries = match entry.kind {
                EntryKind::Package => catalog.seed_entry_binaries(entry, architecture),
                EntryKind::SourcePackage => catalog.source_binaries(&entry.name, architecture),
                _ => continue,
            };
            let known_alternatives = entry
                .alternatives
                .iter()
                .filter(|name| !catalog.seed_binaries(name, architecture).is_empty())
                .cloned()
                .collect::<Vec<_>>();
            if !known_alternatives.is_empty() {
                result
                    .alternatives
                    .entry(entry.name.clone())
                    .or_default()
                    .extend(known_alternatives);
            }
            for binary in binaries {
                if inherited.contains(&binary) {
                    continue;
                }
                if recommendations.contains(&binary) {
                    result.recommends.insert(binary);
                } else {
                    result.depends.insert(binary);
                }
            }
        }
        result
            .alternatives
            .retain(|name, _| result.depends.contains(name) || result.recommends.contains(name));
        planted.insert(seed.clone(), result);
    }
    Ok(planted)
}

fn header<'a>(document: &'a SeedDocument, key: &str) -> Option<&'a str> {
    document
        .headers
        .iter()
        .find(|(name, _)| name.eq_ignore_ascii_case(key))
        .map(|(_, value)| value.as_str())
}

fn names(value: &str, field: &str) -> Result<Vec<String>, String> {
    let result = value
        .split_whitespace()
        .map(str::to_owned)
        .collect::<Vec<_>>();
    if result.is_empty()
        || result.iter().any(|name| !safe_component(name))
        || result.iter().collect::<BTreeSet<_>>().len() != result.len()
    {
        return Err(format!(
            "{field} requires a nonempty list of unique simple names"
        ));
    }
    Ok(result)
}

pub fn parse_bootstrap_packages(input: &str) -> Result<BTreeSet<String>, String> {
    let packages = input
        .split_whitespace()
        .map(str::to_owned)
        .collect::<BTreeSet<_>>();
    if packages.iter().any(|name| !safe_component(name)) {
        return Err("debootstrap input must contain only package names".into());
    }
    Ok(packages)
}

#[derive(Default)]
struct IniConfig {
    sections: BTreeMap<String, BTreeMap<String, String>>,
}

impl IniConfig {
    fn parse(input: &str) -> Result<Self, String> {
        let mut result = Self {
            sections: BTreeMap::from([("DEFAULT".into(), BTreeMap::new())]),
        };
        let mut section = None;
        let mut previous: Option<(String, usize)> = None;
        let mut seen_sections = BTreeSet::new();
        for (index, raw) in input.lines().enumerate() {
            let line = raw.trim();
            if line.is_empty() || line.starts_with(['#', ';']) {
                continue;
            }
            if line.starts_with('[') && line.ends_with(']') {
                let name = line[1..line.len() - 1].to_owned();
                if name.is_empty() || !seen_sections.insert(name.clone()) {
                    return Err(format!(
                        "update.cfg line {}: invalid or repeated section",
                        index + 1
                    ));
                }
                result.sections.entry(name.clone()).or_default();
                section = Some(name);
                previous = None;
                continue;
            }
            let section = section
                .as_ref()
                .ok_or_else(|| format!("update.cfg line {}: missing section", index + 1))?;
            let indent = raw.len() - raw.trim_start().len();
            let fields = result
                .sections
                .get_mut(section)
                .expect("declared section exists");
            if let Some((key, previous_indent)) = &previous {
                if indent > *previous_indent {
                    fields
                        .get_mut(key)
                        .expect("previous key exists")
                        .push_str(&format!("\n{line}"));
                    continue;
                }
            }
            let delimiter = line
                .find([':', '='])
                .ok_or_else(|| format!("update.cfg line {}: expected option", index + 1))?;
            let key = line[..delimiter].trim().to_ascii_lowercase();
            if key.is_empty()
                || fields
                    .insert(key.clone(), line[delimiter + 1..].trim().to_owned())
                    .is_some()
            {
                return Err(format!(
                    "update.cfg line {}: empty or repeated option",
                    index + 1
                ));
            }
            previous = Some((key, indent));
        }
        Ok(result)
    }

    fn required(&self, section: &str, key: &str) -> Result<String, String> {
        self.value(section, key)?
            .ok_or_else(|| format!("update.cfg missing {key} in [{section}]"))
    }

    fn value(&self, section: &str, key: &str) -> Result<Option<String>, String> {
        self.expand(section, key, 0)
    }

    fn expand(&self, section: &str, key: &str, depth: usize) -> Result<Option<String>, String> {
        if depth > 10 {
            return Err(format!("update.cfg interpolation cycle/depth at {key}"));
        }
        let value = self
            .sections
            .get(section)
            .and_then(|fields| fields.get(key))
            .or_else(|| self.sections["DEFAULT"].get(key));
        let Some(mut rest) = value.map(String::as_str) else {
            return Ok(None);
        };
        let mut result = String::new();
        while let Some(index) = rest.find('%') {
            result.push_str(&rest[..index]);
            rest = &rest[index + 1..];
            if let Some(after) = rest.strip_prefix('%') {
                result.push('%');
                rest = after;
            } else if let Some(variable) = rest.strip_prefix('(') {
                let end = variable
                    .find(")s")
                    .ok_or("invalid update.cfg interpolation")?;
                let key = variable[..end].to_ascii_lowercase();
                result.push_str(
                    &self
                        .expand(section, &key, depth + 1)?
                        .ok_or_else(|| format!("unknown update.cfg interpolation `{key}`"))?,
                );
                rest = &variable[end + 2..];
            } else {
                return Err("invalid percent in update.cfg interpolation".into());
            }
        }
        result.push_str(rest);
        Ok(Some(result))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn config_resolves_defaults_interpolation_continuations_and_explicit_maps() {
        let config = "[DEFAULT]\ndist: sample\nprefix: alternate\n[sample]\nseeds: minimal\n desktop\narchitectures: amd64 arm64\nmetapackage_map/desktop: %(prefix)s-desktop\nseed_map/desktop: minimal\n";
        let plan = UpdatePlan::parse("Source: fixture-meta\n", config, None).unwrap();
        assert_eq!(plan.seeds, ["minimal", "desktop"]);
        assert_eq!(plan.metapackage_maps["desktop"], "alternate-desktop");
        assert_eq!(plan.seed_maps["desktop"], ["minimal"]);
        assert!(UpdatePlan::parse("Source: fixture\n", config, None).is_err());
        assert!(UpdatePlan::parse(
            "Source: fixture-meta\n",
            &config.replace("alternate", "%(prefix)s"),
            None
        )
        .is_err());
    }
}
