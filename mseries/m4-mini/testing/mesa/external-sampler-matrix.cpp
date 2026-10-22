/* SPDX-License-Identifier: MIT
 * Based on the public Mesa Apple9 compiler test setup.
 * Compiler byte equivalence only; no GPU output.
 */

#include "agx_compile_apple9.h"
#include "compiler/nir/nir_builder.h"
#include "gallium/include/pipe/p_defines.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned char reference_binary[65536];
static unsigned reference_size;
static bool compile(enum glsl_sampler_dim dimension, unsigned mode) {
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_FRAGMENT, &agx_nir_options, "external sampler contract");
   nir_tex_instr *tex = nir_tex_instr_create(b.shader, mode >= 2 ? 2 : 1);
   tex->op = mode == 2 ? nir_texop_txb : mode == 4 ? nir_texop_txf : mode == 5 ? nir_texop_txs : nir_texop_tex;
   tex->sampler_dim = dimension;
   tex->dest_type = mode == 5 ? nir_type_int32 : nir_type_float32;
   tex->coord_components = mode == 5 ? 0 : 2;
   tex->src[0].src_type = nir_tex_src_coord;
   tex->src[0].src = nir_src_for_ssa(nir_imm_vec2(&b, .375, .625));
   if (mode >= 2) {
      tex->src[1].src_type = mode == 2 ? nir_tex_src_bias : mode == 3 ? nir_tex_src_projector : nir_tex_src_lod;
      tex->src[1].src = nir_src_for_ssa(mode >= 4 ? nir_imm_int(&b, 0) : nir_imm_float(&b, mode == 3 ? 2.0 : 0.0));
   }
   if (mode == 4) tex->src[0].src = nir_src_for_ssa(nir_imm_ivec2(&b, 1, 2));
   if (mode == 5) { tex->num_srcs = 1; tex->src[0] = tex->src[1]; }
   nir_def_init(&tex->instr, &tex->def, mode == 5 ? 2 : 4, 32);
   nir_builder_instr_insert(&b, &tex->instr);
   nir_def *value = mode == 5 ? nir_vec4(&b, nir_i2f32(&b, nir_channel(&b, &tex->def, 0)), nir_i2f32(&b, nir_channel(&b, &tex->def, 1)), nir_imm_float(&b, 0), nir_imm_float(&b, 1)) : &tex->def;
   nir_store_output(&b, value, nir_imm_int(&b, 0), .write_mask = 15,
      .src_type = nir_type_float32, .io_semantics = {.location = FRAG_RESULT_DATA0, .num_slots = 1});
   b.shader->info.io_lowered = true;
   agx_apple9_sampler_key key[32] = {};
   key[0].min_filter = key[0].mag_filter = (mode == 1 ? PIPE_TEX_FILTER_LINEAR : PIPE_TEX_FILTER_NEAREST);
   key[0].wrap[0] = key[0].wrap[1] = key[0].wrap[2] = PIPE_TEX_WRAP_CLAMP_TO_EDGE;
   agx_apple9_texture_mapping mapping = {};
   const char *reason = NULL;
   bool lowered = agx_nir_lower_apple9_sampler_state(b.shader, key, &mapping, &reason);
   agx_shader_part compiled = {};
   bool ok = lowered && agx_compile_apple9_fragment(b.shader, &compiled, &reason);
   printf("dimension=%u sampler_state=%d compiled=%d bytes=%u reason=%s\n", dimension, lowered, ok,
          compiled.info.binary_size, reason ? reason : "none");
   if (ok) {
      if (compiled.info.binary_size > sizeof(reference_binary)) return false;
      if (dimension == GLSL_SAMPLER_DIM_2D) {
         reference_size = compiled.info.binary_size;
         memcpy(reference_binary, compiled.binary, reference_size);
      } else {
         ok = compiled.info.binary_size == reference_size &&
              memcmp(reference_binary, compiled.binary, reference_size) == 0;
      }
   }
   free(compiled.binary);
   ralloc_free(b.shader);
   return ok;
}
int main(void) {
   bool all = true;
   for (unsigned mode = 0; mode < 6; ++mode) {
      printf("case=%u\n", mode);
      bool reference = compile(GLSL_SAMPLER_DIM_2D, mode);
      bool external = compile(GLSL_SAMPLER_DIM_EXTERNAL, mode);
      all &= reference && external;
   }
   return all ? 0 : 1;
}
