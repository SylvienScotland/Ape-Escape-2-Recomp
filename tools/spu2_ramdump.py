#!/usr/bin/env python3
"""0074: snapshot all of IOP RAM a few times per run.

The SPU2 ADMA tap shows core1 streaming from 0x4be40 at the right rate, but the tapped data is digital
silence (peak +/-2 over 20 MB), while SIF DMAs deposit real payloads into a ring at 0xc32c0. Rather than keep
guessing which buffer the sound driver is supposed to consume, dump the entire 2 MB of IOP RAM at three points
in the run and measure amplitude by address. That shows, by measurement, where the PCM actually lives.
"""
import sys

CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"

src = open(CPP, "r", encoding="utf-8", newline=None).read()
if "RAM snapshot" in src:
    print("patch already present")
    sys.exit(0)

src = src.replace("\r\n", "\n")
anchor = "                std::vector<uint8_t> block(static_cast<size_t>(transferWords) * 4u);"
n = src.count(anchor)
if n != 1:
    print(f"ERROR: anchor found {n} times, refusing to patch")
    sys.exit(1)

dump = """                // 0074: full IOP RAM snapshots, to locate the PCM by measurement rather than guesswork.
                {
                    static unsigned ramDumpArms[2] = {0u, 0u};
                    unsigned &arms = ramDumpArms[secondCore ? 1 : 0];
                    ++arms;
                    static unsigned ramDumps = 0u;
                    if (ramDumps < 3u && arms >= (ramDumps + 1u) * 40u)
                    {
                        ++ramDumps;
                        char ramPath[512];
                        std::snprintf(ramPath, sizeof(ramPath), "%s/iopram_%u.bin", dumpDir, ramDumps);
                        if (std::FILE *ramFile = std::fopen(ramPath, "wb"))
                        {
                            std::fwrite(m_ram.data(), 1, m_ram.size(), ramFile);
                            std::fclose(ramFile);
                            std::fprintf(stderr, "[IOP] RAM snapshot %u (arm %u)\\n", ramDumps, arms);
                        }
                    }
                }
""" + anchor

src = src.replace(anchor, dump, 1)
open(CPP, "w", encoding="utf-8", newline="\r\n").write(src)
print("patch applied")
