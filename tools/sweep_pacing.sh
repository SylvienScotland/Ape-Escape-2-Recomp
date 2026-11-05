#!/usr/bin/env bash
# 0071: sweep ADMA pacing values against the [spu2:lap] ring-health metric.
# Target: armsPerLap >= 2 (every block refreshed at least once per lap) and stable, not drifting upward.
set -u
cd /c/dev/Ape-Escape-2-Recomp || exit 1
RUNNER=/c/dev/PS2Recomp/out/runner/ps2xRuntime/RelWithDebInfo
ROM="C:\Users\truga\Downloads\Ape Escape 2 demounted\SLUS_206.85"
ISO="C:\Users\truga\Downloads\Ape Escape 2 (USA)\Ape Escape 2 (USA).iso"

for v in 384 768 934; do
  PID=$(tasklist //FI "IMAGENAME eq ps2EntryRunner.exe" //FO CSV //NH 2>/dev/null | head -1 | cut -d, -f2 | tr -d '"')
  [ -n "$PID" ] && { taskkill //F //PID "$PID" >/dev/null 2>&1; sleep 2; }
  rm -f "run_sweep_$v.log"
  ( cd "$RUNNER" && APE2_SPU2_ADMA_CYCLES="$v" APE2_ISO="$ISO" \
      ./ps2EntryRunner.exe "$ROM" > "/c/dev/Ape-Escape-2-Recomp/run_sweep_$v.log" 2>&1 & )
  sleep 42
  PID=$(tasklist //FI "IMAGENAME eq ps2EntryRunner.exe" //FO CSV //NH 2>/dev/null | head -1 | cut -d, -f2 | tr -d '"')
  [ -n "$PID" ] && taskkill //F //PID "$PID" >/dev/null 2>&1
  echo "=== cycles=$v ==="
  grep "spu2:lap" "run_sweep_$v.log" | tail -3 | cut -c1-120
  grep -c "spu2:lap" "run_sweep_$v.log"
done
echo SWEEP_DONE
