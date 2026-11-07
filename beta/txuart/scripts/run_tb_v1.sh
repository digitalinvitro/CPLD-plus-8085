#!/bin/bash
# run_tb_v1.sh (txuart, 2026-11-08): тестбенч владельца tb_txuart_v1.v против
# РЕАЛЬНОГО RTL top_txuart_por6_v1 (Icarus Verilog 12.0, tools/iverilog).
# Первичная верификация - цикл-точная модель scripts/sim_txuart_v1.py (87/87);
# этот прогон доказывает, что модель соответствует RTL.
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/txuart_v1_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/txuart

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$SRC/tb_txuart_v1.v" "$SRC/top_txuart_por6_v1_utf8.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp"
