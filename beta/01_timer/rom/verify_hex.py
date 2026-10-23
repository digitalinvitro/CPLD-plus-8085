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

v3 (2026-10-23): + UART-образы (задание «таймер как задатчик бодрейта»):
  uart  — timer_test_uart.hex: ISR-автомат «1 прерывание = 1 бит»,
          ре-арм в самом векторе 003Ch (MVI A,N / OUT TMRP), фазы в C
          (0Bh кадр / 0Ah старт / 09h..02h данные / 01h стоп+подготовка
          следующего / 0FFh покой); MAIN с 00A0h; MSG с 00C1h;
          эталон для TMR_N=8 (2400 бод), варианты -D сверяются --disasm.
  usw   — uart_sw_test.hex: полностью софтверный референс (бит = 1042
          такта: LXI H,40 + 2 NOP + цикл DCX H), кадр 10 бит в паре DE.
"""
import sys

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

# ---- ручной эталон (uart, TMR_N=8): ISR-автомат, ре-арм в векторе ----
REF_UART = (
    bytes([0xC3, 0xA0, 0x00])                                  # 0000 JMP 00A0h (MAIN)
    + bytes(0x00 for _ in range(0x3B - 0x03 + 1))              # NOP-заполнение
    # вектор 003Ch занят ре-армом ЦЕЛИКОМ (без JMP): период = N x Q ровно
    + bytes([0x3E, 0x08])                                      # 003C MVI A,08h (TMR_N=8 -> 2400)
    + bytes([0xD3, 0x04])                                      # 003E OUT 04h (ре-арм ~13 мкс от фронта)
    # автомат: 1 прерывание = 1 бит (регистры ISR: C фаза, D сдвиговый,
    # E пауза, HL указатель MSG; MAIN живёт в HLT -- сохранять нечего)
    + bytes([0x79])                                            # 0040 MOV A,C
    + bytes([0xFE, 0xFF])                                      # 0041 CPI 0FFh (покой?)
    + bytes([0xCA, 0x7C, 0x00])                                # 0043 JZ 007Ch (IDLE)
    + bytes([0x0D])                                            # 0046 DCR C
    + bytes([0x79])                                            # 0047 MOV A,C
    + bytes([0xFE, 0x0A])                                      # 0048 CPI 0Ah (старт?)
    + bytes([0xCA, 0x60, 0x00])                                # 004A JZ 0060h (START)
    + bytes([0xFE, 0x01])                                      # 004D CPI 1 (стоп?)
    + bytes([0xCA, 0x66, 0x00])                                # 004F JZ 0066h (STOPB)
    + bytes([0x7A])                                            # 0052 MOV A,D
    + bytes([0x0F])                                            # 0053 RRC (A7 <- D0)
    + bytes([0xE6, 0x80])                                      # 0054 ANI 80h
    + bytes([0xF6, 0x40])                                      # 0056 ORI 40h (SSE; MSE=0 -- маски целы)
    + bytes([0x30])                                            # 0058 SIM
    + bytes([0x37])                                            # 0059 STC (единицы сверху)
    + bytes([0x7A])                                            # 005A MOV A,D
    + bytes([0x1F])                                            # 005B RAR (D >>= 1, D7 <- 1)
    + bytes([0x57])                                            # 005C MOV D,A
    + bytes([0xC3, 0x8A, 0x00])                                # 005D JMP 008Ah (IRET)
    + bytes([0x3E, 0x40])                                      # 0060 MVI A,40h (старт-бит, SOD=0)
    + bytes([0x30])                                            # 0062 SIM
    + bytes([0xC3, 0x8A, 0x00])                                # 0063 JMP IRET
    + bytes([0x3E, 0xC0])                                      # 0066 MVI A,0C0h (стоп-бит, SOD=1)
    + bytes([0x30])                                            # 0068 SIM
    + bytes([0x23])                                            # 0069 INX H (кадры вплотную)
    + bytes([0x7E])                                            # 006A MOV A,M
    + bytes([0xB7])                                            # 006B ORA A (00h = конец строки)
    + bytes([0xCA, 0x75, 0x00])                                # 006C JZ 0075h (ESTR)
    + bytes([0x57])                                            # 006F MOV D,A (след. байт заранее)
    + bytes([0x0E, 0x0B])                                      # 0070 MVI C,0Bh (00h не возникает)
    + bytes([0xC3, 0x8A, 0x00])                                # 0072 JMP IRET
    + bytes([0x0E, 0xFF])                                      # 0075 MVI C,0FFh (покой)
    + bytes([0x1E, 0x0D])                                      # 0077 MVI E,0Dh (GAPN=13 бит)
    + bytes([0xC3, 0x8A, 0x00])                                # 0079 JMP IRET
    + bytes([0x3E, 0xC0])                                      # 007C MVI A,0C0h (покой, SOD=1)
    + bytes([0x30])                                            # 007E SIM
    + bytes([0x1D])                                            # 007F DCR E
    + bytes([0xC2, 0x8A, 0x00])                                # 0080 JNZ IRET
    + bytes([0x21, 0xC1, 0x00])                                # 0083 LXI H,00C1h (MSG)
    + bytes([0x7E])                                            # 0086 MOV A,M (preload D)
    + bytes([0x57])                                            # 0087 MOV D,A
    + bytes([0x0E, 0x0B])                                      # 0088 MVI C,0Bh
    + bytes([0xFB])                                            # 008A EI
    + bytes([0xC9])                                            # 008B RET
    + bytes(0x00 for _ in range(0xA0 - 0x8C))                  # NOP до MAIN
    + bytes([0x31, 0xFF, 0xFF])                                # 00A0 LXI SP,FFFFh
    + bytes([0x3E, 0xC0])                                      # 00A3 MVI A,C0h (SOD=1, гасим BREAK)
    + bytes([0x30])                                            # 00A5 SIM
    + bytes([0x3E, 0x80])                                      # 00A6 MVI A,80h (маячок «....»)
    + bytes([0xD3, 0x00])                                      # 00A8 OUT 00h
    + bytes([0x3E, 0x0F])                                      # 00AA MVI A,0Fh
    + bytes([0xD3, 0x01])                                      # 00AC OUT 01h
    + bytes([0x3E, 0x08])                                      # 00AE MVI A,08h (TMR_N)
    + bytes([0xD3, 0x04])                                      # 00B0 OUT 04h (пуск таймера)
    + bytes([0x3E, 0x1B])                                      # 00B2 MVI A,1Bh (SIMW)
    + bytes([0x30])                                            # 00B4 SIM
    + bytes([0x21, 0xC1, 0x00])                                # 00B5 LXI H,00C1h (MSG)
    + bytes([0x7E])                                            # 00B8 MOV A,M (первый байт заранее)
    + bytes([0x57])                                            # 00B9 MOV D,A
    + bytes([0x0E, 0x0B])                                      # 00BA MVI C,0Bh
    + bytes([0xFB])                                            # 00BC EI
    + bytes([0x76])                                            # 00BD HLT
    + bytes([0xC3, 0xBD, 0x00])                                # 00BE JMP 00BDh (HLT-цикл)
    + bytes([0x54, 0x49, 0x4D, 0x45, 0x52, 0x2D, 0x55, 0x41])  # 00C1 'TIMER-UA
    + bytes([0x52, 0x54, 0x20, 0x4F, 0x4B])                    # RT OK'
    + bytes([0x0D, 0x0A, 0x00])                                # CR LF NUL
)

# ---- ручной эталон (usw): полностью софтверный UART (бит = 1042 такта) ----
REF_USW = (
    bytes([0xC3, 0x06, 0x00])                                  # 0000 JMP 0006h (MAIN)
    + bytes([0x00, 0x00, 0x00])                                # 0003 NOP
    + bytes([0xF3])                                            # 0006 DI
    + bytes([0x3E, 0xC0])                                      # 0007 MVI A,C0h (SOD=1)
    + bytes([0x30])                                            # 0009 SIM
    + bytes([0x3E, 0x1F])                                      # 000A MVI A,1Fh (маскировать ВСЁ)
    + bytes([0x30])                                            # 000C SIM
    + bytes([0x3E, 0x80])                                      # 000D MVI A,80h («....»)
    + bytes([0xD3, 0x00])                                      # 000F OUT 00h
    + bytes([0x3E, 0x0F])                                      # 0011 MVI A,0Fh
    + bytes([0xD3, 0x01])                                      # 0013 OUT 01h
    + bytes([0x31, 0xFF, 0xFF])                                # 0015 LXI SP,FFFFh
    + bytes([0x21, 0x62, 0x00])                                # 0018 LXI H,0062h (MSG)
    + bytes([0x7E])                                            # 001B MOV A,M
    + bytes([0xB7])                                            # 001C ORA A
    + bytes([0xCA, 0x28, 0x00])                                # 001D JZ 0028h (SWGAP)
    + bytes([0x4F])                                            # 0020 MOV C,A
    + bytes([0xCD, 0x2E, 0x00])                                # 0021 CALL 002Eh (TXBYTE)
    + bytes([0x23])                                            # 0024 INX H
    + bytes([0xC3, 0x1B, 0x00])                                # 0025 JMP 001Bh (SWNXT)
    + bytes([0xCD, 0x58, 0x00])                                # 0028 CALL 0058h (DLGAP)
    + bytes([0xC3, 0x18, 0x00])                                # 002B JMP 0018h (SWLP)
    + bytes([0x79])                                            # 002E MOV A,C
    + bytes([0x87])                                            # 002F ADD A (CY=d7, старт=0)
    + bytes([0x5F])                                            # 0030 MOV E,A
    + bytes([0x3E, 0x02])                                      # 0031 MVI A,02h (стоп=1 в бите 9)
    + bytes([0xD2, 0x38, 0x00])                                # 0033 JNC 0038h (TXB1)
    + bytes([0xF6, 0x01])                                      # 0036 ORI 1 (d7)
    + bytes([0x57])                                            # 0038 MOV D,A
    + bytes([0x06, 0x0A])                                      # 0039 MVI B,0Ah (10 бит)
    + bytes([0x7B])                                            # 003B MOV A,E
    + bytes([0xE6, 0x01])                                      # 003C ANI 1
    + bytes([0x0F])                                            # 003E RRC (A7 <- бит)
    + bytes([0xF6, 0x40])                                      # 003F ORI 40h
    + bytes([0x30])                                            # 0041 SIM
    + bytes([0x7A])                                            # 0042 MOV A,D
    + bytes([0x1F])                                            # 0043 RAR
    + bytes([0x57])                                            # 0044 MOV D,A
    + bytes([0x7B])                                            # 0045 MOV A,E
    + bytes([0x1F])                                            # 0046 RAR
    + bytes([0x5F])                                            # 0047 MOV E,A
    + bytes([0x21, 0x28, 0x00])                                # 0048 LXI H,0028h (40 итераций)
    + bytes([0x00])                                            # 004B NOP
    + bytes([0x00])                                            # 004C NOP
    + bytes([0x2B])                                            # 004D DCX H
    + bytes([0x7C])                                            # 004E MOV A,H
    + bytes([0xB5])                                            # 004F ORA L
    + bytes([0xC2, 0x4D, 0x00])                                # 0050 JNZ 004Dh
    + bytes([0x05])                                            # 0053 DCR B
    + bytes([0xC2, 0x3B, 0x00])                                # 0054 JNZ 003Bh (TXLP)
    + bytes([0xC9])                                            # 0057 RET
    + bytes([0x01, 0x32, 0x02])                                # 0058 LXI B,0232h (562 итерации)
    + bytes([0x0B])                                            # 005B DCX B
    + bytes([0x78])                                            # 005C MOV A,B
    + bytes([0xB1])                                            # 005D ORA C
    + bytes([0xC2, 0x5B, 0x00])                                # 005E JNZ 005Bh
    + bytes([0xC9])                                            # 0061 RET
    + bytes([0x54, 0x49, 0x4D, 0x45, 0x52, 0x2D, 0x55, 0x41])  # 0062 'TIMER-UA
    + bytes([0x52, 0x54, 0x20, 0x4F, 0x4B])                    # RT OK'
    + bytes([0x0D, 0x0A, 0x00])                                # CR LF NUL
)

HEXCOLS = {
    'tone':  ('timer_test_tone.hex',  REF_TONE,  0x009F),
    'blink': ('timer_test_blink.hex', REF_BLINK, 0x009F),
    'uart':  ('timer_test_uart.hex',  REF_UART,  0x00D0),
    'usw':   ('uart_sw_test.hex',     REF_USW,   0x0071),
}


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
    for kind, (path, ref, hi) in HEXCOLS.items():
        mem = read_ihex(path)
        addrs = sorted(mem)
        lo, top = addrs[0], addrs[-1]
        if lo != 0x0000 or top != hi:
            print('[FAIL] %s: диапазон %04Xh-%04Xh, ожидался 0000h-%04Xh'
                  % (path, lo, top, hi))
            ok = False
            continue
        blob = bytes(mem[a] for a in range(lo, top + 1))
        if blob == ref:
            print('[ OK ] %s: %d байт, побайтово совпадает с ручным эталоном'
                  % (path, len(blob)))
        else:
            print('[FAIL] %s: расхождение с эталоном:' % path)
            for i, (a, b, r) in enumerate(zip(range(lo, top + 1), blob, ref)):
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
        # uart: ре-арм в самом векторе, N=8, EI/RET автомата, HLT, 'T' в MSG
        ('uart', 0x0001, 0xA0), ('uart', 0x003C, 0x3E), ('uart', 0x003D, 0x08),
        ('uart', 0x003E, 0xD3), ('uart', 0x003F, 0x04), ('uart', 0x0040, 0x79),
        ('uart', 0x0043, 0xCA), ('uart', 0x0052, 0x7A), ('uart', 0x0058, 0x30),
        ('uart', 0x0060, 0x3E), ('uart', 0x0061, 0x40), ('uart', 0x0066, 0x3E),
        ('uart', 0x0067, 0xC0), ('uart', 0x0069, 0x23),            # INX H: кадры вплотную
        ('uart', 0x007C, 0x3E), ('uart', 0x008A, 0xFB), ('uart', 0x008B, 0xC9),
        ('uart', 0x00A0, 0x31), ('uart', 0x00BD, 0x76), ('uart', 0x00C1, 0x54),
        ('uart', 0x00CE, 0x0D), ('uart', 0x00CF, 0x0A), ('uart', 0x00D0, 0x00),
        # usw: DI, маскировать ВСЁ, LXI H,40 (пауза), LXI B,562, 'T' в MSG
        ('usw', 0x0001, 0x06), ('usw', 0x0006, 0xF3), ('usw', 0x000A, 0x3E),
        ('usw', 0x000B, 0x1F), ('usw', 0x0021, 0xCD), ('usw', 0x0031, 0x3E),
        ('usw', 0x0039, 0x06), ('usw', 0x003A, 0x0A), ('usw', 0x0048, 0x21),
        ('usw', 0x0049, 0x28), ('usw', 0x0058, 0x01), ('usw', 0x0059, 0x32),
        ('usw', 0x005A, 0x02), ('usw', 0x0062, 0x54), ('usw', 0x006F, 0x0D),
        ('usw', 0x0070, 0x0A), ('usw', 0x0071, 0x00),
    ]
    for kind, addr, val in checks:
        mem = read_ihex(HEXCOLS[kind][0])
        if mem.get(addr) != val:
            print('[FAIL] %s: %04Xh = %02X, ожидалось %02X' % (kind, addr, mem.get(addr), val))
            ok = False
    if ok:
        print('ВЕРИФИКАЦИЯ ПРОЙДЕНА: все 4 образа корректны (checksum + эталон + точки).')
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
