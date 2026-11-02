#!/bin/bash
# run_tb_v393.sh (lowsize, 2026-11-02): дифференциальная симуляция v3.9.2 vs v3.9.3
# (сброс логики -> сеть GSR, п.18 шапки RTL). Icarus Verilog 12.0,
# распакованный в tools/iverilog (без root, dpkg -x).
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/v393_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/lowsize
# Переименование модулей (оба файла определяют retro_pcld_top)
sed 's/retro_pcld_top/retro_pcld_top_v392/g' "$SRC/top_suart_por6_v392_utf8.v" > "$W/dut392.v"
sed 's/retro_pcld_top/retro_pcld_top_v393/g' "$SRC/top_suart_por6_v393_utf8.v" > "$W/dut393.v"

# Контроль: дифф DUT'ов в симуляции (после нормализации имён) = код-дифф меры
echo "=== ДИФФ КОДА DUT'ов В СИМУЛЯЦИИ (имена нормализованы, комментарии срезаны) ==="
diff <(sed 's/retro_pcld_top_v392/M/g' "$W/dut392.v" | sed 's|//.*||') \
     <(sed 's/retro_pcld_top_v393/M/g' "$W/dut393.v" | sed 's|//.*||') | head -40 || true
echo "=== КОНЕЦ ДИФФА (ожидаются ТОЛЬКО: async always/RST, гейт !por_run) ==="

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut392.v" "$W/dut393.v" "$SRC/scripts/tb_v393_diff.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp"
