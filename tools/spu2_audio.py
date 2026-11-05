#!/usr/bin/env python3
"""0075: give the SPU2 an output path.

Measurement (log entries 0070-0074) settled the audio question: the game streams 16-bit stereo PCM at 48 kHz
off the disc, through the EE (sceCdStRead), across SIF DMA into an IOP ring, and the IOP driver arms SPU2 core1
auto-DMA on it. Every stage works -- the SPU2 is the only place audio dies, because this emulator models SPU2 as
a register map that discards DMA blocks.

So instead of a full SPU2 (voices, envelopes, ADPCM, reverb), this wires the one path the game actually uses:
the armed ADMA buffer is treated as the head of the playback stream, and frames are handed out at the hardware
rate the emulator already assumes (768 IOP cycles per 4-byte stereo frame = 48 kHz). The runtime pumps that into
the existing raylib audio device as a stream.

Deliberately not done here: mixing core0 voices, ADPCM voice decoding, SPU2 registers/IRQ semantics. Those are
needed for SFX but not for the streamed music this game boots with.
"""
import sys

IOP_H = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.h"
IOP_CPP = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"
AUDIO_H = r"C:\dev\PS2Recomp\ps2xRuntime\include\runtime\ps2_audio.h"
AUDIO_CPP = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\ps2_audio.cpp"


def load(path):
    return open(path, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")


def save(path, text):
    open(path, "w", encoding="utf-8", newline="\r\n").write(text)


def patch(path, edits):
    text = load(path)
    for name, (old, new) in edits:
        if new.strip() and new.strip().splitlines()[0] in text and name.startswith("skipif"):
            print(f"  {path}: {name} already present")
            continue
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"ERROR {path}: anchor '{name}' matched {n} times")
        text = text.replace(old, new, 1)
    save(path, text)
    print(f"  patched {path}")


# ---------------------------------------------------------------- IOP memory header
patch(IOP_H, [
    ("function include",
     ("#include <cstdint>", "#include <cstdint>\n#include <functional>")),
    ("function decl",
     ("        [[nodiscard]] std::span<const uint8_t> ram() const noexcept { return m_ram; }",
      """        [[nodiscard]] std::span<const uint8_t> ram() const noexcept { return m_ram; }

        // 0075: SPU2 playback. The game feeds streamed PCM into IOP RAM and arms SPU2 auto-DMA on it; the DMA
        // block used to be discarded, so nothing was ever audible. pullSpu2Pcm hands the armed buffer to the
        // host as 16-bit stereo frames, advancing a read cursor at the hardware playback rate.
        [[nodiscard]] size_t pullSpu2Pcm(int16_t *destination, size_t frameCount);
        [[nodiscard]] bool spu2StreamArmed() const noexcept { return m_spu2Armed; }""")),
    ("state members",
     ("        mutable IopSio2 m_sio2; // mutable: reading DATAOUT pops its FIFO (patch 0018)",
      """        mutable IopSio2 m_sio2; // mutable: reading DATAOUT pops its FIFO (patch 0018)
        uint32_t m_spu2ReadAddr = 0u; // playback cursor inside the armed auto-DMA buffer
        bool m_spu2Armed = false;""")),
])

# ---------------------------------------------------------------- IOP memory implementation
patch(IOP_CPP, [
    ("arm hook",
     ("        const bool autoDma = (admas & (secondCore ? 2u : 1u)) != 0u;\n"
      "        if (autoDma)\n"
      "            delayCycles = std::max<uint64_t>(delayCycles, transferWords * kAdmaCyclesPerWord);",
      """        const bool autoDma = (admas & (secondCore ? 2u : 1u)) != 0u;
        if (autoDma)
            delayCycles = std::max<uint64_t>(delayCycles, transferWords * kAdmaCyclesPerWord);

        // 0075: the auto-DMA source is the stream the SPU2 is expected to play. Record it as the playback head.
        // Re-arming with the same address is a re-read of a block already handed out, so only the address is
        // tracked here; pullSpu2Pcm walks forward from it at 48 kHz.
        if (autoDma && secondCore)
        {
            const uint32_t madrWord = 0x1F801500u;
            uint32_t streamSource = 0u;
            if (const auto current = m_hardware.find(madrWord); current != m_hardware.end())
                streamSource = current->second & 0x1FFFFFu;
            if (streamSource != 0u)
            {
                m_spu2ReadAddr = streamSource;
                m_spu2Armed = true;
            }
        }""")),
    ("pull impl",
     ("    std::optional<IopMemory::DmaStart> IopMemory::takeDmaStart() noexcept",
      """    size_t IopMemory::pullSpu2Pcm(int16_t *destination, size_t frameCount)
    {
        if (!destination || frameCount == 0u || !m_spu2Armed)
            return 0u;

        constexpr uint32_t kFrameBytes = 4u; // 16-bit stereo
        auto *out = reinterpret_cast<uint8_t *>(destination);
        size_t produced = 0u;
        while (produced < frameCount)
        {
            if (m_spu2ReadAddr + kFrameBytes > RamSize)
            {
                m_spu2Armed = false;
                break;
            }
            std::memcpy(out + produced * kFrameBytes, m_ram.data() + m_spu2ReadAddr, kFrameBytes);
            m_spu2ReadAddr = (m_spu2ReadAddr + kFrameBytes) & (RamSize - 1u);
            ++produced;
        }
        return produced;
    }

    std::optional<IopMemory::DmaStart> IopMemory::takeDmaStart() noexcept""")),
])

# ---------------------------------------------------------------- runtime audio backend
patch(AUDIO_H, [
    ("push decl",
     ("    void setAudioReady(bool ready) { m_audioReady = ready; }",
      """    void setAudioReady(bool ready) { m_audioReady = ready; }

    // 0075: feed emulated SPU2 output (interleaved 16-bit stereo at 48 kHz) to the host device.
    void pushStreamPcm(const int16_t *pcm, size_t frames);""")),
])

patch(AUDIO_CPP, [
    ("impl members",
     ("""    std::vector<TrackedSound> activeSounds;
};""",
      """    std::vector<TrackedSound> activeSounds;

    // 0075: streamed SPU2 output. A ring decouples the emulation's frame-rate pulls from the device's own
    // consumption, so a slow video frame does not punch a hole in the music.
    static constexpr size_t kStreamRate = 48000u;
    static constexpr size_t kRingFrames = 48000u * 2u;
    std::vector<int16_t> streamRing = std::vector<int16_t>(kRingFrames * 2u, 0);
    size_t ringHead = 0u;
    size_t ringCount = 0u;
};""")),
    ("push impl",
     ("void PS2AudioBackend::pruneFinishedSounds()",
      """void PS2AudioBackend::pushStreamPcm(const int16_t *pcm, size_t frames)
{
#if defined(PLATFORM_VITA)
    (void)pcm;
    (void)frames;
    return;
#else
    if (!m_audioReady || !pcm || frames == 0u)
        return;

    std::lock_guard<std::mutex> lock(m_mutex);
    auto &impl = *m_impl;

    if (!impl.streamReady)
    {
        impl.stream = LoadAudioStream(static_cast<unsigned>(Impl::kStreamRate), 16u, 2u);
        if (!IsAudioStreamValid(impl.stream))
            return;
        PlayAudioStream(impl.stream);
        impl.streamReady = true;
    }

    for (size_t i = 0; i < frames; ++i)
    {
        const size_t slot = (impl.ringHead + impl.ringCount) % Impl::kRingFrames;
        impl.streamRing[slot * 2u + 0u] = pcm[i * 2u + 0u];
        impl.streamRing[slot * 2u + 1u] = pcm[i * 2u + 1u];
        if (impl.ringCount < Impl::kRingFrames)
            ++impl.ringCount;
        else
            impl.ringHead = (impl.ringHead + 1u) % Impl::kRingFrames; // overrun: drop oldest
    }

    // Top the device up whenever it has consumed what it was given.
    constexpr size_t kChunk = 512u;
    while (impl.ringCount >= kChunk && IsAudioStreamProcessed(impl.stream))
    {
        int16_t block[kChunk * 2u];
        const size_t head = impl.ringHead;
        const size_t first = std::min(kChunk, Impl::kRingFrames - head);
        for (size_t i = 0; i < first; ++i)
        {
            block[i * 2u + 0u] = impl.streamRing[(head + i) * 2u + 0u];
            block[i * 2u + 1u] = impl.streamRing[(head + i) * 2u + 1u];
        }
        for (size_t i = first; i < kChunk; ++i)
        {
            const size_t slot = (head + i) % Impl::kRingFrames;
            block[i * 2u + 0u] = impl.streamRing[slot * 2u + 0u];
            block[i * 2u + 1u] = impl.streamRing[slot * 2u + 1u];
        }
        UpdateAudioStream(impl.stream, block, static_cast<int>(kChunk));
        impl.ringHead = (impl.ringHead + kChunk) % Impl::kRingFrames;
        impl.ringCount -= kChunk;
    }
#endif
}

void PS2AudioBackend::pruneFinishedSounds()""")),
])

print("all patches applied")
