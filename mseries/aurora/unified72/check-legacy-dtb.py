#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check the retained J314S DTB and execute the pinned DART window parser on host."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import struct
import subprocess


def fdt(data):
    if len(data) < 40:
        raise ValueError("truncated FDT header")
    magic, total, start, strings, _, version, _, _, string_size, size = struct.unpack_from(">10I", data)
    if magic != 0xd00dfeed or total != len(data) or version < 17 or start + size > total or strings + string_size > total:
        raise ValueError("unsupported FDT bounds/version")
    pos, stack, nodes = start, [], {}
    while pos < start + size:
        token = struct.unpack_from(">I", data, pos)[0]
        pos += 4
        if token == 1:
            end = data.index(b"\0", pos, start + size)
            stack.append(data[pos:end].decode())
            nodes["/" + "/".join(stack[1:])] = {}
            pos = (end + 4) & ~3
        elif token == 2:
            if not stack:
                raise ValueError("unbalanced FDT node")
            stack.pop()
        elif token == 3:
            length, offset = struct.unpack_from(">II", data, pos)
            pos += 8
            if not stack or offset >= string_size or pos + length > start + size:
                raise ValueError("invalid FDT property")
            end = data.index(b"\0", strings + offset, strings + string_size)
            name = data[strings + offset:end].decode()
            nodes["/" + "/".join(stack[1:])][name] = data[pos:pos + length]
            pos = (pos + length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            if stack:
                raise ValueError("unclosed FDT node")
            return nodes
        else:
            raise ValueError("unknown FDT token")
    raise ValueError("missing FDT end token")


def strings(value):
    return value.rstrip(b"\0").decode().split("\0") if value else []


def cells(value):
    if len(value) % 4:
        raise ValueError("unaligned cell array")
    return struct.unpack(">" + "I" * (len(value) // 4), value)


def function(text, name):
    match = re.search(r"^static int " + re.escape(name) + r"\(", text, re.M)
    if not match:
        raise ValueError("production parser missing")
    pos = text.index("{", match.start()) + 1
    depth = 1
    while depth:
        depth += (text[pos] == "{") - (text[pos] == "}")
        pos += 1
    return text[match.start():pos]


def check(dtb, source, output):
    if output.exists():
        raise ValueError("preserve prior controls; choose a new output")
    data = dtb.read_bytes()
    if hashlib.sha256(data).hexdigest() != "a29ff68864e785f05f5f3e44d5bea8ab3166ac52958ea52023c2fa40740fd306":
        raise ValueError("not the reviewed retained J314S DTB")
    nodes = fdt(data)
    if "apple,j314s" not in strings(nodes["/"]["compatible"]):
        raise ValueError("wrong board")
    providers, phandles = {}, {}
    for path, props in nodes.items():
        if "phandle" in props:
            phandles[cells(props["phandle"])[0]] = path
        compatible = strings(props.get("compatible", b""))
        if not any("-dart" in name for name in compatible):
            continue
        if not set(compatible).intersection(("apple,t6000-dart", "apple,t8103-dart", "apple,t8110-dart")):
            raise ValueError("unreviewed DART hardware compatible: " + path)
        if cells(props.get("#iommu-cells", b"")) != (1,):
            raise ValueError("retained DTB is not the legacy one-cell format")
        window = props.get("apple,dma-range")
        base, length = struct.unpack(">QQ", window) if window is not None else (0, 1 << 32)
        # Legacy windows can have a high constant DVA prefix. The driver checks
        # the width of the span with XOR, not the absolute end against 2**IAS.
        if not length or base + length > 1 << 64:
            raise ValueError("legacy DMA window overflows")
        if "apple,t6000-dart" in compatible and (base ^ (base + length - 1)) >> 32:
            raise ValueError("legacy T6000 window crosses its address-width span")
        providers[path] = {"compatible": compatible, "base": base, "size": length,
                           "window_input": "DT property" if window is not None else "modeled 32-bit default; hardware parameter registers not emulated"}
    clients = []
    for path, props in nodes.items():
        if "iommus" not in props:
            continue
        args, index = cells(props["iommus"]), 0
        while index < len(args):
            provider = phandles[args[index]]
            count = cells(nodes[provider]["#iommu-cells"])[0]
            if index + 1 + count > len(args):
                raise ValueError("truncated IOMMU specifier")
            if provider in providers:
                clients.append({"client": path, "provider": provider, "stream": args[index + 1]})
            index += 1 + count
    if not providers or not clients:
        raise ValueError("no reviewed DART topology")
    body = function(source.read_text(), "apple_dart_parse_dma_window")
    code = r'''// SPDX-License-Identifier: GPL-2.0-only
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <errno.h>
typedef uint32_t u32;
typedef uint64_t dma_addr_t;
struct device { int unused; };
struct apple_dart { dma_addr_t dma_min, dma_max; u32 ias, pgsize; };
struct of_phandle_args { int args_count; u32 args[6]; };
#define DMA_BIT_MASK(n) ((n) == 64 ? UINT64_MAX : ((UINT64_C(1) << (n)) - 1))
#define IS_ALIGNED(x,a) (!((x) & ((a) - 1)))
#define check_add_overflow(a,b,out) __builtin_add_overflow((a),(b),(out))
#define dev_err(...) ((void)0)
'''
    code += body
    code += r'''
static unsigned int checks;
static void legacy(uint64_t base, uint64_t size, unsigned int sid) {
 struct device dev={0}; struct apple_dart dart={.dma_min=base,.dma_max=base+size-1,.ias=32,.pgsize=16384};
 struct of_phandle_args args={.args_count=1,.args={sid}}; dma_addr_t first=0,last=0;
 assert(!apple_dart_parse_dma_window(&dev,&dart,&args,&first,&last));
 assert(first==base && last==base+size-1); checks++;
}
static void window(unsigned int bits, uint64_t base, uint64_t size) {
 struct device dev={0}; struct apple_dart dart={.dma_min=0,.dma_max=DMA_BIT_MASK(bits),.ias=bits,.pgsize=16384};
 struct of_phandle_args args={.args_count=5,.args={0,base>>32,base,size>>32,size}}; dma_addr_t first=0,last=0;
 assert(!apple_dart_parse_dma_window(&dev,&dart,&args,&first,&last));
 assert(first==base && last==base+size-1); checks++;
}
int main(void) {
'''
    for client in clients:
        window = providers[client["provider"]]
        code += f"legacy({window['base']}ULL,{window['size']}ULL,{client['stream']}U);\n"
    code += r'''
 window(32,0,0xfc000000); window(42,0x10000000000ULL,0x1000000000ULL); window(36,0x800000000ULL,0x7ffff0000ULL);
 window(32,0x1f000000000ULL,0xfc000000);
 struct device dev={0}; struct apple_dart dart={.dma_min=0,.dma_max=0xffffffff,.ias=32,.pgsize=16384};
 struct of_phandle_args args={0}; dma_addr_t first,last;
 for (unsigned int n=0;n<=6;n++) { if(n==1||n==5)continue; args.args_count=n;
  assert(apple_dart_parse_dma_window(&dev,&dart,&args,&first,&last)==-EINVAL); checks++; }
 args.args_count=5; assert(apple_dart_parse_dma_window(&dev,&dart,&args,&first,&last)==-EINVAL); checks++;
 args.args[2]=1;args.args[4]=16384;assert(apple_dart_parse_dma_window(&dev,&dart,&args,&first,&last)==-EINVAL); checks++;
 args.args[2]=0;args.args[4]=1;assert(apple_dart_parse_dma_window(&dev,&dart,&args,&first,&last)==-EINVAL); checks++;
 args.args[2]=0xffffc000;args.args[4]=32768;assert(apple_dart_parse_dma_window(&dev,&dart,&args,&first,&last)==-EINVAL); checks++;
 dart.ias=64;dart.dma_max=UINT64_MAX;args.args[1]=0xffffffff;args.args[2]=0xffffc000;args.args[4]=32768;
 assert(apple_dart_parse_dma_window(&dev,&dart,&args,&first,&last)==-EINVAL);checks++;
 printf("%u parser controls passed\n",checks);
}
'''
    output.mkdir(parents=True)
    generated = output / "parser-controls.c"
    generated.write_text(code)
    subprocess.run(["cc", "-std=gnu11", "-Wall", "-Werror", str(generated), "-o", str(output / "parser-controls")], check=True)
    run = subprocess.run([str(output / "parser-controls")], capture_output=True, text=True,
                         preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
    (output / "run.log").write_text(run.stdout + run.stderr)
    run.check_returncode()
    result = {"schema": 1, "kind": "retained-dtb-dart-host-controls", "dtb_sha256": hashlib.sha256(data).hexdigest(),
              "production_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "production_function_sha256": hashlib.sha256(body.encode()).hexdigest(),
              "fixture_sha256": hashlib.sha256(code.encode()).hexdigest(), "providers": providers,
              "legacy_client_specifiers": len(clients), "stdout": run.stdout,
              "result": "pass", "limits": "Unmodified parser executed with DT-derived legacy geometry and synthetic new/invalid windows. Not a DART probe, firmware, complete DT compatibility or hardware boot qualification."}
    (output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(run.stdout, end="")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dtb", "source", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    check(args.dtb, args.source, args.output)
