#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# gen_col_probe.py (clk10-63): построение ВАРИАНТОВ предложения коллеги
# «слить захват адреса с переходом IDLE->T1H» для пробной симуляции.
#   Вариант A (буквальное прочтение «T1H - чистое ожидание !ALE»):
#     ОБА захвата (addr_latch и bus_reg) переносятся в ветку перехода.
#   Вариант B (минимальное прочтение): переносится ТОЛЬКО addr_latch,
#     bus_reg остаётся сэмлироваться в T1H.
# Варианты НЕ являются версией 3.9.2 - это одноразовый пробник.
import io, os

SRC = "/home/z/my-project/CPLD-plus-8085/beta/hiclock/top_suart_por6_v391_utf8.v"
W = "/home/z/my-project/scripts/col_work"
os.makedirs(W, exist_ok=True)

base = io.open(SRC, encoding="utf-8").read()

CAP_BLOCK = """      // --- захват повторным сэмплированием: последний сэмпл валиден ---
      // v3: захват возможен только в T1H, т.е. ПОСЛЕ завершения WB
      // (структурно: из WB в T1H попадаешь только через IDLE) - adm.
      // addr_latch НЕ может перезаписаться посреди импульса (п.6 шапки).
      if (state == S_T1H && ALE) begin
        addr_latch <= A;                 // адрес стабилен весь T1
        if (!IOM) bus_reg <= D;          // данные памяти (доступ начался в начале T1)
      end
"""

IDLE_BR = "          S_IDLE: if (ALE) state <= S_T1H;\n"

def make(variant):
    t = base
    n = t.count(CAP_BLOCK)
    assert n == 1, "CAP_BLOCK найден %d раз" % n
    n = t.count(IDLE_BR)
    assert n == 1, "IDLE_BR найден %d раз" % n
    if variant == "A":      # полный перенос (T1H - чистое ожидание)
        t = t.replace(CAP_BLOCK, "")
        t = t.replace(IDLE_BR,
"""          S_IDLE: if (ALE) begin
            state      <= S_T1H;
            addr_latch <= A;               // ПРЕДЛОЖЕНИЕ КОЛЛЕГИ: захват в переходе
            if (!IOM) bus_reg <= D;        // (первый сэмпл вместо последнего)
          end
""")
    elif variant == "B":    # addr - в переход, bus_reg - остаётся в T1H
        t = t.replace(CAP_BLOCK,
"""      // ВАРИАНТ B ПРЕДЛОЖЕНИЯ КОЛЛЕГИ: addr_latch перенесён в переход,
      // bus_reg остаётся с повторным сэмплированием в T1H
      if (state == S_T1H && ALE) begin
        if (!IOM) bus_reg <= D;          // данные памяти (доступ начался в начале T1)
      end
""")
        t = t.replace(IDLE_BR,
"""          S_IDLE: if (ALE) begin
            state      <= S_T1H;
            addr_latch <= A;               // ПРЕДЛОЖЕНИЕ КОЛЛЕГИ: захват в переходе
          end
""")
    else:
        raise SystemExit("bad variant")
    t = t.replace("retro_pcld_top", "retro_pcld_top_col" + variant.lower())
    return t

for v in ("A", "B"):
    p = os.path.join(W, "col%s.v" % v)
    io.open(p, "w", encoding="utf-8").write(make(v))
    print("OK", p, len(make(v)), "байт")
