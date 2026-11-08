#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_ucf_v22.py - актуализация UCF для txuart v2.2 (узел /4 на 25 МГц,
шунт H1 ОБЯЗАТЕЛЕН; директива владельца 11-9). НОГИ НЕ МЕНЯЮТСЯ (1-в-1
hdl/top_suart.ucf). Правки - только комментарии/TIMESPEC; LOC не тронуты
(проверяется пост-проверкой). CP1251 round-trip."""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "top_txuart.ucf")          # CP1251, правим на месте
SRC_U = os.path.join(ROOT, "top_txuart_utf8.ucf")   # двойник

raw = io.open(SRC, "rb").read()
text = raw.decode("cp1251")

n = 0


def sub(old, new):
    global text, n
    c = text.count(old)
    assert c == 1, "ANCHOR FAIL (count=%d): %r" % (c, old[:100])
    text = text.replace(old, new)
    n += 1


sub('# top_txuart.ucf — цоколевка U1 (XC95144-15PQ100C, PQFP-100) для retro_PCLD_board\n# Вариант TXUART v2.0 - ИСКЛЮЧИТЕЛЬНО АППАРАТНЫЙ ПЕРЕДАТЧИК UART (директивы\n# владельца 11-8 и 11-8веч «Берем дизайн beta\\lowsize 398_clear и переделываем\n# txuart на основе него», база lowsize v3.9.8-clear, beta/txuart); ноги =',
    '# top_txuart.ucf — цоколевка U1 (XC95108-15PQ100C, PQFP-100) для retro_PCLD_board\n# Вариант TXUART v2.2 - ИСКЛЮЧИТЕЛЬНО АППАРАТНЫЙ ПЕРЕДАТЧИК UART (директивы\n# владельца 11-8/11-8веч и 11-9 «уйти на более простой делитель тактовой»:\n# узел /4 на 25 МГц, beta/txuart); НОГИ НЕ МЕНЯЛИСЬ (всё как в v2.0/v2.1);\n# ноги =')
sub('# (вердикт миграции 11-8: BSDL-дифф 0 разногласий, даташиты DS066/DS067) -\n# UCF БЕЗ ПРАВОК НОГ; в ISE-проекте сменить Device на xc95144-15pq100c.',
    '# (вердикт миграции 11-8: BSDL-дифф 0 разногласий, даташиты DS066/DS067) -\n# UCF БЕЗ ПРАВОК НОГ; в ISE-проекте Device = xc95108-15pq100c (v2.2).')
sub('NET "clk"  LOC = "P29";    # GCK3, цепь clk: 50 МГц (v3.9.8, H1 БЕЗ шунта - DIV=/2 генератора U7; с шунтом было 25,00, Task 29-d) -> кольцо r0..r6 -> X1 = 7,14 МГц (duty 1/7) -> CPU 3,57 МГц',
    'NET "clk"  LOC = "P29";    # GCK3, цепь clk: 25 МГц (v2.2, H1 С ШУНТОМ - DIV=/4 генератора U7; ОБЯЗАТЕЛЕН - БЕЗ шунта 50 МГц ЗАПРЕЩЕНО) -> кольцо s0..s3 -> X1 = 6,25 МГц (duty 1/4) -> CPU 3,125 МГц')
sub('NET "X1"         LOC = "P68";  # cpu21, X1(1), 7,14 МГц = 50/7 (v3.9.8: КОЛЬЦО one-hot r0..r6 на clk 50, X1 = r0, duty 1/7); CPU = 3,57 МГц',
    'NET "X1"         LOC = "P68";  # cpu21, X1(1), 6,25 МГц = 25/4 (v2.2: КОЛЬЦО one-hot s0..s3 на clk 25, X1 = s0, duty 1/4); CPU = 3,125 МГц')
sub('#---- тайминг-констрейнт (v2.0: вход 50 МГц, H1 без шунта - база v3.9.8) ----\n# 50 МГц на входе CPLD (H1 БЕЗ шунта, DIV=/2 U7; ранее с шунтом было',
    '#---- тайминг-констрейнт (v2.2: вход 25 МГц, H1 С ШУНТОМ) ----\n# 25 МГц на входе CPLD (H1 С ШУНТОМ, DIV=/4 U7; ОБЯЗАТЕЛЬНО - БЕЗ шунта')
sub('# узел - кольцо r0..r6 на clk 50 (v3.9.8, п.22/23); для CPLD TIMESPEC\n# информационный - f_max считает фиттер (чек-лист п.32g: узел 50 МГц и\n# логика 25 МГц должны закрыться)\n#Created by Constraints Editor (xc95108-pq100-15) - 2026/10/21; v2.0: период 50 МГц, устройство xc95144',
    '# логика - ОДИН домен clk 25 МГц (v2.2, п.23/34); для CPLD TIMESPEC\n# информационный - f_max считает фиттер (чек-лист п.32g: логика 25 МГц\n# должна закрыться)\n#Created by Constraints Editor (xc95108-pq100-15) - 2026/10/21; v2.2: период 25 МГц, устройство xc95108')
sub('TIMESPEC TS_clk = PERIOD "clk" 50 MHz HIGH 50%;',
    'TIMESPEC TS_clk = PERIOD "clk" 25 MHz HIGH 50%;')

# НОГИ НЕ ТРОНУТЫ: LOC-набор 1-в-1 с исходником
locs_src = re.findall(r'LOC\s*=\s*"([^"]+)"', raw.decode("cp1251"))
locs_new = re.findall(r'LOC\s*=\s*"([^"]+)"', text)
assert locs_src == locs_new, "LOC CHANGED!"

b = text.encode("cp1251")
io.open(SRC, "wb").write(b)
io.open(SRC_U, "w", encoding="utf-8", newline="\n").write(text)
back = io.open(SRC, "rb").read().decode("cp1251")
assert back == text
print("gen_ucf_v22: OK - %d правок, LOC %d шт без изменений" % (n, len(locs_new)))
