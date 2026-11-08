#!/bin/bash
# run_tb_v2.sh (txuart, 2026-11-08): тестбенч владельца tb_txuart_v2.v против
# РЕАЛЬНОГО RTL top_txuart_por6_v2 (Icarus Verilog 12.0, tools/iverilog).
# База v3.9.8-clear: кольцо r0..r6 на clk 50 МГц (CLKP=20 нс), ядро на clk25 -
# бит 640 нс (1 562 500 бод), сброс через квалификатор п.21 (~400 нс).
# Первичная верификация - цикл-точная модель scripts/sim_txuart_v2.py (92/92);
# этот прогон доказывает, что модель соответствует RTL.
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/txuart_v2_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/txuart

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$SRC/tb_txuart_v2.v" "$SRC/top_txuart_por6_v2_utf8.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp"
