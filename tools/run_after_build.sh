#!/usr/bin/env bash
# Wait for build80 to finish, then run the game for 60 s with the SPU2 tap so the audio path can be inspected.
set -u
cd /c/dev/Ape-Escape-2-Recomp || exit 1

for _ in $(seq 1 150); do
    if grep -qs "^Built:" build80.log; then break; fi
    if grep -qsE "error C[0-9]+|error MSB|LNK[0-9]+" build80.log; then echo "BUILD_FAILED"; exit 1; fi
    sleep 10
done
grep -qs "^Built:" build80.log || { echo "BUILD_TIMEOUT"; exit 1; }
echo "BUILD_OK"

for _ in 1 2 3; do
    PID=$(tasklist //FI "IMAGENAME eq ps2EntryRunner.exe" //FO CSV //NH 2>/dev/null | head -1 | cut -d, -f2 | tr -d '"')
    if [ -n "$PID" ]; then taskkill //F //PID "$PID" >/dev/null 2>&1; sleep 2; else break; fi
done

mkdir -p dumps/spu2d && rm -f dumps/spu2d/*.bin
(
    cd /c/dev/PS2Recomp/out/runner/ps2xRuntime/RelWithDebInfo || exit 1
    APE2_SPU2_DUMP="C:/dev/Ape-Escape-2-Recomp/dumps/spu2d" \
    APE2_ISO="C:\Users\truga\Downloads\Ape Escape 2 (USA)\Ape Escape 2 (USA).iso" \
    ./ps2EntryRunner.exe "C:\Users\truga\Downloads\Ape Escape 2 demounted\SLUS_206.85" \
        > /c/dev/Ape-Escape-2-Recomp/run_audio4.log 2>&1 &
)

sleep 60
PID=$(tasklist //FI "IMAGENAME eq ps2EntryRunner.exe" //FO CSV //NH 2>/dev/null | head -1 | cut -d, -f2 | tr -d '"')
if [ -n "$PID" ]; then taskkill //F //PID "$PID" >/dev/null 2>&1; fi
echo "AUTORUN_DONE"
