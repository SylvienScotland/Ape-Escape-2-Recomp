#!/usr/bin/env python3
"""Trace EE->IOP audio-relevant copies: APE2_SIF_TRACE=1.

The SPU2 tap proved the streamed PCM buffer at 0x4be40 is all zeros, while the disc has real 16-bit PCM at the
sectors the game reads and the EE-side sceCdStRead consumes them. So the data dies between EE memory and IOP
memory. sceSifSetDma copies (readEeRange -> writeIopMemory) but silently abandons the whole transfer when a
descriptor's source or destination fails range validation, and that path was only visible under aggressive logs
(compiled off). This adds a permanent, env-gated trace plus an unconditional rejection trace.
"""
import shutil
import tempfile

SIF = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\Kernel\Stubs\SIF.cpp"
RT = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\ps2_runtime.cpp"


def load(path):
    with open(path, "r", encoding="utf-8", newline=None) as f:
        return f.read()


def save(path, text):
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)


bak = tempfile.gettempdir()

# ---- SIF.cpp: trace accepted transfers, and every rejection with its addresses -------------------------
sif = load(SIF)
orig = sif

anchor = """            if (!runtime || !canAccessEeRange(rdram, xfer.src, sizeBytes) || !runtime->isIopMemoryRange(xfer.dest, sizeBytes))
            {
                ok = false;
                break;
            }"""
if anchor not in sif:
    anchor = anchor.replace("\n", "\r\n")
assert sif.count(anchor) == 1, ("sif reject anchor", sif.count(anchor))
sif = sif.replace(anchor, """            if (!runtime || !canAccessEeRange(rdram, xfer.src, sizeBytes) || !runtime->isIopMemoryRange(xfer.dest, sizeBytes))
            {
                static unsigned rejected = 0u;
                if (rejected < 24u)
                {
                    ++rejected;
                    std::cerr << "[sif:dma:reject] src=0x" << std::hex << xfer.src << " dst=0x" << xfer.dest
                              << " size=0x" << sizeBytes << std::dec << std::endl;
                }
                ok = false;
                break;
            }""", 1)

anchor2 = """                const uint32_t sizeBytes = static_cast<uint32_t>(xfer.size);
                std::vector<uint8_t> payload(sizeBytes);"""
if anchor2 not in sif:
    anchor2 = anchor2.replace("\n", "\r\n")
assert sif.count(anchor2) == 1, ("sif copy anchor", sif.count(anchor2))
sif = sif.replace(anchor2, """                const uint32_t sizeBytes = static_cast<uint32_t>(xfer.size);
                if (std::getenv("APE2_SIF_TRACE"))
                {
                    static unsigned traced = 0u;
                    if (traced < 80u)
                    {
                        ++traced;
                        std::cerr << "[sif:dma] src=0x" << std::hex << xfer.src << " dst=0x" << xfer.dest
                                  << " size=0x" << sizeBytes << std::dec << std::endl;
                    }
                }
                std::vector<uint8_t> payload(sizeBytes);""", 1)
assert sif != orig
shutil.copyfile(SIF, bak + r"\SIF.cpp.pretrace")
save(SIF, sif)

# ---- ps2_runtime.cpp: trace every write into IOP memory ------------------------------------------------
rt = load(RT)
orig = rt
anchor3 = """bool PS2Runtime::writeIopMemory(uint32_t address, const void *source, size_t size)
{
    return m_iopSubsystem && m_iopSubsystem->writeMemory(address, source, size);
}"""
if anchor3 not in rt:
    anchor3 = anchor3.replace("\n", "\r\n")
assert rt.count(anchor3) == 1, ("runtime anchor", rt.count(anchor3))
rt = rt.replace(anchor3, """bool PS2Runtime::writeIopMemory(uint32_t address, const void *source, size_t size)
{
    if (std::getenv("APE2_SIF_TRACE"))
    {
        static unsigned traced = 0u;
        if (traced < 80u)
        {
            ++traced;
            std::cerr << "[iop:write] addr=0x" << std::hex << address << " size=0x" << size << std::dec << std::endl;
        }
    }
    return m_iopSubsystem && m_iopSubsystem->writeMemory(address, source, size);
}""", 1)
assert rt != orig
shutil.copyfile(RT, bak + r"\ps2_runtime.cpp.pretrace")
save(RT, rt)

print("patched SIF.cpp and ps2_runtime.cpp")
print("sif traces:", sif.count("APE2_SIF_TRACE") + sif.count("sif:dma"), "runtime traces:", rt.count("APE2_SIF_TRACE"))
