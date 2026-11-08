#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_txuart_v21.py - цикл-точная модель top_txuart_por6_v21 (TXUART v2.1, beta/txuart).

Семантика: NBA, ДВА домена (база v3.9.8-clear, п.22/23):
  тик = 20 нс (posedge clk 50 МГц, GCK3);
  узел - КОЛЬЦО one-hot r0..r6 (двойной kill, рестарт из 00 по NOR7,
  INIT r0=1) на clk 50; clk25_q - T-триггер /2 (INIT=0) -> posedge clk25
  на нечётных тиках; por-цепь (por_sh 8 бит Init=FF, строб por_ce = r0,
  por_run Init=SET) - в 50-домене (POR = 8 x 140 = 1120 нс, снятие
  por_run на кромке ~1020 нс);
  логика (FSM шины v3 + харденинг сброса п.21 + ЯДРО TXUART) - на
  posedge clk25; СЕТЬ GSR от cpu_rst = rst_press | por_run (п.18/20):
  FSM + ядро чистятся асинхронно (ядро: shreg SET-ветка 1FF, счётчики
  CLR); rst-цепь - вне GSR (квалификатор 8 тактов clk25 подряд ->
  латентность кнопки ~400..440 нс);
  ядро TXUART v2.1 - mod-16 на clk25: БИТ = 16 x 40 нс = 640 нс
  (v2.1: adv_q и tx_run свернуты - bit_cnt 1..10, idle = 0, busy =
  |bit_cnt; jam baud_cnt <= 0; shreg 9 бит сам-idle - без изменений;
  (1 562 500 бод) - 2х-блокер фита v1.0 снят по построению.

Сценарии (аналог С1-С9 v1.0, пересчитанные на сетку 32 тика = 640 нс):
  С1  POR/idle: TX='1' (INIT), RESET_IN, X1-паттерн 1/7 (кольцо),
      X2 = ~X1, транзит SID=RX, статус 05h=02h
  С2  TX-кадр 55h/AAh: ВСЕ переходы на сетке 32 тика, старт РОВНО 32,
      PC-приёмник декодирует, shreg сам в idle 1FF
  С3  поток 3 байта с TXRDY-поллингом - без потерь; стоп >= 32 тиков
  С4  OUT 04h при busy - байт тихо отброшен, кадр не порчен
  С5  статус-порт: IN 05h = 02h/00h; чтение 04h ядро не трогает
  С6  запись 04h в ОКНЕ POR - кадр НЕ стартует (GSR+!por_run)
  С7  RST посреди кадра - квалификатор ~400 нс -> GSR: TX='1',
      ядро вычищено; после сброса кадр идёт
  С8  строб требует !WRn в T2: ALE-глюк до данных - кадра НЕТ
  С9  регрессия базы: порты 00-02h, KBROW 03h, writeback ОЗУ (/WE ровно
      4 тика = 2 такта clk25), запись в ПЗУ без /WE, кольцо/X1/X2

Запуск: python3 scripts/sim_txuart_v21.py  (пути от папки скрипта)
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))

BAUD_DIV = 16          # clk25 25 МГц / 16 = 1 562 500 бод
BIT_TICKS = BAUD_DIV * 2   # 32 тика по 20 нс = 640 нс
TICK = 20              # нс (posedge clk 50 МГц)
S_IDLE, S_T1H, S_T2, S_WB1, S_WB2, S_WB3, S_WB4 = range(7)

class DUT:
    """Цикл-точная модель retro_pcld_top (txuart v2.0, база v3.9.8-clear)."""
    def __init__(self):
        # узел тактирования (50-домен, вне GSR) - бит-в-бит базы
        self.r = [1, 0, 0, 0, 0, 0, 0]      # кольцо r0..r6, INIT r0=1
        self.clk25_q = 0                    # T-триггер /2, INIT=0
        self.por_sh = 0xFF; self.por_run = 1
        # харденинг сброса п.21 (clk25, вне GSR)
        self.rst_meta = 0; self.rst_sync = 0
        self.rst_press = 0; self.rst_qcnt = 0
        self.reset_q = 0
        # FSM шины v3 (GSR-домен)
        self.state = S_IDLE; self.rd_seen = 0; self.wr_seen = 0
        self.addr_latch = 0; self.bus_reg = 0
        self.seg_q = 0xFF; self.dig_q = 0xF; self.snd_q = 0; self.kbcol_q = 0
        # ядро TXUART v2.1 (GSR-домен, clk25; tx_run/adv_q свернуты)
        self.shreg = 0x1FF; self.bit_cnt = 0; self.baud_cnt = 0
        self.ld_tx_q = 0
        # входы
        self.RST = 0; self.ALE = 0; self.WRn = 1; self.RDn = 1; self.IOM = 0; self.A15 = 0
        self.A_in = None   # AD0-7 со стороны CPU (None = Hi-Z)
        self.D_in = 0      # D-шина памяти (для bus_reg при чтении памяти)
        self.RX = 1
        self.rows = 0      # row0..4 (клавиатура)
        self.t = 0

    # ---------- комбинационные ----------
    @property
    def por_ce(self):    return self.r[0]
    @property
    def X1(self):        return self.r[0]
    @property
    def X2(self):        return 1 if any(self.r[1:]) else 0
    @property
    def cpu_rst(self):   return 1 if (self.rst_press or self.por_run) else 0
    @property
    def in_wb(self):     return self.state >= S_WB1
    @property
    def in_welo(self):   return self.state in (S_WB2, S_WB3)
    @property
    def wr_phase(self):  return self.state >= S_T2
    @property
    def wb_out(self):    return self.in_wb
    @property
    def rd_drive(self):  return 1 if (self.state == S_T2 and self.rd_seen and not self.RDn and not self.ALE) else 0
    @property
    def io_rd_kb(self):  return 1 if (self.IOM and (self.addr_latch & 7) == 3) else 0
    @property
    def io_rd_st(self):  return 1 if (self.IOM and (self.addr_latch & 7) == 5) else 0
    @property
    def io_wr_tx(self):
        return 1 if (self.state == S_T2 and self.WRn == 0 and self.IOM and
                     (self.addr_latch & 7) == 4 and
                     self.bit_cnt == 0 and not self.ld_tx_q and
                     not self.por_run and not self.rst_press) else 0
    @property
    def baud_tick(self): return 1 if self.baud_cnt == BAUD_DIV - 1 else 0
    @property
    def A_out(self):
        """Значение на AD-пинах со стороны CPLD (None = Hi-Z)."""
        if self.rd_drive:
            if self.io_rd_kb:
                return (self.rows & 0x1F) & 0xFF
            if self.io_rd_st:
                return (0 if self.bit_cnt else 2) & 0xFF  # {000000, TXRDY, 0}
            return self.bus_reg
        if self.wb_out:
            return self.addr_latch
        return None
    @property
    def D_out(self):     return self.bus_reg if self.wb_out else None
    @property
    def CSr_n(self):     return 1 if (self.A15 or self.IOM) else 0
    @property
    def CS_n(self):      return 0 if self.in_wb else (1 if (self.A15 or self.IOM) else 0)
    @property
    def OEr_n(self):     return 1 if (self.CSr_n or self.wr_phase) else 0
    @property
    def OE_n(self):      return 1 if (self.CS_n or self.wr_phase) else 0
    @property
    def WE_n(self):      return 0 if self.in_welo else 1
    @property
    def RESET_IN(self):  return self.reset_q
    @property
    def SID(self):       return self.RX
    @property
    def TX(self):        return self.shreg & 1
    @property
    def seg(self):       return (~self.seg_q) & 0xFF
    @property
    def dig(self):       return (~self.dig_q) & 0xF
    @property
    def snd(self):       return self.snd_q
    @property
    def col(self):       return self.kbcol_q & 0xF

    # ---------- служебное: GSR (асинхронный сброс FSM + ядра) ----------
    def _gsr(self):
        self.state = S_IDLE; self.rd_seen = 0; self.wr_seen = 0
        self.addr_latch = 0; self.bus_reg = 0
        self.seg_q = 0xFF; self.dig_q = 0xF; self.snd_q = 0; self.kbcol_q = 0
        self.shreg = 0x1FF; self.bit_cnt = 0; self.baud_cnt = 0
        self.ld_tx_q = 0

    # ---------- тик: posedge clk 50 МГц ----------
    def tick(self):
        # --- узел (50-домен): кольцо, clk25_q, por-цепь (NBA из текущих) ---
        # NOTE: NOT = (1 - x), не ~x - в Python ~1 = -2 (битовый NOT на int)
        r0, r1, r2, r3, r4, r5, r6 = self.r
        q0, q1, q2, q3, q4, q5, q6 = (1 - r0, 1 - r1, 1 - r2, 1 - r3, 1 - r4, 1 - r5, 1 - r6)
        n0 = ((r6 & q0 & q1 & q2) | (q0 & q1 & q2 & q3 & q4 & q5 & q6)) & 1
        n1 = (r0 & q1 & q2 & q3) & 1
        n2 = (r1 & q2 & q3 & q4) & 1
        n3 = (r2 & q3 & q4 & q5) & 1
        n4 = (r3 & q4 & q5 & q6) & 1
        n5 = (r4 & q5 & q6 & q0) & 1
        n6 = (r5 & q6 & q0 & q1) & 1
        self.r = [n0, n1, n2, n3, n4, n5, n6]
        c25_rose = (self.clk25_q == 0)
        self.clk25_q ^= 1
        por_run_old = self.por_run
        self.por_run = self.por_sh & 1
        if r0:  # por_ce = СТАРЫЙ r0 (сэмпл на кромке до NBA)
            self.por_sh = (self.por_sh >> 1) & 0xFF

        cpu_rst_old = 1 if (self.rst_press or por_run_old) else 0

        # --- логика (posedge clk25, нечётные тики) ---
        if c25_rose:
            # харденинг сброса п.21 (вне GSR, тикает всегда)
            rst_meta_n = self.RST
            rst_sync_n = self.rst_meta
            if self.rst_sync != self.rst_press:
                if self.rst_qcnt == 7:
                    rst_press_n = self.rst_sync; rst_qcnt_n = 0
                else:
                    rst_press_n = self.rst_press; rst_qcnt_n = self.rst_qcnt + 1
            else:
                rst_press_n = self.rst_press; rst_qcnt_n = 0
            reset_q_n = 0 if cpu_rst_old else 1

            # FSM шины v3 + ядро TXUART (GSR-домен: сброс по cpu_rst_old)
            if cpu_rst_old:
                self._gsr()
            else:
                self._logic_edge()

            self.rst_meta = rst_meta_n; self.rst_sync = rst_sync_n
            self.rst_press = rst_press_n; self.rst_qcnt = rst_qcnt_n
            self.reset_q = reset_q_n
            # асинхронный GSR-захват: cpu_rst поднялся ТОЛЬКО ЧТО (rst_press_n)
            if not cpu_rst_old and (rst_press_n or self.por_run):
                self._gsr()
        self.t += 1

    # ---------- логический такт clk25 (FSM + ядро, NBA) ----------
    def _logic_edge(self):
        nxt = {}
        # --- FSM шины (v3, бит-в-бит базы) ---
        state = self.state
        addr_latch = self.addr_latch; bus_reg = self.bus_reg
        rd_seen = self.rd_seen; wr_seen = self.wr_seen
        if state == S_T1H and self.ALE:
            addr_latch = self.A_in if self.A_in is not None else addr_latch
            if not self.IOM:
                bus_reg = self.D_in
        if state == S_T2 and self.WRn == 0:
            bus_reg = self.A_in if self.A_in is not None else bus_reg
            if self.IOM:
                p = self.addr_latch & 7
                if p == 0:
                    nxt['seg_q'] = self.A_in & 0xFF if self.A_in is not None else nxt.get('seg_q', self.seg_q)
                    nxt['dig_q'] = (self.A_in & 0xF) if self.A_in is not None else nxt.get('dig_q', self.dig_q)
                    nxt['snd_q'] = (self.A_in >> 4) & 1 if self.A_in is not None else nxt.get('snd_q', self.snd_q)
                elif p == 1:
                    nxt['dig_q'] = (self.A_in & 0xF) if self.A_in is not None else nxt.get('dig_q', self.dig_q)
                    nxt['snd_q'] = (self.A_in >> 4) & 1 if self.A_in is not None else nxt.get('snd_q', self.snd_q)
                elif p == 2:
                    nxt['kbcol_q'] = (self.A_in & 0xF) if self.A_in is not None else nxt.get('kbcol_q', self.kbcol_q)
                # 3'b100 (04h) - старт TX в ядре (строб io_wr_tx ниже); 05h чтение
        if state == S_T2 and self.RDn == 0:
            rd_seen = 1
        if state == S_T2 and self.WRn == 0:
            wr_seen = 1
        new_state = None
        if self.ALE and state == S_T2 and not ((wr_seen and self.WRn) or (rd_seen and self.RDn)):
            new_state = S_IDLE; rd_seen = 0; wr_seen = 0
        else:
            if state == S_IDLE:
                if self.ALE: new_state = S_T1H
            elif state == S_T1H:
                if not self.ALE: new_state = S_T2
            elif state == S_T2:
                if wr_seen and self.WRn:
                    wr_seen = 0
                    new_state = (S_WB1 if (not self.IOM and self.A15 and
                                           not self.por_run and not self.rst_press) else S_IDLE)
                elif rd_seen and self.RDn:
                    rd_seen = 0
                    new_state = S_IDLE
            elif state == S_WB1: new_state = S_WB2
            elif state == S_WB2: new_state = S_WB3
            elif state == S_WB3: new_state = S_WB4
            elif state == S_WB4: new_state = S_IDLE
            else: new_state = S_IDLE
        nxt['state'] = state if new_state is None else new_state
        nxt['rd_seen'] = rd_seen; nxt['wr_seen'] = wr_seen
        nxt['addr_latch'] = addr_latch; nxt['bus_reg'] = bus_reg
        # --- ядро TXUART v2.1 (mod-16 на clk25; tx_run/adv_q свернуты) ---
        shreg = self.shreg; bit_cnt = self.bit_cnt; baud_cnt = self.baud_cnt
        busy_old = (bit_cnt != 0)                # СТАРОЕ значение (NBA-семантика)
        baud_cnt = (baud_cnt + 1) & 0xF          # НАТУРАЛЬНЫЙ wrap mod-16 (декодов НЕТ)
        if self.ld_tx_q:
            shreg = ((self.A_in & 0xFF) << 1) & 0x1FF if self.A_in is not None else 0x1FE  # {A,1'b0}
            bit_cnt = 1; baud_cnt = 0            # jam 0: старт РОВНО 16 тактов clk25 (1..10 = бит-таймы)
        else:
            if self.baud_tick:
                shreg = ((1 << 8) | (shreg >> 1)) & 0x1FF  # инжекция '1' (в idle - НЕТ-ОП)
            if busy_old and self.baud_tick:
                bit_cnt = 0 if bit_cnt == 10 else bit_cnt + 1  # 10-й сдвиг - кадр закрыт (TXRDY)
        nxt['shreg'] = shreg; nxt['bit_cnt'] = bit_cnt; nxt['baud_cnt'] = baud_cnt
        nxt['ld_tx_q'] = self.io_wr_tx           # регистровый строб загрузки (п.30)
        for k, v in nxt.items(): setattr(self, k, v)


class Sim:
    def __init__(self):
        self.d = DUT()
        self.checks = 0; self.fails = 0; self.fails_log = []

    def chk(self, cond, msg):
        self.checks += 1
        if not cond:
            self.fails += 1
            self.fails_log.append(f"    FAIL: {msg}")

    def run(self, n):
        for _ in range(n):
            self.d.tick()
            self.pc_sample()   # PC-приёмник TX-линии сэмплирует КАЖДЫЙ тик

    # ---------- CPU-циклы (в тиках 20 нс; T1 = 3 такта clk25 ALE) ----------
    def cpu_io_write(self, port, data):
        d = self.d
        d.ALE = 1; d.IOM = 1; d.A_in = port; self.run(6)     # T1 (ALE высок; захват адреса)
        d.ALE = 0; self.run(2)                                # T2 начинается
        d.WRn = 0; d.A_in = data; self.run(8)                 # данные на AD при !WR
        d.WRn = 1; d.A_in = None; self.run(4)                 # WR#(вверх), зазор

    def cpu_io_read(self, port):
        d = self.d
        d.ALE = 1; d.IOM = 1; d.A_in = port; self.run(6)     # T1
        d.ALE = 0; self.run(2)                                # T2
        d.RDn = 0; self.run(6)                                # RD# низ (драйв со 2-го такта clk25)
        val = d.A_out                                         # CPU сэмплирует перед RD#(вверх)
        self.run(2)
        d.RDn = 1; self.run(4)
        return val

    # ---------- PC-приёмник ----------
    def pc_listen(self):
        self.pc_rx_bytes = []
        self.pc_rx_bits = []   # (tick_start, width, level) сегменты линии
        self._pcst = {'edge': None, 'byte': 0, 'k': 0}

    def pc_sample(self):
        """Стандартный UART-приёмник ПК (выборки по сетке BIT_TICKS)."""
        d = self.d
        st = self._pcst
        tx = d.TX
        if st['edge'] is None:
            if tx == 0:                     # спад: старт-бит
                st['edge'] = d.t; st['k'] = -1; st['byte'] = 0
        else:
            e = st['edge']
            rel = d.t - e
            half = BIT_TICKS // 2
            if st['k'] == -1 and rel == half:
                if tx != 0:                 # глитч: в центре старта линия '1'
                    st['edge'] = None; st['k'] = 0; st['byte'] = 0
                else:
                    st['k'] = 0
            if 0 <= st['k'] <= 7 and rel == half + BIT_TICKS * (st['k'] + 1):
                st['byte'] |= (tx << st['k']); st['k'] += 1
            if st['k'] == 8 and rel == half + BIT_TICKS * 9:
                if tx == 1:
                    self.pc_rx_bytes.append(st['byte'])
                else:
                    self.pc_rx_bytes.append(('FE', st['byte']))
                st['edge'] = None; st['k'] = 0; st['byte'] = 0
        # трекинг ширин сегментов (для С2/С3)
        tr = getattr(self, '_trk', None)
        if tr is None or tr[2] != tx:
            if tr is not None:
                self.pc_rx_bits.append((tr[0], d.t - tr[0], tr[2]))
            tr = (d.t, d.t, tx)
        self._trk = tr

    def tx_frame(self):
        return self.pc_rx_bits


# ---------------- сценарии ----------------

def s1_por_idle(s: Sim):
    d = s.d
    por_fell = None
    for _ in range(80):
        s.run(1)
        if por_fell is None and d.por_run == 0:
            por_fell = d.t
    # v3.9.8: 8 стробов por_ce=r0 (тики 1,8,...,50) -> снятие на кромке ~51 тик
    # = 1020 нс ("снятие por_run на кромке 1020 нс" - п.23 базы)
    s.chk(por_fell is not None and 49 <= por_fell <= 53,
          f"С1: POR снялся на тике {por_fell} (ожид. ~51 = 8 стробов x 140 нс + 1, кромка 1020 нс)")
    s.chk(d.TX == 1, "С1: TX='1' в idle (INIT shreg=1FF)")
    s.chk(d.bit_cnt == 0 and d.ld_tx_q == 0, "С1: ядро в idle")
    s.chk(d.RESET_IN == 1, "С1: RESET_IN=1 после POR (регистр reset_q)")
    # X1 = r0: период 7 тиков (140 нс), в периоде РОВНО 1 высокий (duty 1/7)
    pat = []
    for _ in range(14):
        pat.append(d.X1); s.run(1)
    s.chk(pat[:7] == pat[7:], f"С1: X1 периодичен 7 тиков ({pat})")
    s.chk(sum(pat[:7]) == 1, f"С1: X1 duty 1/7 в периоде - КОЛЬЦО ({pat[:7]})")
    # X2 - противофаза X1 в КАЖДЫЙ сэмпл (легальный one-hot: X2 = ~r0)
    s.chk(all(d.X1 ^ d.X2 for _ in range(7)), "С1: X2 = ~X1 (противофаза)")
    # кольцо: состояние узла - ровно одна '1' среди r0..r6
    s.chk(sum(d.r) == 1, f"С1: one-hot кольца ({d.r})")
    # транзит SID = RX
    d.RX = 0; s.run(1); s.chk(d.SID == 0, "С1: SID=RX транзит (0)")
    d.RX = 1; s.run(1); s.chk(d.SID == 1, "С1: SID=RX транзит (1)")
    # статус: TXRDY=1 (бит A1), остальные 0
    st = s.cpu_io_read(5)
    s.chk(st == 0x02, f"С1: IN 05h = {st:#04x} (ожид. 02 = TXRDY, A0=0, A7..A2=0)")
    # idle: TX не шевелится 100 тиков
    t0 = d.TX; s.run(100)
    s.chk(d.TX == t0 == 1, "С1: TX стабилен '1' 100 тиков")

def s2_tx_frame(s: Sim):
    d = s.d
    for byte in (0x55, 0xAA):
        s.pc_listen()
        s.cpu_io_write(4, byte)
        s.run(340)  # кадр 10 бит = 320 тиков + запас
        # сетка переходов: ВСЕ переходы линии TX кратны 32 от спада старта
        segs = [x for x in s.tx_frame() if x[1] < 800]   # без idle-хвостов
        lows = [(a, w) for (a, w, lv) in segs if lv == 0]
        s.chk(len(lows) >= 1, f"С2({byte:#04x}): старт-бит есть")
        if not lows: continue
        start = lows[0][0]
        bounds = []
        for (a, w, lv) in segs:
            if a >= start:
                bounds.append(a + w - start)
        s.chk(all(b % 32 == 0 for b in bounds),
              f"С2({byte:#04x}): все переходы на сетке 32 тиков = 640 нс ({bounds})")
        s.chk(bounds and bounds[-1] <= 288,
              f"С2({byte:#04x}): последний переход <= 288 (кадр 10 бит) ({bounds})")
        if byte == 0x55:  # d0=1: старт отделён - ровно 32
            s.chk(bounds and bounds[0] == 32,
                  f"С2(0x55): старт-бит ровно 32 тика = 640 нс ({bounds[:1]})")
        s.chk(s.pc_rx_bytes and s.pc_rx_bytes[-1] == byte,
              f"С2({byte:#04x}): PC-приёмник декодировал {s.pc_rx_bytes[-1] if s.pc_rx_bytes else None}")
        s.chk(d.shreg == 0x1FF and d.bit_cnt == 0,
              f"С2({byte:#04x}): shreg сам в idle 1FF, bit_cnt=0")
    # idle после кадров
    s.run(100); s.chk(d.TX == 1, "С2: TX='1' после кадров (бесконечный стоп)")

def s3_tx_stream(s: Sim):
    d = s.d
    s.pc_listen()
    for byte in (0x41, 0x42, 0x43):   # "ABC"
        guard = 0
        while True:
            st = s.cpu_io_read(5)
            if st & 0x02: break
            guard += 1
            s.chk(guard < 50, "С3: зависание поллинга TXRDY")
            if guard >= 50: return
        s.cpu_io_write(4, byte)
    s.run(400)
    s.chk(s.pc_rx_bytes[-3:] == [0x41, 0x42, 0x43],
          f"С3: поток без потерь {s.pc_rx_bytes[-3:]}")
    s.chk(d.shreg == 0x1FF, "С3: shreg в idle после потока")
    # фактический СТОП между кадрами при поллинге: >= 32 тиков (полный стоп-бит)
    segs = s.tx_frame()
    highs = [(a, w) for (a, w, lv) in segs if lv == 1 and 20 <= w < 800]
    s.chk(len(highs) >= 2 and all(w >= 32 for (a, w) in highs),
          f"С3: межкадровые стопы >= 32 тиков ({[(w) for (a, w) in highs]})")

def s4_tx_busy_drop(s: Sim):
    d = s.d
    s.pc_listen()
    s.cpu_io_write(4, 0x11)           # кадр пошёл
    s.run(40)                          # внутри кадра (старт)
    s.chk(d.bit_cnt != 0, "С4: передача активна")
    s.cpu_io_write(4, 0x99)           # запись при busy - должна быть отброшена
    s.chk(d.bit_cnt != 0, "С4: передача НЕ перезапущена (строб задавлен tx_idle=0)")
    s.run(320)
    s.chk(s.pc_rx_bytes[-1] == 0x11, f"С4: кадр цел, байт busy отброшен ({s.pc_rx_bytes[-1]})")
    s.chk(s.pc_rx_bytes.count(0x99) == 0, "С4: байта 0x99 на линии НЕТ (тихий отброс)")
    st = s.cpu_io_read(5)
    s.chk(st & 0x02, f"С4: TXRDY=1 после освобождения ({st:#04x})")

def s5_status_port(s: Sim):
    d = s.d
    # idle: 02h
    st = s.cpu_io_read(5)
    s.chk(st == 0x02, f"С5: IN 05h в idle = {st:#04x} (ожид. 02)")
    # busy: 00h
    s.cpu_io_write(4, 0x5A)
    s.run(20)
    st = s.cpu_io_read(5)
    s.chk(st == 0x00, f"С5: IN 05h при передаче = {st:#04x} (ожид. 00)")
    s.run(340)
    st = s.cpu_io_read(5)
    s.chk(st == 0x02, f"С5: IN 05h после кадра = {st:#04x} (ожид. 02)")
    s.chk(s.pc_rx_bytes[-1] == 0x5A, "С5: кадр 5Ah дошёл до ПК")
    # IN 04h не определён (RX нет) - уходит в bus_reg, ядро НЕ должно сбоять
    v = s.cpu_io_read(4)
    s.chk(d.bit_cnt == 0 and d.shreg == 0x1FF, f"С5: чтение 04h (не определено, = {v:#04x}) не трогает ядро")

def s6_por_gate(s: Sim):
    # Свежий DUT: POR бывает ТОЛЬКО при подаче питания (INIT).
    # v2.0: в окне POR cpu_rst = por_run = 1 -> GSR держит FSM в IDLE,
    # ПОМИМО этого io_wr_tx задавлен !por_run (двойная страховка п.28/29)
    s.d = DUT(); s.pc_listen()
    d = s.d
    s.run(4)
    s.chk(d.por_run == 1, "С6: окно POR активно (por_run=1 от INIT)")
    s.chk(d.state == S_IDLE, "С6: FSM в IDLE (GSR от cpu_rst в окне POR)")
    s.chk(d.io_wr_tx == 0, "С6: io_wr_tx задавлен (!por_run + state=IDLE)")
    # полный цикл OUT 04h в окне POR - кадра быть НЕ должно
    d.ALE = 1; d.IOM = 1; d.A_in = 4; s.run(6)
    d.ALE = 0; s.run(2)
    d.WRn = 0; d.A_in = 0xC3; s.run(8)
    d.WRn = 1; d.A_in = None; s.run(4)
    s.chk(d.bit_cnt == 0 and d.ld_tx_q == 0 and d.shreg == 0x1FF,
          "С6: OUT 04h в окне POR - кадр НЕ стартовал (мусор floated-шины отброшен)")
    # ждём конец POR, ядро в idle
    s.run(80)
    s.chk(d.por_run == 0 and d.TX == 1, "С6: POR кончился, TX idle")
    # теперь нормальный кадр проходит
    s.cpu_io_write(4, 0x77); s.run(340)
    s.chk(s.pc_rx_bytes[-1] == 0x77, "С6: после POR кадр проходит нормально")

def s7_reset_midframe(s: Sim):
    d = s.d
    s.pc_listen()
    s.cpu_io_write(4, 0xC3)
    s.run(60)                          # внутри кадра
    s.chk(d.bit_cnt != 0, "С7: кадр TX идёт")
    tx_before = d.TX
    d.RST = 1
    s.run(24)                          # 2FF (2 такта clk25) + 8 такт квалификатора + запас
    s.chk(d.TX == 1, "С7: GSR (через квалификатор ~400 нс) - TX='1'")
    s.chk(d.shreg == 0x1FF and d.bit_cnt == 0 and
          d.baud_cnt == 0 and d.ld_tx_q == 0,
          "С7: ядро вычищено (bit_cnt=0, shreg=1FF, счётчики 0)")
    s.chk(d.rst_press == 1, "С7: rst_press взведён (квалификатор п.21)")
    d.RST = 0
    s.run(30)                          # снятие тоже квалифицировано (8 тактов) + reset_q
    s.chk(d.rst_press == 0 and d.cpu_rst == 0, "С7: сброс снят (квалифицированное снятие)")
    s.chk(d.TX == 1 and d.bit_cnt == 0, "С7: после сброса idle")
    # приёмник ПК был посреди убитого кадра - сбросить его состояние
    s.pc_listen()
    # повторный кадр после сброса
    s.cpu_io_write(4, 0x3C); s.run(340)
    s.chk(s.pc_rx_bytes[-1] == 0x3C, "С7: после сброса кадр проходит (0x3C)")
    s.chk(d.shreg == 0x1FF and d.bit_cnt == 0, "С7: ядро снова в idle")
    _ = tx_before

def s8_strobe_needs_wrn(s: Sim):
    d = s.d
    # ALE-глюк ДО данных: T2 вошёл, WRn ещё высок - ALE обрывает T2 (база v3):
    # строба !WRn в T2 не было -> кадра НЕТ
    s.pc_listen()
    d.ALE = 1; d.IOM = 1; d.A_in = 4; s.run(6)
    d.ALE = 0; s.run(2)                       # T2 начался, WRn=1
    d.ALE = 1; s.run(2); d.ALE = 0            # глюк ALE на 1 такт clk25 (обрыв T2)
    s.run(4)
    d.WRn = 0; d.A_in = 0xEE; s.run(6)        # WR# падает УЖЕ в IDLE - не строб
    d.WRn = 1; d.A_in = None; s.run(6)
    s.chk(d.ld_tx_q == 0 and d.bit_cnt == 0 and d.TX == 1,
          "С8: ALE-глюк до данных - кадр НЕ стартовал (строб требует T2 && !WRn)")
    # чистый цикл - ровно один кадр
    s.cpu_io_write(4, 0xA7); s.run(340)
    s.chk(s.pc_rx_bytes[-1] == 0xA7, "С8: чистый OUT 04h - кадр 0xA7 один")

def s9_base_regression(s: Sim):
    d = s.d
    # порты 00h-02h
    s.cpu_io_write(0, 0xA5)            # сегменты (инвертированы на выходе)
    s.cpu_io_write(1, 0x1F)            # разряды + SND
    s.cpu_io_write(2, 0x0F)            # колонки
    s.run(10)
    s.chk(d.seg == (0xA5 ^ 0xFF) & 0xFF, f"С9: seg = {d.seg:#04x}")
    s.chk(d.dig == (0x1F & 0xF) ^ 0xF, f"С9: dig = {d.dig:#x}")
    s.chk(d.snd == 1, "С9: SND = A4 порта 01h")
    s.chk(d.col == 0x0F, f"С9: col = {d.col:#x}")
    # KBROW: чтение 03h -> строки на A0-4
    d.rows = 0b10110
    val = s.cpu_io_read(3)
    s.chk(val == 0b10110, f"С9: IN 03h = {val:#05b} (rows)")
    d.rows = 0
    # запись ОЗУ: writeback, /WE ровно 4 тика (2 такта clk25 = 80 нс), A=addr, D=data
    we_log = []
    s.cpu_mem_write(0x8005, 0x4C, we_log)
    s.chk(len(we_log) >= 1 and all(w == 4 for w in we_log),
          f"С9: /WE импульсы ровно 4 тика 20 нс = 2 такта clk25 ({we_log})")
    # A15-гейт: запись в ПЗУ - без /WE
    we2 = []
    s.cpu_mem_write(0x0400, 0x00, we2)
    s.chk(not we2, f"С9: запись в ПЗУ без /WE ({we2})")
    # попутно: запись в ОЗУ НЕ дёргает ядро (это не OUT 04h)
    s.chk(d.bit_cnt == 0 and d.ld_tx_q == 0, "С9: запись ОЗУ не стартует кадр")
    # кольцо живо: one-hot
    s.chk(sum(d.r) == 1, f"С9: one-hot кольца после шинных циклов ({d.r})")

def s_cpu_mem_write_wrapper(self, addr, data, log):
    """Запись в память: FSM уходит в WB1..WB4, /WE низ 2 такта clk25 = 4 тика."""
    d = self.d
    d.A15 = 1 if (addr & 0x8000) else 0
    d.ALE = 1; d.IOM = 0; d.A_in = addr & 0xFF; self.run(6)
    d.ALE = 0; self.run(2)
    d.WRn = 0; d.A_in = data; self.run(8)
    d.WRn = 1                                 # WR#(вверх) - FSM уходит в WB1..WB4
    we = None; width = 0
    for _ in range(24):
        self.run(1)
        if d.WE_n == 0:
            if we is None: we = d.t
            width += 1
            self.mem_check = (d.A_out, d.D_out)
        else:
            if we is not None:
                log.append(width); we = None; width = 0
    if we is not None: log.append(width)
    d.A_in = None; d.IOM = 0; d.A15 = 0
    self.run(4)

Sim.cpu_mem_write = s_cpu_mem_write_wrapper

def main():
    s = Sim()
    d = s.d
    s.pc_listen()
    for f in (s1_por_idle, s2_tx_frame, s3_tx_stream, s4_tx_busy_drop,
              s5_status_port, s6_por_gate, s7_reset_midframe,
              s8_strobe_needs_wrn, s9_base_regression):
        f(s)
        # между сценариями - успокоить линию и ядро
        d.RX = 1; s.run(40)
    print("=" * 64)
    print(f"ИТОГ: {s.checks - s.fails}/{s.checks} ПАСС")
    if s.fails:
        print("Провалы:")
        for m in s.fails_log: print(m)
        sys.exit(1)
    print("ВСЕ СЦЕНАРИИ ПАСС (С1-С9)")
    sys.exit(0)

if __name__ == "__main__":
    main()
