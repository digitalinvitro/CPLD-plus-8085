#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Мини-ассемблер 8085 для TXSTRESS.
Поддержка: ORG, EQU, DB, IF/ENDIF (без вложений), метки, базовый набор инструкций.
Выдаёт: листинг с T-состояниями, .bin, .hex (Intel HEX).
"""
import sys, re

def parse_num(tok, sym):
    tok = tok.strip()
    if tok in sym:
        return sym[tok]
    # SYM+конст (адреса вида FB+0006h, S_FCNT+1) — gfxstream v1
    m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*\+\s*(\S+)", tok)
    if m and m.group(1) in sym:
        return (sym[m.group(1)] + parse_num(m.group(2), sym)) & 0xFFFF
    if re.fullmatch(r"'(.)'", tok):
        return ord(tok[1])
    m = re.fullmatch(r"([0-9A-Fa-f][0-9A-Fa-f]*)[Hh]", tok)
    if m: return int(m.group(1), 16)
    m = re.fullmatch(r"([0-9]+)[Dd]?", tok)
    if m: return int(m.group(1), 10)
    m = re.fullmatch(r"([0-9]+)[Bb]", tok)
    if m: return int(m.group(1), 2)
    raise ValueError(f"число?: {tok!r}")

R = {'B':0,'C':1,'D':2,'E':3,'H':4,'L':5,'M':6,'A':7}
# (мнемоника, шаблон операндов) -> кодировщик; T-состояния 8085A
def enc(mn, ops, sym, pc):
    mn = mn.upper()
    def n(i): return parse_num(ops[i], sym)
    if mn == 'NOP': return ([0x00], 4)
    if mn == 'DI':  return ([0xF3], 4)
    if mn == 'EI':  return ([0xFB], 4)
    if mn == 'HLT': return ([0x76], 5)
    if mn == 'RRC': return ([0x0F], 4)
    if mn == 'RLC': return ([0x07], 4)
    if mn == 'DAA': return ([0x27], 4)
    if mn == 'CMA': return ([0x2F], 4)
    if mn == 'MOV' and len(ops) == 2:
        d, s = R[ops[0].upper()], R[ops[1].upper()]
        return ([0x40 | (d << 3) | s], 7 if (d == 6 or s == 6) else 4)
    if mn == 'MVI' and len(ops) == 2:
        return ([0x06 | (R[ops[0].upper()] << 3), n(1) & 0xFF], 7)
    if mn == 'LXI' and len(ops) == 2:
        rp = {'B':0,'D':1,'H':2,'SP':3}[ops[0].upper()]
        v = n(1)
        return ([0x01 | (rp << 4), v & 0xFF, (v >> 8) & 0xFF], 10)
    if mn == 'OUT' and len(ops) == 1: return ([0xD3, n(0) & 0xFF], 10)
    if mn == 'IN'  and len(ops) == 1: return ([0xDB, n(0) & 0xFF], 10)
    if mn == 'INR' and len(ops) == 1: return ([0x04 | (R[ops[0].upper()] << 3)], 4)
    if mn == 'DCR' and len(ops) == 1: return ([0x05 | (R[ops[0].upper()] << 3)], 4)
    if mn == 'INX' and len(ops) == 1:
        rp = {'B':0,'D':1,'H':2,'SP':3}[ops[0].upper()]
        return ([0x03 | (rp << 4)], 6)
    if mn == 'DCX' and len(ops) == 1:
        rp = {'B':0,'D':1,'H':2,'SP':3}[ops[0].upper()]
        return ([0x0B | (rp << 4)], 6)
    # --- gfxstream v1: аддитивное расширение (старые источники не трогаются) ---
    if mn == 'DAD' and len(ops) == 1:                      # HL += rp
        rp = {'B':0,'D':1,'H':2,'SP':3}[ops[0].upper()]
        return ([0x09 | (rp << 4)], 10)
    if mn == 'STAX' and len(ops) == 1:                     # [rp] = A (B/D)
        rp = {'B':0,'D':1}[ops[0].upper()]
        return ([0x02 | (rp << 4)], 7)
    if mn == 'LDAX' and len(ops) == 1:                     # A = [rp] (B/D)
        rp = {'B':0,'D':1}[ops[0].upper()]
        return ([0x0A | (rp << 4)], 7)
    if mn == 'XCHG' and len(ops) == 0: return ([0xEB], 4)  # HL <-> DE
    if mn == 'LDA' and len(ops) == 1:
        v = n(0); return ([0x3A, v & 0xFF, (v >> 8) & 0xFF], 13)
    if mn == 'STA' and len(ops) == 1:
        v = n(0); return ([0x32, v & 0xFF, (v >> 8) & 0xFF], 13)
    if mn == 'LHLD' and len(ops) == 1:
        v = n(0); return ([0x2A, v & 0xFF, (v >> 8) & 0xFF], 16)
    if mn == 'SHLD' and len(ops) == 1:
        v = n(0); return ([0x22, v & 0xFF, (v >> 8) & 0xFF], 16)
    if mn == 'PUSH' and len(ops) == 1:
        rp = {'B':0,'D':1,'H':2,'PSW':3}[ops[0].upper()]
        return ([0xC5 | (rp << 4)], 12)
    if mn == 'POP' and len(ops) == 1:
        rp = {'B':0,'D':1,'H':2,'PSW':3}[ops[0].upper()]
        return ([0xC1 | (rp << 4)], 10)
    if mn in ('ORA','ANA','XRA','ADD','ADC','SUB','SBB','CMP') and len(ops) == 1:
        base = {'ADD':0x80,'ADC':0x88,'SUB':0x90,'SBB':0x98,'ANA':0xA0,
                'XRA':0xA8,'ORA':0xB0,'CMP':0xB8}[mn]
        return ([base | R[ops[0].upper()]], 4)
    if mn in ('ANI','ADI','ACI','SUI','SBI','XRI','ORI','CPI') and len(ops) == 1:
        base = {'ADI':0xC6,'ACI':0xCE,'SUI':0xD6,'SBI':0xDE,'ANI':0xE6,
                'XRI':0xEE,'ORI':0xF6,'CPI':0xFE}[mn]
        return ([base, n(0) & 0xFF], 7)
    if mn in ('JMP','JNZ','JZ','JNC','JC','JPO','JPE','JP','JM'):
        op = {'JMP':0xC3,'JNZ':0xC2,'JZ':0xCA,'JNC':0xD2,'JC':0xDA,
              'JPO':0xE2,'JPE':0xEA,'JP':0xF2,'JM':0xFA}[mn]
        v = n(0)
        return ([op, v & 0xFF, (v >> 8) & 0xFF], 10)
    raise ValueError(f"не знаю инструкцию: {mn} {ops}")

def size_of(mn, nops):
    mn = mn.upper()
    if mn in ('JMP','JNZ','JZ','JNC','JC','JPO','JPE','JP','JM','LXI','LDA','STA','LHLD','SHLD'): return 3
    if mn in ('OUT','IN','MVI') and nops >= 1: return 2
    # ФИКС v1.1: непосредственная ALU ДВУХБАЙТОВАЯ (opcode + imm). Раньше
    # размер считался 1, а эмиссия давала 2 - все метки после первого ANI
    # уезжали на +N (v1.0: +13 к FLC, +14 к строкам -> баннер грузил
    # M_BAN-14 и печатал байты КОДА, прыжки SPIN/BUIN вели в чужой код).
    if mn in ('ANI','ADI','ACI','SUI','SBI','XRI','ORI','CPI') and nops >= 1: return 2
    if mn in ('DB',): return None
    return 1

def assemble(src, defines=None):
    defines = defines or {}
    lines = src.splitlines()
    # ---------- проход 1: размеры + символы ----------
    sym, org, pc = {}, 0x0000, 0x0000
    items, skip_if = [], 0
    for raw in lines:
        line = raw.split(';', 1)[0].strip()
        if not line: continue
        if skip_if:
            if line.upper().startswith('ENDIF'): skip_if = 0
            continue
        if line.upper().startswith('IF '):
            cond = parse_num(line[3:].strip(), {**sym, **defines})
            skip_if = 0 if cond else 1
            continue
        if line.upper().startswith('ENDIF'): continue
        label = None
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if m: label, line = m.group(1), m.group(2).strip()
        if not line:
            if label: sym[label] = pc
            continue
        meq = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s+EQU\s+(\S+)\s*$", line, re.I)
        if meq:
            sym[meq.group(1)] = parse_num(meq.group(2), {**sym, **defines})
            continue
        parts = line.split(None, 1)
        head = parts[0].upper()
        rest = parts[1].strip() if len(parts) > 1 else ''
        if head == 'END': break
        if head == 'ORG':
            pc = parse_num(rest, {**sym, **defines}); org = pc
            continue
        if head == 'DB':
            bs = []
            for it in split_db(rest):
                if it.startswith('"'):
                    for ch in it[1:-1]: bs.append(ord(ch))
                else:
                    bs.append(parse_num(it, {**sym, **defines}) & 0xFF)
            if label: sym[label] = pc
            items.append(('db', label, bs, raw))
            pc += len(bs); continue
        ops = [o.strip() for o in rest.split(',')] if rest else []
        if label: sym[label] = pc
        items.append(('ins', label, head, ops, raw))
        pc += size_of(head, len(ops))
    # ---------- проход 2: эмиссия ----------
    out, listing, pc = [], [], org
    for it in items:
        if it[0] == 'db':
            _, label, bs, raw = it
            out.extend(bs)
            listing.append((pc, bs, None, raw))
            pc += len(bs)
        else:
            _, label, mn, ops, raw = it
            code, t = enc(mn, ops, {**sym, **defines}, pc)
            out.extend(code)
            listing.append((pc, code, t, raw))
            pc += len(code)
    return out, listing, sym, org

def split_db(rest):
    items, cur, inq = [], '', False
    i = 0
    while i < len(rest):
        c = rest[i]
        if c == '"': inq = not inq; cur += c
        elif c == ',' and not inq:
            if cur.strip(): items.append(cur.strip())
            cur = ''
        else: cur += c
        i += 1
    if cur.strip(): items.append(cur.strip())
    return items

def intel_hex(data, org=0):
    recs = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        addr = org + i
        body = bytes([len(chunk), (addr >> 8) & 0xFF, addr & 0xFF, 0x00]) + bytes(chunk)
        cs = (-sum(body)) & 0xFF
        recs.append(':' + body.hex().upper() + f'{cs:02X}')
    recs.append(':00000001FF')
    return '\n'.join(recs) + '\n'

if __name__ == '__main__':
    src_path = sys.argv[1]
    out_base = sys.argv[2]
    defines = {}
    for kv in sys.argv[3:]:
        k, v = kv.split('=', 1)
        defines[k] = int(v, 0)
    try:
        src = open(src_path, encoding='utf-8').read()
    except UnicodeDecodeError:
        src = open(src_path, encoding='cp1251').read()  # канон репо (CP1251)
    if defines:
        for k, v in defines.items():
            src = re.sub(rf"(?im)^\s*{k}\s+EQU\s+\S+", f"{k} EQU {v}h", src)
    code, listing, symtab, org = assemble(src)
    print(f"ORG={org:04X}  код={len(code)} байт")
    for addr, codeb, t, raw in listing:
        bs = ' '.join(f'{b:02X}' for b in codeb)
        ts = f'{t:2d}T' if t else '   '
        print(f'{addr:04X}  {bs:<12} {ts}  {raw}')
    img = bytearray(b'\xFF' * 8192)
    img[org:org+len(code)] = bytes(code)
    open(out_base + '.bin', 'wb').write(bytes(img))
    open(out_base + '.hex', 'w').write(intel_hex(code, org))
    print(f'OK: {out_base}.bin/.hex')
