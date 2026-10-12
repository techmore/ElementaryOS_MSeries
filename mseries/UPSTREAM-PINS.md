# Upstream pins (reproducibility record)

First M-series commit is based on:

- `elementary/os` `main` @ `5215b29a2eb2d52bb946b2e8e0b92f75c32e808a`
  ("tmpfiles.d/login.conf: Fix /var/lib/lightdm ownership (#911)"),
  merged up to `7024fd04646a6a8565bf6805989b59fd72de928c` ("Add systemd-coredump (#915)", 2026-10-12)
  https://github.com/elementary/os
- `omacom/omarchy-mac` `quattro` @ `ba546a61f881c1fe9d79d75ec050eab048b8cb63`
  ("Hand off Steam launcher ownership to FEX package (#511)", 2026-09-25)
  https://github.com/omacom/omarchy-mac

Only additive `mseries/` docs plus the `mkosi.images/apple-silicon/` image sit
on top. Minimal clearly-marked one-line additions exist in four upstream
files (`mkosi.conf.d/arch.arm64.conf` dependency, liveiso aarch64 profile
`ExtraTrees`, new `mkosi.images/sysupdate/mkosi.conf.d/arch.arm64.conf`,
`README.md` pointer banner, `daily-9.0.yml` push-trigger removal); no
upstream file content is otherwise modified.
