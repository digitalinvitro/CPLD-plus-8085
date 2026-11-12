#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xstream_calc.py — РАСЧЁТ РЕЖИМА XSTREAM v1 (тик -> весь экран в UART).

Модель железа (beta/txuart, CPLD v2.3, подтверждено железом 11-8..11-12):
  - CPU 1821ВМ85 (8085) @ 3.125 МГц, T = 320 нс (кольцо s0..s3, X1 = 6.25 МГц);
  - аппаратный TX-UART 1 000 000 бод 8N1 (25 МГц / 25), кадр 10 бит = 10.000 мкс
    = 31.25T; запись в TXDATA (OUT 04h) при busy отбрасывается ядром;
  - потолок подачи слепым циклом 32T/байт = 97 656 Б/с (97.7% линии, p04 железно).

Формат кадра XSTREAM: A5 5A [SEQ] + 2000 Б экрана (B000h..B7CFh, 80x25, row-major)
= 2003 Б. Экран = ТЕКСТОВЫЙ, байты как есть (CP1251 у ПК-клиента).

Нагрузка ЦП: выдача кадра = посылающий цикл 32.5T/байт (inner 4-байт разворот
+6 NOP: 4x(MOV A,M+OUT+INX H)=92T + 24T NOP + DCR C 4T + JNZ 10T = 130T/4Б) +
слот дисплея XDIG каждые 80 Б (регенерация 7-сегментника не замирает).
"""
T_NS = 320.0            # такт CPU, нс (3.125 МГц)
BAUD = 1_000_000
BITS = 10               # 8N1
N_ROWS, N_COLS = 25, 80
SCREEN = N_ROWS * N_COLS
HDR = 3                 # A5 5A SEQ
FRAME = HDR + SCREEN

# ---- такты посылающего цикла (asm85-таблица 8085A: INX/DCX=6T, JNZ=10T) ----
INNER_IT = 7*35 + 49                          # подгруппа 8 Б: 7x(23+12) + (23+12+14)
INNER_BYTES = 8
OUTER = 147 + 4 + 10                          # CALL XDIG (147T сим) + DCR B + JNZ
OUTER_BYTES = 200
PAYLD_ITERS = SCREEN // OUTER_BYTES           # 10
HDR_T = 7+10 + 7+10 + 13+10 + 4+13           # A5, 5A, LDA SEQ, OUT, INR+STA
CNT_T = 90                                    # SEQ->ASCII в счётчик экрана
SAVE_T = 12*4 + 10*4                         # PUSH/POP PSW,B,D,H
SEND_T = (PAYLD_ITERS * (25 * INNER_IT + OUTER)
          + HDR_T + CNT_T + SAVE_T)

def main():
    byte_us = BITS / BAUD * 1e6
    print("=== ЛИНИЯ ===")
    print(f"бод {BAUD} 8N1: байт {byte_us:.3f} мкс = {byte_us/(T_NS/1000):.2f}T; "
          f"линия {BAUD/BITS:.0f} Б/с")
    print(f"потолок подачи 32T = {32*T_NS/1000:.2f} мкс/Б = {1e6/(32*T_NS/1000):.0f} Б/с "
          f"= {31.25/32*100:.1f}% линии (p04 железно 97 887 Б/с)")

    print("\n=== КАДР ===")
    print(f"экран {SCREEN} Б (80x25) + шапка {HDR} = {FRAME} Б")
    wire_ms = FRAME * byte_us / 1000
    send_ms = SEND_T * T_NS / 1e6
    send_per_byte = SEND_T / FRAME
    print(f"время на линии (чистый провод): {wire_ms:.2f} мс")
    print(f"посылающий цикл: подгруппа {INNER_IT}T/{INNER_BYTES}Б = {INNER_IT/INNER_BYTES:.2f}T/Б, "
          f"мин. гэп OUT->OUT 35T (>= 31.25T: {'ОК, 0 отбросов' if 35 >= 31.25 else 'ОТБРОСЫ!'})")
    slot_us = OUTER_BYTES * (send_per_byte * T_NS / 1000)
    print(f"слот дисплея {OUTER-14}T каждые {OUTER_BYTES} Б; "
          f"слот каждые {slot_us/1000:.3f} мс -> полный цикл 4 разрядов {slot_us*4/1000:.2f} мс "
          f"({1000/(slot_us*4/1000):.0f} Гц/разряд — без мерцания)")
    print(f"итого CPU: {SEND_T}T/кадр = {send_per_byte:.1f}T/Б = "
          f"{send_per_byte*T_NS/1000:.2f} мкс/Б -> посылка {send_ms:.2f} мс")

    print("\n=== НАГРУЗКА ЦП vs FPS (период = 1/FPS) ===")
    print(f"{'FPS':>6} {'период,мс':>10} {'нагрузка,%':>10}  вердикт")
    for fps in (10, 20, 20.03, 21.0, 21.33, 22.0, 24.0, 25.0):
        period = 1000.0 / fps
        load = send_ms / period * 100
        ok = "ЦП<=50%: ОК" if load <= 50 else "ЦП>50%: НЕ ОК"
        inr = "в 20-25" if 20 <= fps <= 25 else "вне 20-25"
        print(f"{fps:>6.2f} {period:>10.2f} {load:>10.1f}  {ok}; {inr}")
    print("вывод: 20.0-21.3 FPS при нагрузке <= 50%; 22+ FPS требует > 50% -> "
          "по ТЗ владельца требование к FPS снижается; фолбэк 10 FPS = 22.9% ЦП")

    print("\n=== ТИК SW-режима (монитор fw_mon ACdE, CPU 3.125 МГц) ===")
    # слот скана: 4 колонки по ~175T + REFRESH ~277T + XSCHK ~45T
    pass_t = 4*175 + 277 + 45
    # единица QUNIT: LXI B,K_MS(10) + 144 x (DCX+MOV+ORA+JNZ=24T) + CALL REFRESH
    unit_t = 10 + 144*24 + 17+260 + 10
    print(f"слот скана ~{pass_t}T = {pass_t*T_NS/1000:.0f} мкс; "
          f"единица QUNIT ~{unit_t}T = {unit_t*T_NS/1000:.3f} мкс "
          f"(K_MS=144 на CPU 3.125 МГц; в fw_mon было ~1.05 мс на 3.571 МГц)")
    for fps in (20.0, 21.0, 21.33):
        period = 1000.0/fps
        n_pass = int((period - send_ms) / (pass_t*T_NS/1e6))
        real = send_ms + n_pass*(pass_t*T_NS/1e6)
        print(f"цель {fps:.2f} FPS: {n_pass} слотов скана -> период ~{real:.1f} мс "
              f"(= {1000/real:.2f} FPS), нагрузка {send_ms/real*100:.1f}%")

    print("\n=== ВАРИАНТ HW (v24: таймер CPLD -> RST 7.5, тик 51.2 мкс, ре-арм OUT 06h) ===")
    tick_us = 51.2
    print(f"{'N':>4} {'xD':>3} {'период,мс':>10} {'FPS':>7} {'нагрузка,%':>10}")
    for n, d in ((195, 4), (195, 5), (229, 4), (183, 5), (195, 10)):
        per = n * tick_us * d / 1000
        print(f"{n:>4} {d:>3} {per:>10.2f} {1000/per:>7.2f} {send_ms/per*100:>10.1f}")
    print("ПРИНЯТО v1: N=250, делитель 2 -> период = посылка + 2x12.80 = 49.7 мс (20.1 FPS)")
    print("(формула периода HW: посылка + XS_DIVN x N x 51.2 мкс; делитель 3 дал 61 мс - сим)")

if __name__ == '__main__':
    main()
