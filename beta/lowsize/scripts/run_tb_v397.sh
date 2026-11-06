#!/bin/bash
# run_tb_v397.sh (lowsize, 2026-11-06): дифференциальная симуляция
# v3.9.6 vs v3.9.7 (мера п.22: возврат кольцевого делителя one-hot
# r0..r6 вместо двоичного mod-7 cnt). Icarus Verilog 12.0 (tools/iverilog).
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/v397_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/lowsize
sed 's/retro_pcld_top/retro_pcld_top_v396/g' "$SRC/top_suart_por6_v396_utf8.v" > "$W/dut396.v"
sed 's/retro_pcld_top/retro_pcld_top_v397/g' "$SRC/top_suart_por6_v397_utf8.v" > "$W/dut397.v"

# Контроль: дифф DUT'ов в симуляции (имена нормализованы, комментарии срезаны)
echo "=== ДИФФ КОДА DUT'ов В СИМУЛЯЦИИ (имена нормализованы, комментарии срезаны) ==="
diff <(sed 's/retro_pcld_top_v396/M/g' "$W/dut396.v" | sed 's|//.*||' | sed '/^[[:space:]]*$/d') \
     <(sed 's/retro_pcld_top_v397/M/g' "$W/dut397.v" | sed 's|//.*||' | sed '/^[[:space:]]*$/d') || true
echo "=== КОНЕЦ ДИФФА (ожидается ТОЛЬКО блок делителя: r0..r6, кольцо, x1_n r3/r4, X1/X2 от r0) ==="

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut396.v" "$W/dut397.v" "$SRC/scripts/tb_v397_diff.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp" | tee "$W/run.log"

echo
echo "=== СВОДКА ==="
grep -E "PASS|FAIL|ИТОГ|ITOGE|ITOG" "$W/run.log"
