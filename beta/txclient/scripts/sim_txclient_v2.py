#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_txclient_v2.py - верификация TXCLIENT v2 ДО фита (Icarus в песочнице
недоступен). Цикл-точная модель РОВНО по RTL beta/txclient/top_txclient_v2_utf8.v:
FSM шины v3.9.2 (7 состояний, writeback) + блок txclient v2 (win_hit по S0/S1,
hold_req/hlda_q, старт пакета в T2 - hi-байт ПРЯМО В shreg, сериализатор
3 байта 8N1 [A15..A8][A7..A0][data], релиз hold_req В КОНЦЕ ПАКЕТА) + гейты
CS_n/CSr_n.
Сценарии: запись ОЗУ (тайминги бит/содержимое/HOLD на весь пакет), страница-
исключение FFxx, запись в ПЗУ, IO-запись, ЧТЕНИЕ ОЗУ (без HOLD вообще!),
ложная классификация (защитный релиз), бэку-ту-бэк, сброс посреди пакета,
гейты CS в tx_hold."""

BAUD_DIV = 13
EXCL_PAGE = 0xFF
T_T1, T_STROBE = 7, 9            # ALE высок ~7 тиков (1 CLK CPU), !WR ~9 тиков

class DUT:
    """Модель top_txclient v2 (изменённые узлы; делитель/POR/порты не
    моделируются - байт-в-байт v3.9.2 и проверены раньше)."""
    def __init__(self):
        self.state, self.rd_seen, self.wr_seen = 0, 0, 0   # S_IDLE
        self.addr_latch, self.bus_reg = 0x00, 0x00
        self.hold_req = self.hlda_q = 0                    # tx_req УДАЛЁН в v2
        self.tx_byte, self.bit_cnt, self.baud_cnt = 0, 0, 0
        self.shreg = 0x3FF
        self.cs_n = self.csr_n = self.we_n = self.oe_n = self.oer_n = 1
        self.hold = 0
        self.tx = 1

    def tick(self, ale, wrn, rdn, iom, a, d, ah, hl, s0, s1):
        # В RTL txclient - ОТДЕЛЬНЫЙ always-блок: он читает СТАРЫЕ значения
        # state/wr_seen/hold_req (неблокирующие присваивания). В модели
        # фиксируем их до обновлений (порядок секций имитирует 2 блока).
        s = self.state                       # старое состояние
        wr_seen_old = self.wr_seen
        hold_req_old = self.hold_req
        tx_byte_old = self.tx_byte
        in_wb   = s >= 3                       # S_WB1..S_WB4
        in_welo = s in (4, 5)                  # S_WB2/S_WB3
        wr_phase = s >= 2                      # S_T2..WB4
        rd_drive = (s == 2) and self.rd_seen == 1 and rdn == 0 and ale == 0
        win_hit = (iom == 0) and (ah & 0x80) and s0 and (not s1) and (ah != EXCL_PAGE)
        # --- FSM шины (v3.9.2, байт-в-байт) ---
        if s == 1 and ale:
            self.addr_latch = a & 0xFF
            if not iom:
                self.bus_reg = d & 0xFF        # данные памяти (чтение)
        if s == 2 and wrn == 0:
            self.bus_reg = a & 0xFF            # данные записи (A-сети)
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
                    ns = 3 if (not iom and (ah & 0x80)) else 0
                elif self.rd_seen and rdn:
                    self.rd_seen = 0
                    ns = 0
            elif 3 <= s <= 5: ns = s + 1
            elif s == 6: ns = 0
        self.state = ns
        # --- TXCLIENT v2 (байт-в-байт по RTL) ---
        hlda_in = hl
        baud_tick = 1 if self.baud_cnt == (BAUD_DIV - 1) else 0
        self.baud_cnt = 0 if baud_tick else (self.baud_cnt + 1) & 0xF
        txb = self.tx_byte
        if txb == 0:                                       # TXB_IDLE
            # защита от ложного взвода: пакет НЕ стартовал, HLDA пришёл
            if self.hold_req and self.hlda_q and self.state == 0:
                self.hold_req = 0
        elif txb in (1, 2, 3) and baud_tick:               # TXB_HI/TXB_LO/TXB_DAT
            if self.bit_cnt == 9:
                self.bit_cnt, self.baud_cnt = 0, 0
                if txb == 1:
                    self.shreg = ((1 << 9) | (self.addr_latch << 1)) & 0x3FF
                    self.tx_byte = 2                       # байт 2: A0-A7
                elif txb == 2:
                    self.shreg = ((1 << 9) | (self.bus_reg << 1)) & 0x3FF
                    self.tx_byte = 3                       # байт 3: данные
                else:
                    self.shreg, self.tx_byte = 0x3FF, 0
                    self.hold_req = 0                      # РЕЛИЗ В КОНЦЕ ПАКЕТА
            else:
                self.shreg = ((1 << 9) | (self.shreg >> 1)) & 0x3FF
                self.bit_cnt = (self.bit_cnt + 1) & 0xF
        # Взвод (T1) и СТАРТ ПАКЕТА (T2, первый тик !WRn) - ПОСЛЕ case;
        # читаем СТАРЫЕ state/wr_seen/hold_req/tx_byte (как в RTL):
        if s == 1 and ale and win_hit: self.hold_req = 1
        if (s == 2 and wrn == 0 and wr_seen_old == 0 and hold_req_old
                and tx_byte_old == 0):
            self.shreg = ((1 << 9) | (ah << 1)) & 0x3FF    # байт 1: A15-A8 ПРЯМО В shreg
            self.bit_cnt, self.baud_cnt, self.tx_byte = 0, 0, 1
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
        self.tx    = self.shreg & 1
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
            while self.dut.hold: self.tick()            # грант активен (в v2 - ВЕСЬ пакет)
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
bus.idle(500)                              # дать пакету доехать до конца (журнал целиком)
chk("T1: HOLD взведён ещё в T1 (ALE высок)", bus.events[1] is True)
fr = frames(bus.log_tx)
chk("T1: пакет = 3 кадра", len(fr) == 3, str(fr))
if len(fr) == 3:
    chk("T1: байт1 = addr_hi 0x80 (start=0,stop=1)",
        fr[0][0] == 0 and fr[0][1] == 0x80 and fr[0][2] == 1, str(fr[0][:3]))
    chk("T1: байт2 = addr_lo 0x12 (start=0,stop=1)",
        fr[1][0] == 0 and fr[1][1] == 0x12 and fr[1][2] == 1, str(fr[1][:3]))
    chk("T1: байт3 = data 0x5A (start=0,stop=1)",
        fr[2][0] == 0 and fr[2][1] == 0x5A and fr[2][2] == 1, str(fr[2][:3]))
    chk("T1: между кадрами зазор 0 тиков",
        fr[1][3] - fr[0][3] == 10 * BAUD_DIV and fr[2][3] - fr[1][3] == 10 * BAUD_DIV,
        str([f[3] for f in fr]))
    e, grid_ok = bit_lengths_ok(bus.log_tx, fr[0][3])
    chk("T1: все фронты кадра1 на сетке 13 тиков (520 нс)", grid_ok, str(e))
    e2, grid_ok2 = bit_lengths_ok(bus.log_tx, fr[2][3])
    chk("T1: все фронты кадра3 на сетке 13 тиков", grid_ok2, str(e2))
    # v2: HOLD держится ВЕСЬ пакет (в v1 отпускался на 2-м байте)
    hold_by_t = {t: h for t, v, h in bus.log_tx}
    chk("T1: HOLD='1' на старте кадра2 и кадра3 (релиз только в конце пакета)",
        hold_by_t.get(fr[1][3]) == 1 and hold_by_t.get(fr[2][3]) == 1,
        "h(f2)=%s h(f3)=%s" % (hold_by_t.get(fr[1][3]), hold_by_t.get(fr[2][3])))
    chk("T1: HOLD отпущен в стоп-бите кадра3 (не раньше)",
        fr[2][3] + 9 * BAUD_DIV <= rel_t <= fr[2][3] + 10 * BAUD_DIV,
        "rel=%d f3=%d" % (rel_t, fr[2][3]))
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

# ================= T2: запись в страницу-исключение FFxx (стек) =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
bus.cycle(0xFF34, 0x77, write=1, label="excl-write")
bus.idle(100)
chk("T2: HOLD НИКОГДА не взводился (стек быстрый)", bus.hlda_seen == 0)
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
bus.idle(800)                              # оба пакета до конца
fr = frames(bus.log_tx, t_before)
chk("T6: ровно 2 пакета (6 кадров) без потерь", len(fr) == 6, str([(hex(f[1]), f[3]) for f in fr]))
if len(fr) == 6:
    got = [f[1] for f in fr]
    chk("T6: содержимое [80,01,11] затем [80,02,22]",
        got == [0x80, 0x01, 0x11, 0x80, 0x02, 0x22], str([hex(v) for v in got]))
    starts = [f[3] for f in fr]
    chk("T6: кадры без зазоров внутри пакетов",
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

# ================= T8: сброс посреди пакета =================
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
for _ in range(40): bus.tick()          # пакет уже идёт (hi-байт)
chk("T8: до сброса пакет идёт (TX не idle)", bus.dut.tx_byte != 0, str(bus.dut.tx_byte))
# RST на 3 тика: cpu_rst = RST | por_run; в модели DUT нет RST -
# эмулируем прямой записью (синхронный сброс тех же регистров)
dut.state, dut.rd_seen, dut.wr_seen = 0, 0, 0
dut.hold_req = dut.hlda_q = 0
dut.tx_byte = dut.bit_cnt = dut.baud_cnt = 0
dut.shreg = 0x3FF
bus.tick()
chk("T8: после сброса HOLD=0 и TX='1'", dut.hold == 0 and dut.tx == 1)
chk("T8: state=IDLE", dut.state == 0)
bus.hl = 0

print()
print("ИТОГ:", "ВСЕ ПАСС" if ok_all else "ЕСТЬ ПРОВАЛЫ")
raise SystemExit(0 if ok_all else 1)
