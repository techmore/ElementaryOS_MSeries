use std::process::Command;

fn main() {
    let output = Command::new("pkg-config")
        .args(["--libs", "gio-2.0"])
        .output()
        .expect("pkg-config with gio-2.0 development files is required");
    assert!(
        output.status.success(),
        "gio-2.0 development files are required"
    );
    for flag in String::from_utf8(output.stdout)
        .expect("pkg-config output is UTF-8")
        .split_whitespace()
    {
        if let Some(path) = flag.strip_prefix("-L") {
            println!("cargo:rustc-link-search=native={path}");
        } else if let Some(library) = flag.strip_prefix("-l") {
            println!("cargo:rustc-link-lib={library}");
        }
    }
    println!("cargo:rerun-if-changed=build.rs");
}
