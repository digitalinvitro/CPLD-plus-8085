#!/bin/bash
# run_tb_por_fuzz_v395.sh (lowsize, 2026-11-05): тот же fuzz-тест окна POR
# (tb_por_fuzz.v), но B-DUT = v3.9.5 (фикс п.20). Ожидание: v3.9.2 0/N
# и v3.9.5 0/N грязи в момент снятия por_run, rd_drive=0 у обоих.
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/porfuzz_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/lowsize
sed 's/retro_pcld_top/retro_pcld_top_v392/g' "$SRC/top_suart_por6_v392_utf8.v" > "$W/dut392.v"
sed 's/retro_pcld_top/retro_pcld_top_v395/g' "$SRC/top_suart_por6_v395_utf8.v" > "$W/dut395.v"
sed 's/394/395/g' "$SRC/scripts/tb_por_fuzz.v" > "$W/tb_por_fuzz_v395.v"

"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim395.vvp" \
  "$W/dut392.v" "$W/dut395.v" "$W/tb_por_fuzz_v395.v"

N=${1:-100}
for ((s=1; s<=N; s++)); do
  "$IVLROOT/usr/bin/vvp" "$W/sim395.vvp" +SEED=$s | grep '^RESULT'
done | awk '
{
  n++;
  for (i = 3; i <= NF; i++) {
    split($i, kv, "="); v = kv[2] + 0;
    if      (kv[1] == "d_fall392") { if (v != 0) f392++; }
    else if (kv[1] == "d_fall395") { if (v != 0) f395++; }
    else if (kv[1] == "d_stop392") { if (v != 0) s392++; }
    else if (kv[1] == "d_stop395") { if (v != 0) s395++; }
    else if (kv[1] == "rdrive392") rd2 += v;
    else if (kv[1] == "rdrive395") rd5 += v;
    else if (kv[1] == "we392")     we2 += v;
    else if (kv[1] == "we395")     we5 += v;
  }
}
END {
  printf "ИТОГ: seedов=%d\n", n;
  printf "  ГРЯЗЬ В МОМЕНТ СНЯТИЯ por_run:  v3.9.2 = %d/%d   v3.9.5 = %d/%d\n", f392, n, f395, n;
  printf "  ГРЯЗЬ НА «СТАРТЕ CPU» (+200ns): v3.9.2 = %d/%d   v3.9.5 = %d/%d\n", s392, n, s395, n;
  printf "  rd_drive в окне POR (тактов с A-контеншном): v3.9.2 = %d   v3.9.5 = %d\n", rd2, rd5;
  printf "  WE_n=0 в окне POR (НАРУШЕНИЕ gate):          v3.9.2 = %d   v3.9.5 = %d\n", we2, we5;
}'
