#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_mon.py — верификация монитора fw_mon_ape (beta/lowsize/rom, clk10-69).

Метод:
  1) МИНИ-ИНТЕРПРЕТАТОР 8085 из verify_fw.py (точные T-состояния Intel
     8085A) исполняет РЕАЛЬНЫЙ .hex; добавлены DI/EI (в базовом классе
     их нет) и ЗАПИСЬ В ROM 0000h-7FFFh ОТБРАСЫВАЕТСЯ (как железо:
     writeback не запускается, MEMORY_MAP.md §3).
  2) МОДЕЛЬ ПЛАТЫ: порты 00h (сегменты), 01h (разряды+D4=SND), 02h
     (колонки), 03h (ряды); матрица 5x4 (PORTS_MAP.md §10), нажатие
     задаётся парой (row,col); модель регенерации с БЛЭНКИНГ-контролем
     (клк10-67): каждый OUT 01h с битами разряда обязан идти строго
     после OUT 00h=0.
  3) СЦЕНАРИИ по ТЗ владельца: меню APE_, F1 глобально, ввод адреса
     (4 тетрады, сдвиг справа), Enter, ввод программы (2 тетрады,
     "__C3"), запись в ОЗУ и адрес+, игнор пустого Enter, отброс
     записи в ROM, запуск (E) с возвратом по RET, вытеснение 5-й
     тетрады, авто-повтор, тик (тон+длительность).

Использование: python3 verify_mon.py   (из rom/; нужен verify_fw.py)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_fw
from verify_fw import CPU8085, load_hex, chk, STEP_NS

GL = {0x3F: '0', 0x06: '1', 0x5B: '2', 0x4F: '3', 0x66: '4', 0x6D: '5',
      0x7D: '6', 0x07: '7', 0x7F: '8', 0x6F: '9', 0x77: 'A', 0x7C: 'b',
      0x39: 'C', 0x5E: 'd', 0x79: 'E', 0x71: 'F', 0x73: 'P', 0x00: ' '}

# клавиши (row,col) для сценариев
K = dict(A=(0, 0), B=(0, 1), C=(0, 2), D=(0, 3),
         k7=(1, 0), k8=(1, 1), k9=(1, 2), E=(1, 3),
         k4=(2, 0), k5=(2, 1), k6=(2, 2), F=(2, 3),
         k1=(3, 0), k2=(3, 1), k3=(3, 2), ENT=(3, 3),
         k0=(4, 0), F1=(4, 1), F2=(4, 2))


class MonCPU(CPU8085):
    """+DI/EI, +отброс записи в ROM, +трассировка захода в ОЗУ."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.ie = 0
        self.ram_pc = False

    def wr(self, a, v):
        if a < 0x8000:              # ROM: writeback не запускается
            return
        self.m[a & 0xFFFF] = v & 0xFF

    def step(self):
        if 0x8000 <= self.PC <= 0xFFE7:
            self.ram_pc = True
        op = self.m[self.PC]
        if op == 0xF3:              # DI
            self.PC = (self.PC + 1) & 0xFFFF
            self.ie = 0
            return 4
        if op == 0xFB:              # EI
            self.PC = (self.PC + 1) & 0xFFFF
            self.ie = 1
            return 4
        return super().step()


class Board:
    """Порты CPLD + матрица 5x4 + блэнкинг-контроль."""

    def __init__(self):
        self.col = 0
        self.seg_last = None        # последний OUT 00h
        self.keys = {}              # (row,col) -> True/False
        self.log = []               # (T, port, val)
        self.ghost = []             # нарушения блэнкинга
        self.snd_seen = 0           # OUT 01h с D4=1
        self.blank_seen = 0         # OUT 01h с разрядами=0 (полное гашение)

    def out(self, cpu, p, v):
        self.log.append((cpu.T, p, v))
        if p == 0:
            self.seg_last = v
        elif p == 1:
            if (v & 0x0F) == 0:
                self.blank_seen += 1
            else:
                if self.seg_last != 0:      # клк10-67: разряд только пустым
                    self.ghost.append((cpu.T, hex(v), self.seg_last))
                if v & 0x10:
                    self.snd_seen += 1
        elif p == 2:
            self.col = v & 0x0F             # заведённые колонки

    def inp(self, p):
        if p != 3:
            return 0xFF             # прочие порты CPLD не драйвит
        rows = 0
        for (r, c), pr in self.keys.items():
            if pr and (self.col >> c) & 1:
                rows |= 1 << r
        return rows & 0x1F


def make_cpu(board, path):
    mem, top = load_hex(os.path.join(HERE, path))
    assert mem[0] == 0xC3, 'нет JMP на 0000'
    cpu = MonCPU(mem, cb_out=lambda p, v: board.out(cpu, p, v),
                 cb_in=board.inp)
    return cpu, mem


def press(cpu, board, key, hold_t=45_000):
    """Нажать и отпустить клавишу (catch + тик + отпускание + дебаунс)."""
    board.keys[key] = True
    cpu.run(cpu.T + hold_t)         # ловля + DISPATCH (тик ещё прижата)
    board.keys[key] = False
    cpu.run(cpu.T + 60_000)         # отпускание + дебаунс + слоты дисплея


def hold(cpu, board, key, t):
    """Держать клавишу t T-состояний (авто-повтор/залипание)."""
    board.keys[key] = True
    cpu.run(cpu.T + t)
    board.keys[key] = False
    cpu.run(cpu.T + 60_000)


def visible(board):
    """Что видно на дисплее: пара (OUT 01h с разрядом -> следующий OUT 00h
    = глиф этой фазы). Гашение (OUT 00h=0 перед фазой) в пару не попадает.
    """
    lat = {}
    pending = None
    for t, p, v in board.log:
        if p == 1:
            pending = (v & 0x0F) or None
        elif p == 0 and pending:
            lat[pending] = v
            pending = None
    s = ''
    for d in (0x08, 0x04, 0x02, 0x01):      # DIG3..DIG0
        g = lat.get(d, None)
        s += GL.get(g, '?') if g is not None else '?'
    return s


def phases(board, t_from=0):
    """(T, разряд, SEGP-до, SEGP-после) по каждому OUT 01h с разрядом."""
    lg = board.log
    res = []
    for i, (t, p, v) in enumerate(lg):
        if t < t_from or p != 1 or not (v & 0x0F):
            continue
        sb = next((lg[j][2] for j in range(i - 1, -1, -1)
                   if lg[j][1] == 0), None)
        sa = next((lg[j][2] for j in range(i + 1, len(lg))
                   if lg[j][1] == 0), None)
        res.append((t, v & 0x0F, sb, sa))
    return res


def main():
    print("=" * 76)
    print("fw_mon_ape_fast.hex: поведение монитора (FAST=1: тик 4 ед, "
          "дебаунс 2 ед)")
    print("=" * 76)

    board = Board()
    cpu, mem = make_cpu(board, 'fw_mon_ape_fast.hex')
    cpu.run(25_000)                                  # загрузка + меню

    # ---- 1. загрузка ----
    chk("boot: первый OUT 00h = 00 (гашение '8.' после сброса)",
        board.log[0][1] == 0 and board.log[0][2] == 0)
    chk("boot: второй OUT 01h = 00 (разряды off, SND off)",
        board.log[1][1] == 1 and board.log[1][2] == 0)
    chk("boot: меню APE_ на дисплее", visible(board) == "APE ",
        "%r" % visible(board))

    # ---- 2. F1 в меню (4__1) ----
    press(cpu, board, K['F1'])
    chk("F1 в меню: остаёмся в меню, тик отработал",
        visible(board) == "APE " and board.snd_seen > 0)

    # ---- 3. A: ввод адреса 8000 ----
    press(cpu, board, K['A'])
    chk("A: режим адреса - поле пустое", visible(board) == "    ",
        "%r" % visible(board))
    press(cpu, board, K['k8'])
    chk("адрес: '8' -> \"___8\"", visible(board) == "   8",
        "%r" % visible(board))
    press(cpu, board, K['k0'])
    chk("адрес: '80' -> \"__80\"", visible(board) == "  80",
        "%r" % visible(board))
    press(cpu, board, K['k0'])
    chk("адрес: '800' -> \"_800\"", visible(board) == " 800",
        "%r" % visible(board))
    press(cpu, board, K['k0'])
    chk("адрес: '8000' -> \"8000\"", visible(board) == "8000",
        "%r" % visible(board))
    press(cpu, board, K['ENT'])
    chk("Enter: возврат в меню APE_", visible(board) == "APE ",
        "%r" % visible(board))

    # ---- 4. B (=P): ввод программы C3 в 8000 ----
    press(cpu, board, K['B'])
    chk("B: режим программы - поле пустое (__C3 стартовый вид)",
        visible(board) == "    ", "%r" % visible(board))
    press(cpu, board, K['C'])
    chk("прогр.: 'C' -> \"___C\"", visible(board) == "   C",
        "%r" % visible(board))
    press(cpu, board, K['k3'])
    chk("прогр.: 'C3' -> \"__C3\"", visible(board) == "  C3",
        "%r" % visible(board))
    press(cpu, board, K['ENT'])
    chk("Enter: RAM[8000]=C3 записан, поле погашено, адрес 8001",
        mem[0x8000] == 0xC3 and mem[0xFFEA] == 0x80 and
        mem[0xFFEB] == 0x01 and visible(board) == "    ",
        "RAM=%02X ADDR=%02X%02X disp=%r" %
        (mem[0x8000], mem[0xFFEA], mem[0xFFEB], visible(board)))

    # ---- 5. пустой Enter - игнор ----
    before = mem[0x8001]
    press(cpu, board, K['ENT'])
    chk("Enter при пустом поле - игнор (без записи, режим programme)",
        mem[0x8001] == before and mem[0xFFF1] == 0 and
        visible(board) == "    ")

    # ---- 6. второй байт 0E ----
    press(cpu, board, K['k0'])
    press(cpu, board, K['E'])
    chk("прогр.: '0E' -> \"__0E\"", visible(board) == "  0E",
        "%r" % visible(board))
    press(cpu, board, K['ENT'])
    chk("Enter: RAM[8001]=0E записан, адрес 8002",
        mem[0x8001] == 0x0E and mem[0xFFEA] == 0x80 and
        mem[0xFFEB] == 0x02)

    # ---- 7. F1 выходит из ввода программы ----
    press(cpu, board, K['F1'])
    chk("F1 из программы: меню APE_", visible(board) == "APE ")

    # ---- 8. адрес 0080 (ROM): запись отбрасывается железом ----
    press(cpu, board, K['A'])
    for k in ('k0', 'k0', 'k8', 'k0'):
        press(cpu, board, K[k])
    chk("адрес 0080 набран", visible(board) == "0080",
        "%r" % visible(board))
    press(cpu, board, K['ENT'])
    rom_snapshot = mem[0x0080]
    press(cpu, board, K['B'])
    press(cpu, board, K['C'])
    press(cpu, board, K['k3'])
    press(cpu, board, K['ENT'])
    chk("запись в ROM (0080) отброшена, байт 'уходит' впустую",
        mem[0x0080] == rom_snapshot and visible(board) == "    ",
        "ROM[0080]=%02X (был %02X)" % (mem[0x0080], rom_snapshot))
    press(cpu, board, K['F1'])

    # ---- 9. E: запуск с 8000 (кладём RET для пробы) ----
    # адрес 8000 заново (после сценария 8 там 0081)
    press(cpu, board, K['A'])
    for k in ('k8', 'k0', 'k0', 'k0'):
        press(cpu, board, K[k])
    press(cpu, board, K['ENT'])
    mem[0x8000] = 0xC9                  # RET - программа пользователя
    press(cpu, board, K['E'])
    chk("E: ушли в 8000h (исполнен RET пользователя)", cpu.ram_pc,
        "PC заходил в 8000-FFE7")
    chk("E: возврат по RET - снова меню APE_ (клавишу дождались)",
        visible(board) == "APE ", "%r" % visible(board))
    chk("E: дисплей гасился при выходе (OUT 01h=0)",
        board.blank_seen > 0, "полных гашений: %d" % board.blank_seen)

    # ---- 10. вытеснение 5-й тетрады ----
    press(cpu, board, K['A'])
    for k in ('k1', 'k2', 'k3', 'k4', 'k5'):
        press(cpu, board, K[k])
    chk("5 тетрад: показываются последние 4 -> \"2345\"",
        visible(board) == "2345", "%r" % visible(board))
    press(cpu, board, K['ENT'])
    chk("Enter: ADDR=2345h (последние 4 тетрады)",
        mem[0xFFEA] == 0x23 and mem[0xFFEB] == 0x45)

    # ---- 11. авто-повтор: удержание = одно нажатие ----
    press(cpu, board, K['A'])
    hold(cpu, board, K['k7'], 120_000)
    chk("удержание '7': ровно одна тетрада (авто-повтора нет)",
        mem[0xFFEC] == 1 and visible(board) == "   7",
        "ADCNT=%d %r" % (mem[0xFFEC], visible(board)))
    press(cpu, board, K['F1'])

    # ---- 12. F2 игнорируется в меню ----
    n_snd = board.snd_seen
    press(cpu, board, K['F2'])
    chk("F2 в меню - игнор (меню на месте, тика нет)",
        visible(board) == "APE " and board.snd_seen == n_snd)

    # ---- 13. карта клавиш: (2,2) -> '6' в адресе ----
    press(cpu, board, K['A'])
    press(cpu, board, K['k6'])
    chk("карта клавиш: (2,2) показывает '6'", visible(board) == "   6",
        "%r" % visible(board))
    press(cpu, board, K['F1'])

    # ---- 14. блэнкинг по всему прогону ----
    chk("БЛЭНКИНГ: каждый разряд переключён при погашенных сегментах",
        not board.ghost, "нарушений: %d %s" %
        (len(board.ghost), board.ghost[:3]))
    ph = phases(board)
    ok = sum(1 for (_, _, sb, _) in ph if sb == 0)
    chk("фаз регенерации достаточно и все с гашением",
        len(ph) > 200 and ok == len(ph),
        "фаз: %d, с гашением: %d" % (len(ph), ok))

    # ---- 15. тик: тон и длительность (арифметика полного образа) ----
    snd_ev = [(t, v) for (t, p, v) in board.log
              if p == 1 and (v & 0x10)]
    if len(snd_ev) >= 4:
        # snd_ev - события с D4=1; внутри одного тика подряд идут через
        # период тона (2 ед BUNIT: тоггл каждую ед, бит=1 через 2 ед).
        # Межтиковые зазоры >> периода - фильтруем по порогу.
        diffs = [snd_ev[i][0] - snd_ev[i - 1][0]
                 for i in range(1, len(snd_ev))]
        within = [d for d in diffs if d < 12000]   # 2 ед ~ 7650 T
        if len(within) < 2:
            within = diffs[:2]
        period = sum(within[:4]) / min(4, len(within))
        unit = period / 2.0                   # единица ~1 мс
        freq = 1e9 / (period * STEP_NS)
        tick_ms = 30 * unit * STEP_NS / 1e6
        print("  измерено: период тона %.0f T (ед %.0f T = %.0f мкс) -> "
              "тон ~%.0f Гц; тик полного образа (30 ед) ~ %.1f мс"
              % (period, unit, unit * STEP_NS / 1e3, freq, tick_ms))
        chk("тон тика 440..560 Гц (полупериод ~1 мс)",
            440 <= freq <= 560, "%.0f Гц" % freq)
        chk("тик полного образа 25..40 мс", 25 <= tick_ms <= 40,
            "%.1f мс" % tick_ms)
    else:
        chk("есть SND-активность (тик)", False,
            "SND-событий: %d" % len(snd_ev))

    print()
    print("=" * 76)
    if verify_fw.fail == 0:
        print("ИТОГ: ВСЕ ПРОВЕРКИ ПАСС")
    else:
        print("ИТОГ: ПРОВАЛОВ: %d" % verify_fw.fail)
    print("=" * 76)
    sys.exit(1 if verify_fw.fail else 0)


if __name__ == '__main__':
    main()
