#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fault-inject the candidate's actual upload helper with mock BO allocation.

Does not create a DRM/Vulkan device. Full-driver compilation and API cleanup are
separate gates. The tested helper is extracted verbatim from --source.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PRELUDE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef int VkResult;
#define VK_SUCCESS 0
#define VK_ERROR_OUT_OF_DEVICE_MEMORY (-2)
#define AGX_BO_EXEC 1
#define AGX_BO_LOW_VA 2
#define AGX_BO_WRITEBACK 4
#define vk_error(dev, error) ((void)(dev), (error))
struct agx_device { int unused; };
struct hk_device { struct agx_device dev; };
struct va { uint64_t addr; };
struct agx_bo { struct va *va; unsigned char memory[128]; };
struct hk_shader {
    struct { struct { size_t binary_size; unsigned preamble_offset;
        struct { unsigned size_16; } rodata; } info;
        const void *binary; } b;
    struct agx_bo *bo, *rodata_bo;
    uint64_t preamble_addr, rodata_addr;
};
static struct agx_bo bos[2];
static struct va addresses[2];
static unsigned calls, fail_call;
static uint64_t mirror_address;
static struct agx_bo *
agx_bo_create(struct agx_device *dev, size_t size, unsigned align,
              unsigned flags, const char *name)
{
    (void)dev; (void)align; (void)name;
    unsigned index = calls++;
    assert(index < 2 && size <= sizeof(bos[index].memory));
    assert(flags == (index ? AGX_BO_WRITEBACK : (AGX_BO_EXEC | AGX_BO_LOW_VA)));
    if (calls == fail_call) return NULL;
    addresses[index].addr = index ? mirror_address : (1ull << 40);
    bos[index].va = &addresses[index];
    return &bos[index];
}
static void *agx_bo_map(struct agx_bo *bo) { return bo->memory; }
'''
TESTS = r'''
#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "case %s failed at line %d: %s\n", name, __LINE__, #condition); \
    return 1; } } while (0)
static int test(const char *name, unsigned fail, bool rodata, uint64_t address,
                VkResult expected, unsigned expected_calls)
{
    struct hk_device dev = {0};
    unsigned char binary[64];
    memset(binary, 0xa5, sizeof(binary));
    struct hk_shader shader = {0};
    shader.b.info.binary_size = sizeof(binary);
    shader.b.info.preamble_offset = 4;
    shader.b.info.rodata.size_16 = rodata ? 1 : 0;
    shader.b.binary = binary;
    memset(bos, 0, sizeof(bos));
    calls = 0; fail_call = fail; mirror_address = address;
    VkResult result = hk_upload_shader_binary(&dev, &shader);
    CHECK(result == expected);
    CHECK(calls == expected_calls);
    if (fail == 1) {
        CHECK(shader.bo == NULL && shader.rodata_bo == NULL);
    } else {
        CHECK(shader.bo == &bos[0]);
        CHECK(memcmp(shader.bo->memory, binary, sizeof(binary)) == 0);
        CHECK(shader.preamble_addr == (1ull << 40) + 4);
    }
    if (rodata && result == VK_SUCCESS) {
        CHECK(shader.rodata_bo == &bos[1]);
        CHECK(shader.rodata_addr == address);
        CHECK(memcmp(shader.rodata_bo->memory, binary, sizeof(binary)) == 0);
    } else {
        CHECK(shader.rodata_addr == 0);
        if (rodata && fail != 1 && fail != 2) {
            unsigned char zero[64] = {0};
            CHECK(memcmp(bos[1].memory, zero, sizeof(zero)) == 0);
        }
    }
    printf("PASS %s\n", name);
    return 0;
}
int main(void)
{
    int result = 0;
    result |= test("low-mirror-success", 0, true, 0x100000, VK_SUCCESS, 2);
    result |= test("no-rodata-single-allocation", 0, false, 0, VK_SUCCESS, 1);
    result |= test("executable-allocation-failure", 1, true, 0, VK_ERROR_OUT_OF_DEVICE_MEMORY, 1);
    result |= test("rodata-allocation-failure", 2, true, 0, VK_ERROR_OUT_OF_DEVICE_MEMORY, 2);
    result |= test("address-at-limit", 0, true, 1ull << 40, VK_ERROR_OUT_OF_DEVICE_MEMORY, 2);
    result |= test("extent-crosses-limit", 0, true, (1ull << 40) - 32, VK_ERROR_OUT_OF_DEVICE_MEMORY, 2);
    result |= test("last-fitting-extent", 0, true, (1ull << 40) - 64, VK_SUCCESS, 2);
    result |= test("address-overflow-guard", 0, true, UINT64_MAX, VK_ERROR_OUT_OF_DEVICE_MEMORY, 2);
    return result;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.read_text()
    begin = source.index('static VkResult\nhk_upload_shader_binary(')
    end = source.index('static VkResult\nhk_upload_shader(', begin)
    helper = source[begin:end]
    if args.output.exists():
        raise ValueError('new test output required')
    args.output.mkdir(parents=True)
    marker = args.output / 'INCOMPLETE'
    marker.touch()
    negative_old = '''      if (!shader->rodata_bo)
         return vk_error(dev, VK_ERROR_OUT_OF_DEVICE_MEMORY);'''
    if helper.count(negative_old) != 1:
        raise ValueError('expected candidate failure branch required')
    results = {}
    for name, text, expected in [('positive', helper, 0),
                                 ('negative-false-success', helper.replace(negative_old,
                                  '      if (!shader->rodata_bo)\n         return VK_SUCCESS;'), 1)]:
        c = args.output / (name + '.c')
        c.write_text(PRELUDE + text + TESTS)
        binary = args.output / name
        command = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                   '-fno-omit-frame-pointer', str(c), '-o', str(binary)]
        subprocess.run(command, check=True)
        result = subprocess.run([str(binary.resolve())], capture_output=True, text=True)
        (args.output / (name + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode != expected:
            raise ValueError(name + ' unexpected exit: ' + str(result.returncode))
        if name.startswith('negative') and 'case rodata-allocation-failure failed' not in result.stderr:
            raise ValueError('negative must fail the allocation-error assertion')
        results[name] = {'exit_code': result.returncode, 'expected_exit_code': expected,
                         'compiler_command': command}
    (args.output / 'receipt.json').write_text(json.dumps({
        'scope': 'verbatim candidate helper with mock BO allocation/address inputs; no DRM/Vulkan device or API destructor execution',
        'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
        'helper_sha256': hashlib.sha256(helper.encode()).hexdigest(), 'cases': 8,
        'sanitizers': ['address', 'undefined'], 'results': results,
        'full_driver_compiled': False, 'factory_promotion': False, 'hardware_validated': False}, indent=2) + '\n')
    marker.unlink()
    print('Eight helper cases pass; false-success negative is detected; full-driver gates remain')


if __name__ == '__main__':
    main()
