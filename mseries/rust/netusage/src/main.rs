//! Rust candidate for `mseries/netspeed/netusage/netusage.py`.
//!
//! The SQLite schema and system command contracts intentionally match the Python
//! service. SQLite is accessed through its CLI so this crate does not carry an
//! unsafe FFI boundary; values are SQL-quoted before they enter a transaction.

use regex::Regex;
use serde_json::Value;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::env;
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::IpAddr;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const POLL_SECONDS: u64 = 5;
const IDLE_FORCE_SECONDS: u64 = 30;
const IDLE_BYTES: u64 = 512;
const FLUSH_SECONDS: u64 = 15;
const CACHE_REFRESH_SECONDS: u64 = 600;
const MINUTE_RETENTION: u64 = 2 * 86_400;
const HOUR_RETENTION: u64 = 90 * 86_400;
const SCHEMA: &str = "CREATE TABLE IF NOT EXISTS usage_minute (ts INTEGER NOT NULL, proc TEXT NOT NULL, host TEXT NOT NULL, rx INTEGER NOT NULL DEFAULT 0, tx INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (ts, proc, host)) WITHOUT ROWID;\nCREATE TABLE IF NOT EXISTS usage_hour (ts INTEGER NOT NULL, proc TEXT NOT NULL, host TEXT NOT NULL, rx INTEGER NOT NULL DEFAULT 0, tx INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (ts, proc, host)) WITHOUT ROWID;\nCREATE TABLE IF NOT EXISTS dns_hour (ts INTEGER NOT NULL, name TEXT NOT NULL, queries INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (ts, name)) WITHOUT ROWID;\nCREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);\n";

static STOP: AtomicBool = AtomicBool::new(false);

// POSIX only permits async-signal-safe work in a signal handler. A relaxed atomic
// store is the sole operation; all cleanup and flushing stays in the main thread.
extern "C" fn request_stop(_: libc::c_int) {
    STOP.store(true, Ordering::Relaxed);
}

fn install_signal_handlers() {
    // SAFETY: `request_stop` has C ABI, does only an atomic store, and is valid for
    // process lifetime. We use sigaction with an empty mask and default flags.
    unsafe {
        let mut action: libc::sigaction = std::mem::zeroed();
        action.sa_sigaction = request_stop as *const () as usize;
        action.sa_flags = 0;
        libc::sigemptyset(&mut action.sa_mask);
        libc::sigaction(libc::SIGTERM, &action, std::ptr::null_mut());
        libc::sigaction(libc::SIGINT, &action, std::ptr::null_mut());
    }
}

fn log(message: impl AsRef<str>) {
    eprintln!("{}", message.as_ref());
}

fn unix_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn db_path() -> PathBuf {
    if let Some(root) = env::var_os("XDG_DATA_HOME") {
        PathBuf::from(root).join("netusage/usage.db")
    } else {
        env::var_os("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".local/share/netusage/usage.db")
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct SocketUsage {
    proc_name: String,
    remote_ip: String,
    rx: u64,
    tx: u64,
}

fn socket_patterns() -> (Regex, Regex, Regex) {
    (
        Regex::new(r#"\("([^\"]*)",pid=(\d+)"#).unwrap(),
        Regex::new(r"\bbytes_sent:(\d+)").unwrap(),
        Regex::new(r"\bbytes_received:(\d+)").unwrap(),
    )
}

fn process_name(pid: u32, comm: &str, cache: &mut HashMap<u32, (String, String)>) -> String {
    if let Some((old_comm, name)) = cache.get(&pid) {
        if old_comm == comm {
            return name.clone();
        }
    }
    let generic: HashSet<&str> = [
        "python", "python3", "node", "nodejs", "ruby", "perl", "java", "bash", "sh", "deno", "bun",
    ]
    .into_iter()
    .collect();
    let mut name = comm.to_owned();
    if generic.contains(comm.to_lowercase().as_str()) {
        if let Ok(mut file) = fs::File::open(format!("/proc/{pid}/cmdline")) {
            let mut bytes = Vec::new();
            if file.read_to_end(&mut bytes).is_ok() {
                let args = bytes.split(|b| *b == 0).skip(1);
                for arg in args {
                    let arg = String::from_utf8_lossy(arg);
                    if !arg.is_empty() && !arg.starts_with('-') {
                        name = Path::new(arg.as_ref())
                            .file_name()
                            .and_then(|s| s.to_str())
                            .unwrap_or(arg.as_ref())
                            .to_owned();
                        break;
                    }
                }
            }
        }
    }
    if cache.len() > 4096 {
        cache.clear();
    }
    cache.insert(pid, (comm.to_owned(), name.clone()));
    name
}

fn split_host_port(peer: &str) -> (&str, &str) {
    match peer.rsplit_once(':') {
        Some((host, port)) => (host.trim_start_matches('[').trim_end_matches(']'), port),
        None => (peer, ""),
    }
}

fn is_loopback(host: &str) -> bool {
    let unscoped = host.split('%').next().unwrap_or(host);
    unscoped.parse::<IpAddr>().is_ok_and(|ip| ip.is_loopback())
}

fn parse_sockets(
    output: &str,
    names: &mut HashMap<u32, (String, String)>,
) -> HashMap<(String, String), SocketUsage> {
    let (users_re, sent_re, recv_re) = socket_patterns();
    let mut result = HashMap::new();
    for line in output.lines() {
        let fields: Vec<&str> = line.split_whitespace().take(5).collect();
        if fields.len() < 5 {
            continue;
        }
        let local = fields[3];
        let peer = fields[4];
        let rest = line
            .split_whitespace()
            .take(5)
            .collect::<Vec<_>>()
            .join(" ");
        let rest = line
            .find(&rest)
            .map(|offset| &line[offset + rest.len()..])
            .unwrap_or("")
            .trim();
        let rx = recv_re.captures(rest).and_then(|m| m[1].parse().ok());
        let tx = sent_re.captures(rest).and_then(|m| m[1].parse().ok());
        if rx.is_none() && tx.is_none() {
            continue;
        }
        let (remote_ip, _) = split_host_port(peer);
        if is_loopback(remote_ip) {
            continue;
        }
        let proc_name = users_re
            .captures(rest)
            .and_then(|m| {
                let pid = m[2].parse::<u32>().ok()?;
                Some(process_name(pid, &m[1], names))
            })
            .unwrap_or_else(|| "(other)".to_owned());
        result.insert(
            (local.to_owned(), peer.to_owned()),
            SocketUsage {
                proc_name,
                remote_ip: remote_ip.to_owned(),
                rx: rx.unwrap_or(0),
                tx: tx.unwrap_or(0),
            },
        );
    }
    result
}

fn normalize_dns_name(name: &str) -> String {
    name.to_lowercase().trim_end_matches('.').to_owned()
}

fn ignored_name(name: &str) -> bool {
    name == "localhost" || name.ends_with(".arpa") || name.ends_with(".localhost")
}

fn addr_from_json(value: &Value) -> Option<String> {
    let bytes = value.as_array()?;
    let raw: Vec<u8> = bytes
        .iter()
        .map(|v| v.as_u64().and_then(|n| u8::try_from(n).ok()))
        .collect::<Option<_>>()?;
    match raw.len() {
        4 => Some(std::net::Ipv4Addr::new(raw[0], raw[1], raw[2], raw[3]).to_string()),
        16 => Some(std::net::Ipv6Addr::from(<[u8; 16]>::try_from(raw).ok()?).to_string()),
        _ => None,
    }
}

fn learn_answers(
    name: &str,
    answers: Option<&Value>,
    ip_names: &mut HashMap<String, String>,
    overwrite: bool,
) {
    let Some(entries) = answers.and_then(Value::as_array) else {
        return;
    };
    for entry in entries {
        let address = entry
            .get("rr")
            .and_then(|v| v.get("address"))
            .and_then(addr_from_json);
        if let Some(ip) = address {
            if overwrite {
                ip_names.insert(ip, name.to_owned());
            } else {
                ip_names.entry(ip).or_insert_with(|| name.to_owned());
            }
        }
    }
}

#[derive(Default)]
struct Pending {
    usage: BTreeMap<(u64, String, String), (u64, u64)>,
    dns: BTreeMap<(u64, String), (u64, u64)>,
    ip_names: HashMap<String, String>,
}

fn add_usage(pending: &mut Pending, ts: u64, process: String, host: String, rx: u64, tx: u64) {
    let value = pending.usage.entry((ts, process, host)).or_default();
    value.0 = value.0.saturating_add(rx);
    value.1 = value.1.saturating_add(tx);
}

fn add_dns(pending: &mut Pending, hour: u64, name: String, failed: bool) {
    let value = pending.dns.entry((hour, name)).or_default();
    value.0 = value.0.saturating_add(1);
    if failed {
        value.1 = value.1.saturating_add(1);
    }
}

fn run_command(program: &str, args: &[&str], timeout: u64) -> Result<std::process::Output, String> {
    let mut command = Command::new("timeout");
    command.arg(format!("{timeout}s")).arg(program).args(args);
    command.output().map_err(|e| e.to_string())
}

fn read_sockets(
    names: &mut HashMap<u32, (String, String)>,
) -> HashMap<(String, String), SocketUsage> {
    match run_command("ss", &["-tinpHO"], 10) {
        Ok(output) => parse_sockets(&String::from_utf8_lossy(&output.stdout), names),
        Err(error) => {
            log(format!("ss failed: {error}"));
            HashMap::new()
        }
    }
}

fn load_cache_dump(pending: &Arc<Mutex<Pending>>) {
    let output = run_command(
        "resolvectl",
        &["--no-ask-password", "show-cache", "--json=short"],
        10,
    );
    let parsed = output
        .ok()
        .and_then(|o| serde_json::from_slice::<Value>(&o.stdout).ok());
    let Some(links) = parsed.and_then(|v| v.as_array().cloned()) else {
        log("cache dump failed: invalid or unavailable JSON");
        return;
    };
    if let Ok(mut state) = pending.lock() {
        for link in links {
            let Some(cache) = link.get("cache").and_then(Value::as_array) else {
                continue;
            };
            for item in cache {
                let name = item
                    .get("key")
                    .and_then(|v| v.get("name"))
                    .and_then(Value::as_str);
                let Some(name) = name else {
                    continue;
                };
                let name = normalize_dns_name(name);
                if let Some(rrs) = item.get("rrs").and_then(Value::as_array) {
                    for rr in rrs {
                        learn_answers(
                            &name,
                            Some(&Value::Array(vec![rr.clone()])),
                            &mut state.ip_names,
                            false,
                        );
                    }
                }
            }
        }
    }
}

fn dns_monitor(pending: Arc<Mutex<Pending>>) {
    let mut recent_a: HashMap<String, u64> = HashMap::new();
    while !STOP.load(Ordering::Relaxed) {
        let child = Command::new("resolvectl")
            .args(["--no-ask-password", "monitor", "--json=short"])
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn();
        let mut child = match child {
            Ok(child) => child,
            Err(error) => {
                log(format!("cannot start resolvectl monitor: {error}"));
                wait_or_stop(30);
                continue;
            }
        };
        if let Some(stdout) = child.stdout.take() {
            for line in BufReader::new(stdout).lines() {
                if STOP.load(Ordering::Relaxed) {
                    break;
                }
                let Ok(line) = line else {
                    break;
                };
                let Ok(message) = serde_json::from_str::<Value>(&line) else {
                    continue;
                };
                let Some(question) = message
                    .get("question")
                    .and_then(Value::as_array)
                    .and_then(|q| q.first())
                else {
                    continue;
                };
                let name = question
                    .get("name")
                    .and_then(Value::as_str)
                    .map(normalize_dns_name)
                    .unwrap_or_default();
                if name.is_empty() || ignored_name(&name) {
                    continue;
                }
                let qtype = question.get("type").and_then(Value::as_u64).unwrap_or(0);
                let ok = message.get("state").and_then(Value::as_str) == Some("success");
                let now = unix_seconds();
                if let Ok(mut state) = pending.lock() {
                    if ok {
                        learn_answers(&name, message.get("answer"), &mut state.ip_names, true);
                    }
                    let count = match qtype {
                        1 => {
                            recent_a.insert(name.clone(), now);
                            true
                        }
                        28 => now.saturating_sub(*recent_a.get(&name).unwrap_or(&0)) > 3,
                        _ => false,
                    };
                    if count {
                        add_dns(&mut state, now / 3600 * 3600, name, !ok);
                    }
                }
                if recent_a.len() > 2048 {
                    recent_a.clear();
                }
            }
        }
        let _ = child.kill();
        let _ = child.wait();
        if !STOP.load(Ordering::Relaxed) {
            wait_or_stop(10);
        }
    }
}

fn wait_or_stop(seconds: u64) {
    for _ in 0..seconds {
        if STOP.load(Ordering::Relaxed) {
            break;
        }
        thread::sleep(Duration::from_secs(1));
    }
}

struct Sampler {
    previous: Option<HashMap<(String, String), SocketUsage>>,
    names: HashMap<u32, (String, String)>,
}

impl Sampler {
    fn new() -> Self {
        Self {
            previous: None,
            names: HashMap::new(),
        }
    }
    fn poll(&mut self, pending: &Arc<Mutex<Pending>>) {
        let current = read_sockets(&mut self.names);
        let minute = unix_seconds() / 60 * 60;
        if let Some(previous) = &self.previous {
            if let Ok(mut state) = pending.lock() {
                for (key, socket) in &current {
                    let old = previous.get(key);
                    let (mut rx, mut tx) =
                        if old.is_none_or(|old| old.proc_name != socket.proc_name) {
                            (socket.rx, socket.tx)
                        } else {
                            (
                                socket.rx.saturating_sub(old.unwrap().rx),
                                socket.tx.saturating_sub(old.unwrap().tx),
                            )
                        };
                    if old.is_some_and(|old| socket.rx < old.rx || socket.tx < old.tx) {
                        rx = socket.rx;
                        tx = socket.tx;
                    }
                    if rx != 0 || tx != 0 {
                        let host = state
                            .ip_names
                            .get(&socket.remote_ip)
                            .cloned()
                            .unwrap_or_else(|| socket.remote_ip.clone());
                        add_usage(&mut state, minute, socket.proc_name.clone(), host, rx, tx);
                    }
                }
            }
        }
        self.previous = Some(current);
    }
}

fn is_virtual(name: &str, cache: &mut HashMap<String, bool>) -> bool {
    if let Some(value) = cache.get(name) {
        return *value;
    }
    let path = format!("/sys/class/net/{name}");
    let virtual_interface = fs::read_link(path)
        .map(|p| p.to_string_lossy().contains("/virtual/"))
        .unwrap_or(true);
    cache.insert(name.to_owned(), virtual_interface);
    virtual_interface
}

fn link_bytes(cache: &mut HashMap<String, bool>) -> Option<u64> {
    let text = fs::read_to_string("/proc/net/dev").ok()?;
    let mut total = 0u64;
    for line in text.lines().skip(2) {
        let Some((name, rest)) = line.split_once(':') else {
            continue;
        };
        let name = name.trim();
        if rest.trim().is_empty() || is_virtual(name, cache) {
            continue;
        }
        let fields: Vec<u64> = rest
            .split_whitespace()
            .filter_map(|s| s.parse().ok())
            .collect();
        if fields.len() > 8 {
            total = total.saturating_add(fields[0]).saturating_add(fields[8]);
        } else {
            return None;
        }
    }
    Some(total)
}

fn sql_quote(text: &str) -> String {
    format!("'{}'", text.replace('\'', "''").replace('\0', ""))
}

fn sqlite(db: &Path, input: &str) -> Result<(), String> {
    let mut child = Command::new("sqlite3")
        .arg("-batch")
        .arg(db)
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("cannot start sqlite3: {e}"))?;
    child
        .stdin
        .take()
        .ok_or("sqlite3 stdin unavailable")?
        .write_all(input.as_bytes())
        .map_err(|e| e.to_string())?;
    let output = child.wait_with_output().map_err(|e| e.to_string())?;
    if output.status.success() {
        Ok(())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).trim().to_owned())
    }
}

fn open_db(path: &Path) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    sqlite(
        path,
        &format!(".bail on\nPRAGMA journal_mode=WAL;\nPRAGMA synchronous=NORMAL;\n{SCHEMA}"),
    )
}

fn flush(db: &Path, pending: &Arc<Mutex<Pending>>) {
    let (usage, dns) = match pending.lock() {
        Ok(mut state) => (
            std::mem::take(&mut state.usage),
            std::mem::take(&mut state.dns),
        ),
        Err(error) => {
            log(format!("flush lock failed: {error}"));
            return;
        }
    };
    if usage.is_empty() && dns.is_empty() {
        return;
    }
    let mut sql = String::from(".bail on\nBEGIN;\n");
    for ((minute, process, host), (rx, tx)) in &usage {
        let hour = minute / 3600 * 3600;
        for (table, ts) in [("usage_minute", *minute), ("usage_hour", hour)] {
            sql.push_str(&format!("INSERT INTO {table} (ts, proc, host, rx, tx) VALUES ({ts}, {}, {}, {rx}, {tx}) ON CONFLICT(ts, proc, host) DO UPDATE SET rx=rx+excluded.rx, tx=tx+excluded.tx;\n", sql_quote(process), sql_quote(host)));
        }
    }
    for ((hour, name), (queries, failures)) in &dns {
        sql.push_str(&format!("INSERT INTO dns_hour (ts, name, queries, failures) VALUES ({hour}, {}, {queries}, {failures}) ON CONFLICT(ts, name) DO UPDATE SET queries=queries+excluded.queries, failures=failures+excluded.failures;\n", sql_quote(name)));
    }
    sql.push_str(&format!(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_flush', {});\nCOMMIT;\n",
        sql_quote(&unix_seconds().to_string())
    ));
    if let Err(error) = sqlite(db, &sql) {
        log(format!("flush failed: {error}"));
        if let Ok(mut state) = pending.lock() {
            for (key, (rx, tx)) in usage {
                let value = state.usage.entry(key).or_default();
                value.0 = value.0.saturating_add(rx);
                value.1 = value.1.saturating_add(tx);
            }
            for (key, (queries, failures)) in dns {
                let value = state.dns.entry(key).or_default();
                value.0 = value.0.saturating_add(queries);
                value.1 = value.1.saturating_add(failures);
            }
        }
    }
}

fn prune(db: &Path) {
    let now = unix_seconds();
    let sql = format!(
        ".bail on\nDELETE FROM usage_minute WHERE ts < {};\nDELETE FROM usage_hour WHERE ts < {};\nDELETE FROM dns_hour WHERE ts < {};\nPRAGMA wal_checkpoint(TRUNCATE);\n",
        now.saturating_sub(MINUTE_RETENTION),
        now.saturating_sub(HOUR_RETENTION),
        now.saturating_sub(HOUR_RETENTION)
    );
    if let Err(error) = sqlite(db, &sql) {
        log(format!("prune failed: {error}"));
    }
}

fn main() {
    install_signal_handlers();
    let db = db_path();
    if let Err(error) = open_db(&db) {
        log(format!("database open failed: {error}"));
        std::process::exit(1);
    }
    let pending = Arc::new(Mutex::new(Pending::default()));
    load_cache_dump(&pending);
    let monitor_state = Arc::clone(&pending);
    thread::spawn(move || dns_monitor(monitor_state));
    let mut sampler = Sampler::new();
    sampler.poll(&pending); // baseline: pre-existing counters are not charged
    let mut virtual_cache = HashMap::new();
    let mut last_link = link_bytes(&mut virtual_cache);
    let mut last_poll = std::time::Instant::now();
    let mut last_flush = last_poll;
    let mut last_cache = last_poll;
    let mut last_prune = last_poll;
    prune(&db);
    while !STOP.load(Ordering::Relaxed) {
        thread::sleep(Duration::from_secs(POLL_SECONDS));
        if STOP.load(Ordering::Relaxed) {
            break;
        }
        let now = std::time::Instant::now();
        let link = link_bytes(&mut virtual_cache);
        let idle = matches!((link, last_link), (Some(current), Some(previous)) if current.saturating_sub(previous) < IDLE_BYTES && now.duration_since(last_poll).as_secs() < IDLE_FORCE_SECONDS);
        if !idle {
            sampler.poll(&pending);
            last_poll = now;
            last_link = link;
        }
        if now.duration_since(last_flush).as_secs() >= FLUSH_SECONDS {
            flush(&db, &pending);
            last_flush = now;
        }
        if now.duration_since(last_cache).as_secs() >= CACHE_REFRESH_SECONDS {
            load_cache_dump(&pending);
            last_cache = now;
        }
        if now.duration_since(last_prune).as_secs() >= 6 * 3600 {
            prune(&db);
            last_prune = now;
        }
    }
    flush(&db, &pending);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_socket_counters_and_process() {
        let mut names = HashMap::new();
        let data = "ESTAB 0 0 10.0.0.2:443 93.184.216.34:443 users:(\"curl\",pid=42,fd=3) cubic bytes_sent:321 bytes_received:654\n";
        let parsed = parse_sockets(data, &mut names);
        let socket = parsed
            .get(&("10.0.0.2:443".into(), "93.184.216.34:443".into()))
            .unwrap();
        assert_eq!(socket.proc_name, "curl");
        assert_eq!((socket.rx, socket.tx), (654, 321));
    }

    #[test]
    fn rejects_loopback_and_sockets_without_counters() {
        let mut names = HashMap::new();
        let data = "ESTAB 0 0 127.0.0.1:22 127.0.0.1:443 users:(\"ssh\",pid=4,fd=1) bytes_sent:1\nESTAB 0 0 10.0.0.2:443 93.184.216.34:443 users:(\"curl\",pid=42,fd=3) cubic\n";
        assert!(parse_sockets(data, &mut names).is_empty());
    }

    #[test]
    fn dns_answers_accept_v4_and_v6_and_names_are_filtered() {
        assert_eq!(
            addr_from_json(&serde_json::json!([1, 1, 1, 1])).as_deref(),
            Some("1.1.1.1")
        );
        assert_eq!(
            addr_from_json(&serde_json::json!([
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1
            ]))
            .as_deref(),
            Some("::1")
        );
        assert!(ignored_name("localhost"));
        assert!(ignored_name("1.2.3.4.in-addr.arpa"));
        assert!(!ignored_name("example.org"));
    }

    #[test]
    fn sqlite_literals_cannot_inject_statements() {
        assert_eq!(
            sql_quote("x'); DROP TABLE usage_minute;--"),
            "'x''); DROP TABLE usage_minute;--'"
        );
    }

    #[test]
    fn counts_a_and_unpaired_aaaa_once() {
        let mut state = Pending::default();
        add_dns(&mut state, 3_600, "example.org".into(), false);
        add_dns(&mut state, 3_600, "example.org".into(), true);
        assert_eq!(state.dns.get(&(3_600, "example.org".into())), Some(&(2, 1)));
    }

    #[test]
    fn flush_preserves_panel_database_contract() {
        let db = env::temp_dir().join(format!("mseries-netusage-{}.db", std::process::id()));
        let _ = fs::remove_file(&db);
        open_db(&db).unwrap();
        let pending = Arc::new(Mutex::new(Pending::default()));
        {
            let mut state = pending.lock().unwrap();
            add_usage(
                &mut state,
                1_800,
                "browser".into(),
                "example.org".into(),
                21,
                34,
            );
            add_dns(&mut state, 3_600, "example.org".into(), true);
        }
        flush(&db, &pending);
        let output = Command::new("sqlite3").arg("-batch").arg(&db)
            .arg("SELECT ts||'|'||proc||'|'||host||'|'||rx||'|'||tx FROM usage_minute; SELECT ts||'|'||name||'|'||queries||'|'||failures FROM dns_hour;")
            .output().unwrap();
        assert!(output.status.success());
        let rows = String::from_utf8_lossy(&output.stdout);
        assert!(rows.contains("1800|browser|example.org|21|34"), "{rows}");
        assert!(rows.contains("3600|example.org|1|1"), "{rows}");
        let _ = fs::remove_file(&db);
        let _ = fs::remove_file(db.with_extension("db-wal"));
        let _ = fs::remove_file(db.with_extension("db-shm"));
    }
}
