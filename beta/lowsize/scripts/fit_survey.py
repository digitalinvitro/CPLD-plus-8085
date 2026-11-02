#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сводка фит-отчётов линии lowsize/hiclock (v3.9/v3.10/v3.9.2/v3.9.3)."""
import re, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# пути от ПАПКИ СКРИПТА (beta/lowsize/scripts/) — работает из любого CWD
HERE = os.path.dirname(os.path.abspath(__file__))
FILES = [
    ("v3.9   (hiclock)", os.path.join(HERE, "../../hiclock/retro_pcld_top (v39).rpt")),
    ("v3.10  (hiclock)", os.path.join(HERE, "../../hiclock/retro_pcld_top (v310).rpt")),
    ("v3.9.2 (lowsize)", os.path.join(HERE, "../retro_pcld_top (v392).rpt")),
    ("v3.9.3 (lowsize)", os.path.join(HERE, "../retro_pcld_top (v393).rpt")),
    ("v3.9.3 fit2 (прошит)", os.path.join(HERE, "../retro_pcld_top (v393-fit2-1102-954PM).rpt")),
]

def extract(path):
    txt = open(path, encoding='cp1251', errors='replace').read()
    res = {}
    m = re.search(r"Design Name:\s*(\S+)\s+Date:\s*(.+)", txt)
    res['date'] = m.group(2).strip() if m else '?'
    m = re.search(r"Fitting Status:\s*(\w+)", txt)
    res['status'] = m.group(1) if m else '?'
    # Строка сводки: "86 /108 ( 80%) 192 /540  ( 36%) 173/216 ( 80%)   54 /108 ( 50%) 72 /81  ( 89%)"
    m = re.search(r"(\d+)\s*/108.*?(\d+)\s*/540.*?(\d+)/216.*?(\d+)\s*/108.*?(\d+)\s*/81", txt)
    if m:
        res['mc'], res['pt'], res['fbi'], res['reg'], res['pin'] = m.groups()
    else:
        res['mc'] = res['pt'] = res['fbi'] = res['reg'] = res['pin'] = '?'
    res['gsr_unused'] = 'Global set/reset net(s) unused' in txt
    m = re.search(r"Signal 'RST' mapped onto global set/reset net GSR", txt)
    res['gsr_rst'] = bool(m)
    # вхождения литералов в УРАВНЕНИЯХ (секция Equations)
    eq = txt.split('Equations')[-1]
    res['rst_eq']  = len(re.findall(r'\bRST\b', eq)) - len(re.findall(r'RESET_IN?\b', eq))  # грубо
    res['rst_eq']  = len(re.findall(r'(?<![A-Z_])RST(?![A-Z_])', eq))
    res['porrun_eq'] = len(re.findall(r'\bpor_run\b', eq))
    res['clr_rst'] = len(re.findall(r",clk,RST,'0'\)", eq))
    res['cpu_rst_eq'] = len(re.findall(r'\bcpu_rst\b', eq))
    return res

print(f"{'версия':<18}{'дата':<22}{'статус':<11}{'МЦ':>4}{'ПТ':>5}{'вх.ФБ':>7}{'рег':>5}{'ног':>5}  {'GSR':<10}{'RST(ур.)':>9}{'por_run(ур.)':>13}{'CLR=RST':>9}")
print('-'*120)
for name, path in FILES:
    try:
        r = extract(path)
        gsr = 'RST->GSR' if r['gsr_rst'] else ('unused' if r['gsr_unused'] else '?')
        print(f"{name:<18}{r['date']:<22}{r['status']:<11}{r['mc']:>4}{r['pt']:>5}{r['fbi']:>7}{r['reg']:>5}{r['pin']:>5}  {gsr:<10}{r['rst_eq']:>9}{r['porrun_eq']:>13}{r['clr_rst']:>9}")
    except FileNotFoundError:
        print(f"{name:<18}  ФАЙЛ НЕ НАЙДЕН: {path}")
