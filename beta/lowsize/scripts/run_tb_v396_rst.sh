#!/bin/bash
# run_tb_v396_rst.sh (lowsize, 2026-11-06): дифференциальная симуляция
# v3.9.5 vs v3.9.6 по цепи сброса (мера п.21: хардренинг - RST только
# через регистры, RESET_IN - регистр reset_q). Icarus Verilog 12.0
# (tools/iverilog).
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/v396_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/lowsize
sed 's/retro_pcld_top/retro_pcld_top_v395/g' "$SRC/top_suart_por6_v395_utf8.v" > "$W/dut395.v"
sed 's/retro_pcld_top/retro_pcld_top_v396/g' "$SRC/top_suart_por6_v396_utf8.v" > "$W/dut396.v"

# Контроль: дифф DUT'ов в симуляции (имена нормализованы, комментарии срезаны)
echo "=== ДИФФ КОДА DUT'ов В СИМУЛЯЦИИ (имена нормализованы, комментарии срезаны) ==="
diff <(sed 's/retro_pcld_top_v395/M/g' "$W/dut395.v" | sed 's|//.*||' | sed '/^[[:space:]]*$/d') \
     <(sed 's/retro_pcld_top_v396/M/g' "$W/dut396.v" | sed 's|//.*||' | sed '/^[[:space:]]*$/d') | head -80 || true
echo "=== КОНЕЦ ДИФФА (ожидается ТОЛЬКО блок п.21: синхронизатор/квалификатор/cpu_rst/reset_q, гейт S_T2, assign RESET_IN) ==="

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut395.v" "$W/dut396.v" "$SRC/scripts/tb_v396_rst.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp"
