#!/bin/bash
# run_tb_poweron_v32.sh (txuart, 2026-11-17): dokazatel'nyy test sbrosa CPU
# po schetu frontov CLKOUT - VARIANT A (v3.2 = v3.1 + bus_ld_t1/t2 keep; tb 1-v-1).
# Icarus Verilog 12.0 (tools/iverilog). DUT - real'nyy RTL v3.2.
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/poweron_v32_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/txuart
# DUT bez pereimenovaniya - tb_poweron_v30 instanciruet retro_pcld_top
cp "$SRC/top_txuart_por6_v32_utf8.v" "$W/dut32.v"

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut32.v" "$SRC/scripts/tb_poweron_v32.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp" | tee "$W/run.log"

echo
echo "=== SVODKA ==="
grep -E "RESULT|ITOGE" "$W/run.log"
