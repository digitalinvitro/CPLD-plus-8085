#!/usr/bin/env python3
# verify_tm.py - статическая верификация fw_monitor_ACdE_tm_xstream_v1_1.hex
# (плата v2.8, CPLD v28.5 с таймером). Проверяет: Intel HEX (контрольные
# суммы), векторную зону (RST 7.5 = обработчик таймера, прочие - глушилки),
# таблицы, операции таймера OUT 06h / SIM-маски, шапку кадра xstream,
# объём образа (ROM-окно 0000h-7FFFh).
import sys

HEX = "fw_monitor_ACdE_tm_xstream_v1_1.hex"
fails = []

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

def chk(name, cond, detail=""):
    print(("OK   " if cond else "FAIL ") + name + (" - " + detail if detail else ""))
    if not cond:
        fails.append(name)

mem, end = load_hex(HEX)
rom = bytes(mem.get(a, 0) for a in range(end))

print("образ: %d байт (0..%04Xh), ROM-окно 0000h-7FFFh: %s" %
      (end, end - 1, "OK" if end <= 0x8000 else "ПЕРЕПОЛНЕНИЕ"))
if end > 0x8000:
    fails.append("объём")

def word(a):
    return rom[a] | (rom[a + 1] << 8)

chk("JMP START @0000", rom[0] == 0xC3 and word(1) >= 0x0100,
    "%02X %04Xh" % (rom[0], word(1)))

# векторная зона: RST1-7, TRAP, RST5.5/6.5 = глушилки F3 C9 (EI;RET)
for va in (0x08, 0x10, 0x18, 0x20, 0x24, 0x28, 0x2C, 0x30, 0x34, 0x38):
    chk("глушилка EI;RET @%04Xh" % va, rom[va] == 0xFB and rom[va + 1] == 0xC9)

# RST 7.5 (003Ch) = JMP TMISR - НЕ глушилка (таймер v28.5)
chk("RST 7.5 @003Ch = JMP", rom[0x3C] == 0xC3, "цель %04Xh" % word(0x3D))
tmi = word(0x3D)
chk("TMISR: PUSH PSW + DCR E",
    rom[tmi] == 0xF5 and rom[tmi + 1] == 0x1D, "счётчик слотов в E")

# таблицы
GTBL = [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07,
        0x7F, 0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71]
chk("GTBL (глифы 0-F) @0044h", list(rom[0x44:0x54]) == GTBL)
chk("BITTBL @0054h", list(rom[0x54:0x58]) == [1, 2, 4, 8])
KEYTBL = [0x0A, 0x0B, 0x0C, 0x0D, 0x07, 0x08, 0x09, 0x0E,
          0x04, 0x05, 0x06, 0x0F, 0x01, 0x02, 0x03, 0x10,
          0x00, 0x11, 0x12, 0xFF]
chk("KEYTBL @0058h", list(rom[0x58:0x6C]) == KEYTBL)
chk("баннер ACDE-TM", b"ACDE-TM" in rom)

# таймер: OUT 06h (D3 06) - арм/стоп/2 ре-арма
n_out06 = sum(1 for i in range(len(rom) - 1) if rom[i] == 0xD3 and rom[i + 1] == 0x06)
chk("OUT 06h >= 4 (TMON/TMOFF/2 ре-арма ISR)", n_out06 >= 4, "найдено %d" % n_out06)
chk("MVI A,78h + SIM (маски+сброс защёлки)", b"\x3E\x78\x30" in rom)
chk("MVI A,68h + SIM (снята маска 7.5)", b"\x3E\x68\x30" in rom)
chk("MVI A,14 + OUT (N=14 dec = 0Eh, 56 мкс)", b"\x3E\x0E\xD3\x06" in rom)
chk("MVI A,0 + OUT (стоп)", b"\xAF\xD3\x06" in rom)
chk("MVI E,6 (перезарядка слота)", b"\x1E\x06" in rom)

# xstream: шапка кадра A5 5A [SEQ], живой счётчик
chk("MVI A,0A5h (шапка кадра)", b"\x3E\xA5" in rom)
chk("MVI A,5Ah (шапка кадра)", b"\x3E\x5A" in rom)
chk("демо-строка fw_monitor_ACdE_tm_xstream", b"fw_monitor_ACdE_tm_xstream" in rom)

print()
if fails:
    print("ПРОВАЛЕНО: %d проверок: %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")

# v1.1 Шаг-1: слитый порт - записей колонок OUT 02h в образе БЫТЬ НЕ ДОЛЖНО
chk("v1.1: OUT 02h в образе отсутствует (колонки в старшем ниббле 06h)",
    sum(1 for i in range(len(rom) - 1) if rom[i] == 0xD3 and rom[i + 1] == 0x02) == 0)
chk("v1.1: KSCOL-паттерн RLC x4 + ORI 0Eh + OUT 06h (07 07 07 07 F6 0E D3 06)",
    b"\x07\x07\x07\x07\xF6\x0E\xD3\x06" in rom)
chk("v1.1: OUT 06h стало >= 7 (TMON/TMOFF/2 ре-арма/2 KSCOL/INIT)",
    n_out06 >= 7, "найдено %d" % n_out06)
print()
if fails:
    print("ПРОВАЛЕНО: %d проверок: %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ (v1.1)")
