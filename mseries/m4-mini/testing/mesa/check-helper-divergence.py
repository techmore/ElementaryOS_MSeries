#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check PR1's blanket uniform marker against the actual compiled NIR library.

This is a source/IR diagnostic, not a GPU rendering test or candidate fix.
The workspace must have the pinned PR1 source intake and built NIR libraries.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    mesa = args.mesa_workspace.resolve()
    source = mesa / 'mesa-87ac51d411f0e58a9433567ec2666f457be89e1d'
    build = mesa / 'build'
    intake = json.loads((Path(__file__).resolve().parents[2] /
                         'receipts/2026-10-22-gravity-mesa-pr1-source-intake.json').read_text())
    for name in ['src/asahi/compiler/agx_compile.c', 'src/gallium/drivers/asahi/agx_blit.c']:
        if digest(source / name) != intake['files'][name]['after_sha256']:
            raise ValueError('exact PR1 source required')
    text = (source / 'src/asahi/compiler/agx_compile.c').read_text()
    helper = re.search(r'static bool\nagx_mark_def_uniform\(.*?\n}\n', text, re.S).group()
    start = text.index('      nir_foreach_function_impl(impl, nir) {', text.index('if (allow_workgroup_intrinsics)'))
    end = text.index('\n   } else {', start)
    block = text[start:end]
    if args.output.exists():
        raise ValueError('new diagnostic output required')
    root = args.output.resolve()
    root.mkdir(parents=True)
    marker = root / 'INCOMPLETE'
    marker.touch()
    fixture = ('#include "nir.h"\n#include "nir_builder.h"\n#include <stdio.h>\n' +
               '/* MIT helper/block from Gravity Mesa PR1; original agx_compile.c copyright:\n'
               ' * 2021 Alyssa Rosenzweig; 2020 Collabora Ltd.; 2016 Broadcom. */\n' +
               helper + '\nstatic void proposal(nir_shader *nir) {\n' + block + '\n}\n' + r'''
int main(void) {
   static const nir_shader_compiler_options options = {};
   nir_builder b = nir_builder_init_simple_shader(MESA_SHADER_FRAGMENT, &options, "layered tile metadata review");
   nir_def *layer = nir_load_layer_id(&b);
   nir_shader_gather_info(b.shader, b.impl);
   nir_divergence_analysis(b.shader);
   bool before = layer->divergent;
   /* Normal analysis rejects a workgroup read in this stage. Check reference
    * layer semantics first, then add the input that selects PR1's helper path.
    * An independent uniform read cannot change layer-id semantics. */
   (void)nir_load_workgroup_id(&b);
   nir_shader_gather_info(b.shader, b.impl);
   proposal(b.shader);
   bool after = layer->divergent;
   bool valid = (b.impl->valid_metadata & nir_metadata_divergence) != 0;
   printf("reference_layer_divergent=%d\nproposal_layer_divergent=%d\nmetadata_marked_valid=%d\n", before, after, valid);
   ralloc_free(b.shader);
   return before && !after && valid ? 0 : 1;
}
''')
    cpp = root / 'review.cpp'
    cpp.write_text(fixture)
    commands = json.loads((build / 'compile_commands.json').read_text())
    item = next(c for c in commands if c['file'].endswith('/tests/builder_tests.cpp'))
    compile_args = shlex.split(item['command']) if 'command' in item else item['arguments']
    obj = root / 'review.o'
    compile_args[compile_args.index('-o') + 1] = str(obj)
    compile_args[compile_args.index('-c') + 1] = str(cpp)
    compile_args += ['-Wno-unused-parameter']
    with (root / 'compile.log').open('wb') as log:
        subprocess.run(compile_args, cwd=build, stdout=log, stderr=subprocess.STDOUT, check=True)
    # Read Ninja's existing link recipe without executing any build target.
    recipe = subprocess.check_output(['ninja', '-C', str(build), '-t', 'commands',
                                      'src/compiler/nir/nir_tests'], text=True).splitlines()[-1]
    link = [a for a in shlex.split(recipe) if not a.endswith('.o') and
            'libnir_opt_algebraic_pattern_test_' not in a and a != 'src/gtest/libgtest.a' and
            a not in ['-Wl,--whole-archive', '-Wl,--no-whole-archive']]
    link[link.index('-o') + 1] = str(root / 'review')
    link.insert(1, str(obj))
    with (root / 'link.log').open('wb') as log:
        subprocess.run(link, cwd=build, stdout=log, stderr=subprocess.STDOUT, check=True)
    result = subprocess.run([str(root / 'review')], capture_output=True, text=True, check=True)
    (root / 'result.log').write_text(result.stdout + result.stderr)
    record = {
        'scope': 'actual NIR layer-id reference followed by verbatim PR1 uniform marker on a fragment helper with workgroup input; not full helper compilation or GPU output',
        'proposal_head': intake['head'], 'reference_layer_divergent': True,
        'proposal_layer_divergent': False, 'proposal_marks_metadata_valid': True,
        'finding': 'blanket marker erases divergence of layer-id used by the layered store helper',
        'fixture_sha256': digest(cpp), 'nir_archive_sha256': digest(build / 'src/compiler/nir/libnir.a'),
        'divergence_object_sha256': digest(build / 'src/compiler/nir/libnir.a.p/nir_divergence_analysis.c.o'),
        'source_files': {n: digest(source / n) for n in ['src/asahi/compiler/agx_compile.c',
            'src/gallium/drivers/asahi/agx_blit.c', 'src/compiler/nir/nir_divergence_analysis.c']},
        'compile_command': compile_args, 'link_command': link, 'exit_code': 0,
        'hardware_validated': False, 'native_misrender_reproduced': False}
    (root / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    marker.unlink()
    print(result.stdout, end='')
    print('Metadata mismatch confirmed; no rendered-output or hardware claim')


if __name__ == '__main__':
    main()
