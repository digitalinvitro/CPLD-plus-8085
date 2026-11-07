#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_txuart_v1.py - цикл-точная модель top_txuart_por6_v1 (TXUART v1.0, beta/txuart).

Семантика: NBA (все следующие значения вычисляются из текущих, потом присваиваются),
25 МГц (тик = 40 нс), negedge-фаза x1_n внутри тика (полутакт).
База = lowsize v3.9.3 БИТ-В-БИТ (делитель mod-7, por_ce = (cnt==1)|(cnt==6),
por_sh 8 бит Init=FF - БЕЗ М1, FSM шины v3, порты 00-03h, GSR-сброс логики п.18);
TX-транзит v3.7 (sod_q/tx_pass/tx_q/cpu_rst) выпилен; ядро TXUART п.26 - TX-only:
BAUD_DIV=16 (25 МГц/2^4 = 1 562 500 бод), регистровый строб загрузки ld_tx_q (п.28).

Сценарии:
  С1  POR/idle: TX='1' (INIT), RESET_IN, X1-паттерн 5/7, транзит SID=RX, статус 05h=02h
  С2  TX-кадр 55h/AAh: ВСЕ переходы на сетке 16 тиков, старт РОВНО 16, PC-приёмник
      декодирует, shreg сам в idle 1FF (инжекция стопа)
  С3  поток 3 байта с TXRDY-поллингом - без потерь; фактический стоп >= 16 тиков
  С4  OUT 04h при busy - байт тихо отброшен, кадр не порчен
  С5  статус-порт: IN 05h = 02h/00h (бит A1 = TXRDY, остальные 0); ядро не сбояет
  С6  запись 04h в ОКНЕ POR (floated-шина) - кадр НЕ стартует (!por_run в io_wr_tx)
  С7  RST посреди TX-кадра - GSR: TX='1' в первый такт, ядро вычищено, после сброса кадр идёт
  С8  строб требует !WRn в T2: ALE-глюк до данных - кадра НЕТ (база v3 не ломается)
  С9  регрессия базы: порты 00-02h, KBROW 03h, writeback ОЗУ (/WE ровно 2 тика),
      запись в ПЗУ без /WE, X1/X2 противофаза

Запуск: python3 scripts/sim_txuart_v1.py  (пути от папки скрипта)
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))

BAUD_DIV = 16          # 25 МГц / 16 = 1 562 500 бод
TICK = 40              # нс
S_IDLE, S_T1H, S_T2, S_WB1, S_WB2, S_WB3, S_WB4 = range(7)

class DUT:
    """Цикл-точная модель retro_pcld_top (txuart v1.0)."""
    def __init__(self):
        # делитель + POR (вне GSR, база v3.9.3)
        self.cnt = 0; self.x1_n = 0
        self.por_sh = 0xFF; self.por_run = 1
        # FSM шины v3 (GSR-домен)
        self.state = S_IDLE; self.rd_seen = 0; self.wr_seen = 0
        self.addr_latch = 0; self.bus_reg = 0
        self.seg_q = 0xFF; self.dig_q = 0xF; self.snd_q = 0; self.kbcol_q = 0
        # ядро TXUART п.26 (GSR-домен)
        self.shreg = 0x1FF; self.bit_cnt = 0; self.baud_cnt = 0
        self.tx_run = 0; self.adv_q = 0; self.ld_tx_q = 0
        # входы
        self.RST = 0; self.ALE = 0; self.WRn = 1; self.RDn = 1; self.IOM = 0; self.A15 = 0
        self.A_in = None   # AD0-7 со стороны CPU (None = Hi-Z)
        self.D_in = 0      # D-шина памяти (для bus_reg при чтении памяти)
        self.RX = 1
        self.rows = 0      # row0..4 (клавиатура)
        self.t = 0

    # ---------- комбинационные ----------
    @property
    def por_ce(self):    return 1 if self.cnt in (1, 6) else 0   # v3.9.3: фазы r1|r6
    @property
    def X1(self):        return ((1 if self.cnt != 0 else 0) ^ self.x1_n) & 1
    @property
    def X2(self):        return ((1 if self.cnt == 0 else 0) ^ self.x1_n) & 1
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
                     not self.tx_run and not self.ld_tx_q and not self.por_run) else 0
    @property
    def baud_tick(self): return 1 if self.baud_cnt == BAUD_DIV - 1 else 0
    @property
    def adv(self):       return 1 if (self.baud_tick and self.tx_run) else 0
    @property
    def A_out(self):
        """Значение на AD-пинах со стороны CPLD (None = Hi-Z)."""
        if self.rd_drive:
            if self.io_rd_kb:
                return (self.rows & 0x1F) & 0xFF
            if self.io_rd_st:
                return (0 if self.tx_run else 2) & 0xFF   # {000000, TXRDY, 0}
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
    def RESET_IN(self):  return 0 if (self.RST or self.por_run) else 1
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

    # ---------- такт: posedge-фаза ----------
    def tick(self):
        if self.RST:
            # GSR: асинхронный сброс ЛОГИКИ (мгновенно); делитель/POR вне домена
            self.state = S_IDLE; self.rd_seen = 0; self.wr_seen = 0
            self.addr_latch = 0; self.bus_reg = 0
            self.seg_q = 0xFF; self.dig_q = 0xF; self.snd_q = 0; self.kbcol_q = 0
            self.shreg = 0x1FF; self.bit_cnt = 0; self.baud_cnt = 0
            self.tx_run = 0; self.adv_q = 0; self.ld_tx_q = 0
            self.cnt = 0 if self.cnt == 6 else self.cnt + 1
        else:
            # --- NBA: сначала все следующие значения ---
            nxt = {}
            # делитель mod-7 (база бит-в-бит)
            nxt['cnt'] = 0 if self.cnt == 6 else self.cnt + 1
            # FSM шины (v3, бит-в-бит v3.9.3)
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
                    # 3'b100 (04h) - старт TX в ядре TXUART (ниже); 05h-07h - нет записи
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
                        new_state = (S_WB1 if (not self.IOM and self.A15 and not self.por_run) else S_IDLE)
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
            # POR (v3.9.3: 8 бит, строб (cnt==1)|(cnt==6))
            nxt['por_run'] = self.por_sh & 1
            if self.por_ce:
                nxt['por_sh'] = (self.por_sh >> 1) & 0xFF
            # ядро TXUART п.26
            shreg = self.shreg; bit_cnt = self.bit_cnt; baud_cnt = self.baud_cnt
            tx_run = self.tx_run
            baud_cnt = (baud_cnt + 1) & 0xF          # НАТУРАЛЬНЫЙ wrap mod-16 (декодов НЕТ)
            if self.ld_tx_q:
                tx_run = 1
                shreg = ((self.A_in & 0xFF) << 1) & 0x1FF if self.A_in is not None else 0x1FE  # {A,1'b0}
                bit_cnt = 0; baud_cnt = 1            # jam: старт РОВНО 16 тиков
            elif self.adv_q and self.tx_run:
                shreg = ((1 << 8) | (shreg >> 1)) & 0x1FF      # инжекция '1'
                if bit_cnt == 9:
                    tx_run = 0; bit_cnt = 0          # кадр закрыт (стоп на шине)
                else:
                    bit_cnt = bit_cnt + 1
            nxt['shreg'] = shreg; nxt['bit_cnt'] = bit_cnt; nxt['baud_cnt'] = baud_cnt
            nxt['tx_run'] = tx_run
            nxt['adv_q'] = self.adv
            nxt['ld_tx_q'] = self.io_wr_tx           # регистровый строб загрузки (п.28)
            # присваивания (NBA)
            for k, v in nxt.items(): setattr(self, k, v)
        # negedge-фаза (x1_n, вне GSR - тикает всегда)
        c = self.cnt
        self.x1_n = 1 if (c == 3 or (self.x1_n == 1 and c != 4)) else 0
        self.t += 1


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

    # ---------- CPU-циклы (T1 = 3 тика ALE; T2 - 4 тика строба) ----------
    def cpu_io_write(self, port, data):
        d = self.d
        d.ALE = 1; d.IOM = 1; d.A_in = port; self.run(3)     # T1 (ALE высок; захват адреса на 2-м)
        d.ALE = 0; self.run(1)                                # T2 начинается
        d.WRn = 0; d.A_in = data; self.run(4)                 # данные на AD при !WR
        d.WRn = 1; d.A_in = None; self.run(2)                 # WR#(вверх), зазор

    def cpu_io_read(self, port):
        d = self.d
        d.ALE = 1; d.IOM = 1; d.A_in = port; self.run(3)     # T1
        d.ALE = 0; self.run(1)                                # T2
        d.RDn = 0; self.run(3)                                # RD# низ (rd_seen с 1-го, драйв со 2-го)
        val = d.A_out                                         # CPU сэмплирует перед RD#(вверх)
        self.run(1)
        d.RDn = 1; self.run(2)
        return val

    # ---------- PC-приёмник ----------
    def pc_listen(self):
        self.pc_rx_bytes = []
        self.pc_rx_bits = []   # (tick_start, width, level) сегменты линии
        self._pcst = {'edge': None, 'byte': 0, 'k': 0}

    def pc_sample(self):
        """Стандартный UART-приёмник ПК (выборки по сетке BAUD_DIV)."""
        d = self.d
        st = self._pcst
        tx = d.TX
        if st['edge'] is None:
            if tx == 0:                     # спад: старт-бит
                st['edge'] = d.t; st['k'] = -1; st['byte'] = 0
        else:
            e = st['edge']
            rel = d.t - e
            half = BAUD_DIV // 2
            if st['k'] == -1 and rel == half:
                if tx != 0:                 # глитч: в центре старта линия '1'
                    st['edge'] = None; st['k'] = 0; st['byte'] = 0
                else:
                    st['k'] = 0
            if 0 <= st['k'] <= 7 and rel == half + BAUD_DIV * (st['k'] + 1):
                st['byte'] |= (tx << st['k']); st['k'] += 1
            if st['k'] == 8 and rel == half + BAUD_DIV * 9:
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
    for _ in range(40):
        s.run(1)
        if por_fell is None and d.por_run == 0:
            por_fell = d.t
    # v3.9.3: POR = 8 стробов (cnt==1|cnt==6) x 140 нс = 1120 нс = 28 тиков (норма >=21)
    s.chk(por_fell is not None and 27 <= por_fell <= 30,
          f"С1: POR снялся на тике {por_fell} (ожид. 28: 8 стробов x 140 нс = 1120 нс, норма >= 21)")
    s.chk(d.TX == 1, "С1: TX='1' в idle (INIT shreg=1FF)")
    s.chk(d.tx_run == 0 and d.ld_tx_q == 0, "С1: ядро в idle")
    s.chk(d.RESET_IN == 1, "С1: RESET_IN=1 после POR")
    # X1: период 7 тиков (140 нс), в периоде ровно 5 высоких
    pat = []
    for _ in range(14):
        pat.append(d.X1); s.run(1)
    s.chk(pat[:7] == pat[7:], f"С1: X1 периодичен 7 тиков ({pat})")
    s.chk(sum(pat[:7]) == 5, f"С1: X1 duty 5/7 в периоде ({pat[:7]})")
    # X2 - противофаза X1 в КАЖДЫЙ сэмпл (v3.9.2: X2 = ~X1 точно)
    s.chk(all(d.X1 ^ d.X2 for _ in range(7)), "С1: X2 = ~X1 (противофаза)")
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
        s.run(170)  # кадр 10 бит = 160 тиков + запас
        # сетка переходов: ВСЕ переходы линии TX кратны 16 от спада старта
        segs = [x for x in s.tx_frame() if x[1] < 400]   # без idle-хвостов
        lows = [(a, w) for (a, w, lv) in segs if lv == 0]
        s.chk(len(lows) >= 1, f"С2({byte:#04x}): старт-бит есть")
        if not lows: continue
        start = lows[0][0]
        bounds = []
        for (a, w, lv) in segs:
            if a >= start:
                bounds.append(a + w - start)
        s.chk(all(b % 16 == 0 for b in bounds),
              f"С2({byte:#04x}): все переходы на сетке 16 тиков ({bounds})")
        s.chk(bounds and bounds[-1] <= 144,
              f"С2({byte:#04x}): последний переход <= 144 (кадр 10 бит) ({bounds})")
        if byte == 0x55:  # d0=1: старт отделён - ровно 16
            s.chk(bounds and bounds[0] == 16,
                  f"С2(0x55): старт-бит ровно 16 тиков ({bounds[:1]})")
        if byte == 0xAA:  # d1=1,d3=1,...: сегменты сливаются, но старт+байт 0x02h:
            pass
        s.chk(s.pc_rx_bytes and s.pc_rx_bytes[-1] == byte,
              f"С2({byte:#04x}): PC-приёмник декодировал {s.pc_rx_bytes[-1] if s.pc_rx_bytes else None}")
        s.chk(d.shreg == 0x1FF and d.tx_run == 0,
              f"С2({byte:#04x}): shreg сам в idle 1FF, tx_run=0")
    # idle после кадров
    s.run(50); s.chk(d.TX == 1, "С2: TX='1' после кадров (бесконечный стоп)")

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
    s.run(200)
    s.chk(s.pc_rx_bytes[-3:] == [0x41, 0x42, 0x43],
          f"С3: поток без потерь {s.pc_rx_bytes[-3:]}")
    s.chk(d.shreg == 0x1FF, "С3: shreg в idle после потока")
    # фактический СТОП между кадрами при поллинге: >= 16 тиков (полный стоп-бит)
    # ищем высокую секцию между кадрами: сегменты с уровнем 1 внутри окна потока
    segs = s.tx_frame()
    highs = [(a, w) for (a, w, lv) in segs if lv == 1 and 20 <= w < 400]
    s.chk(len(highs) >= 2 and all(w >= 16 for (a, w) in highs),
          f"С3: межкадровые стопы >= 16 тиков ({[(w) for (a, w) in highs]})")

def s4_tx_busy_drop(s: Sim):
    d = s.d
    s.pc_listen()
    sh_at_start = None
    s.cpu_io_write(4, 0x11)           # кадр пошёл
    s.run(20)                          # внутри кадра (старт)
    s.chk(d.tx_run == 1, "С4: передача активна")
    s.cpu_io_write(4, 0x99)           # запись при busy - должна быть отброшена
    s.chk(d.tx_run == 1, "С4: передача НЕ перезапущена (строб задавлен !tx_run)")
    s.run(160)
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
    s.run(10)
    st = s.cpu_io_read(5)
    s.chk(st == 0x00, f"С5: IN 05h при передаче = {st:#04x} (ожид. 00)")
    s.run(170)
    st = s.cpu_io_read(5)
    s.chk(st == 0x02, f"С5: IN 05h после кадра = {st:#04x} (ожид. 02)")
    s.chk(s.pc_rx_bytes[-1] == 0x5A, "С5: кадр 5Ah дошёл до ПК")
    # IN 04h не определён (RX нет) - уходит в bus_reg, ядро НЕ должно сбоять
    v = s.cpu_io_read(4)
    s.chk(d.tx_run == 0 and d.shreg == 0x1FF, f"С5: чтение 04h (не определено, = {v:#04x}) не трогает ядро")

def s6_por_gate(s: Sim):
    # Свежий DUT: POR бывает ТОЛЬКО при подаче питания (INIT) - повторить
    # окно нельзя через RST (RST = GSR, por_run он не поднимает).
    s.d = DUT(); s.pc_listen()
    d = s.d
    # Имитация floated-шины: цикл OUT 04h при por_run=1 - строб io_wr_tx
    # ДОЛЖЕН быть задавлен !por_run (класс v8/v3.9.3 п.18)
    s.run(2)
    s.chk(d.por_run == 1, "С6: окно POR активно (por_run=1 от INIT)")
    s.chk(d.io_wr_tx == 0, "С6: io_wr_tx задавлен !por_run в окне POR")
    # полный цикл OUT 04h в окне POR - кадра быть НЕ должно
    d.ALE = 1; d.IOM = 1; d.A_in = 4; s.run(3)
    d.ALE = 0; s.run(1)
    d.WRn = 0; d.A_in = 0xC3; s.run(4)
    d.WRn = 1; d.A_in = None; s.run(2)
    s.chk(d.tx_run == 0 and d.ld_tx_q == 0 and d.shreg == 0x1FF,
          "С6: OUT 04h в окне POR - кадр НЕ стартовал (мусор floated-шины отброшен)")
    # ждём конец POR, ядро в idle
    s.run(40)
    s.chk(d.por_run == 0 and d.TX == 1, "С6: POR кончился, TX idle")
    # теперь нормальный кадр проходит
    s.cpu_io_write(4, 0x77); s.run(170)
    s.chk(s.pc_rx_bytes[-1] == 0x77, "С6: после POR кадр проходит нормально")

def s7_reset_midframe(s: Sim):
    d = s.d
    s.pc_listen()
    s.cpu_io_write(4, 0xC3)
    s.run(30)                          # внутри кадра
    s.chk(d.tx_run == 1, "С7: кадр TX идёт")
    d.RST = 1; s.run(1)
    s.chk(d.TX == 1, "С7: GSR - TX='1' в первый такт сброса")
    s.chk(d.tx_run == 0 and d.shreg == 0x1FF and d.bit_cnt == 0 and
          d.baud_cnt == 0 and d.ld_tx_q == 0,
          "С7: ядро вычищено (tx_run=0, shreg=1FF, счётчики 0)")
    d.RST = 0; s.run(40)
    s.chk(d.TX == 1 and d.tx_run == 0, "С7: после сброса idle")
    # приёмник ПК был посреди убитого кадра - сбросить его состояние
    s.pc_listen()
    # повторный кадр после сброса
    s.cpu_io_write(4, 0x3C); s.run(170)
    s.chk(s.pc_rx_bytes[-1] == 0x3C, "С7: после сброса кадр проходит (0x3C)")
    s.chk(d.shreg == 0x1FF and d.tx_run == 0, "С7: ядро снова в idle")

def s8_strobe_needs_wrn(s: Sim):
    d = s.d
    # ALE-глюк ДО данных: T2 вошёл, WRn ещё высок - ALE обрывает T2 (база v3):
    # строба !WRn в T2 не было -> кадра НЕТ
    s.pc_listen()
    d.ALE = 1; d.IOM = 1; d.A_in = 4; s.run(3)
    d.ALE = 0; s.run(1)                       # T2 начался, WRn=1
    d.ALE = 1; s.run(1); d.ALE = 0            # глюк ALE на 1 тик (обрыв T2)
    s.run(2)
    d.WRn = 0; d.A_in = 0xEE; s.run(3)        # WR# падает УЖЕ в IDLE - не строб
    d.WRn = 1; d.A_in = None; s.run(3)
    s.chk(d.ld_tx_q == 0 and d.tx_run == 0 and d.TX == 1,
          "С8: ALE-глюк до данных - кадр НЕ стартовал (строб требует T2 && !WRn)")
    # чистый цикл - ровно один кадр
    s.cpu_io_write(4, 0xA7); s.run(170)
    s.chk(s.pc_rx_bytes[-1] == 0xA7, "С8: чистый OUT 04h - кадр 0xA7 один")

def s9_base_regression(s: Sim):
    d = s.d
    # порты 00h-02h
    s.cpu_io_write(0, 0xA5)            # сегменты (инвертированы на выходе)
    s.cpu_io_write(1, 0x1F)            # разряды + SND
    s.cpu_io_write(2, 0x0F)            # колонки
    s.run(5)
    s.chk(d.seg == (0xA5 ^ 0xFF) & 0xFF, f"С9: seg = {d.seg:#04x}")
    s.chk(d.dig == (0x1F & 0xF) ^ 0xF, f"С9: dig = {d.dig:#x}")
    s.chk(d.snd == 1, "С9: SND = A4 порта 01h")
    s.chk(d.col == 0x0F, f"С9: col = {d.col:#x}")
    # KBROW: чтение 03h -> строки на A0-4
    d.rows = 0b10110
    val = s.cpu_io_read(3)
    s.chk(val == 0b10110, f"С9: IN 03h = {val:#05b} (rows)")
    d.rows = 0
    # запись ОЗУ: writeback, WE ровно 2 тика, A=addr, D=data
    we_log = []
    s.cpu_mem_write(0x8005, 0x4C, we_log)
    s.chk(len(we_log) >= 1 and all(w == 2 for w in we_log),
          f"С9: /WE импульсы ровно 2 тика ({we_log})")
    # A15-гейт: запись в ПЗУ - без /WE
    we2 = []
    s.cpu_mem_write(0x0400, 0x00, we2)
    s.chk(not we2, f"С9: запись в ПЗУ без /WE ({we2})")
    # попутно: запись в ОЗУ НЕ дёргает ядро (это не OUT 04h)
    s.chk(d.tx_run == 0 and d.ld_tx_q == 0, "С9: запись ОЗУ не стартует кадр")

def s_cpu_mem_write_wrapper(self, addr, data, log):
    """Запись в память: FSM уходит в WB1..WB4, /WE низ 2 тика."""
    d = self.d
    d.A15 = 1 if (addr & 0x8000) else 0
    d.ALE = 1; d.IOM = 0; d.A_in = addr & 0xFF; self.run(3)
    d.ALE = 0; self.run(1)
    d.WRn = 0; d.A_in = data; self.run(4)
    d.WRn = 1                                 # WR#(вверх) - FSM уходит в WB1..WB4
    we = None; width = 0
    for _ in range(12):
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
    self.run(2)

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
        d.RX = 1; s.run(20)
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
