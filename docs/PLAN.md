# Ape Escape 2 Recomp: plan

## Milestones
0. Toolchain: PS2Recomp built (recomp, analyzer, runtime) on Linux + Windows
1. Analysis: ELF verified (hash in DISC.md), Ghidra function map exported, SDK libs identified
2. Codegen: generated C++ compiles and links against ps2xRuntime
3. First boot: reaches main() without unresolved-function aborts
4. IOP/CD: file reads off the disc image work (sceCd*, SIF RPC, IRX modules)
5. Graphics: GS output visible (first logo/frame), then menus
6. Input + audio: pad, SPU2/streamed audio
7. In-game: first level playable, compared against PCSX2
8. Polish: widescreen, high res, 60fps, mods

## Rules
- No game bytes, generated code, or decompiled game C in git.
- Per-build hacks live in overrides/ as PS2Recomp game overrides, keyed by ELF CRC.
- Every fix gets a note in docs/LOG.md.
