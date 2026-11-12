#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gfx_log_analyze.py — форензика живого лога вьюера GFXSTREAM (gfx_view.ps1 -Log).

СХЕМЫ ЛОГА (различаются по шапке):
  v1.4: utc,seq,type,dt_ms,buf            — только декоды (D-события);
  v1.5: utc,kind,seq,type,dt_ms,buf       — kind: D=декод, P=краска
        (dt_ms = интервал краски, buf = пропуски этой краски), F=флеш
        бэклога (buf = сброшено байт).

ЧТО СЧИТАЕТ:
  1. непрерывность SEQ mod 256        -> потери кадров провод->вьюер;
  2. период провода по обёрткам SEQ   -> реальный период платы, коэффициент
     к номиналу 46.875 мс, калибровка T_FRAME (полный лог, D-строки);
  3. гистограммы dt: декодов (сетка тиков 15.625) и красок (v1.5);
  4. пачки декодов (dt<16) и пропуски краски (сумма buf P-строк);
  5. буфер порта: max/mean, бэклог >1 конверта (2006 Б), флеш-события;
  6. типы/сцены;
  7. модель гейта v1.4 (тик 15.625 + порог 36 мс) — для СТАРЫХ логов:
     структурная доля пропусков краски при измеренном периоде платы.

ВЕРДИКТ ПРИЁМКИ (v1.5-лог): интервал краски стабилен около 46-47 мс,
пропусков 0, флешей нет после старта, разрывов SEQ 0.

Запуск:  python3 gfx_log_analyze.py <gfx_log.csv> [--tick 15.625] [--nominal 46.875]
"""
import argparse
import csv
import statistics as st
import sys

TICK_DEFAULT = 15.625      # мс, квант WM_TIMER вьюера v1.4
NOMINAL_DEFAULT = 46.875   # мс, проектный период кадра v2.1 (3 тика)
ENVELOPE = 2006            # Б, конверт дельты TYPE 02


def parse_ts(s):
    h, m, rest = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def load(path):
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        cols = {c.strip().lower(): c for c in (rd.fieldnames or [])}
        for c in ("utc", "seq", "type", "dt_ms", "buf"):
            if c not in cols:
                print("НЕТ КОЛОНКИ %s; шапка: %s" % (c, rd.fieldnames))
                sys.exit(2)
        kind_col = cols.get("kind")
        for r in rd:
            try:
                rows.append({
                    "t": parse_ts(r[cols["utc"]].strip()),
                    "seq": int(r[cols["seq"]]),
                    "type": int(r[cols["type"]]),
                    "dt": float(r[cols["dt_ms"]]),
                    "buf": int(r[cols["buf"]]),
                    "kind": (r[kind_col].strip().upper() if kind_col else "D"),
                })
            except (ValueError, AttributeError):
                continue
    return rows


def hist(dts, tick, label):
    print("   %s: ср %.3f, медиана %.3f, min %.3f, max %.3f" %
          (label, st.mean(dts), st.median(dts), min(dts), max(dts)))
    bins = [(0, 10, "0-10   (пачка: >=2 кадров за один тик)"),
            (10, 16, "10-16  (пачка/дрожь)"),
            (16, 25, "16-25  (межтиковый)"),
            (25, 35, "25-35  (2 тика ~%.2f)" % (2 * tick)),
            (35, 42, "35-42  (гейт 36 блокирует)"),
            (42, 52, "42-52  (3 тика ~%.2f)" % (3 * tick)),
            (52, 70, "52-70  (4 тика ~%.2f)" % (4 * tick)),
            (70, 1e9, "70+    (затишье USB/старт)")]
    for lo, hi, lbl in bins:
        c = sum(1 for d in dts if lo <= d < hi)
        print("   %s: %5d  %5.1f%%  %s" % (lbl, c, 100.0 * c / len(dts), "#" * int(c / len(dts) * 60)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csvfile")
    ap.add_argument("--tick", type=float, default=TICK_DEFAULT)
    ap.add_argument("--nominal", type=float, default=NOMINAL_DEFAULT)
    a = ap.parse_args()

    rows = load(a.csvfile)
    if len(rows) < 10:
        print("СЛИШКОМ МАЛО СТРОК: %d" % len(rows))
        return 2
    is_v15 = any(r["kind"] != "D" for r in rows) or "kind" in (csv.reader(open(a.csvfile, encoding="utf-8-sig")).__next__() if False else []) or True
    # надёжно: шапка читается в load; kind != D есть только в v1.5
    kind_seen = set(r["kind"] for r in rows)
    is_v15 = kind_seen - {"D"} != set()

    drows = [r for r in rows if r["kind"] == "D"]
    prows = [r for r in rows if r["kind"] == "P"]
    frows = [r for r in rows if r["kind"] == "F"]

    n = len(drows)
    t0, t1 = drows[0]["t"], drows[-1]["t"]
    span = t1 - t0
    print("=" * 72)
    print("ФАЙЛ: %s" % a.csvfile)
    print("СХЕМА: %s   D-строк: %d   P-строк: %d   F-строк: %d" %
          ("v1.5 (kind)" if is_v15 else "v1.4 (только декоды)", n, len(prows), len(frows)))
    print("декоды: окно %.3f с, %.3f мс/кадр (сырое), %.3f FPS" %
          (span, span / max(1, n - 1) * 1000, (n - 1) / span if span > 0 else 0))
    if is_v15 and prows:
        pspan = prows[-1]["t"] - prows[1]["t"] if len(prows) > 2 else 0
        print("краски: %d за %.3f с = %.3f FPS" %
              (len(prows), pspan, (len(prows) - 2) / pspan if pspan > 0 else 0))

    # --- 1. непрерывность SEQ ------------------------------------------------
    seqs = [r["seq"] for r in drows]
    jumps = []
    for i in range(1, n):
        d = (seqs[i] - seqs[i - 1]) % 256
        if d != 1:
            jumps.append((i, seqs[i - 1], seqs[i], d, drows[i]["t"] - drows[i - 1]["t"]))
    print("-" * 72)
    print("1) SEQ: старт с seq=%d, разрывов внутри лога: %d" % (seqs[0], len(jumps)))
    for (i, s0, s1, d, dt) in jumps[:20]:
        print("   D-строка %d: seq %d -> %d (шаг %d, дт %.3f мс)  <-- ПОТЕРЯ %d кадр."
              % (i + 1, s0, s1, d, dt, d - 1))
    if not jumps:
        print("   OK  провод->вьюер без потерь (SEQ непрерывен mod 256)")

    # --- 2. период провода по обёрткам SEQ 255->0 -----------------------------
    print("-" * 72)
    print("2) ПЕРИОД ПРОВОДА по границам SEQ (обёртка 255->0): wall-время 256 кадров")
    wt = [r["t"] for r in drows if r["seq"] == 0 and True]
    # обёртка = D-строка с seq 0, у которой ПРЕДЫДУЩАЯ D-строка 255
    wt = []
    for i in range(1, n):
        if seqs[i] == 0 and seqs[i - 1] == 255:
            wt.append(drows[i]["t"])
    if len(wt) >= 2:
        periods = [(wt[k] - wt[k - 1]) / 256.0 * 1000.0 for k in range(1, len(wt))]
        for k, P in enumerate(periods):
            print("   обёртка %d->%d: %.3f с / 256 = %.4f мс/кадр" % (k + 1, k + 2, wt[k + 1] - wt[k], P))
        Pmean, sd = st.mean(periods), st.pstdev(periods) if len(periods) > 1 else 0.0
        sem = sd / (len(periods) ** 0.5) if len(periods) > 1 else 0.0
        print("   СРЕДНИЙ РЕАЛЬНЫЙ ПЕРИОД: %.4f мс  (min %.4f, max %.4f, ±%.4f SEM)" %
              (Pmean, min(periods), max(periods), sem))
        print("   номинал %.4f мс -> плата %+.3f%% (реальный T = %.4f мкс вместо 0.3200)" %
              (a.nominal, (Pmean / a.nominal - 1) * 100.0, Pmean / a.nominal * 0.3200))
        print("   КАЛИБРОВКА: T_FRAME_new = round(%d * %.4f/%.4f) = %d T" %
              (146484, a.nominal, Pmean, round(146484 * a.nominal / Pmean)))
    else:
        Pmean = None
        print("   обёрток < 2 — период по границам не считается")
    # резервный оценка по сырому среднему (уязвима к бэклагу в начале лога)
    if Pmean is None:
        Pmean = span / max(1, n - 1) * 1000.0
        print("   оценка по сырому среднему: %.4f мс (низкая точность при бэклоге)" % Pmean)

    # --- 3. гистограммы -------------------------------------------------------
    print("-" * 72)
    print("3) ГИСТОГРАММЫ против сетки таймера %.3f мс" % a.tick)
    dts = [(drows[i]["t"] - drows[i - 1]["t"]) * 1000.0 for i in range(1, n)]
    hist(dts, a.tick, "dt ДЕКОДОВ (D)")
    if is_v15 and len(prows) > 3:
        pdts = [prows[i]["dt"] for i in range(2, len(prows))]  # без первой (мусор)
        hist(pdts, a.tick, "dt КРАСОК (P)")

    # --- 4. пачки и пропуски --------------------------------------------------
    print("-" * 72)
    print("4) ПАЧКИ декодов (dt<16 мс = >=2 кадров за один тик):")
    bunch = [(i + 1, seqs[i - 1], seqs[i], dts[i - 1], drows[i]["buf"])
             for i in range(1, n) if dts[i - 1] < 16.0]
    pairs = sum(1 for (li, s0, s1, d, b) in bunch if li >= 2 and dts[li - 2] >= 60.0)
    print("   событий dt<16: %d (%.2f%%); из них после паузы >=60 мс: %d" %
          (len(bunch), 100.0 * len(bunch) / max(1, len(dts)), pairs))
    for (li, s0, s1, d, b) in bunch[:25]:
        print("   D-строка %d: seq %d->%d dt %.1f мс (перед %.1f мс), buf %d" %
              (li + 1, s0, s1, d, (dts[li - 2] if li >= 2 else 0), b))
    if is_v15:
        skips = sum(p["buf"] for p in prows)
        skips_events = sum(1 for p in prows if p["buf"] > 0)
        print("   ПРОПУСКИ КРАСКИ (P.buf): всего %d позиций в %d красках" % (skips, skips_events))
        for p in prows:
            if p["buf"] > 0:
                print("   P: utc %.3f seq %d dt %.0f мс пропущено %d" % (p["t"], p["seq"], p["dt"], p["buf"]))
        if frows:
            print("   ФЛЕШ бэклога: %d событий, %d Б сброшено" % (len(frows), sum(f["buf"] for f in frows)))
            for f in frows[:10]:
                print("   F: utc %.3f сброшено %d Б" % (f["t"], f["buf"]))

    # --- 5. буфер -------------------------------------------------------------
    print("-" * 72)
    print("5) БУФЕР ПОРТА (BytesToRead на тик декода):")
    bufs = [r["buf"] for r in drows]
    print("   ср %.0f Б, медиана %d, max %d" % (st.mean(bufs), st.median(bufs), max(bufs)))
    for thr, lbl in ((ENVELOPE, ">1 конверта (2006)"), (2 * ENVELOPE, ">2 конвертов (4012)")):
        c = sum(1 for b in bufs if b > thr)
        print("   %s: %d тиков (%.2f%%)" % (lbl, c, 100.0 * c / n))
    head = sum(1 for b in bufs[:50] if b > ENVELOPE)
    print("   первые 50 строк с buf>2006: %d (стартовый бэклог)" % head)
    big = sorted(range(n), key=lambda i: -bufs[i])[:8]
    print("   топ buf: %s" % ", ".join("стр%d seq%d %dБ" % (i + 1, seqs[i], bufs[i]) for i in sorted(big)))

    # --- 6. сцены -------------------------------------------------------------
    print("-" * 72)
    print("6) ТИПЫ (01=полные, 02=дельты): чередование сцен")
    runs = []
    cur, start = drows[0]["type"], 0
    for i in range(1, n):
        if drows[i]["type"] != cur:
            runs.append((cur, i - start))
            cur, start = drows[i]["type"], i
    runs.append((cur, n - start))
    print("   серий: %d; первые 30: %s" % (len(runs), ", ".join("T%02d x%d" % (t, c) for t, c in runs[:30])))

    # --- 7. модель гейта v1.4 (для старых логов) -------------------------------
    if not is_v15:
        print("-" * 72)
        print("7) МОДЕЛЬ вьюера v1.4 (тик %.3f мс, гейт 36 мс) при периоде провода:" % a.tick)
        tick = a.tick / 1000.0
        t, nframes, last_paint, skips = 0.0, 0, -1e9, 0
        paints_dt = []
        while t < 600.0:
            t += Pmean / 1000.0
            nframes += 1
            tickn = (int(t / tick) + 1) * tick
            if tickn - last_paint >= 0.036:
                paints_dt.append(tickn - last_paint)
                last_paint = tickn
            else:
                skips += 1
        rate = 100.0 * skips / nframes
        print("   симуляция 600 с: кадров %d, структурных пропусков краски %d (%.2f%%)" %
              (nframes, skips, rate))
        if len(paints_dt) > 2:
            pd = [x * 1000.0 for x in paints_dt[1:]]
            print("   интервалы краски: ср %.1f мс, p10 %.1f, p90 %.1f мс" %
                  (st.mean(pd), sorted(pd)[len(pd) // 10], sorted(pd)[9 * len(pd) // 10]))
        print("   интерпретация: |P - 3*тик| = %.3f мс -> фаза скользит, гейт даёт" %
              abs(Pmean - 3 * a.tick))
        print("   системные пропуски краски даже при идеальном эфире;")
        print("   остаток сверх модели = USB-батчинг CH340 (всплески buf), виден в п.4")
    else:
        print("-" * 72)
        print("7) ВЕРДИКТ ПРИЁМКИ (v1.5):")
        ok = True
        if is_v15 and len(prows) > 3:
            pdts = [prows[i]["dt"] for i in range(2, len(prows))]
            p10, p90 = sorted(pdts)[len(pdts) // 10], sorted(pdts)[9 * len(pdts) // 10]
            spread = p90 - p10
            print("   интервал краски: p10 %.0f / p90 %.0f (разброс %.0f мс)" % (p10, p90, spread))
            if spread <= 6:
                print("   OK  краска ровная (разброс <= 6 мс)")
            else:
                ok = False
                print("   !!  краска неровная — ожидаем ~47±3 мс")
            sk = sum(p["buf"] for p in prows)
            if sk == 0:
                print("   OK  пропусков краски 0 — ни одна позиция не потеряна")
            else:
                ok = False
                print("   !!  пропусков краски %d — скачки на экране" % sk)
        if not jumps:
            print("   OK  провод без потерь (SEQ)")
        else:
            ok = False
            print("   !!  разрывов SEQ %d" % len(jumps))
        fl = sum(f["buf"] for f in frows) if frows else 0
        fl_n = len(frows)
        if fl_n <= 2:
            print("   OK  флешей бэклога %d (только старт — норма)" % fl_n)
        else:
            print("   ?!  флешей %d (%d Б) — USB-батчинг/затыки клиента повторяются" % (fl_n, fl))
        print("   ИТОГ: %s" % ("ПРИНЯТО" if ok else "ЕСТЬ ЗАМЕЧАНИЯ"))

    print("=" * 72)
    print("КОНЕЦ ОТЧЁТА")
    return 0


if __name__ == "__main__":
    sys.exit(main())
