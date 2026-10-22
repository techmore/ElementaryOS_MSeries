# Historical staged scheduler review recipes

Owner, module, alias and teardown changes are now copied unchanged into r5
compatibility. These directories preserve staged provenance and reproduction;
they are not additional patches to apply on the r5 default.

| Option / layer | Frozen base | QEMU cases |
| --- | --- | --- |
| --experimental-owner | r4 + owner | 7 |
| --experimental-module | r4 + owner/module | 8 |
| --experimental-alias | r4 + owner/module/alias | 9 |
| --experimental-teardown | r4 + all four layers | 12 |

Default preparation selects r5 and all twelve cases. Actual M4/legacy objects
compile and source replay matches the tests. Full r5 packaging, actual module
unload and native M4 remain open. The retained 0002 retention prototype is
byte-identical to compatibility 0002.
