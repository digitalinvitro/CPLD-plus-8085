#!/usr/bin/env python3
# verify_tm_v201.py - статическая верификация fw_monitor_ACdE_tm_xstream_v2_0_1.hex
# (плата retro_pcld, CPLD v37F-11 со СВОБОДНЫМ тиком 4 мкс, CPU 3,125 МГц).
# Отличие от v2.0: ИСПРАВЛЕННЫЕ SIM-маски (раскладка Intel 8085:
# D0=M7.5, D1=M6.5, D2=M5.5, D3=MSE, D4=R7.5):
#   3E 1F 30 (MVI A,1Fh+SIM) == 4 - TMOFF, вход TMON, оба выхода TMISR;
#   3E 0E 30 (MVI A,0Eh+SIM) == 2 - выход TMON, TMIARM;
#   TMIARM = 3E 0E 30 00 C9 (MVI 0Eh; SIM; NOP; RET) + 7 CALL.
# Остальное - как v2.0 (вектора, таблицы, константы 3,125 МГц, шапка A5 5A).
import sys

HEX = "fw_monitor_ACdE_tm_xstream_v2_0_1.hex"
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

# векторная зона: RST1-7, TRAP, RST5.5/6.5 = глушилки FB C9 (EI;RET)
for va in (0x08, 0x10, 0x18, 0x20, 0x24, 0x28, 0x2C, 0x30, 0x34, 0x38):
    chk("глушилка EI;RET @%04Xh" % va, rom[va] == 0xFB and rom[va + 1] == 0xC9)

# RST 7.5 (003Ch) = JMP TMISR - НЕ глушилка (свободный тик 4 мкс, п.1)
chk("RST 7.5 @003Ch = JMP", rom[0x3C] == 0xC3, "цель %04Xh" % word(0x3D))
tmi = word(0x3D)
chk("TMISR: PUSH PSW + DCR E",
    rom[tmi] == 0xF5 and rom[tmi + 1] == 0x1D, "счётчик слотов в E")
chk("TMISR: быстрый выход замаскирован (DCR E + JNZ TMTINY)",
    b"\x1D\xC2" in rom[tmi:tmi + 5])

# v2.0.1: ИСПРАВЛЕННЫЕ SIM-маски (раскладка D0=M7.5/D1=M6.5/D2=M5.5/D3=MSE/D4=R7.5)
n_mask = rom.count(b"\x3E\x1F\x30")
chk("SIM 1Fh (маска ВСЕХ + сброс защёлки) == 4 (TMOFF/TMON/TMISR x2)",
    n_mask == 4, "найдено %d" % n_mask)
n_unmask = rom.count(b"\x3E\x0E\x30")
chk("SIM 0Eh (7.5 разрешён, 6.5/5.5 маскированы) == 2 (выход TMON/TMIARM)",
    n_unmask == 2, "найдено %d" % n_unmask)
chk("НЕ ОСТАЛОСЬ битых масок v2.0 (3E 78h+SIM / 3E 68h+SIM)",
    b"\x3E\x78\x30" not in rom and b"\x3E\x68\x30" not in rom)

# дисциплина TMIARM v2.0.1: MVI A,0Eh; SIM; NOP; RET
tmiarm = b"\x3E\x0E\x30\x00\xC9"
ia = rom.find(tmiarm)
chk("TMIARM: MVI 0Eh+SIM+NOP+RET", ia >= 0, "@%04Xh" % ia if ia >= 0 else "нет")
if ia >= 0:
    n_call = sum(1 for i in range(len(rom) - 2)
                 if rom[i] == 0xCD and word(i + 1) == ia)
    chk("CALL TMIARM >= 7 (SCAN/XSL/KRL/KST/TKL/MNR1/MNR3)",
        n_call >= 7, "найдено %d" % n_call)

# армирование v1.2 ДОЛЖНО ОТСУТСТВОВАТЬ (свободный тик, п.1)
n_out06 = sum(1 for i in range(len(rom) - 1) if rom[i] == 0xD3 and rom[i + 1] == 0x06)
chk("OUT 06h == 2 (только KSCOL: колонка on/off)", n_out06 == 2, "найдено %d" % n_out06)
chk("НЕТ ре-арма MVI A,0Eh+OUT 06h", b"\x3E\x0E\xD3\x06" not in rom)
n_stop = sum(1 for i in range(len(rom) - 2)
             if rom[i] == 0xAF and rom[i + 1] == 0xD3 and rom[i + 2] == 0x06)
chk("XRA A+OUT 06h == 1 (KSCOL: колонки off)", n_stop == 1, "найдено %d" % n_stop)
chk("MVI E,6 (перезарядка слота)", b"\x1E\x06" in rom)

# константы 3,125 МГц (п.4)
chk("LXI B,K_MS=130 (DLMS ~1,0 мс)", b"\x01\x82\x00" in rom)
chk("MVI D,RXHB=19 (полбита 4800)", b"\x16\x13" in rom)
chk("MVI D,RXFB=41 (бит 4800, ~208 мкс)", b"\x16\x29" in rom)
chk("LXI SP,FFE8h", b"\x31\xE8\xFF" in rom)

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

# xstream: шапка кадра A5 5A [SEQ], живой счётчик, строка v2.0.1
chk("MVI A,0A5h (шапка кадра)", b"\x3E\xA5" in rom)
chk("MVI A,5Ah (шапка кадра)", b"\x3E\x5A" in rom)
chk("демо-строка v2.0.1", b"fw_monitor_ACdE_tm_xstream v2.0.1" in rom)
chk("строка TICK v37F-11", b"RTL v37F-11" in rom)

print()
if fails:
    print("ПРОВАЛЕНО: %d проверок: %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
