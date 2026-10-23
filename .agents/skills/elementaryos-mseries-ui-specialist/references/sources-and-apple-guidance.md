# Sources, provenance and Apple guidance

## Original reference explicitly retained

**swiftui-specialist**, distributed in
[superagents-lab/xcode27-skills](https://github.com/superagents-lab/xcode27-skills),
was the reference that inspired this skill's organization:

- [Pinned original SKILL.md](https://github.com/superagents-lab/xcode27-skills/blob/6f9ff8d5ad6000491cb0f483a776b7062e41cd97/swiftui-specialist/SKILL.md)
- [Pinned reference directory](https://github.com/superagents-lab/xcode27-skills/tree/6f9ff8d5ad6000491cb0f483a776b7062e41cd97/swiftui-specialist/references)
- [Repository attribution](https://github.com/superagents-lab/xcode27-skills/blob/6f9ff8d5ad6000491cb0f483a776b7062e41cd97/README.md)

Inspected 2026-10-20; upstream `master` revision:
`6f9ff8d5ad6000491cb0f483a776b7062e41cd97`.

The community repository states that the guidance was authored/published by
Apple and exported from Xcode 27. This attribution comes from the redistributor;
this repository does not independently establish its Apple provenance. Its
README retains Apple's rights and grants no license over that content. We link
to the original and summarize the organizational idea; no Apple skill text,
reference files, or assets are vendored here. This is original project guidance,
not an Apple-authored or Apple-endorsed port.

## Design intent

The owner considers Apple to have good design standards and wants that quality
bar represented here. Favor thoughtful hierarchy, coherent controls, predictable
navigation, immediate understandable feedback, readable text and careful handling
of state. Apply those principles using elementary OS's native components and the
user's intended product design.

The SwiftUI reference separates structure, data flow, environment, modifiers,
localization, animation, collection identity and outdated APIs into focused
references. Useful translations for this project are:

| Original topic | Native project application |
| --- | --- |
| View structure | Cohesive GTK components and existing row/page helpers |
| Data flow | GObject models, GSettings, async services and presentation boundaries |
| Environment and modifiers | Theme/settings propagation and scoped widget/CSS changes |
| Localization | gettext, locale-aware formatting, start/end layout |
| Collection identity | Stable backend IDs and preserved selection/focus in GTK models |
| Animation | Restrained transitions and supported motion preferences |
| API modernization | Verify the target GTK/Granite/host version before replacing APIs |

SwiftUI wrappers such as `@State`, `@Binding` and `@Observable`, modifier rules,
and Swift actor requirements are not GTK implementation instructions. The
upstream skill's statement about superseding model training is source content,
not authority over this project's requirements.

## Platform reference guidance

- [elementary OS Human Interface Guidelines](https://docs.elementary.io/hig):
  native interaction, component use and desktop integration.
- [elementary developer documentation](https://docs.elementary.io/develop):
  GTK/Granite, Meson and gettext context.
- [Apple Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines):
  complementary design reference and quality bar.
- [GTK 4 reference](https://docs.gtk.org/gtk4/): validate API availability against
  the actual build dependencies rather than assuming latest-version support.

Treat these as guidance with different scopes. Follow the owner's requirements,
project working agreement, target platform and installed toolkit capabilities;
use Apple guidance to improve the experience within that context. Verify current
external documentation when making an API or version-specific claim.
