#!/usr/bin/env python3
"""Measure the PCM actually emitted to the audio device (APE2_SPU2_PCM tap).

The question this answers is narrow: is the output advancing through new music, or replaying a short chunk?
A healthy stream has almost no equal neighbouring 512-frame chunks. A buzz-loop shows up immediately as a high
repeat count, plus a peak in the chunk-lag spectrum at the loop period.
"""
import sys
import numpy as np

path = sys.argv[1] if len(sys.argv) > 1 else r"dumps\spu2e\out.raw"
data = np.fromfile(path, dtype="<i2")
frames = data[: (len(data) // 2) * 2].reshape(-1, 2)
print(f"frames={len(frames)} seconds={len(frames)/48000.0:.2f}")

if len(frames) < 4096:
    sys.exit("too short")

# chunk comparisons: 512 frames = 10.67 ms, exactly one 1 KB ring block
chunk = 512
n = len(frames) // chunk
blocks = frames[: n * chunk].reshape(n, chunk, 2)
def eq(a, b):
    return float(np.mean(np.all(blocks[a:n - b] == blocks[b:n], axis=(1, 2)))) if n > b + 8 else 0.0

print(f"blocks={n}")
for lag in (1, 2, 3, 4):
    print(f"  block[i]==block[i+{lag}]: {eq(0, lag)*100:.1f}%")

# where does it grow? compare first and last third
third = n // 3
if third > 4:
    print(f"  repeat rate first third: {float(np.mean(np.all(blocks[0:third-2]==blocks[2:third],axis=(1,2))))*100:.1f}%")
    print(f"  repeat rate last third:  {float(np.mean(np.all(blocks[-third:-2]==blocks[-third+2:],axis=(1,2))))*100:.1f}%")

# loudness over time: is it one level (stuck) or varying (music)?
step = max(1, len(frames) // 20)
levels = [float(np.sqrt(np.mean(frames[i:i+step].astype(np.float64)**2))) for i in range(0, len(frames)-step, step)]
print("rms over time:", " ".join(f"{v:.0f}" for v in levels))

# spectrum of the loudest 2048-frame window
speech = frames
win = 2048
best, besti = -1.0, 0
for i in range(0, len(speech) - win, win):
    r = float(np.sqrt(np.mean(speech[i:i+win].astype(np.float64)**2)))
    if r > best:
        best, besti = r, i
seg = speech[besti:besti+win, 0].astype(np.float64) * np.hanning(win)
spec = np.abs(np.fft.rfft(seg)) + 1e-9
flat = float(np.exp(np.mean(np.log(spec))) / np.mean(spec))
print(f"loudest window rms={best:.0f} spectral flatness={flat:.4f} (1.0 = noise)")

# dominant periodicity of the whole signal, in frames
mono = frames[:, 0].astype(np.float64)
mono -= mono.mean()
ac = np.correlate(mono[: 48000 * 2], mono[: 48000 * 2], mode="full")[48000 * 2 - 1:]
ac /= ac[0] + 1e-9
peaks = [(lag, float(ac[lag])) for lag in range(64, 4096) if ac[lag] > 0.5]
if peaks:
    top = sorted(peaks, key=lambda t: -t[1])[:5]
    print("strong periodicities (frames, corr):", ", ".join(f"{l}@{c:.2f}" for l, c in top))
else:
    print("no periodicity above 0.5 in 64..4096 frames")
