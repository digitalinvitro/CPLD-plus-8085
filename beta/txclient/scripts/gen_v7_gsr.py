#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_v7_gsr.py — генератор txclient v7 из v6 (папка beta/txclient, 2026-11-03).

v7 = v6 (RTL п.19/20/21/22/23 БЕЗ ПРАВОК — протокол/шина/сериализатор
байт-в-бит) + МЕРА ПО СБРОСУ, доказанная на v3.9.3 (линия lowsize, фит 11-2:
GSR применилась, железо ПАСС). Директива владельца: «на основе последнего
lowsize дизайна можно попробовать txclient».

Что было (база v3.9.2 во всех фитах txclient): cpu_rst = RST | por_run
входил СИНХРОННО в D-функции всех триггеров; в проваленном фите v5 фиттер
развёрнул его в RST x151 + por_run x155 = 306 литералов (+12 импортов во все
6 ФБ) — прямое давление на узлы, не разместившиеся в v4/v5 (shreg<8>,
bit_cnt<1>, tx_byte_FSM_FFd2, hold_req__or0000).

Что стало: ОБА always-блока (шинный движок 38 триггеров + сериализатор 24)
описаны АСИНХРОННО (posedge clk or posedge RST, if (RST)) — фиттер сводит
общий асинхронный сброс на СЕТЬ GSR (пин P1 и так GSR/I/O; доказано фитом
v3.9.3 11-2: «GSR : 1 1»). cpu_rst УДАЛЁН из дизайна (0 упоминаний в коде).
ВНЕ ДОМЕНА GSR (бит-в-бит v3.9.2/v3.9.3): por_sh/por_run (POR только по
питанию, INIT=FF/1), делитель cnt/x1_n (X1 не глушится).
ЗАЩИТА ОКНА POR (класс v3.9.3 п.18 + СПЕЦИФИКА txclient): FSM/сериализатор
в окне POR живые (GSR не активен), шина CPU «floated» — ДВА гейта !por_run:
  - S_T2 -> WB1 (как v3.9.3): /WE в окне POR невозможен ПО ПОСТРОЕНИЮ;
  - взвод hold_req в T1H (НОВОЕ, аналога в v3.9.3 не было — там не было
    HOLD-движка): floated A/S0/S1 не взводят hold_req, иначе HOLD/HLDA и
    floated WRn в T2 родили бы ложный захват и мусорный кадр в TX.

Использование: python3 gen_v7_gsr.py  (из scripts/ или из корня txclient)
Создаёт: ../top_txclient_v7_utf8.v и ../top_txclient_v7.v (CP1251).
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'top_txclient_v6_utf8.v')
OUT_U8 = os.path.join(HERE, '..', 'top_txclient_v7_utf8.v')
OUT_CP = os.path.join(HERE, '..', 'top_txclient_v7.v')

# ------------------------------------------------------------------ п.24
P24 = """// 24) TXCLIENT v7 (2026-11-03; база v3.9.3 - директива владельца
//     «на основе последнего lowsize дизайна можно попробовать txclient»):
//     СБРОС ЛОГИКИ И СЕРИАЛИЗАТОРА ПЕРЕВЕДЁН НА СЕТЬ GSR. Что было
//     (база v3.9.2 во всех фитах txclient): cpu_rst = RST | por_run
//     входил СИНХРОННО в D-функции ВСЕХ триггеров (Task 25); в
//     проваленном фите v5 (rpt 11-1 7:31PM) фиттер развёрнул его в
//     RST x151 + por_run x155 = 306 литералов сброса (+12 импортов RST/
//     por_run во все 6 ФБ) - прямое давление на узлы, не разместившиеся
//     в v4/v5 (shreg<8> 18ПТ/26вх, bit_cnt<1>, tx_byte_FSM_FFd2,
//     hold_req__or0000). Мера доказана на v3.9.3 (фит 11-2, железо
//     ПАСС): литералы 133 -> 3, вх.ФБ 180 -> 171/173, ПТ 209 -> 192/195.
//     Что стало: ОБА always-блока (шинный движок 38 триггеров:
//     state/rd_seen/wr_seen/addr_latch/bus_reg/seg_q/dig_q/snd_q/
//     kbcol_q + сериализатор 24: hold_req/hlda_q/cap_run/tx_byte/
//     bit_cnt/baud_cnt/shreg/adv_q/ld_q) описаны АСИНХРОННО (posedge
//     clk or posedge RST, if (RST)) - фиттер сводит общий асинхронный
//     сброс на СЕТЬ GSR (пин P1 и так GSR/I/O): минус ~306 литералов,
//     минус ~12 импортов ФБ; wire cpu_rst УДАЛЁН (в коде 0 упоминаний;
//     RESET_IN считает RST|por_run напрямую - без изменений).
//     ВНЕ ДОМЕНА GSR (сознательно, бит-в-бит v3.9.3):
//       - por_sh/por_run: POR только по питанию (INIT=FF/1), повторный
//         POR невозможен (после 00 сдвиг держит нули);
//       - делитель cnt/x1_n: X1 не глушится при сбросе (свойство v3.9).
//     ЗАЩИТА ОКНА POR (класс v3.9.3 п.18 + СПЕЦИФИКА txclient): FSM и
//     сериализатор в окне POR живые (GSR не активен), шина CPU в сбросе
//     «floated» (ВМ85А: управления/адрес/данные в 3-м состоянии):
//       - вход в writeback ГЕЙТЕТСЯ (!por_run в S_T2) - импульс /WE в
//         окне POR невозможен ПО ПОСТРОЕНИЮ (как v3.9.3);
//       - взвод hold_req ГЕЙТЕТСЯ (!por_run в T1H) - НОВОЕ, аналога в
//         v3.9.3 не было (там не было HOLD-движка): floated A/S0/S1 не
//         взводят hold_req; БЕЗ гейта came HOLD/HLDA в окне POR, а
//         floated WRn в T2 родил бы ложный захват и мусорный кадр в TX
//         (cap_run возможен ТОЛЬКО при hold_req=1 - второго гейта не
//         нужно).
//     ПОВЕДЕНИЕ (отличия от v6): сброс стал АСИНХРОННЫМ - нажатие SW20
//     мгновенно гасит FSM и пакет (HOLD падает сразу, TX -> '1' сразу,
//     shreg -> 1FF через SET-ветку GSR; v6 - на такт позже). Нормальные
//     циклы шины и пакеты бит-в-бит v6 (дифсимуляция).
//     РИСК GSR (recovery/removal при снятии кнопки асинхронно к
//     25 МГц) - класс-риск XC9500, как v3.9.3: самозатухающий (FSM в
//     IDLE, оба гейта стоят, защитный релиз IDLE сохранён) -
//     осознанный компромисс; на v3.9.3 железом НЕ проявился (плата
//     11-2 прошита и работает).
//     ВЕРИФИКАЦИЯ: (1) scripts/sim_txclient_v7.py - все сценарии v6 +
//     НОВОЕ (п.24): hostile-«плавания» шины в окне POR (пор_run=1) -
//     ноль /WE, ноль HOLD, ноль TX-активности, ноль cap_run; сброс
//     посреди пакета гасит HOLD мгновенно (GSR-семантика, не на такт);
//     пост-сбросные состояния бит-в-бит значениям RST-ветки; (2)
//     scripts/tb_txclient_v7.v - для владельца (Icarus).
//     ЭКОНОМИКА: план Б п.23 не тронут (Collapsing Input Limit 24-28,
//     окно 8000-9FFF, BAUD_DIV 16); GSR-мера закрывает и «por_sh 8->4»
//     (см. п.18 lowsize: POR 560 нс < нормы 840 - нелегально; GSR
//     дешевле и тайминги CPU не трогает).
//
"""

# ------------------------------------------------------------------ правки
# (old, new, комментарий). Каждый old обязан встречаться РОВНО ОДИН раз.
EDITS = []

# E1. Титул (строка 1).
EDITS.append((
"// top_txclient.v v6 (TXCLIENT, база v3.9.2) - retro_pcld_top + МОНИТОР ЗАПИСЕЙ CPU В",
"// top_txclient.v v7 (TXCLIENT, база v3.9.3) - retro_pcld_top + МОНИТОР ЗАПИСЕЙ CPU В",
"титул строка 1"))

# E1b. Титул (хвост, строка 11).
EDITS.append((
"// CPU 3,57 МГц (X1/X2 = 7,14 МГц; делитель: двоичный счётчик mod-7, п.17;\n"
"// CS_n в writeback ОТ СОСТОЯНИЯ FSM, п.16)",
"// CPU 3,57 МГц (X1/X2 = 7,14 МГц; делитель: двоичный счётчик mod-7, п.17;\n"
"// CS_n в writeback ОТ СОСТОЯНИЯ FSM, п.16; СБРОС ЛОГИКИ И СЕРИАЛИЗАТОРА ->\n"
"// СЕТЬ GSR, п.24)",
"титул хвост"))

# E2. Строка истории (дата).
EDITS.append((
"//  v3.9.2 делитель: кольцо one-hot N=7 -> двоичный счётчик mod-7,\n"
"//  линия lowsize (п.17) - 2026-10-30). База: v1 (Task 70-a, логика чтения/захвата",
"//  v3.9.2 делитель: кольцо one-hot N=7 -> двоичный счётчик mod-7,\n"
"//  линия lowsize (п.17) - 2026-10-30; v3.9.3 сброс логики -> СЕТЬ GSR\n"
"//  (низсайз, п.18) - 2026-11-02; v7 = база v3.9.3: сброс логики И\n"
"//  сериализатора -> GSR, cpu_rst удалён (п.24) - 2026-11-03). База: v1 (Task 70-a, логика чтения/захвата",
"история"))

# E3. Порт RST.
EDITS.append((
"    input  wire       RST,          // SW20, U1.1 (P1, GSTR): покой = 0, нажатие = 1 (актив.1 - доказано платой, Task 25)",
"    input  wire       RST,          // SW20, U1.1 (P1, GSR): покой = 0, нажатие = 1 (актив.1 - доказано платой, Task 25); v7: пин заведён на СЕТЬ GSR (п.24)",
"порт RST"))

# E4. Блок «Сброс» перед module.
EDITS.append((
"// Сброс: SW20 -> RST (нажатие = 1, Task 25) + POR (v3.4: сдвиговый;\n"
"// 1120 нс @ 7,14 МГц в v3.9) -> RESET_IN=0;\n"
"// GSR НЕ используется - сброс всех триггеров через cpu_rst.",
"// Сброс: SW20 -> RST (нажатие = 1, Task 25) + POR (v3.4: сдвиговый;\n"
"// 1120 нс @ 7,14 МГц в v3.9) -> RESET_IN=0;\n"
"// v7 (п.24): сброс ЛОГИКИ и СЕРИАЛИЗАТОРА - асинхронный по RST через\n"
"// СЕТЬ GSR; cpu_rst удалён; por_sh/por_run - вне домена (POR только\n"
"// по питанию); гейты !por_run - в S_T2->WB1 и на взводе hold_req.",
"блок «Сброс»"))

# E5. Вставка п.24 + заголовок TODO.
EDITS.append((
"// Что делать владельцу (TODO, ред. txclient v6; база v3.9.2 сохранена):",
P24 +
"// Что делать владельцу (TODO, ред. txclient v7; база v3.9.3/GSR):",
"вставка п.24 + заголовок TODO"))

# E6. TODO п.3 - хвост (перед "4) ПАСС") + пункт 3a про GSR.
EDITS.append((
"//     СТАРЫЙ исходник;\n"
"//  4) ПАСС -> .jed в плату; осциллограф: X1 = 7,14 МГц (период ровно",
"//     СТАРЫЙ исходник;\n"
"//  3a) v7 (GSR, п.24): в .rpt - \"Global set/reset net(s) used\",\n"
"//     \"GSR : 1\"; литералов RST/por_run в D-функциях ЛОГИКИ и\n"
"//     СЕРИАЛИЗАТОРА НЕТ (v5: RST x151 + por_run x155 = 306 - должны\n"
"//     ИСЧЕЗНУТЬ); cpu_rst в нетлисте НЕТ; уравнение RESET_IN =\n"
"//     (por_run) OR (RST) СОХРАНИЛОСЬ; два гейта !por_run на месте\n"
"//     (S_T2->WB1 и взвод hold_req); por-цепь и cnt/x1_n - без GSR.\n"
"//     ЕСЛИ GSR НЕ применился - rpt НА РАЗБОР, НЕ прошивать (фит\n"
"//     функционально корректен, но мера не сработала);\n"
"//  4) ПАСС -> .jed в плату; осциллограф: X1 = 7,14 МГц (период ровно",
"TODO 3a"))

# E7. Чек-лист f).
EDITS.append((
"//  f) GSR НЕ используется (сброс через D-gating, Task 25);",
"//  f) v6 (база v3.9.2): GSR НЕ использовался (сброс через D-gating,\n"
"//     Task 25). v7 (п.24): СЕТЬ GSR ИСПОЛЬЗУЕТСЯ: \"Global set/reset\n"
"//     net(s) used\" + \"GSR : 1\" в Pin Resources; строка RST в Node\n"
"//     Listing - тип GSR/I/O с признаком GSR (P1, буфер GSR/I); в\n"
"//     D-уравнениях ЛОГИКИ и СЕРИАЛИЗАТОРА нет защит \"NOT RST\"/\n"
"//     \"NOT por_run\" (v5: 306 вхождений - должны ИСЧЕЗНУТЬ); RST в\n"
"//     списках входов ФБ - не более 1 (ФБ RESET_IN); por_run - только\n"
"//     у RESET_IN и двух гейтов (!por_run в hold_req.D и переходе\n"
"//     S_T2->WB1); RESET_IN = (por_run) OR (RST) СОХРАНИЛОСЬ; por_sh/\n"
"//     por_run/cnt/x1_n - БЕЗ GSR (9 регистров); 62 регистра логики и\n"
"//     сериализатора - async SR по RST (GSR), у shreg<8:0> - SET\n"
"//     (INIT 1FF, TX idle '1' в сбросе). ЕСЛИ \"Global set/reset net(s)\n"
"//     unused\" СОХРАНИЛОСЬ - фиттер не дал частичный GSR: фит\n"
"//     функционально корректен (PT-сбросы), но мера не сработала -\n"
"//     rpt НА РАЗБОР, НЕ прошивать;",
"чек-лист f)"))

# E8. Чек-лист g) - прогноз ресурсов v7 после прогноза v6.
EDITS.append((
"//     прогноз ~102-106/108 МЦ, вх.ФБ ~185-205/216, ПТ ~350-380; план Б:\n"
"//     Collapsing Input Limit 24-28;",
"//     прогноз ~102-106/108 МЦ, вх.ФБ ~185-205/216, ПТ ~350-380; план Б:\n"
"//     Collapsing Input Limit 24-28;\n"
"//     txclient v7 (п.24): GSR-сброс (база v3.9.3): минус 306 литералов\n"
"//     сброса, минус ~12 импортов RST/por_run; эффект меры доказан на\n"
"//     v3.9.3 (вх.ФБ -7..-9, ПТ -14..-17 при 133 литералах; здесь их\n"
"//     306 - выигрыш НЕ МЕНЬШЕ) -> прогноз МЦ ~100-105/108, вх.ФБ\n"
"//     ~178-198/216, ПТ ~335-375/540; триггеров 75 (v6: 75), ноги 73/81,\n"
"//     UCF без правок; shreg<8> ОБЯЗАН разместиться (его D худеет ещё\n"
"//     и от ухода cpu_rst-развёрток);",
"чек-лист g) прогноз v7"))

# E9. Чек-лист h) - уравнения v7 (после п.23.1, перед =====).
EDITS.append((
"//     автоматически: scripts/check_decl_order.py (ловит класс\n"
"//     HDLCompilers:28 до ISE; на v6-до правки даёт ровно набор XST).",
"//     автоматически: scripts/check_decl_order.py (ловит класс\n"
"//     HDLCompilers:28 до ISE; на v6-до правки даёт ровно набор XST).\n"
"//     txclient v7 (п.24): D-функции state/rd_seen/wr_seen/addr_latch/\n"
"//     bus_reg/seg_q/dig_q/snd_q/kbcol_q/hold_req/hlda_q/cap_run/\n"
"//     tx_byte/bit_cnt/baud_cnt/shreg/adv_q/ld_q - БЕЗ литералов\n"
"//     сброса (чистая логика); SR-входы 62 регистров логики и\n"
"//     сериализатора - RST (СЕТЬ GSR), у shreg<8:0> - SET (значение\n"
"//     1FF); por-цепь бит-в-бит v3.9.2 (por_sh сдвиг, por_run.D =\n"
"//     por_sh[0], Init=SET); hold_req.D = hold_req OR (state==S_T1H)\n"
"//     AND ALE AND win_hit AND NOT por_run (новый гейт п.24);\n"
"//     state: T2->WB1 = ... AND NOT por_run (гейт v3.9.3); cpu_rst в\n"
"//     нетлисте ОТСУТСТВУЕТ; RESET_IN = por_run OR RST (без изменений).",
"чек-лист h) уравнения v7"))

# E10. Пор-блок: комментарий вне домена GSR.
EDITS.append((
"  // clk через por_ce из делителя); por_run остаётся РЕГИСТРОМ (v3.2,\n"
"  // п.8 шапки - защита от схлопывания PT / Placement Failed).",
"  // clk через por_ce из делителя); por_run остаётся РЕГИСТРОМ (v3.2,\n"
"  // п.8 шапки - защита от схлопывания PT / Placement Failed); v7:\n"
"  // por_sh/por_run ВНЕ домена GSR (п.24) - POR только по питанию.",
"пор-блок комментарий"))

# E11. cpu_rst - удаление def.
EDITS.append((
"  reg  por_run = 1'b1;           // FF-копия для cpu_rst (v3.2; INIT=SET)\n"
"  wire cpu_rst = RST | por_run;  // CPU в сбросе: SW20 нажата или POR",
"  reg  por_run = 1'b1;           // FF-копия POR (v3.2; INIT=SET); v7: вне\n"
"                                 // домена GSR - POR только по питанию (п.24)\n"
"  // v7 (п.24): wire cpu_rst УДАЛЁН - логика (38 триггеров) и\n"
"  // сериализатор (24) сбрасываются АСИНХРОННО через СЕТЬ GSR по RST;\n"
"  // por_run остался для RESET_IN и ДВУХ гейтов окна POR (!por_run в\n"
"  // S_T2->WB1 и на взводе hold_req).",
"cpu_rst удаление"))

# E12. Главный always: синхронный сброс -> асинхронный (GSR).
EDITS.append((
"  always @(posedge clk) begin        // синхронный сброс всех триггеров по (RST|POR) - Task 25\n"
"    if (cpu_rst) begin",
"  always @(posedge clk or posedge RST) begin // v7: асинхронный сброс логики по RST -> СЕТЬ GSR (п.24)\n"
"    if (RST) begin",
"always шинного движка"))

# E13. Гейт POR на входе в writeback.
EDITS.append((
"              // writeback только для записи в ОЗУ (8000-FFFF); запись в ПЗУ\n"
"              // отбрасывается (по железу /WE flash не подключён), порт пропускается\n"
"              state <= (!IOM && A15) ? S_WB1 : S_IDLE;",
"              // writeback только для записи в ОЗУ (8000-FFFF); запись в ПЗУ\n"
"              // отбрасывается (по железу /WE flash не подключён), порт пропускается\n"
"              // v7 (п.24): гейт POR - FSM в окне POR живой (GSR не активен),\n"
"              // шина CPU в сбросе «floated» (ВМ85А: управления/адрес/данные\n"
"              // в 3-м состоянии) - вход в writeback ЗАПРЕЩЁН, иначе\n"
"              // плавающие ALE/WRn могли бы родить /WE (класс v3.9.3 п.18)\n"
"              state <= (!IOM && A15 && !por_run) ? S_WB1 : S_IDLE;",
"гейт por_run в S_T2"))

# E14. Сериализатор: синхронный сброс -> асинхронный (GSR).
EDITS.append((
"  always @(posedge clk) begin\n"
"    if (cpu_rst) begin\n"
"      hold_req <= 1'b0;  hlda_q <= 1'b0;  cap_run <= 1'b0;",
"  always @(posedge clk or posedge RST) begin // v7: асинхронный сброс сериализатора по RST -> СЕТЬ GSR (п.24)\n"
"    if (RST) begin\n"
"      hold_req <= 1'b0;  hlda_q <= 1'b0;  cap_run <= 1'b0;",
"always сериализатора"))

# E15. Гейт POR на взводе hold_req.
EDITS.append((
"      if (state == S_T1H && ALE && win_hit) hold_req <= 1'b1;",
"      // v7 (п.24): гейт POR - floated A/S0/S1 в окне POR не взводят\n"
"      // hold_req (иначе HOLD/HLDA в окне POR, а floated WRn в T2 родил\n"
"      // бы ложный захват и мусорный кадр в TX; cap_run возможен только\n"
"      // при hold_req=1 - отдельного гейта не нужно)\n"
"      if (state == S_T1H && ALE && win_hit && !por_run) hold_req <= 1'b1;",
"гейт por_run на hold_req"))

# E16. Комментарий /WE.
EDITS.append((
"  // v3: /WE НЕ обрывается ALE - импульс доводится до конца (п.4 шапки);\n"
"  // безопасно: автомат доходит до WB4/IDLE за 5 тиков, сброс (cpu_rst) гасит.",
"  // v3: /WE НЕ обрывается ALE - импульс доводится до конца (п.4 шапки);\n"
"  // безопасно: автомат доходит до WB4/IDLE за 5 тиков; сброс гасит импульс:\n"
"  // v6 - cpu_rst за такт (sync), v7 - GSR мгновенно (п.24).",
"комментарий /WE"))

# E17. Комментарий TX.
EDITS.append((
"                                // idle/стоп = '1' (INIT shreg=1FF), в сбросе TX='1';",
"                                // idle/стоп = '1' (INIT shreg=1FF), в сбросе TX='1'\n"
"                                // (v7: сброс shreg по GSR - SET-ветка, п.24);",
"комментарий TX"))


def main():
    src = io.open(SRC, encoding='utf-8').read()
    s = src
    for old, new, tag in EDITS:
        n = s.count(old)
        if n != 1:
            print('ОШИБКА: якорь %r встречается %d раз (ожидался 1)' % (tag, n))
            sys.exit(1)
        s = s.replace(old, new)
        print('ок: %s' % tag)

    # Контроль 1: cpu_rst в КОДЕ (до //) ровно 0 упоминаний (в v6 их было
    # 3: def + 2 if). В комментариях п.24 - можно (там он объясняется).
    code_mentions = 0
    for ln in s.split('\n'):
        bare = ln.split('//')[0]
        code_mentions += bare.count('cpu_rst')
    if code_mentions != 0:
        print('ОШИБКА: cpu_rst в КОДЕ %d раз (ожидалось 0)' % code_mentions)
        sys.exit(1)
    print('ок: cpu_rst в коде 0 упоминаний (удалён)')

    # Контроль 2: синхронного сброса нет, асинхронного - ровно 2 блока.
    for frag, want in (
        ("always @(posedge clk or posedge RST) begin", 2),
        ("    if (RST) begin", 2),
        ("if (cpu_rst)", 0),
        ("(!IOM && A15 && !por_run)", 1),
        ("win_hit && !por_run", 1),
        ("assign RESET_IN = ~(RST | por_run);", 1),
    ):
        got = s.count(frag)
        if got != want:
            print('ОШИБКА: %r встречается %d раз (ожидалось %d)' % (frag, got, want))
            sys.exit(1)
    print('ок: конструкции v7 на месте (2 GSR-блока, 2 гейта POR)')

    # Контроль 3: пор-цепь и делитель НЕ тронуты (бит-в-бит v3.9.2).
    for frag in ("assign X1 = (cnt != 3'd0) ^ x1_n;",
                 "assign X2 = (cnt == 3'd0) ^ x1_n;",
                 "assign por_ce = (cnt == 3'd1) | (cnt == 3'd6);",
                 "reg [2:0] cnt = 3'd0;",
                 "por_run <= por_sh[0];",
                 "if (por_ce) por_sh <= {1'b0, por_sh[7:1]};"):
        if s.count(frag) != 1:
            print('ОШИБКА: пор/делитель повреждён: %r' % frag)
            sys.exit(1)
    print('ок: пор-цепь и делитель бит-в-бит v3.9.2')

    # Контроль 4: значения сброса v6 сохранены в RST-ветках.
    for frag in ("      state      <= S_IDLE;",
                 "      seg_q      <= 8'hFF;   // INIT «8888.» на индикаторе",
                 "      shreg <= 9'h1FF;  adv_q <= 1'b0;  ld_q <= 1'b0;",
                 "      kbcol_q    <= 4'h0;"):
        if s.count(frag) != 1:
            print('ОШИБКА: RST-ветка без %r' % frag)
            sys.exit(1)
    print('ок: значения сброса бит-в-бит v6')

    io.open(OUT_U8, 'w', encoding='utf-8', newline='').write(s)

    # CP1251-версия: строго (любой символ вне CP1251 - ошибка).
    try:
        data = s.encode('cp1251')
    except UnicodeEncodeError as e:
        print('ОШИБКА CP1251: %s' % e)
        sys.exit(1)
    io.open(OUT_CP, 'wb').write(data)

    # Round-trip: CP1251 -> UTF-8 == utf8-версия.
    back = data.decode('cp1251')
    assert back == s, 'round-trip CP1251 сломан'
    print('ок: round-trip CP1251 проверен (%d байт CP1251, %d байт UTF-8)'
          % (len(data), len(s.encode('utf-8'))))


if __name__ == '__main__':
    main()
