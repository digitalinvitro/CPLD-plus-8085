#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_diag4_hex.py -- структурные проверки uart_echo_diag4 против diag3.

diag4 = diag3 с исправленным вводом и порядком эха:
  1. В обеих ветвях выборки RAR заменён на RLC (CY <- SID, а не 0);
     в ветви данных добавлен повторный RLC перед упаковкой TSB.
  2. RXPACK обёрнут в PUSH H / POP H -- LHLD TSB больше не затирает
     накопитель байта L.
  3. Релиз копирует таймлайн в очередь прямыми LDA/STA: LHLD/SHLD
     хранят пару little-endian (8002h = мл. байт), а протокол требует
     [байт][tl-hi][tl-lo] -- иначе эхо шло бы [байт][tl-lo][tl-hi].
  Всё остальное (TX-автомат, MAIN, DMUX, SEGTAB) -- байт в байт с diag3.

Проверки:
  A. Оба образа 480 байт, 0000h-01DFh.
  B. Вектор ре-арма 003Ch и вентиль ISR на E = v3 байт в байт.
  C. TX-автомат 0048h-00A0h = v3 байт в байт (TX не тронут).
  D. Ветвь данных 00B0h: RIM/ANI/RLC/MOV A,L/RAR/MOV L,A/RLC/JMP.
  E. Ветвь старт/хвост 00BBh: RIM/ANI/RLC.
  F. RXPACK 00BFh: PUSH H / LHLD TSB / RALx2 / SHLD / POP H / DCR E.
  G. Релиз 00D3h-00F0h: байт из L (STA BYTE0/MOV D,A), очередь из ОЗУ
     в порядке 8002h (tl-hi) -> QBUF, 8003h (tl-lo) -> QBUF+1 (LHLD
     в v3 переворачивал пару), QCNT=2, MVI C,0Bh; RXE = 00F1h (EI/RET).
  H. Заполнители 00F3h-00FFh и 016Ch-016Fh = 00; MAIN 0100h, DMUX 0170h,
     SEGTAB 01D0h = v3 байт в байт.
"""
import sys

ROM = '/home/z/my-project/CPLD-plus-8085/beta/01_timer/rom'


def load(path):
    mem = {}
    top = 0
    for line in open(path):
        line = line.strip()
        if not line.startswith(':'):
            continue
        b = bytes.fromhex(line[1:])
        if b[3] == 0:
            addr = (b[1] << 8) | b[2]
            for i in range(b[0]):
                mem[addr + i] = b[4 + i]
            top = max(top, addr + b[0])
        elif b[3] == 1:
            break
    return mem, top


def run(mem, a, n):
    return [mem.get(a + i) for i in range(n)]


d3, top3 = load(f'{ROM}/uart_echo_diag3.hex')
d4, top4 = load(f'{ROM}/uart_echo_diag4.hex')
fails = []

# A. размер (top -- исключительный конец: 0x1E0 = 480 байт, 0000h-01DFh)
if top3 != 0x1E0 or top4 != 0x1E0:
    fails.append(f'размер: diag3={top3} diag4={top4}, ждём 480 байт')

# B. вектор ре-арма и вентиль ISR
if run(d4, 0x3C, 4) != [0x3E, 0x08, 0xD3, 0x04]:
    fails.append('вектор 003Ch не равен MVI A,8 / OUT 04h')
if run(d4, 0x40, 8) != [0x7B, 0xB7, 0xCA, 0x48, 0x00, 0xC3, 0xA1, 0x00] or \
        run(d4, 0x40, 8) != run(d3, 0x40, 8):
    fails.append('вентиль ISR (MOV A,E/ORA/JZ/JMP RX) не совпал')

# C. TX-автомат не тронут (0048h-00A0h = v3 байт в байт)
if run(d4, 0x48, 0xA1 - 0x48) != run(d3, 0x48, 0xA1 - 0x48):
    fails.append('TX-автомат 0048h-00A0h отличается от v3 (не должен!)')

# D. ветвь данных: RIM/ANI/RLC/MOV A,L/RAR/MOV L,A/RLC/JMP RXPACK
if run(d4, 0xB0, 11) != [0x20, 0xE6, 0x80, 0x07, 0x7D, 0x1F, 0x6F, 0x07,
                         0xC3, 0xBF, 0x00]:
    fails.append('ветвь данных 00B0h: нет пары RLC+RAR+RLC/JMP 00BFh')

# E. ветвь старт/хвост: RIM/ANI/RLC
if run(d4, 0xBB, 4) != [0x20, 0xE6, 0x80, 0x07]:
    fails.append('ветвь старт/хвост 00BBh: RAR не заменён на RLC')

# F. RXPACK: PUSH H / LHLD TSB / RALx2 / SHLD / POP H / DCR E
if run(d4, 0xBF, 15) != [0xE5, 0x2A, 0x02, 0x80, 0x7C, 0x17, 0x67, 0x7D,
                         0x17, 0x6F, 0x22, 0x02, 0x80, 0xE1, 0x1D]:
    fails.append('RXPACK 00BFh: нет PUSH H/POP H вокруг упаковки TSB')

# G. релиз: JNZ RXE(00F1h), байт из L, очередь tl-hi первым, QCNT=2
if run(d4, 0xD0, 3) != [0xC2, 0xF1, 0x00]:
    fails.append('JNZ RXE не ведёт на 00F1h')
if run(d4, 0xD3, 30) != [0x79, 0xFE, 0xFF, 0xC2, 0xF1, 0x00,
                         0x7D, 0x32, 0x01, 0x80, 0x57,
                         0x3A, 0x02, 0x80, 0x32, 0x04, 0x80,
                         0x3A, 0x03, 0x80, 0x32, 0x05, 0x80,
                         0x3E, 0x02, 0x32, 0x07, 0x80, 0x0E, 0x0B]:
    fails.append('релиз 00D3h-00F0h не совпал (байт из L, tl-hi первым)')
if run(d4, 0xF1, 2) != [0xFB, 0xC9]:
    fails.append('RXE 00F1h: нет EI/RET')

# H. заполнители (00F3h-00FFh и 016Ch-016Fh) и неизменные блоки
bad_fill = [a for a in list(range(0xF3, 0x100)) + list(range(0x16C, 0x170))
            if d4.get(a, 1) != 0x00]
if bad_fill:
    fails.append('заполнитель не нулевой: ' +
                 ', '.join(f'{a:04X}h' for a in bad_fill))
if run(d4, 0x100, 0x170 - 0x100) != run(d3, 0x100, 0x170 - 0x100):
    fails.append('MAIN 0100h-016Fh отличается от v3 (не должен!)')
if run(d4, 0x170, 0x1D0 - 0x170) != run(d3, 0x170, 0x1D0 - 0x170):
    fails.append('DMUX 0170h-01CFh отличается от v3 (не должен!)')
if run(d4, 0x1D0, 16) != [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07,
                          0x7F, 0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71]:
    fails.append('SEGTAB на 01D0h не совпал')

print(f'diag v3: {top3} байт; diag v4: {top4} байт '
      f'(0000h-{top4 - 1:04X}h)')
if fails:
    print('\nПРОВАЛ:')
    for f in fails:
        print(' -', f)
    sys.exit(1)
print('\nПАСС: RLC в обеих ветвях выборки (+повторный RLC для TSB),')
print('PUSH/POP H вокруг LHLD TSB; релиз: байт из L, tl-hi первым;')
print('TX-автомат, MAIN, DMUX, SEGTAB -- байт в байт с diag3.')
