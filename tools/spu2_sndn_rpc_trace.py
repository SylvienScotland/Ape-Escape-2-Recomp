#!/usr/bin/env python3
"""0092: log what the EE asks the sndn driver to do, and what the driver returns.

The driver function runs many times but programmes no voice register, so the next question is whether those calls carry
real commands and whether they succeed. Command id and returned pointer are enough to tell "commands arrive and are
accepted" from "commands arrive and are rejected" - a rejection means the driver's own state is broken, an acceptance
means the work is queued on the driver thread and lost there.
"""
import sys

PATH = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\services\iop_rpc.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

anchor = """        uint32_t returnPointer = executor.executeGuestFunction(server.function,
                                                               request.function,
                                                               server.buffer,
                                                               request.send.size,
                                                               0u,
                                                               server.gp);
        if (returnPointer == 0u)
            returnPointer = server.buffer;
"""

if "sndn cmd=" in text:
    print("already patched")
    sys.exit(0)

count = text.count(anchor)
if count != 1:
    print(f"FAIL: anchor matched {count} times")
    sys.exit(1)

addition = """        // 0092: what the EE asks of the sound driver, and what it answers.
        if (request.sid == 0x736E646Eu)
        {
            static unsigned sndnCalls = 0u;
            if (++sndnCalls <= 40u)
                std::fprintf(stderr, "[sndn] cmd=0x%x send=%u ret=0x%x buffer=0x%x\\n", request.function,
                             request.send.size, returnPointer, server.buffer);
        }
"""

text = text.replace(anchor, anchor + addition, 1)
open(PATH, "w", encoding="utf-8", newline="\r\n").write(text)
print("sndn trace installed")
