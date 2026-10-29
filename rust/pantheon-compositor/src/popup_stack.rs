//! Stacking of xdg popups above every toplevel, as Gala does.
//!
//! smithay's [`Window`] renders its xdg popups (menus, tooltips, popovers) together
//! with its toplevel, so `space_render_elements` draws a window's popups at that
//! window's place in the stack. A menu of a window that sits lower in the stack
//! was therefore clipped by a higher neighbour (a snapped window, a keep-above
//! surface, a panel) until the lower window was clicked. Gala and Mutter draw all
//! popups in a layer above every window instead.
//!
//! [`stacked_render_elements`] builds the output's element list itself: first every
//! popup of every mapped window (top-most window first, newest popup first), then
//! every toplevel without its popups. Because the toplevel pass renders the toplevel
//! surface tree only, no popup is drawn twice.
//!
//! [`popup_under`] is the matching hit test, so a popup that now draws above a
//! neighbour also receives the pointer instead of the neighbour it covers.

use crate::corner_render::{Clipper, RoundedClip};
use smithay::{
    backend::renderer::{
        ImportAll, ImportMem, Renderer, Texture,
        element::{
            AsRenderElements, Kind,
            memory::MemoryRenderBufferRenderElement,
            surface::{WaylandSurfaceRenderElement, render_elements_from_surface_tree},
        },
    },
    desktop::{PopupManager, Space, Window, WindowSurfaceType, utils::under_from_surface_tree},
    output::Output,
    reexports::wayland_server::protocol::wl_surface::WlSurface,
    utils::{Logical, Point, Rectangle, Scale},
};

/// A mapped window with its render location (space coordinates of the top-left
/// corner of its surface tree, before the geometry offset).
struct StackEntry<'a> {
    window: &'a Window,
    render_location: Point<i32, Logical>,
}

/// Every mapped window of `space`, top-most first, with its render location.
fn stack(space: &Space<Window>) -> Vec<StackEntry<'_>> {
    space
        .elements()
        .rev()
        .filter_map(|window| {
            let location = space.element_location(window)?;
            Some(StackEntry {
                window,
                render_location: location - window.geometry().loc,
            })
        })
        .collect()
}

/// Bounding box of `entry` in space coordinates, popups included.
fn bbox(entry: &StackEntry<'_>) -> Rectangle<i32, Logical> {
    let mut bbox = entry.window.bbox_with_popups();
    bbox.loc += entry.render_location;
    bbox
}

/// Offset of `popup` from its window's render location, matching
/// smithay's `Window::render_elements` and `Window::surface_under`.
fn popup_offset(
    window: &Window,
    popup: &smithay::desktop::PopupKind,
    location: Point<i32, Logical>,
) -> Point<i32, Logical> {
    window.geometry().loc + location - popup.geometry().loc
}

/// Render elements for `output`, top-most first: every popup of every mapped window,
/// then every toplevel. Windows outside the output are skipped. An output that is not
/// mapped to the space yields no elements, like `space_render_elements`.
///
/// With a `clipper` (the built-in output), popups are clipped to the popover corner radius
/// and toplevels to the radii the corner policy gives their geometry.
///
/// `frame` returns a window's server-side frame (see `decorations.rs`): its outer rect in
/// space coordinates and its title-bar elements, given the window's own geometry rect. A
/// framed window is rounded as one shape with its frame.
pub fn stacked_render_elements<R, C>(
    renderer: &mut R,
    space: &Space<Window>,
    output: &Output,
    alpha: f32,
    clipper: Option<&Clipper<'_>>,
    frame: &mut crate::decorations::FrameSource<'_, R>,
) -> Vec<C>
where
    R: Renderer + ImportAll + ImportMem,
    R::TextureId: Texture + Clone + 'static,
    C: From<WaylandSurfaceRenderElement<R>>
        + From<RoundedClip<WaylandSurfaceRenderElement<R>>>
        + From<MemoryRenderBufferRenderElement<R>>
        + From<RoundedClip<MemoryRenderBufferRenderElement<R>>>,
{
    let Some(output_geometry) = space.output_geometry(output) else {
        return Vec::new();
    };
    let scale = Scale::from(output.current_scale().fractional_scale());
    let visible = stack(space)
        .into_iter()
        .filter(|entry| output_geometry.overlaps(bbox(entry)))
        .collect::<Vec<_>>();
    let physical_location = |entry: &StackEntry<'_>| {
        (entry.render_location - output_geometry.loc).to_physical_precise_round(scale)
    };

    let mut elements: Vec<C> = Vec::new();
    for entry in &visible {
        // XWayland windows have no xdg popups; their menus are override-redirect
        // windows that the space already keeps at `RenderZindex::Overlay`.
        let Some(toplevel) = entry.window.toplevel() else {
            continue;
        };
        let location = physical_location(entry);
        for (popup, popup_location) in PopupManager::popups_for_surface(toplevel.wl_surface()) {
            let offset =
                popup_offset(entry.window, &popup, popup_location).to_physical_precise_round(scale);
            let tree: Vec<WaylandSurfaceRenderElement<R>> = render_elements_from_surface_tree(
                renderer,
                popup.wl_surface(),
                location + offset,
                scale,
                alpha,
                Kind::Unspecified,
            );
            match clipper {
                Some(clipper) => {
                    let geometry = popup.geometry();
                    let rect = Rectangle::new(
                        entry.render_location
                            + popup_offset(entry.window, &popup, popup_location)
                            + geometry.loc,
                        geometry.size,
                    );
                    elements.extend(clipper.wrap(tree, rect, clipper.popup_radii(rect)));
                }
                None => elements.extend(tree.into_iter().map(C::from)),
            }
        }
    }

    for entry in &visible {
        let location = physical_location(entry);
        let tree: Vec<WaylandSurfaceRenderElement<R>> = match entry.window.toplevel() {
            Some(toplevel) => render_elements_from_surface_tree(
                renderer,
                toplevel.wl_surface(),
                location,
                scale,
                alpha,
                Kind::Unspecified,
            ),
            // `Window::render_elements` only delegates to the X11 surface here.
            None => entry
                .window
                .render_elements(renderer, location, scale, alpha),
        };
        let geometry = entry.window.geometry();
        let content = Rectangle::new(entry.render_location + geometry.loc, geometry.size);
        let (shape, decoration) = match frame(renderer, entry.window, content) {
            Some((outer, elements)) => (outer, elements),
            None => (content, Vec::new()),
        };
        match clipper {
            Some(clipper) => {
                let radii = clipper.toplevel_radii(entry.window, shape);
                elements.extend(clipper.wrap(tree, shape, radii));
                elements.extend(clipper.wrap(decoration, shape, radii));
            }
            None => {
                elements.extend(tree.into_iter().map(C::from));
                elements.extend(decoration.into_iter().map(C::from));
            }
        }
    }
    elements
}

/// The popup surface under `point` (space coordinates), searched across every
/// window top-most first, in the same order [`stacked_render_elements`] draws them.
/// Returns the owning window, the surface and the surface's location.
pub fn popup_under(
    space: &Space<Window>,
    point: Point<f64, Logical>,
) -> Option<(Window, WlSurface, Point<i32, Logical>)> {
    stack(space).into_iter().find_map(|entry| {
        if !bbox(&entry).to_f64().contains(point) {
            return None;
        }
        let toplevel = entry.window.toplevel()?;
        let local = point - entry.render_location.to_f64();
        PopupManager::popups_for_surface(toplevel.wl_surface()).find_map(|(popup, location)| {
            under_from_surface_tree(
                popup.wl_surface(),
                local,
                popup_offset(entry.window, &popup, location),
                WindowSurfaceType::ALL,
            )
            .map(|(surface, surface_location)| {
                (
                    entry.window.clone(),
                    surface,
                    surface_location + entry.render_location,
                )
            })
        })
    })
}
