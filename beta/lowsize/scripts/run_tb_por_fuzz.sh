#!/bin/bash
# run_tb_por_fuzz.sh (lowsize, 2026-11-05): fuzz-test okna POR
# (tb_por_fuzz.v) - dokazatel'stvo defekta starta v3.9.3/v3.9.4:
# v3.9.2 (cpu_rst-prikovka kazhdyj takt) dolzhen byt' CHISTYM v moment
# snjatija por_run pri LJUBOM secd; v3.9.4 (FSM zhiva na plavajuschej
# shine) - grjazit. Zapusk: run_tb_por_fuzz.sh [N_seedov, default 100]
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/porfuzz_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/lowsize
# DUT v3.9.2 (etalon) i v3.9.4 (defekt) iz UTF8-dvojnikov
sed 's/retro_pcld_top/retro_pcld_top_v392/g' "$SRC/top_suart_por6_v392_utf8.v" > "$W/dut392.v"
sed 's/retro_pcld_top/retro_pcld_top_v394/g' "$SRC/top_suart_por6_v394_utf8.v" > "$W/dut394.v"

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim.vvp" \
  "$W/dut392.v" "$W/dut394.v" "$SRC/scripts/tb_por_fuzz.v"

N=${1:-100}
for ((s=1; s<=N; s++)); do
  "$IVLROOT/usr/bin/vvp" "$W/sim.vvp" +SEED=$s | grep '^RESULT'
done | awk '
{
  n++;
  for (i = 3; i <= NF; i++) {
    split($i, kv, "="); v = kv[2] + 0;
    if      (kv[1] == "d_fall392") { if (v != 0) f392++; }
    else if (kv[1] == "d_fall394") { if (v != 0) f394++; }
    else if (kv[1] == "d_stop392") { if (v != 0) s392++; }
    else if (kv[1] == "d_stop394") { if (v != 0) s394++; }
    else if (kv[1] == "rdrive392") rd2 += v;
    else if (kv[1] == "rdrive394") rd4 += v;
    else if (kv[1] == "we392")     we2 += v;
    else if (kv[1] == "we394")     we4 += v;
  }
}
END {
  printf "ИТОГ: seedov=%d\n", n;
  printf "  ГРЯЗЬ В МОМЕНТ СНЯТИЯ por_run:  v3.9.2 = %d/%d   v3.9.4 = %d/%d\n", f392, n, f394, n;
  printf "  ГРЯЗЬ НА «СТАРТЕ CPU» (+200ns): v3.9.2 = %d/%d   v3.9.4 = %d/%d\n", s392, n, s394, n;
  printf "  rd_drive в окне POR (тактов с A-контеншном): v3.9.2 = %d   v3.9.4 = %d\n", rd2, rd4;
  printf "  WE_n=0 в окне POR (НАРУШЕНИЕ gate):          v3.9.2 = %d   v3.9.4 = %d\n", we2, we4;
}'
