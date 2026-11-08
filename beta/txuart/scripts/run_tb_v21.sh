#!/bin/bash
# run_tb_v21.sh (txuart, 2026-11-08): тестбенч tb_txuart_v21.v против
# РЕАЛЬНОГО RTL top_txuart_por6_v21 (Icarus Verilog 12.0, tools/iverilog).
# v2.1 = сжатое ядро (20 -> 18 МЦ: adv_q/tx_run свернуты, jam 0, bit_cnt
# 1..10) на базе v3.9.8-clear: кольцо r0..r6 на clk 50 МГц (CLKP=20 нс),
# ядро на clk25 - бит 640 нс (1 562 500 бод), сброс через квалификатор
# п.21 (~400 нс). Первичная верификация - цикл-точная модель
# scripts/sim_txuart_v21.py (92/92) + дифсим scripts/diffsim_v2_v21.py
# (v2.0 vs v2.1, все наблюдаемые выходы, 0 расхождений); этот прогон
# доказывает, что модель соответствует RTL.
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/txuart_v21_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/txuart

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$SRC/tb_txuart_v21.v" "$SRC/top_txuart_por6_v21_utf8.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp"
