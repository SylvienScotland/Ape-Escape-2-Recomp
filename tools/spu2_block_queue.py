#!/usr/bin/env python3
"""0074: play each armed auto-DMA block once, in arm order, instead of wrapping a learned ring.

Measured on the emitted PCM (APE2_SPU2_PCM tap): 98.4% of adjacent 512-frame output chunks were byte-identical and
the signal correlated 1.00 at lag 64 frames, i.e. the device was fed a frozen 2 KB window looping every 10.7 ms
while framesOut advanced at the correct 48 kHz. Auto-DMA is a block transfer per interrupt, so the armed sequence
*is* the stream; wrapping the newest 2 KB instead replays a fraction of a frame of history forever.

This replaces ring-wrap playback with a queue of armed blocks, played one at a time with the last frame held on
underrun (silence injection would be a worse regression than a held sample).
"""
import sys

PATH = r"C:\dev\PS2Recomp\ps2xIOP\src\emulator\core\iop_memory.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

if "Spu2Queue" in text:
    print("already patched")
    sys.exit(0)


def function_span(src, signature):
    """Return (start, end) of a top-level function, brace matched from its opening brace."""
    start = src.index(signature)
    brace = src.index("{", start)
    depth = 0
    for i in range(brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                while end < len(src) and src[end] in "\r\n":
                    end += 1
                return start, end
    raise SystemExit("ERROR: unbalanced braces")


if "#include <array>" not in text:
    text = text.replace("#include <algorithm>", "#include <algorithm>\n#include <array>", 1)

# ---- 1. queue type + pusher, inserted ahead of the live-read helper
marker = "            // 0074: playback reads the ring out of live IOP RAM the way the SPU2 ADMA engine does."
if text.count(marker) != 1:
    raise SystemExit(f"ERROR: marker matched {text.count(marker)} times")
queue_src = """            // 0074: auto-DMA hands over one block per interrupt, so playback consumes armed blocks in order.
            // The wrap-ring model replayed the newest 2 KB every 10.7 ms (98% repeated output chunks).
            constexpr size_t kSpu2QueueBlocks = 64u;
            constexpr size_t kSpu2BlockCapacity = 2048u;

            struct Spu2Queue
            {
                static constexpr size_t kBlocks = kSpu2QueueBlocks;
                std::array<std::array<uint8_t, kSpu2BlockCapacity>, kSpu2QueueBlocks> blocks{};
                size_t blockBytes = 0u;
                size_t head = 0u; // index of the next block to play
                size_t count = 0u;
                size_t playOffset = 0u;
                uint8_t lastFrame[4] = {0u, 0u, 0u, 0u};
                uint64_t pushed = 0u;
                uint64_t played = 0u;
                uint64_t underruns = 0u;
                uint64_t dropped = 0u;
                uint64_t framesOut = 0u;
            };

            Spu2Queue &spu2Queue()
            {
                static Spu2Queue queue;
                return queue;
            }

            void spu2QueuePush(const std::vector<uint8_t> &ram, uint32_t address, uint32_t sizeBytes)
            {
                if (sizeBytes < 4u || sizeBytes > kSpu2BlockCapacity || address == 0u)
                    return;
                if (static_cast<uint64_t>(address) + sizeBytes > ram.size())
                    return;
                Spu2Queue &queue = spu2Queue();
                if (queue.blockBytes == 0u)
                    queue.blockBytes = sizeBytes;
                if (sizeBytes != queue.blockBytes)
                    return;
                if (queue.count == Spu2Queue::kBlocks)
                {
                    queue.head = (queue.head + 1u) % Spu2Queue::kBlocks;
                    --queue.count;
                    ++queue.dropped;
                }
                std::memcpy(queue.blocks[(queue.head + queue.count) % Spu2Queue::kBlocks].data(), ram.data() + address,
                            sizeBytes);
                ++queue.count;
                if (++queue.pushed % 2000u == 0u)
                    std::fprintf(stderr,
                                 "[spu2:queue] pushed=%llu played=%llu underruns=%llu dropped=%llu depth=%llu "
                                 "audioOut=%.1fs\\n",
                                 static_cast<unsigned long long>(queue.pushed),
                                 static_cast<unsigned long long>(queue.played),
                                 static_cast<unsigned long long>(queue.underruns),
                                 static_cast<unsigned long long>(queue.dropped),
                                 static_cast<unsigned long long>(queue.count),
                                 static_cast<double>(queue.framesOut) / 48'000.0);
            }

""" + marker
text = text.replace(marker, queue_src, 1)

# ---- 2. queue every armed block
anchor = """                                 static_cast<double>(ring.framesOut) / 48'000.0);
            }
"""
if text.count(anchor) != 1:
    raise SystemExit(f"ERROR: fresh-log anchor matched {text.count(anchor)} times")
text = text.replace(anchor, anchor + """
            // 0074: the armed block is the next piece of the stream; queue it for one-shot playback.
            spu2QueuePush(ram, address, sizeBytes);
""", 1)

# ---- 3. replace the wrap-ring body with queue playback
start, end = function_span(text, "size_t IopMemory::pullSpu2Pcm(")
new_pull = """    size_t IopMemory::pullSpu2Pcm(int16_t *destination, size_t frameCount)
    {
        Spu2Queue &queue = spu2Queue();
        constexpr size_t kFrameBytes = 4u; // 16-bit stereo
        const size_t blockBytes = queue.blockBytes ? queue.blockBytes : 1024u;

        if (!destination || frameCount == 0u)
            return 0u;

        auto *out = reinterpret_cast<uint8_t *>(destination);
        for (size_t produced = 0u; produced < frameCount; ++produced)
        {
            if (queue.count == 0u)
            {
                // Underrun: the driver has not armed the next block yet. Holding the last frame keeps the output
                // continuous instead of injecting clicks, and the counter reports how often this happens.
                std::memcpy(out + produced * kFrameBytes, queue.lastFrame, kFrameBytes);
                if (queue.playOffset == 0u)
                    ++queue.underruns;
                continue;
            }

            const uint8_t *block = queue.blocks[queue.head].data();
            std::memcpy(out + produced * kFrameBytes, block + queue.playOffset, kFrameBytes);
            std::memcpy(queue.lastFrame, block + queue.playOffset, kFrameBytes);
            queue.playOffset += kFrameBytes;
            if (queue.playOffset + kFrameBytes > blockBytes)
            {
                queue.playOffset = 0u;
                queue.head = (queue.head + 1u) % Spu2Queue::kBlocks;
                --queue.count;
                ++queue.played;
            }
        }

        queue.framesOut += frameCount;
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
        return frameCount;
    }

"""
text = text[:start] + new_pull + text[end:]
open(PATH, "w", encoding="utf-8", newline="\r\n").write(text)
print("queue playback installed")
