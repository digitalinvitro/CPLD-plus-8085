#!/usr/bin/env python3
# verify27.py - статическая верификация monitor27.hex (плата v2.7)
# Проверяет: векторную зону (глушилки EI;RET), таблицы, баннер,
# объём образа (ROM-окно 0000h-7FFFh), контрольные суммы Intel HEX.
import sys

HEX = "monitor27.hex"

def load_hex(path):
    mem = {}
    end = 0
    for lineno, line in enumerate(open(path), 1):
        line = line.strip()
        if not line:
            continue
        assert line.startswith(":"), "строка %d: не Intel HEX" % lineno
        count = int(line[1:3], 16)
        addr = int(line[3:7], 16)
        rtype = int(line[7:9], 16)
        data = bytes.fromhex(line[9:9 + 2 * count])
        cs = (count + (addr >> 8) + (addr & 0xFF) + rtype + sum(data)) & 0xFF
        assert ((int(line[9 + 2 * count:11 + 2 * count], 16) + cs) & 0xFF) == 0, \
            "строка %d: битая контрольная сумма" % lineno
        if rtype == 0:
            for i, b in enumerate(data):
                mem[addr + i] = b
                end = max(end, addr + i + 1)
        else:
            assert rtype == 1, "rtype %d" % rtype
    return mem, end

def word(mem, a):
    return mem.get(a, 0) | (mem.get(a + 1, 0) << 8)

fails = []
def chk(cond, msg):
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)

mem, end = load_hex(HEX)
print("== Образ %s: верх = %04Xh (%d байт) ==" % (HEX, end - 1, end))

chk(mem.get(0) == 0xC3, "0000h: JMP (C3)")
start_addr = word(mem, 1)
chk(0x0100 <= start_addr < 0x8000, "0001h: адрес START = %04Xh" % start_addr)
STUBS = [0x0008, 0x0010, 0x0018, 0x0020, 0x0024, 0x0028, 0x002C,
         0x0030, 0x0034, 0x0038, 0x003C]
names = ["RST1", "RST2", "RST3", "RST4", "TRAP!", "RST5", "RST5.5",
         "RST6", "RST6.5", "RST7", "RST7.5"]
for a, n in zip(STUBS, names):
    ok = mem.get(a) == 0xFB and mem.get(a + 1) == 0xC9
    chk(ok, "%04Xh %s: глушилка EI;RET (FB C9)" % (a, n))
chk(end <= 0x8000, "образ в ROM-окне (<= 7FFFh)")

GTBL = [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07,
        0x7F, 0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71]
chk([mem.get(0x44 + i) for i in range(16)] == GTBL, "0044h: GTBL '0'..'F'")
BITTBL = [0x01, 0x02, 0x04, 0x08]
chk([mem.get(0x54 + i) for i in range(4)] == BITTBL, "0054h: BITTBL")
KEYTBL = [0x0A, 0x0B, 0x0C, 0x0D, 0x07, 0x08, 0x09, 0x0E,
          0x04, 0x05, 0x06, 0x0F, 0x01, 0x02, 0x03, 0x10,
          0x00, 0x11, 0x12, 0xFF]
chk([mem.get(0x58 + i) for i in range(20)] == KEYTBL, "0058h: KEYTBL")
BAN = [0x4D, 0x4F, 0x4E, 0x32, 0x37, 0x0D, 0x0A, 0x00]
chk([mem.get(0x6C + i) for i in range(8)] == BAN, "006Ch: баннер MON27\\r\\n")
RAMPAT = [0x00, 0x3F, 0xFF, 0x71, 0x55, 0x6D, 0xAA, 0x77]
chk([mem.get(0x74 + i) for i in range(8)] == RAMPAT, "0074h: RAMPAT")

# точечный дизасм-контроль ключевых мест (ручные ожидания байтов)
def at(a, expect, msg):
    got = [mem.get(a + i) for i in range(len(expect))]
    chk(got == expect, msg + " " + " ".join("%02X" % x for x in got))

# START: DI, LXI SP,FFE8h (31 E8 FF: LXI SP = 31h, мл=E8, ст=FF)
sa = start_addr
at(sa, [0xF3, 0x31, 0xE8, 0xFF], "START %04Xh: DI; LXI SP,FFE8h =" % sa)
# TXB1-цикл: IN 05h (DB 05), ANI 02h (E6 02), JZ (CA)
txb = None
for a in range(0x0100, end - 3):
    if mem.get(a) == 0xDB and mem.get(a + 1) == 0x05 and \
       mem.get(a + 2) == 0xE6 and mem.get(a + 3) == 0x02 and \
       mem.get(a + 4) == 0xCA:
        txb = a
        break
chk(txb is not None, "TXRDY-цикл найден: IN 05h / ANI 02h / JZ")
# RXD: RIM (20h), ORA A (B7), JM (FA) - поиск цепочки
rxw = None
for a in range(0x0100, end - 2):
    if mem.get(a) == 0x20 and mem.get(a + 1) == 0xB7 and mem.get(a + 2) == 0xFA:
        rxw = a
        break
chk(rxw is not None, "RXW-цикл найден: RIM / ORA A / JM")
# LOADM-статический глиф 'L': 3E 38 (MVI A,38h)
l38 = [a for a in range(0x0100, end - 1)
       if mem.get(a) == 0x3E and mem.get(a + 1) == 0x38]
chk(len(l38) >= 1, "MVI A,38h ('L' глиф загрузчика) найден")
# RAMT: SHLD ADDRL = 22h EB FF (L=FFEB первый)
shld = [a for a in range(0x0100, end - 2)
        if mem.get(a) == 0x22 and mem.get(a + 1) == 0xEB and mem.get(a + 2) == 0xFF]
chk(len(shld) == 1, "RAMT: SHLD ADDRL (22 EB FF) - ровно один")


# --- XSTREAM v1: экран -> UART ---
# XSEND-шапка: MVI A,0A5h / OUT 04h / NOP x4 / MVI A,5Ah / OUT 04h / NOP x4
#              / LDA FFFAh / OUT 04h
xs = None
for a in range(0x0100, end - 20):
    if (mem.get(a) == 0x3E and mem.get(a+1) == 0xA5 and mem.get(a+2) == 0xD3
            and mem.get(a+3) == 0x04 and mem.get(a+4) == 0x00
            and mem.get(a+5) == 0x00 and mem.get(a+6) == 0x00
            and mem.get(a+7) == 0x00 and mem.get(a+8) == 0x3E
            and mem.get(a+9) == 0x5A and mem.get(a+10) == 0xD3
            and mem.get(a+11) == 0x04 and mem.get(a+12) == 0x00
            and mem.get(a+13) == 0x00 and mem.get(a+14) == 0x00
            and mem.get(a+15) == 0x00 and mem.get(a+16) == 0x3A
            and mem.get(a+17) == 0xFA and mem.get(a+18) == 0xFF
            and mem.get(a+19) == 0xD3):
        xs = a
        break
chk(xs is not None, "XSEND-шапка найдена: A5/OUT/NOPx4/5A/OUT/LDA XSSEQ/OUT")
# XSCHK: MOV C,A / LDA XSPASS(FFFB) / ADD C / STA XSPASS / CPI 47h / JC
xschk = [a for a in range(0x0100, end - 6)
         if mem.get(a) == 0x4F and mem.get(a+1) == 0x3A and mem.get(a+2) == 0xFB
         and mem.get(a+3) == 0xFF and mem.get(a+4) == 0x81
         and mem.get(a+5) == 0x32 and mem.get(a+6) == 0xFB
         and mem.get(a+7) == 0xFF and mem.get(a+8) == 0xFE
         and mem.get(a+9) == 0x47 and mem.get(a+10) == 0xDA]
chk(len(xschk) == 1, "XSCHK (MOV C/LDA FFFB/ADD/STA/CPI 71/JC) - ровно один")
# XBLANK: LXI H,B000h / LXI B,2000 (07D0)
xb = [a for a in range(0x0100, end - 5)
      if mem.get(a) == 0x21 and mem.get(a+1) == 0x00 and mem.get(a+2) == 0xB0
      and mem.get(a+3) == 0x01 and mem.get(a+4) == 0xD0 and mem.get(a+5) == 0x07]
chk(len(xb) == 1, "XBLANK: LXI H,B000h + LXI B,2000 - ровно один")
# сайты тика: MVI A,01h / CALL (скан, NKEY, MNR1) >= 3; MVI A,02h / CALL (BUNIT, WDN, MNR3) >= 3
t1 = sum(1 for a in range(0x0100, end - 1)
         if mem.get(a) == 0x3E and mem.get(a+1) == 0x01 and mem.get(a+2) == 0xCD)
t2 = sum(1 for a in range(0x0100, end - 1)
         if mem.get(a) == 0x3E and mem.get(a+1) == 0x02 and mem.get(a+2) == 0xCD)
chk(t1 >= 3, "сайты тика MVI A,1 / CALL XSCHK: %d (>= 3)" % t1)
chk(t2 >= 3, "сайты тика MVI A,XS_QINC / CALL XSCHK: %d (>= 3)" % t2)
# LOADM вход чистит LACC: XRA A / STA FFFA / STA FFFD
lent = [a for a in range(0x0100, end - 5)
        if mem.get(a) == 0xAF and mem.get(a+1) == 0x32 and mem.get(a+2) == 0xFA
        and mem.get(a+3) == 0xFF and mem.get(a+4) == 0x32
        and mem.get(a+5) == 0xFD and mem.get(a+6) == 0xFF]
chk(len(lent) == 1, "LOADM-вход: XRA A/STA LST/STA LACC (фикс v1.0) - ровно один")
# демо-строка в ROM: 'XSTREAM v1.0'
sig = bytes([0x58, 0x53, 0x54, 0x52, 0x45, 0x41, 0x4D, 0x20, 0x76, 0x31])
dem = any(mem.get(a + i) == sig[i] for a in range(0x0100, end - 10)
          for i in range(10))
dem = any(all(mem.get(a + i) == sig[i] for i in range(10))
          for a in range(0x0100, end - 10))
chk(dem, "демо-экран: строка 'XSTREAM v1.0' в ROM")

print()
if fails:
    print("ВЕРДИКТ: FAIL (%d)" % len(fails))
    sys.exit(1)
print("ВЕРДИКТ: PASS")
