#!/usr/bin/env python3
"""Generate layout/rate variants of the SPS payload, because raw PCM sounded "like music but distorted and slowed".

That report means the payload really is PCM (not ADPCM), and the wrong part is how frames are addressed: either the
channel layout inside each 2048-byte block, or the rate we declare (slowed = we are consuming samples too slowly), or
byte order (distortion). Each variant is the same 20 seconds of source, so they can be compared directly.
"""
import sys
import wave
import numpy as np

src = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\truga\Downloads\Ape Escape 2 demounted\APE2_USA\PCM\BGM\NO28.SPS"
outdir = sys.argv[2] if len(sys.argv) > 2 else r"dumps\bgm\variants"
import os
os.makedirs(outdir, exist_ok=True)

raw = np.fromfile(src, dtype=np.uint8)
hdr = np.frombuffer(raw[0x10:0x20].tobytes(), dtype="<u4")
block_count, payload_bytes, rate = int(hdr[1]), int(hdr[2]), int(hdr[3])
payload = raw[0x800 : 0x800 + min(payload_bytes, len(raw) - 0x800)]
blocks = payload.reshape(-1, 2048)


def write(name, samples, channels, rate_hz, seconds=20.0):
    samples = np.asarray(samples, dtype="<i2")
    limit = int(rate_hz * seconds) * channels
    samples = samples[:limit]
    path = os.path.join(outdir, name)
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate_hz)
        w.writeframes(samples.tobytes())
    print(f"{name:<34} {channels}ch {rate_hz}Hz  {len(samples)//channels} frames")


n_blocks = 400
b = blocks[:n_blocks]

# A. interleaved stereo at several declared rates
inter = b.reshape(-1).view("<i2")
write("a_interleaved_stereo_48k.wav", inter, 2, 48000)
write("b_interleaved_stereo_24k.wav", inter, 2, 24000)
write("c_interleaved_stereo_32k.wav", inter, 2, 32000)
write("d_interleaved_stereo_96k.wav", inter, 2, 96000)

# B. planar: first half of each block = left, second half = right
planar = np.concatenate([np.stack([blk[:1024].view("<i2"), blk[1024:].view("<i2")], axis=1) for blk in b])
write("e_planar_stereo_48k.wav", planar.reshape(-1), 2, 48000)
write("f_planar_stereo_24k.wav", planar.reshape(-1), 2, 24000)

# C. mono readings
write("g_mono_48k.wav", b.reshape(-1).view("<i2"), 1, 48000)
write("h_mono_24k.wav", b.reshape(-1).view("<i2"), 1, 24000)

# D. byte-swapped stereo (distortion test, pitch unchanged)
write("i_swap16_stereo_48k.wav", b.reshape(-1)[1:-1].view(">i2"), 2, 48000)
