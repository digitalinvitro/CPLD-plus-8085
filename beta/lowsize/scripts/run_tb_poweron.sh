#!/bin/bash
# run_tb_poweron.sh (lowsize, 2026-11-06): dokazatel'nyy test stohasticheskoy
# loterei vklyucheniya pitaniya (zhaloba vladel'ca 11-6bis na v3.9.5).
# Icarus Verilog 12.0 (tools/iverilog). DUT - real'nyy RTL v3.9.5.
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/poweron_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/lowsize
# DUT bez pereimenovaniya - tb_poweron instanciruet retro_pcld_top (edinstvennyy v sborke)
cp "$SRC/top_suart_por6_v395_utf8.v" "$W/dut395.v"

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut395.v" "$SRC/scripts/tb_poweron.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp" | tee "$W/run.log"

echo
echo "=== SVODKA ==="
grep -E "RESULT|ITOGE|ITOG" "$W/run.log"
