#!/bin/bash
# run_tb_poweron_v399h.sh (hiclock, 2026-11-07): dokazatel'nyy test
# stohasticheskoy loterei vklyucheniya pitaniya na RTL v3.9.9h (kol'tco
# r0..r5 N=6 na clk 50 MGc, CPU 4,167 MGc + clk25 = /2 + por-cep' v
# 50-domene so stroboom r0). Icarus Verilog 12.0. DUT - real'nyy RTL v3.9.9h.
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/poweron_v399h_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/hiclock
# DUT bez pereimenovaniya - tb_poweron_v399h instanciruet retro_pcld_top
cp "$SRC/top_suart_hiclock_v399_utf8.v" "$W/dut399h.v"

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut399h.v" "$SRC/scripts/tb_poweron_v399h.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp" | tee "$W/run.log"

echo
echo "=== SVODKA ==="
grep -E "RESULT|ITOG" "$W/run.log"
