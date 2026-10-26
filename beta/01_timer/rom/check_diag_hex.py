#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_diag_hex.py -- побайтовая верификация uart_echo_diag.hex.

Опорные факты:
  1) uart_echo_test.hex (v1, 229 байт) уже побайтово верифицирован
     (verify_hex.py v5, REF_ECHO). Вся логика эха в диагностике НЕ
     менялась: векторы и ISR до релиза должны совпасть байт в байт
     (кроме адреса RXE в JNZ: 0099h -> 009Dh, сдвиг +4 байта вставки).
  2) Добавки проверяются контрольными точками (ручная раскладка).

Выход: OK / список расхождений.
"""
import os, sys

def read_hex(path):
    mem = {}
    for line in open(path):
        line = line.strip()
        if not line.startswith(':'):
            continue
        b = bytes.fromhex(line[1:])
        cnt, ah, al, typ = b[0], b[1], b[2], b[3]
        assert ((cnt + ah + al + typ + sum(b[4:4+cnt]) + b[4+cnt]) & 0xFF) == 0, \
            'CRC: ' + line
        if typ == 0:
            base = (ah << 8) | al
            for i, byte in enumerate(b[4:4+cnt]):
                mem[base + i] = byte
    return mem

diag = read_hex(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uart_echo_diag.hex'))
v1   = read_hex(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uart_echo_test.hex'))

errors = []

def expect(tag, addr, data):
    for i, want in enumerate(data):
        got = diag.get(addr + i)
        if got != want:
            errors.append('%s @ %04X: ожидалось %02Xh, получено %s'
                          % (tag, addr + i, want,
                             '%02Xh' % got if got is not None else 'нет'))

# --- 1) векторы + ISR до вставки: как в v1, КРОМЕ адресов переходов на
#       RXE (JZ @007B, JNZ @008D): RXE уехал 0099h -> 009Dh (+4 вставки)
RXE_DELTA = {0x007C, 0x008E}
for a in range(0x0000, 0x0090):
    if a in RXE_DELTA:
        continue
    if diag.get(a) != v1.get(a):
        errors.append('ОБЩЕЕ с v1 @ %04X: v1=%02Xh diag=%02Xh'
                      % (a, v1.get(a, 0), diag.get(a, 0)))
expect('JZ RXE (вентиль)', 0x007B, [0xCA, 0x9D, 0x00])
expect('JNZ RXE (релиз)', 0x008D, [0xC2, 0x9D, 0x00])

# --- 2) вставка релиза: MOV A,L; STA 8001h ---
expect('копия байта', 0x0090, [0x7D, 0x32, 0x01, 0x80])
# --- 3) хвост релиза: MOV A,C; CPI 0FFh; JNZ RXE(009Dh); MOV D,L; MVI C,0Bh; EI; RET ---
expect('релиз', 0x0094, [0x79, 0xFE, 0xFF, 0xC2, 0x9D, 0x00, 0x55, 0x0E, 0x0B, 0xFB, 0xC9])

# --- 4) MAIN: вехи ---
expect('сброс', 0x0000, [0xC3, 0xA0, 0x00])
expect('ре-арм', 0x003C, [0x3E, 0x08, 0xD3, 0x04])
expect('MAIN', 0x00A0, [0x31, 0xFF, 0xFF,       # LXI SP,0FFFFh
                        0x3E, 0xC0, 0x30,       # SOD=1, SIM
                        0x3E, 0x00,             # MVI A,0
                        0x32, 0x00, 0x80,       # STA MUXI
                        0x32, 0x01, 0x80,       # STA BYTE0
                        0x06, 0x00,             # MVI B,0
                        0x3E, 0x1B, 0x30,       # SIMW
                        0x16, 0x3E,             # MVI D,'>'
                        0x0E, 0x0B,             # MVI C,0Bh
                        0x3E, 0x08, 0xD3, 0x04, # TMR_N -> TMRP
                        0x26, 0x00, 0x2E, 0x00, # H=0, L=0
                        0xFB])                  # EI
# BAN: MOV A,C; CPI 0FFh; JNZ BAN (00C0h.., см. таблицу символов)
expect('BAN', 0x00C0, [0x79, 0xFE, 0xFF, 0xC2, 0xC0, 0x00])
# POLL: CALL DMUX; DI; RIM; ANI 80h; JNZ POLL
expect('POLL', 0x00C6, [0xCD, 0xF0, 0x00, 0xF3, 0x20, 0xE6, 0x80, 0xC2, 0xC6, 0x00])
# ловля старта: MVI A,0Ch; OUT 04h; MVI A,08h; SIM; INR B; L=0; H=11; EI
expect('ловля', 0x00D0, [0x3E, 0x0C, 0xD3, 0x04, 0x3E, 0x08, 0x30, 0x04,
                         0x2E, 0x00, 0x26, 0x0B, 0xFB])
# RWAIT/EWAIT/JMP
expect('RWAIT', 0x00DD, [0x7C, 0xB7, 0xC2, 0xDD, 0x00])
expect('EWAIT', 0x00E2, [0x79, 0xFE, 0xFF, 0xC2, 0xE2, 0x00, 0xC3, 0xC6, 0x00])

# --- 5) DMUX: LDA MUXI; INR A; ANI 3; STA MUXI; CPI 1; JZ DMX1; CPI 2; JZ DMX2; CPI 3; JZ DMX3 ---
expect('DMUX диспетч.', 0x00F0, [0x3A, 0x00, 0x80, 0x3C, 0xE6, 0x03, 0x32, 0x00, 0x80,
                                 0xFE, 0x01, 0xCA, 0x13, 0x01,
                                 0xFE, 0x02, 0xCA, 0x22, 0x01,
                                 0xFE, 0x03, 0xCA, 0x2F, 0x01])
# индекс 0: MOV A,B; ANI 0Fh; CALL HSEG; MVI A,1; OUT 1; RET
expect('DMX0', 0x0108, [0x78, 0xE6, 0x0F, 0xCD, 0x40, 0x01, 0x3E, 0x01, 0xD3, 0x01, 0xC9])
# DMX1: MOV A,B; RRC x4; ANI 0Fh; CALL; MVI A,2; OUT; RET
expect('DMX1', 0x0113, [0x78, 0x0F, 0x0F, 0x0F, 0x0F, 0xE6, 0x0F, 0xCD, 0x40, 0x01,
                        0x3E, 0x02, 0xD3, 0x01, 0xC9])
# DMX2: LDA BYTE0; ANI 0Fh; CALL; MVI A,4; OUT; RET
expect('DMX2', 0x0122, [0x3A, 0x01, 0x80, 0xE6, 0x0F, 0xCD, 0x40, 0x01,
                        0x3E, 0x04, 0xD3, 0x01, 0xC9])
# DMX3: LDA BYTE0; RRC x4; ANI 0Fh; CALL; MVI A,8; OUT; RET
expect('DMX3', 0x012F, [0x3A, 0x01, 0x80, 0x0F, 0x0F, 0x0F, 0x0F, 0xE6, 0x0F,
                        0xCD, 0x40, 0x01, 0x3E, 0x08, 0xD3, 0x01, 0xC9])
# HSEG: PUSH H(E5); MOV H,A; MVI L,50h; ADD L; MOV L,A; MVI H,01h; MOV A,M; POP H(E1); OUT 00h; RET
expect('HSEG', 0x0140, [0xE5, 0x67, 0x2E, 0x50, 0x85, 0x6F, 0x26, 0x01, 0x7E,
                        0xE1, 0xD3, 0x00, 0xC9])
# SEGTAB
expect('SEGTAB', 0x0150, [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07,
                          0x7F, 0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71])

# --- 6) границы образа ---
known = sorted(diag)
if known[0] != 0 or known[-1] != 0x015F:
    errors.append('границы образа: %04Xh-%04Xh (ожидалось 0000h-015Fh)'
                  % (known[0], known[-1]))
n = len(known)
print('образ: %04Xh-%04Xh, %d байт' % (known[0], known[-1], n))
print('совпадение с v1 (0000h-008Fh, кроме 2 адресов RXE):',
      'ДА' if all(diag.get(a) == v1.get(a) for a in range(0x0090)
                  if a not in RXE_DELTA) else 'НЕТ')

if errors:
    print('ПРОВАЛЕНО (%d):' % len(errors))
    for e in errors:
        print('  -', e)
    sys.exit(1)
print('ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ: векторы/ISR = v1, вставки и DMUX на местах')
