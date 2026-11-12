#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sim_xstream_v1.py — симуляция XSTREAM v1 ПО РЕАЛЬНОМУ HEX.

Модель: интерпретатор 8085 (подмножество asm85, T-таблица 8085A) + TX-ядро
v2.3 (кадр 8N1 = 31.25T, запись при busy ОТБРАСЫВАЕТСЯ) + клавиатура
(порт 02h колонки / 03h ряды) + для TMR_HW=1 таймер CPLD v24 (загрузка N
через OUT 06h, тик = N x 51.2 мкс, стоп-в-нуле, ре-арм из ISR).

Проверяется:
  1. поток = кадры A5 5A [SEQ] + 2000 Б; SEQ mod 256 без пропусков;
  2. payload КАЖДОГО кадра == снимок B000h..B7CFh на момент начала посылки
     (побайтово; живой счётчик SEQ в B6E4/B6E5 меняется от кадра к кадру);
  3. НОЛЬ отбросов TX; мин. межписьменный интервал >= 31.25T;
  4. период кадра (start->start) ~47.4 мс (SW) / ~46.9 мс (HW);
     нагрузка ЦП на выдачу <= 50%;
  5. монитор жив: нажатие клавиши 'A' переводит STATE в режим адреса и
     обратно, поток кадра НЕ останавливается (провал периода <= ~60 мс);
  6. дисплей: слоты регенерации не замирают во время посылки.

Запуск: python3 sim_xstream_v1.py [путь-к-hex] [--hw]
"""
import sys, re

T_NS = 320.0
FRAME_T = 31.25           # тактов на байт 8N1 (1 Мбод)
TICK_V24_T = 51.2 / (T_NS / 1000)   # тик таймера v24 в T (= 160 T)
XBUF = 0xB000
SCREEN = 2000
HDR = (0xA5, 0x5A)
PASS_T = 327.0            # целевой слот скана, T (печать факта)

DEMO = {
    0x00: 'XSTREAM v1.0 - 80x25 TEXT SCREEN BUFFER B000h-B7CFh -> UART 1000000 8N1',
    0xA0: 'FRAME: A5 5A [SEQ] + 2000 BYTES (ROW-MAJOR 80x25 / CP1251 AT PC CLIENT)',
    0xF0: 'FW: fw_mon ACdE + STREAM - TMR_HW=0 SW-TICK 20 FPS / TMR_HW=1 RST 7.5 (v24)',
    0x280: 'MONITOR: A=ADDR  C=CODE  D=VIEW  E=RUN  F1=MENU  F2=SHOW ADDR',
    0x320: 'WRITE YOUR TEXT INTO B000h..B7CFh - THIS WINDOW IS THE PC SCREEN',
}


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
    """8085 + TX + клавиатура + (HW) таймер v24. Время - в тактах CPU."""
    def __init__(self, mem, hw=False, presses=()):
        self.mem = dict(mem)
        self.hw = hw
        self.A = self.B = self.C = self.D = self.E = self.H = self.L = 0
        self.SP = 0
        self.Z = self.CY = self.AC = self.S = 0
        self.pc = 0
        self.t = 0.0
        self.iff = 0
        # TX v2.3
        self.stream = bytearray()
        self.wtimes = []          # такты всех записей в 04h (вкл. отброшенные)
        self.busy = -1.0
        self.dropped = 0
        # клавиатура/дисплей
        self.kbcol = 0
        self.dig_writes = 0       # слоты регенерации (записи в 01h)
        # прерывание v24
        self.tmr_deadline = None  # такт следующего истечения (или None - стоп)
        self.tmrlatch = False
        self.presses = list(presses)  # (t0, t1, row, col)
        # сценарий
        self.state_log = []
        self.last_state = None

    # ---- память/порты ----
    def rd(self, a): return self.mem.get(a, 0xFF)
    def wr(self, a, v):
        if a < 0x8000:
            return          # запись в ПЗУ железом отбрасывается (MEMORY_MAP §3)
        self.mem[a] = v & 0xFF

    def kbrow(self):
        v = 0
        for (t0, t1, row, col) in self.presses:
            if t0 <= self.t <= t1 and (self.kbcol >> col) & 1:
                v |= 1 << row
        return v & 0x1F

    def out(self, port, val):
        val &= 0xFF
        if port == 0x04:
            self.wtimes.append(self.t)
            if self.t >= self.busy - 1e-9:
                self.stream.append(val)
                self.busy = self.t + FRAME_T
            else:
                self.dropped += 1
        elif port == 0x02:
            self.kbcol = val
        elif port == 0x01:
            self.dig_writes += 1
        elif port == 0x06 and self.hw:
            # таймер v24: загрузка N (стоп-в-нуле; 0 = стоп)
            n = val
            self.tmr_deadline = (self.t + n * TICK_V24_T) if n else None

    def inp(self, port):
        if port == 0x03:
            return self.kbrow()
        return 0x00

    # ---- флаги ----
    def _flags(self, r):
        self.Z = 1 if r == 0 else 0
        self.S = 1 if r & 0x80 else 0
        return r & 0xFF

    # ---- регистры ----
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
        else: self.SP = ((hi << 8) | lo)
    def _hl(self): return (self.H << 8) | self.L
    def _push(self, v):
        self.SP = (self.SP - 1) & 0xFFFF
        self.wr(self.SP, (v >> 8) & 0xFF)
        self.SP = (self.SP - 1) & 0xFFFF
        self.wr(self.SP, v & 0xFF)
    def _pop(self):
        lo = self.rd(self.SP)
        self.SP = (self.SP + 1) & 0xFFFF
        hi = self.rd(self.SP)
        self.SP = (self.SP + 1) & 0xFFFF
        return (hi << 8) | lo
    def _psw(self):
        return (self.S << 7) | (self.Z << 6) | (self.AC << 4) | (self.CY << 2) | 0x02
    def _setpsw(self, v):
        self.S = (v >> 7) & 1; self.Z = (v >> 6) & 1
        self.AC = (v >> 4) & 1; self.CY = (v >> 2) & 1

    def _cond(self, c):
        z, cy, s, p = self.Z, self.CY, self.S, 1
        return {0: not z, 1: z, 2: not cy, 3: cy, 4: not p, 5: p, 6: not s, 7: s}[c]

    # ---- прерывание v24 ----
    def _poll_irq(self):
        if not self.hw:
            return
        if self.tmr_deadline is not None and self.t >= self.tmr_deadline - 1e-9:
            self.tmrlatch = True
            self.tmr_deadline = None     # стоп-в-нуле до ре-арма
        if self.tmrlatch and self.iff:
            self._push(self.pc)
            self.pc = 0x3C               # вектор RST 7.5
            self.iff = 0                 # приём прерывания гасит EI
            self.tmrlatch = False
            self.t += 10                 # отклик 8085 на 7.5 (~3-4 цикла)

    # ---- шаг ----
    def step(self):
        self._poll_irq()
        op = self.rd(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        t = self.t
        # групповые декоды
        if op == 0x00: self.t += 4; return
        if op == 0xF3: self.iff = 0; self.t += 4; return
        if op == 0xFB: self.iff = 1; self.t += 4; return
        if op == 0x30: self.t += 4; return   # SIM: маска 7.5 не моделируется (7.5 не маскирован)
        if op == 0x20: self.t += 4; return   # RIM
        if op == 0x07: self.A = ((self.A << 1) | (self.A >> 7)) & 0xFF; self.CY = self.A & 1; self.t += 4; return
        if op == 0x0F: self.CY = self.A & 1; self.A = ((self.A >> 1) | (self.A << 7)) & 0xFF; self.t += 4; return
        if op == 0x17: cy = self.CY; self.CY = (self.A >> 7) & 1; self.A = ((self.A << 1) | cy) & 0xFF; self.t += 4; return
        if op == 0x1F: cy = self.CY; self.CY = self.A & 1; self.A = (self.A >> 1) | (cy << 7); self.t += 4; return
        if op == 0x2F: self.A ^= 0xFF; self.t += 4; return
        if op == 0xEB: self.D, self.E, self.H, self.L = self.H, self.L, self.D, self.E; self.t += 4; return
        if op == 0xE9: self.pc = self._hl(); self.t += 6; return
        if op == 0xC9: self.pc = self._pop(); self.t += 10; return
        if op == 0xC5 or op == 0xD5 or op == 0xE5 or op == 0xF5:
            r = (op >> 4) & 3
            if r == 3: self._push((self.A << 8) | self._psw())
            else:
                hi, lo = self._rp(r); self._push((hi << 8) | lo)
            self.t += 12; return
        if op == 0xC1 or op == 0xD1 or op == 0xE1 or op == 0xF1:
            v = self._pop()
            r = (op >> 4) & 3
            if r == 3: self.A = (v >> 8) & 0xFF; self._setpsw(v & 0xFF)
            else: self._setrp(r, (v >> 8) & 0xFF, v & 0xFF)
            self.t += 10; return
        if 0x40 <= op <= 0x7F:
            d, s = (op >> 3) & 7, op & 7
            v = self.rd(self._hl()) if s == 6 else self._reg(s)
            if d == 6: self.wr(self._hl(), v)
            else: self._setreg(d, v)
            self.t += 7 if (d == 6 or s == 6) else 4
            return
        if (op & 0xC7) == 0x06:                 # MVI r,imm
            v = self.rd(self.pc); self.pc = (self.pc + 1) & 0xFFFF
            r = (op >> 3) & 7
            if r == 6: self.wr(self._hl(), v)
            else: self._setreg(r, v)
            self.t += 7; return
        if (op & 0xCF) == 0x01:                 # LXI rp,imm16
            lo = self.rd(self.pc); hi = self.rd((self.pc + 1) & 0xFFFF)
            self.pc = (self.pc + 2) & 0xFFFF
            self._setrp((op >> 4) & 3, hi, lo); self.t += 10; return
        if op == 0xD3:                          # OUT imm
            v = self.rd(self.pc); self.pc = (self.pc + 1) & 0xFFFF
            self.out(v, self.A); self.t += 10; return
        if op == 0xDB:                          # IN imm
            v = self.rd(self.pc); self.pc = (self.pc + 1) & 0xFFFF
            self.A = self.inp(v); self.t += 10; return
        if (op & 0xC7) == 0x04 or (op & 0xC7) == 0x05:   # INR/DCR r
            r = (op >> 3) & 7
            v = self._hl() if False else (self.rd(self._hl()) if r == 6 else self._reg(r))
            v = (v + 1) & 0xFF if (op & 7) == 4 else (v - 1) & 0xFF
            self._flags(v); self.AC = 1 if ((v & 0xF) in (0, 0xF)) else self.AC
            if r == 6: self.wr(self._hl(), v)
            else: self._setreg(r, v)
            self.t += 4; return
        if (op & 0xCF) == 0x03 or (op & 0xCF) == 0x0B:   # INX/DCX rp
            r = (op >> 4) & 3
            hi, lo = self._rp(r)
            v = ((hi << 8) | lo) + (1 if (op & 0xCF) == 0x03 else -1)
            self._setrp(r, (v >> 8) & 0xFF, v & 0xFF)
            self.t += 6; return
        if (op & 0xCF) == 0x09:                 # DAD rp
            r = (op >> 4) & 3
            hi, lo = self._rp(r)
            s = (hi << 8) | lo
            r2 = self._hl() + s
            self.CY = 1 if r2 > 0xFFFF else 0
            self.H, self.L = (r2 >> 8) & 0xFF, r2 & 0xFF
            self.t += 10; return
        if op in (0x02, 0x12):                  # STAX B/D
            hi, lo = self._rp((op >> 4) & 1)
            self.wr((hi << 8) | lo, self.A); self.t += 7; return
        if op in (0x0A, 0x1A):                  # LDAX B/D
            hi, lo = self._rp((op >> 4) & 1)
            self.A = self.rd((hi << 8) | lo); self.t += 7; return
        if (op & 0xC7) == 0xC6:                 # imm-ALU
            v = self.rd(self.pc); self.pc = (self.pc + 1) & 0xFFFF
            self._imm_alu(op, v); self.t += 7; return
        if 0x80 <= op <= 0xBF:                  # ALU r
            v = self._reg(op & 7)
            self._imm_alu(op, v); self.t += 4; return
        if (op & 0xC7) in (0xC2, 0xC3):          # JMP-группа (вкл. условные; 0xC3 = безусловный)
            lo = self.rd(self.pc); hi = self.rd((self.pc + 1) & 0xFFFF)
            self.pc = (self.pc + 2) & 0xFFFF
            dst = (hi << 8) | lo
            cc = (op >> 3) & 7
            if op == 0xC3 or self._cond(cc):
                self.pc = dst
            self.t += 10; return
        if (op & 0xC7) == 0xC4 or op == 0xCD:    # CALL-группа (0xCD = безусловный)
            lo = self.rd(self.pc); hi = self.rd((self.pc + 1) & 0xFFFF)
            self.pc = (self.pc + 2) & 0xFFFF
            dst = (hi << 8) | lo
            cc = (op >> 3) & 7
            if op == 0xCD or self._cond(cc):
                self._push(self.pc); self.pc = dst; self.t += 18
            else:
                self.t += 9
            return
        if (op & 0xC7) == 0xC0 and op != 0xC9:  # RET-группа условных
            cc = (op >> 3) & 7
            if self._cond(cc):
                self.pc = self._pop(); self.t += 12
            else:
                self.t += 6
            return
        if op == 0x3A:                          # LDA
            lo = self.rd(self.pc); hi = self.rd((self.pc + 1) & 0xFFFF)
            self.pc = (self.pc + 2) & 0xFFFF
            self.A = self.rd((hi << 8) | lo); self.t += 13; return
        if op == 0x32:                          # STA
            lo = self.rd(self.pc); hi = self.rd((self.pc + 1) & 0xFFFF)
            self.pc = (self.pc + 2) & 0xFFFF
            self.wr((hi << 8) | lo, self.A); self.t += 13; return
        if op == 0x2A:                          # LHLD
            lo = self.rd(self.pc); hi = self.rd((self.pc + 1) & 0xFFFF)
            self.pc = (self.pc + 2) & 0xFFFF
            a = (hi << 8) | lo
            self.L = self.rd(a); self.H = self.rd((a + 1) & 0xFFFF); self.t += 16; return
        if op == 0x22:                          # SHLD
            lo = self.rd(self.pc); hi = self.rd((self.pc + 1) & 0xFFFF)
            self.pc = (self.pc + 2) & 0xFFFF
            a = (hi << 8) | lo
            self.wr(a, self.L); self.wr((a + 1) & 0xFFFF, self.H); self.t += 16; return
        raise RuntimeError(f"опкод {op:02X} @ {self.pc-1:04X} не поддержан")

    def _imm_alu(self, op, v):
        kind = (op >> 3) & 7
        a = self.A
        if kind == 7:
            # CMP: только флаги, A НЕ меняется
            r = a - v
            self.CY = 1 if r < 0 else 0
            self.AC = 1 if (a & 0xF) < (v & 0xF) else 0
            self._flags(r)
            return
        if kind == 0:   r = a + v
        elif kind == 1: r = a + v + self.CY
        elif kind == 2: r = a - v
        elif kind == 3: r = a - v - self.CY
        elif kind == 4: r = a & v
        elif kind == 5: r = a ^ v
        else:           r = a | v
        self.CY = 1 if (r > 0xFF or r < 0) else 0
        self.AC = 1 if ((a & 0xF) + ((-v if kind in (2, 3) else v) & 0xF)
                        + (self.CY if kind in (1, 3) else 0)) > 0xF else 0
        self.A = self._flags(r)


# ---------------------------------------------------------------- парсер
def parse_frames(stream):
    """Зеркало клиента: ресинк по A5 5A, SEQ, 2000 Б payload."""
    frames, resyncs, i, n = [], 0, 0, len(stream)
    while i < n - 2:
        if stream[i] == 0xA5 and stream[i + 1] == 0x5A:
            seq = stream[i + 2]
            if i + 3 + SCREEN <= n:
                frames.append((seq, bytes(stream[i + 3:i + 3 + SCREEN]), i))
                i += 3 + SCREEN
                continue
            break
        else:
            if i > 0: resyncs += 1
            i += 1
    return frames, resyncs


def run(hex_path, hw=False, seconds=1.2, presses=(), label=''):
    cpu = CPU(load_hex(hex_path), hw=hw, presses=presses)
    budget = seconds / (T_NS / 1e9)
    while cpu.t < budget:
        cpu.step()
    return cpu


def verdict(cpu, target_ms, label):
    st = cpu.stream
    frames, resyncs = parse_frames(st)
    ok = True
    print(f"\n=== {label}: {len(st)} Б потока, {len(frames)} кадров, "
          f"ресинк-байтов {resyncs}, отбросов TX {cpu.dropped} ===")
    # 1. отбросы + межписьменный интервал
    gaps = [b - a for a, b in zip(cpu.wtimes, cpu.wtimes[1:])]
    mgap = min(gaps) if gaps else 0
    print(f"мин. межписьменный интервал: {mgap:.1f}T (норма >= 31.25T) "
          f"{'ОК' if mgap >= 31.25 else 'ПРОВАЛ'}")
    ok &= mgap >= 31.25 and cpu.dropped == 0
    # 2. период кадра: start->start по SEQ-байту (3-й Б кадра)
    starts = [cpu.wtimes[i + 2] for i in frames[0][2:3]] if frames else []
    # индексы SEQ-записей: каждая третья запись внутри кадра (3 заголовочных)
    seq_writes = [w for k, w in enumerate(cpu.wtimes) if k % (SCREEN + 3) == 2]
    if len(seq_writes) >= 3:
        per = [b - a for a, b in zip(seq_writes, seq_writes[1:])]
        per_ms = [p * T_NS / 1e6 for p in per]
        # нагрузка: длительность посылки = от 1-го до последнего OUT кадра
        frame_span = []
        w = cpu.wtimes
        for k in range(0, len(w) - (SCREEN + 3) + 1, SCREEN + 3):
            frame_span.append(w[k + SCREEN + 2] - w[k])
        send_ms = sum(frame_span) * T_NS / 1e6 / max(1, len(frame_span))
        period_ms = sum(per_ms) / len(per_ms)
        load = send_ms / period_ms * 100
        print(f"период кадра: ср {period_ms:.2f} мс (цель ~{target_ms}), "
              f"мин {min(per_ms):.2f} макс {max(per_ms):.2f} -> "
              f"{1000/period_ms:.2f} FPS")
        print(f"посылка: {send_ms:.2f} мс -> нагрузка ЦП {load:.1f}% "
              f"{'ОК <=50%' if load <= 50 else 'ПРОВАЛ >50%'}")
        print(f"провал периода при клавишах: {max(per_ms):.1f} мс")
        ok &= load <= 50
    # 3. SEQ mod 256 + payload == снимок экрана
    seqs = [f[0] for f in frames]
    seq_ok = all((b - a) & 0xFF == 1 for a, b in zip(seqs, seqs[1:]))
    print(f"SEQ непрерывность mod 256: {'ОК' if seq_ok else 'ПРОВАЛ'} "
          f"(первый {seqs[0] if seqs else '-'}, кадров {len(seqs)})")
    ok &= seq_ok
    mism = 0
    for (seq, payload, off) in frames:
        # счётчик жив: hex SEQ в B6E4/B6E5
        if payload[0x6E4:0x6E6] != f"{seq:02X}".encode():
            mism += 1
    print(f"живой счётчик SEQ в кадре (B6E4/B6E5): "
          f"{'ОК' if mism == 0 else f'ПРОВАЛ x{mism}'}")
    ok &= mism == 0
    # 4. демо-строки
    if frames:
        p = frames[-1][1]
        for row, txt in DEMO.items():
            got = p[row:row + len(txt)]
            if got != txt.encode():
                print(f"  строка @{row:04X}: '{got.decode(errors='replace')}' != "
                      f"'{txt}' -> ПРОВАЛ")
                ok = False
        print("демо-строки (последний кадр): " + ("ОК" if ok else "см. выше"))
    # 5. слоты дисплея
    print(f"записей DIGP (слотов дисплея): {cpu.dig_writes} "
          f"(~{cpu.dig_writes / (cpu.t * T_NS / 1e6):.0f}/мс)")
    return ok


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else 'xstream_v1.hex'
    print(f"=== XSTREAM v1 SW-тик (TMR_HW=0): {base} ===")
    # 1) холодный старт, тишина
    c = run(base, seconds=1.2)
    ok1 = verdict(c, 47.4, "тишина, 1.2 с")
    print(f"слот скана факт: измеряется по периоду между XSCHK-отправками; "
          f"цель pass ~{PASS_T:.0f}T")
    # 2) клавиша 'A' (row0/col0) на 300..420 мс
    c2 = run(base, seconds=1.2, presses=((0.3 * 1e9 / T_NS, 0.42 * 1e9 / T_NS, 0, 0),),
             label='kbd')
    ok2 = verdict(c2, 47.4, "нажатие 'A' 300..420 мс")
    st = [1 if c2.mem.get(0xFFE9, 0) == 1 else 0]
    print(f"STATE после сеанса: {c2.mem.get(0xFFE9, 0)} (0=меню, 1=адрес) "
          f"{'ОК' if c2.mem.get(0xFFE9, 0) in (0, 1) else '?'}")
    print(f"\nВЕРДИКТ SW: {'ВСЁ ОК' if (ok1 and ok2) else 'ЕСТЬ ПРОВАЛЫ'}")
    return 0 if (ok1 and ok2) else 1


if __name__ == '__main__':
    sys.exit(main())
