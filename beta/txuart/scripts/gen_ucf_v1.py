#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_ucf_v1.py - генератор top_txuart.ucf (TXUART v1.0) из hdl/top_suart.ucf.

НОГИ НЕ МЕНЯЮТСЯ (все NET 1-в-1 с базой): TX P39, SOD P72, SID P73, RX P38,
PGND = 9 {P74,P75,P76,P78,P79,P81,P95,P96,P98} (rx_int НЕТ - P75 остаётся PGND).
Правки ТОЛЬКО в комментариях: титул TXUART, статус SOD (наблюдатель),
актуализация заметок GSR/clk (база v3.9.3, а не v3.4).

Выход: top_txuart_utf8.ucf (UTF8) + top_txuart.ucf (CP1251).
Запуск: python3 scripts/gen_ucf_v1.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ  = os.path.dirname(HERE)
SRC  = os.path.normpath(os.path.join(PRJ, "..", "..", "hdl", "top_suart.ucf"))
OUT_UTF8 = os.path.join(PRJ, "top_txuart_utf8.ucf")
OUT_CP   = os.path.join(PRJ, "top_txuart.ucf")

text = open(SRC, "rb").read().decode("cp1251")
n = 0

def rep(old, new, tag):
    global text, n
    k = text.count(old)
    assert k == 1, f"[{tag}]: якорь найден {k} раз (ожид. 1)"
    text = text.replace(old, new)
    n += 1
    print(f"  [{tag}]: OK")

# 1) титул
rep(
"""# top_suart.ucf — цоколевка U1 (XC95108, PQFP-100) для retro_PCLD_board
# Вариант SOFT-UART ТРАНЗИТЫ (Task 70-a, 2026-10-18); база top_nouart.ucf.""",
"""# top_txuart.ucf — цоколевка U1 (XC95108, PQFP-100) для retro_PCLD_board
# Вариант TXUART v1.0 - ИСКЛЮЧИТЕЛЬНО АППАРАТНЫЙ ПЕРЕДАТЧИК UART (директива
# владельца 11-8, база lowsize v3.9.3, beta/txuart); ноги = hdl/top_suart.ucf
# 1-в-1 (TX P39 / SOD P72 / SID P73 / RX P38, PGND 9 - rx_int НЕТ, P75 = PGND).""",
"T1")

# 2) статус SOD/RX
rep(
"""#  - SOD (P72) и RX (P38) теперь РЕАЛЬНЫЕ входы с нагрузкой (транзиты,
#    Task 70-a): RX -> SID (P73), SOD -> TX (P39). ЗАЗЕМЛЯТЬ НЕЛЬЗЯ:
#    P38/P72 — выходы CH340G/CPU соответственно.""",
"""#  - RX (P38) - РЕАЛЬНЫЙ вход с нагрузкой (транзит SID, Task 70-a).
#    SOD (P72) - вход-НАБЛЮДАТЕЛЬ БЕЗ нагрузки (транзит SOD->TX выпилен,
#    п.27 шапки): keep обязателен. ЗАЗЕМЛЯТЬ НЕЛЬЗЯ: P38/P72 — выходы
#    CH340G/CPU соответственно.""",
"T2")

# 3) GSR-примечание
rep(
"""# ПРИМЕЧАНИЕ GSR: все триггеры имеют синхронный сброс cpu_rst = RST|por_run
# (D-gating) — GSR НЕ используется""",
"""# ПРИМЕЧАНИЕ GSR (v3.9.3, п.18): сброс ЛОГИКИ - асинхронный по RST через
# СЕТЬ GSR (ожидаются строки «Signal 'RST' mapped onto global set/reset
# net GSR.» и «GSR : 1»; ранее был cpu_rst/D-gating — cpu_rst удалён)""",
"T3")

# 4) чек-лист .rpt
rep(
"""#    Keep User Location Constraints: ON; GCK3 = P29, GSR = P1; GSR НЕ
#    используется (сброс через D-gating, Task 25); MC меньше 108.""",
"""#    Keep User Location Constraints: ON; GCK3 = P29, GSR = P1; GSR : 1
#    (класс v3.9.3 п.18); MC 102-104 (прогноз п.30 шапки TXUART).""",
"T4")

# 5) clk-комментарий
rep(
"""NET "clk"  LOC = "P29";    # GCK3, цепь clk: измерено 25,00 МГц (Task 29-d) -> X1 = 25/4 = 6,25 МГц (v3.4, CLK_DIV=4) -> CPU 3,125 МГц""",
"""NET "clk"  LOC = "P29";    # GCK3, цепь clk: измерено 25,00 МГц (Task 29-d) -> X1 = 2x25/7 = 7,14 МГц (v3.9.2, счётчик mod-7) -> CPU 3,57 МГц""",
"T5")

# 6) хвостовой комментарий TIMESPEC (устаревшее про x1_n/toggle-ветку)
rep(
"""# 25 МГц на входе CPLD подтверждены осциллографом; HIGH 50% — запас
# по duty входного такта; в v3.4 делитель — toggle-цепочка (x1_n нет)""",
"""# 25 МГц на входе CPLD подтверждены осциллографом; HIGH 50% — запас
# по duty входного такта; в v3.9.2 делитель — счётчик mod-7 (x1_n NEGEDGE)""",
"T6")

assert text.count('NET "TX"  LOC = "P39"') == 1
assert text.count('NET "SOD" LOC = "P72"') == 1
assert text.count('NET "SID" LOC = "P73"') == 1
assert text.count('NET "RX"  LOC = "P38"') == 1

with open(OUT_UTF8, "w", encoding="utf-8", newline="") as f:
    f.write(text)
cp_bytes = text.encode("cp1251")
with open(OUT_CP, "wb") as f:
    f.write(cp_bytes)
assert open(OUT_CP, "rb").read().decode("cp1251") == text
print(f"gen_ucf_v1: {n} правок применено")
print(f"  {OUT_UTF8}")
print(f"  {OUT_CP} (CP1251, {len(cp_bytes)} байт) - round-trip OK")
