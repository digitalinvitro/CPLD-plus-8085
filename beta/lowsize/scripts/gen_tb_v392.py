#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_tb_v392.py — адаптация диф-тестбенча tb_v391_diff.v (v3.9 vs v3.9.1)
в tb_v392_diff.v (v3.9.1 vs v3.9.2, clk10-65).

Метод: однопроходная замена ПО ТОКЕНАМ-ИДЕНТИФИКАТОРАМ (regex
\\b[A-Za-z_]\\w*\\b): токен, содержащий '391' -> '392'; иначе содержащий
'39' -> '391'. Числа (начинаются с цифры) не трогаются. Затем текст
сообщений 'v3.9.1'/'v3.9' через плейсхолдеры. Заголовок заменяется
собственным (v3.9.2-специфика) ПОСЛЕ токен-прохода.

Итог: эталон = v3.9.1 (дут из top_suart_por6_v391), новый = v3.9.2.
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'tb_v391_diff.v')
DST = os.path.join(HERE, 'tb_v392_diff.v')

HEADER_NEW = """`timescale 1ns/1ps
//=====================================================================
// tb_v392_diff.v (clk10-65): DIFFerencial'naya simulyaciya v3.9.1 vs
// v3.9.2 (zamena kol'ca one-hot N=7 dvoichnym schetchikom mod-7,
// liniya lowsize). Metod: oba RTL v odnom testbenche, OBSHCHIJ stimul,
// sravnenie VSEH vyhodov i obeih shin kazhdye 5 ns (4-znachnaya logika
// ===). ETALON = v3.9.1 (ekvivalent v3.9, dokazano clk10-62); v3.9.2
// otlichaetsya tol'ko uzlom delitelya -> lyuboe rashozhdenie = defekt
// schetchika (X1/X2/por). Vse scenarii i spek-proverki nasledovany ot
// tb_v391_diff.v bez izmenenij (sm. zametki v iskhodnom TB).
//=====================================================================
"""


def tok_repl(m):
    t = m.group(0)
    if '391' in t:
        return t.replace('391', '392')
    if '39' in t:
        return t.replace('39', '391')
    return t


def main():
    s = io.open(SRC, encoding='utf-8').read()

    # 1) Токен-проход (идентификаторы; числа не матчатся - начинаются с цифры)
    s = re.sub(r'\b[A-Za-z_]\w*\b', tok_repl, s)

    # 2) Текст сообщений: v3.9.1 -> v3.9.2, v3.9 -> v3.9.1 (плейсхолдер)
    s = s.replace('v3.9.1', '\x01\x02')
    s = s.replace('v3.9', 'v3.9.1')
    s = s.replace('\x01\x02', 'v3.9.2')

    # 3) Заголовок: всё до 'module tb_v392_diff;' заменить
    anchor = 'module tb_v392_diff;'
    i = s.index(anchor)
    s = HEADER_NEW + s[i:]

    # Контроль
    assert 'retro_pcld_top_v392' in s, 'нет нового DUT v392'
    assert 'retro_pcld_top_v391' in s, 'нет эталона v391'
    assert re.search(r'\bretro_pcld_top_v39\b', s) is None, 'остался голый v39'
    assert 'tb_v392_diff' in s
    assert s.count('module tb_v391_diff') == 0  # упоминания в комментах допустимы
    assert 'v3.9.1.2' not in s and '\x01' not in s
    io.open(DST, 'w', encoding='utf-8', newline='').write(s)
    print('ок: tb_v392_diff.v сгенерирован (%d строк)' % s.count('\n'))


if __name__ == '__main__':
    main()
