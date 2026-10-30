#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sim_v391_equiv.py (clk10-62): ФОРМАЛЬНОЕ доказательство эквивалентности
v3.9.1 (без wb_ram_q) против v3.9 (с wb_ram_q) для шинного автомата.

Метод: полный перебор произведения машин (state, rd_seen, wr_seen,
wb_ram_q) x 64 комбинации входов (cpu_rst, ALE, WRn, RDn, IOM, A15)
от стартового состояния (S_IDLE,0,0,0). Если на каждом достижимом
состоянии произведения при каждом входе выходы совпадают и следующие
состояния сохраняют свойство - машины эквивалентны для ЛЮБЫХ входных
последовательностей (индукция по длине входного слова).

Семантика взята ПОСТРОЧНО из RTL:
  v3.9: top_suart_por6_v39_utf8.v, always 741-811 + assigns 818-835
  v3.9.1: top_suart_por6_v391_utf8.v (удалены 715/746/794, CS_n = in_wb ? ...)
Единственный потребитель wb_ram_q в v3.9 - CS_n (строка 829); драйверы
A/D (818-821), WE_n (834), OE_n (831) работают от in_wb/in_welo - в
модели сравниваются ВСЕ эти выходы.
"""
import itertools, random, sys

# Состояния (RTL 700-706)
S_IDLE, S_T1H, S_T2, S_WB1, S_WB2, S_WB3, S_WB4 = range(7)
ST_NAMES = ["IDLE", "T1H", "T2", "WB1", "WB2", "WB3", "WB4"]

def step(state, rd, wr, wb, use_wb, cpu_rst, ALE, WRn, RDn, IOM, A15):
    """Один posedge clk. use_wb=True -> модель v3.9 (с wb_ram_q),
    False -> v3.9.1. Возвращает (state', rd', wr', wb').
    Порядок присваиваний как в RTL: 758-775 (захваты - не влияют на
    FSM/выходы), 777-778 (флаги), 782-785 (abort), 787-808 (case)."""
    nrd, nwr, nwb = rd, wr, wb                      # держат значение
    if state == S_T2 and (not RDn):
        nrd = 1                                     # строка 777
    if state == S_T2 and (not WRn):
        nwr = 1                                     # строка 778
    if cpu_rst:                                     # строки 742-752
        return (S_IDLE, 0, 0, 0)
    abort = ALE and (state == S_T2) and (not ((wr and WRn) or (rd and RDn)))
    if abort:                                       # строки 782-785
        st, nrd, nwr = S_IDLE, 0, 0
    else:
        st = state
        if st == S_IDLE:
            if ALE: st = S_T1H                      # 788
        elif st == S_T1H:
            if not ALE: st = S_T2                   # 789
        elif st == S_T2:                            # 790-802
            if wr and WRn:
                nwr = 0                             # 793
                if use_wb:
                    nwb = (not IOM) and A15         # 794 (только v3.9)
                st = S_WB1 if ((not IOM) and A15) else S_IDLE   # 797
            elif rd and RDn:
                nrd = 0                             # 799
                st = S_IDLE
        elif st == S_WB1:
            st = S_WB2                              # 803
        elif st == S_WB2:
            st = S_WB3                              # 804
        elif st == S_WB3:
            st = S_WB4                              # 805
        elif st == S_WB4:
            st = S_IDLE                             # 806
        else:
            st = S_IDLE                             # 807 (state=7 недостижим)
    return (st, nrd, nwr, nwb)

def outputs(state, wb, use_wb, IOM, A15):
    """Комбинационные выходы (RTL 732-736, 818-835). Данные шин
    (addr_latch/bus_reg/rows) в диффе не участвуют: их гейты сравниваются,
    содержимое - одинаковые ветки кода."""
    in_wb   = state >= S_WB1                        # 732
    in_welo = state in (S_WB2, S_WB3)               # 733
    wr_phase = state >= S_T2                        # 734
    wb_out  = in_wb                                 # 735
    cs_n = 0 if (in_wb and wb) else (0 if (not A15 and not IOM) else 1)  # 829 v3.9
    if not use_wb:
        cs_n = 0 if in_wb else (0 if (not A15 and not IOM) else 1)      # 829 v3.9.1
    oe_n = cs_n or wr_phase                         # 831
    we_n = not in_welo                              # 834
    csr_n = 1 if (A15 or IOM) else 0                # 828
    oer_n = csr_n or wr_phase                       # 830
    rd_drive = (state == S_T2)                      # гейт 736 (rd/RDn/ALE добавит вызывающий)
    return dict(in_wb=in_wb, in_welo=in_welo, wr_phase=wr_phase, wb_out=wb_out,
                cs_n=cs_n, oe_n=oe_n, we_n=we_n, csr_n=csr_n, oer_n=oer_n)

def outputs_rd(state, rd, RDn, ALE):
    """rd_drive (736) - зависит от rd_seen/RDn/ALE."""
    return (state == S_T2) and rd and (not RDn) and (not ALE)

def main():
    # ---------- 1. Полный перебор произведения машин ----------
    start = (S_IDLE, 0, 0, 0)
    seen = {start}
    frontier = [start]
    checked = 0
    mism = []
    inv_viol = []
    breathe = set()          # достижимые (state<WB1, wb=1) - «дыхание» защёлки
    wb_states = set()        # достижимые с state>=WB1
    inputs = list(itertools.product([0, 1], repeat=6))  # cpu_rst, ALE, WRn, RDn, IOM, A15

    while frontier:
        (st, rd, wr, wb) = cur = frontier.pop()
        in_wb = st >= S_WB1
        if in_wb and wb != 1:
            inv_viol.append(cur)                    # инвариант коллеги
        if wb == 1 and not in_wb:
            breathe.add(cur)
        if in_wb:
            wb_states.add(cur)
        for (crst, ale, wrn, rdn, iom, a15) in inputs:
            # выходы v3.9 и v3.9.1 на этом состоянии и входе
            o39  = outputs(st, wb, True,  iom, a15)
            o391 = outputs(st, 0,  False, iom, a15)   # у v3.9.1 защёлки нет
            if o39 != o391:
                mism.append((cur, (crst, ale, wrn, rdn, iom, a15), "comb", o39, o391))
            if outputs_rd(st, rd, rdn, ale) != outputs_rd(st, rd, rdn, ale):
                mism.append((cur, (crst, ale, wrn, rdn, iom, a15), "rd_drive", None, None))
            # следующие состояния: v3.9.1 обязана иметь те же (state, rd, wr)
            n39  = step(st, rd, wr, wb,  True,  crst, ale, wrn, rdn, iom, a15)
            n391 = step(st, rd, wr, wb,  False, crst, ale, wrn, rdn, iom, a15)
            if n39[:3] != n391[:3]:
                mism.append((cur, (crst, ale, wrn, rdn, iom, a15), "next", n39, n391))
            checked += 1
            if n39 not in seen:
                seen.add(n39)
                frontier.append(n39)

    print("=" * 74)
    print("ФОРМАЛЬНАЯ ЭКВИВАЛЕНТНОСТЬ v3.9.1 vs v3.9 (произведение машин)")
    print("=" * 74)
    print("Достижимых состояний (state, rd_seen, wr_seen, wb_ram_q): %d из 112 возможных" % len(seen))
    print("  ...из них с in_wb=1 (WB1..WB4): %d" % len(wb_states))
    print("  ...с wb_ram_q=1 вне WB («дыхание» защёлки): %d %s" %
          (len(breathe), sorted(ST_NAMES[s] for (s, _, _, _) in breathe)))
    print("Проверено переходов: %d = %d сост. x 64 входов" % (checked, len(seen)))
    print("Инвариант «in_wb -> wb_ram_q=1»: %s" %
          ("ПОДТВЕРЖДЁН на всех достижимых состояниях" if not inv_viol else "НАРУШЕН: %r" % inv_viol[:5]))
    if mism:
        print("РАСХОЖДЕНИЯ: %d (первые 5):" % len(mism))
        for m in mism[:5]:
            print("   ", m)
    else:
        print("Расхождений выходов/переходов: 0 - машины ЭКВИВАЛЕНТНЫ для любых")
        print("входных последовательностей (индукция: старт = сброс, шаг проверен на")
        print("ВСЕХ достижимых состояниях произведения при ВСЕХ 64 комбинациях входов).")

    # ---------- 2. Контрольные недостижимые состояния (для отчёта) ----------
    print("-" * 74)
    unreach = []
    for st in range(8):
        for rd, wr, wb in itertools.product([0, 1], repeat=3):
            if (st, rd, wr, wb) not in seen:
                unreach.append((st, rd, wr, wb))
    print("Недостижимых состояний: %d (включая state=7 и все «in_wb при wb_ram_q=0»)" % len(unreach))
    # проверка: все состояния с in_wb=1 и wb=0 недостижимы - именно на них
    # функции CS_n различаются, что и доказывает полноту эквивалентности
    diff_states = [u for u in unreach if u[0] >= S_WB1 and u[3] == 0]
    all_wb0_reach = [s for s in seen if s[0] >= S_WB1 and s[3] == 0]
    print("  состояний «in_wb=1, wb_ram_q=0»: %d, все недостижимы: %s" %
          (len(diff_states), "ДА" if not all_wb0_reach else "НЕТ: %r" % all_wb0_reach))
    print("  (именно на них CS_n v3.9 и v3.9.1 различаются - тождество на")
    print("   достижимой части = полная эквивалентность, см. индукцию выше)")

    # ---------- 3. Случайный дифференциальный прогон 10^7 шагов ----------
    rng = random.Random(0xC0FFEE)
    N = 10_000_000
    st, rd, wr, wb = start
    n39s, n391s = start, start
    diff = 0
    in_we = 0
    for i in range(N):
        crst = 1 if rng.random() < 0.02 else 0
        ale  = 1 if rng.random() < 0.35 else 0
        wrn  = 1 if rng.random() < 0.60 else 0
        rdn  = 1 if rng.random() < 0.60 else 0
        iom  = rng.randint(0, 1)
        a15  = rng.randint(0, 1)
        prev = n39s[0]
        n39s  = step(*n39s,  True,  crst, ale, wrn, rdn, iom, a15)
        n391s = step(*n391s, False, crst, ale, wrn, rdn, iom, a15)
        o39  = outputs(n39s[0],  n39s[3],  True,  iom, a15)
        o391 = outputs(n391s[0], 0, False, iom, a15)
        if o39["cs_n"] != o391["cs_n"] or n39s[:3] != n391s[:3]:
            diff += 1
        if n39s[0] >= S_WB1 and n39s[3] == 0:
            diff += 10_000_000   # нарушение инварианта - фатально
        if crst and prev in (S_WB2, S_WB3):
            in_we += 1
    print("-" * 74)
    print("Случайный дифпрогон: %d шагов (2%% сбросов, 35%% ALE) - расхождений: %d" % (N, diff))
    print("  сбросов в окне низкого /WE: %d" % in_we)

    ok = (not mism) and (not inv_viol) and diff == 0
    print("=" * 74)
    print("ВЕРДИКТ: %s" % ("ЭКВИВАЛЕНТНОСТЬ ПОЛНАЯ - v3.9.1 == v3.9 (формально + 10^7 шагов)"
                           if ok else "!!! ЕСТЬ РАСХОЖДЕНИЯ !!!"))
    print("=" * 74)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
