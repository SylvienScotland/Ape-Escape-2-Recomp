#!/usr/bin/env python3
"""Differential test of the recompiler's COP2 (VU0 macro mode) translations against a reference.

Like tools/mmi_check.py: one translated statement per distinct COP2 operation the game uses is taken
from generated/output and run next to the reference semantics of the PAL port (port/include/vu0.h and
the decode table of recomp/recomp.py, JackyPendrag0n/ae2-recomp, used with the author's permission) on
random register values. Compared: vf0-31, ACC, Q, I and vi0-15; MAC/status flags are reported apart.

    python tools/cop2_check.py <path to ae2-recomp clone> <out dir>
"""
import glob
import os
import re
import sys

pal_dir, out_dir = sys.argv[1], sys.argv[2]
vu0h = open(os.path.join(pal_dir, 'port', 'include', 'vu0.h')).read()
ps2h = open(os.path.join(pal_dir, 'port', 'include', 'ps2.h')).read()

# ---- PAL recomp.py COP2 decode (ported): instruction word -> reference C, or None when not compared
V_BC = {0: 'ADD', 4: 'SUB', 8: 'MADD', 12: 'MSUB', 16: 'MAX', 20: 'MINI', 24: 'MUL'}
V_FUNCT = {28: ('MUL', 'q'), 29: ('MAX', 'i'), 30: ('MUL', 'i'), 31: ('MINI', 'i'), 32: ('ADD', 'q'), 33: ('MADD', 'q'),
           34: ('ADD', 'i'), 35: ('MADD', 'i'), 36: ('SUB', 'q'), 37: ('MSUB', 'q'), 38: ('SUB', 'i'),
           39: ('MSUB', 'i'), 40: ('ADD', ''), 41: ('MADD', ''), 42: ('MUL', ''), 43: ('MAX', ''), 44: ('SUB', ''),
           45: ('MSUB', ''), 47: ('MINI', '')}
V_SPEC2_BC = {0: 'ADDA', 4: 'SUBA', 8: 'MADDA', 12: 'MSUBA', 24: 'MULA'}
V_SPEC2 = {28: ('MULA', 'q'), 30: ('MULA', 'i'), 32: ('ADDA', 'q'), 33: ('MADDA', 'q'), 34: ('ADDA', 'i'),
           35: ('MADDA', 'i'), 36: ('SUBA', 'q'), 37: ('MSUBA', 'q'), 38: ('SUBA', 'i'), 39: ('MSUBA', 'i'),
           40: ('ADDA', ''), 41: ('MADDA', ''), 42: ('MULA', ''), 44: ('SUBA', ''), 45: ('MSUBA', '')}


def cop2(w):
    rs = (w >> 21) & 31; rt = (w >> 16) & 31; rd = (w >> 11) & 31
    if rs == 1: return ('QMFC2', rt and 'std::memcpy(&c->r[%d], &c->vf[%d], 16);' % (rt, rd) or '')
    if rs == 5: return ('QMTC2', rd and 'std::memcpy(&c->vf[%d], &c->r[%d], 16);' % (rd, rt) or '')
    if not (rs & 16):
        return None
    dest = (w >> 21) & 15
    ft = (w >> 16) & 31; fs = (w >> 11) & 31; fd = (w >> 6) & 31
    fn = w & 63
    if fn < 60:
        if fn < 28:
            base = fn & ~3; bc = fn & 3
            if base in V_BC:
                return ('V%s%s' % (V_BC[base], 'xyzw'[bc]), 'V_%s(%d,%d,%d,VBC(%d,%d));' % (V_BC[base], dest, fd, fs, ft, bc))
            return None
        if fn in V_FUNCT:
            nm, kind = V_FUNCT[fn]
            if kind == 'q': return ('V%sq' % nm, 'V_%s(%d,%d,%d,VQ);' % (nm, dest, fd, fs))
            if kind == 'i': return ('V%si' % nm, 'V_%s(%d,%d,%d,VI_);' % (nm, dest, fd, fs))
            return ('V%s' % nm, 'V_%s(%d,%d,%d,VV(%d));' % (nm, dest, fd, fs, ft))
        if fn == 46: return ('VOPMSUB', 'V_OPMSUB(%d,%d,%d);' % (fd, fs, ft))
        it = ft & 15; is_ = fs & 15; id_ = fd & 15
        if fn == 48: return ('VIADD', 'VIW(%d, VIR(%d) + VIR(%d));' % (id_, is_, it))
        if fn == 49: return ('VISUB', 'VIW(%d, VIR(%d) - VIR(%d));' % (id_, is_, it))
        if fn == 50:
            im = fd if fd < 16 else fd - 32
            return ('VIADDI', 'VIW(%d, VIR(%d) + (%d));' % (it, is_, im))
        if fn == 52: return ('VIAND', 'VIW(%d, VIR(%d) & VIR(%d));' % (id_, is_, it))
        if fn == 53: return ('VIOR', 'VIW(%d, VIR(%d) | VIR(%d));' % (id_, is_, it))
        return None
    op2 = (w & 3) | ((w >> 4) & 0x7c)
    if op2 < 28:
        base = op2 & ~3; bc = op2 & 3
        if base in V_SPEC2_BC:
            return ('V%s%s' % (V_SPEC2_BC[base], 'xyzw'[bc]), 'V_%s(%d,0,%d,VBC(%d,%d));' % (V_SPEC2_BC[base], dest, fs, ft, bc))
        if 16 <= op2 < 20: return ('VITOF%d' % [0, 4, 12, 15][op2 - 16], 'V_ITOF(%d,%d,%d,%d);' % (dest, ft, fs, [0, 4, 12, 15][op2 - 16]))
        if 20 <= op2 < 24: return ('VFTOI%d' % [0, 4, 12, 15][op2 - 20], 'V_FTOI(%d,%d,%d,%d);' % (dest, ft, fs, [0, 4, 12, 15][op2 - 20]))
        return None
    if op2 in V_SPEC2:
        nm, kind = V_SPEC2[op2]
        if kind == 'q': return ('V%sq' % nm, 'V_%s(%d,0,%d,VQ);' % (nm, dest, fs))
        if kind == 'i': return ('V%si' % nm, 'V_%s(%d,0,%d,VI_);' % (nm, dest, fs))
        return ('V%s' % nm, 'V_%s(%d,0,%d,VV(%d));' % (nm, dest, fs, ft))
    fsf = (w >> 21) & 3; ftf = (w >> 23) & 3
    if op2 == 29: return ('VABS', 'V_ABS(%d,%d,%d);' % (dest, ft, fs))
    if op2 == 31: return ('VCLIP', 'V_CLIP(%d,%d);' % (fs, ft))
    if op2 == 46: return ('VOPMULA', 'V_OPMULA(%d,%d);' % (fs, ft))
    if op2 == 48: return ('VMOVE', 'V_MOVE(%d,%d,%d);' % (dest, ft, fs))
    if op2 == 49: return ('VMR32', 'V_MR32(%d,%d,%d);' % (dest, ft, fs))
    if op2 == 56: return ('VDIV', 'V_DIV(%d,%d,%d,%d);' % (fs, fsf, ft, ftf))
    if op2 == 57: return ('VSQRT', 'V_SQRT(%d,%d);' % (ft, ftf))
    if op2 == 58: return ('VRSQRT', 'V_RSQRT(%d,%d,%d,%d);' % (fs, fsf, ft, ftf))
    if op2 == 60: return ('VMTIR', 'VIW(%d, c->vf[%d].uw[%d] & 0xffff);' % (ft & 15, fs, fsf))
    if op2 == 61: return ('VMFIR', 'V_MFIR(%d,%d,%d);' % (dest, ft, fs & 15))
    if op2 == 64: return ('VRNEXT', 'V_RNEXT(%d,%d);' % (dest, ft))
    if op2 == 65: return ('VRGET', 'V_RGET(%d,%d);' % (dest, ft))
    if op2 == 66: return ('VRINIT', 'V_RINIT(%d,%d);' % (fs, fsf))
    if op2 == 67: return ('VRXOR', 'V_RXOR(%d,%d);' % (fs, fsf))
    return None


comment = re.compile(r'^    // 0x([0-9a-f]+): 0x([0-9a-f]+)\s+(\S+)')
samples = {}
for path in sorted(glob.glob('generated/output/*.cpp')):
    lines = open(path, errors='ignore').read().splitlines()
    for i, line in enumerate(lines):
        m = comment.match(line)
        if not m:
            continue
        raw = int(m.group(2), 16)
        if raw >> 26 != 0x12:
            continue
        dec = cop2(raw)
        if not dec or not dec[1]:
            continue
        key = dec[0] + '.' + str((raw >> 21) & 15)   # operation + dest mask
        if key in samples:
            continue
        body = []
        for line2 in lines[i + 1:]:
            if line2.startswith('    // 0x') or line2.startswith('label_') or line2.startswith('}'):
                break
            if re.match(r'^    ctx->pc = 0x[0-9a-fA-F]+u;$', line2):
                if body:
                    break
                continue
            body.append(line2)
        if body:
            samples[key] = (raw, '\n'.join(body), dec[1])

helpers = ps2h[ps2h.index('/* ---------- FPU'):ps2h.index('#define FCOND')]
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, 'cop2_check.cpp'), 'w') as f:
    f.write('// generated by tools/cop2_check.py\n#include "ps2_runtime.h"\n#include "ps2_runtime_macros.h"\n#include <cstdio>\n#include <random>\n\n')
    f.write('namespace pal {\n#define __attribute__(x)\n#define unlikely(x) (x)\n#define likely(x) (x)\n')
    f.write('typedef union { uint64_t ud[2]; int64_t sd[2]; uint32_t uw[4]; int32_t sw[4]; uint16_t uh[8]; int16_t sh[8];'
            ' uint8_t ub[16]; int8_t sb[16]; float f[4]; } r128;\n')
    f.write('struct Ctx { r128 r[32]; r128 hi, lo; uint64_t sa; float facc; uint32_t fcr31; r128 vf[32]; uint32_t vi[32]; r128 vacc; float vq; uint32_t vr; };\n')
    f.write(helpers)
    f.write(vu0h.replace('#pragma once', '').replace('extern uint8_t g_vu0mem[4096];', 'static uint8_t g_vu0mem[4096];'))
    f.write('\n#undef __attribute__\n}\n\n')
    f.write('static void toPal(const R5900Context *ctx, pal::Ctx *c) {\n'
            '    std::memset(c, 0, sizeof(*c));\n'
            '    for (int i = 0; i < 32; ++i) { std::memcpy(&c->r[i], &ctx->r[i], 16); std::memcpy(&c->vf[i], &ctx->vu0_vf[i], 16); }\n'
            '    for (int i = 0; i < 16; ++i) c->vi[i] = ctx->vi[i];\n'
            '    c->vi[16] = ctx->vu0_status; c->vi[17] = ctx->vu0_mac_flags; c->vi[18] = ctx->vu0_clip_flags;\n'
            '    std::memcpy(&c->vi[21], &ctx->vu0_i, 4);\n'
            '    std::memcpy(&c->vacc, &ctx->vu0_acc, 16); c->vq = ctx->vu0_q;\n'
            '    std::memcpy(&c->vr, &ctx->vu0_r, 4); c->vr &= 0x7fffffu;\n}\n\n')
    f.write('static float rf(std::mt19937_64 &rng) {\n'
            '    const uint64_t r = rng(); if ((r & 15) == 0) return 0.0f;\n'
            '    const float m = 1.0f + (float)((r >> 8) & 0xffffff) / 16777216.0f; const int e = (int)((r >> 32) % 24) - 12;\n'
            '    return ((r >> 4) & 1 ? -1.0f : 1.0f) * std::ldexp(m, e);\n}\n\n')
    f.write('int main() {\n    std::mt19937_64 rng(1234);\n    int failures = 0, flagFailures = 0;\n')
    f.write('    alignas(16) static R5900Context ctxStore; R5900Context *ctx = &ctxStore; uint8_t *rdram = nullptr; PS2Runtime *runtime = nullptr;\n'
            '    (void)rdram; (void)runtime;\n')
    for key, (raw, body, ref) in sorted(samples.items()):
        f.write('    {\n        int bad = 0, badFlags = 0; char why[256] = "";\n')
        f.write('        for (int iter = 0; iter < 3000 && !bad; ++iter) {\n')
        f.write('            std::memset(ctx, 0, sizeof(*ctx));\n')
        f.write('            for (int i = 0; i < 32; ++i) { float v[4] = {rf(rng), rf(rng), rf(rng), rf(rng)}; if (i == 0) { v[0] = v[1] = v[2] = 0.0f; v[3] = 1.0f; }'
                ' ctx->vu0_vf[i] = _mm_loadu_ps(v); ctx->r[i] = i ? _mm_set_epi64x((long long)rng(), (long long)rng()) : _mm_setzero_si128(); }\n')
        f.write('            for (int i = 1; i < 16; ++i) ctx->vi[i] = (uint16_t)rng();\n')
        f.write('            { float a[4] = {rf(rng), rf(rng), rf(rng), rf(rng)}; ctx->vu0_acc = _mm_loadu_ps(a); } ctx->vu0_q = rf(rng); ctx->vu0_i = rf(rng);'
                ' ctx->vu0_r = _mm_castsi128_ps(_mm_set1_epi32((int)(0x3F800000u | ((uint32_t)rng() & 0x7FFFFFu))));\n')
        f.write('            pal::Ctx refStore; pal::Ctx *c = &refStore; toPal(ctx, c);\n')
        f.write('            ' + body.replace('\n', '\n            ') + '\n')
        f.write('            { using namespace pal; ' + ref + ' }\n')
        f.write('            pal::Ctx got; toPal(ctx, &got);\n')
        f.write('            for (int r = 0; r < 32 && !bad; ++r) if (std::memcmp(&got.vf[r], &c->vf[r], 16)) { bad = 1; std::snprintf(why, sizeof why, "vf%d got %g %g %g %g ref %g %g %g %g", r,'
                ' got.vf[r].f[0], got.vf[r].f[1], got.vf[r].f[2], got.vf[r].f[3], c->vf[r].f[0], c->vf[r].f[1], c->vf[r].f[2], c->vf[r].f[3]); }\n')
        f.write('            if (!bad && std::memcmp(&got.vacc, &c->vacc, 16)) { bad = 1; std::snprintf(why, sizeof why, "ACC got %g %g %g %g ref %g %g %g %g",'
                ' got.vacc.f[0], got.vacc.f[1], got.vacc.f[2], got.vacc.f[3], c->vacc.f[0], c->vacc.f[1], c->vacc.f[2], c->vacc.f[3]); }\n')
        f.write('            if (!bad && std::memcmp(&got.vq, &c->vq, 4)) { bad = 1; std::snprintf(why, sizeof why, "Q got %g ref %g", got.vq, c->vq); }\n')
        f.write('            for (int r = 1; r < 16 && !bad; ++r) if ((got.vi[r] & 0xffff) != (c->vi[r] & 0xffff)) { bad = 1; std::snprintf(why, sizeof why, "vi%d got %x ref %x", r, got.vi[r], c->vi[r]); }\n')
        f.write('            for (int r = 0; r < 32 && !bad; ++r) if (std::memcmp(&got.r[r], &c->r[r], 16)) { bad = 1; std::snprintf(why, sizeof why, "r%d differs", r); }\n')
        f.write('            if (!bad && got.vr != c->vr) { bad = 1; std::snprintf(why, sizeof why, "R got %x ref %x", got.vr, c->vr); }\n')
        f.write('            if (!bad && (got.vi[17] & 0xffff) != (c->vi[17] & 0xffff)) badFlags = 1;\n')
        f.write('        }\n')
        f.write('        if (bad) { ++failures; std::printf("MISMATCH %-12s %08x  %%s\\n", why); }\n' % (key, raw))
        f.write('        else if (badFlags) { ++flagFailures; std::printf("flags    %-12s %08x  MAC flags differ\\n"); }\n' % (key, raw))
        f.write('        else std::printf("ok       %s\\n");\n    }\n' % key)
    f.write('    std::printf("%%d of %d COP2 operations differ in results, %%d more only in MAC flags\\n", failures, flagFailures);\n    return failures;\n}\n' % len(samples))
print('%d COP2 operation/dest combinations sampled' % len(samples))
