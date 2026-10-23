//! `msdk check [--json] <file.ui.json>...`, `msdk schema`, `msdk components`, `msdk tokens [--json]`.

use std::process::ExitCode;

use msdk::{Severity, check, schema, tokens, vocabulary};

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("components") => print_json(&vocabulary()),
        Some("schema") => print_json(&schema::schema()),
        Some("tokens") if args.get(1).map(String::as_str) == Some("--json") => print_json(&tokens::tokens()),
        Some("tokens") => {
            print!("{}", tokens::css());
            ExitCode::SUCCESS
        }
        Some("check") if args.len() > 1 => run_check(&args[1..]),
        _ => {
            eprintln!(
                "usage: msdk check [--json] <file.ui.json>...\n       msdk schema | components | tokens [--json]"
            );
            ExitCode::from(2)
        }
    }
}

fn print_json(v: &serde_json::Value) -> ExitCode {
    println!("{}", serde_json::to_string_pretty(v).unwrap_or_default());
    ExitCode::SUCCESS
}

fn run_check(args: &[String]) -> ExitCode {
    let json = args.iter().any(|a| a == "--json");
    let mut failed = false;
    let mut report = Vec::new();
    for file in args.iter().filter(|a| *a != "--json") {
        let doc = match std::fs::read_to_string(file)
            .map_err(|e| e.to_string())
            .and_then(|t| serde_json::from_str(&t).map_err(|e| format!("line {}: {e}", e.line())))
        {
            Ok(v) => v,
            Err(e) => {
                failed = true;
                if json {
                    report.push(
                        serde_json::json!({ "file": file, "severity": "error", "code": "bad-json", "message": e }),
                    );
                } else {
                    println!("{file}: error[bad-json] {e}");
                }
                continue;
            }
        };
        let diags = check(&doc);
        failed |= diags.iter().any(|d| d.severity == Severity::Error);
        for d in &diags {
            if json {
                let mut o = d.to_json();
                o["file"] = file.clone().into();
                report.push(o);
            } else {
                println!("{file}: {d}");
            }
        }
        if !json && !diags.iter().any(|d| d.severity == Severity::Error) {
            println!("{file}: ok ({} warning(s))", diags.len());
        }
    }
    if json {
        println!("{}", serde_json::to_string_pretty(&report).unwrap_or_default());
    }
    if failed { ExitCode::FAILURE } else { ExitCode::SUCCESS }
}
