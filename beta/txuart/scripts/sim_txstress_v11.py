#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Симуляция TXSTRESS v1.1 ПО РЕАЛЬНОМУ HEX: мини-интерпретатор 8085 +
модель ядра TX (кадр 8N1 = 31.25T при 1М бод, запись при busy тихо
отбрасывается). Поток генерируется ИСПОЛНЕНИЕМ hex, а не моделью автора.

Проверяется:
  1. баннер "\r\nTXSTRESS v1.1\r\n" ровно 1 раз за цикл, N циклов;
  2. лендмарков ровно 7 за цикл: B=0020..00E0, каждый с токеном
     " TXSTRESS\\r\\n" (фикс бага v1.0: гейт был по старшему байту D,
     лендмарк печатался КАЖДЫЙ блок - 256 строк вместо 7);
  3. FLOOD: 65536 байт +1 mod 256 за цикл, целость вне лендмарков;
  4. SPRINT: слепо 16384 записей по 31T -> принято ровно 8192 'U';
  5. BURST: слепо 8192 записей по 14.875T -> принято 2731 'U' (k=3);
  6. между "BURST OK\\r\\n" и следующим баннером - 0 байт (пауза ~19.7 мс);
  7. TX_BOTH=1: раскладки "05h = no-op" и "05h = алиас того же ядра"
     дают БИТ-В-БИТ одинаковый принятый поток;
  8. темпы: FLOOD ~74.1 КБ/с (42T + лендмарки), цикл ~1108 мс;
     p04: FLOOD ~97.2 КБ/с (32T + лендмарки), цикл ~845 мс.
Дамп принятого потока (2 цикла) пишется в /tmp/txs11_sim.bin как
доказательный фидер для самотеста uart_speed v1.2.
"""
import sys, re

BASE = '/home/z/my-project/CPLD-plus-8085/beta/txuart/rom/txstress'
T_NS = 320.0          # нс на такт
FRAME_T = 31.25       # кадр 8N1 при 1М бод, в тактах CPU
BAN = b"\r\nTXSTRESS v1.1\r\n"

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
    def __init__(self, mem, mode='noop'):
        self.mem = mem
        self.A = self.B = self.C = self.D = self.E = self.H = self.L = 0
        self.Z = 0; self.CY = 0; self.AC = 0
        self.pc = 0
        self.t = 0.0
        self.stream = bytearray()
        self.busy = -1.0        # ядро занято до (такты)
        self.mode = mode        # 'noop': OUT 05h игнор; 'alias': тот же корпус
        self.writes = 0         # записи в ядро (время каждой - в wtimes)
        self.wtimes = []

    def rd(self, a): return self.mem.get(a, 0xFF)

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

    def out(self, port, val):
        if port == 0x04 or (self.mode == 'alias' and port == 0x05):
            self.writes += 1
            self.wtimes.append(self.t)
            if self.t >= self.busy - 1e-9:      # ядро свободно -> кадр уходит
                self.stream.append(val)
                self.busy = self.t + FRAME_T

    def step(self):
        m = self.rd; pc = self.pc
        op = m(pc); size, tt = 1, 4
        if op == 0x00 or op == 0xF3 or op == 0xFB: tt = 4          # NOP/DI/EI
        elif op == 0x0F:                                           # RRC
            b0 = self.A & 1
            self.A = (self.A >> 1) | (b0 << 7); self.CY = b0; tt = 4
        elif op == 0x27:                                           # DAA
            # Intel 8085: коррекции ПОСЛЕДОВАТЕЛЬНЫЕ: сначала младший
            # ниббл, потом старший УЖЕ у скорректированного A
            if (self.A & 0x0F) > 9 or self.AC:
                self.A = (self.A + 0x06) & 0xFF
            if (self.A >> 4) > 9 or self.CY:
                self.A = (self.A + 0x60) & 0xFF
                self.CY = 1
            self.Z = 1 if self.A == 0 else 0; tt = 4
        elif 0x40 <= op <= 0x7F and op != 0x76:                    # MOV d,s
            d, s = (op >> 3) & 7, op & 7
            src = self.rd((self.H << 8) | self.L) if s == 6 else self._reg(s)
            self._setreg(d, src)
            tt = 7 if (d == 6 or s == 6) else 4
        elif 0x40 <= op <= 0x3E and False: pass                    # (заглушка)
        elif op < 0x40 and (op & 7) == 6:                          # MVI r,nn
            self._setreg((op >> 3) & 7, m(pc + 1)); size, tt = 2, 7
        elif op in (0x01, 0x11, 0x21, 0x31):                       # LXI rp,nnnn
            self._setrp((op >> 4) & 3, m(pc + 2), m(pc + 1)); size, tt = 3, 10
        elif op == 0xD3:                                           # OUT nn
            self.out(m(pc + 1), self.A); size, tt = 2, 10
        elif op == 0xDB:                                           # IN nn
            self.A = 0x00; size, tt = 2, 10
        elif op < 0x40 and (op & 7) == 4:                          # INR r
            v = (self._reg((op >> 3) & 7) + 1) & 0xFF
            self._setreg((op >> 3) & 7, v)
            self.Z = 1 if v == 0 else 0; tt = 4
        elif op < 0x40 and (op & 7) == 5:                          # DCR r
            v = (self._reg((op >> 3) & 7) - 1) & 0xFF
            self._setreg((op >> 3) & 7, v)
            self.Z = 1 if v == 0 else 0; tt = 4
        elif op in (0x03, 0x13, 0x23, 0x0B, 0x1B, 0x2B):           # INX/DCX rp
            hi, lo = self._rp((op >> 4) & 3)
            # INX rp = x3 (бит 3 = 0), DCX rp = xB (бит 3 = 1)
            d = 1 if (op & 0x08) == 0 else -1
            v = (((hi << 8) | lo) + d) & 0xFFFF
            self._setrp((op >> 4) & 3, (v >> 8) & 0xFF, v & 0xFF); tt = 6
        elif 0xB0 <= op <= 0xB7:                                   # ORA r
            src = self.rd((self.H << 8) | self.L) if (op & 7) == 6 else self._reg(op & 7)
            self.A |= src; self.CY = 0; self.AC = 0
            self.Z = 1 if self.A == 0 else 0; tt = 4
        elif op == 0xE6:                                           # ANI nn
            self.A &= m(pc + 1); self.CY = 0; self.AC = 0
            self.Z = 1 if self.A == 0 else 0; size, tt = 2, 7
        elif op == 0xC6:                                           # ADI nn
            v = m(pc + 1)
            r = self.A + v
            self.CY = 1 if r > 0xFF else 0
            self.AC = 1 if ((self.A & 0xF) + (v & 0xF)) > 0xF else 0
            self.A = r & 0xFF; self.Z = 1 if self.A == 0 else 0
            size, tt = 2, 7
        elif op == 0xCE:                                           # ACI nn
            v = m(pc + 1)
            r = self.A + v + self.CY
            self.CY = 1 if r > 0xFF else 0
            self.AC = 1 if ((self.A & 0xF) + (v & 0xF) + self.CY) > 0xF else 0
            self.A = r & 0xFF; self.Z = 1 if self.A == 0 else 0
            size, tt = 2, 7
        elif op == 0xFE:                                           # CPI nn
            v = m(pc + 1)
            r = (self.A - v) & 0xFF
            self.CY = 1 if self.A < v else 0
            self.Z = 1 if r == 0 else 0; size, tt = 2, 7
        elif op == 0xC3:                                           # JMP
            self.pc = m(pc + 1) | (m(pc + 2) << 8); self.t += 10; return
        elif op == 0xC2:                                           # JNZ
            size, tt = 3, 7
            if not self.Z:
                self.pc = m(pc + 1) | (m(pc + 2) << 8); self.t += 10; return
        elif op == 0xCA:                                           # JZ
            size, tt = 3, 7
            if self.Z:
                self.pc = m(pc + 1) | (m(pc + 2) << 8); self.t += 10; return
        else:
            raise SystemExit(f"неизвестный опкод {op:02X} @ {pc:04X}")
        self.t += tt
        self.pc = (pc + size) & 0xFFFF

    def _rp(self, r):
        return ((self.B, self.D, self.H)[r], (self.C, self.E, self.L)[r])

    def _setrp(self, r, hi, lo):
        if r == 0: self.B, self.C = hi, lo
        elif r == 1: self.D, self.E = hi, lo
        else: self.H, self.L = hi, lo

    def run(self, t_limit):
        while self.t < t_limit:
            self.step()
        return bytes(self.stream)

# ----------------------- аудит потока -----------------------
LM_RE = re.compile(rb"B=[0-9A-F]{4} TXSTRESS\r\n")
EXP_LM = [b'0020', b'0040', b'0060', b'0080', b'00A0', b'00C0', b'00E0']

def audit(name, s, ncyc, sprint_exact=True):
    ok = True
    def req(cond, msg):
        nonlocal ok
        print(('  OK   ' if cond else '  FAIL ') + msg)
        if not cond: ok = False
    # обрезать до ровно ncyc баннеров (окно может задевать следующий)
    pos = []
    i = s.find(BAN)
    while i >= 0:
        pos.append(i)
        i = s.find(BAN, i + 1)
    if len(pos) > ncyc:
        s = s[:pos[ncyc]]
    nb = s.count(BAN)
    req(nb == ncyc, f"баннеров {nb} == {ncyc}, поток {len(s)} Б")
    parts = s.split(BAN)
    if len(parts) != ncyc + 1:
        print('  FAIL нарезка по баннерам не сошлась'); return False
    for ci in range(1, ncyc + 1):
        cyc = parts[ci]
        if ci > 1:
            tail = parts[ci - 1].rsplit(b"BURST OK\r\n", 1)[1]
            req(tail == b"", f"цикл {ci}: хвост BURST OK->баннер пуст ({len(tail)} Б)")
        lms = LM_RE.findall(cyc)
        vals = [x[2:6] for x in lms]
        req(vals == EXP_LM, f"цикл {ci}: лендмарки {len(lms)} шт {[v.decode() for v in vals]}")
        flo = cyc.split(b"FLOOD OK\r\n", 1)
        req(len(flo) == 2, f"цикл {ci}: маркер FLOOD OK")
        data = LM_RE.sub(b"", flo[0])
        req(len(data) == 65536, f"цикл {ci}: FLOOD данных {len(data)} == 65536")
        brk = sum(1 for i in range(1, len(data)) if data[i] != ((data[i - 1] + 1) & 0xFF))
        req(brk == 0, f"цикл {ci}: +1 разрывов 0 (старт {data[0]:02X}h)")
        spr = flo[1].split(b"SPRINT OK\r\n", 1)
        req(len(spr) == 2, f"цикл {ci}: маркер SPRINT OK")
        if sprint_exact:
            req(spr[0] == b"U" * 8192, f"цикл {ci}: SPRINT ровно 8192 'U', чужих {len(spr[0]) - 8192}")
        else:
            req(spr[0].count(0x55) == len(spr[0]) and 8192 <= len(spr[0]) <= 16384,
                f"цикл {ci}: SPRINT только 'U' ({len(spr[0])} шт, алиас 05h: 8192..16384)")
        bur = spr[1].split(b"BURST OK\r\n", 1)
        req(len(bur) == 2, f"цикл {ci}: маркер BURST OK")
        ub = bur[0].count(0x55)
        req(ub in (2730, 2731, 2816) and bur[0].count(b"U") == ub,
            f"цикл {ci}: BURST {ub} 'U' (реальная сетка 14T+28T: 2816; приближение k=3: 2730..2731), чужих {len(bur[0]) - ub}")
    print(f"  == {name}: {'ПРОЙДЕН' if ok else 'ЕСТЬ ОШИБКИ'} ==")
    return ok

def main():
    ncyc = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    print("== Симуляция TXSTRESS v1.1 по реальному hex ==")
    all_ok = True
    POR_T = 1_572_900          # ~503 мс

    # ---- головной TX_BOTH=1: две раскладки порта 05h ----
    streams = {}
    for mode in ('noop', 'alias'):
        cpu = CPU(load_hex(f'{BASE}/txstress_v11.hex'), mode)
        streams[mode] = cpu.run(POR_T + ncyc * 3_600_000)
        print(f"  head mode={mode}: записей в ядро {cpu.writes}, принято {len(streams[mode])} Б")
    # сравнение режимов: баннер + FLOOD-регион + BURST-регион бит-в-бит;
    # SPRINT при алиасе легально принимает больше 'U' (05h тоже попадает в idle)
    a, b = streams['noop'], streams['alias']
    fa = a.find(b"FLOOD OK\r\n") + len(b"FLOOD OK\r\n")
    fb = b.find(b"FLOOD OK\r\n") + len(b"FLOOD OK\r\n")
    same_flood = a[:fa] == b[:fb]
    all_ok &= same_flood
    print(f"  {'OK  ' if same_flood else 'FAIL'} TX_BOTH=1: баннер+FLOOD бит-в-бит одинаковы ({fa} vs {fb} Б)")
    ok_a = audit('head noop (TX_BOTH=1)', a, ncyc, sprint_exact=True)
    ok_b = audit('head alias (TX_BOTH=1, 05h=второй вход ядра)', b, ncyc, sprint_exact=False)
    all_ok &= ok_a and ok_b

    # темпы head: FLOOD-регион = записи [17 .. 17+65655), цикл = 90274 записи
    cpu = CPU(load_hex(f'{BASE}/txstress_v11.hex'), 'noop')
    cpu.run(POR_T + 2 * 3_600_000)
    wt = cpu.wtimes
    dt = wt[17 + 65655] - wt[17]
    rate = 65655 / (dt * T_NS * 1e-9)
    print(f"  head FLOOD факт (42T+лендмарки): {rate:,.0f} Б/с (ожидание ~73 950)")
    all_ok &= abs(rate - 73950) < 300
    if cpu.writes >= 2 * 90274:
        cyc_t = (wt[90274] - wt[0]) * T_NS / 1e6
        print(f"  head период цикла: {cyc_t:.1f} мс (ожидание ~1091)")
        all_ok &= 1050 < cyc_t < 1110

    # ---- p04: TX_BOTH=0 ----
    cpu = CPU(load_hex(f'{BASE}/txstress_v11_p04.hex'), 'noop')
    s4 = cpu.run(POR_T + ncyc * 2_800_000)
    all_ok &= audit('p04 (TX_BOTH=0)', s4, ncyc)
    cpu = CPU(load_hex(f'{BASE}/txstress_v11_p04.hex'), 'noop')
    cpu.run(POR_T + 2 * 2_800_000)
    wt = cpu.wtimes
    dt = wt[17 + 65655] - wt[17]
    rate4 = 65655 / (dt * T_NS * 1e-9)
    print(f"  p04 FLOOD факт (32T+лендмарки): {rate4:,.0f} Б/с (ожидание ~96 900)")
    all_ok &= abs(rate4 - 96900) < 300
    if cpu.writes >= 2 * 90274:
        cyc4 = (wt[90274] - wt[0]) * T_NS / 1e6
        print(f"  p04 период цикла: {cyc4:.1f} мс (ожидание ~829)")
        all_ok &= 800 < cyc4 < 860

    print("== ВСЁ ОК ==" if all_ok else "== ЕСТЬ ОШИБКИ ==")
    # дамп ровно 2 полных циклов - доказательный фидер для самотеста
    # uart_speed v1.2 (срез по 3-му баннеру: без шва при зацикливании)
    s = streams['noop']
    pos = []
    i = s.find(BAN)
    while i >= 0 and len(pos) < 3:
        pos.append(i)
        i = s.find(BAN, i + 1)
    cut = pos[2] if len(pos) >= 3 else len(s)
    open('/tmp/txs11_sim.bin', 'wb').write(s[:cut])
    print(f"дамп: /tmp/txs11_sim.bin {cut} Б (2 полных цикла head)")
    sys.exit(0 if all_ok else 1)

if __name__ == '__main__':
    main()
