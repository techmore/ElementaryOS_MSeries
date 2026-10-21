use elementary_seed_compiler::archive::PackageCatalog;
use elementary_seed_compiler::{SeedDocument, Structure};
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::process::ExitCode;

fn usage() {
    eprintln!("Usage:\n  elementary-seed-compiler inspect-seed <file> <architecture>\n  elementary-seed-compiler inspect-structure <file> <collection> <seed> [included-collection=STRUCTURE ...]\n  elementary-seed-compiler resolve-seed <STRUCTURE> <collection> <seed> <architecture> [included-collection=SEED-DIR ...]\n  elementary-seed-compiler resolve-seed-packages <STRUCTURE> <collection> <seed> <architecture> <Packages-file> [--follow-recommends] [included-collection=SEED-DIR ...]\n  elementary-seed-compiler expand-source <Packages-file> <architecture> <source ...>\n  elementary-seed-compiler resolve-packages <Packages-file> <architecture> [--follow-recommends] <root-package ...>");
}

fn run() -> Result<(), String> {
    let args: Vec<String> = env::args().collect();
    match args.get(1).map(String::as_str) {
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
            let structure_path = &args[2];
            let local_text =
                fs::read_to_string(structure_path).map_err(|e| format!("{structure_path}: {e}"))?;
            let local = Structure::parse(&local_text).map_err(|e| e.to_string())?;
            let root_dir = std::path::Path::new(structure_path)
                .parent()
                .ok_or_else(|| "STRUCTURE path has no parent directory".to_owned())?;
            let mut available = BTreeMap::new();
            let mut directories = vec![root_dir.to_path_buf()];
            for item in &args[6..] {
                let (name, directory) = item.split_once('=').ok_or_else(|| {
                    format!("invalid included collection `{item}`; expected NAME=SEED-DIR")
                })?;
                let directory = std::path::PathBuf::from(directory);
                let include_path = directory.join("STRUCTURE");
                let include_text = fs::read_to_string(&include_path)
                    .map_err(|e| format!("{}: {e}", include_path.display()))?;
                let included = Structure::parse(&include_text)
                    .map_err(|e| format!("{}: {e}", include_path.display()))?;
                available.insert(name.to_owned(), included);
                directories.push(directory);
            }
            let structure = Structure::with_includes(&args[3], &local, &available)?;
            let mut documents = BTreeMap::new();
            for seed_name in structure.seeds.keys() {
                let paths: Vec<_> = directories
                    .iter()
                    .map(|directory| directory.join(seed_name))
                    .filter(|path| path.is_file())
                    .collect();
                if paths.len() != 1 {
                    return Err(format!(
                        "expected exactly one file for seed `{seed_name}` across supplied collections; found {}",
                        paths.len()
                    ));
                }
                let path = &paths[0];
                let text =
                    fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
                let document =
                    SeedDocument::parse(&text).map_err(|e| format!("{}: {e}", path.display()))?;
                documents.insert(seed_name.clone(), document);
            }
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
            let structure_path = &args[2];
            let local_text =
                fs::read_to_string(structure_path).map_err(|e| format!("{structure_path}: {e}"))?;
            let local = Structure::parse(&local_text).map_err(|e| e.to_string())?;
            let root_dir = std::path::Path::new(structure_path)
                .parent()
                .ok_or_else(|| "STRUCTURE path has no parent directory".to_owned())?;
            let mut available = BTreeMap::new();
            let mut directories = vec![root_dir.to_path_buf()];
            let follow_recommends = args[7..].iter().any(|arg| arg == "--follow-recommends");
            for item in args[7..]
                .iter()
                .filter(|arg| arg.as_str() != "--follow-recommends")
            {
                let (name, directory) = item.split_once('=').ok_or_else(|| {
                    format!("invalid included collection `{item}`; expected NAME=SEED-DIR")
                })?;
                let directory = std::path::PathBuf::from(directory);
                let include_path = directory.join("STRUCTURE");
                let include_text = fs::read_to_string(&include_path)
                    .map_err(|e| format!("{}: {e}", include_path.display()))?;
                let included = Structure::parse(&include_text)
                    .map_err(|e| format!("{}: {e}", include_path.display()))?;
                available.insert(name.to_owned(), included);
                directories.push(directory);
            }
            let structure = Structure::with_includes(&args[3], &local, &available)?;
            let mut documents = BTreeMap::new();
            for seed_name in structure.seeds.keys() {
                let paths: Vec<_> = directories
                    .iter()
                    .map(|directory| directory.join(seed_name))
                    .filter(|path| path.is_file())
                    .collect();
                if paths.len() != 1 {
                    return Err(format!(
                        "expected exactly one file for seed `{seed_name}` across supplied collections; found {}",
                        paths.len()
                    ));
                }
                let path = &paths[0];
                let text =
                    fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
                let document =
                    SeedDocument::parse(&text).map_err(|e| format!("{}: {e}", path.display()))?;
                documents.insert(seed_name.clone(), document);
            }
            let resolved = structure.resolve_seed(&args[4], &args[5], &documents)?;
            let package_text =
                fs::read_to_string(&args[6]).map_err(|e| format!("{}: {e}", args[6]))?;
            let catalog = PackageCatalog::parse_packages(&package_text)
                .map_err(|e| format!("{}: {e}", args[6]))?;
            let roots = elementary_seed_compiler::archive::expand_resolved_seed(
                &resolved, &catalog, &args[5],
            )?;
            let closure =
                catalog.resolve_seed_package_closure(&roots, &args[5], follow_recommends)?;
            for package in &roots.depends {
                println!("root\tdepends\t{package}");
            }
            for package in &roots.recommends {
                println!("root\trecommends\t{package}");
            }
            for snap in &roots.snaps {
                println!("snap\t{snap}");
            }
            for package in closure.packages {
                println!("package\t{}\t{}", package.package, package.architecture);
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

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("elementary-seed-compiler: {error}");
            ExitCode::FAILURE
        }
    }
}
