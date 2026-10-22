#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the actual candidate NIR library; no DRM device or GPU is used."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import shlex
import signal
import subprocess

FIXTURE = r'''
#include "nir.h"
#include "nir_builder.h"
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
   if (argc != 2) return 2;
   const char *name = argv[1];
   bool fragment = strstr(name, "fragment") != NULL;
   bool flagged = strstr(name, "flagged") != NULL;
   nir_shader_compiler_options options = {};
   if (flagged)
      options.divergence_analysis_options = nir_divergence_fragment_workgroup_id_uniform;
   if (strcmp(name, "compute-multiple") == 0)
      options.divergence_analysis_options = nir_divergence_multiple_workgroup_per_compute_subgroup;
   nir_builder b = nir_builder_init_simple_shader(fragment ? MESA_SHADER_FRAGMENT : MESA_SHADER_COMPUTE,
                                                 &options, "helper divergence boundary");
   nir_def *layer = fragment ? nir_load_layer_id(&b) : NULL;
   nir_def *group = NULL;
   nir_def *sum = NULL;
   if (strstr(name, "index"))
      group = nir_load_workgroup_index(&b);
   else if (strstr(name, "shared"))
      group = nir_load_shared_base_ptr(&b, 1, 64);
   else if (strcmp(name, "fragment-normal") != 0) {
      group = nir_load_workgroup_id(&b);
      if (layer) sum = nir_iadd(&b, layer, nir_channel(&b, group, 0));
   }
   nir_shader_gather_info(b.shader, b.impl);
   nir_divergence_analysis(b.shader);
   bool valid = (b.impl->valid_metadata & nir_metadata_divergence) != 0;
   bool ok = valid;
   if (layer) ok &= layer->divergent;
   if (sum) ok &= sum->divergent;
   if (group) ok &= group->divergent == (strcmp(name, "compute-multiple") == 0);
   printf("%s: layer=%d group=%d sum=%d metadata=%d\n", name,
          layer ? layer->divergent : -1, group ? group->divergent : -1,
          sum ? sum->divergent : -1, valid);
   ralloc_free(b.shader);
   return ok ? 0 : 1;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-workspace', type=Path, required=True)
    parser.add_argument('--candidate-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    mesa = args.mesa_workspace.resolve()
    source = mesa / 'mesa-87ac51d411f0e58a9433567ec2666f457be89e1d'
    build = mesa / 'build'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    candidate = json.loads(args.candidate_manifest.read_text())
    for name, item in candidate['files'].items():
        if sha(source / name) != item['after_sha256']:
            raise ValueError('candidate source hash mismatch: ' + name)
    if args.output.exists():
        raise ValueError('new output required')
    out = args.output.resolve()
    out.mkdir(parents=True)
    marker = out / 'INCOMPLETE'
    marker.touch()
    cpp = out / 'fixture.cpp'
    cpp.write_text(FIXTURE)
    commands = json.loads((build / 'compile_commands.json').read_text())
    item = next(c for c in commands if c['file'].endswith('/tests/builder_tests.cpp'))
    compile_args = shlex.split(item['command']) if 'command' in item else item['arguments']
    obj = out / 'fixture.o'
    compile_args[compile_args.index('-o') + 1] = str(obj)
    compile_args[compile_args.index('-c') + 1] = str(cpp)
    with (out / 'compile.log').open('wb') as log:
        subprocess.run(compile_args, cwd=build, stdout=log, stderr=subprocess.STDOUT, check=True)
    recipe = subprocess.check_output(['ninja', '-C', str(build), '-t', 'commands',
                                      'src/compiler/nir/nir_tests'], text=True).splitlines()[-1]
    link = [a for a in shlex.split(recipe) if not a.endswith('.o') and
            'libnir_opt_algebraic_pattern_test_' not in a and a != 'src/gtest/libgtest.a' and
            a not in ['-Wl,--whole-archive', '-Wl,--no-whole-archive']]
    link[link.index('-o') + 1] = str(out / 'fixture')
    link.insert(1, str(obj))
    with (out / 'link.log').open('wb') as log:
        subprocess.run(link, cwd=build, stdout=log, stderr=subprocess.STDOUT, check=True)
    cases = [('fragment-flagged', 0), ('fragment-normal', 0), ('compute-normal', 0),
             ('compute-multiple', 0), ('fragment-no-opt-in', -signal.SIGABRT),
             ('fragment-flagged-index', -signal.SIGABRT), ('fragment-flagged-shared', -signal.SIGABRT)]
    results = {}

    def no_core():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    for name, expected in cases:
        result = subprocess.run([str(out / 'fixture'), name], capture_output=True, text=True, preexec_fn=no_core)
        (out / (name + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode != expected:
            raise ValueError(name + ': unexpected exit ' + str(result.returncode))
        if expected != 0 and 'nir_divergence_analysis.c' not in result.stderr:
            raise ValueError(name + ': expected stage assertion not reached')
        results[name] = {'exit': result.returncode, 'expected_exit': expected}
    (out / 'receipt.json').write_text(json.dumps({
        'scope': 'actual candidate NIR library divergence analysis; four semantic cases and three expected stage-assertion controls; no GPU output',
        'candidate_manifest_sha256': sha(args.candidate_manifest), 'fixture_sha256': sha(cpp),
        'nir_divergence_object_sha256': sha(build / 'src/compiler/nir/libnir.a.p/nir_divergence_analysis.c.o'),
        'compile_command': compile_args, 'link_command': link, 'cases': results,
        'hardware_validated': False}, indent=2) + '\n')
    marker.unlink()
    print('Four real-NIR cases and three stage guards pass; no GPU qualification')


if __name__ == '__main__':
    main()
