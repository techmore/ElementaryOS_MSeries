//! Durable, private replacement for small per-user JSON state files.
//!
//! Keep the previous valid file intact if serialization, disk writes, or a process shutdown is
//! interrupted. All callers write into this app's own config/cache directory.

use std::fs::{self, File, OpenOptions};
use std::io::{self, ErrorKind, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

/// Atomically replace a user-state file and restrict it and its app-specific parent to owner-only
/// access on Unix. The temporary file lives beside the destination so rename remains atomic.
pub fn atomic_write(path: &Path, bytes: &[u8], mode: u32) -> io::Result<()> {
    let parent = path.parent().filter(|parent| !parent.as_os_str().is_empty()).unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(parent, fs::Permissions::from_mode(0o700))?;
    }

    let name = path.file_name().ok_or_else(|| io::Error::new(ErrorKind::InvalidInput, "state file has no name"))?;
    let mut temp = PathBuf::new();
    let mut file = None;
    for _ in 0..64 {
        let serial = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        temp = parent.join(format!(
            ".{}.tmp.{}.{}",
            name.to_string_lossy(),
            std::process::id(),
            serial
        ));
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(mode);
        }
        match options.open(&temp) {
            Ok(opened) => {
                file = Some(opened);
                break;
            }
            Err(error) if error.kind() == ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    }
    let Some(mut file) = file else {
        return Err(io::Error::new(ErrorKind::AlreadyExists, "could not allocate a unique state temp file"));
    };

    let result = (|| {
        file.write_all(bytes)?;
        file.sync_all()?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&temp, fs::Permissions::from_mode(mode))?;
        }
        fs::rename(&temp, path)?;
        File::open(parent)?.sync_all()?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}
