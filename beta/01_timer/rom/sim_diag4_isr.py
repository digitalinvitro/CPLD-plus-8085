#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_diag4_isr.py -- instruction-level доказательство фикса diag4.

Полная эмуляция подмножества 8085, используемого прошивками
uart_echo_diag3 (баг) и uart_echo_diag4 (фикс): MAIN + ISR + DMUX/HSEG
целиком. Сценарий: RESET -> баннер '>' -> ловля ОДНОГО кадра 'a' (61h)
на сетке 2400 (12 выборок: s, d0..d7, хвост 111) -> эхо тройкой
[байт][tl-hi][tl-lo] -> опрос дисплея.

Проверки:
  diag3 (баг):   BYTE0=00, TSB=0000, эхо = три кадра 00h, на дисплее
                 байт 00 -- ТОЧНО наблюдение владельца (10-24).
  diag4 (фикс):  BYTE0=61, TSB=0437, эхо-кадры [61][04][37] со стартом/
                 стопом/холостым на местах, дисплей [B=1][SSELF=0][61].

Модель SIM: SDE = A6, SOD-data = A7 (раскладка подтверждена железом:
баннер timer_test_uart v4 PASS). RIM возвращает SID в A7 (код везде
читает его через ANI 80h). Таймер моделируется драйвером: ISR
вызывается вручную по одному разу на битовый интервал (ре-арм OUT 04h
в векторе -- no-op).

Запуск:  python3 sim_diag4_isr.py
"""
import sys

ROMDIR = '/home/z/my-project/CPLD-plus-8085/beta/01_timer/rom'


def load_hex(path):
    mem = bytearray(0x10000)
    top = 0
    for line in open(path):
        line = line.strip()
        if not line.startswith(':'):
            continue
        b = bytes.fromhex(line[1:])
        if b[3] == 0:
            addr = (b[1] << 8) | b[2]
            for i in range(b[0]):
                mem[addr + i] = b[4 + i]
            top = max(top, addr + b[0])
        elif b[3] == 1:
            break
    return mem, top


class Halt(Exception):
    pass


class Core:
    """8085-ядро: ровно те команды, что встречаются в прошивках."""

    def __init__(self, mem, sid_fn):
        self.mem = mem
        self.sid_fn = sid_fn
        self.a = self.b = self.c = self.d = self.e = self.h = self.l = 0
        self.sp = 0
        self.pc = 0
        self.s = self.z = self.ac = self.p = self.cy = 0
        self.ie = 0
        self.sod = 1                    # уровень SOD (пишется SIM)
        self.events = []                # ('seg'|'dig', значение)
        self.steps = 0

    # ---------- память ----------
    def rd(self, a):
        return self.mem[a & 0xFFFF]

    def wr(self, a, v):
        self.mem[a & 0xFFFF] = v & 0xFF

    # ---------- флаги ----------
    def szp(self, v):
        v &= 0xFF
        self.s = (v >> 7) & 1
        self.z = 1 if v == 0 else 0
        self.p = 0 if (bin(v).count('1') & 1) else 1

    def push(self, hi, lo):
        self.wr(self.sp - 1, hi)
        self.wr(self.sp - 2, lo)
        self.sp = (self.sp - 2) & 0xFFFF

    def pop(self):
        lo = self.rd(self.sp)
        hi = self.rd(self.sp + 1)
        self.sp = (self.sp + 2) & 0xFFFF
        return hi, lo

    def fetch(self):
        v = self.rd(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def fetch16(self):
        lo = self.fetch()
        hi = self.fetch()
        return (hi << 8) | lo

    # ---------- регистры по номеру ----------
    def rget(self, r):
        return (self.b, self.c, self.d, self.e, self.h, self.l,
                None, self.a)[r]

    def rset(self, r, v):
        v &= 0xFF
        if r == 0:
            self.b = v
        elif r == 1:
            self.c = v
        elif r == 2:
            self.d = v
        elif r == 3:
            self.e = v
        elif r == 4:
            self.h = v
        elif r == 5:
            self.l = v
        elif r == 7:
            self.a = v
        else:
            raise RuntimeError('rset M')

    def maddr(self):
        return (self.h << 8) | self.l

    # ---------- шаг ----------
    def step(self):
        self.steps += 1
        op = self.fetch()

        if 0x40 <= op <= 0x7F:                      # MOV r,r / HLT
            if op == 0x76:
                raise Halt('HLT')
            dst, src = (op >> 3) & 7, op & 7        # 01 DDD SSS
            v = self.rd(self.maddr()) if src == 6 else self.rget(src)
            if dst == 6:
                self.wr(self.maddr(), v)
            else:
                self.rset(dst, v)
            return op

        if 0x80 <= op <= 0xBF:                      # ADD/ADC/SUB/SBB/
            r = op & 7                              # ANA/XRA/ORA/CMP r
            v = self.rd(self.maddr()) if r == 6 else self.rget(r)
            g = (op >> 3) & 7
            if g == 0:
                f = self.a + v
                self.cy = (f >> 8) & 1
                self.ac = 1 if ((self.a & 0xF) + (v & 0xF)) > 0xF else 0
                self.a = f & 0xFF
                self.szp(self.a)
            elif g == 1:
                f = self.a + v + self.cy
                self.cy = (f >> 8) & 1
                self.a = f & 0xFF
                self.szp(self.a)
            elif g == 2:
                f = self.a - v
                self.cy = 1 if f < 0 else 0
                self.a = f & 0xFF
                self.szp(self.a)
            elif g == 3:
                f = self.a - v - self.cy
                self.cy = 1 if f < 0 else 0
                self.a = f & 0xFF
                self.szp(self.a)
            elif g == 4:
                self.a &= v
                self.cy = 0
                self.szp(self.a)
            elif g == 5:
                self.a ^= v
                self.cy = 0
                self.ac = 0
                self.szp(self.a)
            elif g == 6:
                self.a |= v
                self.cy = 0
                self.ac = 0
                self.szp(self.a)
            else:
                f = self.a - v
                self.cy = 1 if f < 0 else 0
                self.szp(f)
            return op

        if op == 0x00:                              # NOP
            return op
        if op in (0x01, 0x11, 0x21, 0x31):          # LXI
            v = self.fetch16()
            if op == 0x01:
                self.b, self.c = v >> 8, v & 0xFF
            elif op == 0x11:
                self.d, self.e = v >> 8, v & 0xFF
            elif op == 0x21:
                self.h, self.l = v >> 8, v & 0xFF
            else:
                self.sp = v
            return op
        if op in (0x06, 0x0E, 0x16, 0x1E, 0x26, 0x2E, 0x36, 0x3E):  # MVI
            v = self.fetch()
            r = (op >> 3) & 7
            if r == 6:
                self.wr(self.maddr(), v)
            else:
                self.rset(r, v)
            return op
        if op in (0x04, 0x0C, 0x14, 0x1C, 0x24, 0x2C, 0x34, 0x3C):  # INR
            r = (op >> 3) & 7
            v = (self.rd(self.maddr()) if r == 6 else self.rget(r))
            v = (v + 1) & 0xFF
            self.ac = 1 if (v & 0x0F) == 0 else 0
            self.szp(v)
            if r == 6:
                self.wr(self.maddr(), v)
            else:
                self.rset(r, v)
            return op
        if op in (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D):  # DCR
            r = (op >> 3) & 7
            v = (self.rd(self.maddr()) if r == 6 else self.rget(r))
            v = (v - 1) & 0xFF
            self.ac = 1 if (v & 0x0F) == 0x0F else 0
            self.szp(v)                             # CY НЕ трогается
            if r == 6:
                self.wr(self.maddr(), v)
            else:
                self.rset(r, v)
            return op
        if op == 0x07:                              # RLC
            self.cy = (self.a >> 7) & 1
            self.a = ((self.a << 1) | self.cy) & 0xFF
            return op
        if op == 0x0F:                              # RRC
            self.cy = self.a & 1
            self.a = (self.a >> 1) | (self.cy << 7)
            return op
        if op == 0x17:                              # RAL
            c = self.cy
            self.cy = (self.a >> 7) & 1
            self.a = ((self.a << 1) | c) & 0xFF
            return op
        if op == 0x1F:                              # RAR
            c = self.cy
            self.cy = self.a & 1
            self.a = (self.a >> 1) | (c << 7)
            return op
        if op == 0x22:                              # SHLD a16
            a = self.fetch16()
            self.wr(a, self.l)
            self.wr(a + 1, self.h)
            return op
        if op == 0x2A:                              # LHLD a16
            a = self.fetch16()
            self.l = self.rd(a)
            self.h = self.rd(a + 1)
            return op
        if op == 0x32:                              # STA a16
            self.wr(self.fetch16(), self.a)
            return op
        if op == 0x3A:                              # LDA a16
            self.a = self.rd(self.fetch16())
            return op
        if op == 0x37:                              # STC
            self.cy = 1
            return op
        if op == 0x3F:                              # CMC
            self.cy ^= 1
            return op
        if op in (0xC5, 0xD5, 0xE5, 0xF5):          # PUSH B/D/H/PSW
            if op == 0xC5:
                self.push(self.b, self.c)
            elif op == 0xD5:
                self.push(self.d, self.e)
            elif op == 0xE5:
                self.push(self.h, self.l)
            else:
                psw = (self.s << 7) | (self.z << 6) | (self.ac << 4) | \
                      (self.p << 2) | 0x02 | self.cy
                self.push(psw, self.a)
            return op
        if op in (0xC1, 0xD1, 0xE1, 0xF1):          # POP B/D/H/PSW
            hi, lo = self.pop()
            if op == 0xC1:
                self.b, self.c = hi, lo
            elif op == 0xD1:
                self.d, self.e = hi, lo
            elif op == 0xE1:
                self.h, self.l = hi, lo
            else:
                self.a = lo
                self.s = (hi >> 7) & 1
                self.z = (hi >> 6) & 1
                self.ac = (hi >> 4) & 1
                self.p = (hi >> 2) & 1
                self.cy = hi & 1
            return op
        if op in (0xC3, 0xC2, 0xCA, 0xD2, 0xDA, 0xF2, 0xFA):  # JMP/Jcc
            a = self.fetch16()
            take = True
            if op == 0xC2:
                take = self.z == 0
            elif op == 0xCA:
                take = self.z == 1
            elif op == 0xDA:
                take = self.cy == 1
            elif op == 0xD2:
                take = self.cy == 0
            elif op == 0xFA:
                take = self.s == 1
            elif op == 0xF2:
                take = self.s == 0
            if take:
                self.pc = a
            return op
        if op == 0xCD:                              # CALL a16
            a = self.fetch16()
            self.push((self.pc >> 8) & 0xFF, self.pc & 0xFF)
            self.pc = a
            return op
        if op in (0xC9, 0xC0, 0xC8, 0xD0, 0xD8, 0xF0, 0xF8):  # RET/Rcc
            take = True
            if op == 0xC0:
                take = self.z == 0
            elif op == 0xC8:
                take = self.z == 1
            if take:
                hi, lo = self.pop()
                self.pc = (hi << 8) | lo
            return op
        if op == 0xD3:                              # OUT n
            port = self.fetch()
            if port == 0x00:
                self.events.append(('seg', self.a))
            elif port == 0x01:
                self.events.append(('dig', self.a))
            # порт 04h (ре-арм таймера) моделируется драйвером
            return op
        if op == 0xDB:                              # IN n
            self.fetch()
            self.a = 0
            return op
        if op in (0xE6, 0xF6, 0xEE, 0xCE, 0xC6, 0xD6, 0xDE, 0xFE):  # imm8
            v = self.fetch()
            g = {0xE6: 'ANI', 0xF6: 'ORI', 0xEE: 'XRI', 0xCE: 'ACI',
                 0xC6: 'ADI', 0xD6: 'SUI', 0xDE: 'SBI', 0xFE: 'CPI'}[op]
            if g == 'ANI':
                self.a &= v
                self.cy = 0
                self.szp(self.a)
            elif g == 'ORI':
                self.a |= v
                self.cy = 0
                self.ac = 0
                self.szp(self.a)
            elif g == 'XRI':
                self.a ^= v
                self.cy = 0
                self.ac = 0
                self.szp(self.a)
            elif g == 'ADI':
                f = self.a + v
                self.cy = (f >> 8) & 1
                self.a = f & 0xFF
                self.szp(self.a)
            elif g == 'ACI':
                f = self.a + v + self.cy
                self.cy = (f >> 8) & 1
                self.a = f & 0xFF
                self.szp(self.a)
            elif g == 'SUI':
                f = self.a - v
                self.cy = 1 if f < 0 else 0
                self.a = f & 0xFF
                self.szp(self.a)
            elif g == 'SBI':
                f = self.a - v - self.cy
                self.cy = 1 if f < 0 else 0
                self.a = f & 0xFF
                self.szp(self.a)
            else:  # CPI
                f = self.a - v
                self.cy = 1 if f < 0 else 0
                self.szp(f)
            return op
        if op == 0xAF:                              # XRA A
            self.a = 0
            self.cy = 0
            self.ac = 0
            self.szp(self.a)
            return op
        if op == 0xF3:                              # DI
            self.ie = 0
            return op
        if op == 0xFB:                              # EI
            self.ie = 1
            return op
        if op == 0x30:                              # SIM
            if self.a & 0x40:                       # SDE=A6 (по железу!)
                self.sod = (self.a >> 7) & 1
            return op
        if op == 0x20:                              # RIM
            self.a = (self.sid_fn() << 7) & 0x80
            return op
        raise RuntimeError(
            f'опкод {op:02X} по адресу {self.pc - 1:04X} не поддержан')

    def isr(self):
        """Вход RST 7.5: вектор 003Ch, выход по RET."""
        self.push((self.pc >> 8) & 0xFF, self.pc & 0xFF)
        self.pc = 0x003C
        for _ in range(100000):
            op = self.step()
            if op == 0xC9:
                return
        raise RuntimeError('ISR не вернулся')


def bits_lsb(b):
    return [(b >> i) & 1 for i in range(8)]


def parse_frames(sod):
    """Разбор волновой формы SOD на UART-кадры 8N1 (старт=0, стоп=1)."""
    out, i = [], 0
    while i < len(sod):
        while i < len(sod) and sod[i] == 1:
            i += 1
        if i >= len(sod):
            break
        assert sod[i] == 0, f'старт-бит ожидается 0, такт {i}'
        i += 1
        v = 0
        for k in range(8):
            v |= sod[i] << k
            i += 1
        assert sod[i] == 1, f'стоп-бит ожидается 1, такт {i}'
        i += 1
        out.append(v)
    return out


def run(romfile, label, byte=0x61):
    mem, top = load_hex(f'{ROMDIR}/{romfile}')
    sid = {'v': 1}
    core = Core(mem, lambda: sid['v'])
    CAP = 500000

    # фаза 1: INIT до BAN
    while core.pc != 0x012A:
        core.step()
        assert core.steps < CAP, 'MAIN не дошёл до BAN'
    banner = []
    while core.c != 0xFF:
        core.isr()
        banner.append(core.sod)
        assert len(banner) < 20, 'баннер не кончился'
    assert banner == [0] + bits_lsb(0x3E) + [1], \
        f'{label}: баннер {banner}'

    # фаза 2: POLL, на линии старт-бит
    while core.pc != 0x0130:
        core.step()
        assert core.steps < CAP, 'MAIN не дошёл до POLL'
    sid['v'] = 0

    # фаза 3: 12 выборок кадра (s, d0..d7, хвост 111)
    frame = [0] + bits_lsb(byte) + [1, 1, 1]
    i = 0
    while i < 12:
        if 0x015E <= core.pc <= 0x0162:
            sid['v'] = frame[i]
            core.isr()
            i += 1
        else:
            core.step()
        assert core.steps < CAP, 'кадр приёма не закончился'

    # фаза 4: эхо -- тики TX до C=0FFh
    echo = []
    while core.pc != 0x0130:
        if 0x0163 <= core.pc <= 0x0168 and core.c != 0xFF:
            sid['v'] = 1
            core.isr()
            echo.append(core.sod)
        else:
            core.step()
        assert core.steps < CAP, 'эхо не кончилось'

    # фаза 5: дисплей (POLL крутится, SID=1)
    sid['v'] = 1
    while sum(1 for e in core.events if e[0] == 'dig') < 8:
        core.step()
        assert core.steps < CAP, 'дисплей не крутится'
    pairs, last_seg = [], None
    for kind, v in core.events:
        if kind == 'seg':
            last_seg = v
        elif kind == 'dig' and last_seg is not None:
            pairs.append((v, last_seg))
            last_seg = None
    # нормализация: цикл мультиплексии может начинаться с любого разряда
    for j, p in enumerate(pairs):
        if p[0] == 1:
            pairs = pairs[j:] + pairs[:j]
            break

    res = {
        'label': label,
        'byte': byte,
        'bytes': top,
        'BYTE0': mem[0x8001],
        'TSB': (mem[0x8002], mem[0x8003]),
        'SSELF': mem[0x8006],
        'QCNT': mem[0x8007],
        'B': core.b,
        'echo': echo,
        'frames': parse_frames(echo),
        'pairs': pairs,
    }
    return res


def expect_sod(data_bytes):
    """Волновая форма очереди эха: кадр 1 без холостого, далее [холостой
    бит, старт, 8 данных, стоп] на каждый следующий байт очереди."""
    out = [0] + bits_lsb(data_bytes[0]) + [1]
    for b in data_bytes[1:]:
        out += [1, 0] + bits_lsb(b) + [1]
    return out


SEGTAB = [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07,
          0x7F, 0x6F, 0x77, 0x7C, 0x39, 0x5E, 0x79, 0x71]


def expected_triple(b):
    """Документированный ответ [байт][tl-hi][tl-lo] для байта b:
    tl-hi = 0000 s d0 d1 d2 (s=0), tl-lo = d3..d7 t1 t2 t3 (t=111)."""
    d = bits_lsb(b)
    tl_hi = (d[0] << 2) | (d[1] << 1) | d[2]
    tl_lo = (d[3] << 7) | (d[4] << 6) | (d[5] << 5) | (d[6] << 4) | \
            (d[7] << 3) | 0b111
    return [b, tl_hi, tl_lo]


def expected_pairs(b):
    """Цикл дисплея [DIG0=B][DIG1=SSELF][DIG2=байт.мл][DIG3=байт.ст]."""
    return [(1, SEGTAB[1]), (2, SEGTAB[0]), (4, SEGTAB[b & 0xF]),
            (8, SEGTAB[(b >> 4) & 0xF])]


def main():
    ok = True

    # ---- diag3: воспроизведение бага (наблюдение владельца 10-24) ----
    r3 = run('uart_echo_diag3.hex', "diag3 'a' (баг)", 0x61)
    exp3 = expect_sod([0x00, 0x00, 0x00])
    checks3 = [
        ('BYTE0 = 00h (байт всегда ноль)', r3['BYTE0'] == 0x00),
        ('TSB = 0000h (таймлайн пуст)', r3['TSB'] == (0, 0)),
        ('эхо = три кадра 00h', r3['frames'] == [0x00, 0x00, 0x00]),
        ('волновая форма эха', r3['echo'] == exp3),
        ('B = 1 (старт пойман, счётчик жив)', r3['B'] == 1),
        ('SSELF = 0', r3['SSELF'] == 0),
        ('дисплей: байт 00', r3['pairs'][:4] == expected_pairs(0)),
    ]
    print(f"=== {r3['label']}: {r3['bytes']} байт ===")
    print(f"  BYTE0={r3['BYTE0']:02X}h  TSB={r3['TSB'][0]:02X}{r3['TSB'][1]:02X}h"
          f"  B={r3['B']}  SSELF={r3['SSELF']}  QCNT={r3['QCNT']}")
    print(f"  эхо-байты: {' '.join(f'{v:02X}' for v in r3['frames'])}")
    for name, res in checks3:
        if not res:
            ok = False
        print(f"  [{'PASS' if res else 'ПРОВАЛ'}] {name}")
    print()

    # ---- diag4: документированная таблица ожиданий (README, diag v3) ----
    for name, b in (("'a'", 0x61), ("'o'", 0x6F), ("'3'", 0x33),
                    ("Enter", 0x0D)):
        r4 = run('uart_echo_diag4.hex', f'diag4 {name}', b)
        exp = expected_triple(b)
        exp_sod = expect_sod(exp)
        checks = [
            (f'BYTE0 = {b:02X}h', r4['BYTE0'] == b),
            (f'TSB = {exp[1]:02X}{exp[2]:02X}h',
             r4['TSB'] == (exp[1], exp[2])),
            ("эхо-кадры " + ' '.join(f'{v:02X}' for v in exp),
             r4['frames'] == exp),
            ('волновая форма эха (старт/стоп/холостой)',
             r4['echo'] == exp_sod),
            ('очередь опустошена (QCNT=0)', r4['QCNT'] == 0),
            ('B = 1', r4['B'] == 1),
            ('SSELF = 0 (самозахвата нет)', r4['SSELF'] == 0),
            ('дисплей [B=1][S=0][байт]',
             r4['pairs'][:4] == expected_pairs(b)),
        ]
        print(f"=== {r4['label']}: {r4['bytes']} байт ===")
        print(f"  BYTE0={r4['BYTE0']:02X}h  TSB={r4['TSB'][0]:02X}{r4['TSB'][1]:02X}h"
              f"  B={r4['B']}  SSELF={r4['SSELF']}  QCNT={r4['QCNT']}")
        print(f"  эхо-байты: {' '.join(f'{v:02X}' for v in r4['frames'])}")
        for cname, res in checks:
            if not res:
                ok = False
            print(f"  [{'PASS' if res else 'ПРОВАЛ'}] {cname}")
        print()

    if not ok:
        print('ИТОГ: ПРОВАЛ')
        sys.exit(1)
    print('ИТОГ: ПАСС -- diag3 воспроизводит наблюдение владельца')
    print('(00 00 00 на любой ввод), diag4 даёт документированные тройки')
    print("('a' -> 61 04 37, 'o' -> 6F 07 B7, '3' -> 33 06 67,")
    print('Enter -> 0D 05 87) при НЕизменённом протоколе и TX-части.')


if __name__ == '__main__':
    main()
