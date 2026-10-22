#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asm85.py — мини-ассемблер Intel 8085 для тест-прошивок retro_PCLD_board.

Кодировка: UTF-8 (это инструмент сборки, а не исходник HDL — правило CP1251
на него не распространяется). Исходник .asm читается как CP1251 (с фолбэком
на UTF-8), листинг пишется в CP1251 — как принято в проекте.

Возможности:
  - двухпроходная сборка, метки, выражения (+ - * / и скобки);
  - числа: 1234h / 0x1234 / 123 / 0110b (двоичное) / 'A' (символ) / $ (текущий адрес);
  - директивы: ORG, EQU, DB, DW, IF expr / ELSE / ENDIF, END;
  - условная сборка под варианты прошивки: -D TONE=0;
  - вывод Intel HEX (16 байт в записи, тип 00 + EOF 01) и листинга;
  - режим --disasm: дизассемблирование готового .hex для проверки.

Использование:
  python3 asm85.py src.asm -o out.hex [-l out.lst] [-D NAME=VAL ...]
  python3 asm85.py --disasm out.hex

Система команд: полная таблица 8085 (MOV/MVI/LXI/LDA/STA/LHLD/SHLD/STAX/LDAX/
арифметика с регистром и немедленным операндом/переходы/вызовы/PUSH/POP/INR/DCR/
INX/DCX/DAD/RST/SIM/RIM/EI/DI/HLT и прочие одномашинные).
"""
import argparse
import re
import sys

# ---------------------------------------------------------------- таблицы

REGR = {'B': 0, 'C': 1, 'D': 2, 'E': 3, 'H': 4, 'L': 5, 'M': 6, 'A': 7}
RP = {'B': 0, 'D': 1, 'H': 2, 'PSW': 3, 'SP': 3}   # PUSH/POP: PSW; LXI/INX/DCX/DAD: SP
RP_NO_PSW = {'B': 0, 'D': 1, 'H': 2, 'SP': 3}

# одномашинные (без операндов)
IMPL1 = {
    'NOP': 0x00, 'HLT': 0x76, 'EI': 0xFB, 'DI': 0xF3,
    'SIM': 0x30, 'RIM': 0x20,
    'CMA': 0x2F, 'STC': 0x37, 'CMC': 0x3F, 'DAA': 0x27,
    'RLC': 0x07, 'RRC': 0x0F, 'RAL': 0x17, 'RAR': 0x1F,
    'XCHG': 0xEB, 'XTHL': 0xE3, 'PCHL': 0xE9, 'SPHL': 0xF9,
    'RET': 0xC9, 'RC': 0xD8, 'RNC': 0xD0, 'RZ': 0xC8, 'RNZ': 0xC0,
    'RM': 0xF8, 'RP': 0xF0, 'RPE': 0xE8, 'RPO': 0xE0,
}
# группа "мнемоника регистр": ADD/ADC/SUB/SBB/ANA/XRA/ORA/CMP
GRP_R = {
    'ADD': 0x80, 'ADC': 0x88, 'SUB': 0x90, 'SBB': 0x98,
    'ANA': 0xA0, 'XRA': 0xA8, 'ORA': 0xB0, 'CMP': 0xB8,
}
# группа "мнемоника imm8"
GRP_I8 = {
    'OUT': 0xD3, 'IN': 0xDB,
    'ADI': 0xC6, 'ACI': 0xCE, 'SUI': 0xD6, 'SBI': 0xDE,
    'ANI': 0xE6, 'XRI': 0xEE, 'ORI': 0xF6, 'CPI': 0xFE,
}
# группа "мнемоника addr16"
GRP_A16 = {
    'JMP': 0xC3, 'JNZ': 0xC2, 'JZ': 0xCA, 'JNC': 0xD2, 'JC': 0xDA,
    'JPO': 0xE2, 'JPE': 0xEA, 'JP': 0xF2, 'JM': 0xFA,
    'CALL': 0xCD, 'CNZ': 0xC4, 'CZ': 0xCC, 'CNC': 0xD4, 'CC': 0xDC,
    'CPO': 0xE4, 'CPE': 0xEC, 'CP': 0xF4, 'CM': 0xFC,
    'LDA': 0x3A, 'STA': 0x32, 'LHLD': 0x2A, 'SHLD': 0x22,
}
GRP_RP = {'INX': 0x03, 'DCX': 0x0B, 'DAD': 0x09}   # + rp<<4
GRP_STX = {'STAX': 0x02, 'LDAX': 0x0A}             # только B(0)/D(1)

LABEL_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$')
HEX_RE = re.compile(r'\b([0-9][0-9A-Fa-f]*)[hH]\b')
BIN_RE = re.compile(r'\b([01]+)[bB]\b')
DEC_RE = re.compile(r'\b([0-9]+)[dD]\b')


class AsmError(Exception):
    pass


def expr_eval(text, syms, loc):
    """Вычислить выражение: числа h/0x/dec/bin/'c'/$, символы, + - * / ()."""
    if text is None or str(text).strip() == '':
        raise AsmError('пустое выражение')
    s = str(text).strip()
    if HEX_RE.search(s):
        s = HEX_RE.sub(lambda m: '0x' + m.group(1), s)
    if DEC_RE.search(s):
        s = DEC_RE.sub(lambda m: m.group(1), s)
    if BIN_RE.search(s):
        s = BIN_RE.sub(lambda m: '0b' + m.group(1), s)
    s = s.replace('$', ' LOC ')
    s = re.sub(r"'(.)'", lambda m: str(ord(m.group(1))), s)
    ns = dict(syms)
    ns['LOC'] = loc
    ns['__builtins__'] = {}
    try:
        val = eval(s, ns, ns)  # noqa: S307 — контролируемый ввод ассемблера
    except Exception as e:
        raise AsmError('не вычисляется выражение %r: %s' % (text, e))
    if not isinstance(val, int):
        raise AsmError('выражение %r — не целое' % text)
    return val & 0xFFFFFFFF


class Line:
    __slots__ = ('no', 'text', 'label', 'mnem', 'ops', 'addr', 'bytes')

    def __init__(self, no, text):
        self.no = no
        self.text = text
        self.label = None
        self.mnem = ''
        self.ops = []
        self.addr = None
        self.bytes = b''


def read_source(path):
    raw = open(path, 'rb').read()
    try:
        text = raw.decode('cp1251')
        enc = 'cp1251'
    except UnicodeDecodeError:
        text = raw.decode('utf-8')
        enc = 'utf-8 (фолбэк!)'
    return text, enc


def parse_lines(text):
    lines = []
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.split(';', 1)[0]           # комментарий — от ';' (CP1251-текст только тут)
        bad = [ch for ch in line if ord(ch) > 127]
        if bad:
            raise AsmError('строка %d: не-ASCII вне комментария: %r' % (no, bad[:3]))
        ln = Line(no, raw.rstrip())
        rest = line
        m = LABEL_RE.match(rest)
        if m:
            ln.label = m.group(1).upper()
            rest = m.group(2)
        rest = rest.strip()
        if rest:
            parts = rest.split(None, 1)
            head = parts[0].upper()
            tail = parts[1] if len(parts) > 1 else ''
            tail_head = tail.split(None, 1)[0].upper() if tail.split(None, 1) else ''
            if head == 'EQU' or tail_head == 'EQU':
                # поддерживаются две формы: "ИМЯ EQU выражение" и "ИМЯ: EQU выражение"
                if head == 'EQU':
                    if ln.label is None:
                        raise AsmError('строка %d: EQU требует имени (ИМЯ EQU выражение)' % no)
                    expr = tail.strip()
                else:
                    if ln.label is not None:
                        raise AsmError('строка %d: лишняя метка перед ИМЯ EQU' % no)
                    ln.label = head
                    t2 = tail.split(None, 1)
                    expr = t2[1].strip() if len(t2) > 1 else ''
                ln.mnem = 'EQU'
                ln.ops = [expr] if expr else []
            else:
                ln.mnem = head
                if tail:
                    ln.ops = [p.strip() for p in tail.split(',') if p.strip()]
        lines.append(ln)
    return lines


def opcode_class(mnem, ops, lineno):
    """(класс, размер). Классы: org/equ/if/else/endif/end/db/dw + коды."""
    if mnem in ('', 'NONE'):
        return 'none', 0
    if mnem in ('ORG', 'EQU', 'IF', 'ELSE', 'ENDIF', 'END'):
        return mnem.lower(), 0
    if mnem == 'DB':
        return 'db', len(ops)
    if mnem == 'DW':
        return 'dw', 2 * len(ops)
    if mnem in IMPL1:
        return 'impl', 1
    if mnem in GRP_R:
        return 'rr', 1
    if mnem == 'MOV':
        return 'mov', 1
    if mnem == 'MVI':
        return 'mvi', 2
    if mnem in ('INR', 'DCR'):
        return 'inr', 1
    if mnem in GRP_RP:
        return 'rp', 1
    if mnem in ('PUSH', 'POP'):
        return 'push', 1
    if mnem == 'LXI':
        return 'lxi', 3
    if mnem in GRP_STX:
        return 'stax', 1
    if mnem in GRP_I8:
        return 'i8', 2
    if mnem in GRP_A16:
        return 'a16', 3
    if mnem == 'RST':
        return 'rst', 1
    raise AsmError('строка %d: неизвестная мнемоника %r' % (lineno, mnem))


def check_reg(tok, lineno):
    r = str(tok).strip().upper()
    if r not in REGR:
        raise AsmError('строка %d: ожидался регистр, получено %r' % (lineno, tok))
    return REGR[r]


def check_rp(tok, lineno, table):
    r = str(tok).strip().upper()
    if r not in table:
        raise AsmError('строка %d: ожидалась пара (%s), получено %r'
                       % (lineno, '/'.join(table), tok))
    return table[r]


def range_check(val, hi, what, lineno):
    if not (0 <= val <= hi):
        raise AsmError('строка %d: %s вне диапазона 0..%Xh' % (lineno, what, hi))
    return val


def assemble(path, defines):
    text, enc = read_source(path)
    lines = parse_lines(text)

    syms = {k.upper(): v for k, v in defines.items()}
    dnames = set(syms.keys())
    overrides = []
    loc = 0
    ifstack = []   # [branch_active, cond, seen_else, parent_active]
    deferred = []  # отложенные EQU (ссылки на адресные метки/поздние константы)

    # ---------------------------------------------------------- проход 1
    for ln in lines:
        try:
            cls, size = opcode_class(ln.mnem, ln.ops, ln.no)
        except AsmError:
            if not all(f[0] for f in ifstack):
                continue          # в выключенной ветке допустим любой текст
            raise
        active = all(f[0] for f in ifstack)

        if cls in ('if', 'else', 'endif', 'none'):
            if cls == 'if':
                cond = expr_eval(ln.ops[0] if ln.ops else '0', syms, loc) != 0
                ifstack.append([active and cond, cond, False, active])
            elif cls == 'else':
                if not ifstack:
                    raise AsmError('строка %d: ELSE без IF' % ln.no)
                f = ifstack[-1]
                if f[2]:
                    raise AsmError('строка %d: второй ELSE' % ln.no)
                f[0] = f[3] and (not f[1])
                f[2] = True
            elif cls == 'endif':
                if not ifstack:
                    raise AsmError('строка %d: ENDIF без IF' % ln.no)
                ifstack.pop()
            continue
        if not active:
            continue

        if cls == 'equ':
            if not ln.label:
                raise AsmError('строка %d: EQU требует формы  ИМЯ EQU выражение' % ln.no)
            name, expr = ln.label, ','.join(ln.ops)
            ln.label = None
            try:
                val = expr_eval(expr, syms, loc)
            except AsmError:
                # константа с ссылкой на метки/поздние имена — резолвим после прохода
                if name in syms and name not in dnames:
                    raise AsmError('строка %d: символ %r уже определён' % (ln.no, name))
                syms.setdefault(name, None)
                deferred.append((name, expr, ln.no))
                continue
            if name in syms:
                if name in dnames and syms[name] != val:
                    overrides.append((name, syms[name], val))
                elif syms[name] != val:
                    raise AsmError('строка %d: символ %r уже определён'
                                   % (ln.no, name))
            else:
                syms[name] = val
            continue
        elif cls == 'org':
            newloc = expr_eval(ln.ops[0], syms, loc)
            if newloc < loc:
                raise AsmError('строка %d: ORG назад запрещён (%Xh < %Xh)'
                               % (ln.no, newloc, loc))
            loc = newloc
        elif ln.label:
            if ln.label in syms:
                raise AsmError('строка %d: символ %r уже определён' % (ln.no, ln.label))
            syms[ln.label] = None       # адресная метка, значение после прохода

        ln.addr = loc
        loc += size

    if ifstack:
        raise AsmError('незакрытый IF (осталось уровней: %d)' % len(ifstack))

    # метки не должны остаться с None — кроме переопределённых -D констант
    for ln in lines:
        if ln.label is not None and syms.get(ln.label) is None:
            syms[ln.label] = ln.addr if ln.addr is not None else 0

    # отложенные константы: несколько раундов (цепочки друг на друга)
    for _ in range(len(deferred) + 1):
        progress, rest = False, []
        for name, expr, lno in deferred:
            try:
                val = expr_eval(expr, syms, 0)
            except AsmError:
                rest.append((name, expr, lno))
                continue
            progress = True
            if name in dnames:
                if syms[name] != val:
                    overrides.append((name, syms[name], val))
            else:
                syms[name] = val
        deferred = rest
        if not progress or not deferred:
            break
    if deferred:
        raise AsmError('не вычисляются отложенные константы (циклическая ссылка?): %s'
                       % ', '.join(n for n, _e, _l in deferred))

    unresolved = [k for k, v in syms.items() if v is None]
    if unresolved:
        raise AsmError('неопределённые символы: %s' % ', '.join(sorted(unresolved)))

    # ---------------------------------------------------------- проход 2
    image = {}
    loc = 0
    ifstack = []   # [branch_active, cond, seen_else, parent_active]
    for ln in lines:
        active = all(f[0] for f in ifstack)
        try:
            cls, _ = opcode_class(ln.mnem, ln.ops, ln.no)
        except AsmError:
            if not all(f[0] for f in ifstack):
                continue
            raise
        if cls == 'if':
            cond = expr_eval(ln.ops[0] if ln.ops else '0', syms, loc) != 0
            ifstack.append([active and cond, cond, False, active])
            continue
        if cls == 'else':
            if not ifstack:
                raise AsmError('строка %d: ELSE без IF' % ln.no)
            f = ifstack[-1]
            if f[2]:
                raise AsmError('строка %d: второй ELSE' % ln.no)
            f[0] = f[3] and (not f[1])
            f[2] = True
            continue
        if cls == 'endif':
            ifstack.pop()
            continue
        if cls in ('end', 'none'):
            if cls == 'end':
                break
            continue
        if not active:
            continue

        out = b''
        if cls == 'org':
            loc = expr_eval(ln.ops[0], syms, loc)
        elif cls == 'equ':
            pass
        elif cls == 'db':
            for it in ln.ops:
                if len(it) >= 2 and it[0] == "'":
                    body = it[1:-1] if it.endswith("'") else it[1:]
                    out += body.encode('cp1251')
                else:
                    out += bytes([range_check(expr_eval(it, syms, loc), 0xFF, 'DB-байт', ln.no)])
            _put(image, loc, out)
            loc += len(out)
        elif cls == 'dw':
            for it in ln.ops:
                w = range_check(expr_eval(it, syms, loc), 0xFFFF, 'DW-слово', ln.no)
                out += bytes([w & 0xFF, (w >> 8) & 0xFF])
            _put(image, loc, out)
            loc += len(out)
        else:
            out = _emit(ln, cls, syms, loc)
            _put(image, loc, out)
            loc += len(out)
        ln.bytes = out

    if not image:
        raise AsmError('в исходнике нет ни одного байта кода')
    minaddr, maxaddr = min(image), max(image)
    return image, minaddr, maxaddr, syms, lines, enc, overrides


def _put(image, addr, data):
    for i, b in enumerate(data):
        image[addr + i] = b


def _emit(ln, cls, syms, loc):
    m, ops = ln.mnem, ln.ops
    if cls == 'impl':
        return bytes([IMPL1[m]])
    if cls == 'rr':
        return bytes([GRP_R[m] | check_reg(ops[0], ln.no)])
    if cls == 'mov':
        return bytes([0x40 | (check_reg(ops[0], ln.no) << 3) | check_reg(ops[1], ln.no)])
    if cls == 'mvi':
        return bytes([0x06 | (check_reg(ops[0], ln.no) << 3),
                      range_check(expr_eval(ops[1], syms, loc), 0xFF, 'imm8', ln.no)])
    if cls == 'inr':
        base = 0x04 if m == 'INR' else 0x05
        return bytes([base | (check_reg(ops[0], ln.no) << 3)])
    if cls == 'rp':
        return bytes([GRP_RP[m] | (check_rp(ops[0], ln.no, RP_NO_PSW) << 4)])
    if cls == 'push':
        return bytes([(0xC5 if m == 'PUSH' else 0xC1) | (check_rp(ops[0], ln.no, RP) << 4)])
    if cls == 'lxi':
        rp = check_rp(ops[0], ln.no, RP_NO_PSW)
        v = range_check(expr_eval(ops[1], syms, loc), 0xFFFF, 'imm16', ln.no)
        return bytes([0x01 | (rp << 4), v & 0xFF, (v >> 8) & 0xFF])
    if cls == 'stax':
        r = str(ops[0]).strip().upper()
        if r not in ('B', 'D'):
            raise AsmError('строка %d: STAX/LDAX только B или D' % ln.no)
        return bytes([GRP_STX[m] | (RP[r] << 4)])
    if cls == 'i8':
        return bytes([GRP_I8[m],
                      range_check(expr_eval(ops[0], syms, loc), 0xFF, 'imm8', ln.no)])
    if cls == 'a16':
        v = range_check(expr_eval(ops[0], syms, loc), 0xFFFF, 'addr16', ln.no)
        return bytes([GRP_A16[m], v & 0xFF, (v >> 8) & 0xFF])
    if cls == 'rst':
        n = expr_eval(ops[0], syms, loc)
        if n > 7:
            raise AsmError('строка %d: RST 0..7' % ln.no)
        return bytes([0xC7 | (n << 3)])
    raise AsmError('строка %d: класс %r не эмитится' % (ln.no, cls))


def intel_hex(image, minaddr, maxaddr):
    out = []
    data = bytes(image.get(a, 0x00) for a in range(minaddr, maxaddr + 1))
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        addr = minaddr + off
        rec = bytes([len(chunk), (addr >> 8) & 0xFF, addr & 0xFF, 0x00]) + chunk
        crc = (-sum(rec)) & 0xFF
        out.append(':' + ''.join('%02X' % b for b in rec) + '%02X' % crc)
    out.append(':00000001FF')
    return '\n'.join(out) + '\n'


def listing_text(lines):
    rows = []
    for ln in lines:
        if ln.addr is None and not ln.bytes:
            rows.append('%5d            %s' % (ln.no, ln.text))
        else:
            bb = ' '.join('%02X' % b for b in ln.bytes)
            rows.append('%5d  %04X: %-8s %s' % (ln.no, ln.addr if ln.addr is not None else 0,
                                                bb or '-', ln.text))
    return '\n'.join(rows) + '\n'


# ---------------------------------------------------------------- дизасм

REV_IMPL = {v: k for k, v in IMPL1.items()}
REV_A16 = {v: k for k, v in GRP_A16.items()}
REV_I8 = {v: k for k, v in GRP_I8.items()}
REV_RR = {}
for _name, _base in GRP_R.items():
    for _i in range(8):
        REV_RR[_base | _i] = (_name, _i)
REGN = {v: k for k, v in REGR.items()}
RPN_ = {v: k for k, v in RP.items()}


def read_hex(path):
    mem = {}
    for line in open(path, 'r'):
        line = line.strip()
        if not line.startswith(':'):
            continue
        b = bytes.fromhex(line[1:])
        cnt, ah, al, typ = b[0], b[1], b[2], b[3]
        payload = b[4:4 + cnt]
        crc = b[4 + cnt]
        if ((cnt + ah + al + typ + sum(payload) + crc) & 0xFF) != 0:
            raise AsmError('контрольная сумма Intel HEX не сходится: %s' % line)
        if typ == 0:
            base = (ah << 8) | al
            for i, byte in enumerate(payload):
                mem[base + i] = byte
    return mem


def disasm(path):
    mem = read_hex(path)
    if not mem:
        raise AsmError('нет данных в hex')
    addrs = sorted(mem)
    lo, hi = addrs[0], addrs[-1]
    out = []
    a = lo
    while a <= hi:
        op = mem.get(a, 0x00)
        if op in REV_IMPL:
            txt, n = REV_IMPL[op], 1
        elif op in REV_A16:
            txt, n = '%s %02X%02Xh' % (REV_A16[op], mem.get(a + 2, 0), mem.get(a + 1, 0)), 3
        elif op in REV_I8:
            txt, n = '%s %02Xh' % (REV_I8[op], mem.get(a + 1, 0)), 2
        elif op in REV_RR:
            nm, rg = REV_RR[op]
            txt, n = '%s %s' % (nm, REGN[rg]), 1
        elif 0x40 <= op <= 0x7F:
            txt, n = 'MOV %s,%s' % (REGN[(op >> 3) & 7], REGN[op & 7]), 1
        elif (op & 0xC7) == 0x06:
            txt, n = 'MVI %s,%02Xh' % (REGN[(op >> 3) & 7], mem.get(a + 1, 0)), 2
        elif (op & 0xC7) in (0x04, 0x05):
            txt, n = '%s %s' % ('INR' if (op & 7) == 4 else 'DCR', REGN[(op >> 3) & 7]), 1
        elif (op & 0xCF) == 0x01:
            rp = (op >> 4) & 3
            txt, n = 'LXI %s,%02X%02Xh' % ('SP' if rp == 3 else RPN_[rp],
                                           mem.get(a + 2, 0), mem.get(a + 1, 0)), 3
        elif (op & 0xCF) == 0xC5:
            rp = (op >> 4) & 3
            txt, n = 'PUSH %s' % ('PSW' if rp == 3 else RPN_[rp]), 1
        elif (op & 0xCF) == 0xC1:
            rp = (op >> 4) & 3
            txt, n = 'POP %s' % ('PSW' if rp == 3 else RPN_[rp]), 1
        elif (op & 0xC7) == 0xC7:
            txt, n = 'RST %d' % ((op >> 3) & 7), 1
        elif op in (0x02, 0x12):
            txt, n = 'STAX %s' % ('B' if op == 0x02 else 'D'), 1
        elif op in (0x0A, 0x1A):
            txt, n = 'LDAX %s' % ('B' if op == 0x0A else 'D'), 1
        elif (op & 0xCF) in (0x03, 0x0B):
            rp = (op >> 4) & 3
            txt, n = '%s %s' % ('INX' if (op & 0xCF) == 0x03 else 'DCX',
                                'SP' if rp == 3 else RPN_[rp]), 1
        elif (op & 0xCF) == 0x09:
            rp = (op >> 4) & 3
            txt, n = 'DAD %s' % ('SP' if rp == 3 else RPN_[rp]), 1
        else:
            txt, n = '??? %02Xh' % op, 1
        bb = ' '.join('%02X' % mem.get(a + i, 0) for i in range(n))
        out.append('%04X: %-8s %s' % (a, bb, txt))
        a += n
    return '\n'.join(out) + '\n'


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description='мини-ассемблер 8085 (retro_PCLD_board)')
    ap.add_argument('source', nargs='?')
    ap.add_argument('-o', '--output')
    ap.add_argument('-l', '--listing')
    ap.add_argument('-D', '--define', action='append', default=[], metavar='NAME=VAL')
    ap.add_argument('--disasm', metavar='HEXFILE')
    args = ap.parse_args()

    if args.disasm:
        sys.stdout.write(disasm(args.disasm))
        return
    if not args.source:
        ap.error('нужен исходник .asm (или --disasm out.hex)')

    defines = {}
    for d in args.define:
        if '=' not in d:
            ap.error('-D ждёт NAME=VAL, получено %r' % d)
        k, v = d.split('=', 1)
        defines[k.strip().upper()] = int(v.strip(), 0)

    image, minaddr, maxaddr, syms, lines, enc, overrides = assemble(args.source, defines)
    ihex = intel_hex(image, minaddr, maxaddr)

    if args.output:
        open(args.output, 'w').write(ihex)
    if args.listing:
        open(args.listing, 'w', encoding='cp1251', errors='replace').write(listing_text(lines))

    print('источник : %s (%s)' % (args.source, enc))
    print('образ    : %04Xh-%04Xh, %d байт' % (minaddr, maxaddr, maxaddr - minaddr + 1))
    for name, val in sorted(syms.items()):
        print('  %-8s = %04Xh' % (name, val))
    for name, old, new in overrides:
        print('  ! %s: файловое EQU %s перекрыто ключом -D (=%s)' % (name, new, old))
    print('hex      : %s' % (args.output or '(stdout)'))


if __name__ == '__main__':
    try:
        main()
    except AsmError as e:
        print('ОШИБКА: %s' % e, file=sys.stderr)
        sys.exit(1)
