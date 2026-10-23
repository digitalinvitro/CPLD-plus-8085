#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_diag3_hex.py -- побайтовые и структурные проверки uart_echo_diag3.

  1. Вектор ре-арма 003Ch-003Fh = MVI A,8 / OUT 04h (как в v1/v2).
  2. Вентиль ISR: MOV A,E / ORA A / JZ TXRUN / JMP RX (E = интервалы RX).
  3. RXN1 = 4 (0,5 бита): MVI A,04h / OUT TMRP / MVI A,08h / SIM в MAIN
     (атомарный выброс латча сохранён: загрузка -> SIM 08h).
  4. Обе ветви выборки содержат RIM; данные идут и в L (LSB-first), и в
     TSB (таймлайн, MSB-first через LHLD/RAL/RAL/SHLD).
  5. Релиз: STA BYTE0, очередь [tl-hi, tl-lo] из TSB, QCNT=2, MVI C,0Bh.
  6. TX-автомат: холостой бит (CPI 0Bh -> TXIDLBIT) и подзаряд очереди
     на стоп-фазе (LDA QCNT ... MVI C,0Ch).
  7. MAIN: SSELF-счётчик захватов своего эха (LDA SSELF/INR A/STA при
     C != 0FFh), MVI E,12, MVI L,0; SEGTAB на 01D0h (lo = D0h).
"""
import sys

ROM = '/home/z/my-project/CPLD-plus-8085/beta/01_timer/rom'


def load(path):
    mem = {}
    for line in open(path):
        line = line.strip()
        if not line.startswith(':'):
            continue
        b = bytes.fromhex(line[1:])
        if b[3] == 0:
            for i in range(b[0]):
                mem[(b[1] << 8) | b[2] + i] = b[4 + i]
    return mem


def run(mem, a, n):
    return [mem.get(a + i) for i in range(n)]


d1 = load(f'{ROM}/uart_echo_diag.hex')
d3 = load(f'{ROM}/uart_echo_diag3.hex')
fails = []

# 1. вектор ре-арма -- байт в байт с v1
if run(d3, 0x3C, 4) != run(d1, 0x3C, 4) or run(d3, 0x3C, 4) != [0x3E, 0x08, 0xD3, 0x04]:
    fails.append('вектор 003Ch не равен MVI A,8 / OUT 04h')

# 2. вентиль ISR на E
if run(d3, 0x40, 8) != [0x7B, 0xB7, 0xCA, 0x48, 0x00, 0xC3, 0xA1, 0x00]:
    fails.append('вентиль ISR (MOV A,E/ORA/JZ/JMP RX) не совпал')

# 3. RXN1=4 + атомарный выброс латча в MAIN (последовательность подряд)
arm = [0x3E, 0x04, 0xD3, 0x04, 0x3E, 0x08, 0x30]
mb = run(d3, 0x100, 0x70)
if not any(mb[i:i + 7] == arm for i in range(len(mb) - 7)):
    fails.append('MAIN: MVI A,4/OUT/MVI A,8/SIM не найдена')

# 4. RX-путь: две ветви (RIM на 00B0h для данных, 00BAh для старта/хвоста),
#    упаковка TSB с 00BEh, данные идут и в L (LSB-first)
if run(d3, 0xB0, 3) != [0x20, 0xE6, 0x80] or run(d3, 0xBA, 3) != [0x20, 0xE6, 0x80]:
    fails.append('RIM-ветви выборки не на 00B0h/00BAh')
if run(d3, 0xB4, 3) != [0x7D, 0x1F, 0x6F]:
    fails.append('накопитель L (MOV A,L/RAR/MOV L,A) не на 00B4h')
if run(d3, 0xBE, 10) != [0x2A, 0x02, 0x80, 0x7C, 0x17, 0x67, 0x7D, 0x17,
                         0x6F, 0x22]:
    fails.append('упаковка LHLD TSB/RALx2/SHLD не на 00BEh')

# 5. релиз: STA BYTE0/MOV D,A; LHLD TSB; очередь; QCNT=2; MVI C,0Bh
if run(d3, 0xD6, 20) != [0x7D, 0x32, 0x01, 0x80, 0x57, 0x2A, 0x02, 0x80,
                         0x7C, 0x32, 0x04, 0x80, 0x7D, 0x32, 0x05, 0x80,
                         0x3E, 0x02, 0x32, 0x07]:
    fails.append('релиз 00D6h-00E9h не совпал')

# 6. TX: холостой бит и подзаряд очереди
if d3.get(0x55) != 0xFE or d3.get(0x56) != 0x0B:
    fails.append('CPI 0Bh (холостой бит) не на 0055h')
if run(d3, 0x7C, 3) != [0x3A, 0x07, 0x80]:
    fails.append('LDA QCNT на стоп-фазе не найдена')

# 7. MAIN: SSELF-ветка (LDA SSELF/INR A/STA SSELF), CATCHN/ARMED с 0151h
if run(d3, 0x147, 5) != [0x3A, 0x06, 0x80, 0x3C, 0x32]:
    fails.append('SSELF-ветка (LDA/INR A/STA) не на 0147h')
if run(d3, 0x151, 12) != [0x04, 0xAF, 0x32, 0x02, 0x80, 0x32, 0x03, 0x80,
                          0x2E, 0x00, 0x1E, 0x0C]:
    fails.append('CATCHN: INR B + ARMED: STA TSB x2 / MVI L,0 / MVI E,12')

# 8. SEGTAB на 01D0h
if run(d3, 0x1D0, 16) != [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07,
                          0x7F, 0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71]:
    fails.append('SEGTAB на 01D0h не совпал')

# 9. JMP MAIN -> 0100h
if run(d3, 0, 3) != [0xC3, 0x00, 0x01]:
    fails.append('JMP MAIN не ведёт на 0100h')

top = max(d3)
print(f'diag v1: {max(d1) + 1:3d} байт; diag v3: {top + 1:3d} байт (0000h-{top:04X}h)')
if fails:
    print('\nПРОВАЛ:')
    for f in fails:
        print(' -', f)
    sys.exit(1)
print('\nПАСС: вектор = v1; вентиль на E; RXN1=4 c SIM-выбросом; две ветви')
print('выборки (данные в L + таймлайн в TSB); релиз/очередь/холостой бит,')
print('SSELF, MAIN, SEGTAB -- по контрольным точкам.')
