#!/bin/bash
# run_tb_v398.sh (lowsize, 2026-11-06): дифференциальная симуляция
# v3.9.7 vs v3.9.8 (мера п.23: узел тактирования на 50 МГц - кольцо
# напрямую, X1 = r0, clk25 = /2 для логики, por-цепь в 50-домене).
# Icarus Verilog 12.0 (tools/iverilog).
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/v398_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/lowsize
sed 's/retro_pcld_top/retro_pcld_top_v397/g' "$SRC/top_suart_por6_v397_utf8.v" > "$W/dut397.v"
sed 's/retro_pcld_top/retro_pcld_top_v398/g' "$SRC/top_suart_por6_v398_utf8.v" > "$W/dut398.v"

# Контроль: дифф DUT'ов в симуляции (имена нормализованы, комментарии срезаны)
echo "=== ДИФФ КОДА DUT'ов В СИМУЛЯЦИИ (имена нормализованы, комментарии срезаны) ==="
diff <(sed 's/retro_pcld_top_v397/M/g' "$W/dut397.v" | sed 's|//.*||' | sed '/^[[:space:]]*$/d') \
     <(sed 's/retro_pcld_top_v398/M/g' "$W/dut398.v" | sed 's|//.*||' | sed '/^[[:space:]]*$/d') || true
echo "=== КОНЕЦ ДИФФА (ожидается ТОЛЬКО узел тактирования: кольцо/clk25/X1/X2/por-цепь/такты clk->clk25) ==="

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut397.v" "$W/dut398.v" "$SRC/scripts/tb_v398_diff.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp" | tee "$W/run.log"

echo
echo "=== СВОДКА ==="
grep -E "PASS|FAIL|ИТОГ|ITOGE|ITOG" "$W/run.log"
