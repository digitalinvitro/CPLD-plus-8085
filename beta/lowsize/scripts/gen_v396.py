#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_v396.py (lowsize, 2026-11-06): top_suart_por6_v395.v -> top_suart_por6_v396.v.

Мера п.21: ХАРДРЕНИНГ ЦЕПИ СБРОСА (жалоба владельца 11-6 на v3.9.5,
у ОБОИХ фитов Exhaustive ON/OFF: «только выкл-вкл питания возвращает
работоспособность по сбросу; просто сброс не может восстановить»).
Гипотеза п.1 разбора (подтяжка цепи RST) владельцем СНЯТА - резистор
стоит давно. Мера НЕЗАВИСИМА от цепи RST платы:

  RST входит в кристалл ТОЛЬКО через регистры:
  (a) 2FF-синхронизатор rst_meta/rst_sync (вне сброса, INIT=0);
  (b) квалификатор rst_press/rst_qcnt: переворот на 8-м такте подряд
      устойчивого rst_sync != rst_press (двусторонний);
  (c) cpu_rst = rst_press | por_run - только регистровые источники;
  (d) RESET_IN - РЕГИСТР reset_q (INIT=0 - CPU держится с t=0);
  (e) гейт S_T2: !por_run -> !por_run AND !rst_press.

POR бит-в-бит v3.9.4. Дельта: блок cpu_rst, assign RESET_IN, гейт
S_T2, 4 комментария портов/шапки, п.21 + чек-лист 3d.

CP1251-эталон + UTF8-двойник, round-trip проверка, контроль дельты.
Запуск: python3 scripts/gen_v396.py (из beta/lowsize или откуда угодно).
"""
import difflib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, ".."))
F395 = os.path.join(SRC, "top_suart_por6_v395.v")
F396 = os.path.join(SRC, "top_suart_por6_v396.v")
F396U = os.path.join(SRC, "top_suart_por6_v396_utf8.v")
F395U = os.path.join(SRC, "top_suart_por6_v395_utf8.v")


def rd_cp(p):
    return open(p, "rb").read().decode("cp1251")


def wr_cp(p, t):
    raw = t.encode("cp1251")
    assert raw.decode("cp1251") == t, "round-trip CP1251 FAIL"
    open(p, "wb").write(raw)


# --- правки (UTF8-текст; применяется к CP1251-содержимому) -------------

E_TITLE_OLD = (
    "// top_suart.v v3.9.5 - retro_pcld_top + SOFT-UART ТРАНЗИТЫ + CPU 3,57 МГц "
    "(X1/X2 = 7,14 МГц, счётчик mod-7, п.17; CS_n от FSM, п.16; СБРОС ЛОГИКИ "
    "-> СЕТЬ GSR, п.18, В Т.Ч. ВЕСЬ POR - источник GSR = cpu_rst = RST|por_run, "
    "п.20; POR 8->4 со стробом x1_n - М1 txclient, п.19)"
)
E_TITLE_NEW = (
    "// top_suart.v v3.9.6 - retro_pcld_top + SOFT-UART ТРАНЗИТЫ + CPU 3,57 МГц "
    "(X1/X2 = 7,14 МГц, счётчик mod-7, п.17; CS_n от FSM, п.16; СБРОС ЛОГИКИ "
    "-> СЕТЬ GSR, п.18, В Т.Ч. ВЕСЬ POR - источник GSR = cpu_rst, п.20; "
    "ХАРДРЕНИНГ СБРОСА: RST только через регистры (синхронизатор + "
    "квалификатор), RESET_IN - регистр reset_q, п.21; POR 8->4 со стробом "
    "x1_n - М1 txclient, п.19)"
)

E_TODO_OLD = "// Что делать владельцу (TODO 78, ред. v3.9.5):"
E_TODO_NEW = "// Что делать владельцу (TODO 78, ред. v3.9.6):"

P21 = """//  21) v3.9.6 (линия lowsize, 2026-11-06; ХАРДРЕНИНГ ЦЕПИ СБРОСА -
//      жалоба владельца 11-6 на v3.9.5 (у ОБОИХ фитов, Exhaustive ON
//      и OFF): «только выкл-вкл питания возвращает работоспособность
//      по сбросу; просто сброс не может восстановить работоспособность,
//      пока она не восстановится по питанию»; гипотеза п.1 разбора
//      (подтяжка цепи RST) владельцем СНЯТА - резистор стоит давно,
//      мера сделана НЕЗАВИСИМОЙ от цепи RST платы). ПРИЧИНА: в фите
//      v3.9.5 GSR НЕ свёлся (fallback) - сырой пин RST доходил
//      НАПРЯМУЮ до гейта RESET_IN<=NOT por_run AND NOT RST (нога CPU)
//      и до 40 PTC-сбросов CLR/PRE=NOT RESET_IN: любой мид-рейл/
//      дребезг/помеха на SW20 размазывает моменты фактического снятия
//      сброса у CPU и у триггеров на время фронта (симуляция
//      sim_v395_rst_float.py: спад 10 мкс - BOOT 7-10/20, ложные /WE
//      и контеншн A/AD у ~50% сидов; у механической кнопки на
//      отпускании - миллисекунды дребезга). МЕРА - RST входит в
//      кристалл ТОЛЬКО через регистры:
//      (a) 2FF-синхронизатор rst_meta/rst_sync (вне сброса, INIT=0) -
//          сырой пин больше не касается ни PTC-сбросов, ни RESET_IN;
//      (b) квалификатор rst_press/rst_qcnt: переворот на 8-м такте
//          ПОДРЯД устойчивого rst_sync != rst_press - дребезг/глитч
//          короче 280 нс не виден вовсе; длиннее - ПОЛНОЦЕННЫЙ
//          повторный сброс: каждый взвод заново чистит все 40
//          триггеров, ПОСЛЕДНЕЕ снятие всегда из held-чистого
//          состояния регистровым фронтом;
//      (c) cpu_rst = rst_press | por_run - ТОЛЬКО регистровые
//          источники (комбинаций от пинов в цепи сброса больше НЕТ);
//      (d) RESET_IN - РЕГИСТР reset_q (INIT=0: CPU в сбросе с t=0 до
//          всякого клока - как от INIT=SET por_run в v3.9.5; вне
//          сброса): снятие сброса CPU ВСЕГДА чистым фронтом, моменты
//          отпускания CPU и логики совпадают до скоха одной сети;
//      (e) гейт S_T2: !por_run -> !por_run AND !rst_press (рубеж
//          п.18/20 распространён на окна кнопочного сброса);
//      (f) начатый импульс /WE (80 нс) НЕ обрывается: квалификатор
//          (400 нс) длиннее импульса - запись доводится до конца
//          (полный t_WP ОЗУ), сброс гасит драйвы сразу после.
//      СВОЙСТВА: POR бит-в-бит v3.9.4 (por_sh/por_run не тронуты),
//      низ RESET_IN по питанию 1020 -> до 1160 нс (норма 840, запас
//      x1,35); латентность кнопки 11 тиков счёта (2FF + 8 такт
//      квалификатора + reset_q) = 400..440 нс от пина на взвод и на
//      снятие (кнопка живёт в миллисекундах); tx_pass/
//      tx_q - прежний async SR, источник - регистровый cpu_rst.
//      НОВОЕ СВОЙСТВО: глитч на RST короче ~280 нс (8 тактов) сброс
//      НЕ вызывает (в v3.9.5 вызывал любой). ЦЕНА: +7 рег (57),
//      прогноз 85-87 МЦ / 220-230 ПТ / 165-172 вх.ФБ (у v3.9.5 было
//      79/217/163/50; свободно 29 МЦ). СИМ: tb_v396_rst.v (Icarus):
//      POR/чистая кнопка/дребезг 8 экскурсий/глитчи 100+250 нс/сброс
//      посреди /WE-импульса/регистровость RESET_IN, норм-путь
//      эквивалентен v3.9.5.
//
"""

C3D = """//  3d) v3.9.6 (хардренинг сброса, п.21): в нетлисте rst_meta/rst_sync/
//     rst_press/rst_qcnt<2:0>/reset_q - все ВНЕ сброса/GSR; reset_q -
//     Init=RESET (FDCPE(clk,'0','0') БЕЗ PRE - CPU держится с t=0;
//     константа '0' в уравнении = признак Init, сверять как у por-цепи
//     - прецедент 2565246: cpldfit Init в печати не виден); литерал
//     RST в .rpt - ТОЛЬКО во входах ФБ rst_meta (1 ФБ), в D/PT-
//     функциях БОЛЬШЕ НИГДЕ (v3.9.5: RST стоял в гейте RESET_IN);
//     уравнения-ожидания: reset_q.D = NOT por_run AND NOT rst_press;
//     rst_press.D = rst_sync при rst_qcnt==7 (иначе hold, 4-6 ПТ);
//     rst_qcnt<2:0> - счётчик 0..7 с обнулением при
//     rst_sync==rst_press; гейт S_T2 - с !rst_press; D-функции логики
//     по-прежнему БЕЗ литералов сброса; GSR (если сведётся - от узла
//     cpu_rst) ОПЦИОНАЛЕН: PT-сбросы анатомии v3.9.5 корректны;
//     прогноз: МЦ 85-87, ПТ 220-230, вх.ФБ 165-172, рег 57.
"""

E_POR_OLD = """  reg [3:0] por_sh = 4'hF;       // v3.9.4 (М1): сдвиг вправо: F -> 7 -> 3 -> 1 -> 0
  reg  por_run = 1'b1;           // FF-копия для cpu_rst (v3.2; INIT=SET)
  wire cpu_rst = RST | por_run;  // CPU в сбросе: SW20 нажата или POR
                                 // v3.9.3: cpu_rst остался ТОЛЬКО для
                                 // RESET_IN и tx_pass/tx_q (PT-SR);
                                 // логика сбрасывается через GSR (п.18)
  always @(posedge clk) begin
    por_run <= por_sh[0];        // снятие, когда '0' дойдёт до bit0 (8-й тик)
    if (por_ce) por_sh <= {1'b0, por_sh[3:1]};
  end
"""

E_POR_NEW = """  reg [3:0] por_sh = 4'hF;       // v3.9.4 (М1): сдвиг вправо: F -> 7 -> 3 -> 1 -> 0
  reg  por_run = 1'b1;           // FF-копия для cpu_rst (v3.2; INIT=SET)
  always @(posedge clk) begin
    por_run <= por_sh[0];        // снятие, когда '0' дойдёт до bit0 (4-й тик, М1)
    if (por_ce) por_sh <= {1'b0, por_sh[3:1]};
  end

  //=============================================================
  // v3.9.6 (п.21): ХАРДРЕНИНГ ЦЕПИ СБРОСА. Сырой пин RST входит в
  // кристалл ТОЛЬКО через 2FF-синхронизатор + квалификатор; решения
  // о сбросе принимают ТОЛЬКО регистры: мид-рейл/дребезг/помеха на
  // SW20 физически не доходят ни до 40 сбросовых входов триггеров,
  // ни до ноги RESET_IN (в v3.9.5 RST шёл НАПРЯМУЮ в гейт RESET_IN
  // и в PTC-сбросы NOT RESET_IN - fallback фита 11-5).
  //   rst_meta/rst_sync - синхронизатор (вне сброса, INIT=0);
  //   rst_qcnt/rst_press - квалификатор: переворот rst_press на 8-м
  //     такте ПОДРЯД устойчивого rst_sync != rst_press (двусторонний:
  //     и взвод, и снятие квалифицированы); дребезг короче 280 нс не
  //     виден вовсе, длиннее - полноценный повторный сброс (каждый
  //     взвод заново чистит все 40 триггеров - ПОСЛЕДНЕЕ снятие
  //     всегда из held-чистого состояния, регистровым фронтом);
  //   cpu_rst = rst_press | por_run - ТОЛЬКО регистровые источники;
  //   reset_q - РЕГИСТР выхода RESET_IN (INIT=0: CPU в сбросе с t=0
  //     до всякого клока; снятие - чистым фронтом, как по питанию).
  // Латентность кнопки: 11 тиков счёта (2FF + 8 такт квалификатора +
  // reset_q) = 400..440 нс от пина на взвод и снятие (кнопка живёт в
  // миллисекундах). POR НЕ ТРОНУТ: por_sh/
  // por_run бит-в-бит v3.9.4, низ RESET_IN по питанию до 1160 нс
  // (норма 840 нс, запас x1,35).
  //=============================================================
  reg  rst_meta  = 1'b0;         // ловец метастабильности (вне сброса, INIT=0)
  reg  rst_sync  = 1'b0;         // синхронизованный RST (вне сброса, INIT=0)
  reg  rst_press = 1'b0;         // квалифицированный сброс кнопки (INIT=0)
  reg [2:0] rst_qcnt = 3'b000;   // счётчик квалификации 0..7 (INIT=0)
  wire cpu_rst = rst_press | por_run; // v3.9.6: сброс ТОЛЬКО от регистров
  reg  reset_q = 1'b0;           // РЕГИСТР RESET_IN (INIT=0 - CPU держится с t=0)
  always @(posedge clk) begin
    rst_meta <= RST;
    rst_sync <= rst_meta;
  end
  always @(posedge clk) begin
    if (rst_sync != rst_press) begin
      if (&rst_qcnt) begin
        rst_press <= rst_sync;   // 8-й такт подряд - переворот состояния
        rst_qcnt  <= 3'b000;
      end else
        rst_qcnt  <= rst_qcnt + 3'b001;
    end else
      rst_qcnt  <= 3'b000;       // линия вернулась к состоянию - счёт с нуля
  end
  always @(posedge clk)
    reset_q <= ~cpu_rst;         // снятие сброса CPU - всегда чистым фронтом
"""

E_FSM_OLD = (
    "  always @(posedge clk or posedge cpu_rst) begin // v3.9.5: сброс логики "
    "по cpu_rst = RST|por_run -> сеть GSR (п.20; структура п.18, расширен "
    "ИСТОЧНИК - закрывает дефект старта)"
)
E_FSM_NEW = (
    "  always @(posedge clk or posedge cpu_rst) begin // v3.9.6: сброс логики "
    "по cpu_rst = rst_press|por_run (регистры, п.21; асинхронная структура "
    "GSR п.18/20 сохранена)"
)

E_GATE_OLD = "              state <= (!IOM && A15 && !por_run) ? S_WB1 : S_IDLE;"
E_GATE_NEW = (
    "              state <= (!IOM && A15 && !por_run && !rst_press) ? S_WB1 : "
    "S_IDLE; // v3.9.6: гейт и на кнопку (п.21)"
)

E_RSTI_OLD = (
    "  assign RESET_IN = ~(RST | por_run); // активный 0 по даташиту: 0 = "
    "сброс CPU (SW20 нажата или POR)"
)
E_RSTI_NEW = (
    "  assign RESET_IN = reset_q;          // v3.9.6 (п.21): РЕГИСТР; активный "
    "0 по даташиту: 0 = сброс CPU (кнопка после квалификатора или POR); "
    "INIT=0 - CPU держится с t=0; снятие - чистым регистровым фронтом"
)

E_PRST_OLD = (
    "    input  wire       RST,          // SW20, U1.1 (P1, GSR): покой = 0, "
    "нажатие = 1 (актив.1 - доказано платой, Task 25); v3.9.3: пин заведён на "
    "СЕТЬ GSR (п.18)"
)
E_PRST_NEW = (
    "    input  wire       RST,          // SW20, U1.1 (P1, GSR): покой = 0, "
    "нажатие = 1 (актив.1 - доказано платой, Task 25); v3.9.6: пин входит "
    "ТОЛЬКО в синхронизатор rst_meta (п.21), GSR-ресурс ноги не задействован"
)

E_PRSTI_OLD = "    output wire       RESET_IN,     // P84 cpu7, нога 36: активный 0 = ~(RST|POR)"
E_PRSTI_NEW = (
    "    output wire       RESET_IN,     // P84 cpu7, нога 36: активный 0 = "
    "сброс CPU; v3.9.6: регистр reset_q (п.21)"
)

E_HIST_OLD = (
    "// v3.9.3: сброс ЛОГИКИ - асинхронный по RST через СЕТЬ GSR (п.18);\n"
    "// cpu_rst остался только для tx_pass/tx_q (PT-SR, защита окна POR)\n"
    "// и RESET_IN."
)
E_HIST_NEW = (
    "// v3.9.3: сброс ЛОГИКИ - асинхронный по RST через СЕТЬ GSR (п.18);\n"
    "// cpu_rst остался только для tx_pass/tx_q (PT-SR, защита окна POR)\n"
    "// и RESET_IN; v3.9.6: сырой RST - только в синхронизатор, cpu_rst =\n"
    "// rst_press|por_run (регистры), RESET_IN - регистр reset_q (п.21)."
)

E_WE_OLD = """  // v3: /WE НЕ обрывается ALE - импульс доводится до конца (п.4 шапки);
  // безопасно: автомат доходит до WB4/IDLE за 5 тиков; сброс гасит импульс:
  // v3.9.2 - cpu_rst за такт (sync), v3.9.3 - GSR мгновенно (п.18)."""
E_WE_NEW = """  // v3: /WE НЕ обрывается ALE - импульс доводится до конца (п.4 шапки);
  // безопасно: автомат доходит до WB4/IDLE за 5 тиков; сброс гасит импульс:
  // v3.9.2 - cpu_rst за такт (sync), v3.9.3 - GSR мгновенно (п.18);
  // v3.9.6 - импульс 80 нс квалификатор (400 нс) НЕ успевает оборвать:
  // начатая запись доводится до конца (полный t_WP ОЗУ), сброс гасит
  // драйвы сразу после её завершения (п.21f)."""

EDITS = [
    (E_TITLE_OLD, E_TITLE_NEW, 1),
    (E_TODO_OLD, E_TODO_NEW, 1),
    (E_TODO_NEW, P21 + E_TODO_NEW, 1),   # п.21 вставляется ПЕРЕД строкой TODO
    ("//  4) ПАСС -> .jed в плату;", C3D + "//  4) ПАСС -> .jed в плату;", 1),
    (E_POR_OLD, E_POR_NEW, 1),
    (E_FSM_OLD, E_FSM_NEW, 1),
    (E_GATE_OLD, E_GATE_NEW, 1),
    (E_RSTI_OLD, E_RSTI_NEW, 1),
    (E_PRST_OLD, E_PRST_NEW, 1),
    (E_PRSTI_OLD, E_PRSTI_NEW, 1),
    (E_HIST_OLD, E_HIST_NEW, 1),
    (E_WE_OLD, E_WE_NEW, 1),
]


def main():
    t = rd_cp(F395)
    for old, new, cnt in EDITS:
        found = t.count(old)
        assert found == cnt, (
            "якорь x%d не найден (найдено %d):\n%s" % (cnt, found, old[:90])
        )
        t = t.replace(old, new)

    # --- контроль дельты -------------------------------------------------
    checks = [
        ("wire cpu_rst = rst_press | por_run", 1),
        ("assign RESET_IN = reset_q;", 1),
        ("&& !rst_press", 1),
        ("rst_meta <= RST;", 1),
        ("if (&rst_qcnt)", 1),
        ("always @(posedge clk or posedge cpu_rst)", 3),  # FSM + tx_pass + tx_q
    ]
    for pat, want in checks:
        got = t.count(pat)
        assert got == want, "контроль: '%s' найдено %d, ожидалось %d" % (pat, got, want)
    for gone in ["wire cpu_rst = RST | por_run",
                 "assign RESET_IN = ~(RST | por_run)",
                 "&& !por_run) ? S_WB1"]:
        assert gone not in t, "контроль: старый узор остался: %s" % gone

    wr_cp(F396, t)
    open(F396U, "w", encoding="utf-8").write(t)
    assert rd_cp(F396) == t, "round-trip CP1251 FAIL"

    # --- сводка диффа ----------------------------------------------------
    old_t = open(F395U, encoding="utf-8").read()
    new_l = t.splitlines()
    old_l = old_t.splitlines()
    diff = list(difflib.unified_diff(old_l, new_l, lineterm="", n=0))
    n_add = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    n_del = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    print("gen_v396: OK")
    print("  строк: %d -> %d (+%d/-%d по unified-диффу)" % (len(old_l), len(new_l), n_add, n_del))
    print("  контролов пройдено: %d + %d отрицательных" % (len(checks), 3))


if __name__ == "__main__":
    main()
