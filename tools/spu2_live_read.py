#!/usr/bin/env python3
"""0074: play the SPU2 ring from live IOP RAM instead of a copy taken at arm time.

The shadow ring was added to stop tearing, but it also freezes each slot at whatever it held when the driver last
armed it. The driver fills slots in place, so a slot that is rewritten without a fresh CHCR start keeps playing its
old audio - which is exactly the repeated ~10 ms of music that measures as block[i] == block[i+2] in 76% of arms.

Hardware has no shadow: the SPU2 ADMA engine reads the ring out of IOP RAM in realtime while the driver refills
behind the read pointer. This switches playback to that model and keeps the shadow behind APE2_SPU2_SHADOW=1 for
A/B listening. It also adds APE2_SPU2_PCM=<file>, which appends the exact PCM handed to the audio device so the
emitted signal - rather than the source blocks - can be measured.
"""
import sys

PATH = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

if "shadowPlayback" in text:
    print("already patched")
    sys.exit(0)

# ---- helper: which source to read
old = """            Spu2Ring &spu2Ring()
            {
                static Spu2Ring ring;
                return ring;
            }"""
new = """            Spu2Ring &spu2Ring()
            {
                static Spu2Ring ring;
                return ring;
            }

            // 0074: playback reads the ring out of live IOP RAM the way the SPU2 ADMA engine does. The shadow copy
            // freezes a slot at its arm-time contents, so a slot the driver rewrites in place keeps replaying old
            // audio. APE2_SPU2_SHADOW=1 restores the old behaviour for comparison.
            bool shadowPlayback()
            {
                static const bool value = std::getenv("APE2_SPU2_SHADOW") != nullptr;
                return value;
            }"""
if text.count(old) != 1:
    raise SystemExit(f"ERROR: ring accessor matched {text.count(old)} times")
text = text.replace(old, new, 1)

# ---- read from the chosen source
old_copy = """        constexpr uint32_t kFrameBytes = 4u; // 16-bit stereo
        auto *out = reinterpret_cast<uint8_t *>(destination);
        for (size_t produced = 0u; produced < frameCount; ++produced)
        {
            std::memcpy(out + produced * kFrameBytes, ring.shadow.data() + (ring.cursor - ring.base), kFrameBytes);
            ring.cursor += kFrameBytes;"""
new_copy = """        constexpr uint32_t kFrameBytes = 4u; // 16-bit stereo
        const bool useShadow = shadowPlayback();
        const uint8_t *source = useShadow ? ring.shadow.data() : m_ram.data();
        const uint32_t sourceBase = useShadow ? ring.base : 0u;
        const size_t sourceSize = useShadow ? static_cast<size_t>(ring.size) : m_ram.size();
        if (ring.base >= m_ram.size() || ring.size == 0u || static_cast<size_t>(ring.base) + ring.size > sourceSize)
            return 0u;
        auto *out = reinterpret_cast<uint8_t *>(destination);
        for (size_t produced = 0u; produced < frameCount; ++produced)
        {
            const size_t offset = ring.cursor - sourceBase;
            if (offset + kFrameBytes <= sourceSize)
                std::memcpy(out + produced * kFrameBytes, source + offset, kFrameBytes);
            ring.cursor += kFrameBytes;"""
if text.count(old_copy) != 1:
    raise SystemExit(f"ERROR: playback loop matched {text.count(old_copy)} times")
text = text.replace(old_copy, new_copy, 1)

# ---- tap the emitted PCM
old_tail = """        ring.framesOut += frameCount;
        return frameCount;"""
new_tail = """        ring.framesOut += frameCount;
        // 0074: APE2_SPU2_PCM=<file> appends the PCM actually sent to the device, so output can be measured
        // directly instead of inferring it from the source blocks.
        if (const char *pcmPath = std::getenv("APE2_SPU2_PCM"))
        {
            static std::FILE *pcmFile = nullptr;
            static bool opened = false;
            if (!opened)
            {
                opened = true;
                pcmFile = std::fopen(pcmPath, "wb");
            }
            if (pcmFile)
            {
                std::fwrite(out, kFrameBytes, frameCount, pcmFile);
                std::fflush(pcmFile);
            }
        }
        return frameCount;"""
if text.count(old_tail) != 1:
    raise SystemExit(f"ERROR: tail matched {text.count(old_tail)} times")
text = text.replace(old_tail, new_tail, 1)

open(PATH, "w", encoding="utf-8", newline="\r\n").write(text)
print("live-read playback installed")
