#!/usr/bin/env python3
"""What encoding is the captured stream actually in?

The user reports "chiptune noise, no tempo". The emitted PCM measures like noise (flatness 0.62, zcr 0.22) while the
arm-time blocks measured tonal (flatness 0.05, lag-1 0.85-0.98). If the bytes are compressed or byte-shifted, playing
them as raw 16-bit stereo sounds exactly like that. This scores several interpretations of the same bytes:

  int16    - current interpretation (16-bit little-endian stereo)
  swap16   - byte-swapped 16-bit
  int8     - signed 8-bit samples
  uint8    - unsigned 8-bit samples
  adpcm    - Sony/PSX 16-byte block 4-bit ADPCM (28 samples per block, SPU2 voice data)

Metrics: zero-crossing rate (tonal music ~0.05-0.15, noise ~0.4-0.5), lag-1 autocorrelation (music high), spectral
flatness (1.0 = white noise).
"""
import sys
import numpy as np

path = sys.argv[1] if len(sys.argv) > 1 else r"dumps\spu2e\out.raw"
raw = np.fromfile(path, dtype=np.uint8)
if len(raw) < 8192:
    sys.exit("file too short")
raw = raw[: min(len(raw), 48000 * 4 * 2 * 2)]
print(f"{path}: {len(raw)} bytes")

COEFS = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]


def adpcm_decode(block):
    """Sony 4-bit ADPCM: 1 predictor/shift byte, 1 flag byte, 14 nibble bytes -> 28 samples per 16-byte block."""
    nblocks = len(block) // 16
    out = np.zeros(nblocks * 28, dtype=np.float64)
    s1 = 0
    s2 = 0
    o = 0
    for b in range(nblocks):
        head = block[b * 16 : b * 16 + 16]
        header = int(head[0])
        shift = header & 0x0F
        c1, c2 = COEFS[min(header >> 4, 4)]
        for i in range(28):
            byte = int(head[2 + (i >> 1)])
            nib = (byte >> 4) if (i & 1) == 0 else (byte & 0x0F)
            if nib > 7:
                nib -= 16
            sample = (nib << 12) >> shift
            sample += (s1 * c1 + s2 * c2) >> 6
            sample = max(-32768, min(32767, sample))
            out[o] = sample
            o += 1
            s2 = s1
            s1 = sample
    return out


def metrics(x):
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 4096 or np.std(x) < 1e-9:
        return None
    x = x - x.mean()
    lag1 = float(np.dot(x[:-1], x[1:]) / (np.dot(x, x) + 1e-9))
    zcr = float(np.mean(np.abs(np.diff(np.sign(x))) > 0))
    w = 2048
    flats = []
    for i in range(0, len(x) - w, w * 4):
        seg = x[i : i + w] * np.hanning(w)
        sp = np.abs(np.fft.rfft(seg)) + 1e-9
        flats.append(float(np.exp(np.mean(np.log(sp))) / np.mean(sp)))
    return zcr, lag1, float(np.median(flats)), float(np.sqrt(np.mean(x * x)))


rows = [
    ("int16 L", raw.view("<i2")[0::2]),
    ("swap16 L", raw[1:-1].view(">i2")[0::2]),
    ("int8", raw.view(np.int8)),
    ("uint8-128", raw.astype(np.float64) - 128.0),
]

print(f"{'interpretation':<12} {'zcr':>6} {'lag1':>7} {'flat':>7} {'rms':>8}")
for label, data in rows:
    m = metrics(data)
    if m:
        print(f"{label:<12} {m[0]:>6.3f} {m[1]:>7.3f} {m[2]:>7.3f} {m[3]:>8.0f}")

m = metrics(adpcm_decode(raw[: 16 * 30000])[: 48000 * 2])
if m:
    print(f"{'adpcm':<12} {m[0]:>6.3f} {m[1]:>7.3f} {m[2]:>7.3f} {m[3]:>8.0f}")
