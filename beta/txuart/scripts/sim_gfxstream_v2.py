#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Симуляция GFXSTREAM v2 ПО РЕАЛЬНОМУ HEX: интерпретатор 8085 + модель TX
(кадр 8N1 = 31.25T, запись при busy отбрасывается). Поток = исполнение hex.

Проверяется против эталонной модели ТРЁХ СЦЕН:
  1. баннер "\r\nGFXSTREAM v2\\r\\n" ровно 1 раз после ~503 мс POR;
  2. НОЛЬ отбросов TX; мин. межписьменный интервал >= 32T (>= 31.25);
  3. SEQ 0..N-1 без пропусков; N=2000 (TYPE 01) / N=202 (TYPE 02);
  4. побайтовая сверка всех кадров с моделью сцен:
     S0 БЫСТРЫЙ ШАР (250): вход полный, далее дельты 9 строк
        [RMIN..RMIN+8], кейфрейм каждый 100-й кадр сцены; шар 8x7,
        шаг dc=+-2 (flip-recompute от 0/19), dr=+-2 (от 0/92);
     S1 ДИТЕР-ВОЛНА (240): полные кадры, байт строки = DIT[(rr+NEG16[t&15])&15];
     S2 БЕГУЩАЯ СТРОКА (420): вход полный (сетка+полоса), далее дельты
        строк 45..53; битмап сдвигается влево на 1 px перед каждой дельтой;
  5. период КАЖДОГО кадра: обычные пути 125 000T +-120T; кадры входа в
     сцену (switch-блок + копия битмапа) проверяются отдельной строкой.
"""
import sys
from datetime import datetime

BASE = '/home/z/my-project/CPLD-plus-8085/beta/txuart/rom/gfxstream'
HEXNAME = 'gfxstream_v21.hex'   # прошивка под тест
T_FRAME = 146_484                # целевой период кадра, T (46,875 мс = 3 тика дисплея)
T_NS = 320.0
FRAME_T = 31.25
BAN = b"\r\nGFXSTREAM v2.1\r\n"
ENV = 2006

# ---- таблицы (копии asm; расхождение поймает побайтовая сверка) ----
FONT = [
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,  # пробел
    0x00,0x00,0x00,0x7E,0x7E,0x00,0x00,0x00,  # -
    0x3C,0x66,0x6E,0x76,0x66,0x66,0x3C,0x00,  # 0
    0x18,0x38,0x18,0x18,0x18,0x18,0x7E,0x00,  # 1
    0x3C,0x66,0x06,0x0C,0x30,0x60,0x7E,0x00,  # 2
    0x3C,0x66,0x06,0x1C,0x06,0x66,0x3C,0x00,  # 3
    0x7E,0x60,0x7C,0x06,0x06,0x66,0x3C,0x00,  # 5
    0x1C,0x30,0x60,0x7C,0x66,0x66,0x3C,0x00,  # 6
    0x18,0x3C,0x66,0x66,0x7E,0x66,0x66,0x00,  # A
    0x7C,0x66,0x66,0x7C,0x66,0x66,0x7C,0x00,  # B
    0x7C,0x66,0x66,0x66,0x66,0x66,0x7C,0x00,  # D
    0x7E,0x60,0x60,0x7C,0x60,0x60,0x7E,0x00,  # E
    0x7E,0x60,0x60,0x7C,0x60,0x60,0x60,0x00,  # F
    0x3C,0x66,0x60,0x6E,0x66,0x66,0x3C,0x00,  # G
    0x60,0x60,0x60,0x60,0x60,0x60,0x7E,0x00,  # L
    0x66,0x7E,0x7E,0x66,0x66,0x66,0x66,0x00,  # M
    0x3C,0x66,0x66,0x66,0x66,0x66,0x3C,0x00,  # O
    0x7C,0x66,0x66,0x7C,0x60,0x60,0x60,0x00,  # P
    0x7C,0x66,0x66,0x7C,0x6C,0x66,0x66,0x00,  # R
    0x3C,0x66,0x60,0x3C,0x06,0x66,0x3C,0x00,  # S
    0x7E,0x18,0x18,0x18,0x18,0x18,0x18,0x00,  # T
    0x66,0x66,0x66,0x66,0x66,0x3C,0x18,0x00,  # V
    0x66,0x66,0x3C,0x18,0x3C,0x66,0x66,0x00,  # X
]
MSG = [0x0D,0x0C,0x16,0x13,0x14,0x12,0x0B,0x08,0x0F,0x00,
       0x15,0x04,0x00, 0x01,0x00,
       0x03,0x07,0x02,0x16,0x03,0x02,0x02,0x00, 0x01,0x00,
       0x04,0x06,0x0C,0x11,0x13,0x00, 0x01,0x00,
       0x0C,0x08,0x13,0x14,0x00, 0x09,0x08,0x0E,0x0E,0x00,
       0x0A,0x0B,0x0F,0x10,0x00]
MSGN = 48
DIT = [0x00,0x80,0xC0,0xE0,0xF0,0xF8,0xFC,0xFE,0xFF,0x7F,0x3F,0x1F,0x0F,0x07,0x03,0x01]
NEG16 = [0,15,14,13,12,11,10,9,8,7,6,5,4,3,2,1]
MMASK = [0,0,0,0,0,0xE0,0x3F,0,0,0,0,0,0]
LIM = [250, 240, 420]

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
        elif op == 0x17:                                               # RAL
            b7 = (self.A >> 7) & 1
            self.A = ((self.A << 1) | self.CY) & 0xFF; self.CY = b7; tt = 4
        elif op == 0x1F:                                               # RAR
            b0 = self.A & 1
            self.A = (self.A >> 1) | ((self.CY & 1) << 7); self.CY = b0; tt = 4
        elif op == 0x17:                                               # RAL
            b7 = (self.A >> 7) & 1
            self.A = ((self.A << 1) | self.CY) & 0xFF; self.CY = b7; tt = 4
        elif op == 0x1F:                                               # RAR
            b0 = self.A & 1
            self.A = (self.A >> 1) | ((self.CY & 1) << 7); self.CY = b0; tt = 4
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
        elif op == 0x2F:                                               # CMA
            self.A = (~self.A) & 0xFF; tt = 4
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

# ----------------------- эталонная модель сцен -----------------------
def grid_row(rr):
    p = 0xFF if (rr % 8 == 0 or rr == 99) else 0x80
    return [p] * 19 + [p | 0x01]

def row_ball(rr, c, r):
    row = grid_row(rr)
    if r <= rr < r + 7:
        row[c] = 0xFF
    return row

def build_bitmap():
    bm = []
    for i in range(8):
        bm.append([FONT[g * 8 + i] for g in MSG])
    return bm

def model_stream(nframes):
    """Эталонный поток: баннер + nframes кадров. Возвращает (байты, метки путей)."""
    out = bytearray(BAN)
    kinds = []
    bm = build_bitmap()
    scene, T, sw = 0, 0, 1
    c, r, dc, dr = 0, 0, 2, 2
    dph = 0
    prev_r = 0
    for k in range(nframes):
        seq = k & 0xFF
        # --- T++ и switch (как в ROM: до диспетчера) ---
        T += 1
        entry = False
        if T == LIM[scene]:
            scene = (scene + 1) % 3
            T = 0
            sw = 1
            entry = True
        if k == 0:
            entry = True   # первый кадр: SW=1 с init (без switch-блока)
        if scene == 0:
            # модель шара (до ветки типа кадра)
            nc = c + dc
            if nc > 19 or nc < 0:
                dc = -dc; nc = c + dc
            c = nc
            nr = r + dr
            if nr > 92 or nr < 0:
                dr = -dr; nr = r + dr
            rmin = min(prev_r, nr)
            r = nr
            if sw or dph + 1 >= 100:
                kind = 'BF'
                dph = 0
                sw = 0
                pay = bytearray()
                for rr in range(100):
                    pay += bytes(row_ball(rr, c, r))
                out += bytes([0xA5, 0x5A, 0x01, 0xD0, 0x07, seq]) + bytes(pay)
            else:
                kind = 'BD'
                dph += 1
                mask = bytearray(13)
                for rr in range(rmin, rmin + 9):
                    mask[rr >> 3] |= 1 << (rr & 7)
                pay = bytearray(mask)
                for rr in range(rmin, rmin + 9):
                    pay += bytes([rr]) + bytes(row_ball(rr, c, r))
                out += bytes([0xA5, 0x5A, 0x02, 0xCA, 0x00, seq]) + bytes(pay)
                out += b'\xFF' * (ENV - 6 - len(pay))
        elif scene == 1:
            kind = 'DI'
            t = T
            neg = NEG16[t & 15]
            pay = bytearray()
            for rr in range(100):
                v = DIT[(rr + neg) & 15]
                pay += bytes([v] * 20)
            out += bytes([0xA5, 0x5A, 0x01, 0xD0, 0x07, seq]) + bytes(pay)
        else:
            if sw:
                kind = 'MF'
                sw = 0
                bm = build_bitmap()   # копия мастера -> рабочая (как в ROM на входе)
                pay = bytearray()
                for rr in range(100):
                    if 46 <= rr <= 53:
                        pay += bytes(bm[rr - 46][0:20])
                    else:
                        pay += bytes(grid_row(rr))
                out += bytes([0xA5, 0x5A, 0x01, 0xD0, 0x07, seq]) + bytes(pay)
            else:
                kind = 'MD'
                # сдвиг битмапа влево на 1 px
                for i in range(8):
                    row = bm[i]
                    carry = 0
                    for j in range(MSGN - 1, -1, -1):
                        nc2 = ((row[j] >> 1) | (carry << 7)) & 0xFF
                        carry = row[j] & 1
                        row[j] = nc2
                pay = bytearray(MMASK)
                pay += bytes([45]) + bytes(grid_row(45))
                for i in range(8):
                    pay += bytes([46 + i]) + bytes(bm[i][0:20])
                out += bytes([0xA5, 0x5A, 0x02, 0xCA, 0x00, seq]) + bytes(pay)
                out += b'\xFF' * (ENV - 6 - len(pay))
        prev_r = r
        kinds.append('ENTR' if entry else kind)
    return bytes(out), kinds

# ----------------------- разбор потока -----------------------
def parse_frames(s, nframes):
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

# ----------------------- PNG-превью -----------------------
def render_png(frames_fb, scale, path):
    """frames_fb: список построчных FB (100 строк x 20 Б). Плитка в один PNG."""
    import zlib, struct
    n = len(frames_fb)
    cols = 4
    rows = (n + cols - 1) // cols
    W, H = 160, 100
    Wp, Hp = W * scale, H * scale
    img = [[255] * (cols * Wp) for _ in range(rows * Hp)]
    for idx, fb in enumerate(frames_fb):
        cx, cy = (idx % cols) * Wp, (idx // cols) * Hp
        for r in range(H):
            base = fb[r * 20:(r + 1) * 20]
            for x in range(W):
                bit = (base[x >> 3] >> (7 - (x & 7))) & 1
                if bit:
                    for dy in range(scale):
                        yy = cy + r * scale + dy
                        rowpix = img[yy]
                        for dx in range(scale):
                            rowpix[cx + x * scale + dx] = 0
    raw = b''
    for rowpix in img:
        raw += b'\x00' + bytes(rowpix)
    def chunk(typ, data):
        c = struct.pack('>I', len(data)) + typ + data
        return c + struct.pack('>I', zlib.crc32(typ + data) & 0xFFFFFFFF)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', cols * Wp, rows * Hp, 8, 0, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw, 6))
    png += chunk(b'IEND', b'')
    open(path, 'wb').write(png)

def fb_from_frame(fr):
    return fr['pay']

def fb_from_delta(prev_fb, fr):
    fb = bytearray(prev_fb)
    pay = fr['pay']
    mask = pay[:13]
    pos = 13
    while pos < len(pay) and pay[pos] != 0xFF:
        rr = pay[pos]
        fb[rr * 20:(rr + 1) * 20] = pay[pos + 1:pos + 21]
        pos += 21
    return bytes(fb)

def main():
    nframes = int(sys.argv[1]) if len(sys.argv) > 1 else 940
    print(f"== Симуляция {HEXNAME} по реальному hex, {nframes} кадров, целевой период {T_FRAME}T ==")
    ok = True
    def req(cond, msg):
        nonlocal ok
        print(('  OK   ' if cond else '  FAIL ') + msg)
        if not cond: ok = False

    cpu = CPU(load_hex(f'{BASE}/{HEXNAME}'))
    T_POR = 1_572_864 + 200_000
    T_RUN = T_POR + nframes * int(T_FRAME * 1.15) + 500_000   # запас на некалиброванные пады
    s = cpu.run(T_RUN)

    # 1. баннер
    bi = s.find(BAN)
    req(s.count(BAN) == 1, f"баннер ровно 1 ({s.count(BAN)})")
    if bi < 0:
        raise SystemExit("баннер не найден")
    t_ban = cpu.wtimes[0] * T_NS / 1e6
    req(500 < t_ban < 510, f"баннер после POR-паузы: {t_ban:.1f} мс (ожидание ~503)")

    body = s[bi + len(BAN):]
    req(len(body) >= nframes * ENV, f"поток: {len(body)} Б после баннера (нужно {nframes*ENV})")

    # 2. отбросы и мин-гэп
    req(cpu.dropped == 0, f"отбросов TX: {cpu.dropped} (все {cpu.writes} записей ушли на провод)")
    w = cpu.wtimes
    idx0 = len(BAN)
    seg = w[idx0:idx0 + 3 * ENV]
    min_gap = min(seg[i + 1] - seg[i] for i in range(len(seg) - 1))
    req(min_gap >= 32, f"мин. интервал записей внутри кадров: {min_gap}T >= 32T (31.25T)")

    # 3-5. побайтовая сверка с моделью
    ref, kinds = model_stream(nframes)
    req(len(ref) == len(BAN) + nframes * ENV,
        f"модель: {len(ref) - len(BAN)} Б (нужно {nframes*ENV})")
    bad = None
    for k in range(nframes):
        a = body[k * ENV:(k + 1) * ENV]
        b = ref[len(BAN) + k * ENV: len(BAN) + (k + 1) * ENV]
        if a != b:
            bad = k
            break
    req(bad is None, f"побайтовая сверка {nframes} кадров с моделью: "
        + ("OK" if bad is None else f"первое расхождение кадр {bad}"))

    frames = parse_frames(body, nframes)
    seqs = [f['seq'] for f in frames]
    seq_ok = all(seqs[k] == (k & 0xFF) for k in range(nframes))
    req(seq_ok, "SEQ 0..N-1 (mod 256) без пропусков: " + ("да" if seq_ok else
        f"НЕТ {[(k, seqs[k]) for k in range(nframes) if seqs[k] != (k & 0xFF)][:4]}"))
    nbad = [f['n'] for f in frames if f['n'] not in (2000, 202) or
            (f['typ'] == 1 and f['n'] != 2000) or (f['typ'] == 2 and f['n'] != 202)]
    req(not nbad, f"N поля: TYPE 01 -> 2000, TYPE 02 -> 202 (нарушений {len(nbad)})")

    # 6. периоды по путям: интервал до первого байта кадра k включает
    # pre-работу кадра k (switch/копия) -> ENTR по kinds[k]
    groups = {}
    for k in range(nframes - 1):
        dt = int(w[idx0 + (k + 1) * ENV] - w[idx0 + k * ENV])
        kk = 'ENTR' if kinds[k + 1] == 'ENTR' else kinds[k]
        groups.setdefault(kk, []).append(dt)
    print("  периоды по путям (T, 125000 = 40.000 мс):")
    devmax = 0
    for g in sorted(groups):
        v = sorted(groups[g])
        med = v[len(v) // 2]
        pmin, pmax = v[0], v[-1]
        print(f"    {g:4s}: n={len(v):4d} мед {med:6d} мин {pmin:6d} макс {pmax:6d} "
              f"({pmin*T_NS/1000:.3f}..{pmax*T_NS/1000:.3f} мс)")
        if g != 'ENTR':
            dev = max(abs(pmin - T_FRAME), abs(pmax - T_FRAME))
            devmax = max(devmax, dev)
            need = T_FRAME - med
            if need:
                print(f"           -> коррекция пада: {'+' if need>0 else ''}{need}T = "
                      f"{need//24:+d} итераций (+остаток {need - 24*(need//24)}T = "
                      f"{(need - 24*(need//24))//4} NOP)")
    if devmax == 0:
        print(f"  OK   период обычных путей = ровно {T_FRAME}T = {T_FRAME*T_NS/1000:.3f} мс")
    elif devmax <= 120:
        print(f"  OK   период обычных путей {T_FRAME}T ±{devmax}T (±{devmax*T_NS/1000:.0f} мкс)")
    else:
        req(False, f"период обычных путей {T_FRAME}T ±120T: отклонение {devmax}T")
    entr = groups.get('ENTR', [])
    if entr:
        print(f"    ENTR: n={len(entr)} периоды {[int(x) for x in sorted(entr)]} "
              f"({min(entr)*T_NS/1000:.2f}..{max(entr)*T_NS/1000:.2f} мс — switch-блок/копия битмапа)")
        req(max(entr) <= T_FRAME + 21_000, f"кадры входа в сцену <= {T_FRAME+21_000}T: макс {int(max(entr))}")

    # 7. FPS
    fps = (nframes - 1) * 1e6 / ((w[idx0 + (nframes - 1) * ENV] - w[idx0]) * T_NS / 1e3)
    print(f"  FPS по записям: {fps:.3f}")

    # 8. PNG-превью из модели (модель = поток побайтово, доказано выше)
    fbs = []
    cur = None
    picks = {}
    for k in range(nframes):
        fr = frames[k]
        if fr['typ'] == 1:
            cur = fb_from_frame(fr)
        else:
            cur = fb_from_delta(cur, fr)
        picks[k] = cur
    shots = [5, 120, 260, 300, 495, 600, 700, 830]
    for k in shots:
        fbs.append(picks[k])
    try:
        render_png(fbs, 3, '/home/z/my-project/download/gfxstream_v2_preview.png')
        print("  OK   превью: download/gfxstream_v2_preview.png (кадры %s)" % shots)
    except Exception as e:
        print(f"  !    превью не записано: {e}")

    print("== ВСЁ ОК ==" if ok else "== ЕСТЬ ОШИБКИ ==")
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
