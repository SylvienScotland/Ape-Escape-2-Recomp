#!/usr/bin/env python3
"""Check whether the captured stream is really Sony 4-bit ADPCM, not a degenerate decode.

A broken ADPCM decode can look "tonal" simply by producing a slow ramp, so this reports the things that separate a
real decode from an artefact: rail saturation, sample spread, spectral peak, and whether energy sits where music
lives (100-4000 Hz) instead of near DC.
"""
import sys
import numpy as np

COEFS = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]


def adpcm_decode(block):
    nblocks = len(block) // 16
    out = np.zeros(nblocks * 28, dtype=np.float64)
    s1 = s2 = 0
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
            sample = ((nib << 12) >> shift) + ((s1 * c1 + s2 * c2) >> 6)
            sample = max(-32768, min(32767, sample))
            out[o] = sample
            o += 1
            s2, s1 = s1, sample
    return out


def describe(label, x, rate=48000.0):
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 4096:
        print(f"{label}: too short")
        return
    rails = float(np.mean(np.abs(x) >= 32760))
    peak = float(np.max(np.abs(x)))
    spec = np.abs(np.fft.rfft(x[: 32768] * np.hanning(min(32768, len(x)))))
    freqs = np.fft.rfftfreq(min(32768, len(x)), 1.0 / rate)
    band = (freqs > 80) & (freqs < 6000)
    lowband = (freqs <= 80)
    energy_music = float(spec[band].sum() / (spec.sum() + 1e-9))
    energy_dc = float(spec[lowband].sum() / (spec.sum() + 1e-9))
    dominant = float(freqs[int(np.argmax(spec * band))]) if band.any() else 0.0
    print(f"{label}: n={len(x)} peak={peak:.0f} rails={rails*100:.2f}% "
          f"energy80-6k={energy_music*100:.1f}% energy<=80Hz={energy_dc*100:.1f}% dominant={dominant:.0f}Hz")


path = sys.argv[1] if len(sys.argv) > 1 else r"dumps\spu2e\out.raw"
raw = np.fromfile(path, dtype=np.uint8)
# skip leading silence in the tap so the analysis is not measuring zeros
nz = np.nonzero(raw)[0]
start = int(nz[0]) if len(nz) else 0
raw = raw[start : start + 1024 * 512]
start = int(np.nonzero(raw)[0][0]) if np.count_nonzero(raw) else 0
raw = raw[start:]
print(f"{path}: analysing {len(raw)} bytes from first non-zero")

describe("int16 L ", raw.view("<i2")[0::2])
describe("adpcm   ", adpcm_decode(raw[: 16 * 20000]))
