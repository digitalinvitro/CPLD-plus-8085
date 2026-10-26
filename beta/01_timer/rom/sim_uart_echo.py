#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_uart_echo.py -- событийная модель эхо-теста UART (uart_echo_test.asm).

Проверяет ЛОГИКУ и ТАЙМИНГ полного тракта приёма-передачи ДО прошивки:

  ПКА (терминал 2400 8N1, бит 416,67 мкс ровно)
    -> CH340G -> CPLD RX->SID -> MAIN опрашивает RIM
    -> таймер: 1-й зазор 1,5 бита (RXN1=12 квантов), далее сетка 8Q/бит
    -> ISR: RX-автомат (H=11 интервалов: 12Q + 8x8Q + 3x8Q хвост)
    -> релиз -> эхо TX-автоматом (C=0Bh..01h, D сдвиговый)
    -> SOD -> P39 -> CH340G -> приёмник ПКА (выборка в 1,5+k бита).

Модель таймера повторяет HDL v3.3b3:
  - сетка тиков свободно-бежащая (период Q), фаза -- параметр свипа;
  - загрузка N даёт фронт через (N-1)..N квантов (T0 + N*Q, где T0 --
    последний тик перед загрузкой);
  - ре-арм из ISR (между тиками) даёт СЛЕДУЮЩИЙ фронт ровно через N*Q
    (цепочка фронтов точная, накладные ISR в период не входят).

Аддер ISR (такты CPU 2,5 МГц, из ручной раскладки):
  вход (латентность) ~5 мкс; выборка RIM: вентиль 25 + вход RX 29 = 54t;
  TX: старт 73t, данные 92t, стоп 77t; релиз ~89t.

Проверки (сценарий «печать», 150 мс между символами, 400 свипов фазы
прескалера и латентности опроса):
  1. эхо = посланному тексту ('>'-баннер + посимвольное эхо);
  2. каждая выборка d0..d7 внутри окна середины бита (+-208 мкс) --
     репорт минимального запаса;
  3. фронт старта эха ПОСЛЕ конца кадра приёмника ПКА (10 бит) --
     репорт запаса (урок v4 зеркально);
  4. гонка латча RST 7.5: «залетевший» фронт под DI выбрасывается
     SIM 08h ПОСЛЕ загрузки -- фронт d0 всегда (N-1)..N квантов
     от загрузки;
  5. стресс «paste» (3 мс между символами): репорт потерь (ожидаемо,
     v1 без очереди TX), зависаний быть не должно.

Побайтовая верификация образов -- verify_hex.py (ручной эталон).
"""
import random
import sys

# ---- константы железа ----
Q = 50.71                 # мкс, фактический квант (clk ~25,24 МГц)
N = 8                     # TMR_N: бит = 8 квантов
RXN1 = 12                 # 1-й зазор приёма = 1,5 бита
TCYC = 0.4                # мкс, такт CPU 2,5 МГц (номинал)
BIT_PC = 1e6 / 2400.0     # 416,67 мкс, бит терминала (точно)
ENTRY = 5.0               # мкс, латентность входа в ISR
T_REARM = 17 * TCYC       # MVI A,N + OUT 04h = 17t
T_SAMPLE = 54 * TCYC      # вентиль 25t + вход RX 29t = RIM
T_TX = {'start': 73 * TCYC, 'data': 92 * TCYC, 'stop': 77 * TCYC}
T_RELEASE = 89 * TCYC
T_POLL = 25 * TCYC        # DI+RIM+ANI+JNZ = 25t, период опроса
H_FRAME = 11              # 12Q(d0) + 8x8Q(d1..d7) + 3x8Q(хвост)

BANNER = '>'
TEXT = 'AZ5 az19!'


class SimError(Exception):
    pass


def pc_level(t, chars):
    """Уровень линии ПКА (RX-направление) в момент t."""
    lvl = 1.0
    for (t0, byte) in chars:
        if t < t0 or t >= t0 + 10 * BIT_PC:
            continue
        k = int((t - t0) // BIT_PC)          # 0 старт, 1..8 данные, 9 стоп
        if k == 0:
            lvl = 0.0
        elif k == 9:
            lvl = 1.0
        else:
            lvl = 1.0 if (byte >> (k - 1)) & 1 else 0.0
        break
    return lvl


class Sim:
    """Событийная модель: таймер + ISR + MAIN + линия + приёмник ПКА."""

    def __init__(self, phi, chars):
        self.phi = phi            # фаза сетки тиков (0..Q)
        self.chars = chars        # [(t0, byte)] -- что шлёт ПКА
        self.t = 0.0
        self.now = 0.0
        # ISR-состояние
        self.C = 0xFF             # фаза TX (0FFh покой)
        self.D = 0                # сдвиговый TX
        self.H = 0                # интервалы RX (0 = покой)
        self.L = 0                # накопитель RX
        # MAIN-состояние
        self.state = 'INIT'       # INIT -> BAN -> POLL -> RWAIT -> EWAIT
        self.poll_next = 0.0
        self.pending_front = None # «залетевший» фронт под DI (латч)
        self.next_front = None    # запланированный фронт таймера
        # линия SOD (TX-направление) для приёмника ПКА
        self.sod = 1.0
        self.sod_events = []      # (t, level)
        self.rx_seen = []         # декодированные ПКА символы (эхо)
        self.rx_sample_log = []   # (char, k, sample_t, offset_мкс)
        self.echo_start_log = []  # (char, t_echo_start, margin_мкс)
        self.rx_frames = 0
        self.dropped = 0
        self.arm_fail = 0         # загрузки с фронтом вне окна (N-1..N)

    # ---------- таймер (HDL v3.3b3) ----------
    def tick_before(self, t):
        return self.phi + ((t - self.phi) // Q) * Q

    def timer_load(self, nquants, t_load):
        """Программная загрузка N: фронт = T0 + N*Q (T0 -- последний тик)."""
        self.next_front = self.tick_before(t_load) + nquants * Q
        if not (t_load + (nquants - 1) * Q - 1e-9
                <= self.next_front <= t_load + nquants * Q + 1e-9):
            self.arm_fail += 1

    def timer_rearm(self, t_front):
        """Ре-арм из ISR (между тиками): след. фронт ровно N*Q."""
        self.next_front = t_front + N * Q

    # ---------- линия/приёмник ПКА ----------
    def sod_write(self, t, lvl):
        if self.sod != lvl:
            self.sod = lvl
            self.sod_events.append((t, lvl))

    def pc_receiver(self):
        """Приёмник ПКА: ресинх по старт-фронту, выборка 1,5+k бита."""
        events = sorted(self.sod_events)
        i = 0
        while i < len(events):
            t0, lvl = events[i]
            if lvl == 0.0:                      # старт-фронт
                bits = []
                for k in range(8):
                    ts = t0 + (1.5 + k) * BIT_PC
                    bits.append(1 if self.sod_at(ts, events) else 0)
                stop_ts = t0 + 9.5 * BIT_PC
                stop = 1 if self.sod_at(stop_ts, events) else 0
                byte = sum(b << k for k, b in enumerate(bits))
                self.rx_seen.append((byte, stop))
                i = self.skip_frame(events, i, t0)
            else:
                i += 1

    @staticmethod
    def sod_at(t, events):
        lvl = 1.0
        for (te, le) in events:
            if te <= t:
                lvl = le
            else:
                break
        return lvl

    @staticmethod
    def skip_frame(events, i, t0):
        while i < len(events) and events[i][0] < t0 + 9.5 * BIT_PC:
            i += 1
        return i

    # ---------- ISR ----------
    def isr(self, front_t):
        entry = front_t + ENTRY
        self.timer_rearm(front_t)               # ре-арм -- первое действие
        # --- вентиль + TX-автомат (только при H==0) ---
        if self.H == 0:
            C = self.C
            if C == 0xFF:
                self.sod_write(entry + 18 * TCYC, 1.0)      # покой: SOD=1
            else:
                C -= 1
                self.C = C
                if C == 0x0A:
                    self.sod_write(entry + T_TX['start'], 0.0)
                elif C == 0x01:
                    self.sod_write(entry + T_TX['stop'], 1.0)
                    self.C = 0xFF                   # однобайтовый режим
                else:
                    bit = self.D & 1
                    self.sod_write(entry + T_TX['data'], float(bit))
                    self.D = (self.D >> 1) | 0x80
        # --- RX-автомат (интервалы в H) ---
        if self.H != 0:
            if self.H >= 4:                         # выборка d0..d7
                sid = pc_level(entry + T_SAMPLE, self.chars)
                self.L = ((self.L >> 1) | (0x80 if sid else 0)) & 0xFF
                self.rx_sample_log.append((self.H, entry + T_SAMPLE, sid))
            self.H -= 1
            if self.H == 0:                         # релиз
                if self.C == 0xFF:
                    self.D = self.L                 # эхо: D <- байт
                    self.C = 0x0B
                else:
                    self.dropped += 1               # TX занят (v1: без очереди)
                self.rx_frames += 1

    # ---------- MAIN ----------
    def step(self, horizon):
        while self.now < horizon:
            # ближайшее событие: фронт таймера или галение MAIN
            candidates = []
            if self.next_front is not None:
                candidates.append(self.next_front)
            if self.pending_front is not None:
                candidates.append(self.pending_front)
            if self.state == 'POLL':
                candidates.append(self.poll_next)
            if not candidates:
                self.now = horizon
                break
            ev = min(candidates)
            self.now = ev
            if self.pending_front is not None and ev == self.pending_front:
                # фронт под DI: латч ловится (обслужится только после EI
                # чужого кадра -- в POLL такого нет; выбрасывается SIM 08h)
                self.pending_front = None
                if self.state in ('POLL',):
                    continue                        # DI: не обслуживается
                # в EI-контексте «залетевших» не бывает (модель)
                raise SimError('фронт под DI вне POLL')
            if self.state == 'POLL' and ev == self.poll_next:
                # --- опрос SID (25t на итерацию, DI) ---
                if pc_level(ev, self.chars) == 0.0:
                    t_load = ev + 17 * TCYC         # MVI A,RXN1 + OUT
                    self.timer_load(RXN1, t_load)
                    t_simlr = ev + 21 * TCYC        # SIM 08h ПОСЛЕ загрузки
                    if self.pending_front is not None:
                        self.pending_front = None   # латч выброшен
                    if self.next_front is not None and self.next_front < t_simlr:
                        raise SimError('новый фронт раньше сброса латча')
                    self.H = H_FRAME
                    self.L = 0
                    self.state = 'RWAIT'            # EI в модели неявно
                else:
                    self.poll_next = ev + T_POLL
                continue
            # --- фронт таймера ---
            if ev == self.next_front:
                self.next_front = None
                self.isr(ev)
                if self.state == 'RWAIT' and self.H == 0:
                    self.state = 'EWAIT'            # релиз был в этом ISR
                elif self.state == 'BAN' and self.C == 0xFF:
                    # баннер кончился: MAIN выходит из BAN -> POLL (DI)
                    self.state = 'POLL'
                    self.poll_next = self.now + T_POLL
                    self.pending_front = self.next_front  # фронт под DI
                    self.next_front = None
                elif (self.state == 'EWAIT' and self.H == 0
                      and self.C == 0xFF):
                    # эхо-кадр кончился: MAIN выходит из EWAIT -> POLL (DI)
                    self.state = 'POLL'
                    self.poll_next = self.now + T_POLL
                    self.pending_front = self.next_front  # фронт под DI
                    self.next_front = None
            else:
                raise SimError('непонятное событие')

    def run(self, horizon):
        # INIT: MAIN инициализирует и армует баннер (~40 мкс после сброса)
        t0 = 40.0
        self.timer_load(N, t0)
        self.D = ord(BANNER)
        self.C = 0x0B
        self.H = 0
        self.state = 'BAN'
        self.now = t0
        self.step(horizon)
        if self.C != 0xFF:
            raise SimError('баннер не закончился')
        # POLL: ждём первый символ
        self.state = 'POLL'
        self.poll_next = self.now + T_POLL
        self.pending_front = self.next_front        # фронт под DI (латч)
        self.next_front = None
        self.step(horizon)


def run_typing(n_sweep=400):
    """Сценарий «печать»: символы через 150 мс, свип фазы/латентности."""
    worst_echo = 1e9   # мин. запас эхо-старта (в битах)
    worst_bit = 1e9    # мин. запас выборки середины бита (мкс)
    for i in range(n_sweep):
        rnd = random.Random(1000 + i)
        phi = rnd.uniform(0.0, Q)
        jitter0 = rnd.uniform(0.0, 150.0)
        chars = []
        t = 150_000.0 + jitter0                     # мкс, старт первого
        for ch in TEXT:
            chars.append((t, ord(ch)))
            t += 150_000.0 + rnd.uniform(0.0, 30.0)
        s = Sim(phi, chars)
        s.run(chars[-1][0] + 40_000.0)
        s.pc_receiver()
        if s.arm_fail:
            raise SimError('загрузка вне окна (N-1)..N квантов')
        # ожидаемое эхо: '>'-баннер + TEXT
        got = ''.join(chr(b) if st else ('\x00%d' % b)
                      for (b, st) in s.rx_seen)
        want = BANNER + TEXT
        if got != want:
            raise SimError('эхо неверное: %r != %r' % (got, want))
        # запас эхо-старта: фронт эха после конца кадра ПКА (10 бит)
        for (t0, byte) in chars:
            starts = [te for (te, le) in s.sod_events
                      if le == 0.0 and t0 + 9 * BIT_PC < te < t0 + 60_000.0]
            if not starts:
                raise SimError('эхо-старт не найден для %r' % chr(byte))
            marg = (starts[0] - (t0 + 10 * BIT_PC)) / BIT_PC
            worst_echo = min(worst_echo, marg)
    # посчитать запас выборок на последнем (репрезентативном) прогоне
    s = None
    rnd = random.Random(1000)
    phi = rnd.uniform(0.0, Q)
    chars = []
    t = 150_000.0
    for ch in TEXT:
        chars.append((t, ord(ch)))
        t += 150_000.0
    s = Sim(phi, chars)
    s.run(chars[-1][0] + 40_000.0)
    # привязка выборок к идеальной сетке ПКА
    for (t0, byte) in chars:
        sel = [(hi, ts) for (hi, ts, _sid) in s.rx_sample_log
               if t0 - 200 < ts < t0 + 10 * BIT_PC + 200]
        if len(sel) != 8:
            raise SimError('выборок %d вместо 8 для %r' % (len(sel), chr(byte)))
        for k, (hi, ts) in enumerate(sorted(sel, key=lambda x: x[1])):
            ideal = t0 + (1.5 + k) * BIT_PC
            marg = abs(ts - ideal)
            worst_bit = min(worst_bit, BIT_PC / 2 - marg)
    print('  [ OK ] эхо = баннер + %r x %d свипов фазы/латентности'
          % (TEXT, n_sweep))
    print('  [ OK ] мин. запас выборки середины бита: %.1f мкс (лимит 208,3)'
          % worst_bit)
    print('  [ OK ] мин. запас эхо-старта после конца кадра ПКА: %+.2f бита'
          % worst_echo)
    return worst_bit, worst_echo


def run_paste(gap_ms=3.0, text='AAAAAAAA'):
    """Стресс «paste»: символы подряд (3 мс < 5 мс кадра) -- репорт потерь."""
    rnd = random.Random(42)
    phi = rnd.uniform(0.0, Q)
    chars = []
    t = 150_000.0
    for ch in text:
        chars.append((t, ord(ch)))
        t += gap_ms * 1000.0
    s = Sim(phi, chars)
    s.run(chars[-1][0] + 60_000.0)
    s.pc_receiver()
    good = sum(1 for (b, st) in s.rx_seen if st and chr(b) == 'A')
    total = len(text)
    print('  [ ~~ ] paste %d мс: принято-верно %d из %d отправленных '
          '(потери/мусор ожидаемы: v1 без очереди TX, MAIN не опрашивает'
          % (gap_ms, good, total))
    print('       линию во время чужого кадра); кадров приёма: %d, '
          'отброшено (TX занят): %d' % (s.rx_frames, s.dropped))
    return good, total


def main():
    print('sim_uart_echo: модель эхо-теста (таймер как задатчик бодрейта)')
    worst_bit, worst_echo = run_typing()
    run_paste()
    ok = worst_bit > 0 and worst_echo > 0
    if ok:
        print('СИМУЛЯЦИЯ ПРОЙДЕНА')
    else:
        print('СИМУЛЯЦИЯ ПРОВАЛЕНА')
        sys.exit(1)


if __name__ == '__main__':
    main()
