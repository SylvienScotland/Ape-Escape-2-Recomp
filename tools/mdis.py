#!/usr/bin/env python3
"""Quick EE disassembly of SLUS_206.85 by guest address (for reading [perf:pc] hot spots).

    pip install capstone
    python tools/mdis.py game/SLUS_206.85 0x19bce0 64

Capstone decodes generic MIPS64, not R5900: MMI ops, lq/sq and COP2 macro ops (e.g. lqc2 shown as
bbit032, vadd as '??') are wrong or missing. Good enough to see calls, loads/stores and loops; use the
generated C++ (generated/output, with instruction comments) for the exact semantics.
"""
import struct
import sys

import capstone


def load_segments(path):
    data = open(path, "rb").read()
    phoff, = struct.unpack_from("<I", data, 0x1C)
    phentsize, phnum = struct.unpack_from("<HH", data, 0x2A)
    segs = []
    for i in range(phnum):
        p_type, p_off, p_vaddr, _, p_filesz = struct.unpack_from("<5I", data, phoff + i * phentsize)
        if p_type == 1 and p_filesz:
            segs.append((p_vaddr, data[p_off:p_off + p_filesz]))
    return segs


def read_word(segs, addr):
    for base, blob in segs:
        if base <= addr < base + len(blob) - 3:
            return blob[addr - base:addr - base + 4]
    return None


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    segs = load_segments(sys.argv[1])
    start = int(sys.argv[2], 16) & ~3
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 64
    md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS64 | capstone.CS_MODE_LITTLE_ENDIAN)
    for i in range(count):
        addr = start + 4 * i
        word = read_word(segs, addr)
        if word is None:
            print(f"{addr:08x}: <outside ELF>")
            break
        ins = next(md.disasm(word, addr), None)
        text = f"{ins.mnemonic} {ins.op_str}" if ins else "??"
        print(f"{addr:08x}: {word[::-1].hex()}  {text}")


if __name__ == "__main__":
    main()
