#!/bin/bash
# run_tb_poweron_v397.sh (lowsize, 2026-11-06): dokazatel'nyy test
# stohasticheskoy loterei vklyucheniya pitaniya na RTL v3.9.7 (kol'tso).
# Icarus Verilog 12.0 (tools/iverilog). DUT - real'nyy RTL v3.9.7.
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/poweron_v397_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/lowsize
# DUT bez pereimenovaniya - tb_poweron_v397 instanciruet retro_pcld_top
cp "$SRC/top_suart_por6_v397_utf8.v" "$W/dut397.v"

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut397.v" "$SRC/scripts/tb_poweron_v397.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp" | tee "$W/run.log"

echo
echo "=== SVODKA ==="
grep -E "RESULT|ITOGE|ITOG" "$W/run.log"
