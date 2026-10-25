use elementary_seed_compiler::archive::PackageCatalog;
use elementary_seed_compiler::metapackage::MetapackageMap;
use elementary_seed_compiler::metapackage_lists::{parse_bootstrap_packages, UpdatePlan};
use elementary_seed_compiler::{SeedDocument, Structure};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::process::ExitCode;

fn usage() {
    eprintln!(
        r#"Usage:
  elementary-seed-compiler generate-metapackage-lists <source-directory> <STRUCTURE> <collection> <index-directory> <new-output-directory> [--dist=NAME] [included-collection=SEED-DIR ...]
  elementary-seed-compiler metapackage-substvars <package-list-directory> <binary-architecture> <package>
  elementary-seed-compiler inspect-seed <file> <architecture>
  elementary-seed-compiler inspect-structure <file> <collection> <seed> [included-collection=STRUCTURE ...]
  elementary-seed-compiler resolve-seed <STRUCTURE> <collection> <seed> <architecture> [included-collection=SEED-DIR ...]
  elementary-seed-compiler resolve-seed-packages <STRUCTURE> <collection> <seed> <architecture> <Packages-file> [--follow-recommends] [included-collection=SEED-DIR ...]
  elementary-seed-compiler expand-source <Packages-file> <architecture> <source ...>
  elementary-seed-compiler resolve-packages <Packages-file> <architecture> [--follow-recommends] <root-package ...>"#
    );
}

fn run() -> Result<(), String> {
    let args: Vec<String> = env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("generate-metapackage-lists") if args.len() >= 7 => {
            let source = std::path::Path::new(&args[2]);
            let read = |path: &std::path::Path| {
                fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))
            };
            let distributions = args[7..]
                .iter()
                .filter_map(|arg| arg.strip_prefix("--dist="))
                .collect::<Vec<_>>();
            if distributions.len() > 1 {
                return Err("only one --dist may be supplied".into());
            }
            let includes = args[7..]
                .iter()
                .filter(|arg| !arg.starts_with("--dist="))
                .cloned()
                .collect::<Vec<_>>();
            let plan = UpdatePlan::parse(
                &read(&source.join("debian/control"))?,
                &read(&source.join("update.cfg"))?,
                distributions.first().copied(),
            )?;
            let (structure, documents) = load_seeds(&args[3], &args[4], &includes)?;
            let indices = std::path::Path::new(&args[5]);
            let mut catalogs = BTreeMap::new();
            let mut bootstrap = BTreeMap::new();
            for architecture in &plan.architectures {
                let path = indices.join(format!("Packages-{architecture}"));
                let catalog = PackageCatalog::parse_packages(&read(&path)?)
                    .map_err(|error| format!("{}: {error}", path.display()))?;
                let path = indices.join(format!("Sources-{architecture}"));
                catalogs.insert(
                    architecture.clone(),
                    catalog
                        .with_sources(&read(&path)?)
                        .map_err(|error| format!("{}: {error}", path.display()))?,
                );
                let path = indices.join(format!("debootstrap-{architecture}"));
                bootstrap.insert(
                    architecture.clone(),
                    parse_bootstrap_packages(&read(&path)?)?,
                );
            }
            let files = plan.render_files(&structure, &documents, &catalogs, &bootstrap)?;
            let output = std::path::Path::new(&args[6]);
            fs::create_dir(output).map_err(|error| format!("{}: {error}", output.display()))?;
            for (name, contents) in files {
                let path = output.join(&name);
                fs::write(&path, contents)
                    .map_err(|error| format!("{}: {error}", path.display()))?;
                println!("generated\t{name}");
            }
            Ok(())
        }
        Some("metapackage-substvars") if args.len() == 5 => {
            let directory = std::path::Path::new(&args[2]);
            let path = directory.join("metapackage-map");
            let text = fs::read_to_string(&path)
                .map_err(|error| format!("{}: {error}", path.display()))?;
            let map = MetapackageMap::parse(&text)
                .map_err(|error| format!("{}: {error}", path.display()))?;
            print!("{}", map.render_for(directory, &args[3], &args[4])?);
            Ok(())
        }
        Some("inspect-seed") if args.len() == 4 => {
            let text = fs::read_to_string(&args[2]).map_err(|e| format!("{}: {e}", args[2]))?;
            let seed = SeedDocument::parse(&text).map_err(|e| e.to_string())?;
            let arch = &args[3];
            println!("seed-file\t{}", args[2]);
            for (key, value) in seed.headers {
                println!("header\t{key}\t{value}");
            }
            for feature in seed.features {
                println!("feature\t{feature}");
            }
            for entry in seed
                .entries
                .into_iter()
                .filter(|entry| entry.architectures.applies_to(arch))
            {
                println!(
                    "entry\t{:?}\t{}\trecommended={}",
                    entry.kind, entry.name, entry.recommended
                );
            }
            Ok(())
        }
        Some("inspect-structure") if args.len() >= 5 => {
            let text = fs::read_to_string(&args[2]).map_err(|e| format!("{}: {e}", args[2]))?;
            let local = Structure::parse(&text).map_err(|e| e.to_string())?;
            let mut available = BTreeMap::new();
            for item in &args[5..] {
                let (name, path) = item.split_once('=').ok_or_else(|| {
                    format!("invalid included collection `{item}`; expected NAME=STRUCTURE")
                })?;
                let included_text = fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
                let included =
                    Structure::parse(&included_text).map_err(|e| format!("{path}: {e}"))?;
                available.insert(name.to_owned(), included);
            }
            let structure = Structure::with_includes(&args[3], &local, &available)?;
            for feature in &structure.features {
                println!("feature\t{feature}");
            }
            for seed in structure.inheritance_order(&args[4])? {
                println!("seed\t{seed}");
            }
            Ok(())
        }
        Some("resolve-seed") if args.len() >= 6 => {
            let (structure, documents) = load_seeds(&args[2], &args[3], &args[6..])?;
            let entries = structure.resolve_seed_entries(&args[4], &args[5], &documents)?;
            for entry in entries {
                println!(
                    "entry\t{:?}\t{}\trecommended={}",
                    entry.kind, entry.name, entry.recommended
                );
            }
            Ok(())
        }
        Some("resolve-seed-packages") if args.len() >= 7 => {
            let force_follow_recommends = args[7..].iter().any(|arg| arg == "--follow-recommends");
            let includes = args[7..]
                .iter()
                .filter(|arg| arg.as_str() != "--follow-recommends")
                .cloned()
                .collect::<Vec<_>>();
            let (structure, documents) = load_seeds(&args[2], &args[3], &includes)?;
            let groups = structure.resolve_seed_groups(&args[4], &args[5], &documents)?;
            let package_text =
                fs::read_to_string(&args[6]).map_err(|e| format!("{}: {e}", args[6]))?;
            let catalog = PackageCatalog::parse_packages(&package_text)
                .map_err(|e| format!("{}: {e}", args[6]))?;
            let mut roots = elementary_seed_compiler::archive::SeedPackageRoots::default();
            let mut packages = BTreeSet::new();
            let mut recommended_packages = BTreeSet::new();
            for (name, resolved) in groups {
                let follow_recommends =
                    structure.follows_recommends(&name, &documents, force_follow_recommends)?;
                let seed_roots = elementary_seed_compiler::archive::expand_resolved_seed(
                    &resolved, &catalog, &args[5],
                )?;
                packages.extend(
                    catalog
                        .resolve_seed_package_closure(&seed_roots, &args[5], follow_recommends)?
                        .packages,
                );
                recommended_packages.extend(
                    catalog
                        .resolve_seed_recommendation_closure(
                            &seed_roots,
                            &args[5],
                            follow_recommends,
                        )?
                        .packages,
                );
                roots.depends.extend(seed_roots.depends);
                roots.recommends.extend(seed_roots.recommends);
                roots.snaps.extend(seed_roots.snaps);
            }
            roots
                .recommends
                .retain(|package| !roots.depends.contains(package));
            recommended_packages.retain(|package| !packages.contains(package));
            for package in &roots.depends {
                println!("root\tdepends\t{package}");
            }
            for package in &roots.recommends {
                println!("root\trecommends\t{package}");
            }
            for snap in &roots.snaps {
                println!("snap\t{snap}");
            }
            for package in packages {
                println!("package\t{}\t{}", package.package, package.architecture);
            }
            for package in recommended_packages {
                println!(
                    "recommended-package\t{}\t{}",
                    package.package, package.architecture
                );
            }
            Ok(())
        }
        Some("expand-source") if args.len() >= 5 => {
            let text = fs::read_to_string(&args[2]).map_err(|e| format!("{}: {e}", args[2]))?;
            let catalog = PackageCatalog::parse_packages(&text).map_err(|e| e.to_string())?;
            let mut binaries = Vec::new();
            for source in &args[4..] {
                binaries.extend(catalog.source_binaries(source, &args[3]));
            }
            binaries.sort();
            binaries.dedup();
            for binary in binaries {
                println!("binary\t{binary}");
            }
            Ok(())
        }
        Some("resolve-packages") if args.len() >= 5 => {
            let text = fs::read_to_string(&args[2]).map_err(|e| format!("{}: {e}", args[2]))?;
            let catalog = PackageCatalog::parse_packages(&text).map_err(|e| e.to_string())?;
            let follow_recommends = args[4..].iter().any(|arg| arg == "--follow-recommends");
            let roots: Vec<String> = args[4..]
                .iter()
                .filter(|arg| arg.as_str() != "--follow-recommends")
                .cloned()
                .collect();
            if roots.is_empty() {
                return Err("resolve-packages requires at least one root package".into());
            }
            let closure = catalog.dependency_closure(&roots, &args[3], follow_recommends)?;
            for package in closure.packages {
                println!("package\t{}\t{}", package.package, package.architecture);
            }
            Ok(())
        }
        _ => {
            usage();
            Err("invalid arguments".into())
        }
    }
}

fn load_seeds(
    structure_path: &str,
    collection: &str,
    includes: &[String],
) -> Result<(Structure, BTreeMap<String, SeedDocument>), String> {
    let text =
        fs::read_to_string(structure_path).map_err(|error| format!("{structure_path}: {error}"))?;
    let local = Structure::parse(&text).map_err(|error| format!("{structure_path}: {error}"))?;
    let directory = std::path::Path::new(structure_path)
        .parent()
        .ok_or("STRUCTURE path has no parent directory")?;
    let mut directories = vec![directory.to_path_buf()];
    let mut available = BTreeMap::new();
    for item in includes {
        let (name, directory) = item.split_once('=').ok_or_else(|| {
            format!("invalid included collection `{item}`; expected NAME=SEED-DIR")
        })?;
        let directory = std::path::PathBuf::from(directory);
        let path = directory.join("STRUCTURE");
        let text =
            fs::read_to_string(&path).map_err(|error| format!("{}: {error}", path.display()))?;
        let included =
            Structure::parse(&text).map_err(|error| format!("{}: {error}", path.display()))?;
        if available.insert(name.to_owned(), included).is_some() {
            return Err(format!("included collection `{name}` was supplied twice"));
        }
        directories.push(directory);
    }
    let structure = Structure::with_includes(collection, &local, &available)?;
    let mut documents = BTreeMap::new();
    for seed in structure.seeds.keys() {
        let paths = directories
            .iter()
            .map(|directory| directory.join(seed))
            .filter(|path| path.is_file())
            .collect::<Vec<_>>();
        if paths.len() != 1 {
            return Err(format!(
                "expected exactly one file for seed `{seed}` across supplied collections; found {}",
                paths.len()
            ));
        }
        let path = &paths[0];
        let text =
            fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
        let document =
            SeedDocument::parse(&text).map_err(|error| format!("{}: {error}", path.display()))?;
        documents.insert(seed.clone(), document);
    }
    Ok((structure, documents))
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("elementary-seed-compiler: {error}");
            ExitCode::FAILURE
        }
    }
}
