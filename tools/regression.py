#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
regression.py — РЕГРЕССИЯ СБОРКИ ВСЕХ ПРОШИВОК репозитория CPLD-plus-8085.

Каждый .asm из таблицы ниже пересобирается каноническим tools/asm85.py
во временный каталог и сравнивается байт-в-байт (текст Intel HEX) с
ЗАОКОММИЧЕННЫМ образом .hex. Это доказывает, что tools/asm85.py v1.1
(надмножество asm85 + asm8085) воспроизводит весь парк прошивок репо:
01_timer, lowsize (fw_mon/fw_test_disp/fw_text_kbd), txuart (uart_tx_test),
xstream, gfxstream (v1/v2/v2.1/v2.2), txstress (v10/v11, полные и p04).

Запуск (из любого каталога):
    python3 tools/regression.py [-v]

Вердикт: PASS — все образы воспроизвелись 1-в-1 (код выхода 0);
         FAIL — список расхождений (код выхода 1).

ПРАВИЛО СОПРОВОЖДЕНИЯ: после любых правок asm85.py прогонять этот скрипт;
новые прошивки добавлять в таблицу BUILDS.
"""
import argparse
import hashlib
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASM = os.path.join(HERE, 'asm85.py')

# (исходник .asm, эталонный .hex, ключи -D) — пути от корня репозитория.
# Эталонный .hex обязан быть закоммичен; сборка в него НЕ пишется.
BUILDS = [
    # --- beta/01_timer/rom: таймер/тон/UART-эхо (ветка asm85) ---
    ('beta/01_timer/rom/timer_test.asm',      'beta/01_timer/rom/timer_test_tone.hex',  []),
    ('beta/01_timer/rom/timer_test.asm',      'beta/01_timer/rom/timer_test_blink.hex', ['TONE=0']),
    ('beta/01_timer/rom/timer_test.asm',      'beta/01_timer/rom/timer_test_n10.hex',   ['TMR_N=10']),
    ('beta/01_timer/rom/timer_test_uart.asm', 'beta/01_timer/rom/timer_test_uart.hex',  []),
    ('beta/01_timer/rom/uart_echo_test.asm',  'beta/01_timer/rom/uart_echo_test.hex',   []),
    ('beta/01_timer/rom/uart_sw_test.asm',    'beta/01_timer/rom/uart_sw_test.hex',     []),
    ('beta/01_timer/rom/uart_echo_diag.asm',  'beta/01_timer/rom/uart_echo_diag.hex',   []),
    ('beta/01_timer/rom/uart_echo_diag2.asm', 'beta/01_timer/rom/uart_echo_diag2.hex',  []),
    ('beta/01_timer/rom/uart_echo_diag3.asm', 'beta/01_timer/rom/uart_echo_diag3.hex',  []),
    ('beta/01_timer/rom/uart_echo_diag4.asm', 'beta/01_timer/rom/uart_echo_diag4.hex',  []),
    ('beta/01_timer/rom/uart_echo_diag5.asm', 'beta/01_timer/rom/uart_echo_diag5.hex',  []),
    ('beta/01_timer/rom/uart_echo_diag6.asm', 'beta/01_timer/rom/uart_echo_diag6.hex',  []),
    # --- beta/lowsize/rom: монитор fw_mon ACDE + приёмочные тесты платы ---
    ('beta/lowsize/rom/fw_mon.asm',       'beta/lowsize/rom/fw_mon.hex',            []),
    ('beta/lowsize/rom/fw_mon.asm',       'beta/lowsize/rom/fw_mon_fast.hex',       ['FAST=1']),
    ('beta/lowsize/rom/fw_test_disp.asm', 'beta/lowsize/rom/fw_test_disp.hex',      []),
    ('beta/lowsize/rom/fw_test_disp.asm', 'beta/lowsize/rom/fw_test_disp_fast.hex', ['FAST=1']),
    ('beta/lowsize/rom/fw_text_kbd.asm',  'beta/lowsize/rom/fw_text_kbd.hex',       []),
    ('beta/lowsize/rom/fw_text_kbd.asm',  'beta/lowsize/rom/fw_text_kbd_fast.hex',  ['FAST=1']),
    # --- beta/txuart/rom: первый UART-тест ---
    ('beta/txuart/rom/uart_tx_test.asm', 'beta/txuart/rom/uart_tx_test.hex', []),
    # --- beta/xstream: прерывание -> весь экран в UART (SW/HW-варианты) ---
    ('beta/xstream/xstream_v1.asm', 'beta/xstream/xstream_v1.hex',    []),
    ('beta/xstream/xstream_v1.asm', 'beta/xstream/xstream_v1_hw.hex', ['TMR_HW=1']),
    # --- beta/txuart/rom/gfxstream: графический поток (строились asm8085) ---
    ('beta/txuart/rom/gfxstream/gfxstream_v1.asm',  'beta/txuart/rom/gfxstream/gfxstream_v1.hex',  []),
    ('beta/txuart/rom/gfxstream/gfxstream_v2.asm',  'beta/txuart/rom/gfxstream/gfxstream_v2.hex',  []),
    ('beta/txuart/rom/gfxstream/gfxstream_v21.asm', 'beta/txuart/rom/gfxstream/gfxstream_v21.hex', []),
    ('beta/txuart/rom/gfxstream/gfxstream_v22.asm', 'beta/txuart/rom/gfxstream/gfxstream_v22.hex', []),
    # --- beta/txuart/rom/txstress: стресс-тесты TX (строились asm8085) ---
    # txstress_v10.hex / v10_p04.hex ИСКЛЮЧЕНЫ: они построены ДО фикса бага
    # size_of (asm8085 v1.0, урок 11-10) — адреса меток в непосредственных
    # операндах занижены (+13/+14), это УЛИКА урока, не пересобирается
    # никаким корректным ассемблером. Живая ветка — v11 (ниже, 1-в-1).
    ('beta/txuart/rom/txstress/txstress_v11.asm', 'beta/txuart/rom/txstress/txstress_v11.hex',      []),
    ('beta/txuart/rom/txstress/txstress_v11.asm', 'beta/txuart/rom/txstress/txstress_v11_p04.hex',  ['TX_BOTH=0']),
]


def md5_of(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()[:8]


def main():
    ap = argparse.ArgumentParser(description='регрессия сборки прошивок (tools/asm85.py vs закоммиченные .hex)')
    ap.add_argument('-v', '--verbose', action='store_true', help='показывать вывод asm85 по каждой сборке')
    args = ap.parse_args()

    ok = 0
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        out_hex = os.path.join(tmp, 'out.hex')
        for src_rel, ref_rel, defines in BUILDS:
            src = os.path.join(ROOT, src_rel)
            ref = os.path.join(ROOT, ref_rel)
            if not os.path.isfile(src):
                fails.append((src_rel, ref_rel, 'исходник не найден'))
                continue
            if not os.path.isfile(ref):
                fails.append((src_rel, ref_rel, 'эталонный .hex не найден (закоммить его)'))
                continue
            cmd = [sys.executable, ASM, src, '-o', out_hex]
            for d in defines:
                cmd += ['-D', d]
            p = subprocess.run(cmd, capture_output=True, text=True)
            if args.verbose:
                sys.stdout.write(p.stdout)
                sys.stdout.write(p.stderr)
            if p.returncode != 0:
                tail = (p.stderr or p.stdout).strip().splitlines()
                fails.append((src_rel, ref_rel, 'asm85: ' + (tail[-1] if tail else 'код %d' % p.returncode)))
                continue
            with open(out_hex, 'r') as f:
                built = f.read().strip()
            with open(ref, 'r') as f:
                want = f.read().strip()
            if built == want:
                ok += 1
                print('[OK ] %-44s %-12s -> %s  (%s)'
                      % (os.path.basename(src_rel), ','.join(defines) or '-',
                         os.path.basename(ref_rel), md5_of(ref)))
            else:
                nb, nw = len(built.splitlines()), len(want.splitlines())
                first = next((i for i, (a, b) in enumerate(zip(built.splitlines(), want.splitlines()))
                              if a != b), min(nb, nw))
                fails.append((src_rel, ref_rel,
                              'hex различается (строк собрано/эталон %d/%d, первая %d)'
                              % (nb, nw, first + 1)))

    print('-' * 78)
    if fails:
        print('ВЕРДИКТ: FAIL — %d/%d воспроизвелись' % (ok, len(BUILDS)))
        for src_rel, ref_rel, why in fails:
            print('  [FAIL] %s -> %s: %s' % (src_rel, ref_rel, why))
        return 1
    print('ВЕРДИКТ: PASS — все %d образов воспроизведены байт-в-байт (tools/asm85.py v1.1)' % len(BUILDS))
    return 0


if __name__ == '__main__':
    sys.exit(main())
