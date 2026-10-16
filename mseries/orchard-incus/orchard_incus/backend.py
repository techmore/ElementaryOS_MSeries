"""Display-free logic for Orchard: Incus CLI access, parsing, validation and small calculations.

Nothing here imports GTK, so it can be unit-tested without a display.
"""
import csv
import json
import os
import platform
import re
import subprocess
import time

HIST = 90  # samples kept per instance (~ 4.5 min at 3 s)

PERIOD = 3

IDLE_PERIOD = 15  # seconds between refreshes while the window is unfocused and events are unavailable

SAFETY_PERIOD = 60  # resync even without events, in case one was missed

PROGRESS_RE = re.compile(r"([A-Za-z]+(?: [A-Za-z]+)*): (\d+)%")

PHASES = {"metadata": "Fetching image info", "rootfs": "Downloading image", "Unpacking image": "Unpacking image"}

NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

ARCH = {"aarch64": "arm64", "x86_64": "amd64"}.get(platform.machine(), platform.machine())

PRESETS = [
    ("Alpine (edge)", "images:alpine/edge"), ("Debian 13", "images:debian/trixie"),
    ("Ubuntu 24.04", "images:ubuntu/24.04"), ("Fedora 43", "images:fedora/43"),
    ("Arch Linux", "images:archlinux"), ("Custom…", ""),
]

# chart colours are theme tokens, resolved at draw time so they follow light/dark.
# elementary's light-mode accent/error tokens are pastel (contrast ~1.7:1), so they are darkened until legible
GREEN, BLUE = "success_color", "accent_color"

RGB_FALLBACK = {"success_color": (0.24, 0.77, 0.43), "accent_color": (0.21, 0.54, 0.90)}

MIN_GRAPHIC_CONTRAST = 3.0  # WCAG 1.4.11


def incus(*args, timeout=600, stdin=None):
    p = subprocess.run(["incus", *args], capture_output=True, text=True, timeout=timeout, input=stdin)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip() or f"incus {args[0]} failed")
    return p.stdout


def ijson(*args):
    return json.loads(incus(*args, "--format", "json"))


def stop_or_force(verb, name):
    """Graceful stop/restart with a timeout, then force (init may not be up yet)."""
    try:
        return incus(verb, "--timeout", "30", name, timeout=60)
    except (RuntimeError, subprocess.TimeoutExpired):
        return incus(verb, "--force", name, timeout=60)


def human(n):
    n = float(n or 0)
    for u in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or u == "TiB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def addrs(st, fam):
    out = []
    for nic, d in ((st or {}).get("network") or {}).items():
        if nic == "lo":
            continue
        out += [a["address"] for a in d.get("addresses", []) if a["family"] == fam and a["scope"] == "global"]
    return out


def preflight():
    """Return None when Incus is usable, else (title, detail, command-to-fix)."""
    try:
        incus("version", timeout=10)
    except FileNotFoundError:
        return ("Incus isn't installed", "Orchard needs the Incus container manager.", "sudo apt install incus")
    except subprocess.TimeoutExpired:
        return ("Incus isn't responding", "The Incus service didn't answer in time.", "sudo systemctl restart incus")
    except RuntimeError as e:
        msg = str(e).lower()
        if "permission" in msg or "denied" in msg:
            return ("No permission to use Incus", "Your account isn't allowed to talk to the Incus service. Add it to the incus-admin group, then sign out and back in.",
                    "sudo usermod -aG incus-admin $USER")
        return ("Incus isn't running", "Orchard couldn't reach the Incus service.", "sudo systemctl start incus")
    return None


def _lum(c):
    f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c.red) + 0.7152 * f(c.green) + 0.0722 * f(c.blue)


def contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def valid_name(v):
    return bool(NAME_RE.match(v))


def last(series, default=0.0):
    return series[-1] if series else default


def state_key(status):
    return {"Running": "running", "Frozen": "frozen"}.get(status, "stopped")


# ---------------------------------------------------------------- sparkline


def parse_progress(text):
    """Parse one line of `incus launch` output, e.g. 'Retrieving image: rootfs: 42% (6.97MB/s)'.
    Returns (label, percent, speed-or-None), or None when the line carries no percentage."""
    m = PROGRESS_RE.search(text)
    if not m:
        return None
    speed = re.search(r"\(([^)]*/s)\)", text)
    return m.group(1), int(m.group(2)), speed.group(1) if speed else None


def progress_text(label, pct, speed=None):
    return f"{PHASES.get(label, label)} {pct}%" + (f" · {speed}" if speed else "")


def auto_name(img, rand=os.urandom):
    """A valid instance name derived from an image alias, e.g. 'images:debian/trixie' -> 'debian-trixie-3fa9'."""
    slug = re.sub(r"[^a-z0-9]+", "-", img.split(":")[-1].lower()).strip("-")[:24] or "instance"
    return f"{slug}-{rand(2).hex()}"


def cpu_percent(prev_ns, prev_t, ns, now):
    """CPU use in percent of one core from two cumulative CPU-time readings (nanoseconds) and their timestamps."""
    if prev_ns is None or prev_t is None or now <= prev_t:
        return 0.0
    return max(0.0, (ns - prev_ns) / 1e9 / (now - prev_t) * 100)


def validate_new(name, image, cpu, mem):
    """Problems with the New Instance form, as short messages (empty list = fine)."""
    name, image, cpu, mem = name.strip(), image.strip(), cpu.strip(), mem.strip()
    msgs = []
    if name and not valid_name(name):
        msgs.append("Name: letters, digits and hyphens only.")
    if not image:
        msgs.append("Choose or enter an image.")
    if cpu and not re.fullmatch(r"\d+(-\d+)?", cpu):
        msgs.append("CPU limit: a number such as 2.")
    if mem and not re.fullmatch(r"\d+(\.\d+)?\s*([KMGT]i?B|%)?", mem):
        msgs.append("Memory limit: for example 512MiB or 2GiB.")
    return msgs


def create_args(vm, cpu, mem):
    """Extra `incus launch` arguments for the form's choices (after the image and optional name)."""
    extra = ["--vm"] if vm else []
    if cpu.strip():
        extra += ["-c", f"limits.cpu={cpu.strip()}"]
    if mem.strip():
        extra += ["-c", f"limits.memory={mem.strip()}"]
    return extra


def parse_event(line):
    """(action, source) from one `incus monitor --format json` line, or None if it isn't a usable event."""
    try:
        meta = json.loads(line)["metadata"]
        return meta.get("action", ""), meta.get("source", "")
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


STARTED_ACTIONS = ("instance-started", "instance-restarted", "instance-resumed")


def parse_images_csv(text, limit=60):
    """Rows of `incus image list images: ... -c ldt --format csv` as (alias, description, is_vm), de-duplicated."""
    rows, seen = [], set()
    for line in text.splitlines():
        parts = next(csv.reader([line]), [])
        if len(parts) < 3:
            continue
        alias, desc, typ = parts[0].split(" (")[0], parts[1], parts[2]
        if (alias, typ) in seen:
            continue
        seen.add((alias, typ))
        rows.append((alias, desc, typ == "VIRTUAL-MACHINE"))
        if len(rows) >= limit:
            break
    return rows


def cleanup_loop(name, run, sleep=time.sleep, clock=time.monotonic, patience=120):
    """Delete an instance whose creation was cancelled or failed.

    `incus launch` is one server-side create-and-start operation, so interrupting the client does not stop it: the
    instance still appears (stopped, then running) some seconds later. Keep cancelling related operations and
    force-deleting until the instance is gone. `run(args)` returns (returncode, stdout, stderr). True if deleted."""
    res = f"/1.0/instances/{name}"
    deadline = clock() + patience
    while clock() < deadline:
        rc, out, _ = run(["incus", "operation", "list", "--format", "json"])
        if rc == 0:
            try:
                ops = json.loads(out)
            except ValueError:
                ops = []
            for op in ops:
                if res in ((op.get("resources") or {}).get("instances") or []) and op.get("status") in ("Running", "Pending"):
                    run(["incus", "operation", "delete", op["id"]])
        rc, _, _ = run(["incus", "delete", "-f", name])
        if rc == 0:
            return True
        sleep(1 if deadline - clock() > patience - 30 else 3)
    return False
