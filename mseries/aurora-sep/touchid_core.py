"""Touch ID facts and plain-language findings.

Pure functions only: no D-Bus, no GTK, no subprocess. The GUI collects the
facts (kernel, /dev/sep-bio, fprintd, PAM files) and asks this module what
they mean, exactly like display_diag.py.
"""
import re

# fprintd finger names (net.reactivated.Fprint sweep values), ordered so the
# dropdown lists the common choices first.
FINGERS = [
    "right-index-finger",
    "right-thumb",
    "right-middle-finger",
    "right-ring-finger",
    "right-little-finger",
    "left-index-finger",
    "left-thumb",
    "left-middle-finger",
    "left-ring-finger",
    "left-little-finger",
]

OK, INFO, WARN, BAD = "ok", "info", "warn", "bad"

# The Aurora SEP kernel's uname markers. The 20261015.19 release reports
# "7.1.12-2-20261015.19-sep-ARCH" (no "aurora" in the string), earlier ones
# "7.1.12.aurora2-12.6". /dev/sep-bio is the authoritative signal; the kernel
# string only turns "no needle" into a specific "wrong kernel" hint.
AURORA_MARKS = ("aurora", "sep-arch")


def on_aurora_kernel(kernel):
    return any(mark in kernel.lower() for mark in AURORA_MARKS)


def finger_label(name):
    """'right-index-finger' -> 'Right index finger'."""
    return name.replace("-", " ").capitalize()


ENROLL_MESSAGES = {
    # status: (message, done)
    "enroll-stage-passed": ("Stage saved. Lift and place the same finger again.", False),
    "enroll-retry-scan": ("Scan failed. Lift and try again.", False),
    "enroll-completed": ("Enrolled.", True),
    "enroll-failed": ("Enrollment failed.", True),
    "enroll-data-full": ("No room for another stage. Delete a finger and retry.", True),
    "enroll-disconnected": ("The sensor disconnected.", True),
    "enroll-unknown-error": ("Unknown error.", True),
}

VERIFY_MESSAGES = {
    "verify-match": ("Match.", True),
    "verify-no-match": ("No match.", True),
    "verify-retry-scan": ("Scan failed. Try again.", False),
    "verify-disconnected": ("The sensor disconnected.", True),
    "verify-unknown-error": ("Unknown error.", True),
}


def enroll_message(status, done):
    """Map an EnrollStatus signal to (plain text, finished?)."""
    text, is_done = ENROLL_MESSAGES.get(status, (status, True))
    return text, bool(done or is_done and status in ENROLL_MESSAGES)


def verify_message(status, done):
    """Map a VerifyStatus signal to (plain text, finished?)."""
    text, is_done = VERIFY_MESSAGES.get(status, (status, True))
    return text, bool(done or is_done and status in VERIFY_MESSAGES)


def pam_state(paths):
    """Read /etc/pam.d files and report whether they use the fingerprint.

    paths: {"sudo": "/etc/pam.d/sudo", "polkit": "/etc/pam.d/polkit-1"}
    Returns a list of {"name", "path", "state"} with state one of
    "fingerprint" (pam_fprintd present), "password-only" (file exists, no
    fingerprint), "missing" (no file).
    """
    out = []
    for name, path in paths.items():
        try:
            with open(path) as f:
                content = f.read()
        except OSError:
            out.append({"name": name, "path": path, "state": "missing"})
            continue
        state = "fingerprint" if re.search(r"^\s*auth\s+\S+\s+pam_fprintd\.so", content, re.M) else "password-only"
        out.append({"name": name, "path": path, "state": state})
    return out


def pam_plan(state):
    """Human summary of what the PAM button will do."""
    todo = [p["name"] for p in state if p["state"] != "fingerprint"]
    if not todo:
        return "Fingerprint unlock is set up for sudo and polkit."
    return "Add fingerprint unlock to: " + ", ".join(todo) + "."


def sep_findings(facts):
    """Turn collected facts into findings. Each finding is
    (severity, title, detail, fix) with fix None or a short command hint.

    facts keys: kernel (str), sep_bio (bool), apple_sep (str state),
    fprintd (str state), device (bool)
    """
    findings = []
    on_aurora = on_aurora_kernel(facts.get("kernel", ""))
    if not facts.get("sep_bio"):
        if not on_aurora:
            findings.append((BAD, "Wrong kernel",
                             "Touch ID needs the Aurora SEP kernel; this boot is running "
                             f"{facts.get('kernel')}.",
                             "See mseries/REBOOT-QUEUE.md before selecting an Aurora boot entry"))
        else:
            findings.append((BAD, "No /dev/sep-bio",
                             "The Aurora kernel is running but the enclave device is missing "
                             f"(apple-sep.service: {facts.get('apple_sep', 'unknown')}).",
                             "systemctl status apple-sep.service"))
        return findings
    readiness = facts.get("readiness")
    if readiness and readiness != "ready":
        busy = "busy" in readiness.lower()
        advice = ("Finish any active fingerprint operation and refresh." if busy else
                  "Check the SEP service journal before retrying enrollment.")
        findings.append((WARN, "Touch ID is busy" if busy else "Touch ID is not ready",
                         f"The enclave exists, but its sensor reports: {readiness}. {advice}",
                         "journalctl -b -u apple-sep.service --no-pager"))
        return findings
    if not facts.get("device"):
        findings.append((WARN, "No fingerprint device",
                         "The enclave exists but fprintd does not list a device. " + facts.get("device_error", ""),
                         "systemctl status fprintd; fprintd-list $USER"))
        return findings
    findings.append((OK, "Touch ID is available",
                    "fprintd offers a sensor. Enroll or verify a finger below.", None))
    return findings
