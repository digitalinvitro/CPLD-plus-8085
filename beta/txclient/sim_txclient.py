#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sim_txclient.py - цикл-точная проверка v3.10 txclient (beta/txclient).

Моделирует НА ТОЧНОСТЬ RTL-уравнения top_txclient_por6_v310_utf8.v:
  - делитель mod-7 + POR (por_ce = cnt==1|cnt==6, por_sh 8 бит);
  - автомат шины FSM v3.9.2 (7 состояний, ALE-обрыв, wr/rd_seen, WB);
  - регистры портов 00h/01h/02h + чтение 03h (KBROW) и 07h (TXRDY);
  - txclient v3.10: tx_strobe / окно приёма tx_acc (!busy & !stop_q &
    !busy_d) / tx_send_q / busy-маркер / serial_tx (send_reg[9:0],
    send_cnt mod-217, RCONST=216, выход bittick);
  - транзит SID = RX; SOD в логике НЕ используется (проверяется).
Шина 8085: T = 280 нс = 7 тиков 25 МГц; задачи cpu_out/cpu_in имитируют
циклы OUT/IN с длительностями инструкций; fw_putchar - канонический
цикл прошивки «IN; RRC; JC; OUT». Приёмник UART - модель CH340: ресинк
по каждому спаду TX, сэмплы в центрах бит (бит = 217 тиков = 8,68 мкс).
Упрощения: X1/x1_n не моделируются (на txclient не влияют; узел
верифицирован tb_v392_diff.v для v3.9.2); Hi-Z = 0.

КЛЮЧЕВАЯ ПРОВЕРКА СХЕМЫ Б: ни одна перезагрузка (send-импульс) не
попадает в интервал [падение busy, падение busy + 1 бит) = в бит b7
кадра -> порча битов данных невозможна по построению.

Запуск: python3 sim_txclient.py   (self-checking, код возврата 0/1)
"""
import sys

RCONST   = 216          # v3.10: бит = RCONST+1 = 217 тиков
BIT      = RCONST + 1   # тиков на бит (8,68 мкс)
S_IDLE, S_T1H, S_T2, S_WB1, S_WB2, S_WB3, S_WB4 = range(7)

def busy_of(sreg):
    """busy = |({8{send_reg[9]}} ^ send_reg[8:1]) - схема uart.v"""
    m9   = (sreg >> 9) & 1
    body = (sreg >> 1) & 0xFF
    equ  = (0xFF if m9 else 0x00) ^ body
    return 1 if equ else 0

class Sim:
    def __init__(self):
        # пины (сторона теста)
        self.RST = 1; self.ALE = 0; self.WRn = 1; self.RDn = 1
        self.IOM = 0; self.A15 = 0; self.SOD = 0; self.RX = 1
        self.A_tb = None          # None = тест отдал шину (Hi-Z)
        self.D_tb = None
        self.rows = (0, 0, 0, 0, 0)
        # регистры (INIT как в RTL)
        self.cnt = 0; self.por_sh = 0xFF; self.por_run = 1
        self.state = S_IDLE; self.rd_seen = 0; self.wr_seen = 0
        self.addr_latch = 0; self.bus_reg = 0
        self.seg_q = 0xFF; self.dig_q = 0xF; self.snd_q = 0; self.kbcol_q = 0
        self.send_reg = 0x3FF; self.send_cnt = 0
        self.tx_send_q = 0; self.busy_d = 0; self.stop_q = 0
        # телеметрия
        self.t = 0
        self.tx = []              # значение TX на каждом тике
        self.send_pulses = []     # тики импульсов загрузки
        self.busy_falls = []      # тики падения busy (старт бита b7)
        self._busy_prev = 0

    # ---------- разрешение шин (комбинация на текущем состоянии) ----------
    def _dut_a(self):
        """что драйвит CPLD на A-пины (или None)"""
        if self.state == S_T2 and self.rd_seen and not self.RDn and not self.ALE:
            if self.IOM and (self.addr_latch & 7) == 3:      # KBROW
                r = self.rows
                return (r[4] << 4) | (r[3] << 3) | (r[2] << 2) | (r[1] << 1) | r[0]
            if self.IOM and (self.addr_latch & 7) == 7:      # TXRDY (v3.10)
                acc = (not busy_of(self.send_reg)) and not self.stop_q and not self.busy_d
                return 1 if acc else 0
            return self.bus_reg
        if self.state >= S_WB1:                              # writeback
            return self.addr_latch
        return None
    def _dut_d(self):
        return self.bus_reg if self.state >= S_WB1 else None

    def A_net(self):
        dut, tb = self._dut_a(), self.A_tb
        assert dut is None or tb is None or dut == tb, \
            f"конфликт драйверов A: CPLD={dut:02X} CPU={tb:02X} @tick{self.t}"
        return tb if dut is None else dut
    def D_net(self):
        dut, tb = self._dut_d(), self.D_tb
        assert dut is None or tb is None or dut == tb, \
            f"конфликт драйверов D: CPLD={dut:02X} CPU={tb:02X} @tick{self.t}"
        return tb if dut is None else dut

    # ---------- один posedge 25 МГц ----------
    def posedge(self):
        # --- сэмплы ДО фронта ---
        A = self.A_net(); D = self.D_net()
        ale, wrn, rdn, iom, a15 = self.ALE, self.WRn, self.RDn, self.IOM, self.A15
        state, rd_seen, wr_seen = self.state, self.rd_seen, self.wr_seen
        addr_latch, bus_reg = self.addr_latch, self.bus_reg
        cpu_rst = 1 if (self.RST or self.por_run) else 0
        # txclient: строб/окно/busy ДО фронта
        tx_strobe = (state == S_T2 and not wrn and iom
                     and (addr_latch >> 2 & 1) and (addr_latch >> 1 & 1) and (addr_latch & 1))
        tx_busy = busy_of(self.send_reg)
        tx_acc = (not tx_busy) and (not self.stop_q) and (not self.busy_d)
        send_in = self.tx_send_q                       # .send экземпляра
        send_time = (self.send_cnt == RCONST)
        # телеметрия: падение busy = старт бита b7 (запись ПОСЛЕ коммита)
        if tx_busy == 0 and self._busy_prev == 1:
            pass  # (телеметрия ниже, после коммита)

        # --- следующие значения ---
        n_cnt = 0 if self.cnt == 6 else self.cnt + 1
        n_por_sh = ((self.por_sh >> 1) & 0x7F) if ((self.cnt == 1) or (self.cnt == 6)) else self.por_sh
        n_por_run = self.por_sh & 1

        n_state, n_rd, n_wr = state, rd_seen, wr_seen
        n_al, n_br = addr_latch, bus_reg
        n_seg, n_dig, n_snd, n_kbc = self.seg_q, self.dig_q, self.snd_q, self.kbcol_q
        if cpu_rst:
            n_state, n_rd, n_wr, n_al, n_br = S_IDLE, 0, 0, 0, 0
            n_seg, n_dig, n_snd, n_kbc = 0xFF, 0xF, 0, 0
        else:
            if state == S_T1H and ale:
                n_al = A
                if not iom: n_br = D
            if state == S_T2 and not wrn:
                n_br = A
                if iom:
                    p = addr_latch & 7
                    if   p == 0: n_seg = A
                    elif p == 1: n_dig = A & 0xF; n_snd = (A >> 4) & 1
                    elif p == 2: n_kbc = A & 0xF
                    # p==7: txclient - строб ВНЕ case; 3..6: резерв
            if state == S_T2 and not rdn: n_rd = 1
            if state == S_T2 and not wrn: n_wr = 1
            if ale and state == S_T2 and not ((wr_seen and wrn) or (rd_seen and rdn)):
                n_state, n_rd, n_wr = S_IDLE, 0, 0
            else:
                if   state == S_IDLE:
                    if ale: n_state = S_T1H
                elif state == S_T1H:
                    if not ale: n_state = S_T2
                elif state == S_T2:
                    if wr_seen and wrn:
                        n_wr = 0
                        n_state = S_WB1 if ((not iom) and a15) else S_IDLE
                    elif rd_seen and rdn:
                        n_rd = 0; n_state = S_IDLE
                elif state == S_WB1: n_state = S_WB2
                elif state == S_WB2: n_state = S_WB3
                elif state == S_WB3: n_state = S_WB4
                elif state == S_WB4: n_state = S_IDLE

        # --- serial_tx (адаптация uart.v, RCONST=216) ---
        sreg = self.send_reg
        if send_in or send_time:
            if send_in:
                b0   = 0
                body = A & 0xFF                 # sbyte = A (AD0-AD7)
                m9   = (~(A >> 7)) & 1          # !sbyte[7]
                self.send_pulses.append(self.t)
            else:
                b0   = ((sreg >> 1) & 1) | (0 if tx_busy else 1)
                body = (sreg >> 2) & 0xFF
                m9   = (sreg >> 9) & 1
            self.send_reg = (m9 << 9) | (body << 1) | b0
        n_send_cnt = 0 if (send_in or send_time) else self.send_cnt + 1

        # --- окно приёма v3.10 (busy_d/stop_q) + импульс send ---
        n_busy_d = tx_busy
        if   self.busy_d and not tx_busy:                 n_stop_q = 1
        elif self.stop_q and send_time and not tx_busy:   n_stop_q = 0
        else:                                             n_stop_q = self.stop_q
        n_tx_send_q = 1 if (tx_strobe and tx_acc and not self.tx_send_q) else 0

        # --- коммит ---
        self.cnt, self.por_sh, self.por_run = n_cnt, n_por_sh, n_por_run
        self.state, self.rd_seen, self.wr_seen = n_state, n_rd, n_wr
        self.addr_latch, self.bus_reg = n_al, n_br
        self.seg_q, self.dig_q, self.snd_q, self.kbcol_q = n_seg, n_dig, n_snd, n_kbc
        self.send_cnt = n_send_cnt
        self.busy_d, self.stop_q, self.tx_send_q = n_busy_d, n_stop_q, n_tx_send_q
        nb = busy_of(self.send_reg)
        if nb == 0 and self._busy_prev == 1:     # 1->0 между пост-фронтами = падение busy
            self.busy_falls.append(self.t)
        self._busy_prev = nb
        self.t += 1
        self.tx.append(self.send_reg & 1)       # tx = send_reg[0], ПОСЛЕ фронта

    # ---------- выходные пины (комбинация, после фронта) ----------
    def SID(self):  return self.RX              # транзит, не тронут
    def RESET_IN(self): return 0 if (self.RST or self.por_run) else 1
    def seg_out(self): return (~self.seg_q) & 0xFF
    def dig_out(self): return (~self.dig_q) & 0xF
    def cols(self): return self.kbcol_q
    def WE_n(self): return 0 if self.state in (S_WB2, S_WB3) else 1
    def CS_n(self): return 0 if (self.state >= S_WB1 or self.A15 and not self.IOM) else 1
    def TXRDY(self):
        return 1 if ((not busy_of(self.send_reg)) and not self.stop_q and not self.busy_d) else 0

def run(sim, n):
    for _ in range(n): sim.posedge()
def wait_until(sim, t):
    if sim.t < t: run(sim, t - sim.t)

# ---------------- задачи шины 8085 (T = 7 тиков) ----------------
def cpu_out(sim, port, data):
    """OUT nn: T1 адрес, T2 данные + WR# (WR# низ ~12 тиков)"""
    sim.IOM = 1; sim.A_tb = port; sim.ALE = 1; run(sim, 7)       # T1
    sim.ALE = 0; run(sim, 2)                                     # T2
    sim.A_tb = data; sim.WRn = 0; run(sim, 12)                   # WR# низ
    sim.WRn = 1; sim.A_tb = None; run(sim, 2)                    # WR#↑: CPU отпускает AD (~t_DH < такт)
    sim.IOM = 0; run(sim, 6)

def cpu_in(sim, port):
    """IN nn -> (данные, тик сэмпла); CPU отпускает AD после T1"""
    t0 = sim.t
    sim.IOM = 1; sim.A_tb = port; sim.ALE = 1; run(sim, 7)       # T1
    sim.ALE = 0; sim.A_tb = None; run(sim, 2)                    # CPU в Hi-Z
    sim.RDn = 0; run(sim, 8)                                     # RD# низ, T3
    val = sim.A_net(); t_sample = sim.t                          # сэмпл CPU
    sim.RDn = 1; run(sim, 2); sim.IOM = 0; run(sim, 4)
    return val, t_sample

def mem_write(sim, a15, lo, data):
    """цикл записи в память (IOM=0)"""
    sim.IOM = 0; sim.A15 = a15; sim.A_tb = lo; sim.D_tb = 0
    sim.ALE = 1; run(sim, 7)
    sim.ALE = 0; sim.D_tb = None; run(sim, 2)
    sim.A_tb = data; sim.WRn = 0; run(sim, 12)
    sim.WRn = 1; sim.A_tb = None; run(sim, 2)                    # WR#↑: шина CPU
    sim.A15 = 0; run(sim, 6)

# ---------------- приёмник UART (модель CH340) ----------------
def collect_frames(sim, t_from, t_to):
    """приёмник UART: кадр от каждого спада, 10 сэмплов, затем пауза
    до конца стопа; если линия уже 0 (старт следующего кадра начался
    в стопе - ранний reload) - кадр потерян, ждём высокого (консервативно)"""
    st = sim.tx; frames = []
    i = max(0, t_from); hi = min(t_to, len(st))
    while i < hi:
        if st[i] == 0 and (i == 0 or st[i-1] == 1):
            pos_last = i + (BIT * 19) // 2                       # +9.5 бита
            if pos_last >= hi: break
            samples = [st[i + (BIT * (2 * k + 1)) // 2] for k in range(1, 10)]
            byte = sum(samples[j] << j for j in range(8))
            frames.append({'byte': byte, 'stop': samples[8], 'start': i})
            i = pos_last + 1                                     # после стоп-сэмпла
            while i < hi and st[i] == 0: i += 1                  # потерянный старт: до высокого
        else:
            i += 1
    return frames

def edge_widths(sim, t_from, t_to, n=2):
    """первые n ширин между переходами TX (тика)"""
    st = sim.tx; w = []; prev = 1; last = None
    for i in range(max(0, t_from), min(t_to, len(st))):
        if st[i] != prev:
            if last is not None: w.append(i - last)
            last = i; prev = st[i]
            if len(w) >= n: break
    return (w + [None] * n)[:n]

# ---------------- канонический putchar прошивки ----------------
def fw_putchar(sim, ch):
    """IN 07h; RRC; JC; OUT 07h - T-точно: IN=10T(70), RRC=4T(28),
    JC=10T(70)/7T(49), OUT=10T(70), WR# на ~8.5T от старта OUT"""
    while True:
        t_in = sim.t
        val, t_sample = cpu_in(sim, 0x07)
        wait_until(sim, t_in + 70)                               # конец IN
        run(sim, 28)                                             # RRC
        if val & 1:
            run(sim, 70)                                         # JC taken
            wait_until(sim, sim.t + 56)                          # OUT до WR#
            cpu_out(sim, 0x07, ch)
            return t_sample, sim.t                               # (сэмпл, WR#-низ)
        run(sim, 49)                                             # JC not taken

# ================= сценарии =================
class TB:
    def __init__(self):
        self.sim = Sim(); self.ok = 0; self.bad = 0
    def check(self, cond, msg):
        if cond: self.ok += 1; print(f"  PASS: {msg}")
        else:    self.bad += 1; print(f"  FAIL: {msg}")

def main():
    tb = TB(); sim = tb.sim; E = 0

    # ---------- T0: POR и сброс ----------
    print("T0: POR, TX='1', RESET_IN, TXRDY=1")
    run(sim, 60)
    tb.check(sim.RESET_IN() == 0, "RESET_IN=0 в сбросе (POR идёт)")
    tb.check(sim.tx[-1] == 1, "TX='1' в сбросе (INIT send_reg=3FF)")
    sim.RST = 0
    run(sim, 80)                                                 # POR = 1120 нс + запас
    tb.check(sim.RESET_IN() == 1, "RESET_IN=1 после POR")
    val, _ = cpu_in(sim, 0x07)
    tb.check(val == 0x01, f"IN 07h = 01h (TXRDY=1), получено {val:02X}h")
    E = sim.t

    # ---------- T1: одиночный кадр 55h, ширины бит ----------
    print("T1: OUT 07h,55h -> кадр, ширины бит, TXRDY в кадре")
    cpu_out(sim, 0x07, 0x55)
    run(sim, 40)
    val, _ = cpu_in(sim, 0x07)
    tb.check(val == 0x00, f"IN 07h в кадре = 00h (окно закрыто), получено {val:02X}h")
    run(sim, BIT * 10 + 60)
    fr = collect_frames(sim, E, sim.t)
    tb.check(len(fr) == 1 and fr[0]['byte'] == 0x55 and fr[0]['stop'] == 1,
             f"кадр 55h, стоп=1: {[(hex(f['byte']), f['stop']) for f in fr]}")
    w = edge_widths(sim, E, sim.t)
    tb.check(w[0] is not None and abs(w[0] - BIT) <= 2, f"ширина старт-бита {w[0]} (норма {BIT}+-2)")
    tb.check(w[1] is not None and abs(w[1] - BIT) <= 2, f"ширина бита b0 {w[1]} (норма {BIT}+-2)")
    val, _ = cpu_in(sim, 0x07)
    tb.check(val == 0x01, "IN 07h после кадра = 01h (TXRDY=1)")
    E = sim.t

    # ---------- T2: поток по каноническому putchar ----------
    print("T2: поток 'Hello, World!' + спецбайты по TXRDY-поллингу")
    data = [0x48, 0x65, 0x6C, 0x6C, 0x6F, 0x2C, 0x20, 0x57, 0x6F, 0x72,
            0x6C, 0x64, 0x21, 0x00, 0xFF, 0xAA, 0x80, 0x01]
    gaps = []
    for ch in data:
        _, t_wr = fw_putchar(sim, ch)
        gaps.append(t_wr - sim.busy_falls[-1] if sim.busy_falls else 0)
    run(sim, BIT * 12 + 100)
    fr = collect_frames(sim, E, sim.t)
    got = [f['byte'] for f in fr]
    tb.check(got == data, f"поток байт совпал ({len(got)}/{len(data)})" if got == data
             else f"ПОТОК ИСКАЖЁН: {got}")
    tb.check(fr[-1]['stop'] == 1 if fr else False, "последний кадр: стоп=1")
    tb.check(sim.tx[-1] == 1, "TX='1' (idle) в конце")
    if gaps:
        print(f"  информация: WR# от падения busy (старт b7) = "
              f"{min(gaps)*40/1000:.1f}..{max(gaps)*40/1000:.1f} мкс; бит b7 = 8,68 мкс")
    # СТРУКТУРНАЯ ПРОВЕРКА СХЕМЫ Б: ни один send-импульс не попал в
    # [падение busy, падение busy + 1 бит) = в бит b7
    viol = []
    for p in sim.send_pulses:
        for f in sim.busy_falls:
            if f < p < f + BIT: viol.append((f, p))
    tb.check(not viol, f"перезагрузок в бите b7 нет (нарушений: {len(viol)})")
    E = sim.t

    # ---------- T3: перегрузка (вслепую) ----------
    print("T3: два OUT подряд без опроса -> 1 кадр, второй байт потерян")
    cpu_out(sim, 0x07, ord('A')); run(sim, 120); cpu_out(sim, 0x07, ord('B'))
    val, _ = cpu_in(sim, 0x07)                                   # кадр 'A' ещё в полёте
    tb.check(val == 0x00, "TXRDY=0 пока кадр 'A' в полёте (второй байт отклонён)")
    run(sim, BIT * 10 + 60)
    fr = collect_frames(sim, E, sim.t)
    tb.check(len(fr) == 1 and fr[0]['byte'] == ord('A'),
             f"ровно один кадр 'A': {[(hex(f['byte']), f['stop']) for f in fr]}")
    run(sim, BIT * 10)
    fw_putchar(sim, ord('C'))
    run(sim, BIT * 10 + 60)
    fr = collect_frames(sim, E, sim.t)
    tb.check([f['byte'] for f in fr] == [ord('A'), ord('C')],
             f"далее 'A','C' прошли: {[hex(f['byte']) for f in fr]}")
    E = sim.t

    # ---------- T4: SOD мёртв (регрессия против v3.7) ----------
    print("T4: SOD не влияет на TX (транзит удалён)")
    t0 = sim.t
    sim.SOD = 1; run(sim, 80)         # в v3.7 здесь случился бы захват
    sim.SOD = 0; run(sim, 200)        # в v3.7 TX ушёл бы в '0'
    seg = sim.tx[t0:]
    tb.check(all(v == 1 for v in seg), f"TX='1' всё время (SOD 1->0), сэмплов {len(seg)}")
    E = sim.t

    # ---------- T5: транзит SID = RX жив ----------
    print("T5: SID = RX (приём не тронут)")
    sim.RX = 0; run(sim, 3); tb.check(sim.SID() == 0, "RX=0 -> SID=0")
    sim.RX = 1; run(sim, 3); tb.check(sim.SID() == 1, "RX=1 -> SID=1")

    # ---------- T6: порты дисплея/клавиатуры - без кадров ----------
    print("T6: регрессия портов 00h/01h/02h/03h; TX молчит")
    cpu_out(sim, 0x00, 0xA5)
    tb.check(sim.seg_out() == (~0xA5 & 0xFF), f"seg = {sim.seg_out():02X}h (инверсия A5h)")
    cpu_out(sim, 0x01, 0x1F)
    tb.check(sim.dig_out() == 0x0 and sim.snd_q == 1, f"dig={sim.dig_out():X}h, SND=1")
    cpu_out(sim, 0x02, 0b0101)
    tb.check(sim.cols() == 0b0101, "колонки = 0101")
    sim.rows = (1, 0, 1, 0, 1)
    val, _ = cpu_in(sim, 0x03)
    tb.check(val == 0b00010101, f"IN 03h = 15h (rows), получено {val:02X}h")
    cpu_in(sim, 0x04)                                            # резерв: не должен падать
    run(sim, 40)
    fr = collect_frames(sim, E, sim.t)
    tb.check(len(fr) == 0, f"TX молчал (кадров 0): {len(fr)}")
    sim.rows = (0, 0, 0, 0, 0)
    E = sim.t

    # ---------- T7: запись в ОЗУ - WB, без кадров ----------
    print("T7: запись ОЗУ (A15=1): импульс WE, A/D в WB, TX молчит")
    sim.A15 = 1; sim.IOM = 0; sim.A_tb = 0x34; sim.D_tb = 0
    sim.ALE = 1; run(sim, 7)
    sim.ALE = 0; sim.D_tb = None; run(sim, 2)
    sim.A_tb = 0x5A; sim.WRn = 0; run(sim, 12)
    sim.WRn = 1; sim.A_tb = None                                 # WR#↑: шина CPU
    we_lo = 0; wb_a = wb_d = None
    for _ in range(10):                                          # окно на весь WB
        run(sim, 1)
        if sim.WE_n() == 0: we_lo += 1
        if sim.state >= S_WB1 and wb_a is None:                  # сэмпл ВНУТРИ WB
            wb_a, wb_d = sim.A_net(), sim.D_net()
    tb.check(we_lo == 2, f"WE# низ ровно 2 тика (80 нс): {we_lo}")
    tb.check(wb_a == 0x34 and wb_d == 0x5A,
             f"A={wb_a:02X}h D={wb_d:02X}h в WB (адрес/данные)")
    run(sim, 40)
    fr = collect_frames(sim, E, sim.t)
    tb.check(len(fr) == 0, f"TX молчал при записи в память: {len(fr)}")
    sim.A15 = 0; E = sim.t

    # ---------- T8: «запись» в ПЗУ отбрасывается ----------
    print("T8: запись при A15=0 (ПЗУ) - WE молчит, TX молчит")
    mem_write(sim, a15=0, lo=0x11, data=0x99)
    tb.check(sim.WE_n() == 1, "WE# не дёргался")
    fr = collect_frames(sim, E, sim.t)
    tb.check(len(fr) == 0, f"TX молчал: {len(fr)}")
    E = sim.t

    # ---------- T9: RESET кнопкой в середине кадра ----------
    print("T9: RESET в середине кадра: кадр доигрывается, BREAK нет")
    fw_putchar(sim, ord('X'))
    wait_until(sim, sim.send_pulses[-1] + BIT * 3)               # 3 бита от загрузки = середина кадра
    sim.RST = 1; run(sim, 50); sim.RST = 0; run(sim, 80)         # кнопка 2 мкс + POR
    run(sim, BIT * 10)
    fr = collect_frames(sim, E, sim.t)
    tb.check(len(fr) == 1 and fr[0]['byte'] == ord('X'),
             f"кадр 'X' дошёл целиком: {[(hex(f['byte']), f['stop']) for f in fr]}")
    tb.check(sim.tx[-1] == 1, "TX='1' после всего (BREAK отсутствует)")
    E = sim.t

    # ---------- T10: алиас порта 0Fh (декод по A2-A0) ----------
    print("T10: OUT 0Fh = алиас 07h (декод проекта по A2-A0)")
    fw_putchar(sim, 0x5A)                                        # прогрев
    run(sim, BIT * 10)
    E2 = sim.t
    cpu_out(sim, 0x0F, 0x77)
    run(sim, BIT * 10 + 60)
    fr = collect_frames(sim, E2, sim.t)
    tb.check(len(fr) == 1 and fr[0]['byte'] == 0x77,
             f"алиас 0Fh -> кадр 77h: {[(hex(f['byte']), f['stop']) for f in fr]}")
    E = sim.t

    # ---------- T11: кадры при дёргании SOD ----------
    print("T11: кадр при SOD=1 - не зависит")
    sim.SOD = 1
    fw_putchar(sim, 0x3C)
    sim.SOD = 0
    run(sim, BIT * 10 + 60)
    fr = collect_frames(sim, E, sim.t)
    tb.check(len(fr) == 1 and fr[0]['byte'] == 0x3C,
             f"кадр 3Ch прошёл при SOD=1: {[(hex(f['byte']), f['stop']) for f in fr]}")

    # ---------- итог ----------
    total = tb.ok + tb.bad
    print("=" * 62)
    print(f"ИТОГ: {tb.ok}/{total} PASS, {tb.bad} FAIL")
    sys.exit(1 if tb.bad else 0)

if __name__ == "__main__":
    main()
