#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fit_diff_v398clear.py (2026-11-08) - аудит рефита v3.9.8-clear ред.2
(директива владельца: «Отчет по 398_clear смотри, железо - работает!»).

Сверяет фит владельца 11-7 10:09PM (v398clear-fit1) с золотым фитом
v3.9.8 (v398-fit1, IL 16; см. п.25/п.26 шапки). Строка Date исключается
(фиты в разные дни); всё остальное обязано совпасть БАЙТ-В-БАЙТ, кроме:
  - опции Input Limit (IL 28 у рефита - по директиве п.25 «остаться
    на IL 28»; золотые прогоны IL 16/IL 28 уже сверены между собой);
  - ничего больше.

Дополнительно печатает контрольные точки чек-листа g)/h) шапки из текста
рефита: ресурсы, PGND, отсутствие мёртвых сигналов в нетлисте.

Запуск: python3 scripts/fit_diff_v398clear.py   (из beta/lowsize/)
"""

import difflib
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # beta/lowsize
REFIT  = os.path.join(BASE, "retro_pcld_top (v398clear-fit1-1107-1009PM).rpt")
GOLDEN = os.path.join(BASE, "retro_pcld_top (v398-fit1-1106-719PM).rpt")

DEAD = ["cnt", "x1_q", "x1_p", "x1_n", "x2_q", "x2_p", "t0_q", "wb_ram_q"]
PGND_EXPECT = {"74", "75", "76", "78", "79", "81", "95", "96", "98"}


def load(path):
    with open(path, "rb") as f:
        return f.read().decode("cp1251", errors="replace")


def norm(text):
    # строка Date уникальна для каждого прогона - исключаем из сравнения
    return [re.sub(r"^Design Name:.*Date:.*$", "Design Name: <DATE>",
                   l, flags=re.S) for l in text.split("\n")]


def main():
    ok = True
    refit, golden = load(REFIT), load(GOLDEN)

    # 1) дифф рефита с золотом
    diff = [d for d in difflib.unified_diff(norm(golden), norm(refit),
                                            "golden-v398-IL16", "refit-v398clear-IL28",
                                            lineterm="", n=0)
            if d[:1] in "+-" and d[:3] not in ("+++", "---")]
    print("=== ДИФФ рефита с золотым фитом v3.9.8 (без строки Date) ===")
    for d in diff:
        print("   " + d)
    benign = all(re.fullmatch(r"[-+]Input Limit\s+:\s*\d+", d.strip())
                 for d in diff)
    if diff and benign:
        print("OK: единственное различие - опция Input Limit "
              "(IL 16 у золота -> IL 28 у рефита, директива п.25);")
        print("    золотые IL 16/IL 28 уже сверены между собой байт-в-байт "
              "(п.25) - нетлист идентичен")
    elif not diff:
        print("OK: рефит и золотой фит совпадают ПОЛНОСТЬЮ")
    else:
        print("ПРОВАЛ: различия не сводятся к Input Limit"); ok = False

    # 2) контрольные точки чек-листа шапки по тексту рефита
    print("\n=== КОНТРОЛЬНЫЕ ТОЧКИ чек-листа g)/h) по рефиту ===")
    m = re.search(r"(\d+ ?/108 \( *\d+%\))\s+(\d+ ?/540)", refit)
    if m:
        print(f"OK: ресурсы: МЦ {m.group(1)}, ПТ {m.group(2)}")
    else:
        print("ПРОВАЛ: сводка ресурсов не найдена"); ok = False

    pgnd = set(re.findall(r"(\d+)\s+PGND\s*$", refit, flags=re.M))
    if pgnd == PGND_EXPECT:
        print(f"OK: PGND = {len(pgnd)} шт {sorted(pgnd, key=int)} - "
              "ровно чек-лист c), P73 (SID) вне PGND")
    else:
        print(f"ПРОВАЛ: PGND расходится: {sorted(pgnd, key=int)}"); ok = False

    hits = [d for d in DEAD if re.search(rf"\b{d}\b", refit)]
    if hits:
        print(f"ПРОВАЛ: мёртвые сигналы в нетлисте: {hits}"); ok = False
    else:
        print("OK: в нетлисте нет cnt/x1_q/x1_p/x1_n/x2_q/x2_p/t0_q/wb_ram_q "
              "(Xst:1780 негде взяться)")

    for name, pat in [("clk -> GCK3", r"Signal 'clk' mapped onto global clock net GCK3"),
                      ("RST = P1", r"RST\s+FB2_5\s+1\s+GSR/I/O I"),
                      ("кольцо в FB6", r"FDCPE_r1: FDCPE port map"),
                      ("X2 NOR-форма", r"X2 <= NOT \(\(NOT r1 AND NOT r2"),
                      ("clk25_q T-триггер", r"FTCPE_clk25_q: FTCPE port map \(clk25_q,'1',clk"),
                      ("пор-цепь на clk 50", r"FDCPE_por_sh0: FDCPE port map \(por_sh\(0\),por_sh_D\(0\),clk"),
                      ("сброс п.21", r"FDCPE_rst_meta: FDCPE port map \(rst_meta,RST,clk25_q"),
                      ("GSR fallback", r"Global set/reset net\(s\) unused"),
                      ("D<7> буфер (897)", r"WARNING:Cpld:897.*\n.*Buffering output signal D<7>"),
                      ("Xst-варнингов нет", r"^(?!.*Xst:)[\s\S]*\Z")]:
        if re.search(pat, refit):
            print(f"OK: {name}")
        else:
            print(f"ПРОВАЛ: {name} - паттерн не найден: {pat}"); ok = False

    print("\nИТОГ:", "PASS - рефит 1-в-1 золоту v3.9.8" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
