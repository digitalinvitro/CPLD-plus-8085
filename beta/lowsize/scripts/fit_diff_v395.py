#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Диф фит-отчётов: v3.9.4 fit1 (GSR от ноги RST) -> v3.9.5 fit1 (cpu_rst, GSR fallback?).

Разбирает Buried/Outputs/Equations двух .rpt, печатает: сводки+опции, дельты ПТ
по узлам, анатомию сброса (порт-мэпы NOT RESET_IN, вхождения в уравнениях,
импорты RESET_IN по ФБ), por-цепь (M1: 4 бита, строб x1_n, Init=SET).
"""
import re, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
OLD = os.path.join(HERE, "..", "retro_pcld_top (v394-fit1-1104-1015PM).rpt")
NEW = os.path.join(HERE, "..", "retro_pcld_top (v395-fit1-1105-1040PM).rpt")

def read(path):
    return open(path, encoding='cp1251', errors='replace').read()

def buried(txt):
    m = re.search(r"\*\* \d+ Buried Nodes \*\*(.*?)\*\* \d+ Inputs \*\*", txt, re.S)
    out = {}
    if not m:
        return out
    pat = re.compile(
        r"^(?P<name>\S.*?)\s+(?P<pt>\d+)\s+(?P<inps>\d+)\s+(?P<loc>FB\d+_\d+)\s+STD(?:\s+(?P<init>RESET|SET))?\s*$",
        re.M)
    lines = m.group(1).splitlines()
    i = 0
    while i < len(lines):
        chunk = lines[i]
        j = i + 1
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

def fbs(txt):
    """{FB: (мц, вх, пт)} из '** Function Block Resources **'."""
    m = re.search(r"\*\* Function Block Resources \*\*(.*?)\*\* Global Control", txt, re.S)
    out = {}
    if not m:
        return out
    for mm in re.finditer(r"^FB(\d)\s+(\d+)/18\*?\s+(\d+)/36\*?\s+\d+\s+(\d+)/90\*?", m.group(1), re.M):
        out['FB' + mm.group(1)] = (int(mm.group(2)), int(mm.group(3)), int(mm.group(4)))
    return out

def eqs(txt):
    m = re.search(r"\*\*\*+ Mapped Logic \*\*\*\*(.*?)Register Legend", txt, re.S)
    return m.group(1) if m else ''

def sig_eqs(eq):
    """Все уравнения 'ИМЯ <= ...;' -> {имя: rhs}."""
    out = {}
    for mm in re.finditer(r"^(\S+)\s*<=\s*(.*?);\s*$", eq, re.S | re.M):
        out[' '.join(mm.group(1).split())] = ' '.join(mm.group(2).split())
    return out

def outputs(txt):
    m = re.search(r"\*\* \d+ Outputs \*\*(.*?)\*\* \d+ Buried Nodes \*\*", txt, re.S)
    out = {}
    if not m:
        return out
    pat = re.compile(r"^(?P<name>[A-Za-z_]\w*(?:<\d+>)?)\s+(?P<pt>\d+)\s+(?P<inps>\d+)\s+(?P<loc>FB\d+_\d+)", re.M)
    for mm in pat.finditer(m.group(1)):
        out[mm.group('name')] = (int(mm.group('pt')), int(mm.group('inps')))
    return out

def reset_anatomy(txt, eq):
    print(f"  порт-мэпов с NOT RESET_IN : {len(re.findall(r'NOT RESET_IN', eq))}")
    print(f"  порт-мэпов всего (FDCPE/FTCPE/LDCP): {len(re.findall(r'(?:FDCPE|FTCPE|LDCP)_\w+:', eq))}")
    print(f"  RESET_IN как терм в уравнениях: {len(re.findall(r'NOT por_run AND NOT RST', eq))}")
    print(f"  литералов RST в уравнениях: {len(re.findall(r'(?<![A-Za-z_])RST(?![A-Za-z_])', eq))}")
    print(f"  литералов por_run в уравнениях: {len(re.findall(r'[ ]por_run[ ]', ' ' + eq + ' '))}")
    print(f"  литералов cpu_rst в уравнениях: {len(re.findall(r'(?<![A-Za-z_])cpu_rst(?![A-Za-z_])', eq))}")
    gsr_hit = re.search(r"Signal 'RST' mapped onto global set/reset net GSR", txt)
    gsr = 'RST->GSR' if gsr_hit else ('UNUSED' if 'Global set/reset net(s) unused' in txt else '?')
    print(f"  GSR: {gsr}")
    m = re.search(r"The complement of 'clk' mapped onto global clock net (\w+)", txt)
    m2 = re.search(r"Signal 'clk' mapped onto global clock net (\w+)", txt)
    print(f"  GCK: clk->{m2.group(1) if m2 else '?'}, !clk->{m.group(1) if m else '?'}")
    # импорты RESET_IN по ФБ (списки 'Signals Used by Logic in Function Block')
    for fbm in re.finditer(r"\*\*\*+ FB(\d) \*\*\*\*(.*?)\*\*\*+", txt, re.S):
        sigs = re.search(r"Signals Used by Logic in Function Block(.*?)Signal\s+1\s+", fbm.group(2), re.S)
        cnt = len(re.findall(r"^\s*\d+: RESET_IN\s*$", sigs.group(1), re.M)) if sigs else 0
        rst = len(re.findall(r"^\s*\d+: RST\s*$", sigs.group(1), re.M)) if sigs else 0
        print(f"  FB{fbm.group(1)}: RESET_IN импорт={cnt}, RST импорт={rst}")

old_t, new_t = read(OLD), read(NEW)
old_e, new_e = eqs(old_t), eqs(new_t)
old_s, new_s = sig_eqs(old_e), sig_eqs(new_e)

print("=== СВОДКИ / ОПЦИИ ===")
so, sn = summary(old_t), summary(new_t)
print(f"v3.9.4 fit1 : МЦ/ПТ/вхФБ/рег/ног = {so}  {options(old_t)}")
print(f"v3.9.5 fit1 : МЦ/ПТ/вхФБ/рег/ног = {sn}  {options(new_t)}")
if so and sn:
    print(f"дельта      : МЦ {sn[0]-so[0]:+d}, ПТ {sn[1]-so[1]:+d}, вх.ФБ {sn[2]-so[2]:+d}, рег {sn[3]-so[3]:+d}, ног {sn[4]-so[4]:+d}")

print("\n=== ФБ (МЦ/вх/ПТ) ===")
fo, fn = fbs(old_t), fbs(new_t)
for k in sorted(set(fo) | set(fn)):
    a, b = fo.get(k), fn.get(k)
    print(f"  {k}: {a} -> {b}  (МЦ{b[0]-a[0]:+d}, вх{b[1]-a[1]:+d}, ПТ{b[2]-a[2]:+d})")

print("\n=== АНАТОМИЯ СБРОСА ===")
print("-- v3.9.4 fit1 --"); reset_anatomy(old_t, old_e)
print("-- v3.9.5 fit1 --"); reset_anatomy(new_t, new_e)

print("\n=== ЛИТЕРАЛЫ СБРОСА В D-ФУНКЦИЯХ (v3.9.5, не порт-мэпы) ===")
bad = []
for name, rhs in sorted(new_s.items()):
    if re.search(r"(?<![A-Za-z_])(RST|RESET_IN|cpu_rst)(?![A-Za-z_])", rhs):
        bad.append((name, rhs[:110]))
if bad:
    for n, r in bad:
        print(f"  {n} <= {r}")
else:
    print("  чисто: ни RST, ни RESET_IN, ни cpu_rst в правых частях уравнений")
por = [(n, r) for n, r in sorted(new_s.items()) if 'por_run' in r and not n.startswith('FDCPE')]
print(f"  por_run в правых частях (функциональный гейт п.18): {len(por)} уравн.")
for n, r in por:
    print(f"    {n} <= {r[:120]}")

print("\n=== BURIED (без $): ушёл/пришёл/ПТ-дельта ===")
old_b, new_b = buried(old_t), buried(new_t)
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

print("\n=== ХЕЛПЕРЫ $OpTx ===")
old_h = {n: old_b[n] for n in old_b if n.startswith('$')}
new_h = {n: new_b[n] for n in new_b if n.startswith('$')}
print(f"было {len(old_h)}: " + ", ".join(f"{n}({v[0]}ПТ/{v[1]}вх)" for n, v in sorted(old_h.items())))
print(f"стало {len(new_h)}: " + ", ".join(f"{n}({v[0]}ПТ/{v[1]}вх)" for n, v in sorted(new_h.items())))

print("\n=== ВЫХОДЫ ===")
old_o, new_o = outputs(old_t), outputs(new_t)
print(f"было {len(old_o)}, стало {len(new_o)}")
so_pt, sn_pt = sum(v[0] for v in old_o.values()), sum(v[0] for v in new_o.values())
print(f"sum ПТ выходов: {so_pt} -> {sn_pt} ({sn_pt-so_pt:+d})")
for n in sorted(set(old_o) | set(new_o)):
    po, pn = old_o.get(n), new_o.get(n)
    if po != pn:
        print(f"  {n:<12} {po} -> {pn}  ({(po[0]-pn[0]) if po and pn else '?':+d}ПТ)")

print("\n=== POR-ЦЕПЬ (v3.9.5) ===")
for n in sorted(new_s):
    if 'por_sh' in n or 'por_run' in n:
        print(f"  {n} <= {new_s[n]}")
m = re.search(r"FDCPE_por_run.*", new_t)
print("  порт-мэп por_run:", m.group(0) if m else '?')
for name in ('por_sh<3>', 'por_sh<2>', 'por_sh<1>', 'por_sh<0>', 'por_run'):
    row = [l for l in new_t.splitlines() if l.strip().startswith(name + ' ') and 'SET' in l]
    print(f"  Init {name}: {'SET ok' if row else 'NOT FOUND'}")
