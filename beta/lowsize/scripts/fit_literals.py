#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Точный подсчёт литералов сброса в секции Mapped Logic (только уравнения)."""
import re, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# пути от ПАПКИ СКРИПТА (beta/lowsize/scripts/) — работает из любого CWD
HERE = os.path.dirname(os.path.abspath(__file__))
FILES = [
    ("v3.9   (hiclock)",  os.path.join(HERE, "../../hiclock/retro_pcld_top (v39).rpt")),
    ("v3.10  (hiclock)",  os.path.join(HERE, "../../hiclock/retro_pcld_top (v310).rpt")),
    ("v3.9.2 (lowsize)",  os.path.join(HERE, "../retro_pcld_top (v392).rpt")),
    ("v3.9.3 (lowsize)",  os.path.join(HERE, "../retro_pcld_top (v393).rpt")),
    ("v3.9.3 fit2 (прошит)", os.path.join(HERE, "../retro_pcld_top (v393-fit2-1102-954PM).rpt")),
    ("v3.9.4 fit1", os.path.join(HERE, "../retro_pcld_top (v394-fit1-1104-1015PM).rpt")),
]

for name, path in FILES:
    txt = open(path, encoding='cp1251', errors='replace').read()
    m = re.search(r'\*\*\*\*\* Mapped Logic \*\*\*\*(.*?)Register Legend', txt, re.S)
    eq = m.group(1) if m else ''
    rst_lit    = len(re.findall(r'(?<![A-Za-z0-9_])RST(?![A-Za-z0-9_])', eq))
    porrun_lit = len(re.findall(r'\bpor_run\b', eq))
    cpurst_lit = len(re.findall(r'\bcpu_rst\b', eq))
    clr_rst    = len(re.findall(r",clk,RST,'0'\)", eq))
    clr_curst  = len(re.findall(r",clk,cpu_rst,'0'\)", eq))
    # вхождения в термах (внутри уравнений с '<='): порт-мэпы FDCPE тоже здесь.
    # Порт-мэп считаем ПОСТРОЧНО (аргументы с вложенными скобками D_I(0)
    # ломают [^)]*), поэтому: строка содержит 'port map' И целевой литерал.
    pm_rst     = len(re.findall(r'^.*port map.*(?<![A-Za-z0-9_])RST(?![A-Za-z0-9_]).*$', eq, re.M))
    pm_porrun  = len(re.findall(r'^.*port map.*\bpor_run\b.*$', eq, re.M))
    print(f"{name:<19} RST: всего {rst_lit:>3} (из них в port map {pm_rst:>3}, в термах {rst_lit-pm_rst:>3}) | "
          f"por_run: всего {porrun_lit:>3} (port map {pm_porrun}, в термах {porrun_lit-pm_porrun:>3}) | "
          f"cpu_rst: {cpurst_lit:>3} | CLR=RST: {clr_rst:>3}, CLR=cpu_rst: {clr_curst}")
