#!/usr/bin/env python3
"""0072b: decide from the waveform, not from listening, whether the captured SPU2 stream is music.

If the stream is 48 kHz 16-bit stereo music, then inside a block:
  - consecutive samples are strongly correlated (lag-1 autocorrelation well above 0.9 at low/mid frequencies),
  - the mean absolute step is small compared to the peak,
  - the spectrum is harmonic, not flat.
Noise (or non-PCM data interpreted as PCM) shows the opposite on all three. Block joins are measured against
within-block steps so a genuine discontinuity is distinguishable from naturally noisy content.
"""
import struct
import statistics
import math

TAP = "dumps/spu2e/spu2_core1.bin"

raw = open(TAP, "rb").read()
blocks = [raw[i:i + 1024] for i in range(0, len(raw) - 1023, 1024)]
print("blocks:", len(blocks))

frames_all = [struct.unpack("<512h", bl) for bl in blocks]
peaks = [max(abs(x) for x in fr) for fr in frames_all]
loud = sorted(range(len(blocks)), key=lambda i: -peaks[i])[:30]
print("top peaks:", peaks[loud[0]], peaks[loud[len(loud) // 2]], peaks[loud[-1]])

# ---- within-block statistics on loud blocks
def stats(fr):
    steps = [abs(fr[i] - fr[i - 1]) for i in range(1, len(fr))]
    mean_step = statistics.fmean(steps)
    peak = max(abs(x) for x in fr)
    var = statistics.pvariance(fr)
    lag1 = 0.0
    if var > 0:
        mean = statistics.fmean(fr)
        lag1 = sum((fr[i] - mean) * (fr[i - 1] - mean) for i in range(1, len(fr))) / ((len(fr) - 1) * var)
    zc = sum(1 for i in range(1, len(fr)) if (fr[i - 1] < 0) != (fr[i] < 0)) / len(fr)
    return mean_step, peak, lag1, zc, math.sqrt(var)

rows = [stats(frames_all[i]) for i in loud[:10]]
print("\nloud blocks: mean_step peak lag1 zcr rms")
for i, r in zip(loud[:10], rows):
    print("  blk %5d  step %6.1f  peak %6d  lag1 %+.3f  zcr %.3f  rms %6.1f" % (i, r[0], r[1], r[2], r[3], r[4]))

# ---- joins between consecutive loud blocks
join_steps = []
within_steps = []
for i in loud[:20]:
    if i + 1 >= len(frames_all):
        continue
    a, b = frames_all[i], frames_all[i + 1]
    join_steps.append(abs(b[0] - a[-1]))
    within_steps.append(statistics.fmean(abs(a[k] - a[k - 1]) for k in range(1, len(a))))
print("\njoins: mean |step| at join %.1f  vs within-block %.1f" %
      (statistics.fmean(join_steps), statistics.fmean(within_steps)))

# ---- spectral flatness of the loudest block (pure python DFT on 256 points)
fr = frames_all[loud[0]][:256]
mean = statistics.fmean(fr)
x = [v - mean for v in fr]
mag2 = []
N = len(x)
for k in range(1, N // 2):
    re = sum(x[n] * math.cos(-2 * math.pi * k * n / N) for n in range(N))
    im = sum(x[n] * math.sin(-2 * math.pi * k * n / N) for n in range(N))
    mag2.append(re * re + im * im)
mag2 = [m + 1e-9 for m in mag2]
geo = math.exp(sum(math.log(m) for m in mag2) / len(mag2))
ari = sum(mag2) / len(mag2)
print("spectral flatness of loudest block: %.4f (1.0 = white noise, <0.2 = tonal)" % (geo / ari))

# ---- is the same block repeating at a fixed period (stutter)?
hits = 0
for i in range(0, min(4000, len(blocks) - 2)):
    if blocks[i] == blocks[i + 2]:
        hits += 1
print("block[i] == block[i+2] for %d of first 4000 (ping-pong test)" % hits)

# ---- does the data look like 4-bit ADPCM rather than PCM?
nib = [0] * 16
for bl in blocks[loud[0]:loud[0] + 4]:
    for byte in bl:
        nib[byte & 0xF] += 1
        nib[(byte >> 4) & 0xF] += 1
print("nibble histogram (even = PCM, peaked = ADPCM):", nib)
