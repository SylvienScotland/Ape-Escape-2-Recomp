#!/usr/bin/env python3
"""0075: pump one video frame of SPU2 audio into the host device each rendered frame.

A video frame is 1/60 s, so 800 stereo frames cover it exactly (48000 / 60). The backend's ring absorbs the
mismatch between the emulated frame rate and the device's clock. Gated so it costs nothing when the SPU2 has not
armed a stream yet (e.g. before the first music track starts).
"""
import sys

RT = r"C:\dev\PS2Recomp\ps2xRuntime\src\lib\ps2_runtime.cpp"

text = open(RT, "r", encoding="utf-8", newline=None).read().replace("\r\n", "\n")

if "pullSpu2Pcm" in text:
    print("already patched")
    sys.exit(0)

anchor = "        UploadFrame(frameTex, this, presentWidth, presentHeight);"
n = text.count(anchor)
if n != 1:
    raise SystemExit(f"ERROR: anchor matched {n} times")

hook = """        // 0075: SPU2 streamed audio. The game's music arrives as PCM in IOP RAM and is armed onto SPU2 core1
        // auto-DMA; one video frame is exactly 800 stereo frames at 48 kHz, so pull that and hand it to the device.
        if (m_iopSubsystem && m_iopSubsystem->spu2StreamArmed())
        {
            int16_t spu2Pcm[800 * 2];
            const size_t spu2Frames = m_iopSubsystem->pullSpu2Pcm(spu2Pcm, 800u);
            if (spu2Frames != 0u)
                m_audioBackend.pushStreamPcm(spu2Pcm, spu2Frames);
        }
""" + anchor

text = text.replace(anchor, hook, 1)
open(RT, "w", encoding="utf-8", newline="\r\n").write(text)
print("runtime hook patched")
