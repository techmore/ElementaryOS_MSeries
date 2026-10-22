This candidate is unselected. The source file is unchanged by the three-phase
corrected Mesa5 recipe, but that complete recipe is the tested prerequisite.
Do not rewrite the immutable revision-5 snapshot or promote its package based
solely on AGX/llvmpipe test success.

PR1 enables texture_external. Mesa maps this to OES_EGL_image_external and its
ESSL3 extension, independently of ordinary OES_EGL_image, which is already
initialized true. GL_TEXTURE_2D and GL_TEXTURE_EXTERNAL_OES imports check those
separate flags. The claim therefore includes external-sampler shaders.

A reproducible diagnostic links the actual Apple9 compiler: the basic 2D shader
compiles, while the matching external shader is rejected. This is a compiler
capability finding, not a reproduced GPU/rendering failure. Use
`testing/mesa/check-external-sampler.py --mesa-workspace BUILT_WORKSPACE --output NEW_DIR`
under mseries/m4-mini to reproduce the uncorrected behavior.

The candidate normalizes non-array/non-shadow external dimensions to the same
2D descriptor path at both native texture-lowering entry points. Existing API
validation, sampler restrictions and state-tracker format/plane conversion stay
responsible for their contracts. External arrays/shadow inputs remain rejected.
Exact before/after/patch hashes are in manifest.json. A targeted real native
object plus the prior combined NIR libraries compiles the basic external sample
to the same 282 bytes as its 2D reference. All seven temporarily installed source
files were restored; no cached compiler object or full driver was replaced.

This is not complete external-image support. The ESSL3 contract includes ordinary
and projective sampling, textureSize and texelFetch, with nearest/linear filtering
and the API's external-sampler restrictions. Six constant-coordinate compiler comparisons now pass for nearest, linear, bias,
projective sampling, texel fetch and size query, with exact external/2D binary
equality. Run testing/mesa/test-external-sampler-matrix.py with --mesa-workspace,
--native-object (the separately compiled candidate object) and --output. This
runner does not build or authenticate that supplied object; its receipt hashes it.
Dynamic inputs, malformed-input controls, full driver rebuild, versioned recipe/package and native
EGL/DRM import, YUV, synchronization and GPU output remain open. Do not substitute
only the passing basic sample for those requirements.

Primary specification:
https://registry.khronos.org/OpenGL/extensions/OES/OES_EGL_image_external_essl3.txt
The backend source and tests retain Mesa's MIT attribution; diagnostic Python
uses GPL-3.0-or-later. No Apple firmware or GPU execution is involved here.
