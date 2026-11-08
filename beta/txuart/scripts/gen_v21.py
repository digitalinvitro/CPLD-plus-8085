#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_v21.py - генератор TXUART v2.1 из v2.0 (beta/txuart).

Директива владельца 11-8веч: «У нас нет еще 144 Xilinx, все так же на
108, смотри отчет фит нее лезет» (+ .rpt 11-8 7:14PM, xc95108, FAILED:
Cpld:837 needs 431 - фантом фрагментации при Input Limit 1 / Pterm
Limit 1 / Exhaustive ON; честный бюджет v2.0 111-113 МЦ > 108).

v2.1 = ядро 20 -> 18 МЦ (база v3.9.8-clear, ld_tx_q п.29 - БЕЗ
ИЗМЕНЕНИЙ):
  - adv_q ВЫПИЛЕН: jam baud_cnt <= 0 вместо <= 1 - первый сдвиг на ТОТ
    ЖЕ фронт (лаг adv_q 1 такт скомпенсирован; дифсим v2.0 vs v2.1);
  - tx_run ВЫПИЛЕН: кодировка bit_cnt 1..10 (бит-таймы кадра), idle =
    0000; busy = |bit_cnt (1 ПТ/NOR), TXRDY = ~|bit_cnt (1 ПТ), гейт
    io_wr_tx - 4 inline-литерала (1 ПТ, дешевле v2.0 с узлом tx_run);
    GSR-ветка bit_cnt - CLR (0000 = idle), как в v2.0;
  - shreg 9 бит сам-idle, {A,1'b0} - БЕЗ ИЗМЕНЕНИЙ (v2.0).

Правки-region (всё остальное - БАЙТ-В-БАЙТ v2.0, проверяет check_v21):
  A  шапка-титул (строки 2..27)          -> v2.1
  B1 п.27-п.32 + TODO                    -> v2.1 (+ п.33 резерв)
  B2 чек-лист .rpt: пункты f)/g)/h)      -> v2.1 (3 точечные правки)
  D  ядро TXUART (RTL)                   -> v2.1
  E  статус-мультиплексор A1             -> tx_idle
Сим: scripts/sim_txuart_v21.py из sim_txuart_v2.py (модель ядра +
     проверки сценариев С1-С9 на new-кодировку).

Запуск: python3 scripts/gen_v21.py   (пути от папки скрипта)
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TX   = os.path.dirname(HERE)                      # beta/txuart

V2_UTF8   = os.path.join(TX, "top_txuart_por6_v2_utf8.v")
V21_UTF8  = os.path.join(TX, "top_txuart_por6_v21_utf8.v")
V21_CP    = os.path.join(TX, "top_txuart_por6_v21.v")
SIM_V2    = os.path.join(HERE, "sim_txuart_v2.py")
SIM_V21   = os.path.join(HERE, "sim_txuart_v21.py")


def read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def write_utf8_cp1251(text, p_utf8, p_cp):
    with open(p_utf8, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    try:
        blob = text.encode("cp1251")
    except UnicodeEncodeError as e:
        sys.exit(f"CP1251: символ не кодируется: {e}")
    with open(p_cp, "wb") as f:
        f.write(blob)
    if blob.decode("cp1251") != text:
        sys.exit("CP1251 round-trip: рассинхрон")


def idx_of(lines, prefix, start=0):
    for i in range(start, len(lines)):
        if lines[i].startswith(prefix):
            return i
    sys.exit(f"якорь не найден: {prefix!r}")


# ---------------------------------------------------------------- RTL
NEW_A = """// top_txuart.v v2.1 - retro_pcld_top + TXUART: ИСКЛЮЧИТЕЛЬНО АППАРАТНЫЙ
// ПЕРЕДАТЧИК UART 8N1 1 562 500 бод (такт ядра clk25 = 25 МГц / 2^4,
// BAUD_DIV=16 - натуральный wrap счётчика-делителя БЕЗ декода, п.27)
// на БАЗЕ v3.9.8-clear: вход CPLD 50 МГц - H1 без шунта; КОЛЬЦО one-hot
// r0..r6 на clk 50, X1 = r0 duty 1/7, X2 = r1|..|r6 = ~r0, clk25 = /2
// для логики, por-цепь на clk 50 со стробом r0, п.23 - БЕЗ ИЗМЕНЕНИЙ;
// CS_n от FSM, п.16; СБРОС ЛОГИКИ -> СЕТЬ GSR от узла cpu_rst, п.18/20;
// RST только через регистры, п.21
//
// ЛИНИЯ beta/txuart, ВЕРСИЯ 2.1 (директива владельца 11-8веч: «У нас
// нет еще 144 Xilinx, все так же на 108, смотри отчет фит нее лезет» -
// XC95144 недоступна, целевое устройство СНОВА XC95108-15-PQ100C).
// БАЗА = lowsize v3.9.8-clear ред.2 (фит 11-7 10:09PM 1-в-1 ЗОЛОТОМУ
// v3.9.8, ПРОШИТ И РАБОТАЕТ: 94/108 МЦ) - узел тактирования (кольцо),
// POR-цепь, харденинг сброса п.20/21 и FSM шины - БИТ-В-БИТ. ИСТОРИЯ
// v2.0 (цель была XC95144): фит владельца 11-8 7:14PM на xc95108 упал
// с ERROR:Cpld:837 «needs at least 431» - ФАНТОМ фрагментации (в
// прогоне стояли Exhaustive ON + Input Limit 1 + Pterm Limit 1 - при
// IL/PT=1 фиттер режет логику на однолитеральные осколки $OpTx$BIN_*
// (296 шт); успешная линия всегда: Exhaustive OFF, IL 16..28, Pterm
// 18 - разбор п.27). ЧЕСТНЫЙ бюджет v2.0 (п.31 ред. v2.0) 111-113 МЦ
// и вправду > 108 - v2.1 СЖИМАЕТ ЯДРО 20 -> 18 МЦ (п.31): adv_q и
// tx_run свернуты (jam 0; bit_cnt 1..10, idle = 0, busy = |bit_cnt -
// 1 ПТ), shreg 9 бит сам-idle и ld_tx_q (п.29) - БЕЗ ИЗМЕНЕНИЙ; провод
// TX и TXRDY - 1-в-1 v2.0 (доказано дифсимом, п.31). Ядро TXUART
// (механика v1.0 = txclient v8/hwuart v4.0.1: shreg сам-idle,
// jam-фазировка, регистровый строб ld_tx_q) - на (clk25, cpu_rst).
// ЦЕЛЬ - XC95108-15PQ100C: наивно 94 - 3 транзит + 18 = 109, по
// прецеденту v1.0 (фит лёг на 2 МЦ ниже наивной суммы) ожидание
// 105-108; резерв п.33 (-1 МЦ) - только по команде владельца.
// Спека/бюджет/контракт/чек-лист фита - блок «TXUART v2.1» в конце
// шапки и README линии.
//"""

NEW_B1 = """// TXUART v2.1 (п.27-п.33) - ИСКЛЮЧИТЕЛЬНО АППАРАТНЫЙ ПЕРЕДАТЧИК UART
// НА БАЗЕ v3.9.8-clear. Директива владельца 11-8веч: «У нас нет еще
// 144 Xilinx, все так же на 108, смотри отчет фит нее лезет» (+ .rpt
// 11-8 7:14PM). База бит-в-бит (узел п.22/23, POR, харденинг сброса
// п.20/21, FSM шины); TX-транзит v3.7 выпилен (п.3/п.13 - истор.);
// SOD (P72) - вход-наблюдатель keep; SID = RX сохранён; ядро v1.0
// пересажено с (clk, RST) на (clk25, cpu_rst) и СЖАТО 20 -> 18 МЦ.
//
// п.27 РАЗБОР ФИТА v2.0 (11-8 7:14PM, xc95108, FAILED - архив:
//   «retro_pcld_top (v2-fit1-1108-0714PM-FAILED).rpt»): статус Design
//   Rule Checking Failed, ERROR:Cpld:837 «needs at least 431», 868,
//   «No logic has been mapped», 386 незмапленных узлов (296 из них -
//   однолитеральные осколки $OpTx$BIN_STEP), глобальные GCK/GSR/GTS
//   не назначены. ПРИЧИНА №1 - ЧУЖИЕ ОПЦИИ ФИТТЕРА: в Compiler Options
//   отчёта Exhaustive Fitting: ON + Input Limit: 1 + Pterm Limit: 1;
//   успешная линия всегда: Exhaustive OFF + IL 16..28 + Pterm 18
//   (п.25/п.26; INFO:Cpld:994 «pterm limit: 1 and input limit: 1» в
//   успешных .rpt линии НЕ встречается вовсе). При IL/PT=1 коллапсинг
//   выключен - каждый аддер/мультиплексор рассыпается на 1-ПТ крошки,
//   111 МЦ честной логики раздувается в 431 МЦ фантома. ВЫВОД: 431 -
//   НЕ размер дизайна. ПРИЧИНА №2 - ЧЕСТНЫЙ ПЕРЕБОР: бюджет v2.0
//   (п.31 ред. v2.0) 111-113 МЦ > 108 - на XC95108 v2.0 не влезала и
//   с правильными опциями (потому цель была XC95144). Директива
//   11-8веч: 144 НЕТ -> ядро сжато до 18 МЦ (п.31), цель XC95108.
// п.28 СПЕКА (= v2.0 п.27): TX-only 8N1, бод = clk25 (25 МГц) / 2^4 =
//   1 562 500 (BAUD_DIV=16 - СТЕПЕНЬ ДВОЙКИ: счётчик-делитель -
//   свободный двоичный mod-16, wrap натуральный БЕЗ декода
//   терминального счёта и сбросовой логики - «удобный для счетчиков
//   делителей бод рейтинг» по директиве 11-8; CH340G до 2 Мбит,
//   проверен владельцем на 1,92 М). Доступ CPU: OUT 04h = TXDATA
//   (старт кадра), IN 05h = статус {000000, TXRDY, 0} (бит A1 =
//   tx_idle = ~|bit_cnt - позиция совместима с hwuart v4.0.x). RX
//   НЕТ: приём - программный (SID = RX, RIM 20h - как в lowsize).
//   Такт ядра - clk25 (такт ЛОГИКИ п.23): бод на плате = РОВНО
//   1 562 500 - 2х-блокер фита v1.0 (3,125 М) снят ПО СТРОЕНИЮ.
// п.29 СБРОС/ДОМЕНЫ (= v2.0 п.28 БЕЗ ИЗМЕНЕНИЙ): узел (кольцо r0..r6,
//   clk25_q, por_sh/por_run) - clk 50 МГц, ВНЕ GSR (бит-в-бит базы);
//   логика (FSM, rst-цепь, ядро) - clk25; СЕТЬ GSR - от cpu_rst =
//   rst_press | por_run (п.20/21): ядро в GSR-домене (shreg SET-ветка
//   INIT=1FF - TX='1' до всякого клока; bit_cnt/baud_cnt/ld_tx_q -
//   CLR), чистится и в окне POR, и при кнопке. RESET_IN = reset_q -
//   РЕГИСТР (п.21d, бит-в-бит базы). ЛАТЕНТНОСТЬ кнопки 400..440 нс
//   (п.21): RST посреди кадра глушит ядро через ~10 тиков clk25 -
//   класс «сброс во время передачи = линия в idle», приёмник кадр
//   отбрасывает.
// п.30 РЕГИСТРОВЫЙ СТРОБ ЗАГРУЗКИ ld_tx_q (= v2.0 п.29, БЕЗ ИЗМЕНЕНИЙ):
//   io_wr_tx имеет ЕДИНСТВЕННОГО потребителя (ld_tx_q.D); загрузка
//   shreg - на тик ПОЗЖЕ строба с живых A-пинов: CPU держит данные до
//   подъёма WRn (>= 20 тиков clk25) - запас x10; !ld_tx_q в декоде =
//   ОДНОКРАТНОСТЬ (первый тик !WRn); !rst_press - класс п.21e (оба
//   источника сброса гейтят шинные действия). НОВАЦИЯ v2.1: гейт
//   занятости в декоде - ЛИТЕРАЛЫ tx_idle (4 inline-литерала ~|bit_cnt
//   в тот же 1 ПТ - узел tx_run v2.0 не нужен): OUT 04h при busy тихо
//   отбрасывается, кадр не портится (контракт v1.0/v2.0).
// п.31 ТАЙМИНГ КАДРА И БЮДЖЕТ: загрузка (ld_tx_q) -> старт-бит '0' с
//   этого такта, jam baud_cnt <= 0 -> первый сдвиг ровно через 16
//   тиков clk25 - старт РОВНО 16 тиков = 640 нс, ВСЕ переходы на
//   сетке 16 тиков (v2.0 достигал того же парой «jam 1 + лаг adv_q» -
//   фронт первого сдвига СОВПАДАЕТ, дифсим v2.0 vs v2.1: сетка 1-в-1);
//   bit_cnt = 1..10 - НОМЕР БИТ-ТАЙМА кадра (1 = старт, 2..9 = данные,
//   10 = стоп): на 10-м сдвиге bit_cnt сам в 0 (idle) - кадр закрыт
//   РОВНО на 10-м бит-тайме, TXRDY = ~|bit_cnt поднимается в конце
//   стопа (ТОТ ЖЕ тик, что !tx_run v2.0 - дифсим); сдвиг idle-регистра
//   (все '1') - НЕТ-ОП, гейт сдвига shreg НЕ НУЖЕН (bit_cnt
//   инкрементируется только при busy - иначе бы бежал в idle);
//   инжекция '1' в MSB: после кадра shreg сам в 1FF (idle по
//   построению, как txclient); при непрерывном поллинге фактический
//   стоп у ПК >= 1 полного бита (приёмник терпит длинный стоп -
//   контракт hwuart). сброс cpu_rst: GSR, TX='1' (SET-ветка shreg),
//   ядро вычищено (CLR-ветка bit_cnt/baud_cnt/ld_tx_q - как v2.0).
//   БЮДЖЕТ/ПРОГНОЗ ФИТА: база 94 МЦ - 3 (транзит sod_q/tx_pass/tx_q) +
//   18 (ядро: shreg 9 + bit_cnt 4 + baud_cnt 4 + ld_tx_q 1; ВЫПИЛЕНЫ
//   adv_q 1 и tx_run 1 против v2.0) = 109 МЦ наивно; ПРЕЦЕДЕНТ v1.0:
//   наивная сумма 102, фит лёг в 100 (-2: фиттер сверяет логику ядра
//   с шинной) -> ожидание 105-108 <= 108 - ВЛЕЗАЕТ НА XC95108. Запас
//   тонкий: если фит скажет «needs N», N > 108 - НЕ крутить опции
//   (класс-урок п.27!), писать на аудит; следующий рычаг - резерв
//   п.33. Допуск чек-листа g): МЦ 105-108, рег ~78, вх.ФБ ~200-212/216,
//   ПТ ~300-340/540, ноги 72/81.
// п.32 ЧЕК-ЛИСТ ФИТА (владельцу, после прогона ISE): УСТРОЙСТВО в
//   проекте - xc95108-15pq100c (v2.0 просил xc95144 - ВЕРНУТЬ, если
//   менялся); опции КАК У УСПЕШНОЙ ЛИНИИ (v3.9.8-clear ред.2, п.26):
//   Input Limit 28, Pterm Limit 18, Exhaustive OFF, DENSITY - НЕ IL 1/
//   PT 1/Exhaustive ON (класс-урок п.27!); если ERROR 891/892 - писать
//   на аудит (НЕ включать Exhaustive самовольно):
//   a) Successful, 0 ERROR; WARNING Cpld:897 <= 1-2 (класс D<7>);
//      WARNING:Xst:1780 БЫТЬ НЕ ДОЛЖНО (в RTL нет мёртвых
//      идентификаторов: sod_q/tx_pass/tx_q/cnt/x1_n/adv_q/tx_run
//      вычеркнуты);
//   b) adv_q/tx_run/sod_q/tx_pass/tx_q в .rpt НЕТ; TX = shreg[0]
//      (IO-MC P39, FDCPE с PRE по GSR-классу - SET-ветка, idle '1');
//      shreg - РОВНО 9 триггеров; bit_cnt - РОВНО 4 (idle = 0000);
//   c) GSR: «GSR : 1» (или fallback PT-сбросов от cpu_rst - класс
//      п.25, на разбор); D-функции логики БЕЗ литералов сырого RST
//      (п.21: RST - только во входах rst_meta); por_sh/por_run/
//      clk25_q/rst-цепь (rst_meta/rst_sync/rst_qcnt/rst_press/
//      reset_q) - ВНЕ GSR; ядро + FSM/шина - CLR/SET=cpu_rst;
//   d) КОЛЬЦО на месте (п.22/23 - БЕЗ ИЗМЕНЕНИЙ): r0..r6, двойной
//      kill, рестарт из 00 по NOR7, ДЕКОДОВ РАВЕНСТВА В УЗЛЕ НЕТ;
//      X1 = r0, X2 - OR/NOR-форма r1..r6 БЕЗ регистра в фазе (класс
//      п.10); clk25_q - РОВНО 1 T-триггер; x1_n в нетлисте НЕТ
//      (появился - собран исходник v3.9.7!); por_sh 8 бит Init=FF,
//      por_run.D = por_sh[0];
//   e) baud_cnt: D-функции БЕЗ декода терминального счёта (свободный
//      инкремент, wrap натуральный); строб загрузки - через регистр
//      ld_tx_q (1 МЦ, в .rpt есть); декод io_wr_tx свернут в ld_tx_q.D
//      (1 ПТ ~14 литералов); бит-таймы - bit_cnt 1..10 (декод ==10 -
//      в D bit_cnt, класс ядра - НЕ узел);
//   f) пины: TX P39 вых, SOD P72 вх (INP, наблюдатель), SID P73 вых,
//      RX P38 вх; PGND ровно 9 ({P74,P75,P76,P78,P79,P81,P95,P96,
//      P98}); clk -> GCK3, RST = P1;
//   g) ресурсы сверить с прогнозом п.31 (допуск +-2 МЦ / +-10 вх.ФБ);
//      Maximum Frequency: узел 50 МГц и логика 25 МГц - ОБЕ должны
//      закрыться;
//   h) литералы сброса в термах: rst_press/por_run как RESET (GSR-
//      класс); сырого RST в термах НЕТ (п.21).
// п.33 РЕЗЕРВ (-1 МЦ, НЕ ПРИМЕНЁН - только по команде владельца):
//   ld_tx_q -> одноразовость от !wr_seen (регистр базы: взводится
//   первым тиком !WRn в T2, снимается на WRn(вверх)) - строб загрузки
//   станет комбинационным (io_wr_tx свернётся в D-функции shreg, -1
//   МЦ); ЦЕНА: теряется тиковая фильтрация декода (класс bus_reg -
//   повторный сэмплинг базы и так живёт с сырым !WRn) и тик запаса на
//   прогретые данные A; применить, если фит скажет 109.
//
// Что делать владельцу (TODO, ред. v2.1):
//  1) в ISE-проекте УСТРОЙСТВО xc95108-15pq100c (как было); Set as Top
//     Module = ЭТОТ файл (top_txuart_por6_v21.v, CP1251); UCF - прежний
//     top_txuart.ucf (ноги НЕ менялись);
//  2) ОПЦИИ ФИТТЕРА СВЕРИТЬ С КОМПИЛЯТОРОМ: Input Limit 28, Pterm
//     Limit 18, Exhaustive OFF, Optimization DENSITY (в прогоне 11-8
//     7:14PM стояли IL 1 / PT 1 / Exhaustive ON - класс-урок п.27);
//     фит и .rpt НА АУДИТ ДО ПРОШИВКИ (чек-лист п.32). Обязательные
//     точки узла (v3.9.8-clear, БЕЗ ИЗМЕНЕНИЙ): ветка g_div2p5 -
//     r0..r6 (7 one-hot, двойной kill п.15, clk 50 МГц; INIT: r0=SET,
//     r1..r6=RESET); clk25_q - РОВНО 1 T-триггер (D = NOT clk25_q,
//     clk 50 МГц, Init=RESET) - такт ЛОГИКИ 25 МГц; x1_n/cnt в RTL
//     НЕТ (v3.9.8-clear); X1 = r0 (регистр r0 МОЖЕТ лечь в IO-MC
//     пина), X2 = r1 OR r2 OR r3 OR r4 OR r5 OR r6 (БЕЗ инверсии; X2
//     регистром В ФАЗЕ r0 - БРАК, не шить); ДЕКОДОВ РАВЕНСТВА В УЗЛЕ
//     БЫТЬ НЕ ДОЛЖНО (появились - собран исходник v3.9.2-3.9.6!);
//     wb_ram_q в нетлисте ОТСУТСТВУЕТ; por_sh - РОВНО 8 триггеров
//     (FTCPE, clk 50 МГц, Init=FF), строб r0, por_run.D = por_sh[0],
//     Init=SET; reset_q - FDCPE(clk25,'0','0') БЕЗ PRE; sod_q/
//     tx_pass/tx_q/adv_q/tx_run в нетлисте НЕТ; WARNING:Xst:1780 в
//     логе синтеза БЫТЬ НЕ ДОЛЖНО;
//  3) железо: H1 БЕЗ шунта (50 МГц на GCK3 - уже так после v3.9.8);
//     осциллограф: GCK3 = 50 МГц, X1 = 7,14 МГц (период ровно 140 нс,
//     high 20 / low 120 - duty 1/7), X2 = 7,14 ПРОТИВОФАЗА (если X2 в
//     фазе - БРАК фита, класс п.10), RESET_IN низ ~1,04 мкс по питанию
//     (8 стробов x 140 нс, п.23), CLKOUT = 3,57 МГц duty 50%;
//  4) терминал 1 562 500 8N1 (такт ядра clk25 25 МГц / 16), тест
//     OUT 04h / поллинг IN 05h; по результату - решение о переносе
//     механики в hwuart (v4.0.2) и/или в txclient (v9).
//"""

NEW_D = """  //=============================================================
  // TXUART v2.1 (п.27): ИСКЛЮЧИТЕЛЬНО АППАРАТНЫЙ ПЕРЕДАТЧИК UART
  // (директива владельца 11-8веч: 144 нет - остаёмся на XC95108;
  // механика v1.0 (txclient v8/hwuart v4.0.1) СЖАТА 20 -> 18 МЦ:
  // shreg 9 бит сам-idle + bit_cnt 4 (1..10, idle=0) + baud_cnt 4 +
  // ld_tx_q; adv_q и tx_run свернуты - п.31).
  // OUT 04h = TXDATA: старт кадра 8N1 1 562 500 бод (clk25 25 МГц / 2^4).
  // IN 05h = статус: бит A1 = TXRDY (tx_idle = ~|bit_cnt), остальные
  // биты 0 (позиция бита - совместимость с hwuart v4.0.x).
  //   shreg[8:0]    9 МЦ - {данные, выход}: [0] -> TX (IO-MC, INIT=1 -
  //                 idle '1' до всякого клока, SET-ветка GSR);
  //                 загрузка по ld_tx_q: {A[7:0], 1'b0} с живых A-пинов
  //                 (CPU держит данные до подъёма WRn - запас >= 20
  //                 тиков); сдвиги вправо с инжекцией '1' - после кадра
  //                 shreg САМ приходит в все-'1' (idle по построению,
  //                 как shreg 9'h1FF txclient; ПАРАЛЛЕЛЬНЫХ ЗАГРУЗОК
  //                 IDLE НЕТ; сдвиг idle-регистра - НЕТ-ОП);
  //   bit_cnt[3:0]  4 МЦ - 1..10 = НОМЕР БИТ-ТАЙМА кадра (1 = старт,
  //                 2..9 = данные, 10 = стоп), 0 = idle; busy =
  //                 |bit_cnt - 1 ПТ/NOR; на 10-м сдвиге сам в 0 -
  //                 tx_run v2.0 свернут (TXRDY = ~|bit_cnt, 1 ПТ;
  //                 гейт io_wr_tx - 4 inline-литерала в тот же ПТ);
  //   baud_cnt[3:0] 4 МЦ - mod-16 СВОБОДНЫМ ХОДОМ: D = bc+1, wrap
  //                 НАТУРАЛЬНЫЙ (1111->0000) - декода терминального
  //                 счёта и сбросовой логики в D-функциях счётчика НЕТ
  //                 («удобный для счетчиков делителей бод рейтинг» -
  //                 директива владельца); baud_tick = (bc==15) -
  //                 1 ПТ/4 вх - тик сдвига;
  //   ld_tx_q       1 МЦ - РЕГИСТРОВЫЙ СТРОБ загрузки (п.30 = п.29
  //                 v2.0, БЕЗ ИЗМЕНЕНИЙ): декод io_wr_tx имеет
  //                 ЕДИНСТВЕННОГО потребителя; D-функция бита shreg =
  //                 3 ПТ/~6 вх {ld_tx_q, A[k], baud_tick, shreg[k+1],
  //                 shreg[k]} - все 9 бит в ОДНОМ ФБ (~25 вх <= 36).
  // ВЫПИЛЕНО против v2.0 (-2 МЦ): adv_q (хелпер тика: jam baud_cnt <= 0
  //                 вместо <= 1 даёт первый сдвиг на ТОТ ЖЕ фронт - лаг
  //                 adv_q 1 такт скомпенсирован, урок v8/hwuart
  //                 пересчитан; дифсим: сетка кадров 1-в-1) и tx_run
  //                 (кодировка bit_cnt 1..10 с idle=0: busy = |bit_cnt
  //                 - 1 ПТ; GSR-ветка bit_cnt - CLR, как v2.0).
  // Итого ядро: 18 МЦ; минус TX-транзит v3.7 -3 => прогноз фита на
  // базе v3.9.8-clear (94 МЦ): 94 - 3 + 18 = 109 наивно, по прецеденту
  // v1.0 (-2) ожидание 105-108/108 XC95108 (п.31; резерв п.33).
  // ТАКТ ЯДРА - clk25 (такт ЛОГИКИ v3.9.8, п.23), НЕ сырой clk:
  // бод = 25/16 = ровно 1 562 500 - 2х-блокер фита v1.0 (ядро на clk
  // 50 МГц давало 3,125 М) снят ПО СТРОЕНИЮ, фикс v1.1 mod-32 не нужен.
  //=============================================================
  localparam [4:0] BAUD_DIV = 5'd16;  // clk25 25 МГц/16 = 1 562 500 бод 8N1 (CH340G до 2 Мбит, проверен на 1,92 М);
                                      // 5 бит - 16 не помещается в 4 (класс-урок: 4'd16 усёкся бы в 0);
                                      // степень двойки - wrap натуральный; альтернативы:
                                      // 8 -> 3 125 000 (вне диапазона CH340G), 32 -> 781 250,
                                      // 64 -> 390 625 (медленнее при том же ресурсе счётчика)
  reg [8:0]  shreg    = 9'h1FF;  // [8:1] данные, [0] -> TX (IO-MC P39; INIT=1: idle до всякого клока)
  reg [3:0]  bit_cnt  = 4'd0;    // 1..10 = бит-тайм кадра (1=старт..10=стоп), 0 = idle; busy = |bit_cnt
  reg [3:0]  baud_cnt = 4'd0;    // mod-16 свободным ходом, wrap натуральный; jam при загрузке
  reg        ld_tx_q = 1'b0;     // регистровый строб загрузки (п.30)
  wire baud_tick = (baud_cnt == (BAUD_DIV - 5'd1));            // == 15: тик каждые 16 тактов clk25
  wire tx_idle   = ~|bit_cnt;                                  // idle/TXRDY: 1 ПТ/4 вх (NOR) - inline в строб и статус
  // Старт кадра - ОДНОКРАТНЫЙ строб: первый тик !WRn в T2 записи порта 04h
  // (адрес защёлкнут в T1 - addr_latch стабилен, класс hwuart п.26).
  // Гейты: tx_idle && !ld_tx_q - повторные такты строба !WRn и запись при
  // busy БЛОКИРОВАНЫ (байт тихо отбрасывается, кадр не портится - контракт);
  // !por_run && !rst_press - шинные действия гейтятся ОБОИМИ источниками
  // сброса (класс п.21e; при GSR=cpu_rst FSM в окнах сброса и так в IDLE
  // - двойная страховка: floated-шина в окне POR/кнопки кадр не стартует)
  wire io_wr_tx = (state == S_T2) && !WRn && IOM
                  && addr_latch[2] && !addr_latch[1] && !addr_latch[0]  // порт 04h
                  && tx_idle && !ld_tx_q && !por_run && !rst_press;
  // Декод чтения статуса 05h - ЧИСТЫЙ (без state/!RDn - экономия литералов,
  // класс hwuart): статус живёт в A-драйве ниже (механизм KBROW, rd_drive)
  wire io_rd_st = IOM & addr_latch[2] & ~addr_latch[1] & addr_latch[0]; // чтение 05h
  always @(posedge clk25 or posedge cpu_rst) begin // п.27: асинхронный сброс ядра -> СЕТЬ GSR (cpu_rst = rst_press | por_run, п.20/21)
    if (cpu_rst) begin
      shreg    <= 9'h1FF;   // idle '1' (SET-ветка GSR)
      bit_cnt  <= 4'd0;     // idle (CLR-ветка - как v2.0)
      baud_cnt <= 4'd0;
      ld_tx_q  <= 1'b0;
    end else begin
      ld_tx_q  <= io_wr_tx;                    // строб загрузки - через регистр (п.30)
      baud_cnt <= baud_cnt + 4'd1;             // mod-16 СВОБОДНЫЙ ход: wrap натуральный,
                                               // декодов/сбросовой логики НЕТ (jam ниже перекрывает)
      if (ld_tx_q) begin
        // ЗАГРУЗКА (на тик позже строба io_wr_tx - п.30): байт с живых
        // A-пинов, старт-бит '0' на шине с этого такта; jam baud_cnt <= 0:
        // первый сдвиг ровно через 16 тиков - старт-бит РОВНО 16 тиков
        // (v2.0: jam 1 + лаг adv_q 1 такт = ТОТ ЖЕ фронт; дифсим v2.0
        // vs v2.1: сетка кадров 1-в-1); bit_cnt <= 1 (бит-тайм старта)
        shreg    <= {A, 1'b0};                 // [8:1] = данные (d7..d0), [0] = старт '0'
        bit_cnt  <= 4'd1;
        baud_cnt <= 4'd0;
      end else if (baud_tick) begin
        // ТИК СДВИГА (каждые 16 тактов clk25; в idle сдвиг - НЕТ-ОП,
        // регистр уже весь '1'): инжекция '1' в MSB - на 9-м сдвиге
        // стоп сам встанет в [0] (бит-тайм 10), после кадра shreg ==
        // все-'1' (idle) без отдельных загрузок
        shreg <= {1'b1, shreg[8:1]};
      end
      if (|bit_cnt && baud_tick) begin
        // бит-тайм кадра кончился (сдвиг был): 1..9 -> ++, 10 (стоп
        // отработал) -> 0 = idle, TXRDY поднимается в конце стопа (тот
        // же тик, что !tx_run v2.0). НА ГРУЗКЕ НЕ РАБОТАЕТ: bit_cnt
        // (старое значение) = 0 - строб io_wr_tx возможен только в idle
        bit_cnt <= (bit_cnt == 4'd10) ? 4'd0 : bit_cnt + 4'd1;
      end
    end
  end
"""

OLD_E = "                       : io_rd_st ? {6'b000000, ~tx_run, 1'b0}"
NEW_E = "                       : io_rd_st ? {6'b000000, tx_idle, 1'b0}"

OLD_F_CORE = """//     clk25_q - ВНЕ GSR; ЯДРО TXUART (shreg/bit_cnt/baud_cnt/tx_run/
//     adv_q/ld_tx_q) + FSM/шина - CLR/SET=cpu_rst (SET-ветка shreg ="""
NEW_F_CORE = """//     clk25_q - ВНЕ GSR; ЯДРО TXUART (shreg/bit_cnt/baud_cnt/ld_tx_q)
//     + FSM/шина - CLR/SET=cpu_rst (SET-ветка shreg ="""

OLD_G = """//  g) v2.0: УСТРОЙСТВО XC95144 - MC < 144; прогноз 111-113/144 (п.31:
//     94 базы - 3 транзит + 20 ядро + 1..2 $OpTx); на XC95108 НЕ
//     влезает (111 > 108) - если в проекте стоит 95108, фит упадёт по
//     ресурсам; Maximum Frequency: узел 50 МГц (кольцо/clk25_q/por_sh"""
NEW_G = """//  g) v2.1: УСТРОЙСТВО XC95108 - прогноз 105-108/108 МЦ (п.31: наивно
//     94 - 3 транзит + 18; прецедент v1.0: фит лёг на 2 МЦ ниже
//     наивной суммы); если фит сказал «needs N», N > 108 - НЕ крутить
//     опции (класс-урок п.27!), писать на аудит (резерв п.33);
//     Maximum Frequency: узел 50 МГц (кольцо/clk25_q/por_sh"""

OLD_H = """//       state = 3 триггера (без FFd4); txm_cnt НЕТ - вместо него
//              sod_q/tx_pass/tx_q (3 FF, декодов НЕТ; tx_q и sod_q -
//              в IO-MC пинов TX P39 и SOD P72, tx_pass - лог. МЦ);"""
NEW_H = """//       state = 3 триггера (без FFd4); txm_cnt/sod_q/tx_pass/tx_q/
//              tx_run/adv_q в нетлисте НЕТ (v2.1: свернуты/выпилены);
//       bit_cnt - 4 триггера (idle = 0000, кадр = 1..10; TXRDY =
//              NOR bit_cnt); shreg - 9 триггеров ([0] -> TX IO-MC P39,
//              1FF = idle);"""


def gen_rtl():
    text = read(V2_UTF8)
    lines = text.split("\n")

    # --- region A: титул (до строки v3.9.8-clear ред.2) ---
    iA = idx_of(lines, "// v3.9.8-clear ред.2 (2026-11-07)")
    assert lines[0].startswith("//===="), "шапка: нет открывающей линейки"
    assert lines[iA - 1].strip() == "//", "шапка: нет пустого // перед v3.9.8-clear"
    nA = iA - 1
    lines = lines[:1] + NEW_A.split("\n") + lines[nA:]

    # --- region B1: п.27-п.32 + TODO (до чек-листа .rpt) ---
    iB1 = idx_of(lines, "// TXUART v2.0 (п.27-п.32)")
    iB2 = idx_of(lines, "// -- ЧЕК-ЛИСТ .rpt ПОСЛЕ ФИТА")
    lines = lines[:iB1] + NEW_B1.split("\n") + lines[iB2:]

    body = "\n".join(lines)
    for old, new, tag in ((OLD_F_CORE, NEW_F_CORE, "чек-лист f)"),
                          (OLD_G, NEW_G, "чек-лист g)"),
                          (OLD_H, NEW_H, "чек-лист h)"),
                          (OLD_E, NEW_E, "статус-мультиплексор")):
        assert body.count(old) == 1, f"{tag}: якорь найден {body.count(old)} раз"
        body = body.replace(old, new)

    # --- region D: ядро TXUART (RTL) ---
    arr = body.split("\n")
    iD1 = idx_of(arr, "  // TXUART v2.0 (п.27): ИСКЛЮЧИТЕЛЬНО")
    assert arr[iD1 - 1].strip().startswith("//===="), "ядро: нет линейки сверху"
    iD2 = None
    for i in range(iD1, len(arr)):
        if arr[i].strip() == "// Шинный движок":
            iD2 = i
            break
    assert iD2 is not None, "ядро: не найден хвост (Шинный движок)"
    assert arr[iD2 - 1].strip().startswith("//===="), "ядро: нет линейки снизу"
    arr = arr[:iD1 - 1] + NEW_D.split("\n") + arr[iD2 - 1:]
    out = "\n".join(arr)

    # --- самопроверка генератора: мёртвых идентификаторов В КОДЕ НЕТ ---
    # (комментарии не считаются: исторические упоминания свернутых узлов
    #  в пояснениях v2.1 - легальны, класс-урок остаётся в шапке/п.27)
    mod = out.index("module retro_pcld_top")
    body_code = "\n".join(ln.split("//")[0] for ln in out[mod:].split("\n"))
    for bad in ("tx_run", "adv_q", "sod_q", "tx_pass", "tx_q", "wb_ram_q",
                "x1_n"):
        assert f" {bad}" not in body_code and f"({bad}" not in body_code, \
            f"в КОДЕ остался {bad}"
    write_utf8_cp1251(out, V21_UTF8, V21_CP)
    print(f"RTL v2.1: {len(out.splitlines())} строк -> {V21_UTF8} + CP1251 двойник")


# ---------------------------------------------------------------- SIM
SIM_EDITS = [
    ('"""sim_txuart_v2.py - цикл-точная модель top_txuart_por6_v2 (TXUART v2.0, beta/txuart).',
     '"""sim_txuart_v21.py - цикл-точная модель top_txuart_por6_v21 (TXUART v2.1, beta/txuart).'),
    ("  ядро TXUART v2.0 - mod-16 на clk25: БИТ = 16 x 40 нс = 640 нс",
     "  ядро TXUART v2.1 - mod-16 на clk25: БИТ = 16 x 40 нс = 640 нс\n"
     "  (v2.1: adv_q и tx_run свернуты - bit_cnt 1..10, idle = 0, busy =\n"
     "  |bit_cnt; jam baud_cnt <= 0; shreg 9 бит сам-idle - без изменений;"),
    ("Запуск: python3 scripts/sim_txuart_v2.py  (пути от папки скрипта)",
     "Запуск: python3 scripts/sim_txuart_v21.py  (пути от папки скрипта)"),
    ("""        # ядро TXUART v2.0 (GSR-домен, clk25)
        self.shreg = 0x1FF; self.bit_cnt = 0; self.baud_cnt = 0
        self.tx_run = 0; self.adv_q = 0; self.ld_tx_q = 0""",
     """        # ядро TXUART v2.1 (GSR-домен, clk25; tx_run/adv_q свернуты)
        self.shreg = 0x1FF; self.bit_cnt = 0; self.baud_cnt = 0
        self.ld_tx_q = 0"""),
    ("""                     not self.tx_run and not self.ld_tx_q and""",
     """                     self.bit_cnt == 0 and not self.ld_tx_q and"""),
    ("""    @property
    def adv(self):       return 1 if (self.baud_tick and self.tx_run) else 0
    @property""",
     """    @property"""),
    ("""                return (0 if self.tx_run else 2) & 0xFF   # {000000, TXRDY, 0}""",
     """                return (0 if self.bit_cnt else 2) & 0xFF  # {000000, TXRDY, 0}"""),
    ("""        self.shreg = 0x1FF; self.bit_cnt = 0; self.baud_cnt = 0
        self.tx_run = 0; self.adv_q = 0; self.ld_tx_q = 0

    # ---------- тик: posedge clk 50 МГц ----------""",
     """        self.shreg = 0x1FF; self.bit_cnt = 0; self.baud_cnt = 0
        self.ld_tx_q = 0

    # ---------- тик: posedge clk 50 МГц ----------"""),
    ("""        # --- ядро TXUART v2.0 (mod-16 на clk25) ---
        shreg = self.shreg; bit_cnt = self.bit_cnt; baud_cnt = self.baud_cnt
        tx_run = self.tx_run
        baud_cnt = (baud_cnt + 1) & 0xF          # НАТУРАЛЬНЫЙ wrap mod-16 (декодов НЕТ)
        if self.ld_tx_q:
            tx_run = 1
            shreg = ((self.A_in & 0xFF) << 1) & 0x1FF if self.A_in is not None else 0x1FE  # {A,1'b0}
            bit_cnt = 0; baud_cnt = 1            # jam: старт РОВНО 16 тактов clk25
        elif self.adv_q and self.tx_run:
            shreg = ((1 << 8) | (shreg >> 1)) & 0x1FF      # инжекция '1'
            if bit_cnt == 9:
                tx_run = 0; bit_cnt = 0          # кадр закрыт (стоп на шине)
            else:
                bit_cnt = bit_cnt + 1
        nxt['shreg'] = shreg; nxt['bit_cnt'] = bit_cnt; nxt['baud_cnt'] = baud_cnt
        nxt['tx_run'] = tx_run
        nxt['adv_q'] = self.adv
        nxt['ld_tx_q'] = self.io_wr_tx           # регистровый строб загрузки (п.29)""",
     """        # --- ядро TXUART v2.1 (mod-16 на clk25; tx_run/adv_q свернуты) ---
        shreg = self.shreg; bit_cnt = self.bit_cnt; baud_cnt = self.baud_cnt
        busy_old = (bit_cnt != 0)                # СТАРОЕ значение (NBA-семантика)
        baud_cnt = (baud_cnt + 1) & 0xF          # НАТУРАЛЬНЫЙ wrap mod-16 (декодов НЕТ)
        if self.ld_tx_q:
            shreg = ((self.A_in & 0xFF) << 1) & 0x1FF if self.A_in is not None else 0x1FE  # {A,1'b0}
            bit_cnt = 1; baud_cnt = 0            # jam 0: старт РОВНО 16 тактов clk25 (1..10 = бит-таймы)
        else:
            if self.baud_tick:
                shreg = ((1 << 8) | (shreg >> 1)) & 0x1FF  # инжекция '1' (в idle - НЕТ-ОП)
            if busy_old and self.baud_tick:
                bit_cnt = 0 if bit_cnt == 10 else bit_cnt + 1  # 10-й сдвиг - кадр закрыт (TXRDY)
        nxt['shreg'] = shreg; nxt['bit_cnt'] = bit_cnt; nxt['baud_cnt'] = baud_cnt
        nxt['ld_tx_q'] = self.io_wr_tx           # регистровый строб загрузки (п.30)"""),
    # ---- сценарии ----
    ('    s.chk(d.tx_run == 0 and d.ld_tx_q == 0, "С1: ядро в idle")',
     '    s.chk(d.bit_cnt == 0 and d.ld_tx_q == 0, "С1: ядро в idle")'),
    ("        s.chk(d.shreg == 0x1FF and d.tx_run == 0,\n"
     '              f"С2({byte:#04x}): shreg сам в idle 1FF, tx_run=0")',
     "        s.chk(d.shreg == 0x1FF and d.bit_cnt == 0,\n"
     '              f"С2({byte:#04x}): shreg сам в idle 1FF, bit_cnt=0")'),
    ('    s.chk(d.tx_run == 1, "С4: передача активна")',
     '    s.chk(d.bit_cnt != 0, "С4: передача активна")'),
    ('    s.chk(d.tx_run == 1, "С4: передача НЕ перезапущена (строб задавлен !tx_run)")',
     '    s.chk(d.bit_cnt != 0, "С4: передача НЕ перезапущена (строб задавлен tx_idle=0)")'),
    ('    s.chk(d.tx_run == 0 and d.shreg == 0x1FF, f"С5: чтение 04h (не определено, = {v:#04x}) не трогает ядро")',
     '    s.chk(d.bit_cnt == 0 and d.shreg == 0x1FF, f"С5: чтение 04h (не определено, = {v:#04x}) не трогает ядро")'),
    ("    s.chk(d.tx_run == 0 and d.ld_tx_q == 0 and d.shreg == 0x1FF,\n"
     '          "С6: OUT 04h в окне POR - кадр НЕ стартовал (мусор floated-шины отброшен)")',
     "    s.chk(d.bit_cnt == 0 and d.ld_tx_q == 0 and d.shreg == 0x1FF,\n"
     '          "С6: OUT 04h в окне POR - кадр НЕ стартовал (мусор floated-шины отброшен)")'),
    ('    s.chk(d.tx_run == 1, "С7: кадр TX идёт")',
     '    s.chk(d.bit_cnt != 0, "С7: кадр TX идёт")'),
    ("    s.chk(d.tx_run == 0 and d.shreg == 0x1FF and d.bit_cnt == 0 and\n"
     "          d.baud_cnt == 0 and d.ld_tx_q == 0,\n"
     '          "С7: ядро вычищено (tx_run=0, shreg=1FF, счётчики 0)")',
     "    s.chk(d.shreg == 0x1FF and d.bit_cnt == 0 and\n"
     "          d.baud_cnt == 0 and d.ld_tx_q == 0,\n"
     '          "С7: ядро вычищено (bit_cnt=0, shreg=1FF, счётчики 0)")'),
    ('    s.chk(d.TX == 1 and d.tx_run == 0, "С7: после сброса idle")',
     '    s.chk(d.TX == 1 and d.bit_cnt == 0, "С7: после сброса idle")'),
    ('    s.chk(d.shreg == 0x1FF and d.tx_run == 0, "С7: ядро снова в idle")',
     '    s.chk(d.shreg == 0x1FF and d.bit_cnt == 0, "С7: ядро снова в idle")'),
    ("    s.chk(d.ld_tx_q == 0 and d.tx_run == 0 and d.TX == 1,\n"
     '          "С8: ALE-глюк до данных - кадр НЕ стартовал (строб требует T2 && !WRn)")',
     "    s.chk(d.ld_tx_q == 0 and d.bit_cnt == 0 and d.TX == 1,\n"
     '          "С8: ALE-глюк до данных - кадр НЕ стартовал (строб требует T2 && !WRn)")'),
    ('    s.chk(d.tx_run == 0 and d.ld_tx_q == 0, "С9: запись ОЗУ не стартует кадр")',
     '    s.chk(d.bit_cnt == 0 and d.ld_tx_q == 0, "С9: запись ОЗУ не стартует кадр")'),
]


def gen_sim():
    text = read(SIM_V2)
    for old, new in SIM_EDITS:
        n = text.count(old)
        assert n == 1, f"SIM-якорь найден {n} раз: {old[:60]!r}..."
        text = text.replace(old, new)
    # код сим-модели без докстрингов и #-комментариев: мёртвых
    # идентификаторов быть не должно (исторические упоминания в доке -
    # легальны, класс-урок остаётся в шапке)
    import re as _re
    no_doc = _re.sub(r'"""[\s\S]*?"""', '""', text)
    sim_code = "\n".join(ln.split("#")[0] for ln in no_doc.split("\n"))
    assert "tx_run" not in sim_code, "sim: остался tx_run в коде"
    assert "adv_q" not in sim_code, "sim: остался adv_q в коде"
    with open(SIM_V21, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"SIM v2.1: {len(text.splitlines())} строк -> {SIM_V21}")


if __name__ == "__main__":
    gen_rtl()
    gen_sim()
    print("gen_v21: OK")
