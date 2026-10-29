//! Drawing the corner system (`corners.rs` decides the numbers).
//!
//! * [`screen_mask_elements`]: four small premultiplied-black bitmaps over the built-in
//!   display's corners. Plain memory textures, so they work on every renderer and sit above
//!   anything (windows, the dock, the lock screen).
//! * [`RoundedClip`]: wraps a surface element and draws it through a GLES texture shader that
//!   multiplies the colour by the coverage of a rounded rectangle (a signed-distance
//!   function; circular or superellipse). Only pixels inside the geometry's corner boxes
//!   change, so client-drawn shadows outside the geometry and the window interior are
//!   untouched, and nothing is resized or cropped.
//!
//! The shader finds a pixel with `gl_FragCoord`. Smithay renders with a projection that puts
//! the top row of the output at `gl_FragCoord.y == 0` for the `Normal` frame transform, so
//! output-local physical coordinates are `gl_FragCoord.xy` directly. Frames with any other
//! transform are drawn unclipped rather than wrongly clipped.

use std::{cell::RefCell, collections::HashMap};

use smithay::{
    backend::{
        allocator::Fourcc,
        renderer::{
            Frame, ImportMem, Renderer, RendererSuper, Texture,
            element::{
                Element, Id, Kind, RenderElement, UnderlyingStorage,
                memory::{MemoryRenderBuffer, MemoryRenderBufferRenderElement},
            },
            gles::{GlesFrame, GlesRenderer, GlesTexProgram, Uniform, UniformName, UniformType},
            utils::{CommitCounter, DamageSet, OpaqueRegions},
        },
    },
    desktop::Window,
    utils::{Buffer as BufferCoords, Logical, Physical, Point, Rectangle, Scale, Size, Transform},
};

use crate::corners::{
    CornerStyle, CornerTokens, OutputPolicy, Radii, is_builtin_output, mask_pixels, panel_radii,
    popup_radii, window_radii,
};

const SHADER: &str = r#"
//_DEFINES_
#if defined(EXTERNAL)
#extension GL_OES_EGL_image_external : require
#endif
precision highp float;
#if defined(EXTERNAL)
uniform samplerExternalOES tex;
#else
uniform sampler2D tex;
#endif
uniform float alpha;
varying vec2 v_coords;
#if defined(DEBUG_FLAGS)
uniform float tint;
#endif

// Geometry rectangle in output-local physical pixels: x, y, width, height.
uniform vec4 clip_rect;
// Corner radii in physical pixels: top-left, top-right, bottom-right, bottom-left.
uniform vec4 clip_radii;
// x: superellipse exponent (2 is a circle), y: corner box size as a multiple of the radius.
uniform vec2 clip_shape;
// x: frame height in pixels, y: 1.0 when the frame is flipped vertically (nested Winit output).
uniform vec2 clip_view;

// Coverage of the rounded shape at offset d from the arc centre towards the corner.
// Mirrors corners::corner_distance.
float corner_cover(vec2 d, float extent, float n) {
    d = max(d, vec2(0.0));
    float dist;
    if (n < 2.001) {
        dist = length(d) - extent;
    } else {
        vec2 a = max(d, vec2(0.0001));
        float f = pow(pow(a.x, n) + pow(a.y, n), 1.0 / n);
        vec2 g = pow(a / f, vec2(n - 1.0));
        dist = (f - extent) / max(length(g), 0.0001);
    }
    return clamp(0.5 - dist, 0.0, 1.0);
}

void main() {
    vec4 color = texture2D(tex, v_coords);

#if defined(NO_ALPHA)
    color = vec4(color.rgb, 1.0) * alpha;
#else
    color = color * alpha;
#endif

    vec2 p = gl_FragCoord.xy;
    if (clip_view.y > 0.5) {
        p.y = clip_view.x - p.y;
    }
    vec2 q = p - clip_rect.xy;
    vec2 size = clip_rect.zw;
    if (q.x >= 0.0 && q.y >= 0.0 && q.x <= size.x && q.y <= size.y) {
        bool left = q.x < size.x * 0.5;
        bool top = q.y < size.y * 0.5;
        float r = top ? (left ? clip_radii.x : clip_radii.y)
                      : (left ? clip_radii.w : clip_radii.z);
        if (r > 0.0) {
            float e = r * clip_shape.y;
            vec2 d = vec2(left ? e - q.x : q.x - (size.x - e),
                          top ? e - q.y : q.y - (size.y - e));
            if (d.x > 0.0 && d.y > 0.0) {
                color *= corner_cover(d, e, clip_shape.x);
            }
        }
    }

#if defined(DEBUG_FLAGS)
    if (tint == 1.0)
        color = vec4(0.0, 0.2, 0.0, 0.2) + color * 0.8;
#endif

    gl_FragColor = color;
}
"#;

/// A renderer that can draw [`RoundedClip`] elements: it is (or wraps) a [`GlesRenderer`].
pub trait CornerRenderer: Renderer {
    /// The compiled clip shader of this renderer's GL context (compiled once, cached in the
    /// context). `None` if it failed to compile; windows are then drawn square.
    fn corner_program(&mut self) -> Option<GlesTexProgram>;

    /// The GLES frame behind a frame of this renderer.
    fn gles_frame<'a, 'b, 'c>(
        frame: &'c mut <Self as RendererSuper>::Frame<'a, 'b>,
    ) -> &'c mut GlesFrame<'a, 'b>
    where
        'b: 'a,
        Self: 'a;
}

struct CachedProgram(Option<GlesTexProgram>);

/// Compile (once per GL context) the clip shader.
pub fn gles_corner_program(renderer: &mut GlesRenderer) -> Option<GlesTexProgram> {
    if let Some(cached) = renderer.egl_context().user_data().get::<CachedProgram>() {
        return cached.0.clone();
    }
    let compiled = renderer
        .compile_custom_texture_shader(
            SHADER,
            &[
                UniformName::new("clip_rect", UniformType::_4f),
                UniformName::new("clip_radii", UniformType::_4f),
                UniformName::new("clip_shape", UniformType::_2f),
                UniformName::new("clip_view", UniformType::_2f),
            ],
        )
        .map_err(|error| tracing::error!(%error, "corner clip shader failed to compile; windows stay square"))
        .ok();
    renderer
        .egl_context()
        .user_data()
        .insert_if_missing_threadsafe(|| CachedProgram(compiled.clone()));
    compiled
}

impl CornerRenderer for GlesRenderer {
    fn corner_program(&mut self) -> Option<GlesTexProgram> {
        gles_corner_program(self)
    }

    fn gles_frame<'a, 'b, 'c>(frame: &'c mut GlesFrame<'a, 'b>) -> &'c mut GlesFrame<'a, 'b>
    where
        'b: 'a,
        Self: 'a,
    {
        frame
    }
}

/// A surface element drawn through the corner-clip shader.
#[derive(Debug)]
pub struct RoundedClip<E> {
    inner: E,
    program: GlesTexProgram,
    /// The geometry rectangle in output-local physical pixels.
    rect: Rectangle<i32, Physical>,
    /// Corner radii in physical pixels.
    radii: Radii,
    style: CornerStyle,
}

impl<E> RoundedClip<E> {
    /// The four corner boxes of the geometry rectangle (empty ones for square corners),
    /// in output-local physical pixels, clockwise from the top left.
    fn corner_boxes(&self) -> [Rectangle<i32, Physical>; 4] {
        corner_boxes(self.rect, self.radii, self.style)
    }

    fn uniforms(&self, frame_height: i32, flipped: bool) -> Vec<Uniform<'static>> {
        let rect = self.rect;
        vec![
            Uniform::new(
                "clip_rect",
                [
                    rect.loc.x as f32,
                    rect.loc.y as f32,
                    rect.size.w as f32,
                    rect.size.h as f32,
                ],
            ),
            Uniform::new(
                "clip_radii",
                [
                    self.radii.top_left,
                    self.radii.top_right,
                    self.radii.bottom_right,
                    self.radii.bottom_left,
                ],
            ),
            Uniform::new(
                "clip_shape",
                [self.style.exponent(), self.style.extent(1.0)],
            ),
            Uniform::new(
                "clip_view",
                [frame_height as f32, if flipped { 1.0 } else { 0.0 }],
            ),
        ]
    }
}

fn corner_boxes(
    rect: Rectangle<i32, Physical>,
    radii: Radii,
    style: CornerStyle,
) -> [Rectangle<i32, Physical>; 4] {
    let side = |radius: f32| style.extent(radius).ceil() as i32;
    let (tl, tr, br, bl) = (
        side(radii.top_left),
        side(radii.top_right),
        side(radii.bottom_right),
        side(radii.bottom_left),
    );
    let (x0, y0) = (rect.loc.x, rect.loc.y);
    let (x1, y1) = (x0 + rect.size.w, y0 + rect.size.h);
    let boxed = |x, y, side| Rectangle::new((x, y).into(), (side, side).into());
    [
        boxed(x0, y0, tl),
        boxed(x1 - tr, y0, tr),
        boxed(x1 - br, y1 - br, br),
        boxed(x0, y1 - bl, bl),
    ]
}

impl<E: Element> Element for RoundedClip<E> {
    fn id(&self) -> &Id {
        self.inner.id()
    }

    fn current_commit(&self) -> CommitCounter {
        self.inner.current_commit()
    }

    fn location(&self, scale: Scale<f64>) -> Point<i32, Physical> {
        self.inner.location(scale)
    }

    fn src(&self) -> Rectangle<f64, BufferCoords> {
        self.inner.src()
    }

    fn transform(&self) -> Transform {
        self.inner.transform()
    }

    fn geometry(&self, scale: Scale<f64>) -> Rectangle<i32, Physical> {
        self.inner.geometry(scale)
    }

    fn damage_since(
        &self,
        scale: Scale<f64>,
        commit: Option<CommitCounter>,
    ) -> DamageSet<i32, Physical> {
        self.inner.damage_since(scale, commit)
    }

    /// The inner element's opaque regions without the corner boxes: the corners now have
    /// partial alpha, so they must be blended rather than overwritten.
    fn opaque_regions(&self, scale: Scale<f64>) -> OpaqueRegions<i32, Physical> {
        let inner = self.inner.opaque_regions(scale);
        if inner.is_empty() {
            return inner;
        }
        let origin = self.inner.geometry(scale).loc;
        let boxes = self
            .corner_boxes()
            .map(|corner| Rectangle::new(corner.loc - origin, corner.size));
        inner
            .iter()
            .flat_map(|region| region.subtract_rects(boxes))
            .collect()
    }

    fn alpha(&self) -> f32 {
        self.inner.alpha()
    }

    fn kind(&self) -> Kind {
        self.inner.kind()
    }
}

impl<R, E> RenderElement<R> for RoundedClip<E>
where
    R: CornerRenderer,
    E: RenderElement<R>,
{
    fn draw(
        &self,
        frame: &mut R::Frame<'_, '_>,
        src: Rectangle<f64, BufferCoords>,
        dst: Rectangle<i32, Physical>,
        damage: &[Rectangle<i32, Physical>],
        opaque_regions: &[Rectangle<i32, Physical>],
        cache: Option<&smithay::utils::user_data::UserDataMap>,
    ) -> Result<(), R::Error> {
        // The projection puts output row 0 at `gl_FragCoord.y == 0` for a normal frame and at
        // the far end for the vertically flipped frame of the nested Winit output. Rotated
        // frames are drawn unclipped.
        let flipped = match frame.transformation() {
            Transform::Normal => Some(false),
            Transform::Flipped180 => Some(true),
            _ => None,
        };
        if let Some(flipped) = flipped {
            let height = frame.output_size().h;
            R::gles_frame(frame)
                .override_default_tex_program(self.program.clone(), self.uniforms(height, flipped));
        }
        let result = self
            .inner
            .draw(frame, src, dst, damage, opaque_regions, cache);
        if flipped.is_some() {
            R::gles_frame(frame).clear_tex_program_override();
        }
        result
    }

    /// Never scanned out directly: the clip needs the compositor's own pass.
    fn underlying_storage(&self, _renderer: &mut R) -> Option<UnderlyingStorage<'_>> {
        None
    }
}

/// Everything needed to round the elements of one output's frame.
pub struct Clipper<'a> {
    tokens: CornerTokens,
    program: GlesTexProgram,
    scale: f64,
    output: OutputPolicy,
    is_panel: Box<dyn Fn(&Window) -> bool + 'a>,
}

impl<'a> Clipper<'a> {
    /// `None` for outputs that stay square (anything but the built-in panel), when the
    /// tokens ask for no rounding, or when the shader is not available.
    pub fn new<R: CornerRenderer>(
        renderer: &mut R,
        tokens: CornerTokens,
        output: &smithay::output::Output,
        geometry: Rectangle<i32, Logical>,
        is_panel: impl Fn(&Window) -> bool + 'a,
    ) -> Option<Self> {
        let builtin = is_builtin_output(&output.name());
        if !builtin || tokens.window.max(tokens.screen).max(tokens.popover) <= 0.0 {
            return None;
        }
        Some(Self {
            tokens,
            program: renderer.corner_program()?,
            scale: output.current_scale().fractional_scale(),
            output: OutputPolicy { geometry, builtin },
            is_panel: Box::new(is_panel),
        })
    }

    /// Radii for a toplevel window (or panel) whose geometry is `rect` in space coordinates.
    pub fn toplevel_radii(&self, window: &Window, rect: Rectangle<i32, Logical>) -> Radii {
        if window
            .x11_surface()
            .is_some_and(|surface| surface.is_override_redirect())
        {
            // X11 menus and tooltips are popups in everything but name.
            return popup_radii(&self.tokens, rect, self.output.builtin);
        }
        if (self.is_panel)(window) {
            panel_radii(&self.tokens, rect, self.output)
        } else {
            window_radii(&self.tokens, rect, self.output)
        }
    }

    pub fn popup_radii(&self, rect: Rectangle<i32, Logical>) -> Radii {
        popup_radii(&self.tokens, rect, self.output.builtin)
    }

    /// Wrap the elements of one surface tree whose geometry is `rect` (space coordinates)
    /// with `radii`. Elements clear of every corner box stay plain.
    pub fn wrap<E, C>(
        &self,
        elements: Vec<E>,
        rect: Rectangle<i32, Logical>,
        radii: Radii,
    ) -> Vec<C>
    where
        E: Element,
        C: From<E> + From<RoundedClip<E>>,
    {
        if radii.is_square() {
            return elements.into_iter().map(C::from).collect();
        }
        let scale = Scale::from(self.scale);
        let origin = (rect.loc - self.output.geometry.loc).to_physical_precise_round(scale);
        let size: Size<i32, Physical> = rect.size.to_physical_precise_round(scale);
        let rect = Rectangle::new(origin, size);
        let radii = radii.scaled(self.scale);
        let boxes = corner_boxes(rect, radii, self.tokens.style);
        elements
            .into_iter()
            .map(|element| {
                let geometry = element.geometry(scale);
                if boxes.iter().any(|corner| geometry.overlaps(*corner)) {
                    C::from(RoundedClip {
                        inner: element,
                        program: self.program.clone(),
                        rect,
                        radii,
                        style: self.tokens.style,
                    })
                } else {
                    C::from(element)
                }
            })
            .collect()
    }
}

/// The four mask bitmaps per output and radius, kept across frames so the damage tracker
/// sees the same buffers (and so repaints nothing) while the radius does not change.
#[derive(Default)]
pub(crate) struct MaskBuffers(RefCell<HashMap<MaskKey, [MemoryRenderBuffer; 4]>>);

#[derive(Clone, PartialEq, Eq, Hash)]
struct MaskKey {
    output: String,
    side: u32,
    radius_milli: u32,
    style: u8,
}

/// Flip a square Argb8888 bitmap so the corner lands in another corner of its box.
fn mirrored(pixels: &[u8], side: u32, flip_x: bool, flip_y: bool) -> Vec<u8> {
    let mut out = Vec::with_capacity(pixels.len());
    for j in 0..side {
        for i in 0..side {
            let (si, sj) = (
                if flip_x { side - 1 - i } else { i },
                if flip_y { side - 1 - j } else { j },
            );
            let at = ((sj * side + si) * 4) as usize;
            out.extend_from_slice(&pixels[at..at + 4]);
        }
    }
    out
}

/// Four screen-corner mask elements for the built-in output, front-most first. `pixels` is
/// the output's physical size and `scale` its (fractional) scale.
pub(crate) fn screen_mask_elements<R>(
    renderer: &mut R,
    buffers: &MaskBuffers,
    tokens: &CornerTokens,
    output: &smithay::output::Output,
    pixels: (i32, i32),
    scale: f64,
) -> Vec<MemoryRenderBufferRenderElement<R>>
where
    R: Renderer + ImportMem,
    R::TextureId: Texture + Clone + Send + 'static,
{
    if !is_builtin_output(&output.name()) || tokens.screen <= 0.0 {
        return Vec::new();
    }
    // Logical side of the box, whole so the element's physical size rounds to the bitmap.
    let logical_side = tokens.style.extent(tokens.screen).ceil() as i32;
    let side = (logical_side as f64 * scale).round() as u32;
    let radius = tokens.screen * scale as f32;
    if side == 0 || side as i32 > pixels.0.min(pixels.1) {
        return Vec::new();
    }
    let key = MaskKey {
        output: output.name(),
        side,
        radius_milli: (radius * 1000.0).round() as u32,
        style: tokens.style as u8,
    };
    let set = buffers
        .0
        .borrow_mut()
        .entry(key)
        .or_insert_with(|| {
            let top_left = mask_pixels(radius, side, tokens.style);
            [(false, false), (true, false), (true, true), (false, true)].map(|(fx, fy)| {
                MemoryRenderBuffer::from_slice(
                    &mirrored(&top_left, side, fx, fy),
                    Fourcc::Argb8888,
                    (side as i32, side as i32),
                    1,
                    Transform::Normal,
                    None,
                )
            })
        })
        .clone();
    let (width, height) = (pixels.0 as f64, pixels.1 as f64);
    let far = side as f64;
    let at = [
        (0.0, 0.0),
        (width - far, 0.0),
        (width - far, height - far),
        (0.0, height - far),
    ];
    set.iter()
        .zip(at)
        .filter_map(|(buffer, location)| {
            MemoryRenderBufferRenderElement::from_buffer(
                renderer,
                location,
                buffer,
                None,
                None,
                Some((logical_side, logical_side).into()),
                Kind::Unspecified,
            )
            .ok()
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mirroring_moves_the_corner_to_the_requested_box_corner() {
        // 2x2 bitmap with a distinct alpha per pixel: tl=1 tr=2 bl=3 br=4.
        let px = |a: u8| [0, 0, 0, a];
        let bitmap: Vec<u8> = [px(1), px(2), px(3), px(4)].concat();
        let alphas = |bytes: Vec<u8>| bytes.chunks(4).map(|p| p[3]).collect::<Vec<_>>();
        assert_eq!(alphas(mirrored(&bitmap, 2, false, false)), [1, 2, 3, 4]);
        assert_eq!(alphas(mirrored(&bitmap, 2, true, false)), [2, 1, 4, 3]);
        assert_eq!(alphas(mirrored(&bitmap, 2, false, true)), [3, 4, 1, 2]);
        assert_eq!(alphas(mirrored(&bitmap, 2, true, true)), [4, 3, 2, 1]);
    }

    #[test]
    fn corner_boxes_sit_in_the_four_corners_and_skip_square_corners() {
        let rect = Rectangle::<i32, Physical>::new((100, 50).into(), (400, 300).into());
        let radii = Radii {
            top_left: 0.0,
            top_right: 10.0,
            bottom_right: 20.0,
            bottom_left: 0.0,
        };
        let boxes = corner_boxes(rect, radii, CornerStyle::Circular);
        assert!(boxes[0].is_empty());
        assert_eq!(boxes[1], Rectangle::new((490, 50).into(), (10, 10).into()));
        assert_eq!(boxes[2], Rectangle::new((480, 330).into(), (20, 20).into()));
        assert!(boxes[3].is_empty());
        // The continuous box is larger than the nominal radius.
        let continuous = corner_boxes(rect, radii, CornerStyle::Continuous);
        assert_eq!(continuous[1].size.w, 12);
    }
}
