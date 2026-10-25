use mseries_iso_label::volume_label;
use std::env;
use std::process::ExitCode;

fn main() -> ExitCode {
    let mut args = env::args().skip(1);
    let (Some(profile), Some(arch), None) = (args.next(), args.next(), args.next()) else {
        eprintln!("usage: mseries-iso-label PROFILE ARCH");
        return ExitCode::from(2);
    };
    println!("{}", volume_label(&profile, &arch));
    ExitCode::SUCCESS
}
