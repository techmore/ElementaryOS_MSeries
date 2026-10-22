/*
 * Copyright 2026 The Asahi Linux Contributors
 * SPDX-License-Identifier: MIT
 * Diagnostic fixture based on the public Apple9 compiler test setup.
 * Expected finding: basic 2D compiles, advertised external sampling fails.
 * No EGL image or GPU is created.
 */

#include "agx_compile_apple9.h"
#include "compiler/nir/nir_builder.h"
#include "gallium/include/pipe/p_defines.h"
#include <stdio.h>
#include <stdlib.h>
static bool compile(enum glsl_sampler_dim dimension) {
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_FRAGMENT, &agx_nir_options, "external sampler contract");
   nir_tex_instr *tex = nir_tex_instr_create(b.shader, 1);
   tex->op = nir_texop_tex;
   tex->sampler_dim = dimension;
   tex->dest_type = nir_type_float32;
   tex->coord_components = 2;
   tex->src[0].src_type = nir_tex_src_coord;
   tex->src[0].src = nir_src_for_ssa(nir_imm_vec2(&b, .375, .625));
   nir_def_init(&tex->instr, &tex->def, 4, 32);
   nir_builder_instr_insert(&b, &tex->instr);
   nir_store_output(&b, &tex->def, nir_imm_int(&b, 0), .write_mask = 15,
      .src_type = nir_type_float32, .io_semantics = {.location = FRAG_RESULT_DATA0, .num_slots = 1});
   b.shader->info.io_lowered = true;
   agx_apple9_sampler_key key[32] = {};
   key[0].min_filter = key[0].mag_filter = PIPE_TEX_FILTER_NEAREST;
   key[0].wrap[0] = key[0].wrap[1] = key[0].wrap[2] = PIPE_TEX_WRAP_CLAMP_TO_EDGE;
   agx_apple9_texture_mapping mapping = {};
   const char *reason = NULL;
   bool lowered = agx_nir_lower_apple9_sampler_state(b.shader, key, &mapping, &reason);
   agx_shader_part compiled = {};
   bool ok = lowered && agx_compile_apple9_fragment(b.shader, &compiled, &reason);
   printf("dimension=%u sampler_state=%d compiled=%d bytes=%u reason=%s\n", dimension, lowered, ok,
          compiled.info.binary_size, reason ? reason : "none");
   free(compiled.binary);
   ralloc_free(b.shader);
   return ok;
}
int main(void) {
   bool reference = compile(GLSL_SAMPLER_DIM_2D);
   bool external = compile(GLSL_SAMPLER_DIM_EXTERNAL);
   return reference && !external ? 0 : 1;
}
