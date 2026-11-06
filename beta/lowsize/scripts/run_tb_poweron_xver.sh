#!/bin/bash
# run_tb_poweron_xver.sh (lowsize, 2026-11-06): KROSS-VERSIONNAYA matrica
# tb_poweron (issledovanie zhaloby 11-6/11-7, prodolzhenie) + kontrol'nyj
# eksperiment "hvost 200 ns" na etalone v3.9.5.
#
#  1) ORIGINAL'NYY tb_poweron.v (etalon, bez pravok) - na v3.9.2 / v3.9.3 /
#     v3.9.4 / v3.9.5: ozhidaniya - P1 FAIL na 3.9.3/3.9.4 (defekt 11-5:
#     FSM zhivet vsyo POR na plavayushchey shine), PASS na 3.9.2/3.9.5;
#     P2 (mertvyy clk = polnyy simptom-kompleks zhaloby) PASS na VSEH,
#     vklyuchaya v3.9.2 - "stabil'nost'" v3.9.2 v pole ne obyasnyaetsya RTL.
#  2) tb_poweron_v395_tail.v (edinstvennaya pravka: P1 + hvost) - na
#     v3.9.5: bazovaya liniya dlya sravneniya s v3.9.7 (tb_poweron_v397).
set -e
IVLROOT=/home/z/my-project/tools/iverilog/root
export LD_LIBRARY_PATH=$IVLROOT/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}
W=/home/z/my-project/scripts/poweron_xver_work
mkdir -p "$W"

SRC=/home/z/my-project/CPLD-plus-8085/beta/lowsize

for V in v392 v393 v394 v395; do
  echo
  echo "####################################################################"
  echo "### tb_poweron (original) na v3.9.${V#v39}"
  echo "####################################################################"
  cp "$SRC/top_suart_por6_${V}_utf8.v" "$W/dut.v"
  "$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim_${V}.vvp" \
    "$W/dut.v" "$SRC/scripts/tb_poweron.v"
  "$IVLROOT/usr/bin/vvp" "$W/sim_${V}.vvp" > "$W/run_${V}.log"
  grep -E "RESULT" "$W/run_${V}.log" || true
done

echo
echo "####################################################################"
echo "### tb_poweron_v395_tail (P1 + hvost 200ns/1mks) na etalone v3.9.5"
echo "####################################################################"
cp "$SRC/top_suart_por6_v395_utf8.v" "$W/dut_tail.v"
"$IVLROOT/usr/bin/iverilog" -g2001 -o "$W/sim_tail.vvp" \
  "$W/dut_tail.v" "$SRC/scripts/tb_poweron_v395_tail.v"
"$IVLROOT/usr/bin/vvp" "$W/sim_tail.vvp" | tee "$W/run_tail.log"
grep -E "RESULT" "$W/run_tail.log" || true
