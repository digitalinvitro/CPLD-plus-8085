#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Диф buried-узлов и ПТ-бюджета: v3.9.3 fit2 (прошит) -> v3.9.4 fit1.

Разбирает секции Buried Nodes двух .rpt, сопоставляет по именам
(хелперы $OpTx$... - отдельно, по сигнатурам уравнений), печатает:
кто ушёл, кто пришёл, изменения ПТ по узлам, итоговые дельты.
"""
import re, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
OLD = os.path.join(HERE, "..", "retro_pcld_top (v393-fit2-1102-954PM).rpt")
NEW = os.path.join(HERE, "..", "retro_pcld_top (v394-fit1-1104-1015PM).rpt")

def read(path):
    return open(path, encoding='cp1251', errors='replace').read()

def buried(txt):
    """{имя: (ПТ, вх, Loc, Init)} из секции '** N Buried Nodes **'."""
    m = re.search(r"\*\* \d+ Buried Nodes \*\*(.*?)\*\* \d+ Inputs \*\*", txt, re.S)
    out = {}
    if not m:
        return out
    body = m.group(1)
    # строки вида: имя  ПТ  вх  Loc  STD  [RESET|SET]  (имя может переноситься)
    pat = re.compile(
        r"^(?P<name>\S.*?)\s+(?P<pt>\d+)\s+(?P<inps>\d+)\s+(?P<loc>FB\d+_\d+)\s+STD(?:\s+(?P<init>RESET|SET))?\s*$",
        re.M)
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        chunk = lines[i]
        j = i + 1
        # склеиваем перенесённые имена (следующая строка начинается с пробелов и не матчится)
        while j < len(lines) and not pat.match(lines[j]) and lines[j].strip() and not lines[j].startswith('Signal'):
            chunk += ' ' + lines[j].strip()
            j += 1
        m2 = pat.match(chunk)
        if m2:
            out[' '.join(m2.group('name').split())] = (
                int(m2.group('pt')), int(m2.group('inps')), m2.group('loc'), m2.group('init'))
        i = j if j > i else i + 1
    return out

def options(txt):
    opts = {}
    for key, pat in [('Input Limit', r"Input Limit\s*:\s*(\S+)"),
                     ('Pterm Limit', r"Pterm Limit\s*:\s*(\S+)"),
                     ('Exhaustive',  r"Exhaustive Fitting\s*:\s*(\S+)")]:
        m = re.search(pat, txt)
        opts[key] = m.group(1) if m else '?'
    return opts

def summary(txt):
    m = re.search(r"(\d+)\s*/108.*?(\d+)\s*/540.*?(\d+)/216.*?(\d+)\s*/108.*?(\d+)\s*/81", txt)
    return tuple(int(x) for x in m.groups()) if m else None

def optx_eqs(txt):
    """Уравнения хелперов $OpTx$... -> {имя: уравнение-строка}."""
    m = re.search(r"\*\*\*+ Mapped Logic \*\*\*\*(.*?)Register Legend", txt, re.S)
    eq = m.group(1) if m else ''
    out = {}
    for mm in re.finditer(r"^(\$\w+)\s*<=\s*(.*?);\s*$", eq, re.S | re.M):
        name, rhs = mm.group(1), ' '.join(mm.group(2).split())
        out[name] = rhs
    return out

def op_name(sig):
    """Стабильное имя хелпера по сигнатуре уравнения (без случайных $NNN)."""
    toks = set(re.findall(r"[A-Za-z_0-9$]+", sig))
    feats = []
    if 'ALE' in toks: feats.append('ALE')
    if 'IOM' in toks: feats.append('IOM')
    if 'WRn' in toks: feats.append('WRn')
    for a in re.findall(r"addr_latch\((\d)\)", sig): feats.append('al' + a)
    state = ''.join(f"{'n' if ('NOTstate_FSM_FFd' + k) in sig.replace(' ', '') else ''}F{k}"
                    for k in ('1', '2', '3') if ('state_FSM_FFd' + k) in toks)
    return f"{state}:{'+'.join(sorted(feats)) if feats else '-'}"

old_t, new_t = read(OLD), read(NEW)
old_b, new_b = buried(old_t), buried(new_t)
print("=== СВОДКИ ===")
print("v3.9.3 fit2 :", summary(old_t), options(old_t))
print("v3.9.4 fit1 :", summary(new_t), options(new_t))

old_x, new_x = optx_eqs(old_t), optx_eqs(new_t)
old_help = {n for n in old_b if n.startswith('$')}
new_help = {n for n in new_b if n.startswith('$')}
print(f"\n=== ХЕЛПЕРЫ $OpTx: было {len(old_help)}, стало {len(new_help)} ===")
print("-- v3.9.3 fit2 --")
for n in sorted(old_help):
    pt, inp, loc, init = old_b[n]
    print(f"  {n:<22} {pt}ПТ/{inp}вх {loc}  {op_name(old_x.get(n,''))}")
print("-- v3.9.4 fit1 --")
for n in sorted(new_help):
    pt, inp, loc, init = new_b[n]
    print(f"  {n:<22} {pt}ПТ/{inp}вх {loc}  {op_name(new_x.get(n,''))}")

print("\n=== BURIED (без $): ушёл/пришёл/ПТ-дельта ===")
old_u = {n: v for n, v in old_b.items() if not n.startswith('$')}
new_u = {n: v for n, v in new_b.items() if not n.startswith('$')}
gone = sorted(set(old_u) - set(new_u))
came = sorted(set(new_u) - set(old_u))
common = sorted(set(old_u) & set(new_u))
print(f"было {len(old_u)}, стало {len(new_u)}, общих {len(common)}")
for n in gone:
    pt, inp, loc, init = old_u[n]
    print(f"  УШЁЛ   {n:<38} {pt}ПТ/{inp}вх {loc} {init or ''}")
for n in came:
    pt, inp, loc, init = new_u[n]
    print(f"  ПРИШЁЛ {n:<38} {pt}ПТ/{inp}вх {loc} {init or ''}")
d = 0
for n in common:
    po, io_, lo, ioi = old_u[n]; pn, iN, ln, ini = new_u[n]
    if (po, io_) != (pn, iN):
        print(f"  ИЗМЕН. {n:<38} {po}ПТ/{io_}вх -> {pn}ПТ/{iN}вх  ({po-pn:+d}ПТ)")
        d += po - pn
print(f"  sum ПТ-дельта по общим узлам: {d:+d}")

print("\n=== por_sh / por_run: уравнения v3.9.3 fit2 ===")
for n, rhs in sorted(old_x.items()):
    if 'por_sh' in n or 'por_run' in n or 'por_sh' in rhs:
        print(f"  {n} <= {rhs}")
print("--- por_sh в v3.9.4 fit1 ---")
for n, rhs in sorted(new_x.items()):
    if 'por_sh' in n or 'por_run' in n:
        print(f"  {n} <= {rhs}")
m = re.search(r"FDCPE_por_run.*", new_t)
print("  порт-мэп por_run:", m.group(0) if m else '?')

def outputs(txt):
    """{имя: (ПТ, вх)} из секции '** N Outputs **' (до Buried Nodes)."""
    m = re.search(r"\*\* \d+ Outputs \*\*(.*?)\*\* \d+ Buried Nodes \*\*", txt, re.S)
    out = {}
    if not m:
        return out
    pat = re.compile(r"^(?P<name>[A-Za-z_]\w*(?:<\d+>)?)\s+(?P<pt>\d+)\s+(?P<inps>\d+)\s+(?P<loc>FB\d+_\d+)", re.M)
    for mm in pat.finditer(m.group(1)):
        out[mm.group('name')] = (int(mm.group('pt')), int(mm.group('inps')))
    return out

old_o, new_o = outputs(old_t), outputs(new_t)
print(f"\n=== ВЫХОДЫ: было {len(old_o)}, стало {len(new_o)} ===")
so, sn = sum(v[0] for v in old_o.values()), sum(v[0] for v in new_o.values())
print(f"  sum ПТ выходов: {so} -> {sn} ({sn-so:+d})")
for n in sorted(set(old_o) | set(new_o)):
    po = old_o.get(n); pn = new_o.get(n)
    if po != pn:
        print(f"  {n:<12} {po} -> {pn}  ({(po[0]-pn[0]) if po and pn else '?':+d}ПТ)")
