# M-Series Image Studio

Native GTK 4 + Granite 7 image-studio prototype for ElementaryOS_MSeries.

The first slice provides a guided creation workspace, prompt-type picker, optional
prompt help through the already-running local M-Series assistant, model/LoRA and
batch controls, three guided workflow presets, a saved-recipe library, and live
memory/render-device reporting. Recipes persist prompt, prompt type, workflow,
model/LoRA identifiers, dimensions, batch, seed and tags. `GenerationOutputStore`
provides PNG plus JSON-sidecar persistence, and the Library reads those outputs
with bounded thumbnails. No image-engine adapter is wired yet. The app never
starts a local model worker.

Generation stays disabled until a specific image engine/model/size tuple has a
measured peak-memory budget and has been qualified on the target Vulkan stack.
The prompt helper only contacts the already-running local M-Series text assistant
and shows an editable suggestion for review before changing the prompt.

```sh
meson setup build mseries/image-studio
meson compile -C build
meson test -C build --print-errorlogs
```

Headless UI smoke for the requested adult streamer-series prompt:

```sh
test_data_home=$(mktemp -d)
M_SERIES_IMAGE_STUDIO_TEST_PROMPT='Alexandra Daddario portrayed as a 22-year-old adult college student and modern livestream creator in a three-image editorial character series: hosting a relaxed gaming stream, recording a campus-day vlog, and editing a video in a bright campus cafe. Casual clothing, friendly expression, natural light, consistent identity, no sexualization.' \
M_SERIES_IMAGE_STUDIO_TEST_WORKFLOW='Prompt type study' \
M_SERIES_IMAGE_STUDIO_TEST_SAVE_RECIPE=1 \
M_SERIES_IMAGE_STUDIO_SCREENSHOT=/tmp/image-studio-smoke.png \
M_SERIES_IMAGE_STUDIO_EXIT_AFTER=4 \
XDG_DATA_HOME="$test_data_home" xvfb-run -a ./build/mseries-image-studio
```

The test-only launch hooks also include `M_SERIES_IMAGE_STUDIO_TEST_PAGE=library`
to inspect saved recipes and generated-output metadata. Recipe JSON is saved under
`$XDG_DATA_HOME/mseries-image-studio/recipes`; image PNGs and metadata sidecars
are saved under `$XDG_DATA_HOME/mseries-image-studio/images` when a qualified
engine returns an image.

## Current limit

No image-engine adapter or diffusion runtime has yet been qualified on the
M-Series ARM64/Vulkan stack.
On the implementation host, `mseries-ai-everyday.service` was failed, no local
image or text API endpoint was listening, and the Hugging Face cache contained the
Qwen text model but no diffusion model. The UI, recipe flow and output metadata
store were tested; no AI image was generated. Choosing and qualifying the engine,
model and LoRA remains necessary before the requested streamer-series render.
