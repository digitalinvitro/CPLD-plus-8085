#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sim_diag3_timeline.py -- ожидаемые эхо-триплеты diag3
[принятый байт][таймлайн hi][таймлайн lo] для ключевых сценариев.

Сетка приёма diag3 (RXN1 = N/2 = 4 кванта):
  s   (E=12) : фронт0 через (3..4)Q от загрузки -> ~0,43-0,55 бита;
  d0..d7(E=11..4): фронты через ровно 8Q -> ~1,5..8,5 бита (как в v1/v2);
  t1..t3 (E=3..1): ~9,5/10,5/11,5 бита.
Свип фазы прескалера и латентности опроса -- как в sim_rx_signature.
"""
import itertools

Q = 50.71
N = 8
RXN1 = 4            # 0,5 бита до выборки СТАРТА
ENTRY = 5.0
T_SAMP = 21.6
P_POLL = 74.0
T_LOAD = 15.0
H_FR = 12


def level(t, baud, byte):
    bit = 1e6 / baud
    k = int(t // bit) if t >= 0 else -1
    if k < 0 or k >= 10:
        return 1
    if k == 0:
        return 0
    if k == 9:
        return 1
    return (byte >> (k - 1)) & 1


def decode(byte_ch, baud, phi, det, line_mode='frame'):
    t_load = det + T_LOAD
    T0 = phi + ((t_load - phi) // Q) * Q
    f0 = T0 + RXN1 * Q
    bits = []
    for k in range(H_FR):
        t = f0 + k * N * Q + ENTRY + T_SAMP
        if line_mode == 'low':
            lv = 0
        else:
            lv = level(t, baud, byte_ch)
        bits.append(lv)
    rx = 0
    for k in range(8):
        rx |= bits[1 + k] << k          # d0..d7 = выборки 2..9 (E=11..4)
    hi = 0
    for k in range(4):
        hi = (hi << 1) | bits[k]        # s,d0,d1,d2 (+4 нуля сверху)
    lo = 0
    for k in range(8):
        lo = (lo << 1) | bits[4 + k]    # d3..d7,t1,t2,t3
    return rx, hi, lo, bits


def sweep(byte_ch, baud, line_mode='frame'):
    res = {}
    for phi in [i * Q / 40.0 for i in range(40)]:
        for det in [0.5 + i * (P_POLL - 1.0) / 24.0 for i in range(25)]:
            r = decode(byte_ch, baud, phi, det, line_mode)
            res.setdefault(r[:3], 0)
            res[r[:3]] += 1
    return sorted(res.items(), key=lambda kv: -kv[1])


print('=== ЭХО diag3: [байт][tl-hi][tl-lo] ===\n')
print('--- Терминал 2400 (норма) ---')
for name, code in [('a', 0x61), ('o', 0x6F), ('3', 0x33),
                   ('CR', 0x0D), ('SP', 0x20)]:
    sig = sweep(code, 2400)
    top = ', '.join('%02X %02X %02X(%d)' % (k[0][0], k[0][1], k[0][2], k[1]) for k in sig[:3])
    print(f"  '{name}': {top}")

print('\n--- Терминал ~1200 (вдвое медленнее) ---')
for name, code in [('a', 0x61), ('o', 0x6F), ('CR', 0x0D)]:
    sig = sweep(code, 1200)
    top = ', '.join('%02X %02X %02X(%d)' % (k[0][0], k[0][1], k[0][2], k[1]) for k in sig[:3])
    print(f"  '{name}': {top}")

print('\n--- Терминал ~4800 (профиль fw_mon v5) ---')
for name, code in [('a', 0x61), ('CR', 0x0D)]:
    sig = sweep(code, 4800)
    top = ', '.join('%02X %02X %02X(%d)' % (k[0][0], k[0][1], k[0][2], k[1]) for k in sig[:3])
    print(f"  '{name}': {top}")

print('\n--- Линия прижата к 0 весь кадр (самозахват на замороженном SOD / мёртвая линия) ---')
sig = sweep(0x61, 2400, line_mode='low')
print(f"  любой символ: {sig[0][0][0]:02X} {sig[0][0][1]:02X} {sig[0][0][2]:02X} "
      f"(1000/{sig[0][1]})")

# --- окна выборки (крайние случаи) ---
print('\n--- Окна выборки (дет по 5..75 мкс, фаза 0..Q) ---')
worst = {'s': (1e9, -1e9), 'd0': (1e9, -1e9), 'd7': (1e9, -1e9)}
for phi in [i * Q / 40.0 for i in range(40)]:
    for det in [0.5 + i * (P_POLL - 1.0) / 24.0 for i in range(25)]:
        t_load = det + T_LOAD
        T0 = phi + ((t_load - phi) // Q) * Q
        f0 = T0 + RXN1 * Q
        for tag, k in [('s', 0), ('d0', 1), ('d7', 8)]:
            t = f0 + k * N * Q + ENTRY + T_SAMP
            lo, hi = worst[tag]
            worst[tag] = (min(lo, t), max(hi, t))
for tag in ('s', 'd0', 'd7'):
    lo, hi = worst[tag]
    print(f'  {tag}: {lo:.0f}..{hi:.0f} мкс от истинного фронта старта')
