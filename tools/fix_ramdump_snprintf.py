#!/usr/bin/env python3
"""Repair the literal newline that a generator slip put inside the RAM-snapshot fprintf string.

tools/spu2_ramdump.py emitted "(arm %u)<LF>", ramDumps, arms); which is C2001: newline in constant.
The intended source is the two-character escape \\n. chr(92) is used so this file's own escaping can never
corrupt the replacement again.
"""
CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"

src = open(CPP, "r", encoding="utf-8", newline=None).read()
src = src.replace("\r\n", "\n")

bad = '("[IOP] RAM snapshot %u (arm %u)\n", ramDumps, arms);'
good = '("[IOP] RAM snapshot %u (arm %u)' + chr(92) + 'n", ramDumps, arms);'

n = src.count(bad)
print("broken snprintf occurrences:", n)
if n == 1:
    src = src.replace(bad, good)
    open(CPP, "w", encoding="utf-8", newline="\r\n").write(src)
    print("repaired")
elif n == 0:
    print("nothing to repair (already correct)")
else:
    raise SystemExit("ambiguous: refusing to patch")
