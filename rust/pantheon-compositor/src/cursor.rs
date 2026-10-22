use smithay::{
    backend::{
        allocator::Fourcc,
        renderer::{
            ImportAll, ImportMem, Renderer, Texture,
            element::{
                Kind, Wrap,
                memory::{MemoryRenderBuffer, MemoryRenderBufferRenderElement},
                solid::{SolidColorBuffer, SolidColorRenderElement},
                surface::{WaylandSurfaceRenderElement, render_elements_from_surface_tree},
            },
        },
    },
    input::pointer::{CursorIcon, CursorImageAttributes, CursorImageStatus},
    render_elements,
    utils::{IsAlive, Logical, Point, Rectangle, Scale, Size, Transform},
    wayland::compositor::with_states,
};

use crate::PantheonCompositor;

/// Solid-colour overlay pieces kept across frames. A new `SolidColorBuffer`
/// every frame has a new id, so the damage tracker repaints it every frame
/// even when nothing changed; a kept buffer only damages when its size or
/// colour changes (or it moves).
#[derive(Default)]
pub(crate) struct SolidBuffers(
    std::cell::RefCell<std::collections::HashMap<(String, SolidSlot), SolidColorBuffer>>,
);

#[derive(Clone, Copy, Debug, Hash, PartialEq, Eq)]
pub(crate) enum SolidSlot {
    SnapPreview,
    /// The n-th rectangle of the shell OSD.
    Osd(u8),
}

impl SolidBuffers {
    /// The kept buffer for `slot` on `output`, updated to `size` and `color`.
    pub(crate) fn get(
        &self,
        output: &str,
        slot: SolidSlot,
        size: Size<i32, Logical>,
        color: [f32; 4],
    ) -> SolidColorBuffer {
        let mut buffers = self.0.borrow_mut();
        let buffer = buffers
            .entry((output.to_owned(), slot))
            .or_insert_with(|| SolidColorBuffer::new(size, color));
        // `update` only bumps the commit counter when something differs.
        buffer.update(size, color);
        buffer.clone()
    }
}

/// Physical pixel size of an output, as the wallpaper is scaled for it.
pub(crate) fn output_pixel_size(
    state: &PantheonCompositor,
    output: &smithay::output::Output,
) -> Option<(i32, i32)> {
    let geometry = state.space.output_geometry(output)?;
    let size = geometry
        .size
        .to_f64()
        .to_physical(output.current_scale().fractional_scale())
        .to_i32_round::<i32>();
    Some((size.w, size.h))
}

render_elements! {
    pub CursorRenderElement<R> where R: ImportAll + ImportMem;
    Surface=WaylandSurfaceRenderElement<R>,
    Memory=MemoryRenderBufferRenderElement<R>,
    Solid=SolidColorRenderElement,
    WrappedSurface=Wrap<WaylandSurfaceRenderElement<R>>,
    Animated=smithay::backend::renderer::element::utils::RelocateRenderElement<smithay::backend::renderer::element::utils::RescaleRenderElement<WaylandSurfaceRenderElement<R>>>,
}

/// Built-in pointer used only when the configured cursor theme cannot be read.
pub fn default_cursor_buffer() -> MemoryRenderBuffer {
    const WIDTH: usize = 16;
    const HEIGHT: usize = 20;
    let mut pixels = vec![0; WIDTH * HEIGHT * 4];

    for y in 0..HEIGHT {
        let (first_x, last_x) = match y {
            0..=12 => (0, y),
            13..=17 => (6, 9),
            _ => (6, 8),
        };
        for x in first_x..=last_x {
            // Build a black outline around the white pointer body and stem.
            let outline = x == first_x || x == last_x || y == 12 || y == 18;
            let color = if outline {
                [0, 0, 0, 255]
            } else {
                [255, 255, 255, 255]
            };
            let offset = (y * WIDTH + x) * 4;
            pixels[offset..offset + 4].copy_from_slice(&color);
        }
    }

    MemoryRenderBuffer::from_slice(
        &pixels,
        Fourcc::Argb8888,
        (WIDTH as i32, HEIGHT as i32),
        1,
        Transform::Normal,
        None,
    )
}

pub fn render_cursor_elements<R>(
    renderer: &mut R,
    state: &PantheonCompositor,
    output: &smithay::output::Output,
) -> Vec<CursorRenderElement<R>>
where
    R: Renderer + ImportAll + ImportMem,
    R::TextureId: Texture + Clone + Send + 'static,
{
    let Some(output_geometry) = state.space.output_geometry(output) else {
        return Vec::new();
    };
    let pointer_location = state.seat.get_pointer().unwrap().current_location();
    if !output_geometry.to_f64().contains(pointer_location) {
        return Vec::new();
    }

    let scale = Scale::from(output.current_scale().fractional_scale());
    let cursor_status = if state.screenshot_selection.borrow().active() {
        CursorImageStatus::Named(CursorIcon::Crosshair)
    } else {
        state.cursor_status.clone()
    };
    let mut elements = match &cursor_status {
        CursorImageStatus::Hidden => Vec::new(),
        CursorImageStatus::Surface(surface) if surface.alive() => {
            let hotspot = with_states(surface, |states| {
                states
                    .data_map
                    .get::<std::sync::Mutex<CursorImageAttributes>>()
                    .and_then(|attributes| {
                        attributes.lock().ok().map(|attributes| attributes.hotspot)
                    })
                    .unwrap_or_default()
            });
            let location = (pointer_location - output_geometry.loc.to_f64() - hotspot.to_f64())
                .to_physical(scale)
                .to_i32_round();
            render_elements_from_surface_tree::<R, CursorRenderElement<R>>(
                renderer,
                surface,
                location,
                scale,
                1.0,
                Kind::Cursor,
            )
        }
        CursorImageStatus::Surface(_) | CursorImageStatus::Named(_) => {
            let icon = match &cursor_status {
                CursorImageStatus::Named(icon) => *icon,
                _ => CursorIcon::Default,
            };
            let cursor = state
                .cursor_theme
                .image(icon, output.current_scale().fractional_scale());
            let location = (pointer_location - output_geometry.loc.to_f64() - cursor.hotspot)
                .to_physical(scale)
                .to_i32_round();
            MemoryRenderBufferRenderElement::from_buffer(
                renderer,
                location,
                &cursor.buffer,
                None,
                None,
                None,
                Kind::Cursor,
            )
            .map(CursorRenderElement::from)
            .ok()
            .into_iter()
            .collect()
        }
    };

    if let Some(preview) = state.corner_snap_preview.as_ref()
        && !state.session_locked
        && preview.output.name() == output.name()
    {
        let buffer = state.solid_buffers.get(
            &output.name(),
            SolidSlot::SnapPreview,
            preview.rect.size,
            [0.18, 0.46, 0.92, 1.0],
        );
        let location = (preview.rect.loc - output_geometry.loc)
            .to_f64()
            .to_physical(scale)
            .to_i32_round();
        let element =
            SolidColorRenderElement::from_buffer(&buffer, location, scale, 0.28, Kind::Unspecified);
        elements.push(element.into());
    }

    elements.extend(render_shell_osd_elements(renderer, state, output));

    elements
}

pub fn render_wallpaper_element<R>(
    renderer: &mut R,
    state: &PantheonCompositor,
    output: &smithay::output::Output,
) -> Option<CursorRenderElement<R>>
where
    R: Renderer + ImportAll + ImportMem,
    R::TextureId: Texture + Clone + Send + 'static,
{
    let wallpaper = state.wallpaper.as_ref()?;
    let output_geometry = state.space.output_geometry(output)?;
    let size = output_pixel_size(state, output)?;
    let (buffer, source_region) =
        match wallpaper.buffer_for(size, Some(&state.wallpaper_scaled_sender))? {
            crate::wallpaper::WallpaperBuffer::Scaled(buffer) => (buffer, None),
            crate::wallpaper::WallpaperBuffer::Fallback(buffer, crop) => (buffer, crop),
        };
    MemoryRenderBufferRenderElement::from_buffer(
        renderer,
        (0.0, 0.0),
        &buffer,
        None,
        source_region,
        Some(output_geometry.size),
        Kind::Unspecified,
    )
    .map(CursorRenderElement::from)
    .ok()
}

fn render_shell_osd_elements<R>(
    _renderer: &mut R,
    state: &PantheonCompositor,
    output: &smithay::output::Output,
) -> Vec<CursorRenderElement<R>>
where
    R: Renderer + ImportAll + ImportMem,
    R::TextureId: Texture + Clone + Send + 'static,
{
    let Some(osd) = state.shell_compat.active_osd() else {
        return Vec::new();
    };
    let outputs = state.space.outputs().collect::<Vec<_>>();
    let target_name = osd
        .connector
        .as_ref()
        .filter(|connector| {
            outputs
                .iter()
                .any(|candidate| candidate.name().as_str() == connector.as_str())
        })
        .cloned()
        .or_else(|| {
            osd.monitor
                .and_then(|index| outputs.get(index as usize).map(|target| target.name()))
        })
        .or_else(|| state.primary_output().map(|target| target.name()));
    if target_name.as_deref() != Some(output.name().as_str()) {
        return Vec::new();
    }
    let Some(geometry) = state.space.output_geometry(output) else {
        return Vec::new();
    };

    let width = 304.min(geometry.size.w.saturating_sub(32).max(120));
    let height = 76.min(geometry.size.h.saturating_sub(32).max(48));
    let card = Rectangle::<i32, Logical>::new(
        Point::from((
            geometry.loc.x + (geometry.size.w - width) / 2,
            geometry.loc.y + (geometry.size.h - height) / 2,
        )),
        Size::from((width, height)),
    );
    let scale = Scale::from(output.current_scale().fractional_scale());
    let output_name = output.name();
    let mut elements = Vec::new();
    let mut slot = 0_u8;
    let mut append = |rect: Rectangle<i32, Logical>, color: [f32; 4], opacity: f32| {
        let location = (rect.loc - geometry.loc)
            .to_f64()
            .to_physical(scale)
            .to_i32_round();
        let size = rect.size;
        slot = slot.wrapping_add(1);
        if size.w > 0 && size.h > 0 {
            let buffer = state
                .solid_buffers
                .get(&output_name, SolidSlot::Osd(slot), size, color);
            let element = SolidColorRenderElement::from_buffer(
                &buffer,
                location,
                scale,
                opacity,
                Kind::Unspecified,
            );
            elements.push(element.into());
        }
    };

    append(card, [0.055, 0.065, 0.085, 1.0], 0.94);
    let icon_x = card.loc.x + 22;
    let icon_y = card.loc.y + 25;
    if osd
        .icon
        .as_deref()
        .is_some_and(|icon| icon.contains("brightness"))
    {
        // A simple sun glyph keeps the brightness OSD recognizable without
        // pulling a shell toolkit or image stack into the compositor.
        append(
            Rectangle::new((icon_x + 7, icon_y + 7).into(), (12, 12).into()),
            [1.0, 0.86, 0.49, 1.0],
            1.0,
        );
        for (x, y, w, h) in [
            (icon_x + 11, icon_y, 4, 5),
            (icon_x + 11, icon_y + 21, 4, 5),
            (icon_x, icon_y + 11, 5, 4),
            (icon_x + 21, icon_y + 11, 5, 4),
            (icon_x + 3, icon_y + 3, 4, 4),
            (icon_x + 19, icon_y + 3, 4, 4),
            (icon_x + 3, icon_y + 19, 4, 4),
            (icon_x + 19, icon_y + 19, 4, 4),
        ] {
            append(
                Rectangle::new((x, y).into(), (w, h).into()),
                [1.0, 0.86, 0.49, 1.0],
                1.0,
            );
        }
    } else {
        // The sound indicator uses the same endpoint for volume and mute.
        append(
            Rectangle::new((icon_x, icon_y + 8).into(), (8, 12).into()),
            [0.76, 0.85, 1.0, 1.0],
            1.0,
        );
        append(
            Rectangle::new((icon_x + 8, icon_y + 3).into(), (7, 22).into()),
            [0.76, 0.85, 1.0, 1.0],
            1.0,
        );
        if !osd
            .icon
            .as_deref()
            .is_some_and(|icon| icon.contains("muted"))
        {
            append(
                Rectangle::new((icon_x + 18, icon_y + 8).into(), (4, 12).into()),
                [0.76, 0.85, 1.0, 1.0],
                1.0,
            );
        }
    }

    if let Some(level) = osd.level {
        let max_level = osd.max_level.filter(|value| *value > 0.0).unwrap_or(1.0);
        if level.is_finite() && max_level.is_finite() {
            let bar_width = (width - 76).max(32);
            let bar_height = 8;
            let bar_x = card.loc.x + 62;
            let bar_y = card.loc.y + (height - bar_height) / 2;
            append(
                Rectangle::new((bar_x, bar_y).into(), (bar_width, bar_height).into()),
                [0.28, 0.31, 0.37, 1.0],
                1.0,
            );
            let fill_width =
                ((level / max_level).clamp(0.0, 1.0) * f64::from(bar_width)).round() as i32;
            if fill_width > 0 {
                append(
                    Rectangle::new((bar_x, bar_y).into(), (fill_width, bar_height).into()),
                    [0.45, 0.67, 1.0, 1.0],
                    1.0,
                );
            }
        }
    }
    elements
}

pub fn render_lock_surface_elements<R>(
    renderer: &mut R,
    state: &PantheonCompositor,
    output: &smithay::output::Output,
) -> Vec<CursorRenderElement<R>>
where
    R: Renderer + ImportAll + ImportMem,
    R::TextureId: Texture + Clone + Send + 'static,
{
    let output_name = output.name();
    let scale = Scale::from(output.current_scale().fractional_scale());
    // The pointer (and any volume/brightness OSD) above the lock surface.
    let mut elements = state.screen_corners.elements(
        renderer,
        output,
        state.space.output_geometry(output).map(|g| g.size),
    );
    if let Some(surface) = state.lock_surfaces.get(&output_name) {
        elements.extend(render_cursor_elements(renderer, state, output));
        elements.extend(
            render_elements_from_surface_tree::<R, CursorRenderElement<R>>(
                renderer,
                surface.wl_surface(),
                (0, 0),
                scale,
                1.0,
                Kind::Unspecified,
            ),
        );
    }
    elements
}

/// Snap Assist: live, scaled thumbnails of the other windows in the empty
/// half, on plates over a dimmed backdrop, the selection on an accent plate.
/// Clients are not resized. Front to back: thumbnails, plates, backdrop.
fn render_snap_assist_elements<R>(
    renderer: &mut R,
    state: &PantheonCompositor,
    output: &smithay::output::Output,
) -> Vec<CursorRenderElement<R>>
where
    R: Renderer + ImportAll + ImportMem,
    R::TextureId: Texture + Clone + Send + 'static,
{
    use crate::snap_assist::{BACKDROP_ALPHA, PLATE_ALPHA};
    use smithay::backend::renderer::element::{
        AsRenderElements,
        utils::{Relocate, RelocateRenderElement, RescaleRenderElement},
    };
    let Some(assist) = state.snap_assist.as_ref() else {
        return Vec::new();
    };
    if assist.output.name() != output.name() || state.session_locked {
        return Vec::new();
    }
    let Some(area) = state.space.output_geometry(output) else {
        return Vec::new();
    };
    let scale = Scale::from(output.current_scale().fractional_scale());
    let physical = |point: Point<i32, Logical>| (point - area.loc).to_physical_precise_round(scale);
    let mut elements = Vec::new();
    for (window, thumb) in assist.thumbnails() {
        let from = Rectangle::new(
            state.space.element_location(&window).unwrap_or_default(),
            window.geometry().size,
        );
        let origin = (from.loc - window.geometry().loc - area.loc).to_physical_precise_round(scale);
        let anchor = physical(from.loc);
        let offset = (thumb.loc - from.loc).to_physical_precise_round(scale);
        let resize = Scale::from((
            thumb.size.w.max(1) as f64 / from.size.w.max(1) as f64,
            thumb.size.h.max(1) as f64 / from.size.h.max(1) as f64,
        ));
        let surfaces: Vec<WaylandSurfaceRenderElement<R>> =
            window.render_elements(renderer, origin, scale, 1.0);
        elements.extend(surfaces.into_iter().map(|surface| {
            CursorRenderElement::Animated(RelocateRenderElement::from_element(
                RescaleRenderElement::from_element(surface, anchor, resize),
                offset,
                Relocate::Relative,
            ))
        }));
    }
    if let Some(bars) = assist.ring_bars() {
        for (buffer, bar) in assist.ring.iter().zip(bars) {
            elements.push(
                SolidColorRenderElement::from_buffer(
                    buffer,
                    physical(bar.loc),
                    scale,
                    1.0,
                    Kind::Unspecified,
                )
                .into(),
            );
        }
    }
    for (plate_rect, plate) in assist.plate_rects.iter().zip(&assist.plates) {
        elements.push(
            SolidColorRenderElement::from_buffer(
                plate,
                physical(plate_rect.loc),
                scale,
                PLATE_ALPHA,
                Kind::Unspecified,
            )
            .into(),
        );
    }
    elements.push(
        SolidColorRenderElement::from_buffer(
            &assist.backdrop,
            physical(assist.zone.loc),
            scale,
            BACKDROP_ALPHA,
            Kind::Unspecified,
        )
        .into(),
    );
    elements
}

/// Shared scene assembly for nested and native outputs. Preview transforms
/// never remap windows, so keyboard/pointer focus and workspace order stay put.
pub fn render_desktop_elements<R>(
    renderer: &mut R,
    state: &PantheonCompositor,
    output: &smithay::output::Output,
) -> Result<Vec<CursorRenderElement<R>>, smithay::output::OutputNoMode>
where
    R: Renderer + ImportAll + ImportMem,
    R::TextureId: Texture + Clone + Send + 'static,
{
    use crate::gesture_animation::PreviewKind;
    use smithay::backend::renderer::element::{
        AsRenderElements,
        utils::{Relocate, RelocateRenderElement, RescaleRenderElement},
    };
    let mut elements = state.screen_corners.elements(
        renderer,
        output,
        state
            .space
            .output_geometry(output)
            .map(|geometry| geometry.size),
    );
    elements.extend(render_cursor_elements(renderer, state, output));
    elements.extend(render_snap_assist_elements(renderer, state, output));
    if let (Some(animation), Some(area)) = (
        &state.gesture_animation,
        state.space.output_geometry(output),
    ) {
        let scale = Scale::from(output.current_scale().fractional_scale());
        let mut windows = Vec::new();
        for window in state.space.elements().rev() {
            let Some(location) = state.space.element_location(window) else {
                continue;
            };
            let from = Rectangle::new(location, window.geometry().size);
            let mut to = from;
            match animation.kind {
                PreviewKind::Workspace => {
                    if state.workspace_manager.workspace_for(window.id())
                        == Some(animation.workspace)
                    {
                        to.loc.x += (animation.progress * area.size.w as f64).round() as i32;
                    }
                }
                PreviewKind::Overview { .. } => {
                    if let Some(preview) = animation
                        .windows
                        .iter()
                        .find(|entry| entry.window == *window)
                    {
                        let t = animation.progress.clamp(0.0, 1.0);
                        to.loc.x = (preview.from.loc.x as f64
                            + (preview.to.loc.x - preview.from.loc.x) as f64 * t)
                            .round() as i32;
                        to.loc.y = (preview.from.loc.y as f64
                            + (preview.to.loc.y - preview.from.loc.y) as f64 * t)
                            .round() as i32;
                        to.size.w = (preview.from.size.w as f64
                            + (preview.to.size.w - preview.from.size.w) as f64 * t)
                            .round() as i32;
                        to.size.h = (preview.from.size.h as f64
                            + (preview.to.size.h - preview.from.size.h) as f64 * t)
                            .round() as i32;
                    }
                }
            }
            if from.overlaps(area) {
                windows.push((window.clone(), from, to));
            }
        }
        if animation.kind == PreviewKind::Workspace {
            for step in [-1_i32, 1] {
                let index = animation.workspace as i32 + step;
                if index < 0 {
                    continue;
                }
                for (window, location) in state
                    .workspace_manager
                    .windows_in(index as usize)
                    .into_iter()
                    .rev()
                {
                    if state
                        .minimized_windows
                        .values()
                        .any(|(known, _)| known == &window)
                        || state
                            .x11_minimized_windows
                            .values()
                            .any(|(known, _)| known == &window)
                    {
                        continue;
                    }
                    let from = Rectangle::new(location, window.geometry().size);
                    if !from.overlaps(area) {
                        continue;
                    }
                    let mut to = from;
                    to.loc.x +=
                        ((animation.progress + step as f64) * area.size.w as f64).round() as i32;
                    windows.push((window, from, to));
                }
            }
        }
        for (window, from, to) in windows {
            let origin =
                (from.loc - window.geometry().loc - area.loc).to_physical_precise_round(scale);
            let anchor = (from.loc - area.loc).to_physical_precise_round(scale);
            let offset = (to.loc - from.loc).to_physical_precise_round(scale);
            let resize = Scale::from((
                to.size.w.max(1) as f64 / from.size.w.max(1) as f64,
                to.size.h.max(1) as f64 / from.size.h.max(1) as f64,
            ));
            let surfaces: Vec<WaylandSurfaceRenderElement<R>> =
                window.render_elements(renderer, origin, scale, 1.0);
            elements.extend(surfaces.into_iter().map(|surface| {
                CursorRenderElement::Animated(RelocateRenderElement::from_element(
                    RescaleRenderElement::from_element(surface, anchor, resize),
                    offset,
                    Relocate::Relative,
                ))
            }));
        }
    } else {
        // Not `space_render_elements`: that draws each window's popups at the
        // window's own place in the stack, so a lower window's menu was clipped
        // by a higher neighbour. This draws every popup above every toplevel.
        elements.extend(crate::popup_stack::stacked_render_elements::<
            R,
            CursorRenderElement<R>,
        >(renderer, &state.space, output, 1.0));
    }
    if let Some(wallpaper) = render_wallpaper_element(renderer, state, output) {
        elements.push(wallpaper);
    }
    Ok(elements)
}
