//! Debian control and binary-package metadata used by the package-closure candidate.
//! This is an independent implementation; it does not call apt or Germinate.

use crate::{EntryKind, ParseError, ResolvedSeed, SeedEntry};
use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet, VecDeque};

pub type ControlFields = BTreeMap<String, String>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ControlStanza {
    pub line: usize,
    pub fields: ControlFields,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VersionConstraint {
    pub operator: VersionOperator,
    pub version: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VersionOperator {
    Less,
    LessOrEqual,
    Equal,
    GreaterOrEqual,
    Greater,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ArchitectureQualifier {
    Unqualified,
    Any,
    Native,
    Specific(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Alternative {
    pub package: String,
    pub architecture: ArchitectureQualifier,
    pub version: Option<VersionConstraint>,
}

pub type DependencyGroup = Vec<Alternative>;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MultiArch {
    No,
    Same,
    Foreign,
    Allowed,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProvidedVirtual {
    pub name: String,
    pub version: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BinaryPackage {
    pub package: String,
    pub version: String,
    pub architecture: String,
    pub source: String,
    pub multi_arch: MultiArch,
    pub depends: Vec<DependencyGroup>,
    pub pre_depends: Vec<DependencyGroup>,
    pub recommends: Vec<DependencyGroup>,
    pub provides: Vec<ProvidedVirtual>,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct PackageKey {
    pub package: String,
    pub architecture: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct PackageClosure {
    pub packages: BTreeSet<PackageKey>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct SeedPackageRoots {
    pub depends: BTreeSet<String>,
    pub recommends: BTreeSet<String>,
    pub snaps: BTreeSet<String>,
}

pub fn expand_seed_entries(
    entries: &[SeedEntry],
    catalog: &PackageCatalog,
    architecture: &str,
) -> Result<SeedPackageRoots, String> {
    let mut roots = SeedPackageRoots::default();
    for entry in entries {
        match entry.kind {
            EntryKind::Package | EntryKind::SourcePackage => {
                let packages = if entry.kind == EntryKind::Package {
                    vec![entry.name.clone()]
                } else {
                    catalog.source_binaries(&entry.name, architecture)
                };
                if packages.is_empty() {
                    return Err(format!(
                        "seed source package `{}` has no binaries for {architecture}",
                        entry.name
                    ));
                }
                let target = if entry.recommended {
                    &mut roots.recommends
                } else {
                    &mut roots.depends
                };
                target.extend(packages);
            }
            EntryKind::Snap if !entry.recommended => {
                roots.snaps.insert(entry.name.clone());
            }
            EntryKind::Snap => {
                // Germinate ignores recommended snaps.
            }
            EntryKind::BlacklistPackage | EntryKind::BlacklistSourcePackage => {
                return Err("seed blacklists must be applied before archive expansion".into());
            }
        }
    }
    roots
        .recommends
        .retain(|package| !roots.depends.contains(package));
    Ok(roots)
}

pub fn expand_resolved_seed(
    seed: &ResolvedSeed,
    catalog: &PackageCatalog,
    architecture: &str,
) -> Result<SeedPackageRoots, String> {
    let mut roots = expand_seed_entries(&seed.entries, catalog, architecture)?;
    // Germinate blocklists filter seed inclusions. They do not rewrite archive
    // relationships: a blocked package may still reappear as a dependency.
    roots.depends.retain(|package| {
        !catalog.seed_root_is_blacklisted(
            package,
            architecture,
            &seed.blacklisted_packages,
            &seed.blacklisted_sources,
        )
    });
    roots.recommends.retain(|package| {
        !catalog.seed_root_is_blacklisted(
            package,
            architecture,
            &seed.blacklisted_packages,
            &seed.blacklisted_sources,
        )
    });
    Ok(roots)
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct PackageCatalog {
    packages: BTreeMap<String, Vec<BinaryPackage>>,
}

pub fn parse_control_stanzas(input: &str) -> Result<Vec<ControlStanza>, ParseError> {
    let mut stanzas = Vec::new();
    let mut fields = ControlFields::new();
    let mut last_key: Option<String> = None;
    let mut stanza_line = 0;
    let flush =
        |fields: &mut ControlFields, stanza_line: &mut usize, stanzas: &mut Vec<ControlStanza>| {
            if !fields.is_empty() {
                stanzas.push(ControlStanza {
                    line: *stanza_line,
                    fields: std::mem::take(fields),
                });
            }
            *stanza_line = 0;
        };

    for (index, raw) in input.lines().enumerate() {
        let line_number = index + 1;
        if raw.trim().is_empty() {
            flush(&mut fields, &mut stanza_line, &mut stanzas);
            last_key = None;
            continue;
        }
        if raw.starts_with(' ') || raw.starts_with('\t') {
            let Some(key) = &last_key else {
                return Err(ParseError {
                    line: line_number,
                    message: "continuation line has no preceding control field".into(),
                });
            };
            let value = fields.get_mut(key).expect("last field remains in stanza");
            value.push('\n');
            value.push_str(raw.trim());
            continue;
        }
        let Some((key, value)) = raw.split_once(':') else {
            return Err(ParseError {
                line: line_number,
                message: "expected a Debian control field in `Name: value` form".into(),
            });
        };
        let key = key.trim();
        if key.is_empty()
            || !key
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
        {
            return Err(ParseError {
                line: line_number,
                message: format!("invalid Debian control field name `{key}`"),
            });
        }
        if fields.contains_key(key) {
            return Err(ParseError {
                line: line_number,
                message: format!("duplicate Debian control field `{key}`"),
            });
        }
        let key = key.to_owned();
        if fields.is_empty() {
            stanza_line = line_number;
        }
        fields.insert(key.clone(), value.trim_start().to_owned());
        last_key = Some(key);
    }
    flush(&mut fields, &mut stanza_line, &mut stanzas);
    Ok(stanzas)
}

pub fn parse_relationships(input: &str) -> Result<Vec<DependencyGroup>, String> {
    if input.trim().is_empty() {
        return Ok(Vec::new());
    }
    split_top_level(input, ',')?
        .into_iter()
        .map(|group| {
            let alternatives = split_top_level(group, '|')?
                .into_iter()
                .map(parse_alternative)
                .collect::<Result<Vec<_>, _>>()?;
            if alternatives.is_empty() {
                return Err("empty dependency alternative group".into());
            }
            Ok(alternatives)
        })
        .collect()
}

fn split_top_level(input: &str, delimiter: char) -> Result<Vec<&str>, String> {
    let mut round = 0_u32;
    let mut square = 0_u32;
    let mut start = 0;
    let mut pieces = Vec::new();
    for (index, character) in input.char_indices() {
        match character {
            '(' => round += 1,
            ')' => {
                round = round
                    .checked_sub(1)
                    .ok_or_else(|| "unmatched `)` in package relationship".to_owned())?;
            }
            '[' => square += 1,
            ']' => {
                square = square
                    .checked_sub(1)
                    .ok_or_else(|| "unmatched `]` in package relationship".to_owned())?;
            }
            _ => {}
        }
        if character == delimiter && round == 0 && square == 0 {
            pieces.push(input[start..index].trim());
            start = index + character.len_utf8();
        }
    }
    if round != 0 || square != 0 {
        return Err("unclosed delimiter in package relationship".into());
    }
    pieces.push(input[start..].trim());
    if pieces.iter().any(|piece| piece.is_empty()) {
        return Err("empty item in package relationship".into());
    }
    Ok(pieces)
}

fn parse_alternative(input: &str) -> Result<Alternative, String> {
    let input = input.trim();
    let (atom, constraint_text) = if let Some(open) = input.find('(') {
        let close = input
            .rfind(')')
            .ok_or_else(|| "version constraint has no closing `)`".to_owned())?;
        if close < open || !input[close + 1..].trim().is_empty() {
            return Err(format!("malformed version constraint in `{input}`"));
        }
        (&input[..open], Some(input[open + 1..close].trim()))
    } else {
        if input.contains(')') {
            return Err(format!("unmatched `)` in `{input}`"));
        }
        (input, None)
    };
    let mut words = atom.split_whitespace();
    let package_atom = words
        .next()
        .ok_or_else(|| "missing package name in relationship".to_owned())?;
    if words.next().is_some() {
        return Err(format!("unexpected text after package name in `{input}`"));
    }
    let (package, architecture) = match package_atom.rsplit_once(':') {
        Some((package, "any")) => (package, ArchitectureQualifier::Any),
        Some((package, "native")) => (package, ArchitectureQualifier::Native),
        Some((package, architecture)) => (
            package,
            ArchitectureQualifier::Specific(architecture.to_owned()),
        ),
        None => (package_atom, ArchitectureQualifier::Unqualified),
    };
    if !valid_package_name(package) {
        return Err(format!("invalid package name `{package}`"));
    }
    if let ArchitectureQualifier::Specific(architecture) = &architecture {
        if !valid_architecture(architecture) {
            return Err(format!(
                "invalid package architecture qualifier `{architecture}`"
            ));
        }
    }
    let version = constraint_text.map(parse_version_constraint).transpose()?;
    Ok(Alternative {
        package: package.to_owned(),
        architecture,
        version,
    })
}

fn parse_version_constraint(input: &str) -> Result<VersionConstraint, String> {
    let input = input.trim();
    let (operator, version) = [
        (">>", VersionOperator::Greater),
        ("<<", VersionOperator::Less),
        (">=", VersionOperator::GreaterOrEqual),
        ("<=", VersionOperator::LessOrEqual),
        ("=", VersionOperator::Equal),
    ]
    .into_iter()
    .find_map(|(prefix, operator)| input.strip_prefix(prefix).map(|rest| (operator, rest)))
    .ok_or_else(|| format!("unsupported Debian version relation `{input}`"))?;
    let version = version.trim();
    if !valid_version(version) {
        return Err(format!("invalid version in relationship `{input}`"));
    }
    Ok(VersionConstraint {
        operator,
        version: version.to_owned(),
    })
}

fn valid_package_name(name: &str) -> bool {
    name.as_bytes()
        .first()
        .is_some_and(u8::is_ascii_alphanumeric)
        && name.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || b"+.-".contains(&byte)
        })
}

fn valid_version(version: &str) -> bool {
    let version = match version.split_once(':') {
        Some((epoch, rest)) => {
            if epoch.is_empty() || !epoch.bytes().all(|byte| byte.is_ascii_digit()) {
                return false;
            }
            rest
        }
        None => version,
    };
    let (upstream, revision) = match version.rsplit_once('-') {
        Some((upstream, revision)) => (upstream, Some(revision)),
        None => (version, None),
    };
    !upstream.is_empty()
        && upstream.as_bytes()[0].is_ascii_digit()
        && upstream
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b".+~".contains(&byte))
        && revision.is_none_or(|revision| {
            !revision.is_empty()
                && revision
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || b"+.~".contains(&byte))
        })
}

fn valid_architecture(architecture: &str) -> bool {
    !architecture.is_empty()
        && architecture
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
}

impl BinaryPackage {
    pub fn from_fields(fields: &ControlFields) -> Result<Self, String> {
        let package = required(fields, "Package")?.to_owned();
        if !valid_package_name(&package) {
            return Err(format!("invalid Package field `{package}`"));
        }
        let version = required(fields, "Version")?.to_owned();
        if !valid_version(&version) {
            return Err(format!("invalid Version field `{version}`"));
        }
        let architecture = required(fields, "Architecture")?.to_owned();
        if !valid_architecture(&architecture) {
            return Err(format!("invalid Architecture field `{architecture}`"));
        }
        let source = fields
            .get("Source")
            .map(|value| parse_source_field(value))
            .transpose()?
            .unwrap_or_else(|| package.clone());
        let multi_arch = match fields.get("Multi-Arch").map(String::as_str) {
            None | Some("no") => MultiArch::No,
            Some("same") => MultiArch::Same,
            Some("foreign") => MultiArch::Foreign,
            Some("allowed") => MultiArch::Allowed,
            Some(other) => return Err(format!("unsupported Multi-Arch value `{other}`")),
        };
        let relationships = |field: &str| -> Result<Vec<DependencyGroup>, String> {
            fields
                .get(field)
                .map(|value| parse_relationships(value))
                .unwrap_or_else(|| Ok(Vec::new()))
        };
        let provides = fields
            .get("Provides")
            .map(|value| parse_provides(value))
            .transpose()?
            .unwrap_or_default();
        Ok(Self {
            package,
            version,
            architecture,
            source,
            multi_arch,
            depends: relationships("Depends")?,
            pre_depends: relationships("Pre-Depends")?,
            recommends: relationships("Recommends")?,
            provides,
        })
    }
}

fn parse_provides(input: &str) -> Result<Vec<ProvidedVirtual>, String> {
    let groups = parse_relationships(input)?;
    let mut provided = Vec::new();
    for group in groups {
        if group.len() != 1 {
            return Err("Provides does not support alternative groups".into());
        }
        let alternative = &group[0];
        if alternative.architecture != ArchitectureQualifier::Unqualified {
            return Err("Provides does not support architecture qualifiers".into());
        }
        if let Some(version) = &alternative.version {
            if version.operator != VersionOperator::Equal {
                return Err("versioned Provides must use the `=` relation".into());
            }
        }
        provided.push(ProvidedVirtual {
            name: alternative.package.clone(),
            version: alternative
                .version
                .as_ref()
                .map(|version| version.version.clone()),
        });
    }
    Ok(provided)
}

fn required<'a>(fields: &'a ControlFields, name: &str) -> Result<&'a str, String> {
    fields
        .get(name)
        .map(String::as_str)
        .ok_or_else(|| format!("missing required `{name}` field"))
}

fn parse_source_field(value: &str) -> Result<String, String> {
    let mut words = value.split_whitespace();
    let name = words
        .next()
        .ok_or_else(|| "empty Source field".to_owned())?;
    if !valid_package_name(name) {
        return Err(format!("invalid source package name `{name}`"));
    }
    if let Some(version) = words.next() {
        let version = version
            .strip_prefix('(')
            .and_then(|version| version.strip_suffix(')'))
            .ok_or_else(|| format!("malformed Source field `{value}`"))?;
        if !valid_version(version) {
            return Err(format!("invalid source version `{version}`"));
        }
    }
    if words.next().is_some() {
        return Err(format!("unexpected text in Source field `{value}`"));
    }
    Ok(name.to_owned())
}

impl PackageCatalog {
    pub fn parse_packages(input: &str) -> Result<Self, ParseError> {
        let mut catalog = Self::default();
        for stanza in parse_control_stanzas(input)? {
            let package =
                BinaryPackage::from_fields(&stanza.fields).map_err(|message| ParseError {
                    line: stanza.line,
                    message,
                })?;
            catalog.insert(package);
        }
        Ok(catalog)
    }

    pub fn insert(&mut self, package: BinaryPackage) {
        let entries = self.packages.entry(package.package.clone()).or_default();
        if let Some(existing) = entries
            .iter_mut()
            .find(|existing| existing.architecture == package.architecture)
        {
            if compare_versions(&package.version, &existing.version) == Ordering::Greater {
                *existing = package;
            }
        } else {
            entries.push(package);
            entries.sort_by(|left, right| left.architecture.cmp(&right.architecture));
        }
    }

    pub fn package_names(&self) -> impl Iterator<Item = &str> {
        self.packages.keys().map(String::as_str)
    }

    pub fn source_binaries(&self, source: &str, architecture: &str) -> Vec<String> {
        let mut names = self
            .packages
            .values()
            .flatten()
            .filter(|package| {
                package.source == source
                    && (package.architecture == architecture || package.architecture == "all")
            })
            .map(|package| package.package.clone())
            .collect::<Vec<_>>();
        names.sort();
        names.dedup();
        names
    }

    /// Resolve one seed's binary-package roots.
    /// The feature flag applies only to archive Recommends. Parenthesized seed
    /// entries remain in their own recommendation output. Seed blocklists have
    /// already filtered direct roots and are not passed into archive dependency
    /// selection, matching Germinate's output behavior.
    pub fn resolve_seed_package_closure(
        &self,
        roots: &SeedPackageRoots,
        architecture: &str,
        follow_recommends: bool,
    ) -> Result<PackageClosure, String> {
        let package_roots = roots.depends.iter().cloned().collect::<Vec<_>>();
        self.dependency_closure(&package_roots, architecture, follow_recommends)
    }

    /// Resolve parenthesized seed entries and their hard dependencies into the
    /// separate recommendation output. Archive Recommends are not followed here.
    pub fn resolve_seed_recommendation_closure(
        &self,
        roots: &SeedPackageRoots,
        architecture: &str,
    ) -> Result<PackageClosure, String> {
        let package_roots = roots.recommends.iter().cloned().collect::<Vec<_>>();
        self.dependency_closure(&package_roots, architecture, false)
    }

    pub fn dependency_closure(
        &self,
        roots: &[String],
        architecture: &str,
        follow_recommends: bool,
    ) -> Result<PackageClosure, String> {
        let mut closure = PackageClosure::default();
        let mut queue = VecDeque::new();
        for root in roots {
            let alternative = Alternative {
                package: root.clone(),
                architecture: ArchitectureQualifier::Unqualified,
                version: None,
            };
            let package = self
                .select_alternative(&alternative, architecture)
                .ok_or_else(|| {
                    format!("seed package `{root}` is unavailable for {architecture}")
                })?;
            let key = package_key(package);
            if closure.packages.insert(key.clone()) {
                queue.push_back(key);
            }
        }
        while let Some(key) = queue.pop_front() {
            let package = self
                .get(&key)
                .ok_or_else(|| format!("selected package {} disappeared", key.package))?;
            let mut groups = package.pre_depends.clone();
            groups.extend(package.depends.clone());
            if follow_recommends {
                groups.extend(package.recommends.clone());
            }
            for group in groups {
                let already_selected = group.iter().any(|alternative| {
                    closure.packages.iter().any(|selected| {
                        self.get(selected).is_some_and(|package| {
                            (package.package == alternative.package
                                && self.package_satisfies(package, alternative, architecture))
                                || package.provides.iter().any(|provided| {
                                    provided.name == alternative.package
                                        && self.provider_satisfies(
                                            package,
                                            provided,
                                            alternative,
                                            architecture,
                                        )
                                })
                        })
                    })
                });
                if already_selected {
                    continue;
                }
                let selected = group
                    .iter()
                    .find_map(|alternative| self.select_alternative(alternative, architecture))
                    .ok_or_else(|| {
                        format!(
                            "no available alternative satisfies dependency of `{}` for {architecture}",
                            key.package
                        )
                    })?;
                let selected_key = package_key(selected);
                if closure.packages.insert(selected_key.clone()) {
                    queue.push_back(selected_key);
                }
            }
        }
        Ok(closure)
    }

    fn get(&self, key: &PackageKey) -> Option<&BinaryPackage> {
        self.packages
            .get(&key.package)?
            .iter()
            .find(|package| package.architecture == key.architecture)
    }

    fn seed_root_is_blacklisted(
        &self,
        package: &str,
        architecture: &str,
        blacklisted_packages: &BTreeSet<String>,
        blacklisted_sources: &BTreeSet<String>,
    ) -> bool {
        if blacklisted_packages.contains(package) {
            return true;
        }
        let candidates = self
            .packages
            .get(package)
            .into_iter()
            .flatten()
            .filter(|candidate| {
                architecture_matches(candidate, &ArchitectureQualifier::Unqualified, architecture)
            })
            .collect::<Vec<_>>();
        !candidates.is_empty()
            && candidates
                .iter()
                .all(|candidate| blacklisted_sources.contains(&candidate.source))
    }

    fn select_alternative(
        &self,
        alternative: &Alternative,
        architecture: &str,
    ) -> Option<&BinaryPackage> {
        let direct = self
            .packages
            .get(&alternative.package)
            .into_iter()
            .flatten()
            .filter(|package| self.package_satisfies(package, alternative, architecture))
            .max_by(|left, right| compare_versions(&left.version, &right.version));
        direct.or_else(|| {
            self.packages
                .values()
                .flatten()
                .filter(|provider| {
                    provider.provides.iter().any(|provided| {
                        provided.name == alternative.package
                            && self.provider_satisfies(
                                provider,
                                provided,
                                alternative,
                                architecture,
                            )
                    })
                })
                .max_by(|left, right| compare_versions(&left.version, &right.version))
        })
    }

    fn package_satisfies(
        &self,
        package: &BinaryPackage,
        alternative: &Alternative,
        architecture: &str,
    ) -> bool {
        if !architecture_matches(package, &alternative.architecture, architecture) {
            return false;
        }
        alternative
            .version
            .as_ref()
            .is_none_or(|constraint| version_matches(&package.version, constraint))
    }

    fn provider_satisfies(
        &self,
        provider: &BinaryPackage,
        provided: &ProvidedVirtual,
        alternative: &Alternative,
        architecture: &str,
    ) -> bool {
        if !architecture_matches(provider, &alternative.architecture, architecture) {
            return false;
        }
        match &alternative.version {
            None => true,
            Some(constraint) => provided
                .version
                .as_deref()
                .is_some_and(|version| version_matches(version, constraint)),
        }
    }
}

fn package_key(package: &BinaryPackage) -> PackageKey {
    PackageKey {
        package: package.package.clone(),
        architecture: package.architecture.clone(),
    }
}

fn architecture_matches(
    package: &BinaryPackage,
    qualifier: &ArchitectureQualifier,
    architecture: &str,
) -> bool {
    match qualifier {
        ArchitectureQualifier::Unqualified => {
            package.architecture == "all"
                || package.architecture == architecture
                || package.multi_arch == MultiArch::Foreign
        }
        ArchitectureQualifier::Any => package.multi_arch == MultiArch::Allowed,
        ArchitectureQualifier::Native => {
            package.architecture == "all" || package.architecture == architecture
        }
        ArchitectureQualifier::Specific(name) => {
            package.architecture == "all" || package.architecture == name.as_str()
        }
    }
}

pub fn compare_versions(left: &str, right: &str) -> Ordering {
    let (left_epoch, left_version) = split_epoch(left);
    let (right_epoch, right_version) = split_epoch(right);
    compare_numeric(left_epoch, right_epoch).then_with(|| {
        let (left_upstream, left_revision) = split_revision(left_version);
        let (right_upstream, right_revision) = split_revision(right_version);
        verrevcmp(left_upstream, right_upstream)
            .then_with(|| verrevcmp(left_revision, right_revision))
    })
}

fn split_epoch(version: &str) -> (&str, &str) {
    match version.split_once(':') {
        Some((epoch, rest)) if epoch.bytes().all(|byte| byte.is_ascii_digit()) => (epoch, rest),
        _ => ("0", version),
    }
}

fn split_revision(version: &str) -> (&str, &str) {
    match version.rsplit_once('-') {
        Some((upstream, revision)) => (upstream, revision),
        None => (version, "0"),
    }
}

fn compare_numeric(left: &str, right: &str) -> Ordering {
    let left = left.trim_start_matches('0');
    let right = right.trim_start_matches('0');
    left.len().cmp(&right.len()).then_with(|| left.cmp(right))
}

fn verrevcmp(left: &str, right: &str) -> Ordering {
    let left = left.as_bytes();
    let right = right.as_bytes();
    let (mut i, mut j) = (0, 0);
    while i < left.len() || j < right.len() {
        while (i < left.len() && !left[i].is_ascii_digit())
            || (j < right.len() && !right[j].is_ascii_digit())
        {
            let left_order = order_char(left.get(i).copied());
            let right_order = order_char(right.get(j).copied());
            if left_order != right_order {
                return left_order.cmp(&right_order);
            }
            if i < left.len() {
                i += 1;
            }
            if j < right.len() {
                j += 1;
            }
        }
        while i < left.len() && left[i] == b'0' {
            i += 1;
        }
        while j < right.len() && right[j] == b'0' {
            j += 1;
        }
        let mut first_difference = Ordering::Equal;
        while i < left.len()
            && j < right.len()
            && left[i].is_ascii_digit()
            && right[j].is_ascii_digit()
        {
            if first_difference == Ordering::Equal {
                first_difference = left[i].cmp(&right[j]);
            }
            i += 1;
            j += 1;
        }
        if i < left.len() && left[i].is_ascii_digit() {
            return Ordering::Greater;
        }
        if j < right.len() && right[j].is_ascii_digit() {
            return Ordering::Less;
        }
        if first_difference != Ordering::Equal {
            return first_difference;
        }
    }
    Ordering::Equal
}

fn order_char(character: Option<u8>) -> i32 {
    match character {
        Some(b'~') => -1,
        None => 0,
        Some(character) if character.is_ascii_digit() => 0,
        Some(character) if character.is_ascii_alphabetic() => i32::from(character),
        Some(character) => i32::from(character) + 256,
    }
}

fn version_matches(candidate: &str, constraint: &VersionConstraint) -> bool {
    let ordering = compare_versions(candidate, &constraint.version);
    match constraint.operator {
        VersionOperator::Less => ordering == Ordering::Less,
        VersionOperator::LessOrEqual => ordering != Ordering::Greater,
        VersionOperator::Equal => ordering == Ordering::Equal,
        VersionOperator::GreaterOrEqual => ordering != Ordering::Less,
        VersionOperator::Greater => ordering == Ordering::Greater,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn control_parser_joins_continuations_and_rejects_malformed_fields() {
        let stanzas = parse_control_stanzas(
            "Package: demo\nVersion: 1.0\nDescription: first line\n continuation\n\n",
        )
        .unwrap();
        assert_eq!(stanzas.len(), 1);
        assert_eq!(stanzas[0].fields["Description"], "first line\ncontinuation");
        assert!(parse_control_stanzas(" continuation without field\n").is_err());
        assert!(parse_control_stanzas("Package: one\nPackage: two\n").is_err());
        let error = PackageCatalog::parse_packages(
            "Package: good\nVersion: 1\nArchitecture: arm64\n\nPackage: broken\n",
        )
        .unwrap_err();
        assert_eq!(error.line, 5);
    }

    #[test]
    fn relationship_parser_keeps_alternatives_and_versions_structured() {
        let relations =
            parse_relationships("libc6 (>= 2.38), mail-transport-agent | exim4:any (<< 5:6.0)")
                .unwrap();
        assert_eq!(relations.len(), 2);
        assert_eq!(relations[0][0].package, "libc6");
        assert_eq!(
            relations[0][0].version.as_ref().unwrap().operator,
            VersionOperator::GreaterOrEqual
        );
        assert_eq!(relations[1].len(), 2);
        assert_eq!(relations[1][1].architecture, ArchitectureQualifier::Any);
        assert_eq!(relations[1][1].version.as_ref().unwrap().version, "5:6.0");
        assert!(parse_relationships("one, | two").is_err());
        assert!(parse_relationships("package (>= not-a-version)").is_err());
    }

    #[test]
    fn version_order_matches_debian_epoch_tilde_and_revision_rules() {
        assert_eq!(compare_versions("1:1.0", "2.0"), Ordering::Greater);
        assert_eq!(compare_versions("1.0~rc1", "1.0"), Ordering::Less);
        assert_eq!(compare_versions("1.0-2", "1.0-10"), Ordering::Less);
        assert_eq!(compare_versions("1.01", "1.1"), Ordering::Equal);
    }

    #[test]
    fn package_closure_follows_predepends_depends_alternatives_and_optional_recommends() {
        let packages = "Package: app\nVersion: 1.0\nArchitecture: arm64\nPre-Depends: init (>= 1)\nDepends: missing | libx (>= 2), tool\nRecommends: docs\n\nPackage: init\nVersion: 1.2\nArchitecture: arm64\n\nPackage: libx\nVersion: 2.4\nArchitecture: arm64\n\nPackage: tool\nVersion: 1.0\nArchitecture: all\n\nPackage: docs\nVersion: 1.0\nArchitecture: all\n";
        let catalog = PackageCatalog::parse_packages(packages).unwrap();
        assert_eq!(catalog.packages["app"][0].pre_depends.len(), 1);
        assert_eq!(catalog.packages["app"][0].depends.len(), 2);
        let roots = vec!["app".into()];
        let core = catalog.dependency_closure(&roots, "arm64", false).unwrap();
        assert_eq!(core.packages.len(), 4);
        assert!(!core.packages.iter().any(|key| key.package == "docs"));
        let full = catalog.dependency_closure(&roots, "arm64", true).unwrap();
        assert_eq!(full.packages.len(), 5);
        assert!(full.packages.iter().any(|key| key.package == "docs"));
    }

    #[test]
    fn package_closure_supports_virtual_providers_and_fails_on_missing_dependencies() {
        let packages = "Package: app\nVersion: 1\nArchitecture: amd64\nDepends: mail-transport-agent\n\nPackage: postfix\nVersion: 3.9\nArchitecture: amd64\nProvides: mail-transport-agent\n";
        let catalog = PackageCatalog::parse_packages(packages).unwrap();
        let closure = catalog
            .dependency_closure(&["app".into()], "amd64", false)
            .unwrap();
        assert!(closure.packages.iter().any(|key| key.package == "postfix"));
        assert!(catalog
            .dependency_closure(&["missing".into()], "amd64", false)
            .is_err());
    }

    #[test]
    fn archive_relationships_are_not_rewritten_by_seed_blocklists() {
        let packages = "Package: app\nVersion: 1\nArchitecture: amd64\nDepends: blocked | allowed, virtual\n\nPackage: blocked\nVersion: 1\nArchitecture: amd64\nSource: forbidden-source\n\nPackage: allowed\nVersion: 1\nArchitecture: amd64\n\nPackage: provider\nVersion: 1\nArchitecture: amd64\nSource: forbidden-source\nProvides: virtual\n";
        let catalog = PackageCatalog::parse_packages(packages).unwrap();
        let closure = catalog
            .dependency_closure(&["app".into()], "amd64", false)
            .unwrap();
        assert!(closure.packages.iter().any(|key| key.package == "blocked"));
        assert!(!closure.packages.iter().any(|key| key.package == "allowed"));
        assert!(closure.packages.iter().any(|key| key.package == "provider"));
    }

    #[test]
    fn provides_accepts_only_policy_supported_version_form() {
        for provides in ["virtual (= 2.0)", "virtual, another-virtual"] {
            let fields = parse_control_stanzas(&format!(
                "Package: provider\nVersion: 1\nArchitecture: amd64\nProvides: {provides}\n"
            ))
            .unwrap()
            .remove(0)
            .fields;
            assert!(BinaryPackage::from_fields(&fields).is_ok(), "{provides}");
        }
        for package in ["-bad", ".bad", "+bad"] {
            let fields = parse_control_stanzas(&format!(
                "Package: {package}\nVersion: 1\nArchitecture: amd64\n"
            ))
            .unwrap()
            .remove(0)
            .fields;
            assert!(BinaryPackage::from_fields(&fields).is_err(), "{package}");
        }
        for provides in [
            "virtual (>= 2.0)",
            "virtual:any",
            "virtual | another-virtual",
        ] {
            let fields = parse_control_stanzas(&format!(
                "Package: provider\nVersion: 1\nArchitecture: amd64\nProvides: {provides}\n"
            ))
            .unwrap()
            .remove(0)
            .fields;
            assert!(BinaryPackage::from_fields(&fields).is_err(), "{provides}");
        }
    }

    #[test]
    fn package_catalog_selects_newest_version_and_expands_source_binaries() {
        let packages = "Package: app\nVersion: 1\nArchitecture: arm64\nSource: desktop-source (2.0)\nDepends: library (>= 2)\n\nPackage: library\nVersion: 1\nArchitecture: arm64\n\nPackage: library\nVersion: 2\nArchitecture: arm64\n\nPackage: docs\nVersion: 1\nArchitecture: all\nSource: desktop-source\n";
        let catalog = PackageCatalog::parse_packages(packages).unwrap();
        assert_eq!(
            catalog.source_binaries("desktop-source", "arm64"),
            ["app", "docs"]
        );
        let closure = catalog
            .dependency_closure(&["app".into()], "arm64", false)
            .unwrap();
        assert!(closure.packages.iter().any(|key| key.package == "library"));
    }

    #[test]
    fn source_field_accepts_optional_version_and_rejects_malformed_text() {
        assert_eq!(
            parse_source_field("source-name (2:1.0-3)").unwrap(),
            "source-name"
        );
        for source in ["", "bad name extra", "source-name invalid", "-bad"] {
            assert!(parse_source_field(source).is_err(), "{source:?}");
        }
    }

    #[test]
    fn any_qualified_dependency_requires_multi_arch_allowed() {
        let packages = "Package: app\nVersion: 1\nArchitecture: arm64\nDepends: foreign-lib:any\n\nPackage: foreign-lib\nVersion: 1\nArchitecture: amd64\nMulti-Arch: allowed\n";
        let catalog = PackageCatalog::parse_packages(packages).unwrap();
        let closure = catalog
            .dependency_closure(&["app".into()], "arm64", false)
            .unwrap();
        assert!(closure.packages.contains(&PackageKey {
            package: "foreign-lib".into(),
            architecture: "amd64".into(),
        }));
    }

    #[test]
    fn seed_entries_expand_source_binaries_and_preserve_depends_recommends_and_snaps() {
        let packages = "Package: runtime\nVersion: 1\nArchitecture: arm64\nSource: runtime-src\nRecommends: runtime-extra\n\nPackage: runtime-doc\nVersion: 1\nArchitecture: all\nSource: runtime-src\n\nPackage: optional-app\nVersion: 1\nArchitecture: arm64\n\nPackage: runtime-extra\nVersion: 1\nArchitecture: arm64\n";
        let catalog = PackageCatalog::parse_packages(packages).unwrap();
        let seed = crate::SeedDocument::parse(
            "* %runtime-src\n* (optional-app)\n* snap:sample\n* (snap:ignored)\n",
        )
        .unwrap();
        let roots = expand_seed_entries(&seed.entries, &catalog, "arm64").unwrap();
        assert_eq!(
            roots.depends,
            BTreeSet::from(["runtime".into(), "runtime-doc".into()])
        );
        assert_eq!(roots.recommends, BTreeSet::from(["optional-app".into()]));
        assert_eq!(roots.snaps, BTreeSet::from(["sample".into()]));
        let without_recommends = catalog
            .resolve_seed_package_closure(&roots, "arm64", false)
            .unwrap();
        assert!(!without_recommends
            .packages
            .iter()
            .any(|key| key.package == "optional-app"));
        assert!(!without_recommends
            .packages
            .iter()
            .any(|key| key.package == "runtime-extra"));
        let with_recommends = catalog
            .resolve_seed_package_closure(&roots, "arm64", true)
            .unwrap();
        assert!(!with_recommends
            .packages
            .iter()
            .any(|key| key.package == "optional-app"));
        assert!(with_recommends
            .packages
            .iter()
            .any(|key| key.package == "runtime-extra"));
        let seed_recommends = catalog
            .resolve_seed_recommendation_closure(&roots, "arm64")
            .unwrap();
        assert!(seed_recommends
            .packages
            .iter()
            .any(|key| key.package == "optional-app"));
        assert!(!seed_recommends
            .packages
            .iter()
            .any(|key| key.package == "runtime-extra"));
    }

    #[test]
    fn resolved_seed_blocklists_filter_explicit_binary_roots() {
        let packages = "Package: app\nVersion: 1\nArchitecture: arm64\nDepends: blocked | allowed\n\nPackage: blocked\nVersion: 1\nArchitecture: arm64\nSource: blocked-source\n\nPackage: source-blocked\nVersion: 1\nArchitecture: arm64\nSource: blocked-source\n\nPackage: allowed\nVersion: 1\nArchitecture: arm64\n";
        let catalog = PackageCatalog::parse_packages(packages).unwrap();
        let structure = crate::Structure::parse("desktop:\n").unwrap();
        let documents = BTreeMap::from([(
            "desktop".into(),
            crate::SeedDocument::parse("* app\n* source-blocked\n* !blocked\n* !%blocked-source\n")
                .unwrap(),
        )]);
        let resolved = structure
            .resolve_seed("desktop", "arm64", &documents)
            .unwrap();
        let roots = expand_resolved_seed(&resolved, &catalog, "arm64").unwrap();
        assert!(!roots.depends.contains("source-blocked"));
        let closure = catalog
            .resolve_seed_package_closure(&roots, "arm64", false)
            .unwrap();
        assert!(closure.packages.iter().any(|key| key.package == "blocked"));
        assert!(!closure.packages.iter().any(|key| key.package == "allowed"));
    }
}
