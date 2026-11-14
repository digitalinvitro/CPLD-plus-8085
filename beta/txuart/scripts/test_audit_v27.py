#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_audit_v27.py - испытание аудитора в трёх режимах.

  T1  fit6 (реальный отчёт v2.6) в режиме v26  -> ШИТЬ 21/0 (регрессия)
  T2  fit6 в режиме v27                        -> НЕ ШИТЬ (тика нет - громко)
  T3  синтетический отчёт (fit6 + впрыск печати тика в калиброванном
      формате) в режиме v27                    -> ШИТЬ, все проверки тика PASS

Синтетика валидирует парсер/сим аудитора против ОЖИДАЕМОГО формата
печати cpldfit. Если реальный fit v2.7 напечатает иначе - аудитор громко
FAIL-нет с диагностикой (имя нераспознанного символа), чинится калибровкой.
"""
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RPT = "/home/z/my-project/upload/retro_pcld_top.rpt"
AUD = os.path.join(HERE, "audit_fit_node.py")
SYN = "/tmp/synth_v27.rpt"

src = io.open(RPT, "r", encoding="cp1251", errors="replace").read()

# --- впрыск 1: бюджет 107/108 ---
src = src.replace("101/108 ( 94%) 339 /540", "107/108 ( 99%) 352 /540", 1)
assert "107/108 ( 99%)" in src

# --- впрыск 2: инстансы тика (после инстансов делителя) ---
anchor = "FTCPE_X1: FTCPE port map (X1,t0_q,clk,'0','0');"
inj = anchor + """
FDCPE_tick_cnt0: FDCPE port map (tick_cnt(0),tick_cnt_D(0),clk,'0','0');
FDCPE_tick_cnt1: FDCPE port map (tick_cnt(1),tick_cnt_D(1),clk,'0','0');
FDCPE_tick_cnt2: FDCPE port map (tick_cnt(2),tick_cnt_D(2),clk,'0','0');
FDCPE_tick_cnt3: FDCPE port map (tick_cnt(3),tick_cnt_D(3),clk,'0','0');
FDCPE_tick_cnt4: FDCPE port map (tick_cnt(4),tick_cnt_D(4),clk,'0','0');
FDCPE_tick_q: FDCPE port map (tick_q,tick_q_D,clk,'0','0');"""
assert anchor in src
src = src.replace(anchor, inj, 1)

# --- впрыск 3: уравнения тика (в конец секции Equations) ---
eq_anchor = "baud_cnt_D(0) <= (NOT baud_cnt(0) AND NOT $OpTx$FX_SC$789);"
eqs = eq_anchor + """
tick_step <= por_ce AND baud_tick;
por_ce <= NOT t0_q AND NOT x1_q;
baud_tick <= baud_cnt(4) AND baud_cnt(3) AND NOT baud_cnt(2) AND NOT baud_cnt(1) AND NOT baud_cnt(0);
tick_cnt_D(0) <= (tick_cnt(0) XOR tick_step);
tick_cnt_D(1) <= (tick_cnt(1) XOR (tick_step AND tick_cnt(0)));
tick_cnt_D(2) <= (tick_cnt(2) XOR (tick_step AND tick_cnt(1) AND tick_cnt(0)));
tick_cnt_D(3) <= (tick_cnt(3) XOR (tick_step AND tick_cnt(2) AND tick_cnt(1) AND tick_cnt(0)));
tick_cnt_D(4) <= (tick_cnt(4) XOR (tick_step AND tick_cnt(3) AND tick_cnt(2) AND tick_cnt(1) AND tick_cnt(0)));
tick_q_D <= ((tick_step AND tick_cnt(4)) OR (NOT tick_step AND tick_q));"""
assert eq_anchor in src
src = src.replace(eq_anchor, eqs, 1)

# --- впрыск 4: строка пина TRAP (после X2 в таблице registered) ---
x2row = None
for line in src.split("\n"):
    if line.startswith("X2 ") and " 69   I/O     O " in line:
        x2row = line
        break
assert x2row, "строка X2 не найдена"
traprow = x2row.replace("X2 ", "TRAP", 1).replace("   69  ", "   74  ")
src = src.replace(x2row, x2row + "\n" + traprow, 1)

io.open(SYN, "w", encoding="cp1251", errors="replace").write(src)


def run(args):
    p = subprocess.run([sys.executable, AUD] + args, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


fails = 0

# T1: v26-регрессия на реальном fit6
rc, out = run([RPT, "v26"])
t1 = rc == 0 and "ВЕРДИКТ: ШИТЬ" in out and "PASS 21 / FAIL 0" in out
print("T1 v26-регрессия на fit6:", "PASS" if t1 else "FAIL")
if not t1:
    print(out[-1500:])
    fails += 1

# T2: v27 на fit6 - тика нет, громкий FAIL
rc, out = run([RPT, "v27"])
t2 = rc != 0 and "ВЕРДИКТ: НЕ ШИТЬ" in out and "ТИК v2.7 в отчёте НЕ найден" in out
print("T2 v27 на fit6 (ожид. НЕ ШИТЬ):", "PASS" if t2 else "FAIL")
if not t2:
    print(out[-1500:])
    fails += 1

# T3: v27 на синтетике - ШИТЬ, все тик-проверки PASS
rc, out = run([SYN, "v27"])
t3 = rc == 0 and "ВЕРДИКТ: ШИТЬ" in out
tick_ok = all(s in out for s in (
    "tick_step: 64 строба, каждые ровно 100 клк",
    "фронт tick_q каждые ровно 3200 клк",
    "high tick_q ровно 1600 клк",
    "D(tick_q) без XOR",
    "TRAP: P74, выход, registered, INIT=RESET",
    "МЦ = 107"))
print("T3 v27 на синтетике (ожид. ШИТЬ):", "PASS" if t3 else "FAIL",
      "| тик-пункты:", "ALL" if tick_ok else "НЕ ПОЛНЫ")
if not (t3 and tick_ok):
    print(out)
    fails += 1

print("\nИТОГ теста аудитора: %s (%d провалов)" % ("PASS" if fails == 0 else "FAIL", fails))
sys.exit(1 if fails else 0)
