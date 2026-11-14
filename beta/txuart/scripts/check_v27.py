#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_v27.py - верификатор txuart v2.7 (ТИК на TRAP, вариант C).

Проверки:
  C0  файлы линии; hex прошивки;
  C1  CP1251 round-trip;
  C2  заголовок v2.7 (вариант C, LCM-шаг, джиттер документирован);
  C3  узел тика в КОДЕ: 6 FF, НЕТ декодов равенства, НЕТ ветки сброса,
      TRAP = tick_q; делитель v2.6 и ядро UART НЕ ТРОНУТЫ;
  C4  диф КОДА v2.7 vs v2.6 = чистое ДОБАВЛЕНИЕ (узел тика + порт +
      комментарии; ни одна живая строка не удалена/изменена);
  C5  диф-сим узла тика 12800 клк: tick_step каждые ровно 100 клк
      (первое на 74-м), фронт tick_q каждые ровно 3200 клк, high
      ровно 1600 клк (64/64 мкс); делитель и por/baud стробы в норме;
  C6  UCF: NET TRAP P74; держатели 9 -> 8 (PGND-набор без P74).
"""
import io
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

V27 = os.path.join(ROOT, "top_txuart_por6_v27_utf8.v")
V26 = os.path.join(ROOT, "top_txuart_por6_v26_utf8.v")
UCF = os.path.join(ROOT, "top_txuart.ucf")

pass_n = fail_n = 0


def chk(cond, name, detail=""):
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print("  PASS %s" % name)
    else:
        fail_n += 1
        print("  FAIL %s %s" % (name, detail))


def code_lines(t):
    out = []
    for l in t.split("\n"):
        c = (l.split("//")[0] if "//" in l else l).rstrip()
        if c.strip():
            out.append(re.sub(r"\s+", " ", c.strip()))
    return out


u27 = io.open(V27, encoding="utf-8").read()
u26 = io.open(V26, encoding="utf-8").read()
ucf = io.open(UCF, encoding="cp1251").read()

print("== C0 файлы линии ==")
for p in (V27, os.path.join(ROOT, "top_txuart_por6_v27.v"), UCF,
          os.path.join(ROOT, "rom", "uart_tx_test.hex"),
          os.path.join(HERE, "gen_v27.py")):
    chk(os.path.exists(p), "exists %s" % os.path.basename(p))
chk(len(io.open(os.path.join(ROOT, "rom", "uart_tx_test.hex"), "rb").read()) == 2144,
    "hex: 2144 байт")

print("== C1 CP1251 round-trip ==")
chk(io.open(os.path.join(ROOT, "top_txuart_por6_v27.v"), "rb").read().decode("cp1251") == u27,
    "v27.v (cp1251) == v27_utf8.v (utf8)")

print("== C2 заголовок v2.7 ==")
for pat in ("// top_txuart.v v2.7 -", "v2.7 (ТИК, директива владельца",
            "ВАРИАНТ C", "LCM(4,25) = 100 клк = 4 мкс",
            "первое на клке 74",
            "ДЖИТТЕР (честно)", "128 +/- 8 мкс (6%)",
            "PGND-набор 9 -> 8"):
    chk(pat in u27, "заголовок: %r" % pat[:48])
for pat in ("В D-пути счётчика декодов НЕТ",
            "ЗАЩЁЛКА-МУКС", "БЕЗ XOR - урок v2.5",
            "D = (tick_step & tick_cnt[4]) | (~tick_step & tick_q)"):
    chk(pat in u27, "заголовок: %r" % pat[:48])

print("== C3 узел тика в коде ==")
code = "\n".join((l.split("//")[0] if "//" in l else l) for l in u27.split("\n"))
ncode = "\n".join(re.sub(r"\s+", " ", c.strip()) for c in code.split("\n") if c.strip())
for pat in ("wire tick_step = por_ce & baud_tick;",
            "reg [4:0] tick_cnt = 5'd0;",
            "reg tick_q = 1'b0;",
            "if (tick_step) tick_cnt <= tick_cnt + 5'd1;",
            "tick_q <= (tick_step & tick_cnt[4]) | (~tick_step & tick_q);",
            "assign TRAP = tick_q;",
            "output wire TRAP,"):
    chk(pat in ncode, "код: %r" % pat)
chk(re.search(r"tick_cnt\s*==", ncode) is None, "в узле тика НЕТ декодов равенства")
chk("if (tick_step) tick_cnt <= tick_cnt + 5'd1;\ntick_q <= (tick_step & tick_cnt[4]) | (~tick_step & tick_q);\nend" in ncode
    and "always @(posedge clk or posedge cpu_rst) begin" in ncode
    and "if (cpu_rst) begin" in ncode
    and "shreg <= 9'h1FF;" in ncode,
    "тик - отдельный always БЕЗ сброса (защёлка-мукс); ядро UART со своим cpu_rst НЕ тронуто")
# делитель v2.6 не тронут
for pat in ("t0_q <= ~t0_q;", "if (t0_q) x1_q <= ~x1_q;",
            "if (t0_q) x2_q <= ~x2_q;", "assign por_ce = ~t0_q & ~x1_q;"):
    chk(pat in ncode, "делитель v2.6 цел: %r" % pat)
# ядро UART не тронутo
for pat in ("wire baud_tick = (baud_cnt == (BAUD_DIV - 5'd1));",
            "baud_cnt <= baud_tick ? 5'd0 : baud_cnt + 5'd1;"):
    chk(pat in ncode, "ядро UART цело: %r" % pat[:44])

print("== C4 диф кода v2.7 vs v2.6 = чистое добавление ==")
c26, c27 = Counter(code_lines(u26)), Counter(code_lines(u27))
removed = list((c26 - c27).elements())
added = list((c27 - c26).elements())
chk(removed == [], "НИ ОДНОЙ удалённой/изменённой живой строки", str(removed))
chk("wire tick_step = por_ce & baud_tick;" in added
    and "assign TRAP = tick_q;" in added
    and "output wire TRAP," in added
    and "tick_q <= (tick_step & tick_cnt[4]) | (~tick_step & tick_q);" in added
    and sum(1 for a in added if a.startswith("reg")) == 2,
    "добавлены ровно: узел тика (wire+2 reg+2 строки always+assign) и порт TRAP",
    "%d строк" % len(added))

print("== C5 диф-сим узла тика (12800 клк = 4 периода) ==")
T = 12800
t0, x1, x2 = 0, 1, 0
bc, tc, tq = 0, 0, 0
step_clks, q_edges = [], []
por_seen, bt_seen = 0, 0
for c in range(T):
    por_ce = 1 - (t0 | x1)
    bt = 1 if bc == 24 else 0
    step = por_ce & bt
    if step:
        step_clks.append(c)
    if por_ce:
        por_seen += 1
    if bt:
        bt_seen += 1
    c4 = (tc >> 4) & 1
    nq = (step & c4) | ((1 - step) & tq)  # защёлка-мукс (регистр)
    if tq == 0 and nq == 1:
        q_edges.append(c + 1)             # виден со следующего клка
    nbc = 0 if bt else bc + 1
    ntc = (tc + 1) & 31 if step else tc
    t0, x1, x2 = 1 - t0, x1 ^ t0, x2 ^ t0
    bc, tc, tq = nbc, ntc, nq
gaps = {step_clks[i + 1] - step_clks[i] for i in range(len(step_clks) - 1)}
chk(step_clks[0] == 74, "первое совпадение tick_step на клке 74", str(step_clks[0]))
chk(gaps == {100}, "tick_step каждые ровно 100 клк (4 мкс)", str(sorted(gaps)[:5]))
chk(q_edges == [1675, 4875, 8075, 11275],
    "фронт tick_q каждые ровно 3200 клк (128 мкс): [1675,4875,8075,11275]",
    str(q_edges))
chk(q_edges[1] - q_edges[0] == 3200, "период ровно 128 мкс")
chk(por_seen == T // 4 and bt_seen == T // 25,
    "por_ce 1/4 и baud_tick 1/25 не нарушены")
# ширина high: сим на 100 клк за первым фронтом до первого спада
t0, x1, x2, bc, tc, tq = 0, 1, 0, 0, 0, 0
fall = None
for c in range(4000):
    por_ce = 1 - (t0 | x1)
    bt = 1 if bc == 24 else 0
    step = por_ce & bt
    c4 = (tc >> 4) & 1
    nq = (step & c4) | ((1 - step) & tq)
    if tq == 1 and nq == 0 and fall is None and c > 1775:
        fall = c + 1
    nbc = 0 if bt else bc + 1
    ntc = (tc + 1) & 31 if step else tc
    t0, x1, x2 = 1 - t0, x1 ^ t0, x2 ^ t0
    bc, tc, tq = nbc, ntc, nq
chk(fall is not None and fall - 1675 == 1600, "high ровно 1600 клк (64 мкс)", str(fall))

print("== C6 UCF ==")
chk('NET "TRAP"       LOC = "P74";' in ucf, "UCF: NET TRAP P74")
chk("ВОСЕМЬ держателей '0' (RST7.5/6.5/5.5, INTR, HOLD, A16, A17," in ucf,
    "UCF: держателей ВОСЕМЬ")
chk("(P75, P76, P78, P79, P81, P95, P96," in ucf, "UCF: PGND-набор без P74")
chk("PGND == ровно {P75,P76,P78,P79,P81,P95,P96,P98}" in ucf, "UCF: чек-лист PGND 8 шт")
chk('NET "X1"         LOC = "P68";' in ucf and 'NET "X2"     LOC = "P69";' in ucf,
    "UCF: X1 P68 / X2 P69 на местах")

print("\nИТОГ: PASS %d, FAIL %d" % (pass_n, fail_n))
sys.exit(1 if fail_n else 0)
