#!/bin/bash
# run_tb_v391.sh (clk10-62): дифференциальная симуляция v3.9 vs v3.9.1
# Icarus Verilog 12.0, распакованный в tools/iverilog (без root, dpkg -x)
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/v391_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/hiclock
# Переименование модулей (оба файла определяют retro_pcld_top)
sed 's/retro_pcld_top/retro_pcld_top_v39/g'  "$SRC/top_suart_por6_v39_utf8.v"  > "$W/dut39.v"
sed 's/retro_pcld_top/retro_pcld_top_v391/g' "$SRC/top_suart_por6_v391_utf8.v" > "$W/dut391.v"

# Контроль: дифф DUT'ов в симуляции (после нормализации имён) = реальный код-дифф
echo "=== ДИФФ КОДА DUT'ов В СИМУЛЯЦИИ (имена нормализованы) ==="
diff <(sed 's/retro_pcld_top_v39/M/g'  "$W/dut39.v") \
     <(sed 's/retro_pcld_top_v391/M/g' "$W/dut391.v") || true
echo "=== КОНЕЦ ДИФФА ==="

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut39.v" "$W/dut391.v" /home/z/my-project/scripts/tb_v391_diff.v
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp"
