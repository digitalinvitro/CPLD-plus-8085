#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_v24.py - верификатор txuart v2.4 (узел: ДЕЛИТЕЛЬ владельца 3 FF).

Проверки:
  C0  файлы линии на месте (v2.3 - архив линии, не тронут), hex прошивки;
  C1  CP1251 round-trip: v24.v декодируется в точность в v24_utf8.v;
  C2  заголовок v2.4: блок узла, прогноз 100-102, п.10 в ред. v2.4;
  C3  узел в КОДЕ: ровно 3 регистра t0_q/x1_q/x2_q с атрибутами, D-формы,
      INIT, assigns; идентификаторов s0..s3 в коде НЕТ; декодов равенства
      в узле НЕТ (класс п.9);
  C4  диф КОДА v2.4 vs v2.3 = РОВНО узел (мультимножества удалённых и
      добавленных строк совпадают с ожидаемыми, всё остальное 1-в-1);
  C5  живые документы обновлены (шапка, п.29, бюджет 101, чек-листы
      d/e/h/i, приёмка, Equations, однолитеральный БРАК D(x2));
  C6  UCF не тронут.
"""
import io
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

V24 = os.path.join(ROOT, "top_txuart_por6_v24.v")
V24U = os.path.join(ROOT, "top_txuart_por6_v24_utf8.v")
V23 = os.path.join(ROOT, "top_txuart_por6_v23.v")
V23U = os.path.join(ROOT, "top_txuart_por6_v23_utf8.v")

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


raw24 = io.open(V24, "rb").read()
u24 = io.open(V24U, encoding="utf-8").read()
u23 = io.open(V23, "rb").read().decode("cp1251")  # utf8-двойник v23 удалён при чистке папки

print("== C0 файлы линии ==")
for p in (V23, os.path.join(ROOT, "top_txuart.ucf"),
          os.path.join(ROOT, "rom", "uart_tx_test.hex")):
    chk(os.path.exists(p), "exists %s" % os.path.basename(p))
hexf = os.path.join(ROOT, "rom", "uart_tx_test.hex")
if os.path.exists(hexf):
    chk(len(io.open(hexf, "rb").read()) == 2144, "hex: 2144 байт")

print("== C1 CP1251 round-trip ==")
chk(raw24.decode("cp1251") == u24, "v24.v (cp1251) == v24_utf8.v (utf8)")

print("== C2 заголовок v2.4 ==")
for pat in ("// top_txuart.v v2.4 -",
            "ДЕЛИТЕЛЬ владельца 3 FF (t0_q/x1_q/x2_q)",
            "п.10 (X2 «регистр в фазе» - ПЕРЕФОРМУЛИРОВАН в v2.4)",
            "БУДУЩИЙ комплемент x1_q",
            "ГЕЙТ ФИТА: в .rpt D(x2_q) = 2 ПТ",
            "Прогноз фита v2.4: 103 (факт fit3) - 2 = 101 наивно, ожидание",
            "в v2.4 ТИКА НЕТ - только делитель"):
    chk(pat in u24, "заголовок: %r" % pat[:52])

print("== C3 узел в коде ==")
code = "\n".join((l.split("//")[0] if "//" in l else l) for l in u24.split("\n"))
ncode = [re.sub(r"\s+", " ", c.strip()) for c in code.split("\n") if c.strip()]
ncode_s = "\n".join(ncode)
chk(len(re.findall(r'equivalent_register_removal = "no"', u24)) == 3,
    "атрибут equivalent_register_removal ровно 3 (t0/x1/x2)")
chk('dont_touch = "true"' in u24, "атрибут dont_touch на x2_q")
for pat in ("reg t0_q = 1'b0;", "reg x1_q = 1'b1;", "reg x2_q = 1'b0;",
            "t0_q <= ~t0_q;", "if (t0_q) x1_q <= ~x1_q;",
            "x2_q <= ~(x1_q ^ t0_q);",
            "assign X1 = x1_q;", "assign X2 = x2_q;",
            "assign por_ce = ~t0_q & ~x1_q;",
            "if (CLK_DIV == 4 && CLK_HALF == 1) begin : g_div4"):
    chk(pat in ncode_s, "код: %r" % pat)
for pat in (r"\bs0\b", r"\bs1\b", r"\bs2\b", r"\bs3\b", r"\bkill\b",
            r"NOR4", r"por_ce = s0"):
    chk(re.search(pat, ncode_s) is None, "в коде НЕТ: %s" % pat)
chk(re.search(r"(t0_q|x1_q|x2_q)\s*==", ncode_s) is None,
    "в узле НЕТ декодов равенства (t0/x1/x2 ==)")

print("== C4 диф кода v2.4 vs v2.3 = ровно узел ==")
c23, c24 = Counter(code_lines(u23)), Counter(code_lines(u24))
removed = list((c23 - c24).elements())
added = list((c24 - c23).elements())
exp_removed = ["reg s0 = 1'b1;", "reg s1 = 1'b0;", "reg s2 = 1'b0;", "reg s3 = 1'b0;",
               "s0 <= (s3 & ~s0 & ~s1 & ~s2) | (~s0 & ~s1 & ~s2 & ~s3);",
               "s1 <= s0 & ~s1 & ~s2 & ~s3;",
               "s2 <= s1 & ~s2 & ~s3 & ~s0;",
               "s3 <= s2 & ~s3 & ~s0 & ~s1;",
               "assign X1 = s0;",
               "assign X2 = s1 | s2 | s3;",
               "assign por_ce = s0;"]
exp_added = ['(* keep = "true", equivalent_register_removal = "no" *)',
             '(* keep = "true", equivalent_register_removal = "no" *)',
             '(* keep = "true", equivalent_register_removal = "no", dont_touch = "true" *)',
             "reg t0_q = 1'b0;", "reg x1_q = 1'b1;", "reg x2_q = 1'b0;",
             "t0_q <= ~t0_q;", "if (t0_q) x1_q <= ~x1_q;",
             "x2_q <= ~(x1_q ^ t0_q);",
             "assign X1 = x1_q;", "assign X2 = x2_q;",
             "assign por_ce = ~t0_q & ~x1_q;"]
chk(Counter(removed) == Counter(exp_removed),
    "удалено ровно 11 строк узла-кольца", str(removed))
chk(Counter(added) == Counter(exp_added),
    "добавлено ровно 12 строк делителя", str(added))

print("== C5 живые документы ==")
for pat in ("п.29 СБРОС/ДОМЕНЫ (v2.4 - ОДИН домен 25 МГц): узел (делитель",
            "ДЕЛИТЕЛЬ на месте (v2.4): РОВНО 3 регистра",
            "t0_q.D = NOT t0_q",
            "x2_q.D = t0_q AND x1_q OR NOT t0_q AND NOT x1_q",
            "por_ce = NOT t0_q AND NOT x1_q",
            "Узел тактирования v2.4 (директива владельца 11-14",
            "п.29 СБРОС/ДОМЕНЫ"):
    chk(pat in u24, "док: %r" % pat[:52])
chk(u24.count("high 80 / low 80") == 5, "duty 1/2 в 5 местах (i/e/приёмка/порт/узел)")
chk(u24.count("ОДНОЛИТЕРАЛЬНАЯ") >= 3, "однолитеральный БРАК D(x2) - в 3+ местах")
chk("high 40 / low 120" not in u24.split("// ЛИНИЯ beta/txuart")[0].split("// v2.4")[1]
    if "// v2.4" in u24 else False, "в блоке v2.4 шапки нет старой duty")

print("== C6 UCF ==")
ucf = io.open(os.path.join(ROOT, "top_txuart.ucf"), "r", encoding="cp1251").read()
chk('NET "X1"         LOC = "P68";' in ucf, "UCF: X1 P68 на месте")
chk('NET "X2"     LOC = "P69";' in ucf, "UCF: X2 P69 на месте")
chk('LOC = "P29"' in ucf and 'LOC = "P1"' in ucf, "UCF: clk GCK3 / RST P1 на месте")

print("\nИТОГ: PASS %d, FAIL %d" % (pass_n, fail_n))
sys.exit(1 if fail_n else 0)
