use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::env;
use std::error::Error;
use std::fs::{self, File, FileTimes, OpenOptions};
use std::io;
use std::os::unix::fs::{symlink, DirBuilderExt, PermissionsExt};
use std::os::unix::process::CommandExt;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, ExitCode};
use uuid::Uuid;

type AppResult<T> = Result<T, Box<dyn Error>>;

#[derive(Clone, Debug, Deserialize, Serialize)]
struct ReleaseMetadata {
    entrypoint: String,
    artifact_sha256: String,
    publisher_fingerprint: String,
    verification: String,
}

struct Store {
    path: PathBuf,
    releases: PathBuf,
    generations: PathBuf,
    _lock: File,
}

struct Staging(PathBuf);

impl Drop for Staging {
    fn drop(&mut self) {
        if self.0.exists() {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
}

fn invalid(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, message.into())
}

fn absolute_path(path: &Path) -> AppResult<PathBuf> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()?.join(path)
    };
    Ok(normalize(&absolute))
}

fn normalize(path: &Path) -> PathBuf {
    let mut result = PathBuf::new();
    for component in path.components() {
        match component {
            Component::Prefix(prefix) => result.push(prefix.as_os_str()),
            Component::RootDir => result.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => {
                if !result.pop() {
                    result.push(component.as_os_str());
                }
            }
            Component::Normal(part) => result.push(part),
        }
    }
    result
}

fn sync_directory(path: &Path) -> io::Result<()> {
    File::open(path)?.sync_all()
}

fn durable_directory(path: &Path) -> io::Result<()> {
    let mut missing = Vec::new();
    let mut cursor = path.to_path_buf();
    while !cursor.exists() {
        missing.push(cursor.clone());
        if !cursor.pop() {
            return Err(invalid(format!(
                "cannot find parent directory for {}",
                path.display()
            )));
        }
    }
    for directory in missing.into_iter().rev() {
        fs::create_dir(&directory)?;
        sync_directory(&directory)?;
        if let Some(parent) = directory.parent() {
            sync_directory(parent)?;
        }
    }
    Ok(())
}

fn valid_app(app: &str) -> bool {
    let mut bytes = app.bytes();
    matches!(bytes.next(), Some(b'a'..=b'z' | b'0'..=b'9'))
        && bytes.all(|byte| matches!(byte, b'a'..=b'z' | b'0'..=b'9' | b'.' | b'_' | b'-'))
}

fn valid_digest(digest: &str) -> bool {
    digest.len() == 64
        && digest
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn sync_tree(path: &Path) -> io::Result<()> {
    let mut entries = Vec::new();
    for entry in fs::read_dir(path)? {
        entries.push(entry?.path());
    }
    for entry in entries {
        let kind = fs::symlink_metadata(&entry)?.file_type();
        if kind.is_dir() {
            sync_tree(&entry)?;
        } else if kind.is_file() {
            File::open(&entry)?.sync_all()?;
        }
    }
    sync_directory(path)
}

fn resolve_weak(path: &Path) -> io::Result<PathBuf> {
    let mut cursor = path.to_path_buf();
    let mut suffix = Vec::new();
    while !cursor.exists() {
        if cursor.is_symlink() {
            return fs::canonicalize(cursor);
        }
        let Some(name) = cursor.file_name() else {
            return Err(invalid(format!("cannot resolve path {}", path.display())));
        };
        suffix.push(name.to_os_string());
        if !cursor.pop() {
            return Err(invalid(format!("cannot resolve path {}", path.display())));
        }
    }
    let mut resolved = fs::canonicalize(cursor)?;
    for part in suffix.into_iter().rev() {
        resolved.push(part);
    }
    Ok(normalize(&resolved))
}

fn validate_tree(source: &Path, entrypoint: &str) -> AppResult<()> {
    let relative = Path::new(entrypoint);
    if relative.is_absolute()
        || relative.components().any(|part| {
            matches!(
                part,
                Component::ParentDir | Component::RootDir | Component::Prefix(_)
            )
        })
    {
        return Err(invalid("Entrypoint must stay inside the release").into());
    }
    let mut pending = vec![source.to_path_buf()];
    while let Some(directory) = pending.pop() {
        for entry in fs::read_dir(&directory)? {
            let path = entry?.path();
            let file_type = fs::symlink_metadata(&path)?.file_type();
            if file_type.is_symlink() {
                let target = fs::read_link(&path)?;
                if target.is_absolute()
                    || !resolve_weak(&path.parent().unwrap_or(source).join(&target))?
                        .starts_with(source)
                {
                    return Err(invalid(format!(
                        "Release symlink escapes the app: {}",
                        path.display()
                    ))
                    .into());
                }
            } else if file_type.is_dir() {
                pending.push(path);
            } else if !file_type.is_file() {
                return Err(
                    invalid(format!("Unsupported release file: {}", path.display())).into(),
                );
            }
        }
    }
    let executable = source.join(relative);
    let metadata = fs::metadata(&executable)
        .map_err(|_| invalid("Release entrypoint is missing or not executable"))?;
    if !metadata.is_file() || metadata.permissions().mode() & 0o111 == 0 {
        return Err(invalid("Release entrypoint is missing or not executable").into());
    }
    Ok(())
}

fn copy_tree(source: &Path, destination: &Path) -> io::Result<()> {
    let metadata = fs::symlink_metadata(source)?;
    if metadata.file_type().is_symlink() {
        return symlink(fs::read_link(source)?, destination);
    }
    if metadata.is_dir() {
        fs::create_dir(destination)?;
        for entry in fs::read_dir(source)? {
            let entry = entry?;
            copy_tree(&entry.path(), &destination.join(entry.file_name()))?;
        }
        fs::set_permissions(destination, metadata.permissions())?;
        File::open(destination)?.set_times(
            FileTimes::new()
                .set_accessed(metadata.accessed()?)
                .set_modified(metadata.modified()?),
        )?;
        return Ok(());
    }
    fs::copy(source, destination)?;
    fs::set_permissions(destination, metadata.permissions())?;
    File::open(destination)?.set_times(
        FileTimes::new()
            .set_accessed(metadata.accessed()?)
            .set_modified(metadata.modified()?),
    )?;
    Ok(())
}

impl Store {
    fn new(root: &Path, app: &str) -> AppResult<Self> {
        if !valid_app(app) || app == "." || app == ".." {
            return Err(invalid("Invalid app identifier").into());
        }
        let unresolved = absolute_path(root)?.join(app);
        durable_directory(&unresolved)?;
        let path = fs::canonicalize(unresolved)?;
        let releases = path.join("releases");
        let generations = path.join("generations");
        durable_directory(&releases)?;
        durable_directory(&generations)?;
        let lock_path = path.join(".lock");
        let lock = OpenOptions::new()
            .create(true)
            .append(true)
            .open(lock_path)?;
        // SAFETY: flock operates on the live descriptor owned by `lock`; closing
        // that descriptor releases the process lock when Store is dropped.
        if unsafe { libc::flock(std::os::fd::AsRawFd::as_raw_fd(&lock), libc::LOCK_EX) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        Ok(Self {
            path,
            releases,
            generations,
            _lock: lock,
        })
    }

    fn selected(&self) -> AppResult<Option<PathBuf>> {
        let current = self.path.join("current");
        match fs::symlink_metadata(&current) {
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error.into()),
            Ok(metadata) if !metadata.file_type().is_symlink() => {
                return Err(invalid("Current selector must be a symlink").into())
            }
            Ok(_) => {}
        }
        let selected = fs::canonicalize(current)?;
        if selected.parent() != Some(self.generations.as_path()) {
            return Err(invalid("Current selector escapes the generation store").into());
        }
        Ok(Some(selected))
    }

    fn switch(&self, generation: &Path) -> io::Result<bool> {
        self.switch_with(generation, sync_directory)
    }

    fn switch_with<F>(&self, generation: &Path, sync: F) -> io::Result<bool>
    where
        F: FnOnce(&Path) -> io::Result<()>,
    {
        let temporary = self
            .path
            .join(format!(".current-{}", Uuid::new_v4().simple()));
        let target = generation
            .strip_prefix(&self.path)
            .map_err(|_| invalid("generation escapes the application store"))?;
        symlink(target, &temporary)?;
        if let Err(error) = fs::rename(&temporary, self.path.join("current")) {
            let _ = fs::remove_file(&temporary);
            return Err(error);
        }
        let durable = sync(&self.path).is_ok();
        let _ = fs::remove_file(temporary);
        Ok(durable)
    }

    fn deploy(
        &self,
        source: &Path,
        entrypoint: &str,
        artifact_sha256: &str,
        publisher_fingerprint: &str,
    ) -> AppResult<Value> {
        if !valid_digest(artifact_sha256) {
            return Err(invalid("A verified artifact SHA-256 is required").into());
        }
        let source = fs::canonicalize(source)?;
        if self.path.starts_with(&source) {
            return Err(invalid("Release source contains the deployment store").into());
        }
        validate_tree(&source, entrypoint)?;
        let previous = self.selected()?;
        let release_id = Uuid::new_v4().simple().to_string();
        let staging_path = self
            .path
            .join(format!(".staging-{}", Uuid::new_v4().simple()));
        let mut staging_builder = fs::DirBuilder::new();
        staging_builder.mode(0o700).create(&staging_path)?;
        let staging = Staging(staging_path.clone());
        let staged_app = staging_path.join("app");
        copy_tree(&source, &staged_app)?;
        validate_tree(&staged_app, entrypoint)?;
        let metadata = ReleaseMetadata {
            entrypoint: entrypoint.to_owned(),
            artifact_sha256: artifact_sha256.to_owned(),
            publisher_fingerprint: publisher_fingerprint.to_owned(),
            verification: "performed by calling installer".to_owned(),
        };
        let metadata_path = staging_path.join("release.json");
        fs::write(
            &metadata_path,
            format!("{}\n", serde_json::to_string_pretty(&metadata)?),
        )?;
        sync_tree(&staging_path)?;
        let release = self.releases.join(&release_id);
        fs::rename(&staging_path, &release)?;
        drop(staging);
        sync_directory(&self.releases)?;

        let generation = self.generations.join(&release_id);
        fs::create_dir(&generation)?;
        symlink(
            Path::new("../../releases").join(&release_id).join("app"),
            generation.join("app"),
        )?;
        symlink(
            Path::new("../../releases")
                .join(&release_id)
                .join("release.json"),
            generation.join("release.json"),
        )?;
        if let Some(previous) = previous {
            let previous_name = previous
                .file_name()
                .ok_or_else(|| invalid("Previous generation has no name"))?;
            symlink(
                Path::new("..").join(previous_name),
                generation.join("previous"),
            )?;
        }
        sync_directory(&generation)?;
        sync_directory(&self.generations)?;
        let durable = self.switch(&generation)?;
        let mut result = self.status()?;
        result["activation_durable"] = json!(durable);
        Ok(result)
    }

    fn rollback(&self) -> AppResult<Value> {
        let current = self
            .selected()?
            .ok_or_else(|| invalid("No previous generation is available"))?;
        let previous_link = current.join("previous");
        if !fs::symlink_metadata(&previous_link)
            .map(|metadata| metadata.file_type().is_symlink())
            .unwrap_or(false)
        {
            return Err(invalid("No previous generation is available").into());
        }
        let previous = fs::canonicalize(previous_link)?;
        if previous.parent() != Some(self.generations.as_path()) {
            return Err(invalid("Previous selector escapes the generation store").into());
        }
        let metadata: ReleaseMetadata =
            serde_json::from_slice(&fs::read(previous.join("release.json"))?)?;
        validate_tree(
            &fs::canonicalize(previous.join("app"))?,
            &metadata.entrypoint,
        )?;
        let durable = self.switch(&previous)?;
        let mut result = self.status()?;
        result["activation_durable"] = json!(durable);
        Ok(result)
    }

    fn launch(&self) -> AppResult<PathBuf> {
        let current = self
            .selected()?
            .ok_or_else(|| invalid("No release is active"))?;
        let metadata: ReleaseMetadata =
            serde_json::from_slice(&fs::read(current.join("release.json"))?)?;
        let app = fs::canonicalize(current.join("app"))?;
        let executable = fs::canonicalize(app.join(metadata.entrypoint))?;
        let permissions = fs::metadata(&executable)?.permissions().mode();
        if !executable.starts_with(&app)
            || !fs::metadata(&executable)?.is_file()
            || permissions & 0o111 == 0
        {
            return Err(invalid("Active entrypoint is invalid").into());
        }
        Ok(executable)
    }

    fn status(&self) -> AppResult<Value> {
        let Some(selected) = self.selected()? else {
            return Ok(json!({"current": null}));
        };
        let metadata: ReleaseMetadata =
            serde_json::from_slice(&fs::read(selected.join("release.json"))?)?;
        let previous = selected.join("previous");
        let previous = if fs::symlink_metadata(&previous)
            .map(|metadata| metadata.file_type().is_symlink())
            .unwrap_or(false)
        {
            fs::canonicalize(previous)?
                .file_name()
                .map(|name| name.to_string_lossy().into_owned())
        } else {
            None
        };
        Ok(json!({
            "current": selected.file_name().map(|name| name.to_string_lossy().into_owned()),
            "previous": previous,
            "launch_root": fs::canonicalize(selected.join("app"))?.to_string_lossy(),
            "entrypoint": metadata.entrypoint,
            "artifact_sha256": metadata.artifact_sha256,
            "publisher_fingerprint": metadata.publisher_fingerprint,
            "verification": metadata.verification,
        }))
    }
}

#[derive(Debug)]
enum CommandLine {
    Deploy {
        root: PathBuf,
        app: String,
        source: PathBuf,
        entrypoint: String,
        artifact_sha256: String,
        publisher_fingerprint: String,
    },
    Rollback {
        root: PathBuf,
        app: String,
    },
    Status {
        root: PathBuf,
        app: String,
    },
    Run {
        root: PathBuf,
        app: String,
        args: Vec<String>,
    },
}

fn take_value(args: &[String], index: &mut usize, option: &str) -> Result<String, String> {
    *index += 1;
    args.get(*index)
        .cloned()
        .ok_or_else(|| format!("{option} requires a value"))
}

fn parse_args(args: &[String]) -> Result<CommandLine, String> {
    let default_root = env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".local/lib/mseries-apps");
    let mut root = default_root;
    let mut app = None;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--root" => root = PathBuf::from(take_value(args, &mut index, "--root")?),
            "--app" => app = Some(take_value(args, &mut index, "--app")?),
            "deploy" | "rollback" | "status" | "run" => break,
            option => return Err(format!("unrecognized argument: {option}")),
        }
        index += 1;
    }
    let app = app.ok_or_else(|| "the following arguments are required: --app".to_owned())?;
    let command = args
        .get(index)
        .ok_or_else(|| "a command is required: deploy, rollback, status, or run".to_owned())?;
    index += 1;
    match command.as_str() {
        "deploy" => {
            let mut source = None;
            let mut entrypoint = None;
            let mut artifact_sha256 = None;
            let mut publisher_fingerprint = None;
            while index < args.len() {
                match args[index].as_str() {
                    "--source" => {
                        source = Some(PathBuf::from(take_value(args, &mut index, "--source")?))
                    }
                    "--entrypoint" => {
                        entrypoint = Some(take_value(args, &mut index, "--entrypoint")?)
                    }
                    "--artifact-sha256" => {
                        artifact_sha256 = Some(take_value(args, &mut index, "--artifact-sha256")?)
                    }
                    "--publisher-fingerprint" => {
                        publisher_fingerprint =
                            Some(take_value(args, &mut index, "--publisher-fingerprint")?)
                    }
                    option => return Err(format!("unrecognized argument: {option}")),
                }
                index += 1;
            }
            Ok(CommandLine::Deploy {
                root,
                app,
                source: source.ok_or_else(|| "--source is required".to_owned())?,
                entrypoint: entrypoint.ok_or_else(|| "--entrypoint is required".to_owned())?,
                artifact_sha256: artifact_sha256
                    .ok_or_else(|| "--artifact-sha256 is required".to_owned())?,
                publisher_fingerprint: publisher_fingerprint
                    .ok_or_else(|| "--publisher-fingerprint is required".to_owned())?,
            })
        }
        "rollback" | "status" => {
            if index < args.len() {
                return Err(format!("unrecognized argument: {}", args[index]));
            }
            Ok(if command == "rollback" {
                CommandLine::Rollback { root, app }
            } else {
                CommandLine::Status { root, app }
            })
        }
        "run" => {
            let run_args = if args.get(index).map(String::as_str) == Some("--") {
                index += 1;
                args[index..].to_vec()
            } else {
                args[index..].to_vec()
            };
            Ok(CommandLine::Run {
                root,
                app,
                args: run_args,
            })
        }
        _ => Err(format!("invalid command: {command}")),
    }
}

fn execute(command: CommandLine) -> AppResult<ExitCode> {
    let mut launch: Option<(PathBuf, Vec<String>)> = None;
    let result = match command {
        CommandLine::Deploy {
            root,
            app,
            source,
            entrypoint,
            artifact_sha256,
            publisher_fingerprint,
        } => {
            let store = Store::new(&root, &app)?;
            store.deploy(
                &source,
                &entrypoint,
                &artifact_sha256,
                &publisher_fingerprint,
            )?
        }
        CommandLine::Rollback { root, app } => {
            let store = Store::new(&root, &app)?;
            store.rollback()?
        }
        CommandLine::Status { root, app } => {
            let store = Store::new(&root, &app)?;
            store.status()?
        }
        CommandLine::Run { root, app, args } => {
            let executable = {
                let store = Store::new(&root, &app)?;
                store.launch()?
            };
            launch = Some((executable, args));
            Value::Null
        }
    };
    if let Some((executable, args)) = launch {
        let error = Command::new(&executable).args(args).exec();
        return Err(error.into());
    }
    println!("{}", serde_json::to_string_pretty(&result)?);
    if result.get("activation_durable") == Some(&Value::Bool(false)) {
        eprintln!(
            "App activated; selector durability is unconfirmed because directory sync failed."
        );
    }
    Ok(ExitCode::SUCCESS)
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().skip(1).collect();
    let command = match parse_args(&args) {
        Ok(command) => command,
        Err(error) => {
            eprintln!("atomic-app: {error}");
            return ExitCode::from(2);
        }
    };
    match execute(command) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("atomic-app: {error}");
            ExitCode::from(1)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{normalize, valid_app, valid_digest, validate_tree, Store};
    use std::fs;
    use std::io;
    use std::os::unix::fs::PermissionsExt;
    use std::path::Path;

    #[test]
    fn validates_app_ids_and_artifact_digests() {
        assert!(valid_app("signal-desktop-beta"));
        assert!(!valid_app("Signal"));
        assert!(!valid_app("../escape"));
        assert!(!valid_app(""));
        assert!(valid_digest(&"a".repeat(64)));
        assert!(!valid_digest(&"A".repeat(64)));
        assert!(!valid_digest("deadbeef"));
    }

    #[test]
    fn normalizes_paths_without_escaping_root() {
        assert_eq!(
            normalize(Path::new("/tmp/store/../apps")),
            Path::new("/tmp/apps")
        );
        assert_eq!(
            normalize(Path::new("/tmp/apps/./signal")),
            Path::new("/tmp/apps/signal")
        );
    }

    #[test]
    fn rejects_parent_entrypoint_and_non_executable_file() {
        let root = std::env::temp_dir().join(format!("mseries-atomic-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let binary = root.join("start");
        fs::write(&binary, "x").unwrap();
        fs::set_permissions(&binary, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(validate_tree(&root, "../start").is_err());
        assert!(validate_tree(&root, "start").is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn reports_post_switch_sync_failure_without_claiming_activation_failed() {
        let root = std::env::temp_dir().join(format!("mseries-atomic-sync-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        let store = Store::new(&root, "demo").unwrap();
        let generation = store.generations.join("next");
        fs::create_dir(&generation).unwrap();
        let durable = store
            .switch_with(&generation, |_| Err(io::Error::other("test sync failure")))
            .unwrap();
        assert!(!durable);
        assert_eq!(
            store.selected().unwrap().as_deref(),
            Some(generation.as_path())
        );
        drop(store);
        fs::remove_dir_all(root).unwrap();
    }
}
