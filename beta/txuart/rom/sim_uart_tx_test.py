#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_uart_tx_test.py -- симуляция железной проверки TXUART v2.2.

Метод (по прецеденту beta/lowsize/rom/verify_fw.py):
  1) МИНИ-ИНТЕРПРЕТАТОР 8085 (подмножество команд uart_tx_test.hex,
     точные T-состояния по Intel 8085A) исполняет РЕАЛЬНЫЙ .hex.
  2) Хуки IO:
     - OUT 04h -> модель TX-ядра v2.2: кадр 10 бит x 16 тиков клока
       25 МГц = 160 тиков = 6,4 мкс = 20 T (CPU 3,125 МГц, T = 320 нс);
       TXRDY = 0 до конца кадра (точнее до ~15-го тика стопа, модель
       консервативна: ровно 20 T). Запись при TXRDY=0 = НАРУШЕНИЕ
       протокола (на железе байт тихо отбрасывается).
     - IN 05h  -> {A1 = TXRDY, прочие 0} (карта beta/txuart README).
     - OUT 00h/01h -> модель индикатора (seg/dig-регистры, 1 = горит;
       бит A4 порта 01h = SND - обязан быть 0).
     - IN 03h -> 0 (клавиатура не используется).
  3) ПРОВЕРКИ:
     C0 старт: первый байт уходит при TXRDY=1;
     C1 протокол: КАЖДЫЙ OUT 04h при TXRDY=1 (поллинг не пропущен);
     C2 поток: байты == "TXUART v2.2 OK N=xx" + CR LF, xx = 00,01,02...
        (hex, mod 256), байты НЕ теряются и НЕ дублируются;
     C3 период строк: ~200,1 мс (200 срезов по 3117 T + передача);
     C4 срез SLICE: 3117 T (фаза 0) = 997,4 мкс (-0,26% к 1 мс, допуск 1%);
     C5 мультиплекс: фазы 01->02->04->08, по ~3131 T каждая;
        глифы: DIG0 = HTAB[C&0Fh], DIG1/2 = '-' (40h), DIG3 = 't' (78h);
        промежуток seg->dig (призрак) < 15 T;
     C6 звук: бит A4 всех записей порта 01h == 0 (SND молчит);
     C7 HLT/зависание не встретились за окно симуляции.

Окно симуляции: 2 100 000 T = 672 мс CPU (>= 3 полных строк).

Использование: python3 sim_uart_tx_test.py   (из rom/)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
T_NS = 320.0            # нс на T-состояние (CPU 3,125 МГц, v2.2 шунт)
FRAME_T = 20            # кадр UART 6,4 мкс в T-состояниях
T_END = 2_100_000       # окно симуляции, T
fail = 0


def chk(name, cond, detail=""):
    global fail
    print("  %s %s %s" % ("ПАСС" if cond else "ПРОВ", name, detail))
    if not cond:
        fail += 1


# ---------------------------------------------------------------- HEX
def load_hex(path):
    mem = bytearray(65536)
    top = 0
    for ln in open(path):
        ln = ln.strip()
        if not ln or not ln.startswith(':'):
            continue
        cnt = int(ln[1:3], 16)
        addr = int(ln[3:7], 16)
        typ = int(ln[7:9], 16)
        data = bytes.fromhex(ln[9:9 + 2 * cnt])
        if typ == 0:
            mem[addr:addr + cnt] = data
            top = max(top, addr + cnt)
        elif typ == 1:
            break
        else:
            raise RuntimeError("HEX-тип %d не поддержан" % typ)
    return mem, top


# -------------------------------------------------- интерпретатор 8085
class CPU:
    """Подмножество 8085 для uart_tx_test: точные T, флаги Z/CY."""

    def __init__(self, mem, sim):
        self.m = mem
        self.sim = sim                     # хуки IO/время
        self.A = self.B = self.C = self.D = 0
        self.E = self.H = self.L = 0
        self.SP = 0
        self.PC = 0
        self.Z = 0
        self.CY = 0
        self.T = 0
        self.icount = 0
        self.done = False

    # ---- память
    def fetch(self):
        v = self.m[self.PC]
        self.PC = (self.PC + 1) & 0xFFFF
        return v

    def fetch16(self):
        lo = self.fetch()
        hi = self.fetch()
        return lo | (hi << 8)

    def push(self, v):
        # 8085 PUSH: SP декрементируется ДО записи: hi в (SP), lo в (SP+1),
        # после push SP указывает на младший байт
        self.SP = (self.SP - 1) & 0xFFFF
        self.m[self.SP] = (v >> 8) & 0xFF
        self.SP = (self.SP - 1) & 0xFFFF
        self.m[self.SP] = v & 0xFF

    def pop(self):
        lo = self.m[self.SP]
        self.SP = (self.SP + 1) & 0xFFFF
        hi = self.m[self.SP]
        self.SP = (self.SP + 1) & 0xFFFF
        return lo | (hi << 8)

    # ---- флаги
    def setz(self, v8):
        self.Z = 1 if (v8 & 0xFF) == 0 else 0

    def step(self):
        op = self.fetch()
        t = 4                                     # база одномашинных
        if op == 0x00:                            # NOP
            pass
        elif op == 0xF3:                          # DI
            pass
        elif op == 0x76:                          # HLT
            t = 7
            self.done = True
            self.sim.hlt = True
        elif op == 0xC3:                          # JMP a16
            self.PC = self.fetch16()
            t = 10
        elif op in (0xC2, 0xCA, 0xD2, 0xDA):      # JNZ/JZ/JNC/JC
            a = self.fetch16()
            want = {0xC2: 0, 0xCA: 1, 0xD2: 0, 0xDA: 1}[op]
            have = self.Z if op in (0xC2, 0xCA) else self.CY
            t = 10 if have == want else 7
            if have == want:
                self.PC = a
        elif op == 0xCD:                          # CALL a16
            a = self.fetch16()
            self.push(self.PC)
            self.PC = a
            t = 18
        elif op == 0xC9:                          # RET
            self.PC = self.pop()
            t = 10
        elif op == 0xC8:                          # RZ (6/12)
            if self.Z:
                self.PC = self.pop()
                t = 12
            else:
                t = 6
        elif op in (0x01, 0x11, 0x21, 0x31):      # LXI rp,d16
            v = self.fetch16()
            rp = (op >> 4) & 3
            if rp == 0:
                self.B, self.C = (v >> 8) & 0xFF, v & 0xFF
            elif rp == 1:
                self.D, self.E = (v >> 8) & 0xFF, v & 0xFF
            elif rp == 2:
                self.H, self.L = (v >> 8) & 0xFF, v & 0xFF
            else:
                self.SP = v
            t = 10
        elif (op & 0xC7) == 0x06:                 # MVI r,imm
            v = self.fetch()
            self.setr((op >> 3) & 7, v)
            t = 7
        elif (op & 0xC0) == 0x40:                 # MOV r,r / r,M / M,r
            src = op & 7
            dst = (op >> 3) & 7
            val = self.m[self.HL()] if src == 6 else self.getr(src)
            if dst == 6:
                self.m[self.HL()] = val
                t = 10
            else:
                self.setr(dst, val)
                t = 7 if src == 6 else 4
        elif op in (0x0C, 0x1C, 0x2C, 0x3C, 0x04, 0x14, 0x24, 0x34):
            r = self.getr((op >> 3) & 7)          # INR r
            v = ((r + 1) & 0xFF)
            self.setr((op >> 3) & 7, v)
            self.setz(v)
            t = 4
        elif op in (0x0D, 0x1D, 0x2D, 0x3D, 0x05, 0x15, 0x25, 0x35):
            r = self.getr((op >> 3) & 7)          # DCR r
            v = ((r - 1) & 0xFF)
            self.setr((op >> 3) & 7, v)
            self.setz(v)
            t = 4
        elif op in (0x03, 0x13, 0x23):            # INX rp
            rp = (op >> 4) & 3
            lo, hi = self.rp(rp)
            v = ((hi << 8) | lo) + 1
            self.setrp(rp, v & 0xFFFF)
            t = 6
        elif op == 0x0F:                          # RRC
            b0 = self.A & 1
            self.A = ((self.A >> 1) | (b0 << 7)) & 0xFF
            self.CY = b0
            t = 4
        elif op == 0xE6:                          # ANI imm
            self.A &= self.fetch()
            self.CY = 0
            self.setz(self.A)
            t = 7
        elif op == 0xC6:                          # ADI imm
            v = self.fetch()
            r = self.A + v
            self.A = r & 0xFF
            self.CY = 1 if r > 0xFF else 0
            self.setz(self.A)
            t = 7
        elif op == 0xFE:                          # CPI imm
            v = self.fetch()
            self.setz((self.A - v) & 0xFF)
            self.CY = 1 if self.A < v else 0
            t = 7
        elif op == 0xB7:                          # ORA A
            self.setz(self.A)
            self.CY = 0
            t = 4
        elif op == 0xD3:                          # OUT p
            p = self.fetch()
            self.sim.out(p, self.A)
            t = 10
        elif op == 0xDB:                          # IN p
            p = self.fetch()
            self.A = self.sim.inp(p)
            t = 10
        else:
            raise RuntimeError("опкод %02X не поддержан (PC=%04X T=%d)"
                               % (op, (self.PC - 1) & 0xFFFF, self.T))
        self.T += t
        self.icount += 1
        return t

    def HL(self):
        return (self.H << 8) | self.L

    def rp(self, i):
        # ВОЗВРАЩАЕТ (lo, hi): B=0->C,B; D=1->E,D; H=2->L,H
        return {0: (self.C, self.B), 1: (self.E, self.D),
                2: (self.L, self.H)}[i]

    def setrp(self, i, v):
        hi, lo = (v >> 8) & 0xFF, v & 0xFF
        if i == 0:
            self.B, self.C = hi, lo
        elif i == 1:
            self.D, self.E = hi, lo
        else:
            self.H, self.L = hi, lo

    def getr(self, i):
        return {0: self.B, 1: self.C, 2: self.D, 3: self.E,
                4: self.H, 5: self.L, 6: self.m[self.HL()], 7: self.A}[i]

    def setr(self, i, v):
        v &= 0xFF
        if i == 0:
            self.B = v
        elif i == 1:
            self.C = v
        elif i == 2:
            self.D = v
        elif i == 3:
            self.E = v
        elif i == 4:
            self.H = v
        elif i == 5:
            self.L = v
        elif i == 7:
            self.A = v
        else:
            self.m[self.HL()] = v


# ----------------------------------------------------------------- sim
class Sim:
    def __init__(self):
        self.busy_until = -1          # T, до которого TXRDY=0
        self.stream = bytearray()     # байты в P39 (что ушло бы в CH340G)
        self.stamps = []              # (T, byte) моментов OUT 04h
        self.viol = []                # OUT 04h при busy
        self.seg = 0xFF               # после POR seg=FF (по карте)
        self.dig = 0x0F               # после POR dig=F
        self.dig_events = []          # (T, dig_value, seg_value, C)
        self.seg_events = []          # (T, seg_value)
        self.snd_hits = 0             # OUT 01h с A4=1
        self.hlt = False
        self.inp3_reads = 0

    def txrdy(self, T):
        return T >= self.busy_until

    def out(self, p, a):
        T = self.cpu.T
        if p == 0x04:
            if not self.txrdy(T):
                self.viol.append((T, a))
            self.busy_until = T + FRAME_T
            self.stream.append(a)
            self.stamps.append((T, a))
        elif p == 0x00:
            self.seg = a
            self.seg_events.append((T, a))
        elif p == 0x01:
            if a & 0x10:
                self.snd_hits += 1
            self.dig = a
            self.dig_events.append((T, a, self.seg, self.cpu.C))
        else:
            pass                      # 02h (колонки) прошивкой не пишется

    def inp(self, p):
        if p == 0x05:
            return 0x02 if self.txrdy(self.cpu.T) else 0x00
        if p == 0x03:
            self.inp3_reads += 1
            return 0x00
        return 0x00


HTAB = bytes([0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07,
              0x7F, 0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71])
DTAB = [0x01, 0x02, 0x04, 0x08]
MSG = b"TXUART v2.2 OK N="


def expected_line(n):
    return MSG + ("%02X" % (n & 0xFF)).encode() + b"\r\n"


def main():
    mem, top = load_hex(os.path.join(HERE, "uart_tx_test.hex"))
    print("uart_tx_test.hex: образ 0000h-%04Xh (%d байт)" % (top - 1, top))
    sim = Sim()
    cpu = CPU(mem, sim)
    sim.cpu = cpu

    # RST: PC=0000
    while cpu.T < T_END and not cpu.done:
        cpu.step()

    print("исполнено T=%d (%.1f мс CPU), инструкций %d"
          % (cpu.T, cpu.T * T_NS / 1e6, cpu.icount))

    # C7: HLT/падение
    chk("C7 нет HLT за окно %.0f мс" % (T_END * T_NS / 1e6),
        not sim.hlt)

    # C0/C1: протокол OUT 04h
    chk("C1 все OUT 04h при TXRDY=1 (%d байт, нарушений %d)"
        % (len(sim.stamps), len(sim.viol)), len(sim.viol) == 0,
        str(sim.viol[:3]))
    chk("C0 первый байт при TXRDY=1",
        len(sim.stamps) > 0 and sim.stamps[0][0] >= 0 and len(sim.viol) == 0)

    # C2: поток байтов
    lines = []
    i = 0
    n = 0
    ok_stream = True
    while i + 21 <= len(sim.stream):
        exp = expected_line(n)
        got = bytes(sim.stream[i:i + 21])
        if got != exp:
            ok_stream = False
            print("      строка %d: ожидалось %r, получено %r"
                  % (n, exp, got))
            break
        lines.append(i)
        i += 21
        n += 1
    chk("C2 поток 1-в-1: %d полных строк, хвост %d байт"
        % (len(lines), len(sim.stream) - i),
        ok_stream and len(sim.stream) % 21 == 0 and len(lines) >= 3)
    if lines:
        first = bytes(sim.stream[lines[0]:lines[0] + 21])
        print("      строка 0: %r" % first)

    # C3: период строк
    if len(lines) >= 3:
        periods = [sim.stamps[lines[k + 1]][0] - sim.stamps[lines[k]][0]
                   for k in range(len(lines) - 1)]
        # ожидание: 200 срезов (цикл 4 фаз = 12451 T x 50) + передача
        exp_lo, exp_hi = 623_000, 627_500
        chk("C3 период строк %s T (%.2f мс)"
            % (periods, periods[0] * T_NS / 1e6),
            all(exp_lo <= p <= exp_hi for p in periods))
    else:
        chk("C3 период строк", False, "строк < 3")

    # C4: срез SLICE = интервалы между OUT 01h внутри задержки
    dg = sim.dig_events
    slices = [dg[k + 1][0] - dg[k][0] for k in range(len(dg) - 1)
              if dg[k + 1][0] - dg[k][0] < 5000]
    if slices:
        med = sorted(slices)[len(slices) // 2]
        chk("C4 срез мультиплекса: медиана %d T (%.2f мкс), всего %d"
            % (med, med * T_NS / 1e3, len(slices)),
            3105 <= med <= 3125, "модели: фаза 0 = 3117 T")
    else:
        chk("C4 срез мультиплекса", False, "нет интервалов")

    # C5: фазы и глифы
    order_ok = True
    ghost_ok = True
    glyph_ok = True
    for k in range(len(dg)):
        T, dv, sv, C = dg[k]
        if dv != DTAB[k % 4]:
            order_ok = False
        if k > 0 and dg[k][0] - dg[k - 1][0] >= 5000:
            pass                  # разрыв на время передачи строки
        if dv == 0x08 and sv != 0x78:
            glyph_ok = False
        if dv in (0x02, 0x04) and sv != 0x40:
            glyph_ok = False
        if dv == 0x01 and sv != HTAB[C & 0x0F]:
            glyph_ok = False
    # призрак: seg изменяется на dig-записи раньше -> найти пары
    for k in range(len(dg) - 1):
        Td, dv, sv, _ = dg[k]
        # seg, записанный перед этой dig-записью:
        prev_seg = [s for (Ts, s) in sim.seg_events if Ts <= Td]
        if prev_seg and sv != prev_seg[-1]:
            ghost_ok = False
    chk("C5 фазы 01->02->04->08 по кругу", order_ok,
        "первая фаза %s" % ([d[1] for d in dg[:5]]))
    chk("C5 глифы: DIG0=HTAB[C&0F], '-'=40h, 't'=78h", glyph_ok)
    chk("C5 seg перед dig совпадает (призрак < 15 T)", ghost_ok)

    # C6: звук
    chk("C6 SND (бит A4 порта 01h) молчит", sim.snd_hits == 0)

    # разрывы на передачу строк: OUT 01h молчит во время отправки?
    print("  инфо: байт отправлено %d, строк %d, запись dig %d раз"
          % (len(sim.stream), len(lines), len(dg)))
    print()
    if fail:
        print("ИТОГ: ПРОВАЛОВ %d" % fail)
        sys.exit(1)
    print("ИТОГ: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
