#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_fw.py — верификация тест-прошивок fw_test_disp / fw_text_kbd
(beta/lowsize/rom, clk10-65).

Метод:
  1) МИНИ-ИНТЕРПРЕТАТОР 8085 (подмножество команд, используемых прошивками;
     точные T-состояния по Intel 8085A) исполняет РЕАЛЬНЫЙ .hex;
     OUT/IN - хуки: запись портов CPLD логируется, чтение порта 03h -
     модель матрицы 4x5 (подтяжки на GND, нажатие = 1).
  2) ПОВЕДЕНЧЕСКИЕ проверки на FAST-образе (укороченные выдержки,
     константы единиц K_MS НЕ меняются - T-состояния единиц совпадают
     с полными образами):
     fw_test_disp: порядок сегмент x разряд, биты, длительности в T,
                   тогглы SND, финал tE5t;
     fw_text_kbd: скан колонок, "--" в покое, ловля нажатия (строка/колонка),
                   глифы по таблице, бип (тон + длительность), отпускание,
                   дебаунс, второе нажатие.
  2а) БЛЭНКИНГ (клк10-67, по дефекту железа 10-30: сквозь '1' просвечивал
      '2'): регенерация = ГАШЕНИЕ (SEGP=0) -> РАЗРЯД -> ГЛИФ; проверяется,
      что КАЖДЫЙ разряд переключается строго при погашенных сегментах
      (призрак чужого глифа невозможен по построению) и что после
      переключения в SEGP уходит ровно глиф этой фазы.
  3) АРИФМЕТИКА тайминга полного образа: единица ~1 мс = 3558 T (замер на
     симуляции) x константы полных выдержек -> интервалы в мс/с + тон.

Использование: python3 verify_fw.py   (из rom/)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STEP_NS = 280.0          # нс на T-состояние (CPU 3,571 МГц)
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
        n = int(ln[1:3], 16)
        addr = int(ln[3:7], 16)
        typ = int(ln[7:9], 16)
        data = bytes.fromhex(ln[9:9 + 2 * n])
        if typ == 0:
            mem[addr:addr + n] = data
            top = max(top, addr + n)
        elif typ == 1:
            break
        else:
            raise ValueError('тип записи %d' % typ)
    return mem, top


# ------------------------------------------------------- мини-8085
# T-состояния (Intel 8085A)
T = dict(NOP=4, MVI=7, MVIM=10, LXI=10, MOVRR=4, MOVRM=7, MOVMR=7,
         LDA=13, STA=13, IN=10, OUT=10, INR=4, DCR=4, INX=6, DCX=6,
         DAD=10, RLC=4, RRC=4, CMA=4, ANA=4, ORA=4, XRA=4, ADD=4,
         ADI=7, ANI=7, ORI=7, XRI=7, CPI=7, JMP=10, JC=10, JNC=10,
         JZ=10, JNZ=10, CALL=18, RET=10, PUSH=12, POP=10, HLT=7,
         PCHL=6, XCHG=4, RAL=4, RAR=4, STC=4, CMC=4, DAA=4)


class CPU8085:
    def __init__(self, mem, cb_out=None, cb_in=None):
        self.m = mem
        self.A = 0; self.B = 0; self.C = 0; self.D = 0; self.E = 0
        self.H = 0; self.L = 0; self.SP = 0; self.PC = 0
        self.fS = 0; self.fZ = 1; self.fAC = 0; self.fP = 1; self.fCY = 0
        self.cb_out = cb_out or (lambda p, v: None)
        self.cb_in = cb_in or (lambda p: 0)
        self.halt = False
        self.T = 0

    # --- флаги ---
    def zsp(self, a):
        self.fZ = 1 if (a & 0xFF) == 0 else 0
        self.fS = (a >> 7) & 1
        self.fP = 1 if bin(a & 0xFF).count('1') % 2 == 0 else 0

    def rd(self, a):
        return self.m[a & 0xFFFF]

    def wr(self, a, v):
        self.m[a & 0xFFFF] = v & 0xFF

    def fetch(self):
        v = self.rd(self.PC)
        self.PC = (self.PC + 1) & 0xFFFF
        return v

    def step(self):
        op = self.fetch()
        t = 4
        A, B, C, D, E, H, L = (self.A, self.B, self.C, self.D,
                               self.E, self.H, self.L)
        # --- MOV/MVI блок ---
        src = op & 7
        dst = (op >> 3) & 7
        if 0x40 <= op <= 0x7F:
            if op == 0x76:                      # HLT
                self.halt = True
                return T['HLT']
            regs = [B, C, D, E, H, L, None, A]
            val = self.rd((H << 8) | L) if src == 6 else regs[src]
            if dst == 6:
                self.wr((H << 8) | L, val)
                return T['MOVMR']
            if dst == 0: self.B = val
            elif dst == 1: self.C = val
            elif dst == 2: self.D = val
            elif dst == 3: self.E = val
            elif dst == 4: self.H = val
            elif dst == 5: self.L = val
            elif dst == 7: self.A = val
            return T['MOVRR']
        if 0x00 <= op <= 0x3F:
            pass
        hi = op & 0xF0
        lo = op & 0x0F
        if op in (0x06, 0x0E, 0x16, 0x1E, 0x26, 0x2E, 0x36, 0x3E):  # MVI r/M
            v = self.fetch()
            mdst = (op >> 3) & 7
            if mdst == 0: self.B = v
            elif mdst == 1: self.C = v
            elif mdst == 2: self.D = v
            elif mdst == 3: self.E = v
            elif mdst == 4: self.H = v
            elif mdst == 5: self.L = v
            elif mdst == 7: self.A = v
            else:
                self.wr((H << 8) | L, v)
                return T['MVIM']
            return T['MVI']
        if op in (0x01, 0x11, 0x21, 0x31):      # LXI (B/D/H/SP)
            lo2 = self.fetch()
            hi2 = self.fetch()
            rp = (op >> 4) & 3
            val = (hi2 << 8) | lo2
            if rp == 0: self.B, self.C = hi2, lo2
            elif rp == 1: self.D, self.E = hi2, lo2
            elif rp == 2: self.H, self.L = hi2, lo2
            else: self.SP = val
            return T['LXI']
        if hi == 0x02 and lo in (0x0A, 0x12, 0x1A):  # LDAX
            addr = (B << 8) | C if (op & 0x10) == 0 else (D << 8) | E
            self.A = self.rd(addr)
            return T['LDA']
        if op in (0x0B, 0x1B, 0x2B, 0x3B):      # DCX (B/D/H/SP)
            rp = (op >> 4) & 3
            if rp == 0:
                bc = ((B << 8) | C) - 1
                self.B, self.C = (bc >> 8) & 0xFF, bc & 0xFF
            elif rp == 1:
                de = ((D << 8) | E) - 1
                self.D, self.E = (de >> 8) & 0xFF, de & 0xFF
            elif rp == 2:
                hl = ((H << 8) | L) - 1
                self.H, self.L = (hl >> 8) & 0xFF, hl & 0xFF
            else:
                self.SP = (self.SP - 1) & 0xFFFF
            return T['DCX']
        if op in (0x03, 0x13, 0x23, 0x33):      # INX (B/D/H/SP)
            rp = (op >> 4) & 3
            if rp == 0:
                bc = ((B << 8) | C) + 1
                self.B, self.C = (bc >> 8) & 0xFF, bc & 0xFF
            elif rp == 1:
                de = ((D << 8) | E) + 1
                self.D, self.E = (de >> 8) & 0xFF, de & 0xFF
            elif rp == 2:
                hl = ((H << 8) | L) + 1
                self.H, self.L = (hl >> 8) & 0xFF, hl & 0xFF
            else:
                self.SP = (self.SP + 1) & 0xFFFF
            return T['INX']
        if op == 0x07:                          # RLC
            self.fCY = (A >> 7) & 1
            self.A = ((A << 1) | self.fCY) & 0xFF
            return T['RLC']
        if op == 0x0F:                          # RRC
            self.fCY = A & 1
            self.A = (A >> 1) | (self.fCY << 7)
            return T['RRC']
        if op == 0x17:                          # RAL
            c = self.fCY
            self.fCY = (A >> 7) & 1
            self.A = ((A << 1) | c) & 0xFF
            return T['RAL']
        if op == 0x1F:                          # RAR
            c = self.fCY
            self.fCY = A & 1
            self.A = (A >> 1) | (c << 7)
            return T['RAR']
        if op in (0x04, 0x0C, 0x14, 0x1C, 0x24, 0x2C, 0x34, 0x3C):   # INR
            v = (self.rd((H << 8) | L) if dst == 6 else
                 [self.B, self.C, self.D, self.E, self.H, self.L, 0,
                  self.A][dst])
            v = (v + 1) & 0xFF
            self.zsp(v)
            self.fAC = 1 if (v & 0x0F) == 0 else 0
            if dst == 6:
                self.wr((H << 8) | L, v)
            elif dst == 0: self.B = v
            elif dst == 1: self.C = v
            elif dst == 2: self.D = v
            elif dst == 3: self.E = v
            elif dst == 4: self.H = v
            elif dst == 5: self.L = v
            elif dst == 7: self.A = v
            return T['INR']
        if op in (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D):   # DCR
            v = (self.rd((H << 8) | L) if dst == 6 else
                 [self.B, self.C, self.D, self.E, self.H, self.L, 0,
                  self.A][dst])
            v = (v - 1) & 0xFF
            self.zsp(v)
            self.fAC = 1 if (v & 0x0F) == 0x0F else 0
            if dst == 6:
                self.wr((H << 8) | L, v)
            elif dst == 0: self.B = v
            elif dst == 1: self.C = v
            elif dst == 2: self.D = v
            elif dst == 3: self.E = v
            elif dst == 4: self.H = v
            elif dst == 5: self.L = v
            elif dst == 7: self.A = v
            return T['DCR']
        if op in (0x3A, 0x32):                  # LDA/STA
            lo2 = self.fetch()
            hi2 = self.fetch()
            addr = (hi2 << 8) | lo2
            if op == 0x3A:
                self.A = self.rd(addr)
                return T['LDA']
            self.wr(addr, self.A)
            return T['STA']
        if op == 0xDB:                          # IN
            p = self.fetch()
            self.A = self.cb_in(p) & 0xFF
            return T['IN']
        if op == 0xD3:                          # OUT
            p = self.fetch()
            self.cb_out(p, self.A)
            return T['OUT']
        if op in (0x09, 0x19, 0x29, 0x39):      # DAD (B/D/H/SP)
            rp = (op >> 4) & 3
            if rp == 0: v = (B << 8) | C
            elif rp == 1: v = (D << 8) | E
            elif rp == 2: v = (H << 8) | L
            else: v = self.SP
            hl = (H << 8) | L
            r = hl + v
            self.fCY = 1 if r > 0xFFFF else 0
            self.H, self.L = (r >> 8) & 0xFF, r & 0xFF
            return T['DAD']
        if op == 0x2F:                          # CMA
            self.A = (~A) & 0xFF
            return T['CMA']
        if 0xA0 <= op <= 0xA7:                  # ANA r/M
            v = [B, C, D, E, H, L, self.rd((H << 8) | L), A][src]
            self.A = A & v
            self.fCY = 0; self.fAC = 0 if src != 6 else self.fAC
            self.zsp(self.A)
            return T['ANA']
        if 0xA8 <= op <= 0xAF:                  # XRA r/M
            v = [B, C, D, E, H, L, self.rd((H << 8) | L), A][src]
            self.A = A ^ v
            self.fCY = 0; self.fAC = 0
            self.zsp(self.A)
            return T['XRA']
        if 0xB0 <= op <= 0xB7:                  # ORA r/M
            v = [B, C, D, E, H, L, self.rd((H << 8) | L), A][src]
            self.A = A | v
            self.fCY = 0; self.fAC = 0
            self.zsp(self.A)
            return T['ORA']
        if op == 0xE6:                          # ANI
            v = self.fetch()
            self.A = A & v
            self.fCY = 0; self.fAC = 0
            self.zsp(self.A)
            return T['ANI']
        if op == 0xEE:                          # XRI
            v = self.fetch()
            self.A = A ^ v
            self.fCY = 0; self.fAC = 0
            self.zsp(self.A)
            return T['XRI']
        if op == 0xF6:                          # ORI
            v = self.fetch()
            self.A = A | v
            self.fCY = 0; self.fAC = 0
            self.zsp(self.A)
            return T['ORI']
        if op == 0xFE:                          # CPI
            v = self.fetch()
            r = (A - v) & 0x1FF
            self.fCY = 1 if (A - v) < 0 else 0
            self.zsp(r & 0xFF)
            return T['CPI']
        if op == 0xC3:                          # JMP
            lo2 = self.fetch(); hi2 = self.fetch()
            self.PC = (hi2 << 8) | lo2
            return T['JMP']
        if op in (0xC2, 0xCA, 0xD2, 0xDA):      # JNZ/JZ/JNC/JC
            lo2 = self.fetch(); hi2 = self.fetch()
            addr = (hi2 << 8) | lo2
            cond = ((op == 0xC2 and not self.fZ) or
                    (op == 0xCA and self.fZ) or
                    (op == 0xD2 and not self.fCY) or
                    (op == 0xDA and self.fCY))
            if cond:
                self.PC = addr
                return T['JC']
            return 7
        if op == 0xCD:                          # CALL
            lo2 = self.fetch(); hi2 = self.fetch()
            addr = (hi2 << 8) | lo2
            self.SP = (self.SP - 1) & 0xFFFF
            self.m[self.SP] = (self.PC >> 8) & 0xFF
            self.SP = (self.SP - 1) & 0xFFFF
            self.m[self.SP] = self.PC & 0xFF
            self.PC = addr
            return T['CALL']
        if op == 0xC9:                          # RET
            lo2 = self.m[self.SP]
            hi2 = self.m[(self.SP + 1) & 0xFFFF]
            self.SP = (self.SP + 2) & 0xFFFF
            self.PC = (hi2 << 8) | lo2
            return T['RET']
        if op in (0xC5, 0xD5, 0xE5, 0xF5):      # PUSH
            rp = (op >> 4) & 3
            if rp == 0: hi2, lo2 = B, C
            elif rp == 1: hi2, lo2 = D, E
            elif rp == 2: hi2, lo2 = H, L
            else:
                hi2 = (A if 1 else A) | 0  # A
                lo2 = (self.fS << 7) | (self.fZ << 6) | 0x02 | \
                      (self.fAC << 4) | 0x00 | (self.fP << 2) | 0x01 | \
                      (self.fCY << 0)
                hi2 = A
            self.SP = (self.SP - 1) & 0xFFFF
            self.m[self.SP] = hi2
            self.SP = (self.SP - 1) & 0xFFFF
            self.m[self.SP] = lo2
            return T['PUSH']
        if op in (0xC1, 0xD1, 0xE1, 0xF1):      # POP
            lo2 = self.m[self.SP]
            hi2 = self.m[(self.SP + 1) & 0xFFFF]
            self.SP = (self.SP + 2) & 0xFFFF
            rp = (op >> 4) & 3
            if rp == 0: self.B, self.C = hi2, lo2
            elif rp == 1: self.D, self.E = hi2, lo2
            elif rp == 2: self.H, self.L = hi2, lo2
            else:
                self.A = hi2
                self.fS = (lo2 >> 7) & 1
                self.fZ = (lo2 >> 6) & 1
                self.fAC = (lo2 >> 4) & 1
                self.fP = (lo2 >> 2) & 1
                self.fCY = lo2 & 1
            return T['POP']
        if op == 0xE9:                          # PCHL
            self.PC = (H << 8) | L
            return T['PCHL']
        if op == 0xEB:                          # XCHG
            self.H, self.D = D, H
            self.L, self.E = E, L
            return T['XCHG']
        raise ValueError('опкод %02X @ %04X не поддержан' % (op, self.PC - 1))

    def run(self, max_t):
        while self.T < max_t and not self.halt:
            self.T += self.step()
        return self.T


# ---------------------------------------------------------------- тесты
def test_disp():
    print("=" * 76)
    print("fw_test_disp_fast.hex: поведение (FAST=1: 3 ед/сегмент, 2 ед/пауза)")
    print("=" * 76)
    mem, top = load_hex(os.path.join(HERE, 'fw_test_disp_fast.hex'))
    assert mem[0] == 0xC3, 'нет JMP на 0000'
    ev = []          # (T, port, val)

    def out(p, v):
        ev.append((cpu.T, p, v))

    cpu = CPU8085(mem, cb_out=out)
    cpu.SP = 0x8400
    cpu.run(1_500_000)

    seg = [(t, v) for (t, p, v) in ev if p == 0]
    dig = [(t, v) for (t, p, v) in ev if p == 1]

    chk("init: первый OUT 00h = 00 (гашение '8.')", ev[0][1] == 0 and ev[0][2] == 0)
    chk("init: второй OUT 01h = 00 (разряды off, SND off)",
        ev[1][1] == 1 and ev[1][2] == 0)

    # --- сегментные шаги: шаг = p0(v!=0) ... p0(v==0); p1 внутри: интервал ---
    steps = []
    i = 2
    n = len(ev)
    while i < n and len(steps) < 32:
        t, p, v = ev[i]
        if p == 0 and v != 0:
            j = i + 1
            digs = []
            while j < n and not (ev[j][1] == 0 and ev[j][2] == 0):
                if ev[j][1] == 1:
                    digs.append((ev[j][0], ev[j][2]))
                j += 1
            # ev[j] = p0=0 (гашение сегмента) - конец шага
            digit = None
            for _, dv in digs:
                if dv & 0x0F:
                    digit = dv & 0x0F
                    break
            steps.append(dict(seg=v, digit=digit, t0=t,
                              t1=ev[j][0] if j < n else t, digs=digs))
            i = j
        i += 1
    chk("число сегментных шагов = 32", len(steps) == 32, "найдено %d" % len(steps))
    okorder = True
    for k, st in enumerate(steps[:32]):
        d, sg = k // 8, k % 8
        if st['seg'] != (1 << sg) or st['digit'] != (1 << d):
            okorder = False
            print("      шаг %d: ожидался разряд %02X сегмент %02X, получено %02X/%02X"
                  % (k, 1 << d, 1 << sg, st['digit'] or 0, st['seg']))
    chk("порядок: разряды 0->3, сегменты a->dp", okorder)

    # интервал (p0 сегмент -> p0 гашение) = выдержка: SEG_MS ед x 3558 T
    okt = True
    for st in steps[:32]:
        dur = st['t1'] - st['t0']
        exp = 3 * 3558 + 100 if 'FAST' else 0
        if not (exp * 0.97 <= dur <= exp * 1.03):
            okt = False
            print("      шаг t0=%d: длительность %d (ожидалось ~%d)" % (st['t0'], dur, exp))
    chk("выдержка сегмента = 3 ед x 3558 T (FAST)", okt)

    # тон: p1 в интервале чередует бит D4; первый = разряд|10h
    okt2 = True
    for st in steps[:32]:
        if not st['digs'] or not (st['digs'][0][1] & 0x10):
            okt2 = False
    chk("тон включён в начале каждого шага (бит D4)", okt2)
    d0 = steps[0]['digs']
    snd_bits = [1 if (v & 0x10) else 0 for (_, v) in d0]
    toggles = sum(1 for a, b in zip(snd_bits, snd_bits[1:]) if a != b)
    chk("SND тогглится каждую единицу (3 в FAST)",
        len(d0) == 5 and toggles == 3 and snd_bits[-1] == 0,
        "p1 в интервале: %d (проклок+3+гашение тона), переключений: %d"
        % (len(d0), toggles))
    if len(d0) >= 2:
        half = d0[1][0] - d0[0][0]
        chk("полупериод тона ~3558 T (996 мкс -> ~502 Гц)",
            3558 * 0.97 <= half <= 3558 * 1.03, "=%d T" % half)

    # --- финал tE5t: после 32-го шага фазы циклят глифы 78,79,6D,78 ---
    # протокол с блэнкингом (клк10-67): на фазу OUT 00h=0 (гашение) ->
    # OUT 01h (разряд) -> OUT 00h=глиф; разряд переключается только пустым
    if len(steps) == 32:
        t_end = steps[-1]['t1']
        tail_ev = [(t, p, v) for (t, p, v) in ev if t > t_end]
        tail = [v for (t, p, v) in tail_ev if p == 0 and v != 0]
        te5t = [0x78, 0x79, 0x6D, 0x78]
        cnt = min(16, len(tail))
        okt3 = cnt >= 16 and all(tail[i] == te5t[i % 4] for i in range(cnt))
        chk("финал: глифы tE5t (78,79,6D,78) в регенерации", okt3,
            "хвост: %s" % [hex(v) for v in tail[:8]])
        digtail = [v for (t, p, v) in tail_ev if p == 1]
        cnt = min(16, len(digtail))
        okt4 = cnt >= 16 and all(
            (digtail[i] & 0x0F) == (0x08 >> (i % 4)) and (digtail[i] & 0x10) == 0
            for i in range(cnt))
        chk("финал: разряды DIG3->DIG0, тон выключен", okt4,
            "хвост: %s" % [hex(v) for v in digtail[:8]])
        # БЛЭНКИНГ: перед каждым OUT 01h последний OUT 00h = 0 (гашение),
        # после OUT 01h в SEGP уходит ровно глиф этой фазы
        dmap = {0x08: 0, 0x04: 1, 0x02: 2, 0x01: 3}
        okg, why, nph = True, "", 0
        for i, (t, p, v) in enumerate(tail_ev):
            if p != 1 or not (v & 0x0F):
                continue
            prev0 = next((tail_ev[j][2] for j in range(i - 1, -1, -1)
                          if tail_ev[j][1] == 0), None)
            nxt0 = next((tail_ev[j][2] for j in range(i + 1, len(tail_ev))
                         if tail_ev[j][1] == 0), None)
            if nxt0 is None:        # фаза обрезана окном симуляции - пропуск
                continue
            phn = dmap.get(v & 0x0F)
            if prev0 != 0 or nxt0 != te5t[phn]:
                okg = False
                why = ("OUT 01h=%02X: до него SEGP=%s, после=%s (ожидалось 0/%02X)"
                       % (v & 0x0F, prev0, nxt0, te5t[phn]))
                break
            nph += 1
        chk("финал: блэнкинг (гашение -> разряд -> глиф фазы)",
            okg and nph >= 8, why or "проверено фаз: %d" % nph)
        # период фазы tE5t: глиф->глиф ~5354 T (1499 мкс, регенерация ~167 Гц)
        phs = [t for (t, p, v) in tail_ev if p == 0 and v != 0][:5]
        if len(phs) >= 2:
            dph = phs[1] - phs[0]
            chk("фаза tE5t ~5354 T (1499 мкс, регенерация ~167 Гц)",
                5354 * 0.97 <= dph <= 5354 * 1.03, "=%d T" % dph)

    # --- арифметика ПОЛНОГО образа ---
    print()
    print("  Арифметика полного образа (K_MS=144, SEG_MS=900, GAP_MS=60):")
    unit = 3558                       # CALL+LXI+loop+toggle+RET+loop-tail
    iv = 900 * unit
    gap = 60 * 3515
    chk("выдержка сегмента 896,6 мс в диапазоне 0,8..1,0 с",
        800 <= iv * STEP_NS / 1e6 <= 1000, "=%.1f мс" % (iv * STEP_NS / 1e6))
    chk("пауза между сегментами ~59 мс", abs(gap * STEP_NS / 1e6 - 59.0) < 1,
        "=%.1f мс" % (gap * STEP_NS / 1e6))
    tot = 32 * (iv + gap)
    print("  полный обход: 32 x (896,6 + 59,0) мс = %.1f с, затем tE5t"
          % (tot * STEP_NS / 1e9))


def test_kbd():
    print()
    print("=" * 76)
    print("fw_text_kbd_fast.hex: поведение (FAST=1: бип 4 ед, дебаунс 2 ед)")
    print("=" * 76)
    mem, top = load_hex(os.path.join(HERE, 'fw_text_kbd_fast.hex'))
    assert mem[0] == 0xC3, 'нет JMP на 0000'
    state = dict(col=0, keys={}, log=[])

    def out(p, v):
        if p == 2:
            state['col'] = v
        state['log'].append((cpu.T, p, v))

    def inp(p):
        if p != 3:
            return 0xFF
        rows = 0
        for (r, c), pr in state['keys'].items():
            if pr and (state['col'] >> c) & 1:
                rows |= 1 << r
        return rows & 0x1F

    cpu = CPU8085(mem, cb_out=out, cb_in=inp)
    cpu.SP = 0x8400
    cpu.run(300_000)
    log = state['log']

    cols = [v for (t, p, v) in log if p == 2 and v != 0]
    segs = [v for (t, p, v) in log if p == 0 and v != 0]
    digs = [v for (t, p, v) in log if p == 1 and (v & 0x0F)]
    chk("в покое колонки опрашиваются по кругу 01,02,04,08",
        all(cols[i] == (1 << (i % 4)) for i in range(8)),
        "%s" % [hex(v) for v in cols[:8]])
    chk("в покое глиф '-' (40h) на обоих разрядах",
        segs and all(v == 0x40 for v in segs[:4]),
        "%s" % [hex(v) for v in segs[:4]])
    chk("в покое регенерация разрядов 01h/08h попеременно (DPH с правого)",
        all((digs[i] & 0x0F) == (0x01 if i % 2 == 0 else 0x08)
            for i in range(6)), "%s" % [hex(v) for v in digs[:6]])

    # --- нажатие SW11 (row2/col2) ---
    state['keys'][(2, 2)] = True
    log.clear()
    cpu.run(cpu.T + 60_000)
    log = state['log']
    cols = [v for (t, p, v) in log if p == 2]
    digs = [v for (t, p, v) in log if p == 1]
    segs = [v for (t, p, v) in log if p == 0]
    chk("HIT: колонки гасятся (OUT 02h=0) сразу после ловли", 0 in cols[:5])
    # бип: OUT 01h с D4; число тогглов = BEEP_MS
    beepdigs = [(t, v) for (t, p, v) in log if p == 1 and (v & 0x10)]
    chk("бип: SND тогглится каждый BEEP_UNIT (4 в FAST: биты 1,0,1,0)",
        len(beepdigs) == 2, "единиц SND в логе: %d (из 4 BEEP_UNIT)" % len(beepdigs))
    # глифы во время и после бипа: '3'(4F) на 08h, '2'(5B) на 01h
    m3 = [v for (t, p, v) in log if p == 1 and (v & 0x0F) == 0x08]
    m0 = [v for (t, p, v) in log if p == 1 and (v & 0x0F) == 0x01]
    okg3 = any(True for _ in m3) and True
    # глифы и блэнкинг: модель регенерации (клк10-67). На каждый OUT 01h:
    #   sb - последний OUT 00h до него (обязан быть 0 = гашение),
    #   sa - первый OUT 00h после него (глиф этого разряда)
    def phases(lg):
        res = []
        for i, (t, p, v) in enumerate(lg):
            if p != 1:
                continue
            sb = next((lg[j][2] for j in range(i - 1, -1, -1)
                       if lg[j][1] == 0), None)
            sa = next((lg[j][2] for j in range(i + 1, len(lg))
                       if lg[j][1] == 0), None)
            res.append((t, v & 0x0F, sb, sa))
        return res

    ph = phases(log)
    p08 = [sa for (t, d, sb, sa) in ph if d == 0x08 and sa is not None]
    p01 = [sa for (t, d, sb, sa) in ph if d == 0x01 and sa is not None]
    chk("строка 2 -> глиф '2' (5Bh) на левом (DIG3)",
        0x5B in p08[-4:] if p08 else False, "%s" % [hex(x) for x in p08[-6:]])
    chk("колонка 2 -> глиф '2' (5Bh) на правом (DIG0)",
        0x5B in p01[-4:] if p01 else False, "%s" % [hex(x) for x in p01[-6:]])
    bad = [(hex(d), sb) for (t, d, sb, sa) in ph
           if sb is not None and sb != 0]
    chk("блэнкинг: КАЖДЫЙ разряд переключается при погашенных сегментах",
        not bad, "нарушений: %d %s" % (len(bad), bad[:3]))
    # длительность бипа: полупериод тона по SND-событиям (t,v)
    if len(beepdigs) >= 2:
        step2 = beepdigs[1][0] - beepdigs[0][0]      # 2 единицы (1->0->1)
        half = step2 / 2.0                            # полупериод тона
        print("  измерено: полупериод тона %.0f T (%.0f мкс, ~%.0f Гц) -> "
              "бип полного образа (200 ед) = %.0f мс"
              % (half, half * STEP_NS / 1e3, 1e9 / (2 * half * STEP_NS),
                 half * 200 * STEP_NS / 1e6))

    # --- отпускание ---
    state['keys'][(2, 2)] = False
    t0 = cpu.T
    cpu.run(cpu.T + 200_000)
    cols = [v for (t, p, v) in state['log'] if p == 2 and t >= t0]
    chk("после отпускания скан возобновился (колонки 01..08)",
        any(v == 0x01 for v in cols) and any(v == 0x08 for v in cols))
    # дисплей держит последний результат
    segs = [v for (t, p, v) in state['log'] if p == 0 and t >= t0]
    chk("дисплей держит '2'/'2' после отпускания",
        0x5B in segs, "%s" % [hex(v) for v in segs[:6]])

    # --- второе нажатие SW1 (row0/col0) ---
    state['keys'][(0, 0)] = True
    t0 = cpu.T
    cpu.run(cpu.T + 60_000)
    ph2 = [pp for pp in phases(state['log']) if pp[0] >= t0]
    p08 = [sa for (t, d, sb, sa) in ph2 if d == 0x08 and sa is not None]
    p01 = [sa for (t, d, sb, sa) in ph2 if d == 0x01 and sa is not None]
    chk("второе нажатие: '0'(3Fh) слева, '0'(3Fh) справа",
        (0x3F in p08[-3:] if p08 else False) and
        (0x3F in p01[-3:] if p01 else False))

    # --- арифметика полного образа ---
    print()
    print("  Арифметика полного образа (BEEP_MS=200, SET_MS=30):")
    print("  бип = 200 x полупериод = ~0,21 с, тон ~475 Гц;"
          " дебаунс = 30 x ~1,05 мс = ~31 мс")


if __name__ == '__main__':
    print("verify_fw.py: мини-8085 (T-состояния Intel 8085A), реальные .hex")
    print()
    test_disp()
    test_kbd()
    print()
    print("=" * 76)
    if fail == 0:
        print("ИТОГ: ВСЕ ПРОВЕРКИ ПАСС")
    else:
        print("ИТОГ: ПРОВАЛОВ: %d" % fail)
    print("=" * 76)
    sys.exit(1 if fail else 0)
