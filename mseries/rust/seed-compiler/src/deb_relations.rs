//! Binary control relationship reduction for the metapackage build stage.

use crate::archive::{
    compare_versions, parse_relationships, Alternative, ArchitectureQualifier, ControlFields,
    DependencyGroup, VersionConstraint, VersionOperator,
};
use std::cmp::Ordering;

pub(crate) fn architecture_matches(pattern: &str, host: &str) -> bool {
    if pattern == host || pattern == "any" {
        return true;
    }
    let parts = pattern.split('-').collect::<Vec<_>>();
    if parts.len() < 2 || parts.len() > 4 {
        return false;
    }
    let tuple = ["base", "gnu", "linux", host];
    parts
        .iter()
        .rev()
        .zip(tuple.iter().rev())
        .all(|(pattern, value)| *pattern == "any" || pattern == value)
}

fn allowed_alternative(input: &str, host: &str) -> Result<Option<String>, String> {
    if let Some(open) = input.find('[') {
        let close = input[open..]
            .find(']')
            .map(|offset| open + offset)
            .ok_or("unclosed relationship architecture restriction")?;
        if !input[close + 1..].trim().is_empty() {
            return Err("unsupported text after relationship architecture restriction".into());
        }
        let patterns = input[open + 1..close]
            .split_whitespace()
            .collect::<Vec<_>>();
        if patterns.is_empty() {
            return Err("empty relationship architecture restriction".into());
        }
        let positive = patterns
            .iter()
            .filter(|pattern| !pattern.starts_with('!'))
            .collect::<Vec<_>>();
        let applies = (positive.is_empty()
            || positive
                .iter()
                .any(|pattern| architecture_matches(pattern, host)))
            && !patterns
                .iter()
                .filter_map(|pattern| pattern.strip_prefix('!'))
                .any(|pattern| architecture_matches(pattern, host));
        Ok(applies.then(|| input[..open].trim().to_owned()))
    } else {
        Ok(Some(input.trim().to_owned()))
    }
}

fn parse(input: &str, host: &str) -> Result<Vec<DependencyGroup>, String> {
    let mut groups = Vec::new();
    for group in input.split(',').filter(|group| !group.trim().is_empty()) {
        let alternatives = group
            .split('|')
            .map(|item| allowed_alternative(item, host))
            .collect::<Result<Vec<_>, _>>()?
            .into_iter()
            .flatten()
            .collect::<Vec<_>>();
        if !alternatives.is_empty() {
            groups.extend(parse_relationships(&alternatives.join(" | "))?);
        }
    }
    Ok(groups)
}

fn bound(constraint: Option<&VersionConstraint>, lower: bool) -> Option<(&str, bool)> {
    constraint.and_then(|constraint| match (constraint.operator, lower) {
        (VersionOperator::Equal, _) => Some((constraint.version.as_str(), true)),
        (VersionOperator::Greater, true) | (VersionOperator::Less, false) => {
            Some((constraint.version.as_str(), false))
        }
        (VersionOperator::GreaterOrEqual, true) | (VersionOperator::LessOrEqual, false) => {
            Some((constraint.version.as_str(), true))
        }
        _ => None,
    })
}

fn version_implies(left: Option<&VersionConstraint>, right: Option<&VersionConstraint>) -> bool {
    [true, false]
        .into_iter()
        .all(|lower| match (bound(left, lower), bound(right, lower)) {
            (_, None) => true,
            (None, Some(_)) => false,
            (Some((left, left_inclusive)), Some((right, right_inclusive))) => {
                let comparison = compare_versions(left, right);
                comparison
                    == if lower {
                        Ordering::Greater
                    } else {
                        Ordering::Less
                    }
                    || (comparison == Ordering::Equal && (!left_inclusive || right_inclusive))
            }
        })
}

fn term_implies(left: &Alternative, right: &Alternative) -> bool {
    left.package == right.package
        && left.architecture == right.architecture
        && version_implies(left.version.as_ref(), right.version.as_ref())
}

fn implies(left: &DependencyGroup, right: &DependencyGroup) -> bool {
    left.iter()
        .all(|left| right.iter().any(|right| term_implies(left, right)))
}

fn satisfied_by_self(term: &Alternative, package: &str, version: &str, host: &str) -> bool {
    if term.package != package
        || !match &term.architecture {
            ArchitectureQualifier::Unqualified => true,
            ArchitectureQualifier::Specific(architecture) => architecture == host,
            _ => false,
        }
    {
        return false;
    }
    term.version.as_ref().is_none_or(|constraint| {
        let comparison = compare_versions(version, &constraint.version);
        match constraint.operator {
            VersionOperator::Less => comparison == Ordering::Less,
            VersionOperator::LessOrEqual => comparison != Ordering::Greater,
            VersionOperator::Equal => comparison == Ordering::Equal,
            VersionOperator::GreaterOrEqual => comparison != Ordering::Less,
            VersionOperator::Greater => comparison == Ordering::Greater,
        }
    })
}

fn insert(groups: &mut Vec<DependencyGroup>, group: DependencyGroup, union: bool) {
    let dominates = |left: &DependencyGroup, right: &DependencyGroup| {
        if union {
            implies(right, left)
        } else {
            implies(left, right)
        }
    };
    if groups.iter().any(|old| dominates(old, &group)) {
        return;
    }
    let position = groups
        .iter()
        .position(|old| dominates(&group, old))
        .unwrap_or(groups.len());
    groups.retain(|old| !dominates(&group, old));
    groups.insert(position.min(groups.len()), group);
}

fn format_group(group: &DependencyGroup) -> String {
    group
        .iter()
        .map(|term| {
            let mut value = term.package.clone();
            match &term.architecture {
                ArchitectureQualifier::Unqualified => {}
                ArchitectureQualifier::Any => value.push_str(":any"),
                ArchitectureQualifier::Native => value.push_str(":native"),
                ArchitectureQualifier::Specific(architecture) => {
                    value.push(':');
                    value.push_str(architecture);
                }
            }
            if let Some(constraint) = &term.version {
                let operator = match constraint.operator {
                    VersionOperator::Less => "<<",
                    VersionOperator::LessOrEqual => "<=",
                    VersionOperator::Equal => "=",
                    VersionOperator::GreaterOrEqual => ">=",
                    VersionOperator::Greater => ">>",
                };
                value.push_str(&format!(" ({operator} {})", constraint.version));
            }
            value
        })
        .collect::<Vec<_>>()
        .join(" | ")
}

pub(crate) fn normalize(
    fields: &mut ControlFields,
    package: &str,
    version: &str,
    host: &str,
) -> Result<(), String> {
    let mut stronger = Vec::<DependencyGroup>::new();
    for (field, union) in [
        ("Pre-Depends", false),
        ("Depends", false),
        ("Recommends", false),
        ("Suggests", false),
        ("Enhances", true),
        ("Conflicts", true),
        ("Breaks", true),
        ("Replaces", true),
        ("Provides", true),
        ("Built-Using", true),
        ("Static-Built-Using", true),
    ] {
        let Some(value) = fields.remove(field) else {
            continue;
        };
        let mut result = Vec::new();
        for mut group in parse(&value.replace('\n', " "), host)? {
            if !union
                && (group
                    .iter()
                    .any(|term| satisfied_by_self(term, package, version, host))
                    || stronger.iter().any(|strong| implies(strong, &group)))
            {
                continue;
            }
            if matches!(
                field,
                "Conflicts"
                    | "Breaks"
                    | "Replaces"
                    | "Provides"
                    | "Built-Using"
                    | "Static-Built-Using"
            ) && group.len() != 1
            {
                return Err(format!("{field} does not support alternatives"));
            }
            if field == "Provides"
                && group.iter().any(|term| {
                    term.version
                        .as_ref()
                        .is_some_and(|version| version.operator != VersionOperator::Equal)
                })
            {
                return Err("Provides only supports exact versions".into());
            }
            if matches!(field, "Built-Using" | "Static-Built-Using")
                && group.iter().any(|term| {
                    term.version
                        .as_ref()
                        .is_none_or(|version| version.operator != VersionOperator::Equal)
                })
            {
                return Err(format!("{field} requires exact source versions"));
            }
            let mut reduced = Vec::<Alternative>::new();
            for term in group.drain(..) {
                if reduced.iter().any(|old| term_implies(&term, old)) {
                    continue;
                }
                let position = reduced
                    .iter()
                    .position(|old| term_implies(old, &term))
                    .unwrap_or(reduced.len());
                reduced.retain(|old| !term_implies(old, &term));
                reduced.insert(position.min(reduced.len()), term);
            }
            insert(&mut result, reduced, union);
        }
        if !union {
            stronger.extend(result.iter().cloned());
        }
        if !result.is_empty() {
            fields.insert(
                field.into(),
                result
                    .iter()
                    .map(format_group)
                    .collect::<Vec<_>>()
                    .join(", "),
            );
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reduces_strengthened_versions_alternatives_self_and_weaker_fields() {
        let mut fields = ControlFields::from([
            (
                "Depends".into(),
                "lib (>= 1), fixture (= 2), lib (>= 3), a | b | c, a | b, arch [arm64]".into(),
            ),
            (
                "Recommends".into(),
                "lib (>= 2), extra, arch [amd64]".into(),
            ),
        ]);
        normalize(&mut fields, "fixture", "2", "arm64").unwrap();
        assert_eq!(fields["Depends"], "lib (>= 3), a | b, arch");
        assert_eq!(fields["Recommends"], "extra");
    }
}
