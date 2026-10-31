#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_txclient.py - верификация TXCLIENT v1 ДО фита (Icarus в песочнице
недоступен). Цикл-точная модель РОВНО по RTL beta/txclient/top_txclient_v1_utf8.v:
FSM шины v3.9.2 (7 состояний, writeback) + блок txclient (win_decode,
hold_req/tx_req/hlda_q, сериализатор 2 байта 8N1) + гейты CS_n/CSr_n.
Сценарии: окно-запись (тайминги бит/содержимое/HOLD-рукопожатие), не-окно,
IO-запись, чтение окна, бэку-ту-бэк, сброс посреди пакета."""

BAUD_DIV = 13
WIN_PAGE = 0xF0
T_T1, T_STROBE = 7, 9            # ALE высок ~7 тиков (1 CLK CPU), !WR ~9 тиков

class DUT:
    """Модель top_txclient (изменённые узлы; делитель/POR/порты не моделируются -
    байт-в-байт v3.9.2 и проверены раньше)."""
    def __init__(self):
        self.state, self.rd_seen, self.wr_seen = 0, 0, 0   # S_IDLE
        self.addr_latch, self.bus_reg = 0x00, 0x00
        self.hold_req = self.tx_req = self.hlda_q = 0
        self.tx_byte, self.bit_cnt, self.baud_cnt = 0, 0, 0
        self.shreg = 0x3FF
        self.cs_n = self.csr_n = self.we_n = self.oe_n = self.oer_n = 1
        self.hold = 0
        self.tx = 1

    def tick(self, ale, wrn, rdn, iom, a, d, a15, hl):
        s = self.state                       # последовательностная логика читает СТАРЫЕ значения
        in_wb   = s >= 3                       # S_WB1..S_WB4
        in_welo = s in (4, 5)                  # S_WB2/S_WB3
        wr_phase = s >= 2                      # S_T2..WB4
        rd_drive = (s == 2) and self.rd_seen == 1 and rdn == 0 and ale == 0
        win_hit = (iom == 0) and ((a15 & 0xFF) == WIN_PAGE)
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
                    ns = 3 if (not iom and a15) else 0
                elif self.rd_seen and rdn:
                    self.rd_seen = 0
                    ns = 0
            elif 3 <= s <= 5: ns = s + 1
            elif s == 6: ns = 0
        self.state = ns
        # --- TXCLIENT v1 (байт-в-байт по RTL) ---
        hlda_in = hl
        baud_tick = 1 if self.baud_cnt == (BAUD_DIV - 1) else 0
        self.baud_cnt = 0 if baud_tick else (self.baud_cnt + 1) & 0xF
        txb = self.tx_byte
        if txb == 0:                                       # TXB_IDLE
            if self.hold_req and self.tx_req and self.hlda_q and self.state == 0:
                self.shreg = ((1 << 9) | (self.addr_latch << 1)) & 0x3FF
                self.bit_cnt, self.baud_cnt, self.tx_byte = 0, 0, 1
            elif self.hold_req and self.hlda_q and self.state == 0:
                self.hold_req = 0                          # чтение окна: без пакета
        elif txb in (1, 2) and baud_tick:                  # TXB_LO/TXB_DAT
            if self.bit_cnt == 9:
                self.bit_cnt, self.baud_cnt = 0, 0
                if txb == 1:
                    self.shreg = ((1 << 9) | (self.bus_reg << 1)) & 0x3FF
                    self.tx_byte = 2
                    self.hold_req = 0                      # релиз на загрузке 2-го байта
                    self.tx_req = 0
                else:
                    self.shreg, self.tx_byte = 0x3FF, 0
            else:
                self.shreg = ((1 << 9) | (self.shreg >> 1)) & 0x3FF
                self.bit_cnt = (self.bit_cnt + 1) & 0xF
        if self.state == 1 and ale and win_hit: self.hold_req = 1
        if self.state == 2 and wrn == 0 and self.hold_req: self.tx_req = 1
        self.hlda_q = hlda_in
        # --- выходы: комбинационные сети СЛЕДУЮТ НОВОМУ состоянию (в RTL
        # assign стоят на регистрах и после фронта читают новые значения) ---
        tx_hold = self.hold_req | self.hlda_q
        in_wb_o   = 1 if self.state >= 3 else 0
        in_welo_o = 1 if self.state in (4, 5) else 0
        wr_phase_o = 1 if self.state >= 2 else 0
        self.cs_n  = 0 if in_wb_o else (1 if tx_hold else (0 if a15 else 1))
        self.csr_n = 1 if (a15 or iom or tx_hold) else 0
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
        self.a, self.d, self.a15, self.hl = 0, 0, 0, 0
        self.log_tx = []                    # (tick, tx) каждый тик
        self.events = []                    # журнал для проверок
        self.t = 0
        self.hlda_seen = 0

    def tick(self):
        self.dut.tick(self.ale, self.wrn, self.rdn, self.iom, self.a, self.d,
                      self.a15, self.hl)
        self.log_tx.append((self.t, self.dut.tx))
        self.t += 1

    def idle(self, n):
        self.ale, self.wrn, self.rdn = 0, 1, 1
        for _ in range(n): self.tick()

    def cycle(self, addr, data=None, iom=0, write=1, label=""):
        # T1
        self.a15 = (addr >> 8) & 0x00FF if addr > 0xFF else 0
        self.a15 = (addr >> 8) & 0xFF     # на AH-пинах; бит A15 - старший
        self.a, self.iom = addr & 0xFF, iom
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
        self.tick()
        if write and not iom and (addr >> 8) & 0xFF >= 0x80:
            self.mem[addr] = data & 0xFF                # ОЗУ приняло (writeback)
        # HOLD/HLDA рукопожатие
        if self.dut.hold:
            for _ in range(2): self.tick()              # CPU замечает HOLD
            self.hl = 1; self.hlda_seen += 1
            while self.dut.hold: self.tick()            # грант активен
            self.release_t = self.t - 1                 # HOLD упал (релиз на загрузке 2-го байта)
            for _ in range(2): self.tick()              # HLDA ещё 2 тика после HOLD=0
            self.hl = 0
        self.events.append((label, hold_at_t1))
        self.a15 = 0

# ---------- декодер UART (для проверок) ----------
def frames(tx_log, t_from=0):
    """Разбивает журнал TX на кадры 10 бит по переднему фронту старт-бита;
    возвращает [(битов_значение, [длины бит])]."""
    ticks = [t for t, v in tx_log if t >= t_from and v == 0]
    out = []
    i = 0
    log = dict(tx_log)
    while i < len(ticks):
        t0 = ticks[i]
        # пропускаем тики внутри предыдущего кадра (не должно быть, но защита)
        if out and t0 <= out[-1][2]: i += 1; continue
        bits = []
        lens = []
        for k in range(10):
            tk = t0 + k * BAUD_DIV + BAUD_DIV // 2
            bits.append(log.get(tk, 1))
        # длины: фронт вниз на t0, вверх на t0+BAUD_DIV... измеряем по журналу
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
    log = dict(tx_log)
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

# ================= T1: окно-запись F012h <- 5Ah =================
dut, bus = DUT(), None
bus = Bus(dut); bus.idle(10)
bus.cycle(0xF012, 0x5A, write=1, label="win-write")
rel_t = bus.release_t
bus.idle(300)                              # дать пакету доехать до конца (журнал целиком)
chk("T1: HOLD взведён ещё в T1 (ALE высок)", bus.events[-1][1] is True)
fr = frames(bus.log_tx)
chk("T1: пакет = 2 кадра", len(fr) == 2, str(fr))
if len(fr) == 2:
    chk("T1: байт1 = addr_lo 0x12 (start=0,stop=1)",
        fr[0][0] == 0 and fr[0][1] == 0x12 and fr[0][2] == 1, str(fr[0][:3]))
    chk("T1: байт2 = data 0x5A (start=0,stop=1)",
        fr[1][0] == 0 and fr[1][1] == 0x5A and fr[1][2] == 1, str(fr[1][:3]))
    chk("T1: между кадрами зазор 0 тиков", fr[1][3] - fr[0][3] == 10 * BAUD_DIV,
        str(fr[1][3] - fr[0][3]))
    e, grid_ok = bit_lengths_ok(bus.log_tx, fr[0][3])
    chk("T1: все фронты кадра1 на сетке 13 тиков (520 нс)", grid_ok, str(e))
    e2, grid_ok2 = bit_lengths_ok(bus.log_tx, fr[1][3])
    chk("T1: все фронты кадра2 на сетке 13 тиков", grid_ok2, str(e2))
    chk("T1: HOLD отпущен в первых битах кадра2 (CPU ждёт только голову пакета)",
        rel_t < fr[1][3] + 3 * BAUD_DIV, "rel=%d f2=%d" % (rel_t, fr[1][3]))
chk("T1: ОЗУ приняло запись (writeback штатно)", bus.mem.get(0xF012) == 0x5A)
chk("T1: после пакета TX idle '1' и HOLD=0", dut.tx == 1 and dut.hold == 0)

# CS-гейты: в tx_hold память выключена; в WB - ОЗУ включена и /WE импульс 2 тика
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(5)
bus.a15 = 0xF0; bus.a = 0x34; bus.iom = 0; bus.ale = 1
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
# пока CPU вне шины (tx_hold) и FSM НЕ в WB - выбор памяти погашен
# (в WB /CE ОЗУ = 0 легитимно: это сама запись, п.16)
chk("CS: в tx_hold вне WB /CE ОЗУ и ПЗУ = 1 (A15/IOM флоат - декод не работает)",
    all(c == 1 and r == 1 for c, r, h, s in zip(cs_hist, csr_hist, txh_hist, st_hist)
        if h and s == 0),
    str([(c, r) for c, r, h, s in zip(cs_hist, csr_hist, txh_hist, st_hist)
         if h and s == 0][:12]))

# ================= T2: запись ВНЕ окна (страница 80h) =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
bus.cycle(0x8012, 0x5A, write=1, label="non-win")
bus.idle(100)
chk("T2: HOLD НИКОГДА не взводился", bus.hlda_seen == 0)
chk("T2: TX всё время '1'", all(v == 1 for _, v in bus.log_tx))
chk("T2: ОЗУ приняло запись", bus.mem.get(0x8012) == 0x5A)

# ================= T3: IO-запись (порт 00h) =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
bus.cycle(0x00, 0xAA, iom=1, write=1, label="io-write")
bus.idle(100)
chk("T3: HOLD НИКОГДА не взводился", bus.hlda_seen == 0)
chk("T3: TX всё время '1'", all(v == 1 for _, v in bus.log_tx))

# ================= T4: ЧТЕНИЕ окна (F040h) =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
bus.cycle(0xF040, write=0, label="win-read")
bus.idle(100)
chk("T4: HOLD взводился (пинг-понг)", bus.hlda_seen == 1)
chk("T4: пакета НЕТ - TX всё время '1'", all(v == 1 for _, v in bus.log_tx))
chk("T4: HOLD отпущен", dut.hold == 0)

# ================= T5: бэку-ту-бэк F001<-11, F002<-22 =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(10)
t_before = bus.t
bus.cycle(0xF001, 0x11, write=1, label="win-1")
bus.cycle(0xF002, 0x22, write=1, label="win-2")
bus.idle(300)                              # оба пакета до конца (второй - в очереди hold_req)
fr = frames(bus.log_tx, t_before)
chk("T5: ровно 2 пакета (4 кадра) без потерь", len(fr) == 4, str([(hex(f[1]), f[3]) for f in fr]))
if len(fr) == 4:
    got = [f[1] for f in fr]
    chk("T5: содержимое [01,11] затем [02,22]",
        got == [0x01, 0x11, 0x02, 0x22], str([hex(v) for v in got]))
    starts = [f[3] for f in fr]
    chk("T5: кадры без зазоров внутри пакетов",
        starts[1] - starts[0] == 10 * BAUD_DIV and starts[3] - starts[2] == 10 * BAUD_DIV,
        str(starts))
chk("T5: обе записи в ОЗУ", bus.mem.get(0xF001) == 0x11 and bus.mem.get(0xF002) == 0x22)

# ================= T6: сброс посреди пакета =================
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(5)
bus.a15, bus.a, bus.iom, bus.ale = 0xF0, 0x99, 0, 1
for _ in range(T_T1): bus.tick()
bus.ale = 0; bus.a = 0x66; bus.wrn = 0
for _ in range(T_STROBE + 2): bus.tick()
bus.wrn = 1; bus.tick()
for _ in range(2): bus.tick()
bus.hl = 1
for _ in range(40): bus.tick()          # пакет уже стартовал
chk("T6: до сброса пакет идёт (TX не idle)", bus.dut.tx_byte != 0, str(bus.dut.tx_byte))
# RST на 3 тика
tx_before = bus.dut.tx
bus.ale, bus.wrn = 0, 1
# cpu_rst моделируем RST=1: в RTL cpu_rst = RST | por_run; в модели DUT нет RST -
# эмулируем прямой записью (синхронный сброс тех же регистров)
dut.state, dut.rd_seen, dut.wr_seen = 0, 0, 0
dut.hold_req = dut.tx_req = dut.hlda_q = 0
dut.tx_byte = dut.bit_cnt = dut.baud_cnt = 0
dut.shreg = 0x3FF
bus.tick()
chk("T6: после сброса HOLD=0 и TX='1'", dut.hold == 0 and dut.tx == 1)
chk("T6: state=IDLE", dut.state == 0)

print()
print("ИТОГ:", "ВСЕ ПАСС" if ok_all else "ЕСТЬ ПРОВАЛЫ")
raise SystemExit(0 if ok_all else 1)
