# Third-party source

`src/` adapts Smithay's `smallvil` example compositor from
<https://github.com/Smithay/smithay/tree/023b78b1c5a05ca512767cacc07efca55fae8be4/smallvil>.
The upstream license is included as `SMITHAY-LICENSE.txt`.

`protocol/pantheon-desktop-shell-v1.xml` is based on elementary/Gala's
`protocol/pantheon-desktop-shell-v1.xml` at commit `f0791434`
(<https://github.com/elementary/gala/tree/f0791434/protocol>), released under
LGPL-2.1-or-later. This copy advertises protocol version 2 and includes the
M-series `set_offset` request already used by this repository's Gala/Dock
patches. The source XML retains its copyright and SPDX notice.
