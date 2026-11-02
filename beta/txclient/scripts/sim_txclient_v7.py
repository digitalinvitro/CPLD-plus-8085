#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_txclient_v7.py - верификация TXCLIENT v7 ДО фита (Icarus в песочнице
недоступен). Цикл-точная модель РОВНО по RTL beta/txclient/top_txclient_v7_utf8.v
(v7 = v6 + СБРОС -> СЕТЬ GSR, п.24: ОБА always-блока асинхронные по RST,
cpu_rst удалён, ДВА гейта !por_run - вход в WB и взвод hold_req; por_run
смоделирован - dut.por_run, GSR-семантика сброса - dut.rst()):
FSM шины v3.9.2 (7 состояний, writeback) + блок txclient v6 (окно 8000h-BFFFh
= A15 & !AH14, п.22; hold_req/hlda_q/cap_run; СЕРИАЛЬНЫЙ захват hi-байта:
9 тиков, bc 0..8, старт-бит заходит через мультиплексор на bc==0; кадры 2/3 -
СЕРИАЛЬНАЯ ПРЕДЗАГРУЗКА во время передачи предыдущего, п.22; v6/п.23:
ИСТОЧНИКИ КАДРОВ СДВИГАЮТСЯ К LSB синхронно с инжекцией - в shreg<8>
инжектируется ОДИН провод (addr_latch[0]/bus_reg[0]), 16-входового
мультиплексора НЕТ; РЕГИСТРОВЫЕ хелперы adv_q/ld_q - п.21; TX = shreg[0] |
cap_run; сериализатор 3 байта 8N1 [hi][lo][data]; фазировка baud_cnt<=1 в
конце захвата - сетка 13 тиков точная; релиз hold_req В КОНЦЕ ПАКЕТА) + гейты
CS_n/CSr_n.
Сценарии: запись ОЗУ (фаза захвата цикл-точна: старт-бит ровно на тике 10 от
первого !WRn, TX='1' всю фазу; кадры hi/lo/data; сетка 13 тиков; зазоры 0),
СДВИГ ИСТОЧНИКОВ (в окне WB регистры ЦЕЛЫ; addr_latch=0 к началу кадра 2,
bus_reg=0 к началу кадра 3 - п.23), вне окна FFxx И C000-FFFF, запись в ПЗУ,
IO-запись, ЧТЕНИЕ ОЗУ (без HOLD вовсе), ложная классификация (защитный
релиз), бэку-ту-бэк, сброс в фазе захвата и посреди пакета, гейты CS в
tx_hold, границы окна BFFF (захват) и C000 (мимо).
НОВОЕ (v7, п.24): T8/T9 сброс = dut.rst() (GSR - МГНОВЕННО, ещё ДО
такта); T13 - hostile-«плавания» шины в окне POR (por_run=1): ноль /WE,
ноль HOLD, ноль TX-активности (гейты !por_run), после POR штатный пакет;
T14 - сброс посреди пакета гасит HOLD мгновенно (GSR, не на такт)."""

import random

BAUD_DIV = 13
WIN_HI, WIN_LO = 0x8000, 0xBFFF   # окно захвата (п.22)
T_T1, T_STROBE = 7, 9            # ALE высок ~7 тиков (1 CLK CPU), !WR ~9 тиков

class DUT:
    """Модель top_txclient v6 (изменённые узлы; делитель/POR/порты не
    моделируются - байт-в-байт v3.9.2 и проверены раньше)."""
    def __init__(self):
        self.state, self.rd_seen, self.wr_seen = 0, 0, 0   # S_IDLE
        self.addr_latch, self.bus_reg = 0x00, 0x00
        self.hold_req = self.hlda_q = self.cap_run = 0     # tx_req УДАЛЁН в v2
        self.tx_byte, self.bit_cnt, self.baud_cnt = 0, 0, 0
        self.shreg = 0x1FF                                 # 9 бит (v4)
        self.adv_q = self.ld_q = 0                         # хелперы п.21
        self.cs_n = self.csr_n = self.we_n = self.oe_n = self.oer_n = 1
        self.hold = 0
        self.tx = 1
        self.ah = 0                       # последний сэмпл AH (для отладки)
        self.por_run = 0                  # v7 (п.24): окно POR (1 = гейты активны)

    def rst(self):
        """v7 (п.24): GSR-сброс - АСИНХРОННЫЙ, мгновенный (не на такт):
        все 62 регистра логики и сериализатора в значения RST-ветки RTL
        (por_sh/por_run вне домена - в модели не ведутся). Выходные
        комбинационные сети обновляются сразу (HOLD = f(hold_req),
        TX = f(shreg, cap_run))."""
        self.state, self.rd_seen, self.wr_seen = 0, 0, 0
        self.addr_latch, self.bus_reg = 0x00, 0x00
        self.hold_req = self.hlda_q = self.cap_run = 0
        self.tx_byte = self.bit_cnt = self.baud_cnt = 0
        self.shreg = 0x1FF
        self.adv_q = self.ld_q = 0
        self.hold = 0
        self.tx = 1

    def tick(self, ale, wrn, rdn, iom, a, d, ah, hl, s0, s1):
        # В RTL txclient - ОТДЕЛЬНЫЙ always-блок: он читает СТАРЫЕ значения
        # state/wr_seen/hold_req/cap_run (неблокирующие присваивания).
        s = self.state                       # старое состояние
        wr_seen_old = self.wr_seen
        hold_req_old = self.hold_req
        tx_byte_old = self.tx_byte
        cap_old = self.cap_run
        bit_cnt_old = self.bit_cnt
        adv_q_old, ld_q_old = self.adv_q, self.ld_q        # хелперы - СТАРЫЕ
        al0_old, br0_old = self.addr_latch & 1, self.bus_reg & 1  # инжекция п.23 -
        # СТАРЫЙ LSB (в RTL оба блока читают старые значения NBA)
        self.ah = ah & 0xFF
        in_wb   = s >= 3                       # S_WB1..S_WB4
        in_welo = s in (4, 5)                  # S_WB2/S_WB3
        wr_phase = s >= 2                      # S_T2..WB4
        rd_drive = (s == 2) and self.rd_seen == 1 and rdn == 0 and ale == 0
        win_hit = (iom == 0) and (ah & 0x80) and (not (ah & 0x40)) and s0 and (not s1)  # окно 8000-BFFF (п.22)
        # --- FSM шины (v3.9.2, байт-в-байт) ---
        # v6 (п.23): сдвиг источников кадров к LSB - в ШИННОМ движке,
        # приоритет НИЖЕ загрузки T1/T2 (else-if, как в RTL); условия по
        # СТАРЫМ adv_q/tx_byte/bit_cnt (оба always-блока читают старое)
        al_shift = adv_q_old and tx_byte_old == 1 and bit_cnt_old >= 2
        br_shift = adv_q_old and tx_byte_old == 2 and bit_cnt_old >= 2
        if s == 1 and ale:
            self.addr_latch = a & 0xFF
            if not iom:
                self.bus_reg = d & 0xFF        # данные памяти (чтение)
        elif al_shift:                         # v6 (п.23): источник кадра 2 едет к LSB
            self.addr_latch = (self.addr_latch >> 1) & 0x7F   # {1'b0, r[7:1]}
        if s == 2 and wrn == 0:
            self.bus_reg = a & 0xFF            # данные записи (A-сети)
        elif br_shift:                         # v6 (п.23): источник кадра 3 едет к LSB
            self.bus_reg = (self.bus_reg >> 1) & 0x7F
        if s == 2 and rdn == 0: self.rd_seen = 1
        if s == 2 and wrn == 0: self.wr_seen = 1
        if ale and s == 2 and not (self.wr_seen and wrn) and not (self.rd_seen and rdn):
            ns, self.rd_seen, self.wr_seen = 0, 0, 0
        else:
            ns = s
            if s == 0:
                if ale: ns = 1
            elif s == 1:
                if not ale: ns = 2
            elif s == 2:
                if self.wr_seen and wrn:
                    self.wr_seen = 0
                    # v7 (п.24): гейт POR - вход в WB запрещён (как v3.9.3)
                    ns = 3 if (not iom and (ah & 0x80) and not self.por_run) else 0
                elif self.rd_seen and rdn:
                    self.rd_seen = 0
                    ns = 0
            elif 3 <= s <= 5: ns = s + 1
            elif s == 6: ns = 0
        self.state = ns
        # --- TXCLIENT v4 (байт-в-байт по RTL) ---
        hlda_in = hl
        baud_tick = 1 if self.baud_cnt == (BAUD_DIV - 1) else 0
        self.baud_cnt = 0 if baud_tick else (self.baud_cnt + 1) & 0xF
        # хелперы п.21: регистрируются КАЖДЫЙ тик из СТАРЫХ значений (как в RTL)
        adv = 1 if (tx_byte_old != 0 and baud_tick) else 0
        ld  = 1 if (adv and bit_cnt_old == 9) else 0
        self.adv_q, self.ld_q = adv, ld
        if cap_old:
            # ФАЗА ЗАХВАТА hi-байта (п.22): вход in_cap по СТАРОМУ bit_cnt
            # (bc 0..8: bc0 = старт-бит '0', bc1..8 = A8..A15 с AH), сдвиг
            # КАЖДЫЙ тик; конец - по bit_cnt(старому)==8 (9-й тик).
            in8 = 0 if bit_cnt_old == 0 else (self.ah >> (bit_cnt_old - 1)) & 1
            self.shreg = ((in8 << 8) | (self.shreg >> 1)) & 0x1FF
            if bit_cnt_old == 8:
                self.cap_run = 0
                self.tx_byte = 1                        # TXB_HI
                self.bit_cnt = 0
                self.baud_cnt = 1                       # ФАЗА под adv_q (п.21):
            else:                                       # сдвиг кадра ровно на 13-м
                self.bit_cnt = (bit_cnt_old + 1) & 0xF  # такте после спада TX
        else:
            txb = self.tx_byte
            if txb == 0:                                   # TXB_IDLE
                # защита от ложного взвода: пакет НЕ стартовал, HLDA пришёл
                if self.hold_req and self.hlda_q and self.state == 0:
                    self.hold_req = 0
            elif txb in (1, 2, 3):                         # TXB_HI/TXB_LO/TXB_DAT
                if adv_q_old:                              # сдвиг бита (И В ТИК ld_q ТОЖЕ -
                    # там adv_q=1): сериальная предзагрузка (п.22) - вход
                    # shreg<8> на тике bc = бит (bc-1) следующего кадра
                    if bit_cnt_old == 0:                   # стоп текущего кадра
                        in8 = 1
                    elif bit_cnt_old == 1:                 # старт следующего (если есть)
                        in8 = 0 if txb in (1, 2) else 1
                    elif txb == 1:                         # кадр 2 (п.23): инжекция ОДНОГО провода
                        in8 = al0_old                      # addr_latch[0] СТАРОГО значения
                    elif txb == 2:                         # кадр 3 (п.23): инжекция ОДНОГО провода
                        in8 = br0_old                      # bus_reg[0] СТАРОГО значения
                    else:                                  # кадра 4 нет - idle
                        in8 = 1
                    self.shreg = ((in8 << 8) | (self.shreg >> 1)) & 0x1FF
                if ld_q_old:                               # конец стоп-бита (+1 такт к baud_tick):
                    self.bit_cnt = 0                       # baud_cnt НЕ трогаем - сетка 13 тиков
                    if txb == 1:
                        self.tx_byte = 2                   # байт 2 (AL) УЖЕ предзагружен
                    elif txb == 2:
                        self.tx_byte = 3                   # байт 3 (D) УЖЕ предзагружен
                    else:
                        self.tx_byte = 0                   # shreg уже все '1' (in_frame кадра 3 льёт '1')
                        self.hold_req = 0                  # РЕЛИЗ В КОНЦЕ ПАКЕТА
                elif adv_q_old:
                    self.bit_cnt = (bit_cnt_old + 1) & 0xF
        # Взвод (T1) и СТАРТ ЗАХВАТА (T2, первый тик !WRn) - ПОСЛЕ case/if;
        # читаем СТАРЫЕ state/hold_req/tx_byte/cap_run (как в RTL):
        # v7 (п.24): гейт POR - floated A/S0/S1 в окне POR не взводят
        # hold_req (иначе HOLD/HLDA в окне POR и мусорный кадр в TX)
        if s == 1 and ale and win_hit and not self.por_run: self.hold_req = 1
        if (s == 2 and wrn == 0 and hold_req_old
                and tx_byte_old == 0 and cap_old == 0):
            self.cap_run = 1                               # ТОЛЬКО взвод (п.22):
            # предзагрузки/очисток НЕТ: старт-бит заходит через in_cap на
            # bc==0, bit_cnt==0 в IDLE - структурный инвариант, baud_cnt
            # фазируется jam'ом <=1 в конце захвата
        self.hlda_q = hlda_in
        # --- выходы: комбинационные сети СЛЕДУЮТ НОВОМУ состоянию ---
        tx_hold = self.hold_req | self.hlda_q
        in_wb_o   = 1 if self.state >= 3 else 0
        in_welo_o = 1 if self.state in (4, 5) else 0
        wr_phase_o = 1 if self.state >= 2 else 0
        self.cs_n  = 0 if in_wb_o else (1 if tx_hold else (0 if (ah & 0x80) else 1))
        self.csr_n = 1 if ((ah & 0x80) or iom or tx_hold) else 0
        self.oe_n  = self.cs_n | wr_phase_o
        self.oer_n = self.csr_n | wr_phase_o
        self.we_n  = 0 if in_welo_o else 1
        self.hold  = self.hold_req
        self.tx    = (self.shreg & 1) | self.cap_run    # TX = shreg[0] | cap_run (п.20/21)
        return self

class Bus:
    """Модель ВМ85А на уровне машинных циклов + память/ввод-вывод."""
    def __init__(self, dut):
        self.dut, self.mem = dut, {}
        self.ale, self.wrn, self.rdn, self.iom = 0, 1, 1, 0
        self.s0, self.s1 = 0, 0                # статус ВМ85А (MW: S0=1,S1=0)
        self.a, self.d, self.ah, self.hl = 0, 0, 0, 0
        self.log_tx = []                       # (tick, tx, hold) каждый тик
        self.t = 0
        self.hlda_seen = 0
        self.wr_first = None                   # первый тик !WRn последнего цикла

    def tick(self):
        self.dut.tick(self.ale, self.wrn, self.rdn, self.iom, self.a, self.d,
                      self.ah, self.hl, self.s0, self.s1)
        self.log_tx.append((self.t, self.dut.tx, self.dut.hold))
        self.t += 1

    def idle(self, n):
        self.ale, self.wrn, self.rdn, self.s0, self.s1 = 0, 1, 1, 0, 0
        for _ in range(n): self.tick()

    def cycle(self, addr, data=None, iom=0, write=1, label=""):
        # T1: адрес; статус ВМ85А: (IO/M, S1, S0): MR/OF = (0,1,0/1),
        # MW = (0,0,1), IOR/IOW = (1,1/0,0/1)
        self.ah = (addr >> 8) & 0xFF
        self.a, self.iom = addr & 0xFF, iom
        if write: self.s0, self.s1 = 1, 0
        else:     self.s0, self.s1 = 0, 1
        self.d = (self.mem.get(addr, 0) if (not iom and not write) else 0)
        hold_at_t1 = None
        self.ale, self.wrn, self.rdn = 1, 1, 1
        for _ in range(T_T1):
            self.tick()
            if hold_at_t1 is None and self.dut.hold: hold_at_t1 = True
        self.ale = 0
        # T2/T3: строб
        self.wrn, self.rdn = (0, 1) if write else (1, 0)
        if write and not iom: self.a = data & 0xFF    # данные по A-сетям
        self.wr_first = self.t                        # первый тик !WRn
        for _ in range(T_STROBE - 1): self.tick()
        self.wrn, self.rdn = 1, 1
        self.s0 = self.s1 = 0
        self.tick()
        if write and not iom and (addr >> 8) & 0xFF >= 0x80:
            self.mem[addr] = data & 0xFF                # ОЗУ приняло (writeback)
        # HOLD/HLDA рукопожатие
        if self.dut.hold:
            for _ in range(2): self.tick()              # CPU замечает HOLD
            self.hl = 1; self.hlda_seen += 1
            while self.dut.hold: self.tick()            # грант активен (в v4 - ВЕСЬ пакет)
            self.release_t = self.t - 1                 # HOLD упал (конец пакета)
            for _ in range(2): self.tick()              # HLDA ещё 2 тика после HOLD=0
            self.hl = 0
        self.events = (label, hold_at_t1)
        self.ah = 0

# ---------- декодер UART (для проверок) ----------
def frames(tx_log, t_from=0):
    """Разбивает журнал TX на кадры 10 бит по переднему фронту старт-бита."""
    ticks = [t for t, v, h in tx_log if t >= t_from and v == 0]
    log = {t: v for t, v, h in tx_log}
    out = []
    i = 0
    while i < len(ticks):
        t0 = ticks[i]
        if out and t0 <= out[-1][2]: i += 1; continue
        bits = []
        for k in range(10):
            tk = t0 + k * BAUD_DIV + BAUD_DIV // 2
            bits.append(log.get(tk, 1))
        end = t0 + 10 * BAUD_DIV
        out.append((bits, t0, end - 1))
        i += 1
    res = []
    for bits, t0, t1 in out:
        val = 0
        for k in range(1, 9):                # data биты 1..8, LSB-первый
            if bits[k]: val |= 1 << (k - 1)
        res.append((bits[0], val, bits[9], t0))
    return res

def bit_lengths_ok(tx_log, t0, div=BAUD_DIV):
    """Все фронты кадра обязаны лежать на сетке t0 + k*div (слияние
    одинаковых соседних бит легитимно - проверяем кратность, не равенство)."""
    log = {t: v for t, v, h in tx_log}
    edges, lvl = [], log.get(t0 - 1, 1)
    for t in range(t0, t0 + 10 * div + 2):
        cur = log.get(t, 1)
        if cur != lvl:
            edges.append(t); lvl = cur
    return edges, all((e - t0) % div == 0 for e in edges)

ok_all = True
def chk(name, cond, detail=""):
    global ok_all
    print(("PASS " if cond else "FAIL ") + name + (("  " + detail) if detail and not cond else ""))
    if not cond: ok_all = False

# ================= T1: запись ОЗУ 8012h <- 5Ah =================
dut, bus = DUT(), None
bus = Bus(dut); bus.idle(10)
bus.cycle(0x8012, 0x5A, write=1, label="ram-write")
rel_t = bus.release_t
bus.idle(600)                              # дать пакету доехать до конца (журнал целиком)
chk("T1: HOLD взведён ещё в T1 (ALE высок)", bus.events[1] is True)
fr = frames(bus.log_tx)
chk("T1: пакет = 3 кадра", len(fr) == 3, str(fr))
if len(fr) == 3:
    chk("T1: байт1 = addr_hi 0x80 (start=0,stop=1) - СЕРИАЛЬНЫЙ захват с AH",
        fr[0][0] == 0 and fr[0][1] == 0x80 and fr[0][2] == 1, str(fr[0][:3]))
    chk("T1: байт2 = addr_lo 0x12 (start=0,stop=1)",
        fr[1][0] == 0 and fr[1][1] == 0x12 and fr[1][2] == 1, str(fr[1][:3]))
    chk("T1: байт3 = data 0x5A (start=0,stop=1)",
        fr[2][0] == 0 and fr[2][1] == 0x5A and fr[2][2] == 1, str(fr[2][:3]))
    chk("T1: между кадрами зазор 0 тиков (сетка 130 точная - фазировка п.21)",
        fr[1][3] - fr[0][3] == 10 * BAUD_DIV and fr[2][3] - fr[1][3] == 10 * BAUD_DIV,
        str([f[3] for f in fr]))
    chk("T1: старт-бит кадра1 ровно на тике 10 от первого !WRn (старт+1 такт state, 9 тиков захвата, п.22)",
        fr[0][3] == bus.wr_first + 10, "f1=%d wr1=%d" % (fr[0][3], bus.wr_first))
    e, grid_ok = bit_lengths_ok(bus.log_tx, fr[0][3])
    chk("T1: все фронты кадра1 на сетке 13 тиков (520 нс)", grid_ok, str(e))
    e2, grid_ok2 = bit_lengths_ok(bus.log_tx, fr[2][3])
    chk("T1: все фронты кадра3 на сетке 13 тиков", grid_ok2, str(e2))
    # v2/v3/v4: HOLD держится ВЕСЬ пакет
    hold_by_t = {t: h for t, v, h in bus.log_tx}
    chk("T1: HOLD='1' на стартах кадров 2 и 3 (релиз только в конце пакета)",
        hold_by_t.get(fr[1][3]) == 1 and hold_by_t.get(fr[2][3]) == 1,
        "h(f2)=%s h(f3)=%s" % (hold_by_t.get(fr[1][3]), hold_by_t.get(fr[2][3])))
    chk("T1: HOLD отпущен в конце стоп-бита кадра3 (+1 такт ld_q, не раньше)",
        fr[2][3] + 9 * BAUD_DIV <= rel_t <= fr[2][3] + 10 * BAUD_DIV + 2,
        "rel=%d f3=%d" % (rel_t, fr[2][3]))
    # TX='1' ВСЮ фазу захвата (джанк сдвига и мультиплексора не виден в линии)
    tx_by_t = {t: v for t, v, h in bus.log_tx}
    chk("T1: TX='1' все тики фазы захвата (гейт cap_run работает)",
        all(tx_by_t.get(bus.wr_first + k) == 1 for k in range(10)),
        str([tx_by_t.get(bus.wr_first + k) for k in range(10)]))
chk("T1: ОЗУ приняло запись (writeback штатно)", bus.mem.get(0x8012) == 0x5A)
chk("T1: после пакета TX idle '1' и HOLD=0", dut.tx == 1 and dut.hold == 0)

# CS-гейты: в tx_hold память выключена; в WB - ОЗУ включена и /WE импульс 2 тика
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(5)
bus.ah = 0x80; bus.a = 0x34; bus.iom = 0; bus.s0, bus.s1 = 1, 0; bus.ale = 1
for _ in range(T_T1): bus.tick()
bus.ale = 0; bus.a = 0x77; bus.wrn = 0
we_hist, cs_hist, csr_hist, txh_hist, st_hist = [], [], [], [], []
for i in range(T_STROBE + 30):
    if i == T_STROBE: bus.wrn = 1          # конец строба -> FSM уходит в WB1..4 -> IDLE
    bus.tick()
    we_hist.append(bus.dut.we_n); cs_hist.append(bus.dut.cs_n); csr_hist.append(bus.dut.csr_n)
    txh_hist.append(bus.dut.hold_req or bus.dut.hlda_q)
    st_hist.append(bus.dut.state)
chk("CS: /WE импульс ровно 2 тика", we_hist.count(0) == 2, str(we_hist))
chk("CS: в WB /CE ОЗУ = 0 (запись состоялась)", any(c == 0 for c in cs_hist))
chk("CS: в WB /WE и /CE совпадают по времени",
    all((w == 0) <= (c == 0) for w, c in zip(we_hist, cs_hist)))
chk("CS: в tx_hold вне WB /CE ОЗУ и ПЗУ = 1 (A15/IOM флоат - декод не работает)",
    all(c == 1 and r == 1 for c, r, h, s in zip(cs_hist, csr_hist, txh_hist, st_hist)
        if h and s == 0),
    str([(c, r) for c, r, h, s in zip(cs_hist, csr_hist, txh_hist, st_hist)
         if h and s == 0][:12]))

# ================= T2: запись ВНЕ ОКНА FFxx (стек fw_mon) =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
bus.cycle(0xFF34, 0x77, write=1, label="excl-write")
bus.idle(100)
chk("T2: HOLD НИКОГДА не взводился (FFxx вне окна 8000-BFFF, п.22)", bus.hlda_seen == 0)
chk("T2: TX всё время '1' (в поток не пишется)", all(v == 1 for _, v, h in bus.log_tx))
chk("T2: ОЗУ приняло запись (логгер прозрачен для шины)", bus.mem.get(0xFF34) == 0x77)

# ================= T3: запись в ПЗУ (страница 12h) =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
bus.cycle(0x1234, 0x99, write=1, label="rom-write")
bus.idle(100)
chk("T3: HOLD НИКОГДА не взводился", bus.hlda_seen == 0)
chk("T3: TX всё время '1'", all(v == 1 for _, v, h in bus.log_tx))
chk("T3: ПЗУ запись отбросила (writeback не запускался)", bus.mem.get(0x1234) is None)

# ================= T4: IO-запись (порт 00h) =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
bus.cycle(0x00, 0xAA, iom=1, write=1, label="io-write")
bus.idle(100)
chk("T4: HOLD НИКОГДА не взводился", bus.hlda_seen == 0)
chk("T4: TX всё время '1'", all(v == 1 for _, v, h in bus.log_tx))

# ================= T5: ЧТЕНИЕ ОЗУ (9000h) - БЕЗ HOLD ВОВСЕ =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
bus.cycle(0x9000, write=0, label="ram-read")
bus.idle(100)
chk("T5: HOLD НИКОГДА не взводился (S0/S1: чтение - ноль издержек)", bus.hlda_seen == 0)
chk("T5: TX всё время '1'", all(v == 1 for _, v, h in bus.log_tx))

# ================= T6: бэку-ту-бэк 8001<-11, 8002<-22 =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
t_before = bus.t
bus.cycle(0x8001, 0x11, write=1, label="ram-1")
bus.cycle(0x8002, 0x22, write=1, label="ram-2")
bus.idle(900)                              # оба пакета до конца
fr = frames(bus.log_tx, t_before)
chk("T6: ровно 2 пакета (6 кадров) без потерь", len(fr) == 6, str([(hex(f[1]), f[3]) for f in fr]))
if len(fr) == 6:
    got = [f[1] for f in fr]
    chk("T6: содержимое [80,01,11] затем [80,02,22]",
        got == [0x80, 0x01, 0x11, 0x80, 0x02, 0x22], str([hex(v) for v in got]))
    starts = [f[3] for f in fr]
    chk("T6: кадры без зазоров внутри пакетов (сетка 130)",
        all(starts[k + 1] - starts[k] == 10 * BAUD_DIV for k in (0, 1, 3, 4)),
        str(starts))
    chk("T6: между пакетами пауза (CPU работал)",
        starts[3] - starts[2] > 10 * BAUD_DIV, str(starts[3] - starts[2]))
chk("T6: обе записи в ОЗУ", bus.mem.get(0x8001) == 0x11 and bus.mem.get(0x8002) == 0x22)

# ================= T7: ложная классификация (статус=запись, строб=чтение) =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
bus.ah = 0x90; bus.a = 0x40; bus.iom = 0
bus.s0, bus.s1 = 1, 0                      # статус "MW" (глюк классификации)
bus.ale, bus.wrn, bus.rdn = 1, 1, 1
for _ in range(T_T1): bus.tick()           # T1: win_hit -> hold_req
chk("T7: HOLD взведён по статусу", dut.hold == 1)
bus.ale = 0
bus.wrn, bus.rdn = 1, 0                    # НО строб - ЧТЕНИЕ (!WRn не придёт)
for _ in range(T_STROBE): bus.tick()
bus.wrn, bus.rdn = 1, 1
for _ in range(2): bus.tick()
bus.hl = 1                                 # CPU грант (hlda_seen тут не ведётся - цикл ручной)
hl_grant = bus.dut.hold == 1               # HOLD ещё активен к моменту гранта
for _ in range(60): bus.tick()             # защитная ветка IDLE должна снять hold_req
chk("T7: защитный релиз без пакета (пинг-понг)",
    hl_grant and dut.hold == 0 and dut.tx == 1, "grant=%s" % hl_grant)
chk("T7: пакета НЕТ - TX всё время '1'", all(v == 1 for _, v, h in bus.log_tx))
bus.hl = 0

# ================= T8: сброс В ФАЗЕ ЗАХВАТА =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(5)
bus.ah, bus.a, bus.iom = 0x80, 0x99, 0
bus.s0, bus.s1 = 1, 0
bus.ale, bus.wrn, bus.rdn = 1, 1, 1
for _ in range(T_T1): bus.tick()
bus.ale = 0; bus.a = 0x66; bus.wrn = 0
for _ in range(4): bus.tick()              # ~3 тика строба: захват уже идёт
chk("T8: захват активен (cap_run=1, TX='1' - гейт держит idle)",
    dut.cap_run == 1 and dut.tx == 1, "cap=%d tx=%d" % (dut.cap_run, dut.tx))
# v7 (п.24): RST = асинхронный GSR-сброс (dut.rst() - мгновенно, не на такт)
dut.rst()
chk("T8: GSR мгновенно: HOLD=0, cap_run=0, TX='1' (ещё ДО такта)",
    dut.hold == 0 and dut.cap_run == 0 and dut.tx == 1)
bus.tick()
chk("T8: после тика HOLD=0, cap_run=0, TX='1'", dut.hold == 0 and dut.cap_run == 0 and dut.tx == 1)
chk("T8: state=IDLE", dut.state == 0)
bus.hl = 0

# ================= T9: сброс посреди пакета =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(5)
bus.ah, bus.a, bus.iom = 0x80, 0x99, 0
bus.s0, bus.s1 = 1, 0
bus.ale, bus.wrn, bus.rdn = 1, 1, 1
for _ in range(T_T1): bus.tick()
bus.ale = 0; bus.a = 0x66; bus.wrn = 0
for _ in range(T_STROBE + 2): bus.tick()
bus.wrn = 1; bus.s0 = bus.s1 = 0; bus.tick()
for _ in range(2): bus.tick()
bus.hl = 1
for _ in range(40): bus.tick()          # пакет уже идёт (кадр 1)
chk("T9: до сброса пакет идёт (TX не idle)", bus.dut.tx_byte != 0, str(bus.dut.tx_byte))
dut.rst()                                 # v7 (п.24): GSR мгновенно
chk("T9: GSR мгновенно: HOLD=0 и TX='1' (ещё ДО такта)", dut.hold == 0 and dut.tx == 1)
bus.tick()
chk("T9: после тика HOLD=0 и TX='1'", dut.hold == 0 and dut.tx == 1)
chk("T9: state=IDLE", dut.state == 0)
bus.hl = 0

# ================= T10: фаза захвата цикл-точна (побитно с AH) =================
# Адрес 0xB37E (в окне 8000-BFFF): A15..A8 = 1,0,1,1,0,0,1,1 - порядок захода
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
bus.cycle(0xB37E, 0x2B, write=1, label="ram-write-b3")
bus.idle(600)
fr = frames(bus.log_tx)
chk("T10: байт1 = 0xB3 (порядок A8->A15 из in_cap)", len(fr) >= 1 and fr[0][1] == 0xB3,
    str([hex(f[1]) for f in fr[:3]]))
chk("T10: байт2 = 0x7E, байт3 = 0x2B", len(fr) >= 3 and fr[1][1] == 0x7E and fr[2][1] == 0x2B,
    str([hex(f[1]) for f in fr[:3]]))
# рука-фаза: cap_run должен идти РОВНО 9 тиков подряд (bc 0..8, п.22)
cap_t = [t for t, v, h in bus.log_tx if dut.cap_run]
chk("T10:phase TX='1' во время всей фазы захвата",
    all(v == 1 for t, v, h in bus.log_tx if t <= bus.wr_first + 9),
    str([(t, v) for t, v, h in bus.log_tx[bus.wr_first:bus.wr_first + 11]]))

# ================= T11: ГРАНИЦЫ ОКНА 8000-BFFF (п.22) =================
# BFFF - последняя строка окна: захват С ПОЛНЫМ адресом (hi=BF)
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
bus.cycle(0xBFFF, 0x9D, write=1, label="win-top")
bus.idle(600)
fr = frames(bus.log_tx)
chk("T11: BFFF захвачен: пакет [BF][FF][9D]", len(fr) == 3 and fr[0][1] == 0xBF
    and fr[1][1] == 0xFF and fr[2][1] == 0x9D, str([(hex(f[1]), f[3]) for f in fr]))
chk("T11: сетка кадров 130 без зазоров",
    len(fr) == 3 and fr[1][3] - fr[0][3] == 10 * BAUD_DIV and fr[2][3] - fr[1][3] == 10 * BAUD_DIV)
# C000 - первая строка ЗА окном: ни HOLD, ни пакета
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
bus.cycle(0xC000, 0x5C, write=1, label="win-out")
bus.idle(100)
chk("T11: C000 - HOLD НИКОГДА (вне окна, п.22)", bus.hlda_seen == 0)
chk("T11: C000 - TX всё время '1'", all(v == 1 for _, v, h in bus.log_tx))
chk("T11: C000 - ОЗУ приняло запись (логгер прозрачен)", bus.mem.get(0xC000) == 0x5C)

# ================= T12: СДВИГ ИСТОЧНИКОВ к LSB (п.23) - структурно =================
# Ручной цикл записи 8012h <- 5Ah с инспекцией регистров: (а) в окне WB
# (WB1..WB4) addr_latch/bus_reg ЦЕЛЫ - сдвиг ещё не начался (старт с bc=2
# первого кадра ~1,9 мкс после WR#(вверх), WB кончается через ~0,2 мкс);
# (б) addr_latch=0 к началу кадра 2, bus_reg=0 к началу кадра 3 (8 бит
# уехали в поток).
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
bus.ah, bus.a, bus.iom = 0x80, 0x12, 0
bus.s0, bus.s1 = 1, 0
bus.ale, bus.wrn, bus.rdn = 1, 1, 1
for _ in range(T_T1): bus.tick()
bus.ale = 0; bus.a = 0x5A; bus.wrn = 0
for _ in range(T_STROBE - 1): bus.tick()
bus.wrn = 1; bus.s0 = bus.s1 = 0
bus.tick()                                  # T2 -> WB1
wb_regs, wb_we, wb_cs = [], [], []
if bus.dut.state == 3:                      # WB1 (сэмпл до цикла)
    wb_regs.append((bus.dut.addr_latch, bus.dut.bus_reg))
    wb_we.append(bus.dut.we_n); wb_cs.append(bus.dut.cs_n)
for _ in range(8):                          # WB1..WB4 (+запас)
    bus.tick()
    if bus.dut.state in (3, 4, 5, 6):
        wb_regs.append((bus.dut.addr_latch, bus.dut.bus_reg))
        wb_we.append(bus.dut.we_n); wb_cs.append(bus.dut.cs_n)
chk("T12: в окне WB (WB1..WB4) регистры ЦЕЛЫ (сдвиг не начался, п.23)",
    len(wb_regs) >= 4 and all(al == 0x12 and br == 0x5A for al, br in wb_regs),
    str(wb_regs))
chk("T12: writeback состоялся (/WE импульс 2 тика, /CE ОЗУ = 0 в те же тики)",
    wb_we.count(0) == 2 and all((w == 0) <= (c == 0) for w, c in zip(wb_we, wb_cs)),
    str(list(zip(wb_we, wb_cs))))
bus.hl = 1                                  # грант - пакет поедет
al_at_f2 = br_at_f3 = al_first_inj = None
while bus.dut.hold:                         # до конца пакета (релиз hold_req)
    if bus.dut.tx_byte == 1 and al_first_inj is None and bus.dut.bit_cnt == 2:
        al_first_inj = bus.dut.addr_latch   # тик 1-й инжекции: регистр ещё цел
    if al_at_f2 is None and bus.dut.tx_byte == 2:
        al_at_f2 = bus.dut.addr_latch
    if br_at_f3 is None and bus.dut.tx_byte == 3:
        br_at_f3 = bus.dut.bus_reg
    bus.tick()
chk("T12: на 1-й инжекции (bc=2 кадра 1) addr_latch ещё цел (0x12)",
    al_first_inj == 0x12, str(al_first_inj))
chk("T12: addr_latch=0 к началу кадра 2 (8 бит уехали в поток, п.23)",
    al_at_f2 == 0, str(al_at_f2))
chk("T12: bus_reg=0 к началу кадра 3 (8 бит уехали в поток, п.23)",
    br_at_f3 == 0, str(br_at_f3))
bus.hl = 0
bus.idle(50)

# ================= T13: hostile-шина В ОКНЕ POR (п.24) =================
# v7: FSM и сериализатор в окне POR ЖИВЫЕ (GSR не активен), шина CPU
# "floated" (ВМ85А: управления/адрес/данные в 3-м состоянии) - гейты
# !por_run обязаны держать ноль /WE (гейт S_T2->WB1), ноль HOLD (гейт
# взвода hold_req), ноль TX-активности (cap_run возможен только при
# hold_req=1). 3000 тактов случайных «плаваний» - методика sim_v393_gsr.py.
dut, bus = DUT(), None; bus = Bus(dut)
dut.por_run = 1
we_lo = hold_hi = tx_act = cap_se = hr_se = wb_se = 0
random.seed(20261103)
for _ in range(3000):
    bus.ale = random.randint(0, 1)
    bus.wrn = random.randint(0, 1)
    bus.rdn = random.randint(0, 1)
    bus.iom = random.randint(0, 1)
    bus.a, bus.ah = random.randint(0, 255), random.randint(0, 255)
    bus.s0, bus.s1 = random.randint(0, 1), random.randint(0, 1)
    bus.hl = random.randint(0, 1)
    bus.tick()
    we_lo += (bus.dut.we_n == 0)
    hold_hi += (bus.dut.hold == 1)
    tx_act += (bus.dut.tx == 0)
    cap_se += (bus.dut.cap_run == 1)
    hr_se += (bus.dut.hold_req == 1)
    wb_se += (bus.dut.state in (3, 4, 5, 6))
chk("T13: POR-окно: /WE НИКОГДА (гейт S_T2->WB1, п.24)", we_lo == 0, str(we_lo))
chk("T13: POR-окно: HOLD НИКОГДА (гейт взвода hold_req, п.24)", hold_hi == 0, str(hold_hi))
chk("T13: POR-окно: TX-активности НЕТ", tx_act == 0, str(tx_act))
chk("T13: POR-окно: cap_run/hold_req НИКОГДА", cap_se == 0 and hr_se == 0,
    "cap=%d hr=%d" % (cap_se, hr_se))
chk("T13: POR-окно: FSM живая (WB1..4 недостижимы)", wb_se == 0, str(wb_se))
dut.por_run = 0                            # POR кончился (por_run -> 0)
bus.idle(5)
bus.cycle(0x8012, 0x5A, write=1, label="post-por")
bus.idle(600)
fr = frames(bus.log_tx)
chk("T13: после POR штатная запись -> пакет [80][12][5A]",
    len(fr) == 3 and [f[1] for f in fr] == [0x80, 0x12, 0x5A],
    str([(hex(f[1]), f[3]) for f in fr[:4]]))
chk("T13: ОЗУ приняло запись", bus.mem.get(0x8012) == 0x5A)

# ================= T14: сброс посреди пакета - GSR МГНОВЕННО (п.24) =====
# В RTL сброс асинхронный (posedge clk or posedge RST): нажатие SW20 гасит
# FSM/пакет БЕЗ ожидания такта (v6 - на такт позже). Проверяем ДО такта.
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(5)
bus.ah, bus.a, bus.iom = 0x80, 0x99, 0
bus.s0, bus.s1 = 1, 0
bus.ale, bus.wrn, bus.rdn = 1, 1, 1
for _ in range(T_T1): bus.tick()
bus.ale = 0; bus.a = 0x66; bus.wrn = 0
for _ in range(T_STROBE + 2): bus.tick()
bus.wrn = 1; bus.s0 = bus.s1 = 0; bus.tick()
for _ in range(2): bus.tick()
bus.hl = 1
for _ in range(40): bus.tick()
chk("T14: до сброса пакет идёт (tx_byte != IDLE, HOLD=1)",
    bus.dut.tx_byte != 0 and bus.dut.hold == 1,
    "txb=%d hold=%d" % (bus.dut.tx_byte, bus.dut.hold))
dut.rst()                                  # GSR: без такта
chk("T14: GSR мгновенно: HOLD=0, TX='1', state=IDLE, shreg=1FF (ДО такта)",
    dut.hold == 0 and dut.tx == 1 and dut.state == 0 and dut.shreg == 0x1FF)
bus.tick()
chk("T14: после тика состояние держится", dut.hold == 0 and dut.tx == 1 and dut.state == 0)
bus.hl = 0
bus.idle(20)

print()
print("ИТОГ:", "ВСЕ ПАСС" if ok_all else "ЕСТЬ ПРОВАЛЫ")
raise SystemExit(0 if ok_all else 1)
