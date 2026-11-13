#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xlog_analyze.py — анализатор CSV-логов клиента XSTREAM (xstream_view.ps1).

Понимает ОБА формата:
  v1.2.1 (живой лог владельца 11-13): шапка 7 колонок, строки несут 8
         полей — {3:F1} формата -f брал культуру потока (ru-RU -> "17,1"),
         и запятая-CSV расщепляла dt на целую и дробную части (урок 12);
         распознаётся автоматически: 5-е поле = одна цифра 0-9.
  v1.2.2: чистые 7 полей, dt через InvariantCulture ("17.1"), строки kind
         OPEN/D/S/R/FIN (R = рестарт потока платы, v1.2.2).

Считает: длительность, кадры (D-строки + «Итог»-овый счётчик парсера,
если передан), медианный dt и рабочую точку FPS, события гэпов по
кумулятивной колонке seq_gaps (в v1.2.2 рестарты идут в kind R и НЕ
раздувают seq_gaps), ресинки, обёртки SEQ 255->0, байтовую смету
(кадровая нагрузка 2003 Б/кадр vs bytes_total), среднюю скорость линии.

Запуск:
  python3 xlog_analyze.py <лог.csv> [--frames N]
    --frames N  счётчик кадров парсера из «Итог» клиента (для байтовой
                сметы; по умолчанию = числу D-строк)
"""
import sys
from datetime import datetime

def main():
    args = sys.argv[1:]
    if not args:
        print("использование: xlog_analyze.py <лог.csv> [--frames N]")
        return 2
    path = args[0]
    frames_parser = None
    if "--frames" in args:
        frames_parser = int(args[args.index("--frames") + 1])

    rows = []
    with open(path, "r", encoding="cp1251", errors="replace") as f:
        header = f.readline().strip()
        for line in f:
            line = line.strip()
            if line:
                rows.append(line.split(","))

    widths = {}
    for fs in rows:
        widths[len(fs)] = widths.get(len(fs), 0) + 1
    print("ШАПКА (%d колонок): %s" % (len(header.split(",")), header))
    print("ПОЛЕЙ В СТРОКАХ: " + ", ".join("%d: %d строк" % kv for kv in sorted(widths.items())))

    # --- распознавание формата ---
    fmt = "v1.2.2"
    if 8 in widths and widths.get(7, 0) == 0:
        n_digit = sum(1 for fs in rows if len(fs) == 8 and len(fs[4]) == 1 and fs[4].isdigit())
        if n_digit == widths[8]:
            fmt = "v1.2.1 (фантомная 8-я колонка: dt '17,1' -> '17','1', урок 12)"
        else:
            fmt = "v1.2.1 (НЕраспознанная раскладка 8 полей!)"
    elif 7 in widths and widths.get(8, 0):
        fmt = "СМЕСЬ форматов (7 и 8 полей)!"
    print("ФОРМАТ: %s" % fmt)

    def dt_of(fs):
        if len(fs) == 8 and len(fs[4]) == 1 and fs[4].isdigit():
            return float(fs[3] + "." + fs[4])
        return float(fs[3])

    def idx_of(fs):
        # ширино-зависимые индексы: 8 полей (v1.2.1, расщеплённый dt) или 7 (v1.2.2)
        if len(fs) == 8:
            return 5, 6, 7   # bytes_total, resyncs, seq_gaps
        return 4, 5, 6

    def ts_of(fs):
        return datetime.strptime(fs[0], "%Y-%m-%dT%H:%M:%S.%f")

    D = [(ts_of(fs), int(fs[2]), dt_of(fs), int(fs[idx_of(fs)[0]]), int(fs[idx_of(fs)[1]]), int(fs[idx_of(fs)[2]]))
         for fs in rows if fs[1] == "D"]
    kinds = {}
    for fs in rows:
        kinds[fs[1]] = kinds.get(fs[1], 0) + 1
    r_rows = [(ts_of(fs), int(fs[2]), dt_of(fs)) for fs in rows if fs[1] == "R"]

    t0, t1 = ts_of(rows[0]), ts_of(rows[-1])
    dur = (t1 - t0).total_seconds()
    print("-" * 76)
    print("СЕАНС: %s .. %s = %.1f с" % (t0.time(), t1.time(), dur))
    print("СТРОКИ: " + ", ".join("%s=%d" % kv for kv in sorted(kinds.items())))
    if r_rows:
        for t, seq, dt in r_rows:
            print("  R (рестарт потока): %s, SEQ->%d, dt=%.1f мс" % (t.time(), seq, dt))
    nD = len(D)
    if frames_parser is None:
        frames_parser = nD
        print("Кадров (парсер = D-строки): %d" % nD)
    else:
        print("Кадров: D-строк %d (лог), парсер %d (Итог) — D <= парсер: один D-ряд на тик таймера" % (nD, frames_parser))
    avg_fps = frames_parser / dur if dur > 0 else 0.0
    print("Средний FPS за сеанс: %.2f" % avg_fps)

    dts = sorted(d for _, _, d, _, _, _ in D if d < 200)
    if dts:
        def pct(p):
            return dts[min(len(dts) - 1, int(round((len(dts) - 1) * p)))]
        med = pct(0.50)
        print("dt (D-строки <200 мс): n=%d  min=%.1f  p10=%.1f  медиана=%.1f  p90=%.1f  max=%.1f мс"
              % (len(dts), dts[0], pct(0.10), med, pct(0.90), dts[-1]))
        print("Рабочая точка по медиане: %.2f FPS (сим-прогноз 20.1 FPS / 49.8 мс; окно ТЗ 20-25)" % (1000.0 / med))

    # --- гэпы по кумулятивной колонке ---
    print("-" * 76)
    print("СОБЫТИЯ ГЭПОВ (прыжки кумулятивной seq_gaps):")
    events, prev_g, prev_seq = [], 0, None
    for t, seq, dt, b, rs, g in D:
        if g != prev_g:
            events.append((t, prev_seq, seq, g - prev_g, dt))
            prev_g = g
        prev_seq = seq
    for t, ps, seq, add, dt in events:
        print("  %s: SEQ %s -> %d, +%d гэпов, dt=%.1f мс"
              % (t.time(), ps if ps is not None else "-", seq, add, dt))
    tot = sum(e[3] for e in events)
    print("Итого гэпов по событиям: %d" % tot)

    res_max = max([int(fs[idx_of(fs)[1]]) for fs in rows if fs[1] in ("D", "S", "FIN", "R")] or [0])
    print("Ресинки (макс): %d -> %s" % (res_max, "ЛИНИЯ ЧИСТАЯ" if res_max == 0 else "ЕСТЬ МУСОР"))
    wraps = sum(1 for i in range(1, len(D)) if D[i][1] < D[i - 1][1])
    print("Обёрток SEQ 255->0: %d (норма)" % wraps)

    # --- байты ---
    last = rows[-1]
    b_last = int(last[idx_of(last)[0]])
    fb = frames_parser * 2003
    print("-" * 76)
    print("БАЙТЫ: bytes_total = %d; кадровая нагрузка %d x 2003 = %d; мусор/недокадры = %d Б (%.2f%%)"
          % (b_last, frames_parser, fb, b_last - fb, 100.0 * (b_last - fb) / max(1, b_last)))
    print("Скорость линии средняя: %.1f КБ/с (поток при %.2f FPS = %.1f КБ/с; линия 100 КБ/с макс)"
          % (b_last / dur / 1024.0, avg_fps, 2003 * avg_fps / 1024.0))
    print("=" * 76)
    return 0

if __name__ == "__main__":
    sys.exit(main())
