#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_ucf_v2.py - актуализация комментариев top_txuart.ucf под TXUART v2.0.

НОГИ НЕ МЕНЯЮТСЯ (72/72 LOC = hdl/top_suart.ucf 1-в-1, XC95144 PQ100
попиново идентичен XC95108 PQ100 - вердикт миграции 11-8). Правки -
ТОЛЬКО комментарии + TIMESPEC (25 -> 50 МГц: база v3.9.8-clear живёт на
входе 50 МГц, H1 без шунта; для CPLD TIMESPEC информационный, f_max
считает фиттер).

Правки (якоря, каждый РОВНО один раз):
  U0  шапка файла (v1.0 -> v2.0, XC95144, база v3.9.8-clear)
  U1  комментарий NET clk (50 МГц, кольцо)
  U2  примечание GSR (источник = cpu_rst, п.20/21)
  U3  комментарий NET X1 (7,14 МГц, кольцо)
  U4  комментарий NET RESET_IN (регистр reset_q, п.21)
  U5  секция soft-UART (RX/TX/SOD/SID) -> TXUART v2.0
  U6  строка чек-листа в шапке (MC 111-113/144, PGND 9)
  U7  тайминг-констрейнт (25 -> 50 МГц)

Выход: top_txuart_utf8.ucf (UTF8) + top_txuart.ucf (CP1251).
Запуск: python3 scripts/gen_ucf_v2.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ  = os.path.dirname(HERE)
SRC  = os.path.join(PRJ, "top_txuart_utf8.ucf")
OUT_UTF8 = SRC
OUT_CP   = os.path.join(PRJ, "top_txuart.ucf")

src = open(SRC, encoding="utf-8").read()
n_edits = 0

def rep(old, new, tag):
    global src, n_edits
    k = src.count(old)
    assert k == 1, f"U[{tag}]: якорь найден {k} раз (ожид. 1):\n---\n{old[:200]}\n---"
    src = src.replace(old, new)
    n_edits += 1
    print(f"  U[{tag}]: OK")

# ------------------------------------------------- U0: шапка
rep(
"""#=====================================================================
# top_txuart.ucf — цоколевка U1 (XC95108, PQFP-100) для retro_PCLD_board
# Вариант TXUART v1.0 - ИСКЛЮЧИТЕЛЬНО АППАРАТНЫЙ ПЕРЕДАТЧИК UART (директива
# владельца 11-8, база lowsize v3.9.3, beta/txuart); ноги = hdl/top_suart.ucf
# 1-в-1 (TX P39 / SOD P72 / SID P73 / RX P38, PGND 9 - rx_int НЕТ, P75 = PGND).
""",
"""#=====================================================================
# top_txuart.ucf — цоколевка U1 (XC95144-15PQ100C, PQFP-100) для retro_PCLD_board
# Вариант TXUART v2.0 - ИСКЛЮЧИТЕЛЬНО АППАРАТНЫЙ ПЕРЕДАТЧИК UART (директивы
# владельца 11-8 и 11-8веч «Берем дизайн beta\\lowsize 398_clear и переделываем
# txuart на основе него», база lowsize v3.9.8-clear, beta/txuart); ноги =
# hdl/top_suart.ucf 1-в-1 (TX P39 / SOD P72 / SID P73 / RX P38, PGND 9 -
# rx_int НЕТ, P75 = PGND). XC95144 PQ100 попиново 1-в-1 к XC95108 PQ100
# (вердикт миграции 11-8: BSDL-дифф 0 разногласий, даташиты DS066/DS067) -
# UCF БЕЗ ПРАВОК НОГ; в ISE-проекте сменить Device на xc95144-15pq100c.
""",
"U0")

# ------------------------------------------------- U1: NET clk
rep(
"""NET "clk"  LOC = "P29";    # GCK3, цепь clk: измерено 25,00 МГц (Task 29-d) -> X1 = 2x25/7 = 7,14 МГц (v3.9.2, счётчик mod-7) -> CPU 3,57 МГц
""",
"""NET "clk"  LOC = "P29";    # GCK3, цепь clk: 50 МГц (v3.9.8, H1 БЕЗ шунта - DIV=/2 генератора U7; с шунтом было 25,00, Task 29-d) -> кольцо r0..r6 -> X1 = 7,14 МГц (duty 1/7) -> CPU 3,57 МГц
""",
"U1")

# ------------------------------------------------- U2: примечание GSR
rep(
"""# ПРИМЕЧАНИЕ GSR (v3.9.3, п.18): сброс ЛОГИКИ - асинхронный по RST через
# СЕТЬ GSR (ожидаются строки «Signal 'RST' mapped onto global set/reset
# net GSR.» и «GSR : 1»; ранее был cpu_rst/D-gating — cpu_rst удалён). Проверить в отчёте фиттера (Task 25/68-f).
""",
"""# ПРИМЕЧАНИЕ GSR (v2.0 = база v3.9.8-clear п.18/20/21): сброс ЛОГИКИ и
# ЯДРА TXUART - асинхронный по cpu_rst = rst_press | por_run через СЕТЬ
# GSR (ожидаются «GSR : 1» или fallback PT-сбросов - класс п.25, на
# разбор); сырой RST (P1) входит ТОЛЬКО в синхронизатор rst_meta.
# Проверить в отчёте фиттера (Task 25/68-f, чек-лист п.32c шапки RTL).
""",
"U2")

# ------------------------------------------------- U3: NET X1
rep(
"""NET "X1"         LOC = "P68";  # cpu21, X1(1), 6,25 МГц = 25/4 (v3.4, CLK_DIV=4, декод-иммунный делитель); CPU = 3,125 МГц
""",
"""NET "X1"         LOC = "P68";  # cpu21, X1(1), 7,14 МГц = 50/7 (v3.9.8: КОЛЬЦО one-hot r0..r6 на clk 50, X1 = r0, duty 1/7); CPU = 3,57 МГц
""",
"U3")

# ------------------------------------------------- U4: NET RESET_IN
rep(
"""NET "RESET_IN"   LOC = "P84";  # cpu7,  RESET IN#(36) = ~(RST|POR), активный 0 по даташиту 8085A (Task 25)
""",
"""NET "RESET_IN"   LOC = "P84";  # cpu7,  RESET IN#(36) = регистр reset_q (п.21d базы: INIT=0 - CPU в сбросе с t=0; снятие чистым фронтом), активный 0 по даташиту 8085A (Task 25)
""",
"U4")

# ------------------------------------------------- U5: секция soft-UART
rep(
"""#---- soft-UART транзиты (Task 70-a) ----
NET "RX"  LOC = "P38";     # вход: U1.38 <- цепь платы «TX» (CH340G.TXD); транзит в SID; ЗАЗЕМЛЯТЬ НЕЛЬЗЯ (выход CH340G)!
NET "TX"  LOC = "P39";     # выход: U1.39 -> цепь платы «RX» (CH340G.RXD); TX = SOD (транзит передачи)
NET "SOD" LOC = "P72";     # вход: cpu18, SOD(4) — CPU.SOD; транзит в TX; теперь с нагрузкой (INP)
NET "SID" LOC = "P73";     # выход: cpu17, SID(5) — CPU.SID; транзит RX; РАНЕЕ PGND (до Task 70-a) — теперь ВЫХОД CPLD!
""",
"""#---- UART: RX-транзит + TXUART (Task 70-a; v2.0 п.27) ----
NET "RX"  LOC = "P38";     # вход: U1.38 <- цепь платы «TX» (CH340G.TXD); транзит в SID; ЗАЗЕМЛЯТЬ НЕЛЬЗЯ (выход CH340G)!
NET "TX"  LOC = "P39";     # выход: U1.39 -> цепь платы «RX» (CH340G.RXD); TX = shreg[0] (ядро TXUART: OUT 04h, 1 562 500 8N1)
NET "SOD" LOC = "P72";     # вход: cpu18, SOD(4) — CPU.SOD; транзит УДАЛЁН (п.27) - наблюдатель БЕЗ нагрузки, keep обязателен; ЗАЗЕМЛЯТЬ НЕЛЬЗЯ (выход CPU)!
NET "SID" LOC = "P73";     # выход: cpu17, SID(5) — CPU.SID; транзит RX; РАНЕЕ PGND (до Task 70-a) — теперь ВЫХОД CPLD!
""",
"U5")

# ------------------------------------------------- U6: строка чек-листа шапки
rep(
"""#  - чек-лист .rpt: PGND == ровно {P74,P75,P76,P78,P79,P81,P95,P96,P98}
#    (9 шт!); входы на местах (INP), включая SOD P72 и RX P38;
#    Keep User Location Constraints: ON; GCK3 = P29, GSR = P1; GSR : 1
#    (класс v3.9.3 п.18); MC 102-104 (прогноз п.30 шапки TXUART).
""",
"""#  - чек-лист .rpt: PGND == ровно {P74,P75,P76,P78,P79,P81,P95,P96,P98}
#    (9 шт!); входы на местах (INP), включая SOD P72 (наблюдатель) и
#    RX P38; Keep User Location Constraints: ON; GCK3 = P29, GSR = P1;
#    GSR : 1 или fallback (класс п.25); MC 111-113/144 (прогноз п.31
#    шапки TXUART v2.0; УСТРОЙСТВО xc95144-15pq100c!); кольцо r0..r6 в
#    FB - п.32d чек-листа.
""",
"U6")

# ------------------------------------------------- U7: тайминг-констрейнт
rep(
"""#---- тайминг-констрейнт (владелец, Constraints Editor 2026-10-21) ----
# 25 МГц на входе CPLD подтверждены осциллографом; HIGH 50% — запас
# по duty входного такта; в v3.9.2 делитель — счётчик mod-7 (x1_n NEGEDGE)
#Created by Constraints Editor (xc95108-pq100-15) - 2026/10/21
NET "clk" TNM_NET = clk;
TIMESPEC TS_clk = PERIOD "clk" 25 MHz HIGH 50%;
""",
"""#---- тайминг-констрейнт (v2.0: вход 50 МГц, H1 без шунта - база v3.9.8) ----
# 50 МГц на входе CPLD (H1 БЕЗ шунта, DIV=/2 U7; ранее с шунтом было
# 25,00 МГц - Task 29-d); HIGH 50% - запас по duty входного такта;
# узел - кольцо r0..r6 на clk 50 (v3.9.8, п.22/23); для CPLD TIMESPEC
# информационный - f_max считает фиттер (чек-лист п.32g: узел 50 МГц и
# логика 25 МГц должны закрыться)
#Created by Constraints Editor (xc95108-pq100-15) - 2026/10/21; v2.0: период 50 МГц, устройство xc95144
NET "clk" TNM_NET = clk;
TIMESPEC TS_clk = PERIOD "clk" 50 MHz HIGH 50%;
""",
"U7")

# ------------------------------------------------------------- запись
utf8_text = src
with open(OUT_UTF8, "w", encoding="utf-8", newline="") as f:
    f.write(utf8_text)
try:
    cp_bytes = utf8_text.encode("cp1251")
except UnicodeEncodeError as e:
    print(f"ОШИБКА CP1251: {e}")
    sys.exit(1)
with open(OUT_CP, "wb") as f:
    f.write(cp_bytes)
assert open(OUT_CP, "rb").read().decode("cp1251") == utf8_text
# контроль: все LOC нетронуты
import re
locs = re.findall(r'LOC\s*=\s*"(\w+)"', utf8_text)
print(f"gen_ucf_v2: {n_edits} правок применено, LOC-констрейнтов: {len(locs)}")
print(f"  {OUT_UTF8}")
print(f"  {OUT_CP} (CP1251, {len(cp_bytes)} байт) - round-trip OK")
