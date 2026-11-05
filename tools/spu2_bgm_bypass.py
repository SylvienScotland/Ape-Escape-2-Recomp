#!/usr/bin/env python3
"""0087: env-gated BGM bypass.

APE2_BGM_SPS=<file.SPS> plays a stage-music file directly, instead of depending on the SPU2 voice engine. The payload
is mono 16-bit little-endian at 48 kHz starting at 0x800 (established by measurement: acf lag-1 dominates lag-2, so it
is one sample chain; 99% of energy sits below 11.8 kHz, so the 48 kHz header field is the real rate). Each mono sample
is duplicated to both channels and pushed at 800 frames per video frame, matching the existing audio path.

Default behaviour is unchanged; this is a listening aid for the port, not a fix for the voice engine.
"""
import sys

PATH = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\ps2_runtime.cpp"
text = open(PATH, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

if "APE2_BGM_SPS" in text:
    print("already patched")
    sys.exit(0)

anchor = """        if (m_iopSubsystem && m_iopSubsystem->spu2StreamArmed())
        {
            int16_t spu2Pcm[800 * 2];
            const size_t spu2Frames = m_iopSubsystem->pullSpu2Pcm(spu2Pcm, 800u);
            if (spu2Frames != 0u)
                m_audioBackend.pushStreamPcm(spu2Pcm, spu2Frames);
        }
"""
n = text.count(anchor)
if n != 1:
    print(f"FAIL: audio pull anchor matched {n} times")
    sys.exit(1)

replacement = """        // 0087: BGM bypass - APE2_BGM_SPS=<file.SPS> plays a stage-music file straight to the device, for
        // listening tests while the SPU2 voice engine is not implemented. Payload is mono 16-bit at 48 kHz from
        // offset 0x800; each sample is duplicated to both channels, 800 frames per video frame.
        if (const char *bgmPath = std::getenv("APE2_BGM_SPS"))
        {
            static std::FILE *bgmFile = nullptr;
            static bool bgmOpened = false;
            if (!bgmOpened)
            {
                bgmOpened = true;
                bgmFile = std::fopen(bgmPath, "rb");
                if (bgmFile != nullptr)
                    std::fseek(bgmFile, 0x800, SEEK_SET);
                else
                    std::fprintf(stderr, "[bgm] cannot open %s\\n", bgmPath);
            }
            if (bgmFile != nullptr)
            {
                int16_t mono[800];
                size_t got = std::fread(mono, sizeof(int16_t), 800u, bgmFile);
                if (got < 800u)
                {
                    std::fseek(bgmFile, 0x800, SEEK_SET); // loop the track
                    got += std::fread(mono + got, sizeof(int16_t), 800u - got, bgmFile);
                }
                int16_t stereo[800 * 2];
                for (size_t i = 0u; i < 800u; ++i)
                {
                    const int16_t sample = i < got ? mono[i] : 0;
                    stereo[i * 2u] = sample;
                    stereo[i * 2u + 1u] = sample;
                }
                m_audioBackend.pushStreamPcm(stereo, 800u);
            }
        }
        else if (m_iopSubsystem && m_iopSubsystem->spu2StreamArmed())
        {
            int16_t spu2Pcm[800 * 2];
            const size_t spu2Frames = m_iopSubsystem->pullSpu2Pcm(spu2Pcm, 800u);
            if (spu2Frames != 0u)
                m_audioBackend.pushStreamPcm(spu2Pcm, spu2Frames);
        }
"""
open(PATH, "w", encoding="utf-8", newline="\r\n").write(text.replace(anchor, replacement, 1))
print("BGM bypass installed")
