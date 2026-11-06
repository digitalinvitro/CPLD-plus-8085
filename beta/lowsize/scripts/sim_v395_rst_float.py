#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Симуляция дефекта «сброс кнопкой не восстанавливает комплекс, только
выкл-вкл питания» (жалоба владельца 11-6, v3.9.5, оба фита ON/OFF).

ИСТОЧНИК МОДЕЛИ
---------------
Поведение взято из RTL top_suart_por6_v395_utf8.v (верифицирован
диффсимами проекта: tb_v395_diff 10595 циклов 0 расхождений,
tb_por_fuzz 0/100 грязи) - НЕ из печати .rpt: печать cpldfit теряет
инверсию макроячейки (прецеденты: шапка RTL v3.9.2 «терял полярность
декодов в фятах 10-22»; в v395-fit1 .rpt так напечатаны как минимум
cnt_T(0), cnt_T(1) (восстанавливаются до mod-7 только с инверсией -
ресурсные счётчики 1ПТ/3вх и 2ПТ/3вх сходятся лишь так), X1/X2 (XOR
разорван переносом строки) и WE_n (печать даёт строб в WB3/WB4, RTL -
в WB2/WB3)). Из .rpt взяты только INIT триггеров (por_sh=F, por_run=1,
cnt=000, x1_n=0, логика шины в сбросе: seg=FF, dig=F, TX=1) и анатомия
сброса фита: GSR НЕ свёлся (fallback) - 40 асинхронных PTC-сбросов
CLR/PRE = NOT RESET_IN = cpu_rst = por_run | RST, разводимых через
5 импортов RESET_IN (FB1/2/3/5/6).

ДЕФЕКТ, КОТОРЫЙ СТРОИТСЯ
------------------------
Цепь RST платы (SCHEMATIC.md 514/586, Task 25): SW20.1->U1.1,
R2 240->VCC на SW20.2, SW20.3/4->GND; ЗАМЕР владельца: покой ~0 В,
нажатие ~+5 В. Единственная совместимая трактовка: нажатие подаёт +5
через R2 240, В ПОКОЕ RST НЕ ПОДКЛЮЧЕН НИ К ЧЕМУ (сеть RST = {SW20.1,
U1.1}, подтяжки вниз НЕТ). Отпускание кнопки = медленный спад с +5
через порог входа (десятки мкс). Всё время спада:
  - 40 цепочек асинхронного сброса висят МИД-РЕЙЛОМ -> ячейки теряют
    помехозащиту, часть переворачивается (модель: P_FLIP за полутакт);
  - RESET_IN (U1.84 -> cpu36 RESET IN~, прямая, без RC) спадает тем же
    фронтом -> момент отпускания CPU разнесён с моментом фактического
    снятия сброса логики (разные пороги) на скос до долей времени спада.
Питание обходит RST целиком: por_run INIT=1 держит cpu_rst=1 с t=0 и
снимает его ЧИСТЫМ регистровым фронтом - потому «только по питанию».

СЦЕНАРИИ (по 20 сидов)
----------------------
  A. por             - питание: эталон чистого старта v3.9.5.
  B. btn_fast        - кнопка с быстрым фронтом = плата с подтяжкой
                       RST 10к на GND (предлагаемый фикс).
  C. float_cpufirst  - текущая плата: CPU отпускается РАНЬШЕ снятия
                       сброса логики (худший случай).
  D. float_cpulate   - текущая плата: CPU отпускается ПОЗЖЕ (FSM живёт
                       в окне на плавающей шине CPU - механизм v3.9.3).
  E. hardened        - тот же плавающий спад + хардренинг RTL v3.9.6:
                       RST -> 3FF-синхронизатор -> квалификатор 6 тактов,
                       RESET_IN - РЕГИСТР (чистый фронт CPU в любом случае).

МЕТРИКИ: dirt (регистров не в сбросовом значении к 1-й выборке CPU),
spurious_we (полутакты ложного /WE при выбранной памяти вне легальной
записи), contention (полутакты одновременного вождения A/AD сетей
CPLD и CPU), boot (первая выборка PC=0 обслужена верно).

РЕЗУЛЬТАТЫ (20-30 сидов, 11-6; полный лог: sim_v395_rst_float.log)
------------------------------------------------------------------------
  A. питание            BOOT 19-20/20, ложных /WE и контеншна НЕТ
  B. кнопка+подтяжка10к BOOT 19-20/20, ложных /WE и контеншна НЕТ
  C. кнопка-флот, CPU раньше: BOOT 7-10/20, ложные /WE у ~50%,
     контеншн A/AD у ~50% (первая выборка PC=0 обслуживается мусором)
  D. кнопка-флот, CPU позже:  BOOT 17-18/20 (FSM успевает дренировать)
  E. флот + хардренинг v3.9.6: BOOT 18-20/20, ложных /WE НЕТ
  Развёртка по спаду (сцена C, 30 сидов): 0 мкс -> 28/30; 2 мкс -> 13/30;
  10 мкс -> 10/30; 50 мкс -> 15/30 (насыщение) - деградация растёт с
  временем спада, нулевой спад эквивалентен питанию.

ВЕРДИКТ: цифровая логика v3.9.5 корректна (POR 1020 нс/4 сдвига,
мод-7, узор X1 - всё сошлось); дефект живёт в ЦЕПИ RST платы: без
подтяжки вниз отпускание кнопки оставляет мид-рейл на 40 асинхронных
сбросах и разносит моменты отпускания CPU и CPLD на время спада.
Фиксы: (1) ПЛАТА - подтяжка RST 10к на GND (закрывает Task 25);
(2) RTL v3.9.6 - синхронизатор+квалификатор+регистровый RESET_IN
(~4-6 МЦ из 29 свободных) как страховка на любом железе.

Запуск:  python3 sim_v395_rst_float.py
"""

import random

# ---------------------------------------------------------------- константы
HALF_NS = 20.0            # полутакт GCK 25 МГц
CPU_CLK_HALF = 14         # такт CPU (CLKOUT 3,57 МГц) = 280 нс = 14 полутактов
K_HALF = 16000            # длина прогона, полутактов (320 мкс)
CPU_WAKE_HALF = 42        # выход CPU из сброса после чистого фронта (~3 CLKOUT)
POR_MIN_HALF = 42         # 840 нс - норма POR
QUAL_K = 6                # квалификатор хардренинга, тактов
DWELL = 500               # плавающий спад: 500 полутактов = 10 мкс мид-рейла
P_FORCE = 0.10            # мид-рейл: за полутакт ячейка с P=10% дотягивается
P_FLIP = 0.02             # мид-рейл: за полутакт ячейка с P=2% переворачивается

# 40 сбрасываемых регистров фита (аудит v3.9.5); seg/dig/tx - PRE (1 в сбросе)
RESETTABLE = (['st0', 'st1', 'st2', 'rd_seen', 'wr_seen'] +
              ['al%d' % i for i in range(8)] +
              ['br%d' % i for i in range(8)] +
              ['seg%d' % i for i in range(8)] +
              ['dig%d' % i for i in range(4)] +
              ['col%d' % i for i in range(4)] +
              ['snd', 'tx', 'txpass'])


def _get(c, n):
    if n == 'st0':
        return c.state & 1
    if n == 'st1':
        return (c.state >> 1) & 1
    if n == 'st2':
        return (c.state >> 2) & 1
    if n[:2] == 'al':
        return c.al[int(n[2:])]
    if n[:2] == 'br':
        return c.br[int(n[2:])]
    if n[:3] == 'seg':
        return c.seg[int(n[3:])]
    if n[:3] == 'dig':
        return c.dig[int(n[3:])]
    if n[:3] == 'col':
        return c.col[int(n[3:])]
    return getattr(c, n)


def _set(c, n, v):
    if n == 'st0':
        c.state = (c.state & ~1) | (1 if v else 0)
    elif n == 'st1':
        c.state = (c.state & ~2) | ((1 if v else 0) << 1)
    elif n == 'st2':
        c.state = (c.state & ~4) | ((1 if v else 0) << 2)
    elif n[:2] == 'al':
        c.al[int(n[2:])] = v
    elif n[:2] == 'br':
        c.br[int(n[2:])] = v
    elif n[:3] == 'seg':
        c.seg[int(n[3:])] = v
    elif n[:3] == 'dig':
        c.dig[int(n[3:])] = v
    elif n[:3] == 'col':
        c.col[int(n[3:])] = v
    else:
        setattr(c, n, v)


def _rst_val(n):
    if n[:3] == 'seg' or n[:3] == 'dig' or n == 'tx':
        return 1
    return 0


# ------------------------------------------------------------ модель CPLD
class Chip(object):
    """Фитнетлист v3.9.5 по семантике RTL.

    hard=False - как прошито: 40 PTC-сбросов от узла cpu_rst =
                 por_run | RST; RESET_IN комбинационный.
    hard=True  - кандидат v3.9.6: RST через 3FF-синхронизатор,
                 квалификатор QUAL_K тактов, RESET_IN - регистр.
    """

    def __init__(self, hard=False):
        self.hard = hard
        self.por_shifts = 0
        self.por_run_end = None
        self.por_shifts_at_end = None
        self.reset_all()

    def reset_all(self):
        # INIT по .rpt / RTL
        self.cnt = [0, 0, 0]                 # cnt[0], cnt[1], cnt[2]
        self.x1n = 0
        self.por_sh = [1, 1, 1, 1]           # [sh0, sh1, sh2, sh3] = 0xF
        self.por_run = 1
        self.state = 0                       # S_IDLE
        self.rd_seen = 0
        self.wr_seen = 0
        self.al = [0] * 8                    # addr_latch
        self.br = [0] * 8                    # bus_reg
        self.seg = [1] * 8                   # seg_q = FF
        self.dig = [1] * 4                   # dig_q = F
        self.col = [0] * 4                   # kbcol_q
        self.snd = 0
        self.tx = 1
        self.txpass = 0
        self.sod_q = 0
        # хардренинг v3.9.6
        self.rsync = [0, 0, 0]
        self.clean = 0
        self.reset_in_r = 0

    # --------------------------------------------------------- комбинация
    def comb(self, rst_eff, env):
        """rst_eff - уровень RST для внутренней логики. env - окружение:
        ale, rdn, wrn, iom, a15 (линии CPU), a_driven (bool, CPU ведёт
        A/AD), a_cpu[8] (что ведёт CPU), d_mem[8] (данные памяти на D),
        row0..row4, sod."""
        c0, c1, c2 = self.cnt
        st = self.state
        ale, rdn, wrn = env['ale'], env['rdn'], env['wrn']
        iom, a15 = env['iom'], env['a15']

        # ---- делитель (дегарблен; семантика = mod-7 RTL)
        t0 = 0 if ((1 - c0) & c1 & c2) else 1            # c0|!c1|!c2
        t1 = 1 if (c0 | (c1 & c2)) else 0                # c0|c1*c2
        d2 = 1 if (((1 - c1) & c2) | (c0 & c1 & (1 - c2))) else 0
        eq0 = 1 - (c0 | c1 | c2)

        # ---- x1_n: FTCPE по negedge, T как в .rpt (чистая печать)
        x1n_t = 1 if ((self.x1n & (1 - c0) & (1 - c1) & c2) |
                      ((1 - self.x1n) & c0 & c1 & (1 - c2))) else 0

        # ---- POR-цепь (RTL: сдвиг {1'b0, por_sh[3:1]} по por_ce=x1_n)
        por_run_d = self.por_sh[0]

        # ---- сброс
        if self.hard:
            cpu_rst = 1 if (self.por_run | self.rsync[2]) else 0
            reset_in = self.reset_in_r
        else:
            cpu_rst = 1 if (self.por_run | rst_eff) else 0
            reset_in = 1 - cpu_rst

        # ---- FSM (RTL-семантика)
        in_wb = 1 if st >= 3 else 0                      # WB1..WB4
        in_welo = 1 if st in (4, 5) else 0               # /WE низ
        wr_phase = 1 if st >= 2 else 0                   # T2..WB4
        rd_drive = 1 if (st == 2 and self.rd_seen and not rdn and
                         not ale) else 0
        io_rd_kb = 1 if (iom and not self.al[2] and self.al[1] and
                         self.al[0]) else 0

        # ---- декоды памяти (RTL)
        csr_n = 1 if (a15 or iom) else 0
        cs_n = 0 if in_wb else (1 if (not a15 or iom) else 0)
        oer_n = 1 if (csr_n or wr_phase) else 0
        oe_n = 1 if (cs_n or wr_phase) else 0
        we_n = 0 if in_welo else 1

        # ---- драйвы шины
        # A/AD: CPU (T1-адрес, T2-запись) или CPLD (rd_drive: данные,
        # wb_out: addr_latch)
        cpld_a = None
        if rd_drive:
            if io_rd_kb:
                cpld_a = [0, 0, 0, self.row(4, env), self.row(3, env),
                          self.row(2, env), self.row(1, env),
                          self.row(0, env)]
            else:
                cpld_a = list(self.br)
        elif in_wb:
            cpld_a = list(self.al)
        a_oe = 1 if cpld_a is not None else 0
        d_oe = in_wb
        d_out = list(self.br) if d_oe else None

        # ---- RESET_IN для CPU (в hard - регистровый)
        outs = dict(cpu_rst=cpu_rst, reset_in=reset_in, a_oe=a_oe,
                    d_oe=d_oe, we_n=we_n, cs_n=cs_n, csr_n=csr_n,
                    oe_n=oe_n, oer_n=oer_n, rd_drive=rd_drive,
                    cpld_a=cpld_a, d_out=d_out,
                    x1=1 - (eq0 ^ self.x1n), x2=eq0 ^ self.x1n)

        # ---- next-D (сэмплы на фронте)
        nxt = dict(t0=t0, t1=t1, d2=d2, x1n_t=x1n_t, por_run_d=por_run_d)
        # захват повторным сэмплированием (RTL)
        if st == 1 and ale:                              # S_T1H && ALE
            nxt['al'] = list(env['a_cpu'])               # addr_latch <= A
            nxt['br'] = list(env['d_mem']) if not iom else None
        if st == 2 and not wrn:                          # S_T2 && !WRn
            nxt['br_w'] = list(env['a_cpu'])
            if iom:
                nxt['port'] = (self.al[2], self.al[1], self.al[0],
                               list(env['a_cpu']))
        # трекинг стробов
        nxt['rs_set'] = 1 if (st == 2 and not rdn) else 0
        nxt['ws_set'] = 1 if (st == 2 and not wrn) else 0
        # переходы
        if ale and st == 2 and not ((self.wr_seen and wrn) or
                                    (self.rd_seen and rdn)):
            nxt['state'] = 0                             # ALE обрывает T2
            nxt['rs_clr'] = nxt['ws_clr'] = 1
        else:
            if st == 0:
                nxt['state'] = 1 if ale else 0
            elif st == 1:
                nxt['state'] = 2 if not ale else 1
            elif st == 2:
                if self.wr_seen and wrn:
                    nxt['state'] = 3 if (not iom and a15 and
                                         not self.por_run) else 0
                    nxt['ws_clr'] = 1
                elif self.rd_seen and rdn:
                    nxt['state'] = 0
                    nxt['rs_clr'] = 1
                else:
                    nxt['state'] = 2
            elif 3 <= st <= 5:
                nxt['state'] = st + 1
            elif st == 6:
                nxt['state'] = 0
            else:
                nxt['state'] = 0
        return outs, nxt

    def row(self, i, env):
        return env.get('row%d' % i, 0)

    # --------------------------------------------------------- полушаг
    def half_step(self, k, rst_eff, env, midrail=None):
        """midrail = rnd: мид-рейл на 40 цепочках асинхронного сброса -
        за полутакт каждая ячейка с P_FORCE дотягивается до сбросового
        значения, с P_FLIP переворачивается; такт идёт своим ходом."""
        outs, nxt = self.comb(rst_eff, env)

        if midrail is not None:
            rnd = midrail
            for r in RESETTABLE:
                cur = _get(self, r)
                if rnd.random() < P_FLIP:
                    cur ^= 1
                if rnd.random() < P_FORCE:
                    cur = _rst_val(r)
                _set(self, r, cur)
        elif outs['cpu_rst']:
            for r in RESETTABLE:
                _set(self, r, _rst_val(r))

        if k % 2 == 0:                       # posedge clk (конвенция
            # sim_v392_div7: фронт на границе k->k+1 при k чётном)
            self.cnt[0] ^= nxt['t0']
            self.cnt[1] ^= nxt['t1']
            self.cnt[2] = nxt['d2']
            new_run = self.por_sh[0]         # por_run.D = СТАРЫЙ por_sh[0]
            if self.x1n:                     # por_ce = x1_n
                self.por_sh = [self.por_sh[1], self.por_sh[2],
                               self.por_sh[3], 0]
                self.por_shifts += 1
            if self.por_run == 1 and new_run == 0:
                self.por_run_end = k
                self.por_shifts_at_end = self.por_shifts
            self.por_run = new_run
            # FSM
            if 'al' in nxt:
                self.al = list(nxt['al'])
            if nxt.get('br') is not None:
                self.br = list(nxt['br'])
            if 'br_w' in nxt:
                self.br = list(nxt['br_w'])
            if 'port' in nxt:
                a2, a1, a0, data = nxt['port']
                sel = (a2 << 2) | (a1 << 1) | a0
                if sel == 0:
                    self.seg = list(data)
                elif sel == 1:
                    self.dig = list(data[:4])
                    self.snd = 1 if data[4] else 0
                elif sel == 2:
                    self.col = list(data[:4])
            if nxt.get('rs_clr'):
                self.rd_seen = 0
            elif nxt.get('rs_set'):
                self.rd_seen = 1
            if nxt.get('ws_clr'):
                self.wr_seen = 0
            elif nxt.get('ws_set'):
                self.wr_seen = 1
            self.state = nxt['state']
            self.sod_q = env.get('sod', 0)
            if self.hard:
                self.rsync = [rst_eff, self.rsync[0], self.rsync[1]]
                sp = self.rsync[2]
                if sp:
                    self.clean = 0
                    self.reset_in_r = 0
                else:
                    self.clean = min(self.clean + 1, QUAL_K)
                    if self.clean >= QUAL_K and self.por_run == 0:
                        self.reset_in_r = 1
        else:                                # negedge: x1_n - FTCPE (XOR)
            self.x1n ^= nxt['x1n_t']
        return outs

    def dirty(self):
        return sum(1 for r in RESETTABLE if _get(self, r) != _rst_val(r))


# ------------------------------------------------------------ модель CPU
class Cpu(object):
    """Абстрактный ВМ85А при CLKOUT 3,57 МГц (14 полутактов CPLD).
    В сбросе линии плавают (модель fuzz tb_por_fuzz). После снятия -
    монотонный паттерн циклов монитора:
      fetch ROM 0x00NN (IOM=0, A15=0, RD), write RAM 0x80NN (IOM=0,
      A15=1, WR), read IO 0x20 (IOM=1, A15=0, RD).
    T1 = CPU_CLK_HALF полутактов с ALE=1 и адресом на A/AD;
    T2/T3 - стробы; между циклами пауза 4 полутакта."""

    def __init__(self, rnd):
        self.rnd = rnd
        self.state = 'reset'
        self.wake = 0
        self.cycle = 0
        self.phase = 0
        self.first_fetch_lo = None
        self.first_fetch_k = None
        self.last = self.float_lines()

    def float_lines(self):
        return dict(ale=self.rnd.randint(0, 1), rdn=self.rnd.randint(0, 1),
                    wrn=self.rnd.randint(0, 1), iom=self.rnd.randint(0, 1),
                    a15=self.rnd.randint(0, 1), a_driven=False,
                    a_cpu=[self.rnd.randint(0, 1) for _ in range(8)],
                    cyc=-1)

    def step(self, k, in_reset):
        if in_reset:
            self.state = 'reset'
            out = self.float_lines()
            self.last = out
            return out, 'float'
        if self.state != 'run':
            if self.state != 'wake':
                self.wake = CPU_WAKE_HALF
            self.state = 'wake'
            self.wake -= 1
            if self.wake <= 0:
                self.state = 'run'
                self.cycle = 0
                self.phase = 0
            out = self.float_lines()
            self.last = out
            return out, 'float'
        cyc = self.cycle % 3
        iom = 1 if cyc == 2 else 0
        a15 = 1 if cyc == 1 else 0
        t1 = CPU_CLK_HALF
        if self.phase < t1:                       # T1: ALE=1, адрес на A/AD
            lo = {0: 0x00, 1: 0x00, 2: 0x20}[cyc]
            self.phase += 1
            if cyc == 0 and self.first_fetch_lo is None:
                self.first_fetch_lo = lo
                self.first_fetch_k = k
            out = dict(ale=1, rdn=1, wrn=1, iom=iom, a15=a15, a_driven=True,
                       a_cpu=[(lo >> i) & 1 for i in range(8)], cyc=cyc)
            self.last = out
            return out, 't1'
        self.phase += 1
        if self.phase < 2 * t1:                   # T2/T3: строб
            if cyc == 1:                          # запись: CPU ведёт данные
                out = dict(ale=0, rdn=1, wrn=0, iom=iom, a15=a15,
                           a_driven=True,
                           a_cpu=[1, 0, 1, 0, 1, 0, 1, 0], cyc=cyc)
            else:                                 # чтение: A/AD плавают
                out = dict(ale=0, rdn=0, wrn=1, iom=iom, a15=a15,
                           a_driven=False,
                           a_cpu=[self.rnd.randint(0, 1) for _ in range(8)],
                           cyc=cyc)
            self.last = out
            return out, 't2'
        self.phase += 1
        if self.phase < 3 * t1:                   # T4 (хвост цикла)
            out = dict(ale=0, rdn=1, wrn=1, iom=iom, a15=a15,
                       a_driven=False,
                       a_cpu=[self.rnd.randint(0, 1) for _ in range(8)],
                       cyc=cyc)
            self.last = out
            return out, 't4'
        self.phase = 0                            # конец цикла
        self.cycle += 1
        out = dict(ale=0, rdn=1, wrn=1, iom=iom, a15=a15, a_driven=False,
                   a_cpu=[self.rnd.randint(0, 1) for _ in range(8)],
                   cyc=cyc)
        self.last = out
        return out, 't4'


def make_env(cpu_out):
    """Окружение для comb: линии CPU; если CPLD ведёт A/AD - на сетях
    его данные (конфликт разрешается железом, считаем электрически
    'побеждает' тот, кто сильнее, для модели данных берём CPLD)."""
    env = dict(ale=cpu_out['ale'], rdn=cpu_out['rdn'], wrn=cpu_out['wrn'],
               iom=cpu_out['iom'], a15=cpu_out['a15'],
               a_cpu=list(cpu_out['a_cpu']), a_driven=cpu_out['a_driven'],
               d_mem=[0, 1, 1, 0, 0, 0, 0, 0],      # «код ROM» 0x61
               row0=0, row1=0, row2=0, row3=0, row4=0, sod=0)
    return env


# ------------------------------------------------------------ сцены
def run_scene(name, mode, seeds=20):
    res = []
    for seed in range(seeds):
        rnd = random.Random(9000 + seed)
        chip = Chip(hard=(mode == 'hardened'))
        cpu = Cpu(rnd)
        t_press, t_hold = 1000, 300
        t_rel = t_press + t_hold
        # окно 1-го цикла: от T1 первой выборки до её конца + хвост WB
        win = None
        st = dict(contention=0, spurious_we=0, dirt=None, al=None,
                  boot=None, por_len=None, shifts=None, handover=False)
        for k in range(K_HALF):
            # ---- кнопка
            if mode == 'por':
                rst_eff, midrail = 0, None
            elif mode == 'btn_fast':
                rst_eff = 1 if (t_press <= k < t_rel + 5) else 0
                midrail = None
            else:
                if t_press <= k < t_rel:
                    rst_eff, midrail = 1, None
                elif k < t_rel + DWELL:
                    rst_eff, midrail = 1, rnd     # спад: пин ещё читается 1
                else:
                    rst_eff, midrail = 0, None
            # ---- CPU
            if mode in ('por', 'btn_fast'):
                if cpu.state != 'run':
                    probe, _ = chip.comb(rst_eff,
                                         make_env(cpu.float_lines()))
                    rip = probe['reset_in'] if not chip.hard \
                        else chip.reset_in_r
                else:
                    rip = 1
                cpu_out, phase = cpu.step(k, 1 - rip)
            elif mode == 'float_cpufirst':
                # CPU отпускается на 1/3 спада (порог CPU ниже порога CPLD)
                in_rst = not (t_rel + DWELL // 3 <= k)
                cpu_out, phase = cpu.step(k, in_rst)
            elif mode == 'float_cpulate':
                in_rst = k < t_rel + DWELL
                cpu_out, phase = cpu.step(k, in_rst)
            else:                                  # hardened
                cpu_out, phase = cpu.step(k, 1 - chip.reset_in_r)
            # ---- CPLD
            env = make_env(cpu_out)
            outs, _ = chip.comb(rst_eff, env)
            # легальный /WE: T2/T4 цикла записи CPU (WB-хвост - его же
            # растянутый импульс)
            legit_w = (cpu.state == 'run' and phase in ('t2', 't4') and
                       cpu_out['cyc'] == 1)
            spurious = (outs['we_n'] == 0 and outs['cs_n'] == 0 and
                        not legit_w)
            contention = (outs['a_oe'] and cpu_out['a_driven'])
            # метрики считаем ТОЛЬКО в окне 1-го цикла выборки PC=0
            if win is None and cpu.first_fetch_k is not None:
                win = (cpu.first_fetch_k - CPU_CLK_HALF,
                       cpu.first_fetch_k + 3 * CPU_CLK_HALF + 16)
            if win is not None and win[0] <= k < win[1]:
                if contention:
                    st['contention'] += 1
                if spurious:
                    st['spurious_we'] += 1
                if (phase == 't2' and cpu_out['cyc'] == 0 and
                        outs['a_oe'] and outs['rd_drive']):
                    st['handover'] = True
            chip.half_step(k, rst_eff, env, midrail)
            # ---- вердикт 1-й выборки
            if (st['boot'] is None and cpu.first_fetch_k is not None and
                    k >= cpu.first_fetch_k + 3 * CPU_CLK_HALF):
                st['dirt'] = chip.dirty()
                st['al'] = list(chip.al)
                got = 0
                for i in range(8):
                    got |= (1 if chip.al[i] else 0) << i
                st['boot'] = (got == cpu.first_fetch_lo and
                              st['contention'] == 0 and
                              st['spurious_we'] == 0 and
                              st['handover'])
            if chip.por_run_end is not None and st['por_len'] is None:
                st['por_len'] = (chip.por_run_end + 1) * HALF_NS
                st['shifts'] = chip.por_shifts_at_end
        res.append(st)
    boots = sum(1 for r in res if r['boot'])
    dirts = [r['dirt'] for r in res if r['dirt'] is not None]
    n_spur = sum(1 for r in res if r['spurious_we'])
    n_cont = sum(1 for r in res if r['contention'])
    spur_med = sorted(r['spurious_we'] for r in res)[len(res) // 2]
    cont_med = sorted(r['contention'] for r in res)[len(res) // 2]
    print("=== %s (%d сидов) ===" % (name, seeds))
    print("  BOOT_OK: %d/%d" % (boots, seeds))
    if dirts:
        print("  грязь к концу 1-го цикла (рег. из 40 не в сбросовом): "
              "min=%d медиана=%d max=%d" %
              (min(dirts), sorted(dirts)[len(dirts) // 2], max(dirts)))
    print("  1-й цикл: ложных /WE у %d/%d сидов (медиана %d полутактов);"
          " контеншн A/AD у %d/%d (медиана %d)"
          % (n_spur, seeds, spur_med, n_cont, seeds, cont_med))
    if res[0]['por_len'] is not None:
        print("  POR: %d нс (норма >= 840), сдвигов por_sh: %d"
              % (res[0]['por_len'], res[0]['shifts']))
    return res


# ------------------------------------------------------------ самопроверка
def selftest():
    print("=" * 74)
    print("САМОПРОВЕРКА МОДЕЛИ v3.9.5 (против .rpt и ожиданий RTL)")
    print("=" * 74)
    ok = True
    chip = Chip()
    rnd = random.Random(7)
    cpu = Cpu(rnd)
    x1s, xns, cnts = [], [], []
    por_len = None
    for k in range(2000):
        cpu_out, phase = cpu.step(k, k < 100)
        env = make_env(cpu_out)
        outs, _ = chip.comb(0, env)
        if k > 120:
            x1s.append(outs['x1'])
            xns.append(chip.x1n)
            cnts.append(tuple(chip.cnt))
        chip.half_step(k, 0, env, None)
        if chip.por_run_end is not None and por_len is None:
            por_len = chip.por_run_end + 1
    legal = {(0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1), (1, 0, 0),
             (1, 0, 1), (1, 1, 0)}
    cond = set(cnts) == legal
    print("  %s  mod-7 орбита 0..6, 111 недостижим" %
          ("ПАСС" if cond else "ПРОВ"))
    ok &= cond
    s = ''.join(str(b) for b in x1s)
    i0 = s.find("1111100")
    pat = s[i0:i0 + 42] if i0 >= 0 else s[:42]
    cond = i0 >= 0 and pat == "1111100" * 6
    print("  %s  узор X1 «1111100» (100/40 нс, 7,143 МГц)"
          % ("ПАСС" if cond else "ПРОВ"))
    if not cond:
        print("        факт: %s" % pat)
    ok &= cond
    cond = chip.por_shifts_at_end == 4 and por_len >= POR_MIN_HALF
    print("  %s  POR: %d сдвига por_sh (F->7->3->1->0), %d нс (норма 840)"
          % ("ПАСС" if cond else "ПРОВ", chip.por_shifts_at_end,
             por_len * HALF_NS))
    ok &= cond
    # строб x1_n: ровно 2 полутакта «1» в каждом периоде cnt 280 нс (14 пт)
    cond = i0 >= 0
    if cond:
        for off in range(i0, i0 + 56, 14):
            win = xns[off:off + 14]
            if sum(win) != 2 or win[5:7] != [1, 1]:
                cond = False
    print("  %s  строб x1_n: 1 импульс 40 нс в каждом периоде cnt 280 нс"
          % ("ПАСС" if cond else "ПРОВ"))
    ok &= cond
    return ok


def main():
    ok = selftest()
    print()
    print("=" * 74)
    print("СЦЕНАРИИ СБРОСА (по 20 сидов; кнопка: нажатие 20 мкс,")
    print("отпускание с плавающим спадом ~10 мкс)")
    print("=" * 74)
    run_scene("A. ПИТАНИЕ (por_clean) - эталон v3.9.5", 'por')
    run_scene("B. КНОПКА, быстрый фронт (плата с подтяжкой RST 10к на GND)",
              'btn_fast')
    run_scene("C. КНОПКА на текущей плате (плавающий спад), CPU отпускается "
              "РАНЬШЕ CPLD", 'float_cpufirst')
    run_scene("D. КНОПКА на текущей плате (плавающий спад), CPU отпускается "
              "ПОЗЖЕ CPLD", 'float_cpulate')
    run_scene("E. КНОПКА с плавающим спадом + ХАРДРЕНИНГ RTL v3.9.6",
              'hardened')
    print()
    print("ВЕРДИКТ: %s" % ("модель самосогласована" if ok else
                           "ЕСТЬ ПРОВАЛЫ САМОПРОВЕРКИ - модель править"))


if __name__ == '__main__':
    main()
