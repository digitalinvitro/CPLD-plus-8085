#!/bin/bash
# run_tb_v401.sh (hwuart, 2026-11-05): дифференциальная симуляция v4.0.0 vs v4.0.1
# (POR-счётчик 8->4 со стробом x1_n, М1 из lowsize v3.9.4, п.27 шапки RTL).
# Icarus Verilog 12.0, распакованный в tools/iverilog (без root, dpkg -x).
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/v401_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/hwuart
# Переименование модулей (оба файла определяют retro_pcld_top)
sed 's/retro_pcld_top/retro_pcld_top_v400/g' "$SRC/top_hwuart_por6_v400_utf8.v" > "$W/dut400.v"
sed 's/retro_pcld_top/retro_pcld_top_v401/g' "$SRC/top_hwuart_por6_v401_utf8.v" > "$W/dut401.v"

# Контроль: дифф DUT'ов в симуляции (после нормализации имён) = код-дифф меры
echo "=== ДИФФ КОДА DUT'ов В СИМУЛЯЦИИ (имена нормализованы, комментарии срезаны) ==="
diff <(sed 's/retro_pcld_top_v400/M/g' "$W/dut400.v" | sed 's|//.*||') \
     <(sed 's/retro_pcld_top_v401/M/g' "$W/dut401.v" | sed 's|//.*||') | head -30 || true
echo "=== КОНЕЦ ДИФФА (ожидаются ТОЛЬКО: строб por_ce=x1_n, por_sh[3:0], сдвиг [3:1]) ==="

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut400.v" "$W/dut401.v" "$SRC/scripts/tb_v401_diff.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp"
