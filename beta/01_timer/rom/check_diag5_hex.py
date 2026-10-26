#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Верификация uart_echo_diag5.hex против эталона uart_echo_diag4.hex.

Контракт diag5:
  0000h-0129h  == diag4 (вектора, ре-арм, ISR целиком, init MAIN до EI)
  012Ah-016Fh  НОВЫЙ хвост MAIN: повторяющийся баннер (BAN/DLAY) + нули
  0170h-01DFh  == diag4 (DMUX, HSEG, SEGTAB)
"""
import os, zlib, hashlib

BASE = os.path.dirname(os.path.abspath(__file__))  # каталог rom/

def parse(path):
    mem = {}
    for line in open(path):
        line = line.strip()
        if not line.startswith(':'):
            continue
        b = bytes.fromhex(line[1:])
        cnt = b[0]; addr = (b[1] << 8) | b[2]
        if b[3] == 0x00:
            for i, v in enumerate(b[4:4+cnt]):
                mem[addr + i] = v
    return bytes(mem[a] for a in range(0x01E0))

d4 = parse(f"{BASE}/uart_echo_diag4.hex")
d5 = parse(f"{BASE}/uart_echo_diag5.hex")

ok = True

# 1. совпадающие зоны
for lo, hi, what in [(0x000, 0x12A, "вектора+ISR+init MAIN (до EI)"),
                     (0x170, 0x1E0, "DMUX+HSEG+SEGTAB")]:
    diffs = [a for a in range(lo, hi) if d4[a] != d5[a]]
    print(f"[{'OK ' if not diffs else 'FAIL'}] {lo:04X}h-{hi-1:04X}h {what}: расхождений {len(diffs)}")
    ok &= not diffs

# 2. новый хвост MAIN -- точные ожидания (asm85-листинг сверен глазами)
expect = bytes.fromhex(
    "79FEFFC22A01"      # 012A BAN: MOV A,C; CPI FFh; JNZ BAN
    "210004"            # 0130 REARM: LXI H,0400h
    "CD7001"            # 0133 DLAY: CALL DMUX
    "2B"                # 0136 DCX H
    "7D"                # 0137 MOV A,L
    "B4"                # 0138 ORA H
    "C23301"            # 0139 JNZ DLAY
    "04"                # 013C INR B
    "163E"              # 013D MVI D,'>'
    "0E0B"              # 013F MVI C,0Bh
    "C32A01"            # 0141 JMP BAN
)
tail = d5[0x12A:0x12A + len(expect)]
print(f"[{'OK ' if tail == expect else 'FAIL'}] хвост MAIN 012Ah: {tail.hex(' ').upper()}")
ok &= tail == expect
pad = d5[0x12A + len(expect):0x170]
print(f"[{'OK ' if pad == bytes(len(pad)) else 'FAIL'}] паддинг {0x12A+len(expect):04X}h-016Fh: {len(pad)} x 00")
ok &= pad == bytes(len(pad))

# 3. суммы/хэши для ридбека владельца
s = sum(d5); c = zlib.crc32(d5) & 0xFFFFFFFF; h = hashlib.sha256(d5).hexdigest()
print(f"\ndiag5: 480 байт, sum={s:04X}h, CRC32(0..1DFh)={c:08X}, SHA256={h[:16]}…")
print(f"Команда владельца:  crc 0 1E0  -> ожидается {c:08X}")
print("\nВЕРДИКТ:", "ПАСС -- diag5 соответствует контракту" if ok else "ЕСТЬ РАСХОЖДЕНИЯ")
raise SystemExit(0 if ok else 1)
