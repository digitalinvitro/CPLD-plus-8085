#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_diag2_hex.py -- побайтовая сверка uart_echo_diag2 против diag v1.

Требования v2 (шапка uart_echo_diag2.asm):
  1. Критичный путь приёма НЕ ТРОНУТ: вектор ре-арма 003Ch-003Fh,
     вентиль+TX+RX до JM (0040h-0080h) и сами выборки d0..d7
     (0083h-0089h: RIM/ANI/RAR/MOV A,L/RAR/MOV L,A) = v1 БАЙТ В БАЙТ.
     Отличия допустимы только в операнде JM (0081h-0082h: RXT->RXTAIL).
  2. Вставки v2: JMP RXDCR (008Ah: C3 94 00), блок RXTAIL
     (008Dh: 20 E6 80 1F 7B 17 5F), RXDCR = DCR H (0094h).
  3. Релиз: STA 8001h (009Bh), арифметика релиза та же; ISR кончается
     RET на 00A8h -- без наезда на MAIN (00B0h).
  4. MAIN: LXI SP,FFFF (00B0h); пара OUT TMRP(04h) -> SIM 08h атомарный
     выброс латча СОХРАНЕНА (MVI E,0 -- ПОСЛЕ SIM).
  5. SEGTAB с 0160h (lo = 60h -- ADD L без переноса).
"""
import sys

ROM = '/home/z/my-project/CPLD-plus-8085/beta/01_timer/rom'


def load(path):
    """Intel HEX -> dict addr:byte (без контрольных сумм файлов)."""
    mem = {}
    for line in open(path):
        line = line.strip()
        if not line.startswith(':'):
            continue
        b = bytes.fromhex(line[1:])
        count, addr, rectype = b[0], (b[1] << 8) | b[2], b[3]
        if rectype == 0:
            for i in range(count):
                mem[addr + i] = b[4 + i]
    return mem


def run(mem, a, n):
    return [mem.get(a + i) for i in range(n)]


d1 = load(f'{ROM}/uart_echo_diag.hex')
d2 = load(f'{ROM}/uart_echo_diag2.hex')
fails = []

# 1. вектор ре-арма MVI A,8 / OUT 04h
if run(d2, 0x3C, 4) != [0x3E, 0x08, 0xD3, 0x04]:
    fails.append('вектор 003Ch не равен MVI A,8 / OUT 04h')
if run(d2, 0x3C, 4) != run(d1, 0x3C, 4):
    fails.append('вектор 003Ch отличается от v1')

# 2. критичный путь: 0040h-007Ah и 0083h-0089h = v1 (операнды переходов
#    JZ RXE 007Bh-007Dh и JM RXTAIL 0080h-0082h проверяются отдельно)
for lo, hi, tag in [(0x40, 0x7B, 'вентиль+TX+RX до JZ'),
                    (0x83, 0x8A, 'выборки d0..d7 (RIM..MOV L,A)')]:
    d = [f'{a:04X}' for a in range(lo, hi) if d2.get(a) != d1.get(a)]
    if d:
        fails.append(f'{tag} изменён по адресам {d}')

# 3. переходы: JZ RXE (007Bh: CA A7 00), JM RXTAIL (0080h: FA 8D 00)
if run(d2, 0x7B, 3) != [0xCA, 0xA7, 0x00]:
    fails.append(f'JZ RXE на 007Bh не совпал: '
                 f'{[f"{b:02X}" for b in run(d2, 0x7B, 3)]}')
if run(d2, 0x80, 3) != [0xFA, 0x8D, 0x00]:
    fails.append(f'JM RXTAIL на 0080h не совпал: '
                 f'{[f"{b:02X}" for b in run(d2, 0x80, 3)]}')

# 4. вставки v2
if run(d2, 0x8A, 3) != [0xC3, 0x94, 0x00]:
    fails.append('JMP RXDCR (C3 94 00) не на 008Ah')
if run(d2, 0x8D, 7) != [0x20, 0xE6, 0x80, 0x1F, 0x7B, 0x17, 0x5F]:
    fails.append('блок RXTAIL (RIM/ANI/RAR/MOV A,E/RAL/MOV E,A) не на 008Dh')
if d2.get(0x94) != 0x25:
    fails.append('RXDCR: DCR H не на 0094h')

# 5. релиз: MOV A,L/STA 8001h/MOV A,C/CPI FF/JNZ RXE/MOV D,L/MVI C,0B/EI/RET
exp = ([0x7D] + [0x32, 0x01, 0x80] + [0x79, 0xFE, 0xFF] + [0xC2, 0xA7, 0x00]
       + [0x55] + [0x0E, 0x0B] + [0xFB, 0xC9])
if run(d2, 0x9A, 15) != exp:
    fails.append(f'релиз 009Ah-00A8h не совпал: '
                 f'{[f"{b:02X}" for b in run(d2, 0x9A, 15)]}')

# 6. MAIN: LXI SP,FFFF на 00B0h
if run(d2, 0xB0, 3) != [0x31, 0xFF, 0xFF]:
    fails.append('MAIN: LXI SP,FFFF не на 00B0h')
# OUT 04h, затем через MVI A -- SIM 08h (загрузка -> атомарный сброс латча)
mb = run(d2, 0xB0, 0x50)
ok = any(mb[i] == 0xD3 and mb[i + 1] == 0x04 and mb[i + 2] == 0x3E
         and mb[i + 3] == 0x08 and mb[i + 4] == 0x30
         for i in range(len(mb) - 4))
if not ok:
    fails.append('MAIN: пара OUT TMRP -> MVI A,08h -> SIM не найдена')

# 7. SEGTAB с 0160h
if run(d2, 0x160, 16) != [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07,
                          0x7F, 0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71]:
    fails.append('SEGTAB на 0160h не совпал')

# 8. JMP MAIN -> 00B0h
if run(d2, 0, 3) != [0xC3, 0xB0, 0x00]:
    fails.append('JMP MAIN не ведёт на 00B0h')

# --- отчёт ---
top = max(d2)
print(f'diag v1: {max(d1) + 1:3d} байт (0000h-{max(d1):04X}h)')
print(f'diag v2: {top + 1:3d} байт (0000h-{top:04X}h)')
print('Различия против v1 (первый адрес блока):')
prev = None
for a in sorted(set(d1) | set(d2)):
    if d1.get(a) != d2.get(a):
        if prev is None or a > prev + 8:
            v1 = '--' if d1.get(a) is None else f'{d1.get(a):02X}'
            print(f'  {a:04X}: v1={v1} v2={d2.get(a):02X}')
        prev = a
if fails:
    print('\nПРОВАЛ:')
    for f in fails:
        print(' -', f)
    sys.exit(1)
print('\nПАСС: вектор и выборки d0..d7 = v1 байт в байт (изменился только')
print('операнд JM); вставки v2, релиз, MAIN, DMUX/SEGTAB -- по точкам.')
