#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the production optional-gauge discovery function with mocked SMC I/O."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    text = (args.source / "drivers/power/supply/macsmc-power.c").read_text()
    start = text.index("static int macsmc_battery_optional_properties(")
    end = text.index("\nstatic int macsmc_power_probe(", start)
    function = text[start:end]
    names = re.findall(r"BATT_OPTIONAL\((\w+), (\w+), (\d+)\)", function)
    if len(names) != 16:
        raise ValueError("review the harness when the production optional-property table changes")
    enums = "enum power_supply_property {" + ",".join("POWER_SUPPLY_PROP_" + prop for prop, _, _ in names) + "};\n"
    # Distinct mock key identities preserve shared-key behavior (charge and energy).
    keys = list(dict.fromkeys(key for _, key, _ in names))
    enums += "enum {" + ",".join(keys) + "};\n"
    harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef unsigned smc_key;
#define SMC_KEY(key) key
#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))
#define APPLE_SMC_READABLE 128
#define dev_dbg(...) ((void)0)
struct apple_smc_key_info { unsigned size; unsigned flags; };
struct macsmc_power { void *smc; void *dev; };
static int mode, selected = -1, reads;
static int apple_smc_get_key_info(void *smc, smc_key key, struct apple_smc_key_info *info)
{
    (void)smc;
    info->size = key == BAAC ? 8 : 2;
    info->flags = APPLE_SMC_READABLE;
    if ((int)key != selected) return 0;
    if (mode == 1) return -1;
    if (mode == 2) info->size = 255;
    if (mode == 3) info->flags = 0;
    return 0;
}
static int apple_smc_read(void *smc, smc_key key, u8 *value, unsigned size)
{
    (void)smc;
    reads++;
    assert(size <= 8);
    if ((int)key == selected && mode == 4) return -1;
    memset(value, 0, size);
    if ((int)key == selected && mode == 5) return size - 1;
    return size;
}
'''
    harness += function
    harness += r'''
int main(void)
{
    struct macsmc_power power = {0};
    enum power_supply_property props[50];
    memset(props, 0xff, sizeof(props));
    int n = macsmc_battery_optional_properties(&power, props, 16);
    assert(n == 32 && reads == 16);
    for (int i = 0; i < 16; i++) assert(props[16 + i] == i);
    assert((int)props[32] == -1);
    /* Omit each key under every failure mode, including both properties for shared keys. */
    for (selected = 0; selected <= BAAC; selected++) {
        int omitted = selected == B0DC || selected == B0FC || selected == B0RM ? 2 : 1;
        for (mode = 1; mode <= 5; mode++) {
            reads = 0;
            memset(props, 0xff, sizeof(props));
            n = macsmc_battery_optional_properties(&power, props, 16);
            assert(n == 32 - omitted);
            assert((int)props[n] == -1);
            assert(reads == (mode <= 3 ? 16 - omitted : 16));
        }
    }
    puts("macsmc: all-readable and 65 per-key failure cases passed (ASan/UBSan)");
}
'''
    with tempfile.TemporaryDirectory(prefix="macsmc-discovery-") as temporary:
        root = Path(temporary)
        source, binary = root / "test.c", root / "test"
        # Enums must precede the mock functions that use BAAC.
        source.write_text(enums + harness)
        subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-Wno-sign-compare", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                        str(source), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
