#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Симуляция GFXSTREAM v1 ПО РЕАЛЬНОМУ HEX: мини-интерпретатор 8085 +
модель TX-ядра v2.3 (кадр 8N1 = 31.25T при 1М бод, запись при busy
тихо отбрасывается). Поток генерируется ИСПОЛНЕНИЕМ hex.

Проверяется (против эталонной модели паттерна):
  1. баннер "\r\nGFXSTREAM v1\\r\\n" ровно 1 раз, после ~503 мс POR;
  2. НОЛЬ отбросов TX (все записи в порт уходят на провод);
  3. SEQ кадров 0,1,2,... без пропусков; TYPE: 0..74 полный (01),
     далее дельта (02), каждый 100-й кадр — полный (ресинк);
  4. TYPE 01: N=2000, payload = сетка 8x8 + шар 8x8 в расчной позиции
     (побайтово, 100 строк x 20 Б);
  5. TYPE 02: N=202, маска 13 Б = строки [min(r_prev,r_new)..max+7],
     9 блоков [номер][20 Б] == строки расчного кадра, хвост = FFh;
  6. период кадра = 125 000T = 40.000 мс (25.000 FPS) в ОБЕИХ режимах
     (калибровка W_FULL/W_DEL + PAD);
  7. темп посылки 47T/Б: межписьменные интервалы в кадре >= 31.25T.
"""
import sys, re

BASE = '/home/z/my-project/CPLD-plus-8085/beta/txuart/rom/gfxstream'
T_NS = 320.0
FRAME_T = 31.25
BAN = b"\r\nGFXSTREAM v1\r\n"
ENV = 2006            # конверт кадра на проводе
NPAY = 2000           # payload TYPE 01
NDELTA = 13 + 9 * 21  # payload TYPE 02 = 202

def load_hex(path):
    mem = {}
    for ln in open(path):
        ln = ln.strip()
        assert ln.startswith(':'), ln
        b = bytes.fromhex(ln[1:])
        assert (sum(b) & 0xFF) == 0, f"CS fail {ln}"
        cnt, a, typ = b[0], (b[1] << 8) | b[2], b[3]
        if typ == 0:
            for i, v in enumerate(b[4:4 + cnt]):
                mem[a + i] = v
        elif typ == 1:
            break
    return mem

class CPU:
    """8085 (подмножество asm8085) + корпус TX. Время - в тактах CPU."""
    def __init__(self, mem):
        self.mem = dict(mem)
        self.A = self.B = self.C = self.D = self.E = self.H = self.L = 0
        self.SP = 0
        self.Z = 0; self.CY = 0; self.AC = 0; self.S = 0
        self.pc = 0
        self.t = 0.0
        self.stream = bytearray()
        self.busy = -1.0
        self.writes = 0
        self.wtimes = []
        self.dropped = 0

    def rd(self, a): return self.mem.get(a, 0xFF)
    def wr(self, a, v): self.mem[a] = v & 0xFF

    def _reg(self, r):
        return (self.B, self.C, self.D, self.E, self.H, self.L, 0, self.A)[r]

    def _setreg(self, r, v):
        if r == 0: self.B = v
        elif r == 1: self.C = v
        elif r == 2: self.D = v
        elif r == 3: self.E = v
        elif r == 4: self.H = v
        elif r == 5: self.L = v
        elif r == 7: self.A = v

    def _rp(self, r):
        return ((self.B, self.D, self.H, self.SP)[r], (self.C, self.E, self.L, 0)[r])

    def _setrp(self, r, hi, lo):
        if r == 0: self.B, self.C = hi, lo
        elif r == 1: self.D, self.E = hi, lo
        elif r == 2: self.H, self.L = hi, lo
        else: self.SP = (hi << 8) | lo

    def _hl(self): return (self.H << 8) | self.L

    def out(self, port, val):
        if port == 0x04:
            self.writes += 1
            self.wtimes.append(self.t)
            if self.t >= self.busy - 1e-9:
                self.stream.append(val)
                self.busy = self.t + FRAME_T
            else:
                self.dropped += 1

    def _alu_add(self, v, with_cy=False):
        c = self.CY if with_cy else 0
        r = self.A + v + c
        self.CY = 1 if r > 0xFF else 0
        self.AC = 1 if ((self.A & 0xF) + (v & 0xF) + c) > 0xF else 0
        self.A = r & 0xFF
        self.Z = 1 if self.A == 0 else 0
        self.S = 1 if self.A & 0x80 else 0

    def step(self):
        m = self.rd; pc = self.pc
        op = m(pc); size, tt = 1, 4
        if op == 0x00 or op == 0xF3 or op == 0xFB: tt = 4              # NOP/DI/EI
        elif op == 0x07:                                               # RLC
            b7 = (self.A >> 7) & 1
            self.A = ((self.A << 1) | b7) & 0xFF; self.CY = b7; tt = 4
        elif op == 0x0F:                                               # RRC
            b0 = self.A & 1
            self.A = (self.A >> 1) | (b0 << 7); self.CY = b0; tt = 4
        elif 0x40 <= op <= 0x7F and op != 0x76:                        # MOV d,s
            d, s = (op >> 3) & 7, op & 7
            src = self.rd(self._hl()) if s == 6 else self._reg(s)
            if d == 6: self.wr(self._hl(), src)
            else: self._setreg(d, src)
            tt = 7 if (d == 6 or s == 6) else 4
        elif op < 0x40 and (op & 7) == 6:                              # MVI r/M,nn
            v = m(pc + 1)
            if ((op >> 3) & 7) == 6: self.wr(self._hl(), v); tt = 10
            else: self._setreg((op >> 3) & 7, v); tt = 7
            size = 2
        elif op in (0x01, 0x11, 0x21, 0x31):                           # LXI rp
            self._setrp((op >> 4) & 3, m(pc + 2), m(pc + 1)); size, tt = 3, 10
        elif op == 0xD3:                                               # OUT nn
            self.out(m(pc + 1), self.A); size, tt = 2, 10
        elif op == 0xDB:                                               # IN nn
            self.A = 0x00; size, tt = 2, 10
        elif op < 0x40 and (op & 7) == 4:                              # INR r/M
            r = (op >> 3) & 7
            if r == 6:
                a = self._hl(); v = (self.rd(a) + 1) & 0xFF
                self.wr(a, v); tt = 10
            else:
                v = (self._reg(r) + 1) & 0xFF; self._setreg(r, v); tt = 4
            self.Z = 1 if v == 0 else 0
        elif op < 0x40 and (op & 7) == 5:                              # DCR r/M
            r = (op >> 3) & 7
            if r == 6:
                a = self._hl(); v = (self.rd(a) - 1) & 0xFF
                self.wr(a, v); tt = 10
            else:
                v = (self._reg(r) - 1) & 0xFF; self._setreg(r, v); tt = 4
            self.Z = 1 if v == 0 else 0
        elif op in (0x03, 0x13, 0x23, 0x0B, 0x1B, 0x2B):               # INX/DCX rp
            hi, lo = self._rp((op >> 4) & 3)
            d = 1 if (op & 0x08) == 0 else -1
            v = (((hi << 8) | lo) + d) & 0xFFFF
            self._setrp((op >> 4) & 3, (v >> 8) & 0xFF, v & 0xFF); tt = 6
        elif op in (0x09, 0x19, 0x29, 0x39):                           # DAD rp
            hi, lo = self._rp((op >> 4) & 3)
            hl = self._hl() + ((hi << 8) | lo)
            self.CY = 1 if hl > 0xFFFF else 0
            hl &= 0xFFFF
            self.H, self.L = (hl >> 8) & 0xFF, hl & 0xFF; tt = 10
        elif op in (0x02, 0x12):                                       # STAX B/D
            hi, lo = self._rp(0 if op == 0x02 else 1)
            self.wr((hi << 8) | lo, self.A); tt = 7
        elif op in (0x0A, 0x1A):                                       # LDAX B/D
            hi, lo = self._rp(0 if op == 0x0A else 1)
            self.A = self.rd((hi << 8) | lo); tt = 7
        elif op == 0x3A:                                               # LDA aaaa
            self.A = self.rd(m(pc + 1) | (m(pc + 2) << 8)); size, tt = 3, 13
        elif op == 0x32:                                               # STA aaaa
            self.wr(m(pc + 1) | (m(pc + 2) << 8), self.A); size, tt = 3, 13
        elif op == 0xEB:                                               # XCHG
            self.D, self.E, self.H, self.L = self.H, self.L, self.D, self.E; tt = 4
        elif 0x80 <= op <= 0x87:                                       # ADD r
            src = self.rd(self._hl()) if (op & 7) == 6 else self._reg(op & 7)
            self._alu_add(src); tt = 7 if (op & 7) == 6 else 4
        elif 0x88 <= op <= 0x8F:                                       # ADC r
            src = self.rd(self._hl()) if (op & 7) == 6 else self._reg(op & 7)
            self._alu_add(src, with_cy=True); tt = 7 if (op & 7) == 6 else 4
        elif 0xB8 <= op <= 0xBF:                                       # CMP r
            src = self.rd(self._hl()) if (op & 7) == 6 else self._reg(op & 7)
            r = (self.A - src) & 0xFF
            self.CY = 1 if self.A < src else 0
            self.Z = 1 if r == 0 else 0; tt = 4
        elif 0xA8 <= op <= 0xAF:                                       # XRA r
            src = self.rd(self._hl()) if (op & 7) == 6 else self._reg(op & 7)
            self.A ^= src; self.CY = 0; self.AC = 0
            self.Z = 1 if self.A == 0 else 0; tt = 4
        elif 0xB0 <= op <= 0xB7:                                       # ORA r
            src = self.rd(self._hl()) if (op & 7) == 6 else self._reg(op & 7)
            self.A |= src; self.CY = 0; self.AC = 0
            self.Z = 1 if self.A == 0 else 0; tt = 4
        elif 0xA0 <= op <= 0xA7:                                       # ANA r
            src = self.rd(self._hl()) if (op & 7) == 6 else self._reg(op & 7)
            self.A &= src; self.CY = 0; self.AC = 0
            self.Z = 1 if self.A == 0 else 0; tt = 4
        elif op == 0xE6:                                               # ANI nn
            self.A &= m(pc + 1); self.CY = 0; self.AC = 0
            self.Z = 1 if self.A == 0 else 0; size, tt = 2, 7
        elif op == 0xF6:                                               # ORI nn
            self.A |= m(pc + 1); self.CY = 0; self.AC = 0
            self.Z = 1 if self.A == 0 else 0; size, tt = 2, 7
        elif op == 0xC6:                                               # ADI nn
            self._alu_add(m(pc + 1)); size, tt = 2, 7
        elif op == 0xCE:                                               # ACI nn
            self._alu_add(m(pc + 1), with_cy=True); size, tt = 2, 7
        elif op == 0xFE:                                               # CPI nn
            v = m(pc + 1)
            r = (self.A - v) & 0xFF
            self.CY = 1 if self.A < v else 0
            self.Z = 1 if r == 0 else 0; size, tt = 2, 7
        elif op == 0xC3:                                               # JMP
            self.pc = m(pc + 1) | (m(pc + 2) << 8); self.t += 10; return
        elif op == 0xC2:                                               # JNZ
            size, tt = 3, 7
            if not self.Z:
                self.pc = m(pc + 1) | (m(pc + 2) << 8); self.t += 10; return
        elif op == 0xCA:                                               # JZ
            size, tt = 3, 7
            if self.Z:
                self.pc = m(pc + 1) | (m(pc + 2) << 8); self.t += 10; return
        elif op == 0xD2:                                               # JNC
            size, tt = 3, 7
            if not self.CY:
                self.pc = m(pc + 1) | (m(pc + 2) << 8); self.t += 10; return
        elif op == 0xDA:                                               # JC
            size, tt = 3, 7
            if self.CY:
                self.pc = m(pc + 1) | (m(pc + 2) << 8); self.t += 10; return
        else:
            raise SystemExit(f"неизвестный опкод {op:02X} @ {pc:04X}")
        self.t += tt
        self.pc = (pc + size) & 0xFFFF

    def run(self, t_limit):
        while self.t < t_limit:
            self.step()
        return bytes(self.stream)

# ----------------------- эталонная модель -----------------------
def grid_payload():
    fb = bytearray()
    for r in range(100):
        for j in range(20):
            fb.append(0xFF if (r % 8 == 0 or r == 99) else (0x81 if j == 19 else 0x80))
    return fb

GRID = grid_payload()

def fb_with_ball(c, r):
    fb = bytearray(GRID)
    for i in range(8):
        fb[(r + i) * 20 + c] = 0xFF
    return bytes(fb)

def model_stream(nframes):
    """Эталонный поток: баннер + nframes кадров."""
    out = bytearray(BAN)
    c, r, dc, dr = 0, 0, 1, 1
    dph = 0
    prev = (c, r)
    for k in range(nframes):
        nc, nr = c + dc, r + dr
        if nc == 0 or nc == 19: dc = -dc
        if nr == 0 or nr == 92: dr = -dr
        dph += 1
        wrap = dph == 100
        if wrap: dph = 0
        full = k < 75 or wrap
        seq = k & 0xFF
        fb = fb_with_ball(nc, nr)
        if full:
            out += bytes([0xA5, 0x5A, 0x01, 0xD0, 0x07, seq]) + fb
        else:
            mask = bytearray(13)
            rmin, rmax = min(prev[1], nr), max(prev[1], nr)
            for rr in range(rmin, rmax + 8):
                mask[rr >> 3] |= 1 << (rr & 7)
            pay = bytearray(mask)
            for rr in range(rmin, rmax + 8):
                pay += bytes([rr]) + fb[rr * 20:(rr + 1) * 20]
            assert len(pay) == NDELTA, len(pay)
            frame = bytes([0xA5, 0x5A, 0x02, 0xCA, 0x00, seq]) + pay
            assert len(frame) <= ENV
            frame += b'\xFF' * (ENV - len(frame))
            out += frame
        prev = (nc, nr); c, r = nc, nr
    return bytes(out)

# ----------------------- разбор потока -----------------------
def parse_frames(s, nframes):
    """s = принятый поток после баннера. Возвращает список кадров."""
    frames = []
    pos = 0
    for k in range(nframes):
        if s[pos:pos + 2] != b'\xA5\x5A':
            raise SystemExit(f"кадр {k}: нет магии A5 5A @ {pos} "
                             f"(байты {s[pos:pos+8].hex()})")
        typ = s[pos + 2]
        n = s[pos + 3] | (s[pos + 4] << 8)
        seq = s[pos + 5]
        pay = s[pos + 6:pos + 6 + n]
        rest = s[pos + 6 + n:pos + ENV]
        frames.append(dict(typ=typ, n=n, seq=seq, pay=pay, rest=rest))
        pos += ENV
    return frames

def main():
    nframes = int(sys.argv[1]) if len(sys.argv) > 1 else 130
    print(f"== Симуляция GFXSTREAM v1 по реальному hex, {nframes} кадров ==")
    ok = True
    def req(cond, msg):
        nonlocal ok
        print(('  OK   ' if cond else '  FAIL ') + msg)
        if not cond: ok = False

    cpu = CPU(load_hex(f'{BASE}/gfxstream_v1.hex'))
    T_POR = 1_572_864 + 200_000          # POR-пауза ~503 мс + запас
    T_RUN = T_POR + nframes * 125_000 + 250_000
    s = cpu.run(T_RUN)

    # 1. баннер
    bi = s.find(BAN)
    req(s.count(BAN) == 1, f"баннер \"GFXSTREAM v1\" ровно 1 ({s.count(BAN)})")
    if bi < 0:
        raise SystemExit("баннер не найден")
    t_ban = cpu.wtimes[0] * T_NS / 1e6
    req(500 < t_ban < 510, f"баннер после POR-паузы: {t_ban:.1f} мс (ожидание ~503)")

    body = s[bi + len(BAN):]
    req(len(body) >= nframes * ENV, f"поток: {len(body)} Б после баннера (нужно {nframes*ENV})")

    # 2. ноль отбросов TX
    req(cpu.dropped == 0, f"отбросов TX: {cpu.dropped} (все {cpu.writes} записей ушли на провод)")

    # 3-5. кадры против модели
    ref = model_stream(nframes)
    frames = parse_frames(body, nframes)
    seqs = [f['seq'] for f in frames]
    req(seqs == list(range(nframes)), f"SEQ 0..{nframes-1} без пропусков: "
        f"{'да' if seqs == list(range(nframes)) else seqs[:8]+['...']}")
    types = ['full' if (f['typ'] == 1) else ('delta' if f['typ'] == 2 else '?') for f in frames]
    want = []
    dph = 0; c, r, dc, dr = 0, 0, 1, 1
    for k in range(nframes):
        nc, nr = c + dc, r + dr
        if nc == 0 or nc == 19: dc = -dc
        if nr == 0 or nr == 92: dr = -dr
        dph += 1
        wrap = dph == 100
        if wrap: dph = 0
        want.append('full' if (k < 75 or wrap) else 'delta')
        c, r = nc, nr
    req(types == want, f"типы кадров по модели: "
        f"{'да' if types == want else [(i, types[i], want[i]) for i in range(nframes) if types[i]!=want[i]][:5]}")

    bad = 0; first_bad = None
    for k, (fr, rfr) in enumerate(zip(frames, [None] + frames[:-1])):
        if fr['typ'] == 1:
            exp = ref[len(BAN) + k * ENV: len(BAN) + k * ENV + ENV]
            got = bytes([0xA5, 0x5A, 0x01, 0xD0, 0x07, fr['seq']]) + fr['pay'] + fr['rest']
            if got != exp or fr['n'] != 2000:
                bad += 1
                if first_bad is None: first_bad = k
        else:
            exp = ref[len(BAN) + k * ENV: len(BAN) + k * ENV + ENV]
            got = bytes([0xA5, 0x5A, 0x02, fr['n'] & 0xFF, (fr['n'] >> 8) & 0xFF, fr['seq']]) + fr['pay'] + fr['rest']
            if got != exp or fr['n'] != NDELTA:
                bad += 1
                if first_bad is None: first_bad = k
    req(bad == 0, f"побайтовая сверка {nframes} кадров с моделью: расхождений {bad}"
        + (f", первый кадр {first_bad}" if first_bad is not None else ""))

    # 6. период кадра (единая задержка + выровненная работа путей)
    w = [int(x) for x in cpu.wtimes]
    all_dt = {}
    for k in range(1, nframes):
        dt = w[16 + k * ENV] - w[16 + (k - 1) * ENV]
        all_dt.setdefault(dt, []).append(k)
    pmin, pmax = min(all_dt), max(all_dt)
    print(f"  периоды кадров: мин {pmin}T ({pmin*T_NS/1000:.3f} мс), "
          f"макс {pmax}T ({pmax*T_NS/1000:.3f} мс), "
          f"разброс {pmax-pmin}T ({(pmax-pmin)*T_NS/1000:.1f} мкс), "
          f"значений {len(all_dt)}")
    dev = max(abs(pmin - 125_000), abs(pmax - 125_000))
    if dev == 0:
        print("  OK   период = ровно 125 000T = 40.000 мс (25.000 FPS)")
    elif dev <= 120:
        print(f"  OK   период 125 000T ±{dev}T (±{dev*T_NS/1000:.0f} мкс) — "
              f"веточный джиттер, FPS 25.000±0.1")
    else:
        need = 125_000 - (pmin + pmax) // 2
        print(f"  !    средний период off на {need}T: "
              f"W_FRAME {need//24:+d} (-> {927 + need//24}), остаток "
              f"{need - 24*(need//24)}T — NOP/ORI-доводка")
    req(dev <= 120, f"период обоих режимов 125 000T ±120T (25.000 FPS): "
        f"отклонение {dev}T")

    # 7. межписьменные интервалы >= 31.25T внутри кадров
    min_gap = min(w[i + 1] - w[i] for i in range(16, min(16 + 3 * ENV, len(w) - 1)))
    req(min_gap >= 31, f"мин. интервал записей внутри кадров: {min_gap}T >= 31.25T")

    fps = (nframes - 1) * 1e6 / ((w[16 + (nframes - 1) * ENV] - w[16]) * T_NS / 1e3)
    print(f"  FPS по записям: {fps:.3f} (период 40 мс -> 25.000)")
    print("== ВСЁ ОК ==" if ok else "== ЕСТЬ ОШИБКИ ==")
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
