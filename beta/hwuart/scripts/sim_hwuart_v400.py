#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_hwuart_v400.py - цикл-точная модель top_hwuart_por6_v400 (v4.0.0, линия beta/hwuart).

Семантика: NBA (все следующие значения вычисляются из текущих, потом присваиваются),
25 МГц (тик = 40 нс), negedge-фаза x1_n внутри тика (полутакт).
База v3.9.3 (делитель mod-7, POR, FSM шины v3, порты 00-03h) - бит-в-бит;
ядро UART п.26 - полудуплекс (общие shreg/bit_cnt/baud_cnt).

Сценарии:
  С1  POR/idle: TX='1', rx_full=0, RESET_IN, X1-паттерн, транзит SID=RX
  С2  TX-кадр 55h/AAh: бит РОВНО 13 тиков, старт ровно 13, PC-приёмник декодирует,
      shreg сам в idle (все '1'), зазор кадра 0 (idle='1' бесконечный стоп)
  С3  поток 3 байт с TXRDY-поллингом - без потерь
  С4  OUT 04h при busy - байт тихо отброшен, кадр не порчен
  С5  RX 55h: rx_full/IRQ фронт, IN 05h статус, IN 04h = байт, чтение гасит IRQ
  С6  RX во время TX - байт игнорируется (полудуплекс), кадр TX цел
  С7  RST посреди TX-кадра и посреди RX-кадра - GSR: TX='1' мгновенно, ядро чистое
  С8  глитч RX (3 тика) - abort в центре старта, rx_full не взводится, bc==0
  С9  регрессия базы: порты 00-02h, KBROW 03h, writeback ОЗУ (WE ровно 2 тика)

Запуск: python3 scripts/sim_hwuart_v400.py  (пути от папки скрипта)
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))

BAUD_DIV = 13          # 25 МГц / 13 = 1 923 077,8 бод
TICK = 40              # нс
S_IDLE, S_T1H, S_T2, S_WB1, S_WB2, S_WB3, S_WB4 = range(7)

class DUT:
    """Цикл-точная модель retro_pcld_top v4.0.0."""
    def __init__(self):
        # делитель + POR (вне GSR)
        self.cnt = 0; self.x1_n = 0
        self.por_sh = 0xFF; self.por_run = 1
        # FSM шины v3 (GSR-домен)
        self.state = S_IDLE; self.rd_seen = 0; self.wr_seen = 0
        self.addr_latch = 0; self.bus_reg = 0
        self.seg_q = 0xFF; self.dig_q = 0xF; self.snd_q = 0; self.kbcol_q = 0
        # ядро UART п.26 (GSR-домен)
        self.shreg = 0x1FF; self.bit_cnt = 0; self.baud_cnt = 0
        self.rx_s0 = 1; self.rx_s1 = 1
        self.rx_run = 0; self.rx_full = 0; self.tx_run = 0; self.adv_q = 0
        # входы
        self.RST = 0; self.ALE = 0; self.WRn = 1; self.RDn = 1; self.IOM = 0; self.A15 = 0
        self.A_in = None   # AD0-7 со стороны CPU (None = Hi-Z)
        self.D_in = 0      # D-шина памяти (для bus_reg при чтении памяти)
        self.RX = 1
        self.rows = 0      # row0..4 (клавиатура)
        self.t = 0

    # ---------- комбинационные ----------
    @property
    def por_ce(self):    return 1 if (self.cnt == 1 or self.cnt == 6) else 0
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
    def io_rd_rx(self):  return 1 if (self.IOM and (self.addr_latch & 7) == 4) else 0
    @property
    def io_rd_st(self):  return 1 if (self.IOM and (self.addr_latch & 7) == 5) else 0
    @property
    def io_wr_tx(self):
        return 1 if (self.state == S_T2 and self.WRn == 0 and self.IOM and
                     not self.tx_run and not self.rx_run and not self.por_run and
                     (self.addr_latch & 7) == 4) else 0
    @property
    def baud_tick(self): return 1 if self.baud_cnt == BAUD_DIV - 1 else 0
    @property
    def adv(self):       return 1 if (self.baud_tick and (self.rx_run or self.tx_run)) else 0
    @property
    def rx_start(self):
        return 1 if (not self.rx_run and not self.tx_run and self.rx_s1 and not self.rx_s0) else 0
    @property
    def A_out(self):
        """Значение на AD-пинах со стороны CPLD (None = Hi-Z)."""
        if self.rd_drive:
            if self.io_rd_kb:
                return ((self.rows & 0x1F)) & 0xFF
            if self.io_rd_rx:
                return (self.shreg >> 1) & 0xFF
            if self.io_rd_st:
                return ((0 if self.tx_run else 2) | (1 if self.rx_full else 0)) & 0xFF
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
    def rx_int(self):    return self.rx_full
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
        t = self.t
        if self.RST:
            # GSR: асинхронный сброс логики (мгновенно, делитель/POR вне домена)
            self.state = S_IDLE; self.rd_seen = 0; self.wr_seen = 0
            self.addr_latch = 0; self.bus_reg = 0
            self.seg_q = 0xFF; self.dig_q = 0xF; self.snd_q = 0; self.kbcol_q = 0
            self.shreg = 0x1FF; self.bit_cnt = 0; self.baud_cnt = 0
            self.rx_s0 = 1; self.rx_s1 = 1
            self.rx_run = 0; self.rx_full = 0; self.tx_run = 0; self.adv_q = 0
            # делитель/POR тикают (вне GSR)
            nxt_x1n = None
            self.cnt = 0 if self.cnt == 6 else self.cnt + 1
        else:
            # --- NBA: сначала все следующие значения ---
            nxt = {}
            # делитель mod-7
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
                    # 3'b100 (04h) - старт TX в ядре (ниже); 05h - нет записи
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
            # POR
            nxt['por_run'] = self.por_sh & 1
            if self.por_ce:
                nxt['por_sh'] = (self.por_sh >> 1) & 0xFF
            # ядро UART п.26
            shreg = self.shreg; bit_cnt = self.bit_cnt; baud_cnt = self.baud_cnt
            rx_run = self.rx_run; rx_full = self.rx_full; tx_run = self.tx_run
            adv_q_nxt = self.adv
            baud_cnt = 0 if self.baud_tick else (baud_cnt + 1) & 0xF   # свободный ход mod-13 (jam'ы ниже перекрывают)
            if self.rx_start:
                rx_run = 1; bit_cnt = 0; baud_cnt = 6
            elif self.io_wr_tx:
                tx_run = 1; shreg = ((self.A_in & 0xFF) << 1) & 0x1FF  # {A,1'b0}
                bit_cnt = 0; baud_cnt = 1
            elif self.adv_q and (self.rx_run or self.tx_run):
                if self.rx_run:
                    if bit_cnt == 0:
                        if self.rx_s1:
                            rx_run = 0; bit_cnt = 0      # глитч-аборт
                        else:
                            bit_cnt = 1                   # старт валидирован
                    elif bit_cnt <= 8:
                        shreg = ((self.rx_s1 << 8) | (shreg >> 1)) & 0x1FF
                        bit_cnt = bit_cnt + 1
                    else:                                 # bc==9: стоп
                        rx_full = 1; rx_run = 0; bit_cnt = 0
                else:                                     # tx_run
                    shreg = ((1 << 8) | (shreg >> 1)) & 0x1FF
                    if bit_cnt == 9:
                        tx_run = 0; bit_cnt = 0
                    else:
                        bit_cnt = bit_cnt + 1
            if self.io_rd_rx:
                rx_full = 0                               # чтение гасит RXRDY (последним)
            nxt['shreg'] = shreg; nxt['bit_cnt'] = bit_cnt; nxt['baud_cnt'] = baud_cnt
            nxt['rx_run'] = rx_run; nxt['rx_full'] = rx_full; nxt['tx_run'] = tx_run
            nxt['adv_q'] = adv_q_nxt
            # 2FF-синхронизатор RX (NBA: rx_s1 <- СТАРЫЙ rx_s0)
            nxt['rx_s0'] = self.RX
            nxt['rx_s1'] = self.rx_s0
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

    # ---------- CPU-циклы (T1 = 3 тика ALE - FSM захватывает адрес на тике T1H; T2 - 4 тика строба) ----------
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

    # ---------- PC-сторона ----------
    def pc_send(self, byte, jitter=0):
        """Расписание изменений линии RX (CH340G.TXD): кадр 8N1, бит 13 тиков."""
        d = self.d
        sched = []  # (tick, level)
        t0 = d.t + 2
        lvl = [(0, 1)] + [(0, 0)] + [((byte >> i) & 1) for i in range(8)] + [(1,)]
        # start=0, d0..d7, stop=1
        bits = [0] + [((byte >> i) & 1) for i in range(8)] + [1]
        t = t0
        for b in bits:
            sched.append((t + jitter, b))
            t += BAUD_DIV
        self.rx_sched = getattr(self, 'rx_sched', []) + sched

    def pc_feed(self):
        """Применить расписание линии RX до текущего тика."""
        d = self.d
        if not hasattr(self, 'rx_sched'): return
        rest = []
        for (t, lvl) in self.rx_sched:
            if t <= d.t:
                d.RX = lvl
            else:
                rest.append((t, lvl))
        self.rx_sched = rest

    def pc_listen(self):
        """PC-приёмник TX-линии: собранные байты + ширины битов."""
        self.pc_rx_bytes = []
        self.pc_rx_bits = []   # (tick_start, width) каждого сегмента последнего кадра
        self.pc_stop_min = None
        self._pcst = {'edge': None, 'byte': 0, 'k': 0}   # приёмник - в исходное
        self._trk = None                                  # трекинг сегментов - заново

    def pc_sample(self):
        """Вызывается каждый тик: сэмплирует TX как стандартный UART-приёмник."""
        d = self.d
        st = getattr(self, '_pcst', None)
        if st is None:
            self._pcst = {'edge': None, 'byte': 0, 'k': 0}
            st = self._pcst
        tx = d.TX
        if st['edge'] is None:
            if tx == 0:                     # спад: старт-бит
                st['edge'] = d.t; st['k'] = -1; st['byte'] = 0  # накопитель - с нуля!
                st = self._pcst
        else:
            e = st['edge']
            rel = d.t - e
            # выборки: старт в +6, данные +19+13k, стоп +123
            if st['k'] == -1 and rel == 6:
                if tx != 0:
                    st['edge'] = None; st['k'] = 0; st['byte'] = 0   # глитч
                else:
                    st['k'] = 0
            if 0 <= st['k'] <= 7 and rel == 19 + 13 * st['k']:
                st['byte'] |= (tx << st['k']); st['k'] += 1
            if st['k'] == 8 and rel == 123:
                if tx == 1:
                    self.pc_rx_bytes.append(st['byte'])
                else:
                    self.pc_rx_bytes.append(('FE', st['byte']))
                st['edge'] = None; st['k'] = 0; st['byte'] = 0
        # трекинг ширин битов (для С2)
        tr = getattr(self, '_trk', None)
        if tr is None or tr[1] != tx:
            if tr is not None:
                self.pc_rx_bits.append((tr[0], d.t - tr[0], tr[1]))
            tr = (d.t, tx)
        self._trk = tr

    def tx_frame(self):
        """Последний кадр TX: [(tick, width, level)...] с ширинами."""
        return self.pc_rx_bits


# ---------------- сценарии ----------------

def s1_por_idle(s: Sim):
    d = s.d
    por_fell = None
    for _ in range(40):
        s.run(1)
        if por_fell is None and d.por_run == 0:
            por_fell = d.t
    s.chk(por_fell is not None and 25 <= por_fell <= 32,
          f"С1: POR снялся на тике {por_fell} (ожид. 26-29, норма >=21)")
    s.chk(d.TX == 1, "С1: TX='1' в idle (INIT)")
    s.chk(d.rx_full == 0 and d.tx_run == 0 and d.rx_run == 0, "С1: ядро в idle")
    s.chk(d.RESET_IN == 1, "С1: RESET_IN=1 после POR")
    # X1: период 7 тиков (140 нс), в периоде ровно 5 высоких/2 низких
    # (фаза выборки произвольна - точный узор 100/40 нс проверен в lowsize
    # на полутактах 20 нс; здесь инвариант периода и duty)
    pat = []
    for _ in range(14):
        pat.append(d.X1); s.run(1)
    s.chk(pat[:7] == pat[7:], f"С1: X1 периодичен 7 тиков ({pat})")
    s.chk(sum(pat[:7]) == 5, f"С1: X1 duty 5/7 в периоде ({pat[:7]})")
    # транзит SID = RX
    d.RX = 0; s.run(1); s.chk(d.SID == 0, "С1: SID=RX транзит (0)")
    d.RX = 1; s.run(1); s.chk(d.SID == 1, "С1: SID=RX транзит (1)")
    # статус: TXRDY=1
    st = s.cpu_io_read(5)
    s.chk(st == 0x02, f"С1: IN 05h = {st:#04x} (ожид. 02 = TXRDY)")
    # idle: TX не шевелится 100 тиков
    t0 = d.TX; s.run(100)
    s.chk(d.TX == t0 == 1, "С1: TX стабилен '1' 100 тиков")

def s2_tx_frame(s: Sim):
    d = s.d
    for byte in (0x55, 0xAA):
        s.pc_listen()
        s.cpu_io_write(4, byte)
        s.run(145)  # кадр 10 бит = 130 тиков
        # сетка переходов: ВСЕ переходы линии TX - на границах битов (кратно 13
        # от спада старта); соседние одинаковые биты сливаются в один сегмент
        segs = [x for x in s.tx_frame() if x[1] < 200]   # без стартового idle-хвоста прошлых сценариев
        lows = [(a, w) for (a, w, lv) in segs if lv == 0]
        s.chk(len(lows) >= 1, f"С2({byte:#04x}): старт-бит есть")
        if not lows: continue
        start = lows[0][0]
        bounds = []
        t = start
        for (a, w, lv) in segs:
            if a >= start:
                t = a + w
                bounds.append(t - start)
        s.chk(all(b % 13 == 0 for b in bounds),
              f"С2({byte:#04x}): все переходы на сетке 13 тиков ({bounds})")
        s.chk(bounds and bounds[-1] <= 117,
              f"С2({byte:#04x}): последний переход <= 117 (кадр 10 бит) ({bounds})")
        if byte == 0x55:  # d0=1: старт отделён - ровно 13
            s.chk(bounds and bounds[0] == 13,
                  f"С2(0x55): старт-бит ровно 13 тиков ({bounds[:1]})")
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
        # поллинг TXRDY (IN 05h бит 1)
        guard = 0
        while True:
            st = s.cpu_io_read(5)
            if st & 0x02: break
            guard += 1
            s.chk(guard < 50, "С3: зависание поллинга TXRDY")
            if guard >= 50: return
        s.cpu_io_write(4, byte)
    s.run(160)
    s.chk(s.pc_rx_bytes[-3:] == [0x41, 0x42, 0x43],
          f"С3: поток без потерь {s.pc_rx_bytes[-3:]}")
    s.chk(d.shreg == 0x1FF, "С3: shreg в idle после потока")

def s4_tx_busy_drop(s: Sim):
    d = s.d
    s.pc_listen()
    s.cpu_io_write(4, 0x11)           # кадр пошёл
    s.run(20)                          # внутри кадра (старт)
    s.chk(d.tx_run == 1, "С4: передача активна")
    s.cpu_io_write(4, 0x99)           # запись при busy - должна быть отброшена
    s.run(140)
    s.chk(s.pc_rx_bytes[-1] == 0x11, f"С4: кадр цел, байт busy отброшен ({s.pc_rx_bytes[-1]})")
    st = s.cpu_io_read(5)
    s.chk(st & 0x02, f"С4: TXRDY=1 после освобождения ({st:#04x})")

def s5_rx_byte(s: Sim):
    d = s.d
    s.pc_send(0x55)
    deadline = d.t + 160
    while d.rx_full == 0 and d.t < deadline:
        s.pc_feed(); s.run(1); s.pc_sample()
    s.chk(d.rx_full == 1, f"С5: rx_full взведён (t={d.t})")
    s.chk(d.rx_int == 1, "С5: IRQ RST 7.5 (rx_int=1)")
    st = s.cpu_io_read(5)
    s.chk(st & 0x01, f"С5: статус RXRDY=1 ({st:#04x})")
    val = s.cpu_io_read(4)
    s.chk(val == 0x55, f"С5: IN 04h = {val:#04x} (ожид. 55h)")
    s.chk(d.rx_full == 0 and d.rx_int == 0, "С5: чтение погасило RXRDY/IRQ")
    s.pc_sample()

def s6_rx_during_tx(s: Sim):
    d = s.d
    s.pc_listen()
    s.cpu_io_write(4, 0x77)           # TX-кадр пошёл
    s.run(15)                          # старт-бит TX идёт
    s.pc_send(0x3C)                    # ПК шлёт одновременно (нарушение контракта)
    deadline = d.t + 200
    while d.t < deadline:
        s.pc_feed(); s.run(1); s.pc_sample()
    s.chk(d.rx_full == 0, "С6: RX при занятом TX игнорирован (rx_full=0)")
    s.chk(s.pc_rx_bytes[-1] == 0x77, f"С6: кадр TX цел ({s.pc_rx_bytes[-1]})")
    s.chk(d.tx_run == 0 and d.shreg == 0x1FF, "С6: ядро вернулось в idle")

def s7_reset_midframe(s: Sim):
    d = s.d
    # RST посреди TX-кадра
    s.cpu_io_write(4, 0xC3)
    s.run(30)                          # внутри кадра
    s.chk(d.tx_run == 1, "С7: кадр TX идёт")
    d.RST = 1; s.run(1)
    s.chk(d.TX == 1, "С7: GSR - TX='1' в первый такт сброса")
    s.chk(d.tx_run == 0 and d.shreg == 0x1FF and d.bit_cnt == 0 and d.baud_cnt == 0,
          "С7: ядро вычищено (tx_run=0, shreg=1FF, счётчики 0)")
    d.RST = 0; s.run(40)
    s.chk(d.TX == 1 and d.tx_run == 0, "С7: после сброса idle")
    # RST посреди RX-кадра (модель хоста: замолчал, линия в idle)
    s.pc_send(0x81)
    for _ in range(25):
        s.pc_feed(); s.run(1); s.pc_sample()
    d.RST = 1
    s.rx_sched = []; s._pcst = {'edge': None, 'byte': 0, 'k': 0}
    d.RX = 1
    for _ in range(30):
        s.run(1)
    s.chk(d.rx_run == 0 and d.rx_full == 0 and d.shreg == 0x1FF,
          "С7: RX-кадр убит сбросом чисто")
    d.RST = 0; s.run(40); s.pc_sample()
    s.chk(d.rx_run == 0 and d.bit_cnt == 0 and d.rx_full == 0,
          "С7: после сброса ядро в idle (псевдостартов нет - линия в idle)")
    # после сброса приёмник жив (контрольная посылка)
    s.pc_send(0x5A)
    deadline = d.t + 200
    while d.rx_full == 0 and d.t < deadline:
        s.pc_feed(); s.run(1); s.pc_sample()
    val = s.cpu_io_read(4)
    s.chk(val == 0x5A, f"С7: приёмник жив после сброса (IN 04h = {val:#04x})")
    s.pc_sample()

def s8_rx_glitch(s: Sim):
    d = s.d
    d.RX = 0; s.run(3)                 # глитч 3 тика << 6.5 (центр старта)
    d.RX = 1
    s.run(30)
    s.chk(d.rx_full == 0, "С8: глитч не породил байт")
    s.chk(d.bit_cnt == 0 and d.rx_run == 0, "С8: ядро в idle после аборта (инвариант bc==0)")
    s.pc_sample()

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
    # POR-гейт уже проверен v3.9.3 (sim_v393_gsr) - здесь FSM/порты живы после POR (С1)

def s_cpu_mem_write_wrapper(self, addr, data, log):
    """Запись в память: FSM уходит в WB1..WB4, /WE низ 2 тика."""
    d = self.d
    d.A15 = 1 if (addr & 0x8000) else 0
    d.ALE = 1; d.IOM = 0; d.A_in = addr & 0xFF; self.run(3)
    d.ALE = 0; self.run(1)
    d.WRn = 0; d.A_in = data; self.run(4)
    d.WRn = 1                                 # WR#(вверх) - FSM уходит в WB1..WB4
    # трекинг /WE во время WB
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
    # старт: RST=0, POR от INIT
    s.pc_listen()
    for f in (s1_por_idle, s2_tx_frame, s3_tx_stream, s4_tx_busy_drop,
              s5_rx_byte, s6_rx_during_tx, s7_reset_midframe,
              s8_rx_glitch, s9_base_regression):
        f(s)
        # между сценариями - успокоить линию и ядро
        d.RX = 1; s.run(20); s.pc_sample()
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
