#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_hex.py — независимая сверка собранных .hex с ручным эталоном.

Эталон рассчитан вручную по карте опкодов Intel 8085 (не ассемблером):
  0000: JMP 0080h | 003C: JMP 0040h (вектор RST 7.5) | ISR с 0040h | MAIN с 0080h.
Плюс: контроль checksum каждой записи Intel HEX и структуры EOF.

v2: в ISR НЕТ PUSH B/POP B — счётчик мигания B:C обязан жить между
прерываниями; в v1 POP B каждую квитанцию восстанавливал исходные
KB:KA и мигание никогда не срабатывало (баг найден по симптомам
«тон есть, g+dp горят, мигания нет»).
"""
import sys

HEXCOLS = {'tone': 'timer_test_tone.hex', 'blink': 'timer_test_blink.hex'}

# ---- ручной эталон (tone) ----
REF_TONE = (
    bytes([0xC3, 0x80, 0x00])                                  # 0000 JMP 0080h
    + bytes(0x00 for _ in range(0x3B - 0x03 + 1))              # NOP-заполнение
    + bytes([0xC3, 0x40, 0x00])                                # 003C JMP ISR (RST 7.5)
    + bytes([0x00])                                            # 003F
    + bytes([0xF5])                                            # PUSH PSW (v2: БЕЗ PUSH B!)
    + bytes([0x3A, 0x01, 0x80])                                # LDA 8001h (DIGST)
    + bytes([0xEE, 0x10])                                      # XRI 10h (SND)
    + bytes([0x32, 0x01, 0x80])                                # STA 8001h
    + bytes([0xD3, 0x01])                                      # OUT 01h
    + bytes([0x0D])                                            # DCR C
    + bytes([0xC2, 0x61, 0x00])                                # JNZ 0061h
    + bytes([0x0E, 0x74])                                      # MVI C,74h (KA=116)
    + bytes([0x05])                                            # DCR B
    + bytes([0xC2, 0x61, 0x00])                                # JNZ 0061h
    + bytes([0x06, 0x04])                                      # MVI B,04h (KB=4)
    + bytes([0x3A, 0x00, 0x80])                                # LDA 8000h (SEGST)
    + bytes([0xEE, 0x40])                                      # XRI 40h ('g')
    + bytes([0x32, 0x00, 0x80])                                # STA 8000h
    + bytes([0xD3, 0x00])                                      # OUT 00h
    + bytes([0x3E, 0x14])                                      # MVI A,14h (N=20)
    + bytes([0xD3, 0x04])                                      # OUT 04h (ре-арм)
    + bytes([0xF1, 0xFB, 0xC9])                                # POP PSW, EI, RET (v2: БЕЗ POP B!)
    + bytes(0x00 for _ in range(0x80 - 0x68))                  # NOP до MAIN
    + bytes([0x31, 0xFF, 0xFF])                                # LXI SP,FFFFh
    + bytes([0x3E, 0xC0])                                      # MVI A,C0h ('g'+dp)
    + bytes([0x32, 0x00, 0x80])                                # STA SEGST
    + bytes([0xD3, 0x00])                                      # OUT 00h
    + bytes([0x3E, 0x0F])                                      # MVI A,0Fh (все разряды)
    + bytes([0x32, 0x01, 0x80])                                # STA DIGST
    + bytes([0xD3, 0x01])                                      # OUT 01h
    + bytes([0x01, 0x74, 0x04])                                # LXI B,0474h (B=4,C=116)
    + bytes([0x3E, 0x14])                                      # MVI A,14h
    + bytes([0xD3, 0x04])                                      # OUT 04h
    + bytes([0x3E, 0x1B])                                      # MVI A,1Bh (SIM-слово)
    + bytes([0x30])                                            # SIM
    + bytes([0xFB])                                            # EI
    + bytes([0x76])                                            # HLT
    + bytes([0xC3, 0x9C, 0x00])                                # JMP 009Ch (HLT-цикл)
)

REF_BLINK = (
    REF_TONE[:0x40]
    + bytes([0xF5])                                            # PUSH PSW (v2: БЕЗ PUSH B!)
    + bytes([0x0D])                                            # DCR C
    + bytes([0xC2, 0x57, 0x00])                                # JNZ 0057h
    + bytes([0x0E, 0x74])                                      # MVI C,74h
    + bytes([0x05])                                            # DCR B
    + bytes([0xC2, 0x57, 0x00])                                # JNZ 0057h
    + bytes([0x06, 0x04])                                      # MVI B,04h
    + bytes([0x3A, 0x00, 0x80])                                # LDA 8000h
    + bytes([0xEE, 0x40])                                      # XRI 40h
    + bytes([0x32, 0x00, 0x80])                                # STA 8000h
    + bytes([0xD3, 0x00])                                      # OUT 00h
    + bytes([0x3E, 0x14, 0xD3, 0x04])                          # MVI A,14h, OUT 04h
    + bytes([0xF1, 0xFB, 0xC9])                                # POP PSW, EI, RET (v2: БЕЗ POP B!)
    + bytes(0x00 for _ in range(0x80 - 0x5E))
    + REF_TONE[0x80:]
)


def read_ihex(path):
    mem = {}
    eof_seen = False
    for n, line in enumerate(open(path), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(':'):
            raise SystemExit('%s:%d запись не начинается с ":"' % (path, n))
        raw = bytes.fromhex(line[1:])
        cnt, ah, al, typ = raw[0], raw[1], raw[2], raw[3]
        payload = raw[4:4 + cnt]
        crc = raw[4 + cnt]
        if len(raw) != cnt + 5:
            raise SystemExit('%s:%d длина записи не сходится' % (path, n))
        if ((cnt + ah + al + typ + sum(payload) + crc) & 0xFF) != 0:
            raise SystemExit('%s:%d НЕВЕРНАЯ контрольная сумма' % (path, n))
        if typ == 1:
            if cnt != 0:
                raise SystemExit('%s:%d EOF-запись с данными' % (path, n))
            eof_seen = True
            continue
        if typ != 0:
            raise SystemExit('%s:%d неожиданный тип записи %d' % (path, n))
        base = (ah << 8) | al
        for i, b in enumerate(payload):
            mem[base + i] = b
    if not eof_seen:
        raise SystemExit('%s: нет EOF-записи' % path)
    return mem


def main():
    ok = True
    for kind, path in HEXCOLS.items():
        mem = read_ihex(path)
        ref = REF_TONE if kind == 'tone' else REF_BLINK
        addrs = sorted(mem)
        lo, hi = addrs[0], addrs[-1]
        if lo != 0x0000 or hi != 0x009F:
            print('[FAIL] %s: диапазон %04Xh-%04Xh, ожидался 0000h-009Fh' % (path, lo, hi))
            ok = False
            continue
        blob = bytes(mem[a] for a in range(lo, hi + 1))
        if blob == ref:
            print('[ OK ] %s: %d байт, побайтово совпадает с ручным эталоном' % (path, len(blob)))
        else:
            print('[FAIL] %s: расхождение с эталоном:' % path)
            for i, (a, b, r) in enumerate(zip(range(lo, hi + 1), blob, ref)):
                if b != r:
                    print('   %04Xh: в hex %02X, в эталоне %02X' % (a, b, r))
            ok = False
    # ключевые контрольные точки независимо от эталона
    checks = [
        ('tone', 0x0000, 0xC3), ('tone', 0x0001, 0x80), ('tone', 0x003C, 0xC3),
        ('tone', 0x003D, 0x40), ('tone', 0x0040, 0xF5),
        ('tone', 0x0041, 0x3A),                                    # v2: LDA сразу после PUSH PSW (нет C5)
        ('tone', 0x0061, 0x3E), ('tone', 0x0063, 0xD3), ('tone', 0x0064, 0x04),
        ('tone', 0x0065, 0xF1),                                    # v2: POP PSW после ре-арма (нет C1)
        ('tone', 0x0066, 0xFB), ('tone', 0x009A, 0x30), ('tone', 0x009C, 0x76),
        ('blink', 0x003D, 0x40), ('blink', 0x0040, 0xF5), ('blink', 0x0041, 0x0D),
        ('blink', 0x0057, 0x3E), ('blink', 0x005B, 0xF1),
    ]
    for kind, addr, val in checks:
        mem = read_ihex(HEXCOLS[kind])
        if mem.get(addr) != val:
            print('[FAIL] %s: %04Xh = %02X, ожидалось %02X' % (kind, addr, mem.get(addr), val))
            ok = False
    if ok:
        print('ВЕРИФИКАЦИЯ ПРОЙДЕНА: оба образа корректны (checksum + эталон + точки).')
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
