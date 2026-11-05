#!/bin/bash
# run_tb_v395.sh (lowsize, 2026-11-05): дифференциальная симуляция v3.9.4 vs v3.9.5
# (мера п.20: GSR-источник = cpu_rst = RST|por_run - закрытие дефекта
# старта v3.9.3/v3.9.4). Icarus Verilog 12.0 (tools/iverilog).
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/v395_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/lowsize
sed 's/retro_pcld_top/retro_pcld_top_v394/g' "$SRC/top_suart_por6_v394_utf8.v" > "$W/dut394.v"
sed 's/retro_pcld_top/retro_pcld_top_v395/g' "$SRC/top_suart_por6_v395_utf8.v" > "$W/dut395.v"

# Контроль: дифф DUT'ов в симуляции (имена нормализованы, комментарии срезаны)
echo "=== ДИФФ КОДА DUT'ов В СИМУЛЯЦИИ (имена нормализованы, комментарии срезаны) ==="
diff <(sed 's/retro_pcld_top_v394/M/g' "$W/dut394.v" | sed 's|//.*||') \
     <(sed 's/retro_pcld_top_v395/M/g' "$W/dut395.v" | sed 's|//.*||') | head -20 || true
echo "=== КОНЕЦ ДИФФА (ожидаются ТОЛЬКО 2 строки: always ... or posedge cpu_rst / if (cpu_rst)) ==="

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut394.v" "$W/dut395.v" "$SRC/scripts/tb_v395_diff.v"
"$IVLROOT/usr/bin/vvp" "$W/sim.vvp"
