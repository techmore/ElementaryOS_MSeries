# Elementary M4 compatibility backports

These are elementary adaptations, separate from the unchanged Gravity packaging
exports in ../patches. The scheduler patch derives from Aurora commits 6c2d17f
and 0d1871c, preserving both source links in its header. Gravity uses the same
uninitialized C scheduler storage, including the M4 g16_drm constructor.

Only the initialization changes are ported to the older API. Aurora's newer
owner/lifetime refactor and KUnit suite require separate review; no G17 test or
native M4 runtime success is claimed. Hash gates bind the patch and result.
