#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Верификация TXSTRESS: HEX<->BIN, DAA-перевод цифр, аудит темпов."""
T = 320e-9  # 8085 @ 3.125 МГц

def check_hex(path, binpath):
    data = {}
    for ln in open(path):
        ln = ln.strip()
        assert ln.startswith(':'), ln
        b = bytes.fromhex(ln[1:])
        assert (sum(b) & 0xFF) == 0, f"CS fail: {ln}"
        cnt, ah, al, typ = b[0], b[1], b[2], b[3]
        if typ == 0:
            addr = (ah << 8) | al
            for i, v in enumerate(b[4:4+cnt]): data[addr+i] = v
        elif typ == 1:
            break
    img = open(binpath, 'rb').read()
    for a, v in sorted(data.items()):
        assert img[a] == v, f"bin mismatch @{a:04X}"
    assert img[:2] == b'\xF3\x11', "нет DI/LXI на 0000h"
    print(f"  {path}: HEX=BIN, CS OK, вход F3 11 (DI; LXI D) OK, байт кода={len(data)}")

def daa_check():
    ok = []
    for n in range(16):
        a = (n + 0x90) & 0xFF
        # DAA
        if (a & 0x0F) > 9 or False: a = (a + 0x06) & 0xFF
        if (a >> 4) > 9: a = (a + 0x60) & 0xFF
        a = (a + 0x40 + (1 if n > 9 else 0)) & 0xFF  # ACI 40h: перенос после DAA
        if (a & 0x0F) > 9: a = (a + 0x06) & 0xFF
        if (a >> 4) > 9: a = (a + 0x60) & 0xFF
        ok.append(chr(a) == "0123456789ABCDEF"[n])
    assert all(ok), ok
    print("  DAA-трюк: все 16 нибблов -> '0'..'F' OK")

def audit():
    print("  Темпы (TX_BOTH=1, оба порта):")
    for name, t_per_byte, note in [
        ("FLOOD ", 42,    "MOV4+OUT10+OUT10+INR4+DCR4+JNZ10"),
        ("SPRINT", 62/2,  "(2x(MOV4+OUT10+OUT10)+DCR4+JNZ10)/2"),
        ("BURST ", 238/16,"(16x(MOV4+OUT10)+DCR4+JNZ10)/16"),
    ]:
        rate = 1 / (t_per_byte * T)
        line1, line156 = 100_000, 156_250
        print(f"    {name} {t_per_byte:7.3f}T = {t_per_byte*T*1e6:6.2f} мкс/Б -> "
              f"{rate:8.0f} Б/с  ({rate/line1*100:5.1f}% линии 1М, "
              f"{rate/line156*100:5.1f}% линии 1.5625М)   [{note}]")
    print("  Темпы (TX_BOTH=0, только 04h):")
    for name, t_per_byte, note in [
        ("FLOOD ", 32,   "MOV4+OUT10+INR4+DCR4+JNZ10"),
        ("SPRINT", 42/2, "(2x(MOV4+OUT10)+DCR4+JNZ10)/2"),
        ("BURST ", 238/16, "без изменений (порт 04h)"),
    ]:
        rate = 1 / (t_per_byte * T)
        print(f"    {name} {t_per_byte:7.3f}T = {t_per_byte*T*1e6:6.2f} мкс/Б -> "
              f"{rate:8.0f} Б/с  ({rate/100_000*100:5.1f}% 1М, "
              f"{rate/156_250*100:5.1f}% 1.5625М)   [{note}]")
    print(f"  Печать строки: 54T/символ = {54*T*1e6:.2f} мкс > кадра (10.0/6.4 мкс) — чисто")
    print(f"  POR-пауза: 16384 x 24T = {16384*24*T*1e3:.0f} мс")

print("== Верификация TXSTRESS ==")
for ver in ('v10', 'v11'):
    check_hex(f'/home/z/my-project/download/txstress_{ver}.hex',
              f'/home/z/my-project/download/txstress_{ver}.bin')
    check_hex(f'/home/z/my-project/download/txstress_{ver}_p04.hex',
              f'/home/z/my-project/download/txstress_{ver}_p04.bin')
daa_check()
audit()
print("== ВСЁ ОК ==")
