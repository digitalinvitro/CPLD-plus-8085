#!/bin/bash
# run_tb_poweron_v31.sh (txuart, 2026-11-17): dokazatel'nyy test sbrosa CPU
# po schetu frontov CLKOUT - VARIANT A (v3.1 = v3.0 + X2 open; tb 1-v-1 v30).
# Icarus Verilog 12.0 (tools/iverilog). DUT - real'nyy RTL v3.1.
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/poweron_v31_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/txuart
# DUT bez pereimenovaniya - tb_poweron_v30 instanciruet retro_pcld_top
cp "$SRC/top_txuart_por6_v31_utf8.v" "$W/dut31.v"

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut31.v" "$SRC/scripts/tb_poweron_v31.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp" | tee "$W/run.log"

echo
echo "=== SVODKA ==="
grep -E "RESULT|ITOGE" "$W/run.log"
