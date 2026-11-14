#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_v26.py - верификатор txuart v2.6 (x2_q = T-триггер, T=t0_q).

Проверки:
  C0  файлы линии; hex прошивки;
  C1  CP1251 round-trip;
  C2  заголовок v2.6 (урок фита v2.5: D-форма неаудитируема);
  C3  узел в КОДЕ: T-форма x2_q, НЕТ D-формы, атрибуты, INIT, assigns,
      НЕТ s0..s3, НЕТ декодов равенства в узле;
  C4  диф КОДА v2.6 vs v2.5 = РОВНО ОДНА строка (T-форма);
  C5  живые документы обновлены;
  C6  UCF не тронут; аудитор отчёта на месте; сим-цикл T-формы.
"""
import io
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

V26 = os.path.join(ROOT, "top_txuart_por6_v26.v")
V26U = os.path.join(ROOT, "top_txuart_por6_v26_utf8.v")
V25 = os.path.join(ROOT, "top_txuart_por6_v25.v")
V25U = os.path.join(ROOT, "top_txuart_por6_v25_utf8.v")

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


raw26 = io.open(V26, "rb").read()
u26 = io.open(V26U, encoding="utf-8").read()
u25 = io.open(V25U, encoding="utf-8").read()

print("== C0 файлы линии ==")
for p in (V25, V25U, os.path.join(ROOT, "top_txuart.ucf"),
          os.path.join(ROOT, "rom", "uart_tx_test.hex"),
          os.path.join(ROOT, "scripts", "audit_fit_node.py"),
          os.path.join(ROOT, "scripts", "gen_v26.py")):
    chk(os.path.exists(p), "exists %s" % os.path.basename(p))
hexf = os.path.join(ROOT, "rom", "uart_tx_test.hex")
if os.path.exists(hexf):
    chk(len(io.open(hexf, "rb").read()) == 2144, "hex: 2144 байт")

print("== C1 CP1251 round-trip ==")
chk(raw26.decode("cp1251") == u26, "v26.v (cp1251) == v26_utf8.v (utf8)")

print("== C2 заголовок v2.6 ==")
for pat in ("// top_txuart.v v2.6 -",
            "v2.6 (урок ФИТА v2.5, 11-14 6:27PM)",
            "ТОЛЬКО строка даты (байт-в-байт)",
            "D-форма X2 в этом тулчейне НЕАУДИТИРУЕМА В ПРИНЦИПЕ",
            "X2 ^ X1 ИНВАРИАНТ",
            "(0,1,0)->", "(1,1,0)->(0,0,1)->(1,0,1)"):
    chk(pat in u26, "заголовок: %r" % pat[:52])

print("== C3 узел в коде ==")
code = "\n".join((l.split("//")[0] if "//" in l else l) for l in u26.split("\n"))
ncode_s = "\n".join(re.sub(r"\s+", " ", c.strip()) for c in code.split("\n") if c.strip())
chk("if (t0_q) x2_q <= ~x2_q;" in ncode_s, "код: T-форма x2_q (T = t0_q)")
chk("(x1_q & t0_q) | (~x1_q & ~t0_q)" not in ncode_s, "в коде НЕТ И-ИЛИ D-формы")
chk("x2_q <= ~(x1_q ^ t0_q)" not in ncode_s, "в коде НЕТ XOR D-формы")
chk(len(re.findall(r'equivalent_register_removal = "no"', u26)) == 3,
    "атрибут equivalent_register_removal ровно 3")
chk('dont_touch = "true"' in u26, "атрибут dont_touch на x2_q")
for pat in ("reg t0_q = 1'b0;", "reg x1_q = 1'b1;", "reg x2_q = 1'b0;",
            "t0_q <= ~t0_q;", "if (t0_q) x1_q <= ~x1_q;",
            "assign X1 = x1_q;", "assign X2 = x2_q;",
            "assign por_ce = ~t0_q & ~x1_q;"):
    chk(pat in ncode_s, "код: %r" % pat)
for pat in (r"\bs0\b", r"\bs1\b", r"\bs2\b", r"\bs3\b"):
    chk(re.search(pat, ncode_s) is None, "в коде НЕТ: %s" % pat)
chk(re.search(r"(t0_q|x1_q|x2_q)\s*==", ncode_s) is None,
    "в узле НЕТ декодов равенства")

print("== C4 диф кода v2.6 vs v2.5 = ровно одна строка ==")
c25, c26 = Counter(code_lines(u25)), Counter(code_lines(u26))
removed = list((c25 - c26).elements())
added = list((c26 - c25).elements())
chk(removed == ["x2_q <= (x1_q & t0_q) | (~x1_q & ~t0_q);"],
    "удалена ровно 1 строка (И-ИЛИ D-форма)", str(removed))
chk(added == ["if (t0_q) x2_q <= ~x2_q;"],
    "добавлена ровно 1 строка (T-форма)", str(added))

print("== C5 живые документы ==")
for pat in ("T-ТРИГГЕР,",
            "X2 ^ X1 = const = 0^1 = 1 при конфиг",
            "same-D слияние с x1_q невозможно: INIT различны",
            "печатный FDCPE_X2 = НЕ ШИТЬ",
            "x2_q = T-триггер (T=t0_q, INIT=RESET);",
            "РЕЗЕРВ: 7 МЦ / 7 вх.ФБ / ~200 ПТ (ПТ у X2: 2 -> 0-1)"):
    chk(pat in u26, "док: %r" % pat[:52])

print("== C6 UCF + аудитор + сим-цикл ==")
ucf = io.open(os.path.join(ROOT, "top_txuart.ucf"), "r", encoding="cp1251").read()
chk('NET "X1"         LOC = "P68";' in ucf, "UCF: X1 P68 на месте")
chk('NET "X2"     LOC = "P69";' in ucf, "UCF: X2 P69 на месте")
aud = io.open(os.path.join(HERE, "audit_fit_node.py"), encoding="utf-8").read()
chk("FTCPE_X2" in aud and "t_form" in aud, "аудитор знает T-форму")
t0, x1, x2 = 0, 1, 0
cycle = []
for _ in range(8):
    cycle.append((t0, x1, x2))
    t0, x1, x2 = 1 - t0, x1 ^ t0, x2 ^ t0
chk(all(x2 == (1 - x1) for _, x1, x2 in cycle), "сим: X2 = ~X1 в каждом такте")
chk([s[1] for s in cycle[:4]] == [1, 1, 0, 0] and cycle[4] == cycle[0],
    "сим: период X1 = 4, цикл (0,1,0)->(1,1,0)->(0,0,1)->(1,0,1)")

print("\nИТОГ: PASS %d, FAIL %d" % (pass_n, fail_n))
sys.exit(1 if fail_n else 0)
