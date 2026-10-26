//! Owned subprocess work for SDK clients. A private Unix process group, bounded
//! nonblocking pipes and monotonic deadline bound inherited-pipe handling. The
//! runner reaps its leader and cancels same-group descendants. Dropping its handle
//! requests cancellation; daemon/privileged jobs need an OS-owned service adapter.

use crate::runtime::{FailureKind, ServiceFailure};
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, Ordering},
};
use std::time::Duration;

#[derive(Debug, Clone, Copy)]
pub struct Limits {
    pub timeout: Duration,
    /// Combined stdout and stderr bytes; at most 16 MiB is accepted.
    pub output_bytes: usize,
}
impl Default for Limits {
    fn default() -> Self {
        Self { timeout: Duration::from_secs(120), output_bytes: 1024 * 1024 }
    }
}

#[derive(Debug)]
pub struct Output {
    pub stdout: String,
    pub stderr: String,
}

struct Control {
    cancelled: AtomicBool,
    finished: AtomicBool,
    group: Mutex<Option<i32>>,
}

pub struct Process {
    control: Arc<Control>,
}
impl Process {
    pub fn cancel(&self) {
        self.control.cancelled.store(true, Ordering::SeqCst);
        if let Some(pid) = *self.control.group.lock().unwrap_or_else(|e| e.into_inner()) {
            kill_group(pid);
        }
    }
    pub fn is_finished(&self) -> bool {
        self.control.finished.load(Ordering::SeqCst)
    }
}
impl Drop for Process {
    fn drop(&mut self) {
        if !self.is_finished() {
            self.cancel();
        }
    }
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
fn kill_group(pid: i32) {
    if pid > 0 {
        // SAFETY: only the dedicated group created by this operation is targeted.
        unsafe {
            libc::kill(-pid, libc::SIGKILL);
        }
    }
}
#[cfg(not(any(target_os = "linux", target_os = "macos")))]
fn kill_group(_: i32) {}

pub fn spawn(
    command: String,
    limits: Limits,
    operation: u64,
    complete: impl FnOnce(Result<Output, ServiceFailure>) + Send + 'static,
) -> Result<Process, ServiceFailure> {
    let control = Arc::new(Control {
        cancelled: AtomicBool::new(false),
        finished: AtomicBool::new(false),
        group: Mutex::new(None),
    });
    let worker = control.clone();
    std::thread::Builder::new()
        .name("msdk-process".into())
        .spawn(move || {
            let result = run(command, limits, operation, &worker);
            worker.finished.store(true, Ordering::SeqCst);
            complete(result);
        })
        .map_err(|_| failure(FailureKind::Unavailable, operation))?;
    Ok(Process { control })
}

fn failure(kind: FailureKind, operation: u64) -> ServiceFailure {
    ServiceFailure::new(kind, "process.run", "/runtime/process.run", operation)
}

#[cfg(not(any(target_os = "linux", target_os = "macos")))]
fn run(_: String, _: Limits, operation: u64, _: &Control) -> Result<Output, ServiceFailure> {
    Err(failure(FailureKind::Unavailable, operation))
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
fn run(command: String, limits: Limits, operation: u64, control: &Control) -> Result<Output, ServiceFailure> {
    use std::io::Read;
    use std::os::{fd::AsRawFd, unix::process::CommandExt};
    use std::process::{Command, Stdio};
    use std::time::Instant;
    if limits.timeout.is_zero() || limits.output_bytes == 0 || limits.output_bytes > 16 * 1024 * 1024 {
        return Err(failure(FailureKind::InvalidInput, operation));
    }
    if control.cancelled.load(Ordering::SeqCst) {
        return Err(failure(FailureKind::Cancelled, operation));
    }
    let mut child = Command::new("/bin/sh")
        .arg("-c")
        .arg(command)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .process_group(0)
        .spawn()
        .map_err(|error| {
            failure(
                match error.kind() {
                    std::io::ErrorKind::PermissionDenied => FailureKind::PermissionDenied,
                    std::io::ErrorKind::InvalidInput => FailureKind::InvalidInput,
                    std::io::ErrorKind::NotFound => FailureKind::Unavailable,
                    _ => FailureKind::Io,
                },
                operation,
            )
        })?;
    let pid = child.id() as i32;
    *control.group.lock().unwrap_or_else(|e| e.into_inner()) = Some(pid);
    let mut stdout = child.stdout.take().expect("piped stdout");
    let mut stderr = child.stderr.take().expect("piped stderr");
    let result = (|| {
        for fd in [stdout.as_raw_fd(), stderr.as_raw_fd()] {
            // SAFETY: owned live pipe descriptors; retain existing status flags.
            let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
            if flags == -1 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } == -1 {
                return Err(failure(FailureKind::Io, operation));
            }
        }
        let start = Instant::now();
        let mut out = Vec::new();
        let mut err = Vec::new();
        let mut total = 0usize;
        loop {
            if control.cancelled.load(Ordering::SeqCst) {
                return Err(failure(FailureKind::Cancelled, operation));
            }
            if start.elapsed() >= limits.timeout {
                return Err(failure(FailureKind::TimedOut, operation));
            }
            let mut buffer = [0_u8; 8192];
            for (pipe, target) in [(&mut stdout as &mut dyn Read, &mut out), (&mut stderr as &mut dyn Read, &mut err)] {
                loop {
                    if control.cancelled.load(Ordering::SeqCst) {
                        return Err(failure(FailureKind::Cancelled, operation));
                    }
                    if start.elapsed() >= limits.timeout {
                        return Err(failure(FailureKind::TimedOut, operation));
                    }
                    match pipe.read(&mut buffer) {
                        Ok(0) => break,
                        Ok(count) => {
                            if total.saturating_add(count) > limits.output_bytes {
                                return Err(failure(FailureKind::OutputLimit, operation));
                            }
                            target.extend_from_slice(&buffer[..count]);
                            total += count;
                        }
                        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => break,
                        Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
                        Err(_) => return Err(failure(FailureKind::Io, operation)),
                    }
                }
            }
            if out.len().saturating_add(err.len()) > limits.output_bytes {
                return Err(failure(FailureKind::OutputLimit, operation));
            }
            if exited_without_reaping(pid).map_err(|_| failure(FailureKind::Io, operation))? {
                // Descendants must not keep pipe ownership alive after the leader
                // exits. Clean the group and drain its finite buffered bytes next.
                kill_group(pid);
                for (pipe, target) in
                    [(&mut stdout as &mut dyn Read, &mut out), (&mut stderr as &mut dyn Read, &mut err)]
                {
                    loop {
                        match pipe.read(&mut buffer) {
                            Ok(0) => break,
                            Ok(count) => {
                                if total.saturating_add(count) > limits.output_bytes {
                                    return Err(failure(FailureKind::OutputLimit, operation));
                                }
                                target.extend_from_slice(&buffer[..count]);
                                total += count;
                            }
                            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
                            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => break,
                            Err(_) => return Err(failure(FailureKind::Io, operation)),
                        }
                    }
                }
                if out.len().saturating_add(err.len()) > limits.output_bytes {
                    return Err(failure(FailureKind::OutputLimit, operation));
                }
                let output = Output {
                    stdout: String::from_utf8_lossy(&out).into_owned(),
                    stderr: String::from_utf8_lossy(&err).into_owned(),
                };
                // Keep the leader unreaped until all group-directed signals are
                // finished, preventing PID reuse from targeting another process.
                let mut group = control.group.lock().unwrap_or_else(|e| e.into_inner());
                kill_group(pid);
                *group = None;
                let status = child.wait().map_err(|_| failure(FailureKind::Io, operation))?;
                return if status.success() {
                    Ok(output)
                } else {
                    Err(failure(FailureKind::ProcessFailed, operation).with_detail(output.stderr))
                };
            }
            std::thread::sleep(Duration::from_millis(5));
        }
    })();
    let mut group = control.group.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(pid) = group.take() {
        kill_group(pid);
        let _ = child.wait();
    }
    result
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
fn exited_without_reaping(pid: i32) -> std::io::Result<bool> {
    // SAFETY: initialized siginfo output, live child PID, WNOWAIT preserves its
    // identity until cancellation/group cleanup and wait() are serialized.
    let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
    let result = unsafe {
        libc::waitid(libc::P_PID, pid as libc::id_t, &mut info, libc::WEXITED | libc::WNOHANG | libc::WNOWAIT)
    };
    if result == -1 {
        return Err(std::io::Error::last_os_error());
    }
    #[cfg(target_os = "linux")]
    let child = unsafe { info.si_pid() };
    #[cfg(target_os = "macos")]
    let child = info.si_pid;
    Ok(child == pid)
}
