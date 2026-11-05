#!/usr/bin/env python3
"""Determine the layout of an .SPS stage-music file.

Established from the header: 0x800 bytes of header, then N = field@0x14 blocks of 2048 bytes each, sample rate
field@0x1C = 48000. This scores the plausible in-block layouts so the payload can be decoded correctly instead of
being played as raw interleaved stereo (which measures noise-like).
"""
import sys
import numpy as np

path = sys.argv[1]
raw = np.fromfile(path, dtype=np.uint8)
hdr = np.frombuffer(raw[0x10:0x20].tobytes(), dtype="<u4")
channels_or_version, block_count, payload_bytes, sample_rate = (int(v) for v in hdr)
print(f"header: ver/chan={channels_or_version} blocks={block_count} payload={payload_bytes} rate={sample_rate}")

payload = raw[0x800 : 0x800 + payload_bytes]
blocks = payload[: (len(payload) // 2048) * 2048].reshape(-1, 2048)
print(f"payload {len(payload)} bytes -> {len(blocks)} blocks of 2048")
take = blocks[:400]


def metrics(x, label):
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 8192 or np.std(x) < 1e-9:
        print(f"{label:<26} too short/flat")
        return
    x = x - x.mean()
    lag1 = float(np.dot(x[:-1], x[1:]) / (np.dot(x, x) + 1e-9))
    zcr = float(np.mean(np.abs(np.diff(np.sign(x))) > 0))
    w = 2048
    flats = []
    for i in range(0, len(x) - w, w * 8):
        seg = x[i : i + w] * np.hanning(w)
        sp = np.abs(np.fft.rfft(seg)) + 1e-9
        flats.append(float(np.exp(np.mean(np.log(sp))) / np.mean(sp)))
    print(f"{label:<26} zcr={zcr:5.3f} lag1={lag1:5.3f} flat={np.median(flats):5.3f} rms={np.sqrt(np.mean(x*x)):7.0f}")


# A: interleaved stereo, left channel across blocks
metrics(take.view("<i2")[::2].reshape(-1), "interleaved L")
# B: planar within block: first 1024 bytes L, second 1024 bytes R
metrics(take[:, :1024].copy().view("<i2").reshape(-1), "planar L (half block)")
lr = take[:, 1024:].copy().view("<i2").reshape(-1)
metrics(lr, "planar R (half block)")
# cross-correlate the two planes to see if they are a stereo pair
try:
    a = take[:, :1024].copy().view("<i2").reshape(-1).astype(np.float64)
    b = take[:, 1024:].copy().view("<i2").reshape(-1).astype(np.float64)
    n = min(len(a), len(b))
    print(f"planar L/R correlation: {np.corrcoef(a[:n], b[:n])[0,1]:.3f}")
except Exception as exc:
    print("planar corr failed", exc)
# C: whole payload as one int16 stream
metrics(payload[: 48000 * 4].view("<i2").reshape(-1), "whole payload mono")
# D: interleaved with a per-block 32-byte header skipped
stripped = np.concatenate([blk[32:] for blk in take])
metrics(stripped.view("<i2")[::2].reshape(-1), "interleaved, 32B hdr skip")

# Sony 4-bit ADPCM (16-byte frames) over the payload
COEFS = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]
def adpcm(block):
    out = np.zeros((len(block) // 16) * 28, dtype=np.float64)
    s1 = s2 = 0
    o = 0
    for b in range(len(block) // 16):
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

metrics(adpcm(payload[: 2048 * 60]), "adpcm 16B frames")
