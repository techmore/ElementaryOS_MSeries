//! Build-time substitution variables from generated metapackage package lists.
//! Independently implemented from the published dh_germinate_metapackage contract.

use crate::archive::parse_relationships;
use crate::ParseError;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct MetapackageMap {
    seeds_by_package: BTreeMap<String, String>,
}

impl MetapackageMap {
    pub fn parse(input: &str) -> Result<Self, ParseError> {
        let mut result = Self::default();
        for (index, line) in input.lines().enumerate() {
            let fields: Vec<_> = line.split_whitespace().collect();
            if fields.is_empty() {
                continue;
            }
            if fields.len() != 2 || !fields.iter().all(|field| safe_component(field)) {
                return Err(ParseError {
                    line: index + 1,
                    message: "expected `SEED METAPACKAGE` using simple file names".into(),
                });
            }
            if result
                .seeds_by_package
                .insert(fields[1].to_owned(), fields[0].to_owned())
                .is_some()
            {
                return Err(ParseError {
                    line: index + 1,
                    message: format!("duplicate metapackage mapping `{}`", fields[1]),
                });
            }
        }
        Ok(result)
    }

    /// Render a fresh germinate substvars fragment. The caller can supply this
    /// alongside other substvars to dpkg-gencontrol; this does not merge or mutate
    /// an existing debhelper file. Unmapped packages have no germinate variables.
    pub fn render_for(
        &self,
        directory: &Path,
        architecture: &str,
        package: &str,
    ) -> Result<String, String> {
        if !safe_component(architecture) || !safe_component(package) {
            return Err("architecture and package must be simple file names".into());
        }
        let Some(seed) = self.seeds_by_package.get(package) else {
            return Ok(String::new());
        };
        let read = |suffix: &str| {
            let path = directory.join(format!("{seed}{suffix}-{architecture}"));
            fs::read_to_string(&path).map_err(|error| format!("{}: {error}", path.display()))
        };
        // Read and validate both lists before returning any output.
        render_substvars(&read("")?, &read("-recommends")?)
    }
}

pub(crate) fn safe_component(value: &str) -> bool {
    value
        .as_bytes()
        .first()
        .is_some_and(u8::is_ascii_alphanumeric)
        && value.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || b"+.-".contains(&byte)
        })
}

/// Package-list lines become sorted, unique relationship entries, as in a fresh
/// debhelper substvars file. Empty lists omit the corresponding variable.
pub fn render_substvars(depends: &str, recommends: &str) -> Result<String, String> {
    let mut result = String::new();
    for (name, text) in [("Depends", depends), ("Recommends", recommends)] {
        let mut relationships = BTreeSet::new();
        for (index, line) in text.lines().enumerate() {
            let relationship = line.trim();
            if relationship.is_empty() {
                return Err(format!("{name} list line {} is empty", index + 1));
            }
            let groups = parse_relationships(relationship)
                .map_err(|error| format!("{name} list line {}: {error}", index + 1))?;
            if groups.len() != 1 {
                return Err(format!(
                    "{name} list line {} must contain one relationship",
                    index + 1
                ));
            }
            relationships.insert(relationship);
        }
        if !relationships.is_empty() {
            result.push_str(&format!(
                "germinate:{name}={}\n",
                relationships.into_iter().collect::<Vec<_>>().join(", ")
            ));
        }
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn renders_relationships_without_losing_alternatives_or_versions() {
        assert_eq!(
            render_substvars("zeta\n alpha (>= 2) | beta \nzeta\n", "docs\n").unwrap(),
            "germinate:Depends=alpha (>= 2) | beta, zeta\ngerminate:Recommends=docs\n"
        );
        assert_eq!(render_substvars("", "").unwrap(), "");
        assert_eq!(
            render_substvars("", "docs\n").unwrap(),
            "germinate:Recommends=docs\n"
        );
    }

    #[test]
    fn rejects_ambiguous_maps_and_paths_outside_the_package_directory() {
        assert!(MetapackageMap::parse("desktop fixture-meta\nother fixture-meta\n").is_err());
        assert!(MetapackageMap::parse("../desktop fixture-meta\n").is_err());
        assert!(MetapackageMap::parse("desktop fixture-meta extra\n").is_err());
        let map = MetapackageMap::parse("desktop fixture-meta\n").unwrap();
        assert!(map
            .render_for(Path::new("."), "../arm64", "fixture-meta")
            .is_err());
        assert_eq!(
            map.render_for(Path::new("/nonexistent"), "arm64", "unmapped")
                .unwrap(),
            ""
        );
    }

    #[test]
    fn rejects_broken_lists_instead_of_emitting_partial_relationships() {
        assert!(render_substvars("good\n", "bad (>= )\n").is_err());
        assert!(render_substvars("good\n\n", "").is_err());
        assert!(render_substvars("one, two\n", "").is_err());
    }
}
