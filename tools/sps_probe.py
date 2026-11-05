#!/usr/bin/env python3
"""Locate the PCM payload inside an .SPS stage-music file and identify its format.

Header (little-endian, observed): "No28" tag, 0x01, a count, a byte size, then 0x0000bb80 = 48000 Hz, then padding.
The question this answers is where the audio actually starts and whether it is 16-bit stereo PCM.
"""
import sys
import numpy as np

path = sys.argv[1]
raw = np.fromfile(path, dtype=np.uint8)
print(f"{path}: {len(raw)} bytes")
head = raw[:64].tolist()
print("header:", " ".join(f"{b:02x}" for b in head))
print("u32 @0x10..0x1c:", [int(np.frombuffer(raw[o:o+4].tobytes(), dtype="<u4")[0]) for o in (0x10, 0x14, 0x18, 0x1c)])


def metrics(x):
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 8192 or np.std(x) < 1e-9:
        return None
    x = x - x.mean()
    lag1 = float(np.dot(x[:-1], x[1:]) / (np.dot(x, x) + 1e-9))
    zcr = float(np.mean(np.abs(np.diff(np.sign(x))) > 0))
    w = 2048
    flats = []
    for i in range(0, len(x) - w, w * 8):
        seg = x[i:i + w] * np.hanning(w)
        sp = np.abs(np.fft.rfft(seg)) + 1e-9
        flats.append(float(np.exp(np.mean(np.log(sp))) / np.mean(sp)))
    return zcr, lag1, float(np.median(flats))


print(f"{'offset':>8} {'mode':<6} {'zcr':>6} {'lag1':>7} {'flat':>7} {'corr':>6}")
for off in (0, 0x20, 0x800, 0x1000, 0x2000, 0x4000):
    chunk = raw[off: off + 48000 * 8]
    if len(chunk) < 16384:
        continue
    i16 = chunk[: (len(chunk) // 4) * 4].view("<i2").reshape(-1, 2).astype(np.float64)
    for mode, data in (("stereo", i16[:, 0]), ("mono", i16.reshape(-1))):
        m = metrics(data[:48000 * 4])
        if m:
            corr = float(np.corrcoef(i16[:, 0], i16[:, 1])[0, 1]) if mode == "stereo" else 0.0
            print(f"{off:>8} {mode:<6} {m[0]:>6.3f} {m[1]:>7.3f} {m[2]:>7.3f} {corr:>6.3f}")
