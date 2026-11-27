#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fit_ff_audit.py — аудитор триггеров фити-отчёта Xilinx cpldfit (XC9500).

Разбирает .rpt и печатает ТАБЛИЦУ всех триггеров проекта (FDCPE/FTCPE/LDCP —
примитивы cpldfit) с тем, что в них реально подключилось:

  - тактирование: глобальная сеть GCK или локальная;
  - асинхронный CLR: глобальный GSR-сброс (норма) или локальная сеть ( suspect);
  - асинхронный PRE: глобальный GSR-установка или константа/локальная;
  - место (FB_MC), пад, ПТ/входы, исходная сеть D/T;
  - триггеры, не разместившиеся при упавшем фите (отдельно, с ERROR-пометкой).

Главный вопрос аудита: КАЖДЫЙ ли триггер охвачен асинхронным глобальным
сбросом/установкой (сетью GSR, пин 1). Триггер без GSR получает только
power-up значение INIT и НЕ сбрасывается кнопкой/POR — класс брака (был в
v3.9.x: x1_q с INIT=1 вне GSR). Утилита помечает такие явным (warn).

Использование:
    python3 tools/fit_ff_audit.py <отчёт.rpt> [ещё.rpt ...] [-o сводка.md]

Зависимости: только Python 3 (stdlib). Партнёр tools/rpt_fb_tables.py
(там — таблицы функциональных блоков, здесь — регистры).

Формат источника: секции 'Register Legend', 'Mapped Logic',
'UnMapped Logic', таблицы '** N Outputs/Buried Nodes/Inputs **' отчёта
cpldfit (уравнения и FDCPE/FTCPE/LDCP port map).
"""
import argparse
import re
import sys
from pathlib import Path

# --- разбор легенды примитивов: "FDCPE (Q,D,C,CLR,PRE); FTCPE (...); ..." ---
def parse_legend(text):
    legend = {}
    m = re.search(r'Register Legend:\s*(.*?)(?:\n\s*\n|$)',
                  text, re.S)
    if m:
        for prim, ports in re.findall(r'(\w+)\s*\(([^)]*)\)', m.group(1)):
            plist = [p.strip() for p in ports.split(',')]
            legend[prim] = plist
    # стандартный порядок cpldfit на случай отсутствия легенды
    return legend or {'FDCPE': ['Q', 'D', 'C', 'CLR', 'PRE'],
                      'FTCPE': ['Q', 'T', 'C', 'CLR', 'PRE'],
                      'LDCP':  ['Q', 'D', 'G', 'CLR', 'PRE']}

# --- нормализация имени: уравнения D(0) -> таблицы D<0> ---
def norm(name):
    return name.replace('(', '<').replace(')', '>').strip()

def split_row(line):
    return [p.strip() for p in re.split(r'\s{2,}|\t+', line.strip()) if p.strip()]

# --- таблицы сводки: имя -> (лок, пад, пт, вх) ---
def parse_summary_tables(text):
    info = {}
    cur = None                      # 'out' | 'buried' | 'inp' | None
    for line in text.splitlines():
        if '**' in line and 'Outputs' in line:
            cur = 'out';  continue
        if '**' in line and 'Buried Nodes' in line:
            cur = 'bur';  continue
        if '**' in line and 'Inputs' in line:
            cur = 'inp';  continue
        if (line.startswith('***') or line.startswith('**********')
                or 'Legend' in line or 'Pin No.' in line
                or 'Function Block Details' in line
                or 'Compiler Options' in line):
            cur = None
            continue
        if cur not in ('out', 'bur', 'inp'):
            continue
        row = split_row(line)
        if not row:
            continue
        if cur in ('out', 'bur'):
            if len(row) >= 3 and re.fullmatch(r'\d+', row[1]):
                name = row[0]
                pts, inps = row[1], row[2]
                loc = row[3] if len(row) > 3 else ''
                pin = row[4] if cur == 'out' and len(row) > 4 else ''
                info[norm(name)] = dict(loc=loc, pin=pin, pts=pts, inps=inps,
                                        kind='выход' if cur == 'out' else 'закопан')
        elif cur == 'inp':
            # Signal  Loc  PinNo  PinType  PinUse: Type/Use через один пробел
            row2 = line.split()
            if len(row2) >= 4 and row2[-1] in ('GSR', 'GCK', 'I/O'):
                info[norm(row2[0])] = dict(loc=row2[1], pin=row2[2], pts='-',
                                           inps='-', kind='вход')
    return info

# --- сети GSR/GCK из таблицы входов (столбец Pin Use) ---
def parse_global_nets(text):
    gsr, gck = None, None
    in_inp = False
    for line in text.splitlines():
        if '**' in line and 'Inputs' in line:
            in_inp = True;  continue
        if in_inp and ('Legend' in line or 'UnMapped' in line or 'Mapped Logic' in line):
            in_inp = False
        if in_inp and line.strip():
            row = line.split()          # Type/Use идут через один пробел
            if len(row) >= 4:
                use = row[-1]
                if use == 'GSR':
                    gsr = row[0]
                elif use == 'GCK':
                    gck = row[0]
    return gsr, gck

# --- инстансы триггеров из секций Mapped/UnMapped Logic ---
def parse_ffs(text, legend):
    ffs, section = [], None
    pend = ''                       # накопитель многострочных port map
    for raw in text.splitlines():
        if 'UnMapped Logic' in raw and raw.startswith('*'):
            section = 'unmapped'; pend = '';  continue
        if 'Mapped Logic' in raw and raw.startswith('*'):
            section = 'mapped';   pend = '';  continue
        line = (pend + ' ' + raw.strip()).strip() if pend else raw.strip()
        if not line:
            continue
        if ');' not in line:
            if '(' in line and ':' in line and 'port map' in line:
                pend = line          # продолжение port map на следующих строках
            elif pend:
                pend = line
            continue
        pend = ''
        m = re.match(r'^([\w/$]+):\s*(\w+)\s+port map\s*\((.*)\)\s*;', line)
        if not m or section is None:
            continue
        inst, prim, args_s = m.groups()
        if prim not in legend:
            continue
        args = [a.strip() for a in args_s.split(',')]
        ports = legend[prim]
        if len(args) != len(ports):
            continue                 # не регистр (защита от кривой строки)
        rec = dict(zip(ports, args))
        rec['inst'] = inst;  rec['prim'] = prim;  rec['section'] = section
        ffs.append(rec)
    return ffs

# --- классификация подключения одного порта ---
def cls_port(val, gsr, gck, kind):
    if val in ("'0'", '0'):
        return '—', 'ok'
    if val in ("'1'", '1'):
        return ('конст. 1', 'warn' if kind == 'PRE' else 'ok')
    if gsr and norm(val) == norm(gsr):
        return ('GSR %s' % ('сброс' if kind == 'CLR' else 'установка'), 'ok')
    if gck and norm(val) == norm(gck):
        return ('GCK(глоб.)', 'ok' if kind == 'C' else 'warn')
    return ('лок. %s' % val, 'warn' if kind in ('CLR', 'PRE') else 'info')

def loc_key(loc):
    m = re.match(r'FB(\d+)_(\d+)', loc or '')
    return (int(m.group(1)), int(m.group(2))) if m else (9, 99)

def audit(path, out_lines):
    text = Path(path).read_text(encoding='cp1251', errors='replace')
    legend = parse_legend(text)
    info = parse_summary_tables(text)
    gsr, gck = parse_global_nets(text)
    ffs = parse_ffs(text, legend)

    fit_ok = 'Fitting Status: Successful' in text
    out_lines.append('## %s' % Path(path).name)
    out_lines.append('')
    out_lines.append('- Фит: %s; сеть GSR: **%s**; сеть GCK: **%s**; триггеров: %d'
                     % ('успешен' if fit_ok else '**НЕ СХОДИТСЯ**',
                        gsr or 'не опознана', gck or 'не опознана', len(ffs)))
    out_lines.append('')
    out_lines.append('| # | Триггер (Q) | Тип | Место | Пад | ПТ/Вх | Вход D/T | CLK | Async CLR | Async PRE | Статус GSR |')
    out_lines.append('|---|---|---|---|---|---|---|---|---|---|---|')

    warns, unplaced = [], []
    order = sorted(ffs, key=lambda r: (0 if r['section'] == 'mapped' else 1,
                                       loc_key(info.get(norm(r.get('Q', '')), {}).get('loc', ''))))
    for i, r in enumerate(order, 1):
        q = r['Q']
        meta = info.get(norm(q), {})
        if not meta and re.search(r'_I\(', q):
            # выходной регистр: Q-порт сидит на внутреннем D_I(k), пад = X(k)
            q2 = re.sub(r'_I\(', '(', q)
            meta = info.get(norm(q2), {})
            if meta:
                q = q2
        loc = meta.get('loc', '') or ('НЕ РАЗМЕЩЁН' if r['section'] == 'unmapped' else '')
        pin = meta.get('pin', '')
        pts = '%s/%s' % (meta.get('pts', '-'), meta.get('inps', '-'))
        clk_s, clk_c = cls_port(r.get('C', '—'), gsr, gck, 'C')
        clr_s, clr_c = cls_port(r.get('CLR', '—'), gsr, gck, 'CLR')
        pre_s, pre_c = cls_port(r.get('PRE', '—'), gsr, gck, 'PRE')
        if r['prim'] == 'LDCP':
            clk_s = 'гейт %s' % r.get('G', '')
        if r['section'] == 'unmapped':
            status = '**НЕ РАЗМЕЩЁН**'
            unplaced.append(q)
        elif clr_c == 'warn' or pre_c == 'warn':
            status = '**ЛОКАЛЬНЫЙ** (%s/%s)' % (clr_s, pre_s)
            warns.append('%s: %s/%s' % (q, clr_s, pre_s))
        elif clr_s.startswith('GSR') or pre_s.startswith('GSR'):
            status = 'ok GSR'
        else:
            status = '**НЕТ асинхр.** (только INIT)'
            warns.append('%s: без асинхронного сброса/установки' % q)
        dt = r.get('D', r.get('T', r.get('G', '')))
        dt_s = '`%s`' % dt if len(dt) <= 28 else '`%s…' % dt[:27]
        out_lines.append('| %d | `%s` | %s | %s | %s | %s | %s | %s | %s | %s | %s |'
                         % (i, q, r['prim'], loc or '—', pin or '—', pts, dt_s,
                            clk_s, clr_s, pre_s, status))

    out_lines.append('')
    n_gsr = sum(1 for r in order if r['section'] == 'mapped'
                and (norm(r.get('CLR', '')) == norm(gsr or '?')
                     or norm(r.get('PRE', '')) == norm(gsr or '?')))
    out_lines.append('**Итог:** всего %d; на GSR-сбросе/установке %d; '
                     'с локальным/без асинхронного управления %d; не размещено %d.'
                     % (len(ffs), n_gsr, len(warns), len(unplaced)))
    for w in warns:
        out_lines.append('- WARN: %s' % w)
    for u in unplaced:
        out_lines.append('- ERROR: не размещён: %s' % u)
    out_lines.append('')
    return len(ffs), n_gsr, warns, unplaced

def main():
    ap = argparse.ArgumentParser(description='Аудит триггеров фити-отчёта cpldfit (GSR/GCK/CLR/PRE)')
    ap.add_argument('reports', nargs='+', help='.rpt файлы cpldfit')
    ap.add_argument('-o', '--out', help='записать сводку в файл (markdown)')
    args = ap.parse_args()
    out = []
    for path in args.reports:
        audit(path, out)
    text = '\n'.join(out)
    print(text)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
        print('(записано: %s)' % args.out, file=sys.stderr)

if __name__ == '__main__':
    main()
