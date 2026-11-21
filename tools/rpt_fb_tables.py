#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rpt_fb_tables.py — парсер фити-отчёта Xilinx cpldfit (XC9500) для retro_pcld_top.

Разбирает .rpt и печатает по каждому FB (FB1..FB6):
  - входные линии ФБ (с классификацией: pin / локальный фидбек / узел другого ФБ),
  - МЦ-таблицу (сигнал, ПТ, ассоциированный пад, потребители),
  - формулы промежуточных узлов (таблица F ниже — наполнена по уравнениям v37F-11;
    при изменении RTL дополнить/поправить записи, uncredited узлы печатаются как
    'см. уравнение rpt').

Использование:
    python3 tools/rpt_fb_tables.py <путь/к/retro_pcld_top.rpt> [-o выход.md]

Зависимости: только Python 3 (stdlib). Источник данных: секции
'Inputs/Outputs/Buried Nodes', MC-таблицы FB1..FB6 и 'Equations' отчёта.
"""
import re
import sys

FB = ['FB1', 'FB2', 'FB3', 'FB4', 'FB5', 'FB6']

# --- формулы узлов (по уравнениям cpldfit, v37F-11; `·` И, `+` ИЛИ, `!` НЕ) ---
F = {
 'io_wr_tx':'!bit_cnt0·!bit_cnt1·!bit_cnt2·!bit_cnt3·!cpu_rst_r·io_wr·FC_0_  →  строб загрузки UART (только при bit_cnt=0)',
 'io_wr':'IOM·!WRn·FC_1_  →  общий строб «запись IO-порта»',
 'bus_ld_t1':'!FFd2·!FFd3·FFd1·ALE·!IOM  →  T1H+ALE, цикл памяти: захват шины (чтение ОЗУ)',
 'bus_ld_t2':'FFd2·!FFd3·FFd1·!WRn  →  T2-фаза записи: D(k)←A(k).PIN',
 'in_wb':'FFd3 + FFd2·!FFd1  →  фаза выдачи на шину D (writeback)',
 'cpu_rst_r':'FD: D=RESET_IN·!rst_press  →  сброс-домен логики (async CLR большинства регистров)',
 'baud_tick':'!bc0·!bc1·!bc2·bc3·bc4  →  тик скорости UART (baud_cnt=24-я фаза)',
 'rst_sync':'FD: D=rst_meta  →  2-я ступень синхронизации пина RST',
 'rst_meta':'FD: D=RST (GSR-пин P1)  →  1-я ступень синхронизации RST',
 'rd_drive':'FFd2·!FFd3·FFd1·rd_seen·!ALE·!RDn  →  фаза выдачи данных порта на AD-шину',
 'rd_seen':'FT  →  «порты читались» (гасится fsm_rddone=rd_seen·RDn)',
 'wr_seen':'FT  →  «порты писались» (гасится fsm_wrdone=wr_seen·WRn)',
 'fsm_wrdone':'wr_seen·WRn', 'fsm_rddone':'rd_seen·RDn',
 'rst_press':'FT: T=(rst_press·!rst_sync + !rst_press·rst_sync) при полном окне rst_win и !X1·!t0_q  →  переворот фазы сброса',
 'kbcol_wr06':'!al0·al1·al2·io_wr  →  запись порта 06h (столбцы клавиатуры)',
 'seg7const':"seg(7)='1' — константа (бит не используется)",
 'X1':'FT: T=t0_q  →  счётчик-делитель осциллятора X1(P68)',
 't0_q':"FT: T='1'  →  тоггл-такт осциллятора",
 'TX':'FD (PRE=cpu_rst_r): D=TX·!baud_tick·!io_wr_tx + baud_tick·shreg1·!io_wr_tx;  io_wr_tx→D=0 (старт-бит)',
 'shreg1':'FD: D=io_wr_tx·A0 + baud_tick·shreg2·!io_wr_tx + !baud_tick·shreg1·!io_wr_tx',
 'shreg3':'FD: D=io_wr_tx·A2 + baud_tick·shreg4·!io_wr_tx + !baud_tick·shreg3·!io_wr_tx',
 'shreg4':'FD: D=io_wr_tx·A3 + baud_tick·shreg5·!io_wr_tx + !baud_tick·shreg4·!io_wr_tx',
 'shreg5':'FD: D=io_wr_tx·A4 + baud_tick·shreg6·!io_wr_tx + !baud_tick·shreg5·!io_wr_tx',
 'shreg6':'FD: D=io_wr_tx·A5 + baud_tick·shreg7·!io_wr_tx + !baud_tick·shreg6·!io_wr_tx',
 'shreg7':'FD: D=io_wr_tx·A6 + baud_tick·shreg8·!io_wr_tx + !baud_tick·shreg7·!io_wr_tx',
 'shreg8':'FD (комплемент-форма): 3 случая → загрузка=A7, сдвиг=1 (инжекция), hold=shreg8',
 'RESET_IN':'FD: D=RESET_IN·!rst_press + rst_win0·rst_win1·rst_win2·CLKOUT·!clkout_d·!rst_press·!rst_sync  →  выход сброса 8085',
 'RST75':'FD: D=baud_tick·!X1·!t0_q  →  выход RST 7.5',
 'SND':'FD: D=SND·!$435 + A4·$435  →  выход SND (запись порта 01h, бит 4)',
 'SID':'проходной: SID = RX (пин RX → пин SID)',
 'addr_latch':'FD: D=al(k)·!$433 + A(k).PIN·$433, где $433=!FFd2·!FFd3·FFd1·ALE  →  демультиплексор адреса (захват при ALE)',
 'D_wr':'FD: D=bus_ld_t1·D(k).PIN + D(k)·!t1·!t2 + !t1·t2·A(k).PIN; OE пада=in_wb  →  защёлка данных шины',
 'D_stub':'D_I(k)=D(k)_BUFR (реплика, UNMAPPED); OE пада=in_wb',
 'A_pad':'A_I(k)=addr_latch(k)·!rd_drive + row?(k)·$4 + D(k)·rd_drive·!$4; OE пада=rd_drive+in_wb  →  AD-шина 8085 (двунапр.)',
 'col':'FD: D=col(k)·!kbcol_wr06 + A(4+k).PIN·kbcol_wr06  →  столбцы клавиатуры (порт 06h)',
 'seg':'FD (PRE=cpu_rst_r): D=!A(k).PIN·$434 + seg(k)·!$434  →  сегменты (инверсия, порт 00h)',
 'dig':'FD: D=!A(k).PIN·$435 + dig(k)·!$435  →  разряды индикации (порт 01h)',
 'CS_n':'(IOM + !A15)·!in_wb, пад актив 0  →  выбор ОЗУ',
 'CSr_n':'IOM + A15, актив 0  →  выбор второго чипа',
 'WE_n':'!(FFd3·(FFd2+!FFd1))  →  /WE (актив 0 в фазах записи)',
 'OE_n':'!((!FFd2·!FFd3)·(in_wb + !IOM·A15))  →  /OE',
 'OEr_n':'!FFd2·!FFd3·!IOM·!A15, актив 0  →  /OE второго чипа',
 'bit_cnt':'счётчик бит UART 0..9 (D/T-уравнения rpt)',
 'baud_cnt':'счётчик скорости UART 0..24 (D/T-уравнения rpt)',
 'tmr_cnt':'счётчик таймера (T=baud_tick·!X1·!t0_q [·tmr_cnt0])',
 'rst_win':'FT  →  окно сброса (3 бита, тактированный счёт нажатия)',
 'state_FSM':'FD/FT  →  биты FSM шинных фаз',
 'clkout_d':'FD: D=CLKOUT  →  задержанная копия CLKOUT',
 'OpT4':'al0·al1·!al2·IOM  →  IO-декод «порт 03h» (строки клавиатуры на AD)',
 'OpT414':'!rst_press·!rst_sync',
 'OpT433':'!FFd2·!FFd3·FFd1·ALE  →  строб захвата адреса (T1H+ALE)',
 'OpT434':'!al0·!al1·!al2·io_wr  →  запись порта 00h (сегменты)',
 'OpT435':'al0·!al1·!al2·io_wr  →  запись порта 01h (разряды+SND)',
 'OpT439':'bc0·bc1·bc2·bc3  (baud_cnt(3:0)=15)',
 'OpT442':'rst_press·rst_sync + RESET_IN·!rst_press·!rst_sync',
 'A_7_IOBUFE':'!rd_drive·!in_wb  →  /OE трёхсостояний AD-шины (OE=rd_drive+in_wb)',
}

def F_of(name):
    for pfx, key in (('$OpTx$FX_DC$433', 'OpT433'), ('$OpTx$FX_DC$434', 'OpT434'),
                     ('$OpTx$FX_DC$435', 'OpT435'), ('$OpTx$FX_DC$439', 'OpT439'),
                     ('$OpTx$FX_DC$442', 'OpT442'), ('$OpTx$FX_DC$414', 'OpT414'),
                     ('$OpTx$FX_DC$4', 'OpT4')):
        if name.startswith(pfx):
            return F[key]
    if name.startswith('seg<7'):
        return F['seg7const']
    if name.startswith('seg'):
        return F['seg']
    if name.startswith('dig'):
        return F['dig']
    if name.startswith('col'):
        return F['col']
    if name.startswith('addr_latch'):
        return F['addr_latch']
    if re.match(r'^D<\d>?$', name) or re.match(r'^D\(\d\)$', name):
        return F['D_wr']
    if name.startswith('D<4') or name.startswith('D<5') and 'BUFR' in name:
        return F['D_stub']
    if re.match(r'^A<\d>?$', name):
        return F['A_pad']
    if name.startswith('baud_cnt'):
        return F['baud_cnt']
    if name.startswith('bit_cnt'):
        return F['bit_cnt']
    if name.startswith('tmr_cnt'):
        return F['tmr_cnt']
    if name.startswith('rst_win'):
        return F['rst_win']
    if name.startswith('state_FSM'):
        return F['state_FSM']
    if name.startswith('A_7_IOBUFE'):
        return F['A_7_IOBUFE']
    if name.startswith('shreg'):
        m = re.match(r'^shreg<(\d)>$', name) or re.match(r'^shreg\((\d)\)$', name)
        if m and ('shreg' + m.group(1)) in F:
            return F['shreg' + m.group(1)]
        return 'FD: сдвиг/загрузка (уравнение rpt)'
    if name in F:
        return F[name]
    return 'см. уравнение rpt'


def parse_mcs(seg):
    """MC-таблица FB: склейка двухстрочных имён, маркеры 1<- / \\/1."""
    out, buf = [], ''
    for l in seg.split('\n'):
        t = l.strip()
        if not t:
            continue
        if t.startswith(('Signal ', 'Name ', '***', 'Number of', 'Legend')) or \
          'Total   Imp' in l or t.startswith('Pt'):
            continue
        if re.search(r'FB\d_\d+', t):
            row = (buf + ' ' + t).strip() if buf else t
            buf = ''
            m = re.match(r'^(.*?)\s+(\d+)\s+((?:\\/\d+|\d+<-|\d+))\s+((?:\\/\d+|\d+<-|\d+))\s+'
                         r'(\d+)\s+(FB\d_\d+)\s*(.*)$', row)
            if not m:
                continue
            name, tot, imp, exp, unused, loc, tail = m.groups()
            tail = tail.strip()
            pin = use = ''
            if tail.startswith('(b)'):
                rest = tail[3:].strip()
                if rest and 'I' in rest:
                    use = rest.split()[1] if len(rest.split()) > 1 else rest.split()[0]
            elif tail:
                p = tail.split()
                if p and p[0].isdigit():
                    pin, p = p[0], p[1:]
                if p:
                    use = p[-1]
            if name == '(unused)':
                out.append((loc, None, int(tot), pin, use))
            else:
                out.append((loc, name, int(tot), pin, use))
        else:
            if re.match(r'^[A-Za-z_$<(/]', t) or t == 'A_7_IOBUFE/A_7_IOBUFE_TRST':
                buf = (buf + ' ' + t).strip()
    return out


def line_list(seg):
    k = seg.find('Signals Used by Logic in Function Block')
    seg2 = seg[k:k + 3200]
    cut = seg2.find('0----+----')
    if cut > 0:
        seg2 = seg2[:cut]
    return re.findall(r'\d+:\s+(\S+)', seg2)


def main():
    args = sys.argv[1:]
    out_path = None
    rpt = None
    i = 0
    while i < len(args):
        if args[i] == '-o':
            out_path = args[i + 1]; i += 2
        else:
            rpt = args[i]; i += 1
    if not rpt:
        sys.exit(__doc__)
    s = open(rpt, encoding='utf-8', errors='replace').read()

    # сводка и статус
    m = re.search(r'Fitting Status:\s*(\S+)', s)
    print(f'# {rpt}: Fitting Status {m.group(1) if m else "?"}')
    m = re.search(r'Macrocells\s+Product Terms\s+Function Block\s+Registers\s+Pins\s*\n'
                  r'Used/Tot\s+Used/Tot\s+Inps Used/Tot\s+Used/Tot\s+Used/Tot\s*\n(.*)', s)
    if m:
        print('Сводка:', ' '.join(m.group(1).split()))

    pos = [s.find(f'*** {f}  ') for f in FB] + [s.find('*******************************  Equations')]
    pin_in, pin_out = {}, {}
    i = s.find('** Inputs **')
    if i < 0:
        i = s.find('** 30 Inputs **')
    for m in re.finditer(r'^(\S+)\s+(FB\d_\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s*$', s[i:i + 1800], re.M):
        pin_in[m.group(2)] = (m.group(1), m.group(3), m.group(5))
    i = s.find('** Outputs **')
    if i < 0:
        i = s.find('** 43 Outputs **')
    for m in re.finditer(r'^(\S+)\s+\d+\s+\d+\s+(FB\d_\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s*$', s[i:i + 3200], re.M):
        pin_out[m.group(2)] = (m.group(1), m.group(3), m.group(5))

    homes, consumers, all_mcs = {}, {}, {}
    for n, f in enumerate(FB):
        seg = s[pos[n]:pos[n + 1]]
        all_mcs[f] = parse_mcs(seg)
        for loc, name, *_ in all_mcs[f]:
            if name:
                homes[name] = f
        for ln in line_list(seg):
            b = ln.replace('.PIN', '').replace('.LFBK', '')
            consumers.setdefault(b, set()).add(f)
    sig_pin = {}
    for sig, pin, use in pin_in.values():
        sig_pin[sig] = (pin, 'вход')
    for sig, pin, use in pin_out.values():
        sig_pin.setdefault(sig, (pin, use))

    lines_budget = {}
    for m in re.finditer(r'Number of function block inputs used/remaining:\s*(\d+)/(\d+)', s):
        pass  # точные пары печатаем ниже из секций FB
    out = []
    for n, f in enumerate(FB):
        seg = s[pos[n]:pos[n + 1]]
        mcs = all_mcs[f]
        lines = line_list(seg)
        used = sum(1 for r in mcs if r[1] is not None)
        mb = re.search(r'Number of function block inputs used/remaining:\s*(\d+)/(\d+)', seg)
        budget = f'{mb.group(1)}/{mb.group(2)}' if mb else '?'
        out.append(f'\n## {f} — МЦ {used}/18, линии ФБ {budget} (в списке сигналов: {len(lines)})')
        out.append('### Входы (линии ФБ + локальные фидбеки)')
        out.append('| сигнал | источник | формула/роль (для узлов) |')
        out.append('|---|---|---|')
        seen = set()
        for ln in lines:
            b = ln.replace('.PIN', '').replace('.LFBK', '')
            if b in seen and ln.endswith('.PIN'):
                continue
            if ln.endswith('.PIN'):
                seen.add(b)
                out.append(f'| {ln} | **pin {b}** | прямой вход с двунаправленного пада |')
            elif ln.endswith('.LFBK'):
                out.append(f'| {ln} | узел этого же ФБ | локальный фидбек (линию ФБ не тратит) |')
            elif homes.get(b) == f:
                p = sig_pin.get(b)
                extra = f' (выход на пад P{p[0]})' if p and p[1] != 'вход' else ''
                out.append(f'| {b} | локальный сигнал ФБ{extra} | {F_of(b)} |')
            elif b in sig_pin and sig_pin[b][1] == 'вход':
                p = sig_pin[b]
                out.append(f'| {b} | **pin {b} (P{p[0]}, вход)** | входной пин |')
            elif b in sig_pin:
                p = sig_pin[b]
                h = homes.get(b, '?')
                out.append(f'| {b} | выход пада {b} (P{p[0]}), регистр в {h} | {F_of(b)} |')
            elif b.startswith('FC_'):
                out.append(f'| {b} | внутренняя сеть фиттера | декод-конъюнкция (в rpt не раскрыта) |')
            else:
                src = homes.get(b)
                tag = f'узел/регистр из {src}' if src else '**UNMAPPED-узел (ФБ нет)**'
                out.append(f'| {b} | {tag} | {F_of(b)} |')
        out.append('### Выходы (МЦ ФБ)')
        out.append('| МЦ | сигнал | пад МЦ | формула / что несёт |')
        out.append('|---|---|---|---|')
        for loc, name, tot, pin, use in mcs:
            if name is None:
                sig = pin_in.get(loc)
                if sig:
                    out.append(f'| {loc} | — (МЦ свободна) | **pin {sig[0]} (P{sig[1]}, {sig[2]})** | входной пад, МЦ не занята |')
                else:
                    out.append(f'| {loc} | (unused) | {"P" + pin + " " + use if pin else "buried"} | свободна |')
                continue
            if loc in pin_in and use in ('I', 'GCK', 'GSR'):
                pi = pin_in[loc]
                pad = f'пин также **{pi[0]} (P{pi[1]}, вход {pi[2]})**'
            elif loc in pin_out:
                po = pin_out[loc]
                pad = f'**pin {po[0]} (P{po[1]}, {po[2]})**'
            elif pin and use in ('O', 'I/O'):
                pad = f'**pin P{pin} ({use})**'
            elif pin:
                pad = f'пад P{pin} не используется ({use or "(b)"})'
            else:
                pad = 'buried'
            cons = sorted(consumers.get(name, set()) - {f})
            shared = loc in pin_in and use in ('I', 'GCK', 'GSR')
            tail = (f'  [читают: {",".join(cons)}]'
                    if cons and (pad == 'buried' or shared or (pin and use not in ('O', 'I/O'))) else '')
            out.append(f'| {loc} | {name} ({tot}ПТ) | {pad} | {F_of(name)}{tail} |')
    txt = '\n'.join(out)
    print(txt)
    if out_path:
        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write(txt + '\n')


if __name__ == '__main__':
    main()
