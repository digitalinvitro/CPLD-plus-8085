#!/bin/bash
# run_tb_v394.sh (lowsize, 2026-11-05): дифференциальная симуляция v3.9.3 vs v3.9.4
# (POR-счётчик 8->4 со стробом x1_n, М1 из txclient v8, п.19 шапки RTL).
# Icarus Verilog 12.0, распакованный в tools/iverilog (без root, dpkg -x).
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/v394_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/lowsize
# Переименование модулей (оба файла определяют retro_pcld_top)
sed 's/retro_pcld_top/retro_pcld_top_v393/g' "$SRC/top_suart_por6_v393_utf8.v" > "$W/dut393.v"
sed 's/retro_pcld_top/retro_pcld_top_v394/g' "$SRC/top_suart_por6_v394_utf8.v" > "$W/dut394.v"

# Контроль: дифф DUT'ов в симуляции (после нормализации имён) = код-дифф меры
echo "=== ДИФФ КОДА DUT'ов В СИМУЛЯЦИИ (имена нормализованы, комментарии срезаны) ==="
diff <(sed 's/retro_pcld_top_v393/M/g' "$W/dut393.v" | sed 's|//.*||') \
     <(sed 's/retro_pcld_top_v394/M/g' "$W/dut394.v" | sed 's|//.*||') | head -30 || true
echo "=== КОНЕЦ ДИФФА (ожидаются ТОЛЬКО: строб por_ce=x1_n, por_sh[3:0], сдвиг [3:1]) ==="

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut393.v" "$W/dut394.v" "$SRC/scripts/tb_v394_diff.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp"
