#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_v25.py - верификатор txuart v2.5 (D(x2_q) в И-ИЛИ форме).

Проверки:
  C0  файлы линии (v2.3/v2.4 - архивы), hex прошивки;
  C1  CP1251 round-trip;
  C2  заголовок v2.5 (урок аудита фита v2.4);
  C3  узел в КОДЕ: И-ИЛИ форма D(x2_q), атрибуты, INIT, assigns, НЕТ
      XOR-записи, НЕТ s0..s3, НЕТ декодов равенства в узле;
  C4  диф КОДА v2.5 vs v2.4 = РОВНО ОДНА строка (x2_q D-форма);
  C5  живые документы обновлены;
  C6  UCF не тронут; аудитор отчёта на месте.
"""
import io
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

V25 = os.path.join(ROOT, "top_txuart_por6_v25.v")
V25U = os.path.join(ROOT, "top_txuart_por6_v25_utf8.v")
V24 = os.path.join(ROOT, "top_txuart_por6_v24.v")
V24U = os.path.join(ROOT, "top_txuart_por6_v24_utf8.v")

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


raw25 = io.open(V25, "rb").read()
u25 = io.open(V25U, encoding="utf-8").read()
u24 = io.open(V24U, encoding="utf-8").read()

print("== C0 файлы линии ==")
for p in (V24, V24U, os.path.join(ROOT, "top_txuart.ucf"),
          os.path.join(ROOT, "rom", "uart_tx_test.hex"),
          os.path.join(ROOT, "scripts", "audit_fit_node.py")):
    chk(os.path.exists(p), "exists %s" % os.path.basename(p))
hexf = os.path.join(ROOT, "rom", "uart_tx_test.hex")
if os.path.exists(hexf):
    chk(len(io.open(hexf, "rb").read()) == 2144, "hex: 2144 байт")

print("== C1 CP1251 round-trip ==")
chk(raw25.decode("cp1251") == u25, "v25.v (cp1251) == v25_utf8.v (utf8)")

print("== C2 заголовок v2.5 ==")
for pat in ("// top_txuart.v v2.5 -",
            "v2.5 (урок АУДИТА ФИТА v2.4, 11-14 1:51PM)",
            "X2_D = t0_q XOR X1 БЕЗ NOT",
            "КЛАСС: «потеря инверсии»",
            "самовыравнивается из ЛЮБОГО кода",
            "1:51PM): Successful, 101/108"):
    chk(pat in u25, "заголовок: %r" % pat[:52])

print("== C3 узел в коде ==")
code = "\n".join((l.split("//")[0] if "//" in l else l) for l in u25.split("\n"))
ncode_s = "\n".join(re.sub(r"\s+", " ", c.strip()) for c in code.split("\n") if c.strip())
chk("(x1_q & t0_q) | (~x1_q & ~t0_q)" in ncode_s, "код: И-ИЛИ форма D(x2_q)")
chk("x2_q <= ~(x1_q ^ t0_q)" not in ncode_s, "в коде НЕТ XOR-записи D(x2_q)")
chk(len(re.findall(r'equivalent_register_removal = "no"', u25)) == 3,
    "атрибут equivalent_register_removal ровно 3")
chk('dont_touch = "true"' in u25, "атрибут dont_touch на x2_q")
for pat in ("reg t0_q = 1'b0;", "reg x1_q = 1'b1;", "reg x2_q = 1'b0;",
            "t0_q <= ~t0_q;", "if (t0_q) x1_q <= ~x1_q;",
            "assign X1 = x1_q;", "assign X2 = x2_q;",
            "assign por_ce = ~t0_q & ~x1_q;"):
    chk(pat in ncode_s, "код: %r" % pat)
for pat in (r"\bs0\b", r"\bs1\b", r"\bs2\b", r"\bs3\b"):
    chk(re.search(pat, ncode_s) is None, "в коде НЕТ: %s" % pat)
chk(re.search(r"(t0_q|x1_q|x2_q)\s*==", ncode_s) is None,
    "в узле НЕТ декодов равенства")

print("== C4 диф кода v2.5 vs v2.4 = ровно одна строка ==")
c24, c25 = Counter(code_lines(u24)), Counter(code_lines(u25))
removed = list((c24 - c25).elements())
added = list((c25 - c24).elements())
chk(removed == ["x2_q <= ~(x1_q ^ t0_q);"],
    "удалена ровно 1 строка (XOR-форма)", str(removed))
chk(added == ["x2_q <= (x1_q & t0_q) | (~x1_q & ~t0_q);"],
    "добавлена ровно 1 строка (И-ИЛИ форма)", str(added))

print("== C5 живые документы ==")
for pat in ("ФОРМА И-ИЛИ ОБЯЗАТЕЛЬНА (урок фита v2.4",
            "XOR-форма без NOT = НЕ ШИТЬ",
            "РЕЗЕРВ ПОСЛЕ ФИТА v2.4: 108-101 = 7",
            "резерв под тик: 7 МЦ, 7 вх.ФБ"):
    chk(pat in u25, "док: %r" % pat[:52])

print("== C6 UCF ==")
ucf = io.open(os.path.join(ROOT, "top_txuart.ucf"), "r", encoding="cp1251").read()
chk('NET "X1"         LOC = "P68";' in ucf, "UCF: X1 P68 на месте")
chk('NET "X2"     LOC = "P69";' in ucf, "UCF: X2 P69 на месте")

print("\nИТОГ: PASS %d, FAIL %d" % (pass_n, fail_n))
sys.exit(1 if fail_n else 0)
