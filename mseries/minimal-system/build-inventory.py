#!/usr/bin/env python3
"""Builds packages.tsv: every package the Ubuntu-based system installs on purpose, mapped to a layer, an
Arch Linux ARM / Asahi Alarm source, an action, the reason it exists and the leanest known form.

Inputs (read-only, nothing is installed):
  - `apt-mark showmanual` on the machine (what was installed deliberately), plus the packages named in
    mkosi configs and install scripts (declared-packages.py);
  - the pacman sync databases of Arch Linux ARM (core, extra, alarm) and Asahi Alarm, downloaded to a cache dir.

Usage: build-inventory.py <cache-dir> <repo-root> > packages.tsv
"""
import json, os, re, subprocess, sys, tarfile, urllib.request

CACHE, ROOT = sys.argv[1], sys.argv[2]
os.makedirs(CACHE, exist_ok=True)
DBS = {
    "core": "http://os.archlinuxarm.org/aarch64/core/core.db",
    "extra": "http://os.archlinuxarm.org/aarch64/extra/extra.db",
    "alarm": "http://os.archlinuxarm.org/aarch64/alarm/alarm.db",
    "asahi-alarm": "https://github.com/asahi-alarm/asahi-alarm/releases/download/aarch64/asahi-alarm.db",
}


def fetch(name, url):
    path = os.path.join(CACHE, name + ".db")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        urllib.request.urlretrieve(url, path)
    return path


arch = {}  # name -> list of {repo, ver}
prov = {}
for repo, url in DBS.items():
    t = tarfile.open(fetch(repo, url))
    for m in t.getmembers():
        if not m.name.endswith("/desc"):
            continue
        f, cur = {}, None
        for line in t.extractfile(m).read().decode(errors="ignore").splitlines():
            if len(line) > 2 and line.startswith("%") and line.endswith("%"):
                cur = line.strip("%")
                f[cur] = []
            elif line and cur:
                f[cur].append(line)
        if "NAME" not in f:
            continue
        e = {"repo": repo, "ver": f["VERSION"][0]}
        arch.setdefault(f["NAME"][0], []).append(e)
        for p in f.get("PROVIDES", []):
            prov.setdefault(p.split("=")[0], []).append((f["NAME"][0], repo))


def best(name):
    """Prefer Asahi Alarm's build when it has the package."""
    if name in arch:
        es = sorted(arch[name], key=lambda e: e["repo"] != "asahi-alarm")
        return name, es[0]["repo"], es[0]["ver"]
    if name in prov:
        n, r = prov[name][0]
        return n, r, arch[n][0]["ver"]
    return None


# Debian name -> Arch name where the names differ and the generic rules cannot guess.
ALIAS = {
    "network-manager": "networkmanager", "openssh-client": "openssh", "nfs-common": "nfs-utils", "vainfo": "libva-utils",
    "xkb-data": "xkeyboard-config", "python3-gi": "python-gobject", "python3-gi-cairo": "python-gobject",
    "libvirt-clients": "libvirt", "libvirt-daemon-system": "libvirt", "ovmf": "edk2-aarch64", "virtinst": "virt-install",
    "freerdp3-sdl": "freerdp", "freerdp3-wayland": "freerdp", "freerdp3-x11": "freerdp", "gdisk": "gptfdisk",
    "genisoimage": "cdrtools", "wimtools": "wimlib", "libssl-dev": "openssl", "libssl3t64": "openssl", "build-essential": "base-devel",
    "g++": "gcc", "golang-go": "go", "rustc": "rust", "cargo": "rust", "clang-21": "clang", "llvm-21": "llvm", "llvm-21-dev": "llvm",
    "libclang-21-dev": "clang", "libclc-21-dev": "libclc", "libllvmspirvlib-21-dev": "spirv-llvm-translator",
    "libgtk-3-dev": "gtk3", "libgtk-3-0t64": "gtk3", "libgtk-3-bin": "gtk3", "gir1.2-gtk-3.0": "gtk3", "libgtk-4-dev": "gtk4",
    "libadwaita-1-dev": "libadwaita", "libvte-2.91-gtk4-dev": "vte4", "libgtksourceview-5-dev": "gtksourceview5",
    "libhandy-1-dev": "libhandy", "libsecret-1-dev": "libsecret", "libsqlite3-dev": "sqlite", "libbz2-dev": "bzip2",
    "libbz2-1.0": "bzip2", "libgee-0.8-dev": "libgee", "libgit2-glib-1.0-dev": "libgit2-glib", "libgstreamer1.0-dev": "gstreamer",
    "libgstreamer-plugins-base1.0-dev": "gst-plugins-base", "libibus-1.0-dev": "ibus", "libmutter-18-dev": "mutter",
    "libpackagekit-glib2-dev": "packagekit", "libpipewire-0.3-dev": "pipewire", "libpolkit-gobject-1-dev": "polkit",
    "libseat-dev": "seatd", "libudev-dev": "systemd-libs", "libudev1": "systemd-libs", "udev": "systemd", "libvulkan-dev": "vulkan-headers",
    "libvulkan1": "vulkan-icd-loader", "libswitchboard-3-dev": "switchboard", "libwingpanel-9-dev": "wingpanel",
    "libzeitgeist-2.0-dev": "zeitgeist", "libgnome-bg-4-dev": "gnome-desktop-4", "libecal2.0-dev": "evolution-data-server",
    "libedataserver1.2-dev": "evolution-data-server", "gir1.2-ecal-2.0": "evolution-data-server", "gir1.2-edataserver-1.2": "evolution-data-server",
    "gir1.2-glib-2.0": "glib2", "gir1.2-webkit-6.0": "webkitgtk-6.0", "protobuf-compiler": "protobuf", "pkg-config": "pkgconf",
    "ninja-build": "ninja", "xsltproc": "libxslt", "xauth": "xorg-xauth", "xvfb": "xorg-server-xvfb", "libqt6svg6": "qt6-svg",
    "libqt6widgets6": "qt6-base", "libpam0g": "pam", "libpam0g-dev": "pam", "libpam-modules": "pam", "libpam-modules-bin": "pam",
    "libpam-runtime": "pam", "libattr1-dev": "attr", "libheif-plugin-libde265": "libde265", "libcairo2-dev": "cairo",
    "libexpat1-dev": "expat", "libfuse-dev": "fuse3", "libgbm-dev": "mesa", "libgbm1": "mesa", "libasound2t64": "alsa-lib",
    "libatk-bridge2.0-0t64": "at-spi2-core", "libatk1.0-0t64": "at-spi2-core", "libatspi2.0-0t64": "at-spi2-core",
    "libglib2.0-0t64": "glib2", "libpango-1.0-0": "pango", "libncursesw6": "ncurses", "libtinfo6": "ncurses", "ncurses-base": "ncurses",
    "libfreetype6": "freetype2", "libss2": "e2fsprogs", "libcom-err2": "e2fsprogs", "libext2fs2t64": "e2fsprogs",
    "libsmartcols1": "util-linux-libs", "libblkid1": "util-linux-libs", "libmount1": "util-linux-libs", "libuuid1": "util-linux-libs",
    "mount": "util-linux", "libcrypt1": "libxcrypt", "libdb5.3t64": "db5.3", "liblzma5": "xz", "libproc2-0": "procps-ng", "procps": "procps-ng",
    "libgcc-s1": "gcc-libs", "libsysprof-6-dev": "sysprof", "libgtop2-dev": "libgtop", "libpugixml1v5": "pugixml",
    "zlib1g": "zlib", "zlib1g-dev": "zlib", "libselinux1": "libselinux", "libsemanage2": "libsemanage", "libsepol2": "libsepol",
    "libsemanage-common": "libsemanage", "rfkill": "util-linux", "libva-drm2": "libva", "systemd-container": "systemd",
    "systemd-coredump": "systemd", "systemd-cryptsetup": "systemd", "systemd-homed": "systemd", "systemd-repart": "systemd",
    "systemd-resolved": "systemd", "systemd-zram-generator": "zram-generator", "plymouth-theme-elementary": "plymouth",
    "xfonts-cyrillic": "xorg-fonts-misc", "xfonts-scalable": "xorg-fonts-type1", "fonts-freefont-ttf": "gnu-free-fonts",
    "fonts-ipafont-gothic": "otf-ipafont", "fonts-unifont": "unifont", "fonts-tlwg-loma-otf": "ttf-tlwg",
    "io.elementary.greeter": "lightdm-pantheon-greeter", "pantheon": "pantheon-session", "gnu-coreutils": "coreutils",
    "rust-coreutils": "uutils-coreutils", "coreutils-from-uutils": "uutils-coreutils", "opencode-dev": "opencode",
    "python3": "python", "python3-dev": "python", "python3-all": "python", "python3-venv": "python", "libgtk-3-0": "gtk3",
    "libcurl4t64": "curl", "libxml2-dev": "libxml2", "libdisplay-info3": "libdisplay-info", "libinput10": "libinput",
    "libxi6": "libxi", "libxtst6": "libxtst", "libwayland-dev": "wayland", "libgomp1": "libgomp", "libpugixml-dev": "pugixml",
    "libvirglrenderer-dev": "virglrenderer", "dconf-cli": "dconf", "bridge-utils": "iproute2", "bindgen": "rust-bindgen", "gh": "github-cli", "valac": "vala", "gpg": "gnupg", "gpgv": "gnupg", "glslc": "shaderc", "glslang-tools": "glslang", "device-tree-compiler": "dtc", "linux-libc-dev": "linux-api-headers", "login": "shadow", "passwd": "shadow", "uidmap": "shadow", "librsvg2-bin": "librsvg", "libsecret-tools": "libsecret", "liblz4-1": "lz4", "libx11-6": "libx11", "libfuse3-dev": "fuse3", "libaudit-common": "audit", "fonts-noto-color-emoji": "noto-fonts-emoji", "libcanberra-gtk3-dev": "libcanberra", "libwebkitgtk-6.0-dev": "webkitgtk-6.0", "apparmor-profiles": "apparmor", "dconf-cli": "dconf", "fex-emu-armv8.4": "FEX-Emu",
}
AUR = {"hfsprogs", "chntpw", "powerstat", "brave-browser", "zeitgeist", "tether", "blueferry-backend", "blueferry-gtk"}


def lookup(d):
    if d in ALIAS:
        h = best(ALIAS[d])
        if h:
            return h
    if (h := best(d)):
        return h
    cands = []
    if d.startswith("python3-"):
        cands.append("python-" + d[8:])
    if d.startswith("gir1.2-"):
        cands.append(re.sub(r"-[\d.]+$", "", d[7:]))
    if d.startswith("io.elementary.panel."):
        cands.append("wingpanel-indicator-" + d.rsplit(".", 1)[1])
    if d.startswith("io.elementary."):
        cands += ["pantheon-" + d.rsplit(".", 1)[1], d.rsplit(".", 1)[1]]
    if d.startswith("fonts-"):
        cands += ["ttf-" + d[6:], d[6:]]
    m = re.match(r"^lib(.+?)(-dev|\d+(t64)?|-\d+)*$", d)
    if m:
        cands += [m.group(1), "lib" + m.group(1)]
    cands.append(re.sub(r"(-dev|-bin|-common|-data|-utils)$", "", d))
    for c in cands:
        if (h := best(c)):
            return h
    return None


# (regex, layer, action, why, leanest form). First match wins. Action: consume | wrap | replace | build-only | drop | optional | implicit
RULES = [
    # ours / specific
    (r"pantheon-rust-compositor", "L2 display", "replace", "Smithay compositor implementing the Pantheon shell protocol; already the running session", "Keep. Measured 195 MB PSS in the live session; becomes `mseries-wm`"),
    (r"io\.elementary\.quick-settings|mseries-wingpanel-datetime|io\.elementary\.panel\..*", "L3 shell", "wrap", "Wingpanel indicators the shell needs; Quick Settings and datetime carry our patches", "Rebuild from source in PKGBUILDs; replace each with an SDK indicator once Wingpanel is replaced"),
    (r"claude-pantheon-rs|elementary-torrential", "L4 apps", "replace", "Our native Rust/GTK apps", "Port to the SDK (benchmark specs s06 and similar); keep as the reference implementations"),
    (r"energy-monitor", "L4 apps", "optional", "Separate product by the owner (home energy), not part of the OS", "Ship as its own package; not in the base image"),
    (r"plymouth-theme-elementary", "L1 base", "wrap", "elementary boot/unlock splash (Plymouth theme)", "Rebuild as a PKGBUILD or replace with a minimal Rust-drawn splash"),
    (r"bindgen", "L5 build", "build-only", "Rust FFI generator for builds", "Build container only"),
    (r"dconf-cli", "L1 base", "consume", "dconf command line for GSettings scripts", "Arch `dconf`"),
    (r"mseries-.*", "L3 shell", "wrap", "Our own M-series services and plugins", "Package as PKGBUILDs; fold daemons into one Rust supervisor over time (18 processes, 301 MB PSS today)"),
    # kernels
    (r"linux-image-elementary-aurora72-wip3", "L0 hardware", "replace", "Running Aurora kernel (hand built, copied into /boot)", "Becomes a `linux-aurora` PKGBUILD in `mseries-kernel`"),
    (r"linux-image-elementary-aurora(72-wip2|-enhancements)", "L0 hardware", "drop", "Older Aurora kernels (about 150 MB each installed)", "Keep the running kernel plus one known-good fallback, not three"),
    (r"linux-image-generic|linux-headers-generic", "L0 hardware", "drop", "Ubuntu stock kernel meta-packages; Asahi hardware needs the Asahi/Aurora kernel", "Replaced by `linux-asahi` (Asahi Alarm) or our `linux-aurora`"),
    (r"linux-libc-dev", "L5 build", "build-only", "Kernel UAPI headers for compiling", "Arch `linux-api-headers` in the build container"),
    (r"linux-firmware", "L0 hardware", "consume", "Generic device firmware", "Arch `linux-firmware`; Apple firmware comes from `asahi-fwextract` at install"),
    # boot and Debian plumbing replaced by Arch/Asahi pieces
    (r"grub-efi.*|shim-signed|mokutil|initramfs-tools|casper|systemd-boot.*", "L0 hardware", "drop", "Ubuntu boot chain (Secure Boot shim, initramfs-tools, live-media support)", "Asahi chain: m1n1, U-Boot (`uboot-asahi`), `grub`, mkinitcpio"),
    (r"elementary-(desktop|minimal|standard|live)|io\.elementary\.(apt-shim|installer-session)", "L3 shell", "drop", "elementary image meta-packages and installer hooks", "Arch `pantheon-session` group members, chosen one by one"),
    (r"elementary-sdk", "L5 build", "build-only", "Pantheon development meta-package", "Build container only"),
    (r"apt|dpkg|nala|libapt-pkg.*|debhelper|dh-python|lintian|pybuild.*|debconf|libdebconfclient.*|debianutils|ubuntu-keyring|command-not-found|tailscale-archive-keyring|init-system-helpers|sensible-utils", "drop", "drop", "Debian/Ubuntu packaging and apt tooling", "Replaced by pacman and makepkg"),
    (r"base-files|base-passwd|bsdutils|sysvinit-utils|mawk|hostname|login\.defs|logsave|perl-base|libc6|libc-bin|libc-gconv-modules-extra|gcc-16-base|libselinux1|libsemanage.*|libsepol2", "drop", "drop", "Debian base plumbing", "Arch `base` provides the equivalent (`filesystem`, `glibc`); gconv extras alone are 18 MB"),
    # duplicated heavy apps
    (r"chatgpt", "L4 apps", "drop", "ChatGPT desktop (Electron): measured 4.8 GB PSS across 113 processes, 1.6 GB installed", "Do not carry; use the native client over the T3 server or the web"),
    (r"claude-desktop", "L4 apps", "drop", "Claude desktop (Electron): measured 2.3 GB PSS", "Replaced by `claude-pantheon-rs` (60 MB, about 0% idle)"),
    (r"google-chrome-stable", "L4 apps", "drop", "Second Chromium browser, 434 MB installed", "Brave (or Firefox) covers it"),
    (r"brave-browser", "L4 apps", "optional", "Main browser", "AUR `brave-bin` or our installer; add `widevine` from Asahi Alarm"),
    (r"firefox", "L4 apps", "optional", "Alternative browser", "Arch `firefox` (158.0.1 in the ARM repo)"),
    (r"opencode-dev", "L4 apps", "optional", "OpenCode agent (723 MB installed dev build)", "Arch ships `opencode` in `extra`; compare size before keeping the dev build"),
    # Qt stack used by one upstream app
    (r"libqt6.*|qml6-module-.*|qt6-wayland|python3-pyqt6", "L4 apps", "drop", "Qt stack pulled in only for the upstream CodexBar desktop", "Drop; the native indicator (`claude-pantheon-rs` Wingpanel indicator) replaces it, saving about 50 MB"),
    # fonts
    (r"fonts-(liberation|noto-color-emoji)", "L1 base", "consume", "Core fonts (Latin text, emoji)", "Arch `ttf-liberation`, `noto-fonts-emoji`"),
    (r"fonts-(wqy-zenhei|ipafont-gothic|tlwg-loma-otf|unifont|freefont-ttf)|xfonts-.*", "L1 base", "drop", "Duplicate CJK/Thai/legacy X11 fonts (unifont alone is 32 MB)", "One CJK family (`noto-fonts-cjk`) if needed; no X11 bitmap fonts"),
    # virtualisation and containers
    (r"libvirt-.*|virt-manager|virtinst", "L4 apps", "drop", "libvirt stack; overlaps the Incus setup already used", "Use `incus` plus `qemu-system-aarch64` only"),
    (r"qemu-system-x86", "L4 apps", "optional", "x86 emulation for VMs (58 MB)", "Only if x86 guests are needed; FEX covers userspace x86"),
    (r"qemu-system-arm|incus|ovmf|passt", "L4 apps", "optional", "VM and container host for Orchard/Machine Lab", "Arch `incus`, `qemu-system-aarch64`, `edk2-aarch64`"),
    (r"podman|distrobox|bubblewrap|flatpak|xdg-dbus-proxy", "L4 apps", "optional", "Containers and Flatpak sandbox", "Keep Flatpak/bubblewrap; podman only if Incus does not cover the use"),
    (r"fex-emu.*", "L4 apps", "optional", "x86 userspace emulation", "Asahi Alarm `FEX-Emu` and `muvm`"),
    (r"freerdp3-.*|blueferry-.*|tether|tailscale|hfsprogs|wimtools|cabextract|genisoimage|chntpw|openssl-provider-legacy|nmap|arp-scan|traceroute|aria2|mpv|ffmpeg|swappy|powerstat|btop|nfs-common|bridge-utils", "L4 apps", "optional", "Optional tools and clients installed for specific jobs (RDP, iPhone bridge, VPN, macOS/Windows image tools, network probes, media)", "Install on demand; none belongs in the base image"),
    # build toolchain
    (r"gcc|g\+\+|build-essential|clang.*|llvm.*|libclang.*|libclc.*|libllvm.*|cmake|meson|ninja-build|cargo|rustc|golang-go|nodejs|npm|just|shellcheck|gh|gdb|bison|flex|bc|cbindgen|pahole|patch|patchelf|device-tree-compiler|protobuf-compiler|glsl.*|spirv.*|pkg-config|gettext|valac|check|xsltproc|xvfb|flatpak-builder|libvirglrenderer.*|vulkan-tools|sysprof|libsysprof.*|python3-(pytest|hypothesis|mako|ply|pyelftools|capstone|libarchive-c|docutils|wheel|yaml|argcomplete|all|dev|venv)|python3", "L5 build", "build-only", "Compilers, headers and test tools used to build Mesa, the kernel, Vala patches and our Rust apps", "Move to the SDK build container (clang/LLVM alone is about 800 MB installed); none ships on a user machine"),
    (r"git", "L5 build", "optional", "Source control on the owner's development machine", "Dev machines only"),
    # Pantheon pieces consumed from Arch for now
    (r"io\.elementary\.wingpanel|libwingpanel.*|libswitchboard.*|libgala-dev|libgranite.*|gir1\.2-granite.*|pantheon|io\.elementary\.greeter|io\.elementary\.tasks", "L3 shell", "wrap", "Pantheon shell pieces the session needs until each is replaced", "Arch `pantheon` group at the same versions; Wingpanel measured 379 MB PSS, a replacement target"),
    (r"gnome-online-accounts.*|evolution-data-server|libecal.*|libedataserver.*|gir1\.2-(ecal|edataserver).*|gnome-settings-daemon-common|libgnome-.*|libical-dev|libaccountsservice-dev|libportal.*|libcloudproviders-dev", "L3 shell", "wrap", "Account, calendar and settings services the Pantheon indicators and Calendar call", "Evolution Data Server alone idles around 29 MB; keep only if Calendar/Mail stay"),
    # hardware and power
    (r"alsa-ucm-conf-asahi|asahi-audio|speakersafetyd|pipewire.*|wireplumber|pulseaudio-utils|rtkit|libpulse-dev|liblilv-dev|lv2-dev|libcanberra.*", "L0 hardware", "consume", "Audio path for Apple speakers and mics, including speaker protection", "Asahi Alarm audio packages plus Arch PipeWire; nothing to trim, speaker safety is mandatory"),
    (r"fprintd|power-profiles-daemon|powertop|smartmontools|pciutils|libva.*|vainfo|plymouth|kmod|dkms|rfkill|bluez|network-manager|libnm-dev|libnma.*|xkb-data|libinput.*|libdrm.*|libdisplay-info.*|libseat-dev|libei-dev|libepoxy-dev|libwayland-dev|libgbm.*|libvulkan.*|libxkbcommon0|libumockdev-dev", "L1 base", "consume", "Hardware access, networking, power and display plumbing the compositor and shell sit on", "Arch packages; `dkms` is unnecessary because modules ship with the kernel package"),
    # base userland
    (r"bash|dash|coreutils|diffutils|findutils|grep|gzip|sed|tar|util-linux|xz-utils|e2fsprogs|dosfstools|btrfs-progs|cryptsetup.*|lvm2|udev|login|passwd|mount|ncurses.*|procps|systemd.*|zstd|unzip|curl|wget|gnupg|gpg|gpgv|ca-certificates|nano|vim|openssh-client|rust-coreutils|gnu-coreutils|coreutils-from-uutils|sudo-rs|dbus.*|desktop-file-utils|xdg-utils|xdg-terminal-exec|xdg-desktop-portal-wlr|wl-clipboard|ydotool|xdotool|xauth|bc|erofs-utils|gdisk|hfsprogs|uidmap|zlib.*|apparmor.*", "L1 base", "consume", "Core userland, storage, encryption, session bus", "Arch `base`. Keep `sudo-rs`. Do not add uutils unless a measured win; two coreutils variants are installed today (14 MB + 9 MB)"),
]
RULES = [(re.compile(r"^(?:%s)$" % p), *rest) for p, *rest in RULES]
LIBRARY = re.compile(r"^(lib.*|gir1\.2-.*|python3-.*|.*-dev)$")


def classify(d):
    hit = lookup(d)
    for rx, layer, action, why, lean in RULES:
        if rx.match(d):
            break
    else:
        if LIBRARY.match(d):
            layer, action = ("L5 build", "build-only") if d.endswith("-dev") or "-dev" in d else ("deps", "implicit")
            why = "Header/development package" if action == "build-only" else "Runtime library or binding pulled in as a dependency"
            lean = "Resolved automatically by pacman dependencies; headers ship inside the main Arch package" if action == "implicit" else "Build container only; Arch ships headers inside the main package"
        else:
            layer, action, why, lean = "review", "review", "Not yet classified", ""
    if hit:
        src = "asahi-alarm" if hit[1] == "asahi-alarm" else "arch-official"
        arch_pkg, repo, ver = hit
    elif d in AUR:
        src, arch_pkg, repo, ver = "aur-or-ours", "", "", ""
    else:
        src, arch_pkg, repo, ver = "unresolved", "", "", ""
    if action == "drop":
        src = "drop"
    if re.match(r"^(mseries-.*|claude-pantheon-rs|pantheon-rust-compositor|elementary-torrential|io\.elementary\.quick-settings|linux-image-elementary-aurora72-wip3)$", d):
        src = "ours"
    return layer, src, arch_pkg, repo, ver, action, why, lean


def main():
    manual = set(subprocess.check_output(["apt-mark", "showmanual"], text=True).split())
    names = subprocess.check_output(["apt-cache", "pkgnames"], text=True)
    open(os.path.join(CACHE, "allnames.txt"), "w").write(names)
    declared = subprocess.check_output([sys.executable, os.path.join(os.path.dirname(__file__), "declared-packages.py"), os.path.join(CACHE, "allnames.txt"), ROOT], text=True)
    decl = {l.split()[0] for l in declared.splitlines() if l.strip()} - {"an", "and"}
    union = sorted(manual | decl)
    sizes = {}
    out = subprocess.run(["dpkg-query", "-W", "-f=${Package}\t${Installed-Size}\n", *union], capture_output=True, text=True).stdout
    for l in out.splitlines():
        p, _, s = l.partition("\t")
        sizes[p] = int(s or 0) / 1024
    print("\t".join(["debian_package", "installed_mb", "layer", "source", "arch_package", "arch_repo", "arch_version", "action", "why", "leanest_form", "evidence"]))
    for d in union:
        layer, src, ap, repo, ver, action, why, lean = classify(d)
        ev = "manual" if d in manual else "declared-only"
        print("\t".join([d, f"{sizes.get(d, 0):.1f}", layer, src, ap, repo, ver, action, why, lean, ev]))


main()
