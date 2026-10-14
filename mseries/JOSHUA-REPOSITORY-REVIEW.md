# Joshua Warren repository review — 2026-10-12

All **148 public repositories** returned by GitHub pagination were screened.
**144 had accessible README content**; four did not provide usable README content.
The complete inventory below records a disposition for every repository. Public
metadata and a SHA-256 of each retrieved README are preserved in
[JOSHUA-REPOSITORY-INVENTORY.json](JOSHUA-REPOSITORY-INVENTORY.json).

This is a compatibility/value screen, not a claim that all 148 codebases were
compiled, tested or audited. Priority projects received additional review of
installation docs and selected integration code. The MLX/Coreglass components
were installed and checked separately; see [local AI receipts](local-ai/receipts/2026-10-12.md).
Repository update timestamps and fork descriptions do not establish support.

## Installed local troubleshooting enhancement

Revalidated GitHub's public repository names on 2026-10-12: all 148 match the
recorded inventory, with no additions or removals. Joshua's Linux MLX runtime
now powers our pinned Gemma 4 E4B local crash/log assistant, native GTK app and
Wingpanel robot menu. See [setup and behavior](local-ai/README.md) and
[verification receipts](local-ai/receipts/2026-10-12-troubleshooter.md).

## Recommended build priorities

1. **Keep MLX, private Honeykrisp and Coreglass.** Already integrated. Preserve
   elementary's system Mesa and native desktop; use Compact at 4096 context.
2. **Prepare a separate M1 Pro ANE trial.** Current [omarchy-ane README](https://github.com/joshuaswarren/omarchy-ane) now
   lists T6000/H13J as tested, with bind and exact fp16 execution evidence.
   This supersedes older indexed untested tables, not our own hardware status:
   this machine still has no ANE node, module or accel0 device. Its kernel has
   `CONFIG_APPLE_SEP=y`; SEP is unrelated to ANE and does not establish Touch ID
   enrollment/login support. ANE needs matching kernel headers/driver and the
   board's device tree enabled, with rollback and post-boot smoke checks.
   No ANE module, device tree or boot artifact was changed by this review.
3. **Benchmark before adding engines.** Coreglass refuses this active desktop's
   load above 0.5; do not force an idle benchmark. Use inference-fleet's fixed
   models, prompts, revisions and repetitions. Later compare oMLX/MLX serve
   through their documented Linux integrations. Their default macOS README
   requirements alone neither prove nor disprove those separate Linux ports.
4. **Extend native CodexBar selectively.** Provider collectors may add value,
   but first compare upstream CodexBar coverage. Avoid a second credential
   store or quota values inferred from absent API fields. Its Quickshell UI is
   a design/data reference, not a replacement for Wingpanel. Middle-click
   refresh is ported; the native dropdown is now approximately 25% smaller.
5. **Treat metal2vk and extra compute engines as research.** Kernel translation
   is not full application compatibility. The current MLX engine matrix names
   Linux routes for llama.cpp, oMLX and mlx-serve, plus model-specific video and
   networking experiments. Results on M1 Max/M2 Max/96 GB hosts are not M1 Pro
   performance or memory guarantees. Start with a small fixed model here.
6. **Optional later applications:** Omalight/LightCraft photo editing, Linux
   iOS tooling, and Apple Reminders/iMessage bridges. The bridges need another
   running macOS host when they depend on Apple's Mac-side message database.
   **Correction (2026-10-13):** that is not universal. Tether is a separate
   direct iPhone-to-Linux candidate with SMS/iMessage and OTP handoff and no
   Mac relay; see [Tether continuity](TETHER-CONTINUITY.md). It is not yet
   source/license-audited or qualified on this M1 Pro. Media/panel plugins
   require a native frontend port.

## Boundaries and non-goals

- No mass installation of these repositories, Arch package repository enablement,
  kernel upgrade, authentication enrollment or cloud credential configuration.
- No reviewed repository was identified as a ready bare-metal M1 Pro Touch ID
  login package. Track SEP/Touch ID work separately from Joshua's ANE stack.
- Cluster inference requires additional hosts and network measurements. It is
  useful for capacity experiments, not automatically faster than local inference.
- Planned/spec-phase projects, superseded snapshots, macOS-only terminals and
  unrelated commerce/home integrations should not enter the base OS image.
- Fresh source documents change faster than search indexes; recheck pinned
  source/release requirements before each port.

## Full inventory

Each project name links to the primary repository. “Optional” does not imply
ARM64 installation has been qualified on this machine.

| Repository | Disposition | Value / limitation for our build |
| --- | --- | --- |
| [remnic](https://github.com/joshuaswarren/remnic) | Optional agent tooling | Current judge/live-runner docs specify Linux x64 qualification; verify ARM64 before adopting. |
| [metal2vk](https://github.com/joshuaswarren/metal2vk) | Research | Metal compute-to-Vulkan translation; kernel correctness is not whole-model qualification or Metal graphics compatibility. |
| [omarchy-apple-dev](https://github.com/joshuaswarren/omarchy-apple-dev) | Optional developer tools | Linux iOS/Flutter build and device deploy workflow; port apt/toolchain dependencies and validate SDK/account requirements. |
| [omarchy-mlx](https://github.com/joshuaswarren/omarchy-mlx) | Use now | Installed v0.7.32; private Vulkan driver and compact Qwen 4B API verified. |
| [mil-hwx-compiler](https://github.com/joshuaswarren/mil-hwx-compiler) | Research | ANE compiler prerequisite; keep target-specific validation and avoid assuming M1/M4 program compatibility. |
| [omarchy-ane](https://github.com/joshuaswarren/omarchy-ane) | Next hardware trial | Current README promotes M1 Pro/T6000 to tested; our kernel lacks its ANE device/driver; requires a boot-chain-aware port. |
| [coreglass](https://github.com/joshuaswarren/coreglass) | Use now | Installed; local target patch verified; benchmark only when quiet. |
| [Macintosh-Skeletal-Filled](https://github.com/joshuaswarren/Macintosh-Skeletal-Filled) | Optional appearance | Styling/font reference; preserve elementary defaults unless explicitly selecting a theme. |
| [omarchy-cluster](https://github.com/joshuaswarren/omarchy-cluster) | Later multi-machine work | Potential shared model capacity across hosts; documented large-model runs can be slow; unnecessary for a single laptop. |
| [simple-magento-vagrant](https://github.com/joshuaswarren/simple-magento-vagrant) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [php5.4-vagrant-env](https://github.com/joshuaswarren/php5.4-vagrant-env) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [n98-magerun](https://github.com/joshuaswarren/n98-magerun) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [magento2](https://github.com/joshuaswarren/magento2) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [magento-elasticsearch](https://github.com/joshuaswarren/magento-elasticsearch) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [magehero](https://github.com/joshuaswarren/magehero) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [MageVagrant](https://github.com/joshuaswarren/MageVagrant) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [bdd-box](https://github.com/joshuaswarren/bdd-box) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [bdd](https://github.com/joshuaswarren/bdd) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [BlackfireMagentoVagrant](https://github.com/joshuaswarren/BlackfireMagentoVagrant) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [magento-uses-this](https://github.com/joshuaswarren/magento-uses-this) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [magento-userscripts](https://github.com/joshuaswarren/magento-userscripts) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [MagentoDiscuss](https://github.com/joshuaswarren/MagentoDiscuss) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [Magento-SOAP-API-Library](https://github.com/joshuaswarren/Magento-SOAP-API-Library) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [magemalt5](https://github.com/joshuaswarren/magemalt5) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [magemalt](https://github.com/joshuaswarren/magemalt) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [magescotch5](https://github.com/joshuaswarren/magescotch5) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [magescotch](https://github.com/joshuaswarren/magescotch) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [ane-linux-experiments](https://github.com/joshuaswarren/ane-linux-experiments) | Research | Hardware probes and receipts; use production driver/runtime for normal use, not raw experiments. |
| [modelctl](https://github.com/joshuaswarren/modelctl) | Research | Generic workload/budget contracts and synthetic fixtures; not a ready end-user quota manager. |
| [sovereign-inference](https://github.com/joshuaswarren/sovereign-inference) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [magento-adobe-commerce-graphql-cache-fix](https://github.com/joshuaswarren/magento-adobe-commerce-graphql-cache-fix) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [magento-adobe-commerce-base](https://github.com/joshuaswarren/magento-adobe-commerce-base) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [magento-adobe-commerce-ai-content-generator-mass-actions](https://github.com/joshuaswarren/magento-adobe-commerce-ai-content-generator-mass-actions) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [magento-adobe-commerce-ai-content-generator-core](https://github.com/joshuaswarren/magento-adobe-commerce-ai-content-generator-core) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [magento-adobe-commerce-admin-action-notification](https://github.com/joshuaswarren/magento-adobe-commerce-admin-action-notification) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. No usable README was returned. |
| [omarchy-ytmini](https://github.com/joshuaswarren/omarchy-ytmini) | Optional UI port | Omarchy/Quickshell integration; adapt frontend to elementary instead of loading the Omarchy shell. |
| [omarchy-somafm](https://github.com/joshuaswarren/omarchy-somafm) | Optional UI port | Omarchy/Quickshell integration; adapt frontend to elementary instead of loading the Omarchy shell. |
| [omarchy-hardstop](https://github.com/joshuaswarren/omarchy-hardstop) | Skip until implemented | Spec-phase quitting-time panel concept. |
| [infinitty-omp](https://github.com/joshuaswarren/infinitty-omp) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [remnic-canvas](https://github.com/joshuaswarren/remnic-canvas) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [omp-unlazy-guard](https://github.com/joshuaswarren/omp-unlazy-guard) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [omarchy-theme-red-wedge](https://github.com/joshuaswarren/omarchy-theme-red-wedge) | Optional appearance | Styling/font reference; preserve elementary defaults unless explicitly selecting a theme. |
| [omarchy-theme-legal-tender](https://github.com/joshuaswarren/omarchy-theme-legal-tender) | Optional appearance | Styling/font reference; preserve elementary defaults unless explicitly selecting a theme. |
| [omarchy-remnic](https://github.com/joshuaswarren/omarchy-remnic) | Optional UI port | Omarchy/Quickshell integration; adapt frontend to elementary instead of loading the Omarchy shell. |
| [omarchy-plexmini](https://github.com/joshuaswarren/omarchy-plexmini) | Optional UI port | Omarchy/Quickshell integration; adapt frontend to elementary instead of loading the Omarchy shell. |
| [omarchy-shiplog](https://github.com/joshuaswarren/omarchy-shiplog) | Research desktop concept | Spec-phase description; inspect implementation before adopting a logging workflow. |
| [omarchy-inference-fleet](https://github.com/joshuaswarren/omarchy-inference-fleet) | Next performance trial | Pinned single-node benchmark contracts complement Coreglass; adapt model memory limits to our 32 GB laptop. |
| [omarchy-fleet-shepherd](https://github.com/joshuaswarren/omarchy-fleet-shepherd) | Optional UI port | Omarchy/Quickshell integration; adapt frontend to elementary instead of loading the Omarchy shell. |
| [omarchy-chase](https://github.com/joshuaswarren/omarchy-chase) | Skip until implemented | README explicitly says planning and nothing installable yet. |
| [omarchy-apple-bridge](https://github.com/joshuaswarren/omarchy-apple-bridge) | Optional external Mac integration | Reminders bridge requires a running macOS gateway plus CalDAV; not standalone Linux iCloud sync. |
| [omarchy-agent-usage-more](https://github.com/joshuaswarren/omarchy-agent-usage-more) | Port selectively | Provider collectors may extend usage coverage; compare upstream CodexBar first, avoid duplicated authentication and unknown quota estimates. |
| [walk-cue](https://github.com/joshuaswarren/walk-cue) | Optional personal app | Potential user application; unrelated to the current M1 Pro hardware and inference goals. |
| [say-house](https://github.com/joshuaswarren/say-house) | Optional personal app | Potential user application; unrelated to the current M1 Pro hardware and inference goals. |
| [omp-pulse](https://github.com/joshuaswarren/omp-pulse) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [omaloop](https://github.com/joshuaswarren/omaloop) | Optional UI port | Omarchy/Quickshell integration; adapt frontend to elementary instead of loading the Omarchy shell. |
| [joshuaswarren](https://github.com/joshuaswarren/joshuaswarren) | Reference | Author profile and project map, not an installable component. |
| [codexbar-omarchy](https://github.com/joshuaswarren/codexbar-omarchy) | Port selectively | Quickshell frontend reference; middle-click refresh ported, dropdown reduced about 25%; retain native Wingpanel. |
| [plantoeat-skylight-sync](https://github.com/joshuaswarren/plantoeat-skylight-sync) | Optional personal app | Potential user application; unrelated to the current M1 Pro hardware and inference goals. |
| [openclaw-skylight](https://github.com/joshuaswarren/openclaw-skylight) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [pyskylight](https://github.com/joshuaswarren/pyskylight) | Optional personal app | Potential user application; unrelated to the current M1 Pro hardware and inference goals. |
| [release-agent-sentinel](https://github.com/joshuaswarren/release-agent-sentinel) | Optional infrastructure | Useful upstream release detection and compatibility issue workflow; external issue creation requires deliberate configuration. |
| [tower](https://github.com/joshuaswarren/tower) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [dealt](https://github.com/joshuaswarren/dealt) | Optional personal app | Potential user application; unrelated to the current M1 Pro hardware and inference goals. |
| [allward](https://github.com/joshuaswarren/allward) | Not portable as shipped | Native macOS 26 Swift/Metal terminal; no elementary binary. |
| [cyrus-omp-e2e](https://github.com/joshuaswarren/cyrus-omp-e2e) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [oh-my-pi](https://github.com/joshuaswarren/oh-my-pi) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [qmd](https://github.com/joshuaswarren/qmd) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [mlx-lm](https://github.com/joshuaswarren/mlx-lm) | Later compute integration | Use the pinned Linux compatibility path in omarchy-mlx; an upstream macOS wheel is not a Linux GPU port. |
| [Phosphene](https://github.com/joshuaswarren/Phosphene) | Later compute research | Heavy MLX video workloads; verify Linux patch set and memory qualification; not appropriate as the initial 32 GB model. |
| [uzu](https://github.com/joshuaswarren/uzu) | Research | Custom-kernel engine candidate for metal2vk; kernel compilation does not prove full inference support. |
| [mlx-serve-gguf](https://github.com/joshuaswarren/mlx-serve-gguf) | Research | GGUF custom Metal kernels need the Linux translation/build integration; no drop-in elementary installer. |
| [darktable](https://github.com/joshuaswarren/darktable) | Optional desktop app | Linux photo workflow already available independently; a personal fork needs a specific patch benefit. |
| [lightcraft](https://github.com/joshuaswarren/lightcraft) | Optional desktop app | Cross-platform photo engine used by Omalight; prefer its supported upstream build path. |
| [omalight](https://github.com/joshuaswarren/omalight) | Optional desktop app | Linux photo editor with local/remote Rust engine; build ARM64 and test Vulkan memory use before recommending. |
| [TensorFold](https://github.com/joshuaswarren/TensorFold) | Later compute research | Linux video path is documented in omarchy-mlx packaging, with a 96 GB test host; not our laptop capacity. |
| [mlx-audio](https://github.com/joshuaswarren/mlx-audio) | Later compute integration | Use the pinned Linux compatibility path in omarchy-mlx; an upstream macOS wheel is not a Linux GPU port. |
| [mlx-vlm](https://github.com/joshuaswarren/mlx-vlm) | Later compute integration | Use the pinned Linux compatibility path in omarchy-mlx; an upstream macOS wheel is not a Linux GPU port. |
| [MCDMA](https://github.com/joshuaswarren/MCDMA) | Later multi-machine work | Linux Soft-RoCE research exists; distinct from native Thunderbolt networking and not a dock-display fix. |
| [sushi](https://github.com/joshuaswarren/sushi) | Later compute research | Linux work is on a separate branch; engine matrix still lists in-progress driver work. |
| [ai-data-extraction](https://github.com/joshuaswarren/ai-data-extraction) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [omarchy-mac-installer](https://github.com/joshuaswarren/omarchy-mac-installer) | Boot/install reference | Relevant to installation/recovery; requires exact model and boot-chain validation, not a desktop package install. |
| [aurora-linux-tbnet](https://github.com/joshuaswarren/aurora-linux-tbnet) | Research | Kernel fork candidate for networking; generic README does not establish T6000 dock-video or ANE support; inspect exact branch patches. |
| [omarchy-mac-pkgs](https://github.com/joshuaswarren/omarchy-mac-pkgs) | Port selectively | Boot/package staging and verification patterns; translate Arch hooks into our Ubuntu plus Arch-kernel boot arrangement. |
| [xtool](https://github.com/joshuaswarren/xtool) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [OpenAppleMacros](https://github.com/joshuaswarren/OpenAppleMacros) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [AssetKit](https://github.com/joshuaswarren/AssetKit) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [u-boot](https://github.com/joshuaswarren/u-boot) | Boot/install reference | Relevant to installation/recovery; requires exact model and boot-chain validation, not a desktop package install. |
| [aurora-u-boot](https://github.com/joshuaswarren/aurora-u-boot) | Boot/install reference | Relevant to installation/recovery; requires exact model and boot-chain validation, not a desktop package install. |
| [asahi-installer](https://github.com/joshuaswarren/asahi-installer) | Boot/install reference | Relevant to installation/recovery; requires exact model and boot-chain validation, not a desktop package install. |
| [mesa-1](https://github.com/joshuaswarren/mesa-1) | Use now | honeykrisp-omarchy branch supplies our private compute driver; default branch description is just a mirror. |
| [omarchy-mlx-fork-2026-09](https://github.com/joshuaswarren/omarchy-mlx-fork-2026-09) | Skip superseded | Historical MLX fork; use current overlay/patch/release project. |
| [omarchy-pkgs](https://github.com/joshuaswarren/omarchy-pkgs) | Reference | Pinned sources and edge/rc/stable promotion patterns; never install its Arch binaries into elementary. |
| [CnC_Remastered_Collection](https://github.com/joshuaswarren/CnC_Remastered_Collection) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [ANEForge](https://github.com/joshuaswarren/ANEForge) | Research | macOS ANE research; not a Linux driver or replacement for omarchy-ane. |
| [mlx-serve](https://github.com/joshuaswarren/mlx-serve) | Next engine comparison | Evaluate the Linux build/patch route in the engine matrix; default desktop app is macOS-specific. |
| [omlx](https://github.com/joshuaswarren/omlx) | Next engine comparison | Linux integration is in omarchy-mlx docs/omlx-linux.md; default upstream README describes macOS requirements. |
| [omarchy-bongocat](https://github.com/joshuaswarren/omarchy-bongocat) | Optional UI port | Omarchy/Quickshell integration; adapt frontend to elementary instead of loading the Omarchy shell. |
| [blip](https://github.com/joshuaswarren/blip) | Optional external Mac integration | iMessage needs an awake macOS/SSH gateway; Quickshell frontend needs a Pantheon port. |
| [omarchy-mac](https://github.com/joshuaswarren/omarchy-mac) | Reference | Read current upstream omacom rather than treating a personal fork as authoritative. |
| [hookecho](https://github.com/joshuaswarren/hookecho) | Optional desktop app | Browser version may fit; listed Linux packages are amd64/x86_64, not proof of ARM64 availability. |
| [omastorm](https://github.com/joshuaswarren/omastorm) | Optional UI port | Omarchy/Quickshell integration; adapt frontend to elementary instead of loading the Omarchy shell. |
| [omarchy-libane](https://github.com/joshuaswarren/omarchy-libane) | Skip superseded | Archived snapshot; maintained replacement is omarchy-ane. |
| [mesa](https://github.com/joshuaswarren/mesa) | Reference | Establish branch and patch ancestry; do not replace system Mesa based on repository name. |
| [omarchy-plugin-marketplace](https://github.com/joshuaswarren/omarchy-plugin-marketplace) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [agentyard-cli](https://github.com/joshuaswarren/agentyard-cli) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [openclaw-atlas](https://github.com/joshuaswarren/openclaw-atlas) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [watermarks-remover](https://github.com/joshuaswarren/watermarks-remover) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [Awesome-Agent-Memory](https://github.com/joshuaswarren/Awesome-Agent-Memory) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [awesome-mcp-servers](https://github.com/joshuaswarren/awesome-mcp-servers) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. No usable README was returned. |
| [infinitty](https://github.com/joshuaswarren/infinitty) | Not portable as shipped | Native Swift/Metal macOS terminal; plugin compatibility does not supply a Linux terminal. |
| [pageindex-ts](https://github.com/joshuaswarren/pageindex-ts) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [esphome-m5stickc-senseair-s8](https://github.com/joshuaswarren/esphome-m5stickc-senseair-s8) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [magento-adobe-commerce-openai-content-generator](https://github.com/joshuaswarren/magento-adobe-commerce-openai-content-generator) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [noop](https://github.com/joshuaswarren/noop) | Optional personal app | Potential user application; unrelated to the current M1 Pro hardware and inference goals. |
| [texas-electric-plan-finder](https://github.com/joshuaswarren/texas-electric-plan-finder) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [research](https://github.com/joshuaswarren/research) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [openclaw-langsmith](https://github.com/joshuaswarren/openclaw-langsmith) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [clawpatch](https://github.com/joshuaswarren/clawpatch) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [remnic-codereview](https://github.com/joshuaswarren/remnic-codereview) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [clawhub](https://github.com/joshuaswarren/clawhub) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [parameter-golf](https://github.com/joshuaswarren/parameter-golf) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [openclaw-pageindex](https://github.com/joshuaswarren/openclaw-pageindex) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [openclaw-keystone](https://github.com/joshuaswarren/openclaw-keystone) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [tabzen](https://github.com/joshuaswarren/tabzen) | Optional personal app | Potential user application; unrelated to the current M1 Pro hardware and inference goals. |
| [openclaw-tactician](https://github.com/joshuaswarren/openclaw-tactician) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [openclaw-patcher](https://github.com/joshuaswarren/openclaw-patcher) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [openclaw-mission-control](https://github.com/joshuaswarren/openclaw-mission-control) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [openclaw-smart-router](https://github.com/joshuaswarren/openclaw-smart-router) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [openclaw](https://github.com/joshuaswarren/openclaw) | Optional agent tooling | Separate developer/agent workflow; no direct hardware or Pantheon performance improvement established. |
| [omnivore](https://github.com/joshuaswarren/omnivore) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [highlight-summarizer](https://github.com/joshuaswarren/highlight-summarizer) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [solomon](https://github.com/joshuaswarren/solomon) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [obsidian-solomon-plugin](https://github.com/joshuaswarren/obsidian-solomon-plugin) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [pull-request-analysis](https://github.com/joshuaswarren/pull-request-analysis) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [hubitat_poolcontroller](https://github.com/joshuaswarren/hubitat_poolcontroller) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [homebridge-smartthings-v2](https://github.com/joshuaswarren/homebridge-smartthings-v2) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [teslacam](https://github.com/joshuaswarren/teslacam) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [SmartThingsPublic](https://github.com/joshuaswarren/SmartThingsPublic) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [ImagineAllTheTweets](https://github.com/joshuaswarren/ImagineAllTheTweets) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. No usable README was returned. |
| [JackSparrow](https://github.com/joshuaswarren/JackSparrow) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [devdocs](https://github.com/joshuaswarren/devdocs) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [slidelab](https://github.com/joshuaswarren/slidelab) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [scotch-box](https://github.com/joshuaswarren/scotch-box) | Exclude from OS build | Commerce/development demo or legacy provisioning; no Apple Silicon desktop optimization. |
| [sleep](https://github.com/joshuaswarren/sleep) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [arduino-yun-sensor-box](https://github.com/joshuaswarren/arduino-yun-sensor-box) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [googleanalyticsplus](https://github.com/joshuaswarren/googleanalyticsplus) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [eve-route](https://github.com/joshuaswarren/eve-route) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. |
| [rmcard202SnmpUtils](https://github.com/joshuaswarren/rmcard202SnmpUtils) | Exclude from current scope | Other application, integration, research or historical project; no direct M1 Pro elementary benefit established by this screen. No usable README was returned. |
