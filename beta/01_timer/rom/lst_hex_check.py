#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сверка hex <-> lst для образов asm85 (формат: '  NN  AAAA: XX XX')."""
import os, re, sys

def parse_hex(path):
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
    return mem

def check(lst_path, hex_path):
    mem = parse_hex(hex_path)
    rx = re.compile(r'^\s*\d+\s+([0-9A-F]{4}):\s+((?:[0-9A-F]{2}(?:\s|$))+)', re.M)
    n = bad = 0
    covered = set()
    for m in rx.finditer(open(lst_path, errors='replace').read()):
        addr = int(m.group(1), 16)
        for i, tok in enumerate(m.group(2).split()):
            v = int(tok, 16); n += 1
            covered.add(addr + i)
            if mem.get(addr + i) != v:
                bad += 1
                print(f"  DIFF @{addr+i:04X}h: lst={v:02X} hex={mem.get(addr+i)}")
    # непокрытые листингом байты hex обязаны быть нулевым паддингом
    pad_bad = [a for a in mem if a not in covered and mem[a] != 0x00]
    if pad_bad:
        bad += len(pad_bad)
        print(f"  ПАДДИНГ-БАЙТЫ НЕ НУЛЕВЫЕ: {', '.join(f'{a:04X}h' for a in pad_bad)}")
    print(f"  {lst_path.split('/')[-1]}: листинг {n} байт, hex {len(mem)} байт "
          f"(паддинг {len(mem)-len(covered)}), расхождений {bad}")
    return bad == 0 and len(mem) == 480 and len(covered) == n

if __name__ == '__main__':
    base = os.path.dirname(os.path.abspath(__file__))
    ok = True
    for name in ["uart_echo_diag6", "uart_echo_diag5", "uart_echo_diag4"]:
        ok &= check(f"{base}/{name}.lst", f"{base}/{name}.hex")
    print("ВЕРДИКТ:", "hex==lst ПАСС" if ok else "ЕСТЬ РАСХОЖДЕНИЯ")
    sys.exit(0 if ok else 1)
