/* SPDX-License-Identifier: MIT
 * Based on the public Mesa Apple9 compiler test setup.
 * Compiler equivalence and rejection controls only; no GPU execution.
 */
#include "agx_compile_apple9.h"
#include "compiler/nir/nir_builder.h"
#include "gallium/include/pipe/p_defines.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <initializer_list>

struct result {
   bool compiled;
   unsigned size, texture_mask, sampler_mask;
   unsigned char binary[65536];
};

static result compile(enum glsl_sampler_dim dimension, unsigned mode,
                      bool dynamic, bool sampler_state, unsigned malformed) {
   result out = {};
   nir_builder b = nir_builder_init_simple_shader(
      MESA_SHADER_FRAGMENT, &agx_nir_options, "external sampler contract");
   nir_def *input = NULL;
   if (dynamic) {
      b.shader->info.num_ubos = 1;
      input = nir_load_ubo(&b, 4, 32, nir_imm_int(&b, 0),
                          nir_imm_int(&b, 0), .align_mul = 16, .range = 16);
   }
   nir_tex_instr *tex = nir_tex_instr_create(b.shader,
      (mode >= 2 ? 2 : 1) + (malformed == 2));
   tex->op = mode == 2 ? nir_texop_txb : mode == 4 ? nir_texop_txf :
             mode == 5 ? nir_texop_txs : nir_texop_tex;
   tex->sampler_dim = dimension;
   tex->dest_type = mode == 5 ? nir_type_int32 : nir_type_float32;
   tex->coord_components = mode == 5 ? 0 : malformed == 1 ? 3 : 2;
   tex->is_array = malformed == 1;
   tex->is_shadow = malformed == 2;
   tex->texture_index = 3;
   tex->sampler_index = 7;
   tex->src[0].src_type = nir_tex_src_coord;
   tex->src[0].src = nir_src_for_ssa(dynamic ?
      nir_trim_vector(&b, input, tex->coord_components ? tex->coord_components : 2) :
      malformed == 1 ? nir_imm_vec3(&b, .375, .625, 0) : nir_imm_vec2(&b, .375, .625));
   if (mode >= 2) {
      tex->src[1].src_type = mode == 2 ? nir_tex_src_bias :
                            mode == 3 ? nir_tex_src_projector : nir_tex_src_lod;
      tex->src[1].src = nir_src_for_ssa(mode >= 4 ? nir_imm_int(&b, 0) :
         dynamic ? nir_channel(&b, input, 3) : nir_imm_float(&b, mode == 3 ? 2.0 : 0.0));
   }
   if (mode == 4)
      tex->src[0].src = nir_src_for_ssa(dynamic ? nir_f2i32(&b, nir_trim_vector(&b, input, 2)) :
                                      nir_imm_ivec2(&b, 1, 2));
   if (mode == 5) { tex->num_srcs = 1; tex->src[0] = tex->src[1]; }
   if (malformed == 2) {
      tex->src[1].src_type = nir_tex_src_comparator;
      tex->src[1].src = nir_src_for_ssa(dynamic ? nir_channel(&b, input, 2) : nir_imm_float(&b, .5));
   }
   nir_def_init(&tex->instr, &tex->def, mode == 5 ? 2 : 4, 32);
   nir_builder_instr_insert(&b, &tex->instr);
   nir_def *value = mode == 5 ? nir_vec4(&b,
      nir_i2f32(&b, nir_channel(&b, &tex->def, 0)),
      nir_i2f32(&b, nir_channel(&b, &tex->def, 1)),
      nir_imm_float(&b, 0), nir_imm_float(&b, 1)) : &tex->def;
   nir_store_output(&b, value, nir_imm_int(&b, 0), .write_mask = 15,
      .src_type = nir_type_float32,
      .io_semantics = {.location = FRAG_RESULT_DATA0, .num_slots = 1});
   b.shader->info.io_lowered = true;
   agx_apple9_sampler_key key[32] = {};
   key[7].min_filter = key[7].mag_filter = mode == 1 ? PIPE_TEX_FILTER_LINEAR : PIPE_TEX_FILTER_NEAREST;
   key[7].wrap[0] = key[7].wrap[1] = key[7].wrap[2] = PIPE_TEX_WRAP_CLAMP_TO_EDGE;
   agx_apple9_texture_mapping mapping = {};
   const char *reason = NULL;
   bool lowered = !sampler_state ||
      agx_nir_lower_apple9_sampler_state(b.shader, key, &mapping, &reason);
   agx_shader_part compiled = {};
   out.compiled = lowered && agx_compile_apple9_fragment(b.shader, &compiled, &reason);
   out.size = compiled.info.binary_size;
   out.texture_mask = compiled.info.apple9_texture_mask;
   out.sampler_mask = compiled.info.apple9_sampler_mask;
   printf("dim=%u op=%u dynamic=%u state=%u malformed=%u compiled=%u bytes=%u reason=%s\n",
      dimension, mode, dynamic, sampler_state, malformed, out.compiled, out.size,
      reason ? reason : "none");
   if (out.compiled && out.size <= sizeof(out.binary))
      memcpy(out.binary, compiled.binary, out.size);
   else if (out.size > sizeof(out.binary))
      out.compiled = false;
   free(compiled.binary);
   ralloc_free(b.shader);
   return out;
}

int main(int argc, char **argv) {
   bool original = argc == 2 && !strcmp(argv[1], "--expect-uncorrected");
   unsigned positive = 0, negative = 0, original_rejections = 0;
   bool all = true;
   for (bool state : {false, true}) {
      for (bool dynamic : {false, true}) {
         for (unsigned mode = 0; mode < 6; ++mode) {
            result reference = compile(GLSL_SAMPLER_DIM_2D, mode, dynamic, state, 0);
            result external = compile(GLSL_SAMPLER_DIM_EXTERNAL, mode, dynamic, state, 0);
            bool equal = reference.compiled && external.compiled && reference.size > 0 &&
               reference.size == external.size && reference.texture_mask == external.texture_mask &&
               reference.sampler_mask == external.sampler_mask &&
               !memcmp(reference.binary, external.binary, reference.size);
            if (!original) all &= equal;
            else {
               all &= reference.compiled;
               original_rejections += reference.compiled && !external.compiled;
            }
            positive += equal;
         }
      }
      for (unsigned malformed : {1u, 2u}) {
         result reference = compile(GLSL_SAMPLER_DIM_2D, 0, true, state, malformed);
         result external = compile(GLSL_SAMPLER_DIM_EXTERNAL, 0, true, state, malformed);
         bool rejected = reference.compiled && !external.compiled;
         all &= rejected;
         negative += rejected;
      }
   }
   if (original) all &= original_rejections > 0;
   printf("RESULT positive=%u negative=%u original_rejections=%u passed=%u\n",
          positive, negative, original_rejections, all);
   return all ? 0 : 1;
}
