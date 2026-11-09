#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_fit_v23.py -- аудит фита v2.2 по чек-листу (п.32 README, ред. v2.2).

Проверяет .rpt фита v2.3 (бод 25/25 = РОВНО 1 000 000, сетка CH340G):
  F0  дата/статус: Successful, 0 ERROR;
  F1  ресурсы: МЦ в окне 103-105 из 108 (ожидание 104: 103 v2.2 + 1 бит baud_cnt), ноги 72/81;
  F2  мусор чужих опций: $OpTx$BIN_* = 0, INFO:Cpld:994 = 0,
      WARNING:Xst = 0, WARNING:Cpld:897 <= 3 (класс D<7>, бенигный);
  F3  глобальные: clk -> GCK3; GSR-сеть НЕ используется (v2.2: RST -
      обычный вход, por-цепь 8 x 160 нс = 1280 нс по X1, por_sh/rst_qcnt);
  F4  узел v2.2: кольцо s0..s3 (X1 = s0 1 ПТ; s1_rnm0/s2/s3 по 1 ПТ;
      X2 1 ПТ = NOT(NOR3) = s1|s2|s3); рестарт из dead встроен
      (X1_D = ~X1 & ~s1 & ~s2 - легальная минимизация: на достижимых
      состояниях совпадает с s3 | ~s0 & ~s1 & ~s2 & ~s3);
  F5  старое НЕ присутствует: r0..r6 (кольцо N=7), clk25_q, adv_q,
      tx_run, sod_q/tx_pass/tx_q/cpu_rst (транзиты v3.9.3);
  F6  ядро v2.3: baud_cnt<0..4> - ПЯТЬ бит (+1 МЦ к v2.2), bit_cnt<0..3>
      (код 1..10), ld_tx_q ЕСТЬ, shreg<1..8> + TX (9 бит);
  F7  PGND: закопанные МЦ ровно на {74,75,76,78,79,81,95,96,98};
  F8  константы: READY (P87) и CS1 (P99) = 0 ПТ (ноги '1');
  F9  стробы-декоды $OpTx$FX_DC: 61/67/70/71/73 (5 шт, здоровый коллапс).

Использование: python3 check_fit_v23.py <имя.rpt>
"""
import re
import sys

DEFAULT_RPT = None  # python3 check_fit_v23.py <файл.rpt>
fail = 0


def chk(name, cond, detail=""):
    global fail
    print("  %s %s %s" % ("ПАСС" if cond else "ПРОВ", name, detail))
    if not cond:
        fail += 1


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RPT
    if not path:
        raise SystemExit("Использование: python3 check_fit_v23.py <файл.rpt>")
    txt = open(path, encoding="cp1251", errors="replace").read()

    print("фит:", path)

    # F0
    chk("F0 Fitting Status: Successful", "Fitting Status: Successful" in txt)
    errs = [l for l in txt.splitlines() if "ERROR" in l]
    chk("F0 строк ERROR нет (%d)" % len(errs), not errs, "; ".join(errs[:2]))
    m = re.search(r"Date:\s*(.+)$", txt, re.M)
    chk("F0 дата прогона", bool(m), m.group(1).strip() if m else "-")

    # F1
    m = re.search(r"(\d+)/108 \(\s*\d+%\)\s+(\d+) /540", txt)
    mc, pt = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    chk("F1 МЦ %d/108 в окне 103-105 (<=108)" % mc, 103 <= mc <= 105)
    chk("F1 ПТ %d/540" % pt, 200 <= pt <= 420)
    m = re.search(r"(\d+) /81\s+\(\s*\d+%\)", txt)
    chk("F1 ноги %s/81" % (m.group(1) if m else "?"),
        bool(m) and m.group(1).strip() == "72")

    # F2
    chk("F2 $OpTx$BIN_* = 0 (мусора коллапсинга нет)",
        txt.count("$OpTx$BIN") == 0)
    chk("F2 INFO:Cpld:994 нет", "INFO:Cpld - 994" not in txt
        and "INFO:Cpld:994" not in txt)
    chk("F2 WARNING:Xst нет", "WARNING:Xst" not in txt)
    n897 = txt.count("WARNING:Cpld:897")
    chk("F2 WARNING:Cpld:897 <= 3 (%d, класс D<7>/A<1> буферизация)" % n897,
        n897 <= 3)

    # F3
    chk("F3 clk -> GCK3", "mapped onto global clock net GCK3" in txt)
    chk("F3 GSR-сеть не используется (v2.2: RST - обычный вход)",
        "Global set/reset net(s) unused" in txt)
    chk("F3 por_sh<0..7> в отчёте (por 8 x 160 = 1280 нс)",
        all("por_sh<%d>" % k in txt for k in range(8)))
    chk("F3 rst_qcnt/rst_sync/rst_meta/rst_press (синхронизатор RST)",
        all(s in txt for s in ("rst_qcnt<0>", "rst_sync", "rst_meta",
                               "rst_press")))

    # F4 - узел
    chk("F4 X1 (FB6_3, P68, 1 ПТ)",
        bool(re.search(r"^X1\s+1\s+3\s+FB6_3\s+68", txt, re.M)))
    chk("F4 X2 (FB6_5, P69, 1 ПТ)",
        bool(re.search(r"^X2\s+1\s+3\s+FB6_5\s+69", txt, re.M)))
    for sig in ("s1_rnm0", "s2", "s3"):
        chk("F4 %s: 1 ПТ" % sig,
            bool(re.search(r"^%s\s+1\s+\d+\s+FB6_" % sig, txt, re.M)))
    chk("F4 X1_D = ~X1 & ~s1 & ~s2 (advance s3 + рестарт dead, минимиз.)",
        bool(re.search(r"X1_D <= \(NOT X1 AND NOT s1_rnm0 AND NOT s2\)", txt)))
    chk("F4 X2 = NOT(NOT s1 AND NOT s2 AND NOT s3) = s1|s2|s3",
        bool(re.search(r"X2 <= NOT \(\(NOT s1_rnm0 AND NOT s2 AND NOT s3\)\)",
                       txt)))
    chk("F4 s2_D = ~X1 & s1 & ~s2 & ~s3",
        bool(re.search(r"s2_D <= \(NOT X1 AND s1_rnm0 AND NOT s2 AND NOT s3\)",
                       txt)))
    chk("F4 s3_D = ~X1 & ~s1 & s2 & ~s3",
        bool(re.search(r"s3_D <= \(NOT X1 AND NOT s1_rnm0 AND s2 AND NOT s3\)",
                       txt)))

    # F5 - старое отсутствует
    for dead in (r"\br0\b", r"\br1\b", r"\br6\b", "clk25_q", "adv_q",
                 "tx_run", "sod_q", "tx_pass", r"\btx_q\b", "cpu_rst"):
        chk("F5 нет %s" % dead, re.search(dead, txt) is None)

    # F6 - ядро v2.1
    for sig in ("baud_cnt<0>", "baud_cnt<1>", "baud_cnt<2>", "baud_cnt<3>", "baud_cnt<4>",
                "bit_cnt<0>", "bit_cnt<1>", "bit_cnt<2>", "bit_cnt<3>",
                "ld_tx_q", "shreg<1>", "shreg<8>", "wr_seen", "rd_seen"):
        chk("F6 %s в отчёте" % sig, sig in txt)
    chk("F6 TX (FB3_11, P39, 4 ПТ, SET=idle '1')",
        bool(re.search(r"^TX\s+4\s+\d+\s+FB3_11\s+39", txt, re.M)))
    # v2.3: D(0) = ~ld_tx_q & ~baud_tick & ~bc0 (wrap ЯВНЫЙ) - фиттер может
    # свернуть jam и wrap в один терм; проверяем мягко: ld_tx_q в D(0) есть
    chk("F6 jam/wrap в D(0) baud_cnt (ld_tx_q в уравнении)",
        bool(re.search(r"baud_cnt_D\(0\) <= \(NOT ld_tx_q ", txt)))
    chk("F6 строб 04h в ld_tx_q_D (addr=100, IOM, !WRn)",
        bool(re.search(r"ld_tx_q_D <= \(NOT ld_tx_q AND state_FSM_FFd2 AND "
                       r"NOT addr_latch\(0\) AND\s+NOT addr_latch\(1\) AND "
                       r"addr_latch\(2\)", txt, re.S)))
    chk("F6 TXRDY = ~|bit_cnt в чтении 05h (A_I(1), port 101b)",
        bool(re.search(r"NOT bit_cnt\(0\) AND NOT bit_cnt\(1\) AND NOT "
                       r"bit_cnt\(2\) AND NOT bit_cnt\(3\) AND IOM AND", txt)))

    # F7 - PGND: закопанные МЦ на известных ногах
    pgnd = set()
    for m in re.finditer(r"^\S.*?\s(FB\d_\d+)\s+(\d+)\s+I/O\s+\(b\)",
                         txt.split("Function Block Details")[0], re.M):
        pgnd.add(int(m.group(2)))
    # запасной парсер: строки вида "... FBx_yy NN I/O (b)" в FB-таблицах
    if len(pgnd) < 9:
        for m in re.finditer(r"FB\d_\d+\s+(\d+)\s+I/O\s+\(b\)", txt):
            pgnd.add(int(m.group(1)))
    chk("F7 закопанные МЦ на ногах {74,75,76,78,79,81,95,96,98}",
        pgnd == {74, 75, 76, 78, 79, 81, 95, 96, 98}, str(sorted(pgnd)))

    # F8 - константы '1'
    chk("F8 READY P87 = 0 ПТ",
        bool(re.search(r"^READY\s+0\s+0\s+FB4_5\s+87", txt, re.M)))
    chk("F8 CS1 P99 = 0 ПТ",
        bool(re.search(r"^CS1\s+0\s+0\s+FB2_3\s+99", txt, re.M)))
    chk("F8 CS1 <= '1' в уравнениях", "CS1 <= '1'" in txt)

    # F9 - стробы
    fx = sorted(set(re.findall(r"\$OpTx\$FX_DC\$(\d+)", txt)))
    chk("F9 $OpTx$FX_DC %s (5 декодов записи/чтения портов)"
        % ",".join(fx), fx == ["61", "67", "70", "71", "73"])

    print()
    if fail:
        print("ИТОГ: ПРОВАЛОВ %d" % fail)
        sys.exit(1)
    print("ИТОГ: ЧЕК-ЛИСТ ФИТА v2.2 ЗАКРЫТ")


if __name__ == "__main__":
    main()
