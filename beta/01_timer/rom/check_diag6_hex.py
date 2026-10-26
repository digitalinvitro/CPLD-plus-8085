#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Верификация uart_echo_diag6.hex против эталона uart_echo_diag5.hex.

Контракт diag6 («монитор SID»):
  0000h-012Ah  == diag5 == diag4 (вектора, ре-арм, ISR целиком, init MAIN до EI)
  012Ah-0141h  НОВЫЙ хвост MAIN: плотный цикл опроса SID (RIM -> дисплей)
  0142h-016Fh  паддинг нулями
  0170h-01DFh  == diag5 == diag4 (DMUX, HSEG, SEGTAB)

Хвост MAIN 012Ah (24 байта):
  SIDLP: RIM;         STA BYTE0;     RLC;     ANI 01h;  MOV B,A;
         JNZ SIDOK;   LDA SSELF;     INR A;   STA SSELF;
  SIDOK: CALL DMUX;   JMP SIDLP
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
d6 = parse(f"{BASE}/uart_echo_diag6.hex")

ok = True

# 1. совпадающие зоны (diag6 vs diag5 И vs diag4 -- двойная сверка)
for lo, hi, what in [(0x000, 0x12A, "вектора+ISR+init MAIN (до EI)"),
                     (0x170, 0x1E0, "DMUX+HSEG+SEGTAB")]:
    for name, ref in (("diag5", d5), ("diag4", d4)):
        diffs = [a for a in range(lo, hi) if ref[a] != d6[a]]
        print(f"[{'OK ' if not diffs else 'FAIL'}] {lo:04X}h-{hi-1:04X}h {what} == {name}: расхождений {len(diffs)}")
        ok &= not diffs

# 2. новый хвост MAIN -- точные ожидания (адреса меток: SIDLP=012Ah, SIDOK=013Ch)
expect = bytes.fromhex(
    "20"                # 012A SIDLP: RIM
    "320180"            # 012B STA BYTE0 (8001h)
    "07"                # 012E RLC                (SID -> бит0)
    "E601"              # 012F ANI 01h
    "47"                # 0131 MOV B,A            (DIG0 = уровень SID)
    "C23C01"            # 0132 JNZ SIDOK (013Ch)
    "3A0680"            # 0135 LDA SSELF (8006h)  -- SID=0: активность
    "3C"                # 0138 INR A
    "320680"            # 0139 STA SSELF
    "CD7001"            # 013C SIDOK: CALL DMUX (0170h)
    "C32A01"            # 013F JMP SIDLP (012Ah)
)
tail = d6[0x12A:0x12A + len(expect)]
print(f"[{'OK ' if tail == expect else 'FAIL'}] хвост MAIN 012Ah: {tail.hex(' ').upper()}")
ok &= tail == expect
pad = d6[0x12A + len(expect):0x170]
print(f"[{'OK ' if pad == bytes(len(pad)) else 'FAIL'}] паддинг {0x12A+len(expect):04X}h-016Fh: {len(pad)} x 00")
ok &= pad == bytes(len(pad))

# 3. суммы/хэши для ридбека владельца
s = sum(d6); c = zlib.crc32(d6) & 0xFFFFFFFF; h = hashlib.sha256(d6).hexdigest()
print(f"\ndiag6: 480 байт, sum={s:04X}h, CRC32(0..1DFh)={c:08X}, SHA256={h[:16]}…")
print(f"Команда владельца:  crc 0 1E0  -> ожидается {c:08X}")
print("\nВЕРДИКТ:", "ПАСС -- diag6 соответствует контракту" if ok else "ЕСТЬ РАСХОЖДЕНИЯ")
raise SystemExit(0 if ok else 1)
