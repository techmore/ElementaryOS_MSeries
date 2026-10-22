This unselected candidate applies after the exact public Gravity Mesa PR1 head
`208d4a484459a12c77bf073362613f842288c2e0`. It is not part of the reviewed Mesa
package or baseline image. The preceding PR adds the low-address rodata mirror;
this follow-up handles its allocation failure without substituting a descriptor
address in the 1-TiB executable aperture.

The patch factors shader binary allocation, propagates executable/mirror
allocation failures through both existing Vulkan compile/deserialization error
paths, and checks the mirror's entire copied extent against the 40-bit limit.
It removes the high-address fallback from fast linking. Existing API error
paths destroy partially initialized shaders and unreference both BOs; that is
source-reviewed behavior, not an API fault-injection result.

Before applying, check `src/asahi/vulkan/hk_shader.c` against the manifest's
`before_sha256`. Apply with zero fuzz and require `after_sha256`; the patch itself
must match `patch_sha256`. Do not apply to selected 87ac51d without all eight PR
commits. Do not modify a source tree while its build is running.

The native test extracts the helper verbatim from the patched source and
compiles it with mock BO allocation/address inputs, ASan and UBSan:

```
python3 mseries/m4-mini/testing/mesa/test-rodata-upload.py \
  --source PATH_TO_PATCHED_HK_SHADER_C --output NEW_DIRECTORY
```

Eight cases cover successful copying, no-rodata behavior, each allocation
failure, the address boundary, extent overflow and the last fitting extent.
A false-success negative is detected by the allocation-failure assertion.
This does not exercise real DRM allocation, Vulkan API destruction, firmware,
GPU rendering or an M4. Full-driver compilation and the proposal's helper
uniformity/compositor semantics remain separate gates. No stack promotion is
implied by these helper tests. Mesa source licensing remains MIT; the testing
harness is GPL-3.0-or-later.
