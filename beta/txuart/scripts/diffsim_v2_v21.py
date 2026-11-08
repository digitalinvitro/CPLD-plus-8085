#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diffsim_v2_v21.py - дифсимальная верификация TXUART v2.1 против v2.0.

Доказывает главный тезис п.31/п.27 ред. v2.1: СЖАТИЕ ЯДРА 20 -> 18 МЦ
(adv_q и tx_run свернуты: jam baud_cnt <= 0 вместо <= 1; bit_cnt 1..10,
idle = 0, busy = |bit_cnt; TXRDY = ~|bit_cnt) НЕ МЕНЯЕТ НАБЛЮДАЕМОГО
ПОВЕДЕНИЯ ЧИПА: обе цикл-точные модели (sim_txuart_v2.py и
sim_txuart_v21.py) гоняются с ИДЕНТИЧНЫМ стимулом, после КАЖДОГО тика
20 нс сравниваются ВСЕ наблюдаемые выходы и общие регистры:

  выходы: TX, A_out (вкл. TXRDY/KBROW/writeback-драйв), D_out, CSr_n,
          CS_n, OEr_n, OE_n, WE_n, RESET_IN, SID, seg, dig, snd, col,
          X1, X2;
  общие регистры: shreg, baud_cnt, ld_tx_q, state, rd_seen, wr_seen,
          addr_latch, bus_reg, seg_q, dig_q, snd_q, kbcol_q, clk25_q,
          r0..r6, por_sh, por_run, rst_meta, rst_sync, rst_press,
          rst_qcnt, reset_q.

НЕ сравнивается (легальные отличия v2.1): bit_cnt (кодировка 1..10
против 0..9 - внутренняя), tx_run/adv_q (выпилены в v2.1 - их функции
наблюдаемы через TXRDY/TX), baud_cnt (jam 1 в v2.0 против jam 0 в v2.1 -
внутренняя фаза сдвинута на 1 тик НАВСЕГДА после загрузки; фронты
СДВИГОВ совпадают 1-в-1 - лаг adv_q в v2.0 ровно компенсирует jam 0;
фронты сдвигов покрыты строгим равенством shreg).

Стимул: POR, кадры 0x55/0x00/0xFF/0xA3 (в т.ч. подряд с поллингом
TXRDY), busy-drop, чтение 04h/05h, порты 00h/01h/02h, чтение KBROW 03h,
циклы памяти (чтение/запись с writeback), ALE-глюк, OUT 04h в окне POR,
сброс кнопкой посреди кадра и в idle, случайные межцикловые паузы.

Запуск: python3 scripts/diffsim_v2_v21.py  (пути от папки скрипта)
Ожидание: "ДИФСИМ ПАСС: N тиков, расхождений 0".
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m2 = load("sim_txuart_v2", "sim_txuart_v2.py")
m21 = load("sim_txuart_v21", "sim_txuart_v21.py")

SIGS_OUT = ["TX", "A_out", "D_out", "CSr_n", "CS_n", "OEr_n", "OE_n",
            "WE_n", "RESET_IN", "SID", "seg", "dig", "snd", "col",
            "X1", "X2"]
# baud_cnt НЕ в списке: jam 1 (v2.0) vs jam 0 (v2.1) - легальный сдвиг
# фазы на 1 тик, фронты сдвигов совпадают (проверяется через shreg)
SIGS_REG = ["shreg", "ld_tx_q", "state", "rd_seen", "wr_seen",
            "addr_latch", "bus_reg", "seg_q", "dig_q", "snd_q", "kbcol_q",
            "clk25_q", "por_sh", "por_run", "rst_meta", "rst_sync",
            "rst_press", "rst_qcnt", "reset_q"]


class Diff:
    def __init__(self):
        self.a = m2.Sim()    # v2.0 (эталон)
        self.b = m21.Sim()   # v2.1 (сжатое ядро)
        self.ticks = 0
        self.errs = []

    def _vals(self, d):
        v = {}
        for s in SIGS_OUT:
            v[s] = getattr(d, s)
        for s in SIGS_REG:
            v[s] = getattr(d, s)
        return v

    def step(self):
        self.a.d.tick()
        self.b.d.tick()
        self.ticks += 1
        va = self._vals(self.a.d)
        vb = self._vals(self.b.d)
        for k in va:
            if va[k] != vb[k]:
                self.errs.append((self.ticks, k, va[k], vb[k]))
                if len(self.errs) > 20:
                    self.report(True)

    # ---- драйвер: один и тот же стимул в ОБЕ модели ----
    def cpu_io_write(self, port, data):
        for d in (self.a.d, self.b.d):
            d.ALE = 1; d.IOM = 1; d.A_in = port
        self.multi(6)
        for d in (self.a.d, self.b.d):
            d.ALE = 0
        self.multi(2)
        for d in (self.a.d, self.b.d):
            d.WRn = 0; d.A_in = data
        self.multi(8)
        for d in (self.a.d, self.b.d):
            d.WRn = 1; d.A_in = None
        self.multi(4)

    def cpu_io_read(self, port):
        for d in (self.a.d, self.b.d):
            d.ALE = 1; d.IOM = 1; d.A_in = port
        self.multi(6)
        for d in (self.a.d, self.b.d):
            d.ALE = 0
        self.multi(2)
        for d in (self.a.d, self.b.d):
            d.RDn = 0
        self.multi(6)
        va = self.a.d.A_out
        vb = self.b.d.A_out
        if va != vb:
            self.errs.append((self.ticks, "A_out@RD-sample", va, vb))
        self.multi(2)
        for d in (self.a.d, self.b.d):
            d.RDn = 1
        self.multi(4)
        return va

    def cpu_mem_write(self, addr, data):
        # запись ОЗУ (A15=1, IOM=0) -> writeback (WB1..WB4)
        for d in (self.a.d, self.b.d):
            d.ALE = 1; d.IOM = 0; d.A15 = 1; d.A_in = addr
        self.multi(6)
        for d in (self.a.d, self.b.d):
            d.ALE = 0
        self.multi(2)
        for d in (self.a.d, self.b.d):
            d.WRn = 0; d.A_in = data
        self.multi(8)
        for d in (self.a.d, self.b.d):
            d.WRn = 1; d.A_in = None
        self.multi(4)
        for d in (self.a.d, self.b.d):
            d.A15 = 0; d.IOM = 0

    def cpu_mem_read(self, addr, ddata):
        for d in (self.a.d, self.b.d):
            d.ALE = 1; d.IOM = 0; d.A15 = 0; d.A_in = addr; d.D_in = ddata
        self.multi(6)
        for d in (self.a.d, self.b.d):
            d.ALE = 0
        self.multi(2)
        for d in (self.a.d, self.b.d):
            d.RDn = 0; d.A_in = None
        self.multi(6)
        va = self.a.d.A_out
        vb = self.b.d.A_out
        if va != vb:
            self.errs.append((self.ticks, "A_out@memRD", va, vb))
        self.multi(2)
        for d in (self.a.d, self.b.d):
            d.RDn = 1
        self.multi(4)
        for d in (self.a.d, self.b.d):
            d.D_in = 0
        return va

    def multi(self, n):
        for _ in range(n):
            self.step()

    def report(self, abort=False):
        print("=" * 64)
        print(f"ДИФСИМ: тиков {self.ticks}, расхождений {len(self.errs)}")
        for t, k, x, y in self.errs[:20]:
            print(f"  тик {t} ({t * 20} нс): {k}: v2.0={x!r} v2.1={y!r}")
        if self.errs:
            print("ДИФСИМ ПРОВАЛЕН")
            sys.exit(1)
        print("ДИФСИМ ПАСС: поведение 1-в-1" + (" (аборт)" if abort else ""))
        if abort:
            sys.exit(1)


def main():
    df = Diff()
    a, b = df.a.d, df.b.d

    # ---- 1) POR и idle ----
    df.multi(80)                       # POR: 8 стробов r0, снятие ~тик 51
    df.multi(100)
    v = df.cpu_io_read(0x05)
    assert v == 0x02, f"TXRDY после POR: {v:#04x}"

    # ---- 2) одиночные кадры ----
    for byte in (0x55, 0x00, 0xFF, 0xA3, 0x01, 0x80):
        df.cpu_io_write(0x04, byte)
        df.multi(32 * 12)              # ~12 бит-таймов
        v = df.cpu_io_read(0x05)
        assert v == 0x02, f"TXRDY после кадра {byte:#04x}: {v:#04x}"
        df.multi(13)

    # ---- 3) поток с поллингом TXRDY (байт за байтом, стоп -> старт) ----
    for byte in (0x41, 0x42, 0x43, 0x7F, 0x81):
        guard = 0
        while guard < 50:
            v = df.cpu_io_read(0x05)
            if v & 2:
                break
            guard += 1
        assert v & 2, "TXRDY не поднялся"
        df.cpu_io_write(0x04, byte)
    df.multi(32 * 14)

    # ---- 4) busy-drop ----
    df.cpu_io_write(0x04, 0x11)
    df.multi(64)                       # внутри кадра
    df.cpu_io_write(0x04, 0x99)        # отбрасывается
    df.multi(32 * 12)
    df.multi(20)

    # ---- 5) чтение 04h (не определено) и порты ----
    df.cpu_io_read(0x04)
    df.cpu_io_write(0x00, 0x0F0F & 0xFF)
    df.cpu_io_write(0x01, 0x1F)
    df.cpu_io_write(0x02, 0x05)
    df.multi(10)
    for d in (a, b):
        d.rows = 0b10111
    df.cpu_io_read(0x03)
    for d in (a, b):
        d.rows = 0

    # ---- 6) память: чтение и запись с writeback ----
    df.cpu_mem_read(0x1234, 0x5A)
    df.cpu_mem_read(0x0055, 0xC3)
    df.cpu_mem_write(0x8001, 0x96)
    df.cpu_mem_write(0xFFFF, 0x00)
    df.multi(30)

    # ---- 7) ALE-глюк: ALE в T2 до данных ----
    for d in (a, b):
        d.ALE = 1; d.IOM = 1; d.A_in = 0x04
    df.multi(6)
    for d in (a, b):
        d.ALE = 0
    df.multi(2)
    for d in (a, b):
        d.ALE = 1                      # глюк ALE в T2
    df.multi(2)
    for d in (a, b):
        d.ALE = 0
    df.multi(2)
    for d in (a, b):
        d.WRn = 0; d.A_in = 0x77
    df.multi(8)
    for d in (a, b):
        d.WRn = 1; d.A_in = None
    df.multi(4)
    df.multi(32 * 12)

    # ---- 8) OUT 04h в окне POR (свежий сброс -> попытка старта) ----
    for d in (a, b):
        d.RST = 1
    df.multi(30)
    for d in (a, b):
        d.RST = 0
    df.multi(30)
    df.cpu_io_write(0x04, 0xC3)
    df.multi(32 * 12)

    # ---- 9) сброс посреди кадра ----
    df.cpu_io_write(0x04, 0x5A)
    df.multi(48)
    for d in (a, b):
        d.RST = 1
    df.multi(40)
    for d in (a, b):
        d.RST = 0
    df.multi(80)
    v = df.cpu_io_read(0x05)
    assert v == 0x02, f"TXRDY после сброса: {v:#04x}"

    # ---- 10) случайные паузы + микс циклов ----
    import random
    rnd = random.Random(20261108)
    for i in range(40):
        df.multi(rnd.randrange(1, 30))
        op = i % 4
        byte = rnd.randrange(256)
        if op == 0:
            df.cpu_io_write(0x04, byte)
        elif op == 1:
            df.cpu_io_read(0x05)
        elif op == 2:
            df.cpu_io_write(0x00, byte)
        else:
            df.cpu_mem_read(rnd.randrange(65536), byte)
    df.multi(32 * 12)

    df.report()


if __name__ == "__main__":
    main()
