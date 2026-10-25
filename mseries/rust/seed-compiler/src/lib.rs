use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

pub mod archive;
pub mod metapackage;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParseError {
    pub line: usize,
    pub message: String,
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: {}", self.line, self.message)
    }
}

impl std::error::Error for ParseError {}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Structure {
    pub features: BTreeSet<String>,
    pub includes: Vec<String>,
    pub seeds: BTreeMap<String, Vec<String>>,
}

impl Structure {
    pub fn parse(input: &str) -> Result<Self, ParseError> {
        let mut result = Self::default();
        for (index, raw) in input.lines().enumerate() {
            let line_number = index + 1;
            let line = raw.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            if let Some(rest) = line.strip_prefix("feature ") {
                let feature = rest.trim();
                if feature.is_empty() || feature.split_whitespace().count() != 1 {
                    return Err(ParseError {
                        line: line_number,
                        message: "expected one feature name after `feature`".into(),
                    });
                }
                result.features.insert(feature.to_owned());
                continue;
            }
            if let Some(rest) = line.strip_prefix("include ") {
                let collection = rest.trim();
                if collection.is_empty() || collection.split_whitespace().count() != 1 {
                    return Err(ParseError {
                        line: line_number,
                        message: "expected one collection name after `include`".into(),
                    });
                }
                result.includes.push(collection.to_owned());
                continue;
            }
            let Some((name, parents)) = line.split_once(':') else {
                return Err(ParseError {
                    line: line_number,
                    message: "expected `feature NAME`, `include COLLECTION`, or `SEED: PARENT ...`"
                        .into(),
                });
            };
            let name = name.trim();
            if name.is_empty() || name.chars().any(char::is_whitespace) {
                return Err(ParseError {
                    line: line_number,
                    message: "invalid seed name".into(),
                });
            }
            if result.seeds.contains_key(name) {
                return Err(ParseError {
                    line: line_number,
                    message: format!("duplicate seed declaration `{name}`"),
                });
            }
            result.seeds.insert(
                name.to_owned(),
                parents.split_whitespace().map(str::to_owned).collect(),
            );
        }
        Ok(result)
    }

    /// Return seed names in parent-before-child order, rejecting missing parents and cycles.
    pub fn inheritance_order(&self, seed: &str) -> Result<Vec<String>, String> {
        if !self.seeds.contains_key(seed) {
            return Err(format!("unknown seed `{seed}`"));
        }
        let mut order = Vec::new();
        let mut visiting = BTreeSet::new();
        let mut visited = BTreeSet::new();
        self.visit(seed, &mut visiting, &mut visited, &mut order)?;
        Ok(order)
    }

    /// Compose explicitly supplied included collections before the local structure.
    /// Unknown includes and conflicting declarations fail instead of silently choosing
    /// one source's profile graph.
    pub fn with_includes(
        collection: &str,
        local: &Structure,
        available: &BTreeMap<String, Structure>,
    ) -> Result<Self, String> {
        fn visit(
            name: &str,
            structure: &Structure,
            available: &BTreeMap<String, Structure>,
            visiting: &mut BTreeSet<String>,
            merged: &mut Structure,
        ) -> Result<(), String> {
            if !visiting.insert(name.to_owned()) {
                return Err(format!("collection include cycle includes `{name}`"));
            }
            for include in &structure.includes {
                let included = available
                    .get(include)
                    .ok_or_else(|| format!("included collection `{include}` was not supplied"))?;
                visit(include, included, available, visiting, merged)?;
            }
            for (seed, parents) in &structure.seeds {
                if let Some(existing) = merged.seeds.get(seed) {
                    if existing != parents {
                        return Err(format!(
                            "collection `{name}` conflicts on seed `{seed}` inheritance"
                        ));
                    }
                } else {
                    merged.seeds.insert(seed.clone(), parents.clone());
                }
            }
            merged.features.extend(structure.features.iter().cloned());
            visiting.remove(name);
            Ok(())
        }

        let mut merged = Structure::default();
        visit(
            collection,
            local,
            available,
            &mut BTreeSet::new(),
            &mut merged,
        )?;
        Ok(merged)
    }

    /// Expand inherited seed entries for one architecture. Archive dependencies and
    /// source-package expansion are deliberately outside this seed-only operation.
    pub fn resolve_seed_entries(
        &self,
        seed: &str,
        architecture: &str,
        documents: &BTreeMap<String, SeedDocument>,
    ) -> Result<Vec<SeedEntry>, String> {
        Ok(self.resolve_seed(seed, architecture, documents)?.entries)
    }

    /// Flatten a profile for seed-entry inspection. Archive callers should use
    /// resolve_seed_groups so each contributing seed keeps its own exclusions.
    pub fn resolve_seed(
        &self,
        seed: &str,
        architecture: &str,
        documents: &BTreeMap<String, SeedDocument>,
    ) -> Result<ResolvedSeed, String> {
        let groups = self.resolve_seed_groups(seed, architecture, documents)?;
        let mut entries = BTreeMap::<(EntryKind, String), SeedEntry>::new();
        let mut packages = groups[0].1.blacklisted_packages.clone();
        let mut sources = groups[0].1.blacklisted_sources.clone();
        for (_, group) in groups {
            packages.retain(|name| group.blacklisted_packages.contains(name));
            sources.retain(|name| group.blacklisted_sources.contains(name));
            for entry in group.entries {
                let key = (entry.kind, entry.name.clone());
                if !entries.contains_key(&key)
                    || entries
                        .get(&key)
                        .is_some_and(|old| old.recommended && !entry.recommended)
                {
                    entries.insert(key, entry);
                }
            }
        }
        Ok(ResolvedSeed {
            entries: entries.into_values().collect(),
            blacklisted_packages: packages,
            blacklisted_sources: sources,
        })
    }

    /// Retain the origin of each seed's roots. A per-seed blocklist applies to
    /// that seed and its inherited inner seeds, not to its outer descendants.
    /// The scope is the selected profile and its ancestors.
    pub fn resolve_seed_groups(
        &self,
        seed: &str,
        architecture: &str,
        documents: &BTreeMap<String, SeedDocument>,
    ) -> Result<Vec<(String, ResolvedSeed)>, String> {
        let order = self.inheritance_order(seed)?;
        let ancestors = order
            .iter()
            .map(|name| Ok((name.clone(), self.inheritance_order(name)?)))
            .collect::<Result<BTreeMap<_, _>, String>>()?;
        let mut result = Vec::new();
        for name in &order {
            let mut packages = BTreeSet::new();
            let mut sources = BTreeSet::new();
            for outer in &order {
                if !ancestors[outer].contains(name) {
                    continue;
                }
                let document = documents
                    .get(outer)
                    .ok_or_else(|| format!("seed file `{outer}` was not supplied"))?;
                for entry in document
                    .entries
                    .iter()
                    .filter(|entry| entry.architectures.applies_to(architecture))
                {
                    match entry.kind {
                        EntryKind::BlacklistPackage => {
                            packages.insert(entry.name.clone());
                        }
                        EntryKind::BlacklistSourcePackage => {
                            sources.insert(entry.name.clone());
                        }
                        _ => {}
                    }
                }
            }
            let document = documents
                .get(name)
                .ok_or_else(|| format!("seed file `{name}` was not supplied"))?;
            let entries = document
                .entries
                .iter()
                .filter(|entry| {
                    entry.architectures.applies_to(architecture)
                        && match entry.kind {
                            EntryKind::Package => !packages.contains(&entry.name),
                            EntryKind::SourcePackage => !sources.contains(&entry.name),
                            EntryKind::Snap => !entry.recommended,
                            EntryKind::BlacklistPackage | EntryKind::BlacklistSourcePackage => {
                                false
                            }
                        }
                })
                .cloned()
                .collect();
            result.push((
                name.clone(),
                ResolvedSeed {
                    entries,
                    blacklisted_packages: packages,
                    blacklisted_sources: sources,
                },
            ));
        }
        Ok(result)
    }

    /// Determine Recommends behavior for one seed from Germinate's documented
    /// Structure/seed flags. The CLI force option is an explicit opt-in override.
    pub fn follows_recommends(
        &self,
        seed: &str,
        documents: &BTreeMap<String, SeedDocument>,
        force: bool,
    ) -> Result<bool, String> {
        if force {
            return Ok(true);
        }
        let document = documents
            .get(seed)
            .ok_or_else(|| format!("seed file `{seed}` was not supplied"))?;
        if document.features.contains("follow-recommends") {
            return Ok(true);
        }
        if document.features.contains("no-follow-recommends") {
            return Ok(false);
        }
        Ok(self.features.contains("follow-recommends")
            || document.features.contains("follow-recommends"))
    }

    fn visit(
        &self,
        seed: &str,
        visiting: &mut BTreeSet<String>,
        visited: &mut BTreeSet<String>,
        order: &mut Vec<String>,
    ) -> Result<(), String> {
        if visited.contains(seed) {
            return Ok(());
        }
        if !visiting.insert(seed.to_owned()) {
            return Err(format!("inheritance cycle includes `{seed}`"));
        }
        let parents = self
            .seeds
            .get(seed)
            .ok_or_else(|| format!("seed `{seed}` inherits from an undeclared seed"))?;
        for parent in parents {
            self.visit(parent, visiting, visited, order)?;
        }
        visiting.remove(seed);
        visited.insert(seed.to_owned());
        order.push(seed.to_owned());
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SeedDocument {
    pub headers: BTreeMap<String, String>,
    pub features: BTreeSet<String>,
    pub entries: Vec<SeedEntry>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SeedEntry {
    pub kind: EntryKind,
    pub name: String,
    pub recommended: bool,
    pub architectures: ArchitectureRule,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct ResolvedSeed {
    pub entries: Vec<SeedEntry>,
    pub blacklisted_packages: BTreeSet<String>,
    pub blacklisted_sources: BTreeSet<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum EntryKind {
    Package,
    SourcePackage,
    BlacklistPackage,
    BlacklistSourcePackage,
    Snap,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct ArchitectureRule {
    pub include: BTreeSet<String>,
    pub exclude: BTreeSet<String>,
}

impl ArchitectureRule {
    pub fn applies_to(&self, architecture: &str) -> bool {
        (self.include.is_empty() || self.include.contains(architecture))
            && !self.exclude.contains(architecture)
    }
}

impl SeedDocument {
    /// Parse Germinate's documented seed-line forms without resolving package metadata.
    pub fn parse(input: &str) -> Result<Self, ParseError> {
        let mut result = Self {
            headers: BTreeMap::new(),
            features: BTreeSet::new(),
            entries: Vec::new(),
        };
        for (index, raw) in input.lines().enumerate() {
            let line_number = index + 1;
            let line = raw.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let Some(entry_text) = line.strip_prefix("* ") else {
                if result.entries.is_empty() {
                    if let Some((key, value)) = line.split_once(':') {
                        let key = key.trim();
                        if key.starts_with("Task-") && !key.chars().any(char::is_whitespace) {
                            result
                                .headers
                                .insert(key.to_owned(), value.trim().to_owned());
                        }
                    }
                }
                continue;
            };
            let entry_text = entry_text
                .split_once('#')
                .map_or(entry_text, |(before_comment, _)| before_comment)
                .trim();
            if entry_text.is_empty() {
                continue;
            }
            if let Some(value) = entry_text.strip_prefix("Feature:") {
                let feature = value.trim();
                if feature.is_empty() || feature.split_whitespace().count() != 1 {
                    return Err(ParseError {
                        line: line_number,
                        message: "expected one feature name after `Feature:`".into(),
                    });
                }
                result.features.insert(feature.to_owned());
                continue;
            }
            result.entries.push(parse_entry(entry_text, line_number)?);
        }
        Ok(result)
    }
}

fn parse_entry(input: &str, line: usize) -> Result<SeedEntry, ParseError> {
    let mut text = input.trim();
    let mut architectures = ArchitectureRule::default();
    if text.ends_with(']') {
        let Some(open) = text.rfind('[') else {
            return Err(ParseError {
                line,
                message: "architecture qualifier has no opening `[`".into(),
            });
        };
        let qualifier = &text[open + 1..text.len() - 1];
        if qualifier.is_empty() {
            return Err(ParseError {
                line,
                message: "empty architecture qualifier".into(),
            });
        }
        for arch in qualifier.split_whitespace() {
            if let Some(negative) = arch.strip_prefix('!') {
                if negative.is_empty() {
                    return Err(ParseError {
                        line,
                        message: "empty negated architecture".into(),
                    });
                }
                architectures.exclude.insert(negative.to_owned());
            } else {
                architectures.include.insert(arch.to_owned());
            }
        }
        if !architectures.include.is_empty() && !architectures.exclude.is_empty() {
            return Err(ParseError {
                line,
                message: "cannot mix included and excluded architectures".into(),
            });
        }
        text = text[..open].trim_end();
    }

    let recommended = text.starts_with('(') && text.ends_with(')');
    if recommended {
        text = text[1..text.len() - 1].trim();
    }
    let mut kind = EntryKind::Package;
    if let Some(rest) = text.strip_prefix('!') {
        text = rest.trim_start();
        kind = EntryKind::BlacklistPackage;
    }
    if let Some(rest) = text.strip_prefix('%') {
        text = rest.trim_start();
        kind = match kind {
            EntryKind::BlacklistPackage => EntryKind::BlacklistSourcePackage,
            _ => EntryKind::SourcePackage,
        };
    }
    if let Some(rest) = text.strip_prefix("snap:") {
        if kind != EntryKind::Package {
            return Err(ParseError {
                line,
                message: "snap entries cannot be blacklisted".into(),
            });
        }
        kind = EntryKind::Snap;
        text = rest.trim();
        if text.contains('(') || text.contains(')') {
            return Err(ParseError {
                line,
                message: "snap names cannot use package recommendation syntax".into(),
            });
        }
    }
    if text.is_empty() || text.chars().any(char::is_whitespace) {
        return Err(ParseError {
            line,
            message: "expected one package, source package, or snap name".into(),
        });
    }
    if kind == EntryKind::Snap && text.ends_with("/classic") {
        let name = text.trim_end_matches("/classic");
        if name.is_empty() {
            return Err(ParseError {
                line,
                message: "empty snap name".into(),
            });
        }
    }
    Ok(SeedEntry {
        kind,
        name: text.to_owned(),
        recommended,
        architectures,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn structure_tracks_features_includes_and_inheritance() {
        let structure = Structure::parse(
            "feature follow-recommends\ninclude platform.resolute\nbase:\n desktop: base artwork\nartwork:\n",
        ).unwrap();
        assert!(structure.features.contains("follow-recommends"));
        assert_eq!(structure.includes, ["platform.resolute"]);
        assert_eq!(
            structure.inheritance_order("desktop").unwrap(),
            ["base", "artwork", "desktop"]
        );
    }

    #[test]
    fn structure_rejects_cycles_and_missing_parents() {
        let cycle = Structure::parse("a: b\nb: a\n").unwrap();
        assert!(cycle.inheritance_order("a").unwrap_err().contains("cycle"));
        let missing = Structure::parse("a: absent\n").unwrap();
        assert!(missing
            .inheritance_order("a")
            .unwrap_err()
            .contains("absent"));
    }

    #[test]
    fn structure_composes_included_collections_and_rejects_missing_inputs() {
        let local = Structure::parse(
            "include platform.resolute\nartwork:\ndesktop: desktop-common artwork\n",
        )
        .unwrap();
        let platform = Structure::parse("desktop-common: standard\nstandard:\n").unwrap();
        let available = BTreeMap::from([("platform.resolute".into(), platform)]);
        let merged = Structure::with_includes("elementary.resolute", &local, &available).unwrap();
        assert_eq!(
            merged.inheritance_order("desktop").unwrap(),
            ["standard", "desktop-common", "artwork", "desktop"]
        );
        assert!(
            Structure::with_includes("elementary.resolute", &local, &BTreeMap::new())
                .unwrap_err()
                .contains("not supplied")
        );
    }

    #[test]
    fn seed_resolution_inherits_filters_architectures_and_applies_blacklists() {
        let structure = Structure::parse("base:\ndesktop: base\n").unwrap();
        let documents = BTreeMap::from([
            (
                "base".into(),
                SeedDocument::parse(
                    "* common\n* obsolete\n* !obsolete\n* (optional)\n* (snap:optional-snap)\n",
                )
                .unwrap(),
            ),
            (
                "desktop".into(),
                SeedDocument::parse(
                    "* !common\n* common\n* arm-tool [arm64]\n* amd-tool [amd64]\n",
                )
                .unwrap(),
            ),
        ]);
        let arm64 = structure
            .resolve_seed_entries("desktop", "arm64", &documents)
            .unwrap();
        assert_eq!(
            arm64
                .iter()
                .map(|entry| entry.name.as_str())
                .collect::<Vec<_>>(),
            ["arm-tool", "optional"]
        );
        assert!(
            arm64
                .iter()
                .find(|entry| entry.name == "optional")
                .unwrap()
                .recommended
        );
        assert!(!arm64.iter().any(|entry| entry.name == "optional-snap"));
        let resolved = structure
            .resolve_seed("desktop", "arm64", &documents)
            .unwrap();
        assert_eq!(
            resolved.blacklisted_packages,
            BTreeSet::from(["common".into()])
        );
        assert!(resolved.blacklisted_sources.is_empty());
        let amd64 = structure
            .resolve_seed_entries("desktop", "amd64", &documents)
            .unwrap();
        assert!(amd64.iter().any(|entry| entry.name == "amd-tool"));
        assert!(!amd64.iter().any(|entry| entry.name == "common"));
    }

    #[test]
    fn unrelated_seed_named_blocklist_has_no_global_effect() {
        let structure = Structure::parse("desktop:\nblocklist:\n").unwrap();
        let documents = BTreeMap::from([
            (
                "desktop".into(),
                SeedDocument::parse("* blocked\n").unwrap(),
            ),
            (
                "blocklist".into(),
                SeedDocument::parse("* !blocked\n").unwrap(),
            ),
        ]);
        let resolved = structure
            .resolve_seed("desktop", "arm64", &documents)
            .unwrap();
        assert_eq!(resolved.entries[0].name, "blocked");
        assert!(resolved.blacklisted_packages.is_empty());
    }

    #[test]
    fn inner_blocklist_does_not_exclude_a_descendant_seed_entry() {
        let structure = Structure::parse("base:\ndesktop: base\n").unwrap();
        let documents = BTreeMap::from([
            ("base".into(), SeedDocument::parse("* !blocked\n").unwrap()),
            (
                "desktop".into(),
                SeedDocument::parse("* blocked\n").unwrap(),
            ),
        ]);
        let groups = structure
            .resolve_seed_groups("desktop", "arm64", &documents)
            .unwrap();
        assert!(groups[0].1.blacklisted_packages.contains("blocked"));
        assert!(!groups[1].1.blacklisted_packages.contains("blocked"));
        let resolved = structure
            .resolve_seed("desktop", "arm64", &documents)
            .unwrap();
        assert_eq!(resolved.entries[0].name, "blocked");
    }

    #[test]
    fn recommend_feature_uses_structure_and_seed_override() {
        let global = Structure::parse("feature follow-recommends\ndesktop:\n").unwrap();
        let documents = BTreeMap::from([(
            "desktop".into(),
            SeedDocument::parse("* Feature: no-follow-recommends\n* app\n").unwrap(),
        )]);
        assert!(!global
            .follows_recommends("desktop", &documents, false)
            .unwrap());
        assert!(global
            .follows_recommends("desktop", &documents, true)
            .unwrap());

        let local = Structure::parse("desktop:\n").unwrap();
        let documents = BTreeMap::from([(
            "desktop".into(),
            SeedDocument::parse("* Feature: follow-recommends\n* app\n").unwrap(),
        )]);
        assert!(local
            .follows_recommends("desktop", &documents, false)
            .unwrap());
    }

    #[test]
    fn parses_documented_seed_entries_and_architecture_filters() {
        let seed = SeedDocument::parse(
            "Bluetooth:\nTask-Name: Desktop\n* Feature: follow-recommends\n* bash # shell\n* (fonts-noto) [arm64]\n* %linux [amd64]\n* !obsolete [!arm64]\n* snap:example/classic\n* (snap:ignored)\n",
        ).unwrap();
        assert_eq!(seed.headers["Task-Name"], "Desktop");
        assert!(!seed.headers.contains_key("Bluetooth"));
        assert!(seed.features.contains("follow-recommends"));
        assert_eq!(seed.entries.len(), 6);
        assert_eq!(seed.entries[1].kind, EntryKind::Package);
        assert!(seed.entries[1].recommended);
        assert!(seed.entries[1].architectures.applies_to("arm64"));
        assert!(!seed.entries[1].architectures.applies_to("amd64"));
        assert_eq!(seed.entries[2].kind, EntryKind::SourcePackage);
        assert_eq!(seed.entries[3].kind, EntryKind::BlacklistPackage);
        assert!(!seed.entries[3].architectures.applies_to("arm64"));
        assert_eq!(seed.entries[4].kind, EntryKind::Snap);
        assert!(seed.entries[5].recommended);
        assert_eq!(seed.entries[5].kind, EntryKind::Snap);
    }

    #[test]
    fn malformed_entries_fail_closed() {
        assert!(SeedDocument::parse("* package [\n").is_err());
        assert!(SeedDocument::parse("* package [arm64 !amd64]\n").is_err());
        assert!(SeedDocument::parse("* !snap:thing\n").is_err());
    }
}
