#!/usr/bin/env python3
"""Mono sample-rate sweep for the SPS payload.

Evidence that the payload is mono 16-bit: acf lag-1 (0.882) dominates lag-2 (0.645), and the median adjacent-sample
difference (1966) is smaller than at distance two (3443) - i.e. consecutive samples belong to the same audio channel.
The earlier stereo readings were therefore wrong. What remains is the declared rate: the user heard the 48 kHz mono
version as "slowed", so the real rate is probably higher. This writes the same audio at several rates so the correct
one can be picked by ear (pitch and tempo change together, so it is unambiguous).
"""
import os
import wave
import numpy as np

src = r"C:\Users\truga\Downloads\Ape Escape 2 demounted\APE2_USA\PCM\BGM\NO28.SPS"
outdir = r"dumps\bgm\mono_rates"
os.makedirs(outdir, exist_ok=True)

raw = np.fromfile(src, dtype=np.uint8)
hdr = np.frombuffer(raw[0x10:0x20].tobytes(), dtype="<u4")
payload_bytes = int(hdr[2])
payload = raw[0x800 : 0x800 + payload_bytes]
samples = payload[: len(payload) // 2 * 2].view("<i2")
print(f"payload {len(payload)} bytes -> {len(samples)} mono samples ({len(samples)/48000:.1f}s at 48k)")

seconds = 25.0
for rate in (24000, 32000, 44100, 48000, 64000, 96000):
    n = int(rate * seconds)
    path = os.path.join(outdir, f"mono_{rate//1000}k.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples[:n].tobytes())
    print(f"wrote {path}  ({n} samples, {seconds:.0f}s at {rate} Hz)")
