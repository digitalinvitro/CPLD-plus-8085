#!/bin/bash
# run_tb_v23.sh (txuart, 2026-11-09): тестбенч tb_txuart_v23.v против
# РЕАЛЬНОГО RTL top_txuart_por6_v23 (Icarus Verilog 12.0, tools/iverilog).
# v2.2 = узел /4 на 25 МГц (директива владельца 11-9): кольцо s0..s3 на
# clk 25 МГц (CLKP=40 нс, X1 = s0 = 6,25 МГц duty 1/4), clk25_q УДАЛЁН -
# вся логика на clk 25, ядро v2.3: бод 25/25 = РОВНО 1 000 000 (бит 1000 нс,
# сетка CH340G 48М/48; 1 562 500 = мусор CH340, урок железа 11-9),
# POR 8 x 160 = 1280 нс, сброс через квалификатор
# п.21 (~400 нс). Проверки: P0a - все 16 кодов кольца -> one-hot;
# C1 POR-кромка ~1240 нс; C1b X1 160/40/120 нс + X2 противофаза;
# C2-C5 кадры/поллинг/отброс/статус; C7 сброс посреди кадра.
# Ядро бит-в-бит v2.1 доказано sim_txuart_v21.py (92/92) +
# diffsim_v2_v21.py (8283 тика, 0 расхождений) и check_v23.py (C5).
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/txuart_v23_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/txuart

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$SRC/tb_txuart_v23.v" "$SRC/top_txuart_por6_v23_utf8.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp"
