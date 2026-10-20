use std::env;
use std::error::Error;
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::PathBuf;
use std::process::ExitCode;

type Result<T> = std::result::Result<T, Box<dyn Error>>;

const DESKTOP_ENTRY: &str = "[Desktop Entry]\n\
Type=Application\n\
Name=Homeboard\n\
Comment=Open the household project board\n\
Exec=xdg-open https://tasks.stoverparc.org/board/\n\
Icon=io.elementary.tasks\n\
Terminal=false\n\
Categories=Office;ProjectManagement;\n";

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("mseries-homeboard-launcher: {error}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<()> {
    if env::args_os().len() != 1 {
        return Err("usage: mseries-homeboard-launcher".into());
    }
    let home = PathBuf::from(env::var_os("HOME").ok_or("HOME must be set")?);
    let applications = home.join(".local/share/applications");
    fs::create_dir_all(&applications)?;
    let launcher = applications.join("org.techmore.HomeboardBoard.desktop");
    fs::write(&launcher, DESKTOP_ENTRY)?;
    fs::set_permissions(&launcher, fs::Permissions::from_mode(0o644))?;
    println!("Installed Homeboard launcher in {}", applications.display());
    println!("The board requires Google sign-in. The separate Tasks sync bridge needs Evolution Data Server packages.");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::DESKTOP_ENTRY;

    #[test]
    fn desktop_entry_keeps_the_existing_launch_contract() {
        assert!(DESKTOP_ENTRY.contains("Name=Homeboard\n"));
        assert!(DESKTOP_ENTRY.contains("Exec=xdg-open https://tasks.stoverparc.org/board/\n"));
        assert!(DESKTOP_ENTRY.contains("Icon=io.elementary.tasks\n"));
        assert!(DESKTOP_ENTRY.contains("Categories=Office;ProjectManagement;\n"));
    }
}
