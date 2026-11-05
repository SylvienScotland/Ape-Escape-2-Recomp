#!/usr/bin/env python3
"""Decode the first seconds of an .SPS into two candidate WAVs so the encoding can be settled by ear.

Layout is proven from the header: 0x800 bytes of header, then N blocks of 2048 bytes at 48 kHz. What is not proven is
the in-block encoding; metrics favour Sony 4-bit ADPCM (zcr 0.067, lag-1 0.919) but the decode saturates ~5.8% at the
rails, so it may not be exactly right. Rather than guess, this writes both readings for a listening test.
"""
import sys
import wave
import numpy as np

src = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\truga\Downloads\Ape Escape 2 demounted\APE2_USA\PCM\BGM\NO28.SPS"
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
outdir = sys.argv[3] if len(sys.argv) > 3 else r"dumps\bgm"

raw = np.fromfile(src, dtype=np.uint8)
hdr = np.frombuffer(raw[0x10:0x20].tobytes(), dtype="<u4")
block_count, payload_bytes, rate = int(hdr[1]), int(hdr[2]), int(hdr[3])
payload = raw[0x800 : 0x800 + min(payload_bytes, len(raw) - 0x800)]
print(f"blocks={block_count} payload={len(payload)} rate={rate}")

COEFS = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]


def adpcm_decode(block, limit_samples):
    out = np.zeros(max(limit_samples, 28), dtype=np.int16)
    s1 = s2 = 0
    o = 0
    nblocks = len(block) // 16
    for b in range(nblocks):
        if o >= limit_samples:
            break
        head = block[b * 16 : b * 16 + 16]
        header = int(head[0])
        shift = header & 0x0F
        c1, c2 = COEFS[min(header >> 4, 4)]
        for i in range(28):
            if o >= limit_samples:
                break
            byte = int(head[2 + (i >> 1)])
            nib = (byte >> 4) if (i & 1) == 0 else (byte & 0x0F)
            if nib > 7:
                nib -= 16
            sample = ((nib << 12) >> shift) + ((s1 * c1 + s2 * c2) >> 6)
            sample = max(-32768, min(32767, sample))
            out[o] = sample
            o += 1
            s2, s1 = s1, sample
    return out[:o]


def write_wav(path, samples, channels, rate):
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.asarray(samples, dtype="<i2").tobytes())
    print(f"wrote {path}: {len(samples)} samples, {channels} ch, {rate} Hz")


n = int(rate * seconds)
adpcm = adpcm_decode(payload, n)
write_wav(f"{outdir}/sps_adpcm.wav", adpcm, 1, rate)

pcm = payload[: n * 4].view("<i2").reshape(-1, 2)
write_wav(f"{outdir}/sps_pcm_stereo.wav", pcm, 2, rate)

mono = payload[: n * 2].view("<i2")
write_wav(f"{outdir}/sps_pcm_mono.wav", mono, 1, rate)
