#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_rx_signature.py -- сигнатурная таблица: что наш RX (uart_echo, 2400)
декодирует из кадра терминала при РАЗНОЙ фактической скорости терминала.

Цель: по показаниям дисплея diag (байт + биты хвоста E) определить, что
реально шлёт терминал. Мотивация -- отчёт владельца 10-24 (diag v1):
  счётчик тикает на каждое нажатие, эхо в терминале почти всегда
  НЕВИДИМО (байт 00..1F), изредка 'ю' (CP1251 = 0xFE).
Гипотеза: терминал шлёт НЕ на 2400 (например, 1200 -- профиль монитора).

Модель приёма (подтверждена по HDL v3.3b3 и sim_uart_echo.py):
  - терминал: кадр 10 бит (8N1), бит = 1e6/бод ровно, старт-фронт t=0;
  - MAIN ловит фронт с латентностью det (0..P_POLL, свип);
  - OUT TMRP <- 12 через ~15 мкс после выборки опроса;
  - сетка тиков свободно-бежащая (фаза phi -- свип), загрузка даёт
    фронт через (N-1)..N квантов: Front0 = T0 + 12*Q, T0 = последний
    тик перед загрузкой;
  - ре-арм из вектора: следующие фронты РОВНО через 8*Q (накладные ISR
    в период не входят);
  - выборка в ISR: вход + RIM ~ 26,6 мкс от фронта;
  - кадр: s0..s7 (H=11..4) -> байт LSB-first; хвост t1..t3 (H=3..1)
    -> E = t1<<2 | t2<<1 | t3 (ожидание при 2400: E=7).

Вывод: для каждой пары (символ, бод) -- множество достижимых (байт, E).
"""
import itertools

Q = 50.71          # мкс, квант (clk ~25,24 МГц)
N = 8
RXN1 = 12
ENTRY = 5.0        # мкс, вход в ISR
T_SAMP = 21.6      # мкс, вентиль+вход RIM (54t @ 2,5 МГц)
P_POLL = 74.0      # мкс, период опроса MAIN (diag, 185 тактов)
T_LOAD = 15.0      # мкс, от выборки опроса до OUT TMRP
H_FR = 11          # интервалов в кадре


def level(t, baud, byte):
    """Уровень линии терминала в момент t (кадр от t=0)."""
    bit = 1e6 / baud
    k = int(t // bit) if t >= 0 else -1
    if k < 0 or k >= 10:
        return 1                      # idle
    if k == 0:
        return 0                      # старт
    if k == 9:
        return 1                      # стоп
    return (byte >> (k - 1)) & 1      # данные d0..d7


def decode(byte_ch, baud, phi, det):
    """Один прогон: байт+E, принятые нашим RX."""
    t_load = det + T_LOAD
    T0 = phi + ((t_load - phi) // Q) * Q          # последний тик до загрузки
    f0 = T0 + RXN1 * Q                            # первый фронт (d0)
    bits, tail = [], []
    for k in range(H_FR):
        t = f0 + k * N * Q + ENTRY + T_SAMP
        lv = level(t, baud, byte_ch)
        (bits if k < 8 else tail).append(lv)
    rx = 0
    for k in range(8):
        rx |= bits[k] << k
    E = (tail[0] << 2) | (tail[1] << 1) | tail[2]
    return rx, E


def sweep(byte_ch, baud):
    res = {}
    for phi in [i * Q / 40.0 for i in range(40)]:
        for det in [0.5 + i * (P_POLL - 1.0) / 24.0 for i in range(25)]:
            rx, E = decode(byte_ch, baud, phi, det)
            res.setdefault((rx, E), 0)
            res[(rx, E)] += 1
    return sorted(res.items(), key=lambda kv: -kv[1])


CHARS = [
    ('a', 0x61), ('b', 0x62), ('o', 0x6F), ('w', 0x77), ('x', 0x78),
    ('5', 0x35), ('?', 0x3F), ('A', 0x41), ('SP', 0x20),
    ('CR', 0x0D), ('ю', 0xFE), ('р', 0xE0),
]
BAUDS = [300, 600, 1200, 1800, 2400, 4800, 9600, 19200]

print('Сигнатуры приёма: наш RX (2400) <- терминал (бод X)')
print('байт=hex, E=биты хвоста (7 = хвост чист 1-цами)')
print()
for baud in BAUDS:
    mark = ' <-- норма' if baud == 2400 else ''
    print('=== терминал %d бод%s ===' % (baud, mark))
    for name, code in CHARS:
        sig = sweep(code, baud)
        top = ', '.join('%02X/E%d(%d)' % (k[0][0], k[0][1], k[1])
                        for k in sig[:4])
        print('  %s(%02X): %s' % (name, code, top))
    print()
