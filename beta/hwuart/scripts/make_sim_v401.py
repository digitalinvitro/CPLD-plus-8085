#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_sim_v401.py — адаптер симов v4.0.0 -> v4.0.1 (линия beta/hwuart, 2026-11-05).

Создаёт:
  1) sim_hwuart_v401.py из sim_hwuart_v400.py — дельта М1 (п.27 шапки RTL):
     por_sh = 0xF (4 бита), строб por_ce = x1_n (1 импульс за период cnt
     280 нс вместо пары декодов (cnt==1)|(cnt==6)), сдвиг & 0xF; С1 переверен
     (POR 26 тиков модели = 1040 нс >= нормы 840; в v4.0.0 было 29).
     ВСЁ ОСТАЛЬНОЕ (GSR, ядро UART, сценарии С2-С9) - байт-в-байт v4.0.0.
  2) tb_hwuart_v401.v из tb_hwuart_v400.v - тестбенч владельцу (iverilog):
     переименование версий + комментарий POR (~1020-1040 нс, 4 сдвига).

Запуск: python3 scripts/make_sim_v401.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

SIM_SRC = os.path.join(HERE, 'sim_hwuart_v400.py')
SIM_OUT = os.path.join(HERE, 'sim_hwuart_v401.py')
TB_SRC = os.path.join(HERE, '..', 'tb_hwuart_v400.v')
TB_OUT = os.path.join(HERE, '..', 'tb_hwuart_v401.v')

# ------------------------------------------------------------ sim-модель
EDITS = []

# E1. Шапка docstring.
EDITS.append((
'"""sim_hwuart_v400.py - цикл-точная модель top_hwuart_por6_v400 (v4.0.0, линия beta/hwuart).',
'"""sim_hwuart_v401.py - цикл-точная модель top_hwuart_por6_v401 (v4.0.1, линия beta/hwuart).',
"шапка docstring"))

# E2. Примечание М1 в docstring.
EDITS.append((
"База v3.9.3 (делитель mod-7, POR, FSM шины v3, порты 00-03h) - бит-в-бит;\n"
"ядро UART п.26 - полудуплекс (общие shreg/bit_cnt/baud_cnt).\n",
"База v4.0.0 (= lowsize v3.9.3: делитель mod-7, FSM шины v3, порты 00-03h)\n"
"бит-в-бит; ядро UART п.26 - полудуплекс (общие shreg/bit_cnt/baud_cnt).\n"
"v4.0.1 = v4.0.0 + М1 (п.27 шапки RTL, из lowsize v3.9.4): POR-счётчик 8->4,\n"
"строб por_ce = x1_n - 1 импульс за период cnt 280 нс (было (cnt==1)|(cnt==6),\n"
"2 строба); POR = 4 x 280 = 1120 нс >= нормы 840 нс (запас 1,33x).\n",
"примечание М1"))

# E3. Запуск.
EDITS.append((
"Запуск: python3 scripts/sim_hwuart_v400.py  (пути от папки скрипта)",
"Запуск: python3 scripts/sim_hwuart_v401.py  (пути от папки скрипта)",
"строка запуска"))

# E4. Docstring класса.
EDITS.append((
'"""Цикл-точная модель retro_pcld_top v4.0.0."""',
'"""Цикл-точная модель retro_pcld_top v4.0.1."""',
"docstring класса"))

# E5. Инициализация por_sh.
EDITS.append((
"        self.por_sh = 0xFF; self.por_run = 1",
"        self.por_sh = 0xF; self.por_run = 1   # v4.0.1 (М1): 4 бита, Init=F",
"инициализация por_sh"))

# E6. Строб por_ce = x1_n (сэмпл по posedge значения x1_n, выставленного
# на negedge ПРЕДЫДУЩЕГО тика: x1_n=1 в [140,180) каждого периода 280 нс).
EDITS.append((
"    def por_ce(self):    return 1 if (self.cnt == 1 or self.cnt == 6) else 0",
"    def por_ce(self):    return self.x1_n   # v4.0.1 (М1): строб x1_n",
"строб por_ce"))

# E7. Сдвиг 4 бита.
EDITS.append((
"                nxt['por_sh'] = (self.por_sh >> 1) & 0xFF",
"                nxt['por_sh'] = (self.por_sh >> 1) & 0xF",
"сдвиг por_sh"))

# E8. С1: момент снятия POR (4 строба с шагом 7 тиков: сдвиги на тиках
# 4, 11, 18, 25; por_run падает на такт после 4-го сдвига -> тик 26).
EDITS.append((
'    s.chk(por_fell is not None and 25 <= por_fell <= 32,\n'
'          f"С1: POR снялся на тике {por_fell} (ожид. 26-29, норма >=21)")',
'    s.chk(por_fell is not None and 25 <= por_fell <= 27,\n'
'          f"С1: POR снялся на тике {por_fell} (ожид. 26: 4 строба x 280 нс '
'= 1040 нс от INIT, норма >=21 = 840 нс; в v4.0.0 было 29)")',
"С1 POR"))


def main():
    src = io.open(SIM_SRC, encoding='utf-8').read()
    s = src
    for old, new, tag in EDITS:
        n = s.count(old)
        if n != 1:
            print('ОШИБКА: якорь %r встречается %d раз (ожидался 1)' % (tag, n))
            sys.exit(1)
        s = s.replace(old, new)
        print('ок: %s' % tag)

    # Контроль: дельта М1 в модели точная.
    for frag, want in (
        ("self.por_sh = 0xF", 1),
        ("return self.x1_n", 1),
        ("(self.por_sh >> 1) & 0xF", 1),
        ("(self.por_sh >> 1) & 0xFF", 0),
        ("cnt == 1 or cnt == 6", 0),     # старый строб исчез
        ("(cnt == 1 or self.cnt == 6)", 0),
    ):
        got = s.count(frag)
        if got != want:
            print('ОШИБКА: %r встречается %d раз (ожидалось %d)' % (frag, got, want))
            sys.exit(1)
    # пор-цепь вне GSR: в ветке RST por_sh не трогается
    if "self.por_sh = 0xF; self.por_run = 1" not in s:
        print('ОШИБКА: INIT por_sh потерян')
        sys.exit(1)
    print('ок: дельта М1 в модели точная')

    io.open(SIM_OUT, 'w', encoding='utf-8', newline='').write(s)
    print('создано: %s (%d строк)' % (SIM_OUT, s.count('\n')))

    # ---------------- tb владельцу ----------------
    tb = io.open(TB_SRC, encoding='utf-8').read()
    renames = [
        ("tb_hwuart_v400.v - testbench for hwuart v4.0.0 (beta/hwuart).",
         "tb_hwuart_v401.v - testbench for hwuart v4.0.1 (beta/hwuart)."),
        ("//  - rx_int goes to P75 (RST 7.5); SID = RX transit observer is alive.",
         "//  - rx_int goes to P75 (RST 7.5); SID = RX transit observer is alive.\n"
         "//  - v4.0.1 = v4.0.0 + M1 (p.27): POR counter 8->4, strobe por_ce = x1_n\n"
         "//    (1 pulse per cnt period 280 ns); POR ~1020-1040 ns from INIT\n"
         "//    (4 shifts F->7->3->1->0), norm 840 ns kept, margin 1.33x."),
        ("//    (75/75 PASS, scenarios C1-C9); this tb repeats the key functional",
         "//    (75/75 PASS, scenarios C1-C9); this tb repeats the key functional"),
        ("// Run:  iverilog -o tb_hwuart.vvp tb_hwuart_v400.v top_hwuart_por6_v400_utf8.v",
         "// Run:  iverilog -o tb_hwuart.vvp tb_hwuart_v401.v top_hwuart_por6_v401_utf8.v"),
        ("    // ---- wait POR (~1120 ns) ----",
         "    // ---- wait POR (~1020-1040 ns from INIT, M1: 4 shifts x 280 ns) ----"),
    ]
    for old, new in renames:
        n = tb.count(old)
        if n != 1:
            print('ОШИБКА tb: якорь %r встречается %d раз (ожидался 1)' % (old[:50], n))
            sys.exit(1)
        tb = tb.replace(old, new)
    io.open(TB_OUT, 'w', encoding='utf-8', newline='').write(tb)
    print('создано: %s (%d строк)' % (TB_OUT, tb.count('\n')))


if __name__ == '__main__':
    main()
