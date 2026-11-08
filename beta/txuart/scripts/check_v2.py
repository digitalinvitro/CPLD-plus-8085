#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_v2.py - верификатор top_txuart_por6_v2 (TXUART v2.0, beta/txuart).

Проверки:
  1. Кодировка: CP1251-оригинал декодируется строго; _utf8-двойник ==
     декодированному CP1251 байт-в-байт (синхронность двойников).
  2. Обязательные фразы шапки (титул v2.0 на базе v3.9.8-clear,
     п.27-п.32, XC95144, чек-лист, TODO ред. v2.0).
  3. Мёртвые идентификаторы ОТСУТСТВУЮТ в коде (без комментариев):
     транзит sod_q/tx_pass/tx_q + legacy-узел cnt/x1_n/x1_q/x2_q/x1_p/
     x2_p/t0_q - точка приёмки Xst:1780 (класс v398_clear ред.2).
     cpu_rst ЖИВ (GSR-источник п.20) - в мёртвых НЕ числится.
  4. База (v3.9.8-clear) БИТ-В-БИТ: кольцо r0..r6 (двойной kill,
     рестарт NOR7), clk25_q, X1 = r0, X2 = OR(r1..r6), por_ce = r0,
     por_sh 8 бит, харденинг сброса п.21, FSM, декоды памяти, KBROW,
     SID = RX, RESET_IN = reset_q - контрольные строки ДОСЛОВНО.
  5. Структура ядра TXUART (на clk25/cpu_rst): BAUD_DIV=5'd16; натуральный
     wrap (инкремент БЕЗ декода); jam <= 1; однократный io_wr_tx
     (!tx_run && !ld_tx_q && !por_run && !rst_press); загрузка {A,1'b0};
     инжекция '1'; закрытие bit_cnt==9; io_rd_st (05h); статус
     {6'b000000, ~tx_run, 1'b0}; TX = shreg[0]; SET-ветка shreg.
  6. Порядок объявлений (HDLCompilers:28): ядро после объявлений FSM
     (state/addr_latch), до «Шинный движок»; io_rd_st до A-драйва.
  7. Хвост: endmodule без завершающего перевода строки - как у базы.

Запуск: python3 scripts/check_v2.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ  = os.path.dirname(HERE)
CP   = os.path.join(PRJ, "top_txuart_por6_v2.v")
UTF8 = os.path.join(PRJ, "top_txuart_por6_v2_utf8.v")
BASE = os.path.normpath(os.path.join(PRJ, "..", "lowsize", "top_suart_por6_v398_clear_utf8.v"))

fails, checks = [], 0

def chk(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)

def strip_comments(text):
    out = []
    for line in text.split("\n"):
        i = line.find("//")
        out.append(line[:i] if i >= 0 else line)
    return "\n".join(out)

# ---- 1. кодировка и двойники
cp_bytes = open(CP, "rb").read()
utf8_text = open(UTF8, encoding="utf-8").read()
try:
    decoded = cp_bytes.decode("cp1251")
except UnicodeDecodeError as e:
    decoded = None
    fails.append(f"CP1251: файл не декодируется строго ({e})")
chk(decoded == utf8_text, "CP1251 round-trip: декодированный != _utf8-двойнику (двойники разсинхронизированы)")
base_text = open(BASE, encoding="utf-8").read()

# ---- 2. шапка
for phrase in [
    "top_txuart.v v2.0",
    "ИСКЛЮЧИТЕЛЬНО АППАРАТНЫЙ",
    "ПЕРЕДАТЧИК UART 8N1 1 562 500 бод",
    "БАЗА = lowsize v3.9.8-clear ред.2",
    "директива владельца 11-8веч",
    "дизайн beta\\lowsize 398_clear и переделываем txuart на основе него»",
    "кольцо ВЕРНУЛОСЬ в нетлист",
    "ЦЕЛЬ - XC95144-",
    "XC95144-15PQ100C",
    "TXUART v2.0 (п.27-п.32)",
    "п.27 СПЕКА",
    "п.28 СБРОС/ДОМЕНЫ v2.0",
    "п.29 РЕГИСТРОВЫЙ СТРОБ ЗАГРУЗКИ ld_tx_q",
    "п.30 ТАЙМИНГ КАДРА",
    "п.31 БЮДЖЕТ/ПРОГНОЗ ФИТА",
    "п.32 ЧЕК-ЛИСТ ФИТА",
    "фикс v1.1 mod-32 НЕ НУЖЕН",
    "такт ядра - clk25",
    "WARNING:Xst:1780 БЫТЬ НЕ ДОЛЖНО",
    "Что делать владельцу (TODO, ред. v2.0)",
    "СМЕНИТЬ УСТРОЙСТВО на xc95144-15pq100c",
    "терминал 1 562 500 8N1",
]:
    chk(phrase in utf8_text, f"шапка: нет фразы <{phrase[:60]}>")

code = strip_comments(utf8_text)

# ---- 3. мёртвые идентификаторы в КОДЕ отсутствуют
for dead in ["sod_q", "tx_pass", "tx_q",
             "cnt", "x1_n", "x1_q", "x2_q", "x1_p", "x2_p", "t0_q"]:
    chk(not re.search(rf"\b{re.escape(dead)}\b", code),
        f"код: мёртвый идентификатор <{dead}> присутствует (точка приёмки Xst:1780)")
chk(re.search(r"\bcpu_rst\b", code) is not None,
    "код: cpu_rst ДОЛЖЕН быть жив (GSR-источник п.20, бит-в-бит базы)")
# порт SOD жив (наблюдатель, keep)
chk(re.search(r'\(\* keep = "TRUE" \*\) input wire SOD,', utf8_text) is not None,
    "порт SOD: нет входа-наблюдателя с keep")
chk("SOD" in utf8_text[:9000], "порт SOD: объявление не найдено в зоне портов")

# ---- 4. база БИТ-В-БИТ (кольцо/POR/сброс/FSM)
base_facts = [
    # кольцо (п.15/22 - двойной kill, рестарт из 00 по NOR7)
    ("if (CLK_DIV == 2 && CLK_HALF == 1) begin : g_div2p5", "ветка g_div2p5"),
    ("r0 <= (r6 & ~r0 & ~r1 & ~r2) | (~r0 & ~r1 & ~r2 & ~r3 & ~r4 & ~r5 & ~r6);", "r0: двойной kill + рестарт NOR7"),
    ("r1 <= r0 & ~r1 & ~r2 & ~r3;", "r1.D"),
    ("r2 <= r1 & ~r2 & ~r3 & ~r4;", "r2.D"),
    ("r3 <= r2 & ~r3 & ~r4 & ~r5;", "r3.D"),
    ("r4 <= r3 & ~r4 & ~r5 & ~r6;", "r4.D"),
    ("r5 <= r4 & ~r5 & ~r6 & ~r0;", "r5.D"),
    ("r6 <= r5 & ~r6 & ~r0 & ~r1;", "r6.D"),
    ("reg  r0 = 1'b1;", "INIT r0=SET (состояние 0)"),
    ("reg  r1 = 1'b0;", "INIT r1=RESET"),
    ("reg  r6 = 1'b0;", "INIT r6=RESET"),
    ("clk25_q <= ~clk25_q;", "clk25_q T-триггер /2"),
    ("reg  clk25_q = 1'b0;", "INIT clk25_q=0 (фаза фиксирована)"),
    ("assign clk25 = clk25_q;", "clk25 = такт логики"),
    ("assign X1 = r0;", "X1 = r0 (7,143 МГц, duty 1/7)"),
    ("assign X2 = r1 | r2 | r3 | r4 | r5 | r6;", "X2 = OR(r1..r6) = ~r0"),
    ("assign por_ce = r0;", "por_ce = r0 (строб 1/140 нс, 50-домен)"),
    # POR (50-домен, без декодов)
    ("reg [7:0] por_sh = 8'hFF;", "por_sh 8 бит Init=FF"),
    ("reg  por_run = 1'b1;", "por_run Init=SET"),
    ("por_run <= por_sh[0];", "por_run.D = por_sh[0]"),
    ("if (por_ce) por_sh <= {1'b0, por_sh[7:1]};", "сдвиг por_sh по стробу r0"),
    # харденинг сброса (п.21 - бит-в-бит)
    ("reg  rst_meta  = 1'b0;", "rst_meta"),
    ("reg  rst_sync  = 1'b0;", "rst_sync"),
    ("reg  rst_press = 1'b0;", "rst_press"),
    ("reg [2:0] rst_qcnt = 3'b000;", "rst_qcnt"),
    ("wire cpu_rst = rst_press | por_run;", "cpu_rst = rst_press | por_run"),
    ("reg  reset_q = 1'b0;", "reset_q INIT=0"),
    ("rst_meta <= RST;", "RST только в синхронизатор"),
    ("rst_sync <= rst_meta;", "2FF-синхронизатор"),
    ("if (rst_sync != rst_press) begin", "квалификатор"),
    ("if (&rst_qcnt) begin", "8 тактов подряд"),
    ("rst_press <= rst_sync;", "переворот состояния"),
    ("reset_q <= ~cpu_rst;", "reset_q = регистр RESET_IN"),
    ("assign RESET_IN = reset_q;", "RESET_IN = reset_q (регистр)"),
    # FSM/шина (бит-в-бит)
    ("localparam S_IDLE = 3'd0,", "FSM localparams"),
    ("reg  [2:0] state  = S_IDLE;", "state 3 триггера"),
    ("reg [7:0] addr_latch = 8'h00;", "addr_latch"),
    ("reg [7:0] bus_reg    = 8'h00;", "bus_reg"),
    ("wire io_rd_kb = IOM & ~addr_latch[2] & addr_latch[1] & addr_latch[0];", "KBROW 03h"),
    ("wire rd_drive = (state == S_T2) && rd_seen && !RDn && !ALE;", "rd_drive"),
    ("state <= (!IOM && A15 && !por_run && !rst_press) ? S_WB1 : S_IDLE;", "гейт POR/кнопки в WB (п.21)"),
    ("assign CSr_n = A15 | IOM;", "CSr_n"),
    ("assign CS_n  = in_wb ? 1'b0 : (!A15 | IOM);", "CS_n от FSM (п.16)"),
    ("assign OEr_n = CSr_n | wr_phase;", "OEr_n"),
    ("assign OE_n  = CS_n  | wr_phase;", "OE_n"),
    ("assign WE_n  = !in_welo;", "WE_n"),
    ("assign CS1   = 1'b1;", "CS1 = '1'"),
    ("assign READY = 1'b1;", "READY"),
    ("assign SID = RX;", "SID = RX транзит"),
    ("assign seg = ~seg_q;", "seg инверсия"),
    ("assign col0 = kbcol_q[0];", "колонки"),
]
# строки с комментариями ищем в ПОЛНОМ тексте (не в strip_comments)
for frag, what in [
    ("wire io_rd_kb = IOM & ~addr_latch[2] & addr_latch[1] & addr_latch[0]; // чтение 03h (KBROW)", "KBROW 03h (строка с комментарием)"),
    ("always @(posedge clk25 or posedge cpu_rst) begin // v3.9.6: сброс логики по cpu_rst = rst_press|por_run (регистры, п.21; асинхронная структура GSR п.18/20 сохранена); v3.9.8: такт логики clk25 (п.23)", "FSM: такт clk25, GSR=cpu_rst (бит-в-бит базы)"),
]:
    chk(frag in utf8_text, f"база: нет контрольной строки <{what}>")
chk(code.count("always @(posedge clk25 or posedge cpu_rst) begin") >= 2,
    "такт clk25 + GSR: должно быть >= 2 always-блока (FSM + ядро TXUART)")
for frag, what in base_facts:
    chk(frag in code, f"база: нет контрольной строки <{what}> (база должна быть бит-в-бит)")

# ---- 5. структура ядра TXUART (на clk25/cpu_rst)
core_facts = [
    ("localparam [4:0] BAUD_DIV = 5'd16;", "BAUD_DIV 16 (5 бит - 16 в 4 не помещается)"),
    ("reg [8:0] shreg    = 9'h1FF;", "shreg 9 бит INIT=1FF"),
    ("reg [3:0] bit_cnt  = 4'd0;", "bit_cnt 4 бит"),
    ("reg [3:0] baud_cnt = 4'd0;", "baud_cnt 4 бит"),
    ("reg  tx_run  = 1'b0;", "tx_run"),
    ("reg  adv_q   = 1'b0;", "adv_q"),
    ("reg  ld_tx_q = 1'b0;", "ld_tx_q"),
    ("wire baud_tick = (baud_cnt == (BAUD_DIV - 5'd1));", "baud_tick == 15"),
    ("wire adv = baud_tick && tx_run;", "adv"),
    ("wire io_wr_tx = (state == S_T2) && !WRn && IOM", "io_wr_tx - строб T2/!WRn/IOM"),
    ("&& addr_latch[2] && !addr_latch[1] && !addr_latch[0]", "декод порта 04h"),
    ("&& !tx_run && !ld_tx_q && !por_run && !rst_press;", "гейты !tx_run/!ld_tx_q/!por_run/!rst_press"),
    ("wire io_rd_st = IOM & addr_latch[2] & ~addr_latch[1] & addr_latch[0];", "io_rd_st 05h"),

    ("      ld_tx_q  <= io_wr_tx;", "регистровый строб ld_tx_q <= io_wr_tx"),
    ("      baud_cnt <= baud_cnt + 4'd1;", "НАТУРАЛЬНЫЙ wrap счётчика (инкремент без декода)"),
    ("        tx_run   <= 1'b1;", "tx_run <= 1 в загрузке"),
    ("        shreg    <= {A, 1'b0};", "загрузка {A, старт 0}"),
    ("        bit_cnt  <= 4'd0;", "bit_cnt <= 0 в загрузке"),
    ("        baud_cnt <= 4'd1;", "jam baud_cnt <= 1"),
    ("      end else if (adv_q && tx_run) begin", "тик сдвига по adv_q && tx_run"),
    ("        shreg <= {1'b1, shreg[8:1]};", "инжекция '1'"),
    ("        if (bit_cnt == 4'd9) begin", "закрытие кадра на bc==9"),
    ("          tx_run  <= 1'b0;", "tx_run <= 0 (конец кадра)"),
    (": io_rd_st ? {6'b000000, ~tx_run, 1'b0}", "статус-байт {000000,TXRDY,0}"),
    ("  assign TX  = shreg[0];", "TX = shreg[0]"),
]
for frag, what in core_facts:
    chk(frag in code, f"ядро: нет <{what}>")

for frag, what in [
    ("always @(posedge clk25 or posedge cpu_rst) begin // п.27: асинхронный сброс ядра -> СЕТЬ GSR (cpu_rst = rst_press | por_run, п.20/21)", "GSR-домен ядра (clk25/cpu_rst, строка с комментарием)"),
    ("shreg    <= 9'h1FF;   // idle '1' (SET-ветка GSR)", "SET-ветка shreg"),
    ('// synthesis attribute fsm_encoding of state is "compact"', "прагма FSM Task 46"),
    ("TX-транзит v3.7 (sod_q/tx_pass/tx_q) ВЫПИЛЕН (п.27, v2.0)", "надгробие транзита"),
]:
    chk(frag in utf8_text, f"комментарий: нет <{what}>")

# ---- 6. порядок объявлений (HDLCompilers:28)
i_state  = code.index("reg  [2:0] state  = S_IDLE;")
i_core   = code.index("localparam [4:0] BAUD_DIV = 5'd16;")
i_engine = utf8_text.index("// Шинный движок")
i_ardrv  = utf8_text.index("assign A = rd_drive ?")
chk(i_state < i_core, "порядок: ядро TXUART стоит ДО объявлений state (HDLCompilers:28)")
chk(i_core < utf8_text.index("always @(posedge clk25 or posedge cpu_rst) begin // v3.9.6: сброс логики"),
    "порядок: ядро TXUART стоит ПОСЛЕ объявлений FSM, но ДО шинного движка")
i_core_end = utf8_text.index("end\n\n  //=============================================================\n  // Шинный движок")
chk(i_core < i_core_end < i_ardrv, "порядок: ядро < движок < A-драйв (io_rd_st объявлен раньше использования)")

# ---- 7. хвост
chk(utf8_text.endswith("endmodule"), "хвост: файл должен кончаться endmodule без \\n (как база)")

# ---- 8. дельта от базы: в НОВЫХ СТРОКАХ КОДА (без комментариев) мёртвых
# идентификаторов быть не должно (в комментариях-надгробиях упоминания
# sod_q/tx_pass/tx_q ДОПУСТИМЫ - это история, не код)
base_lines = set(base_text.splitlines())
new_lines = [l for l in utf8_text.splitlines() if l not in base_lines]
new_code = strip_comments("\n".join(new_lines))
for dead in ["tx_pass", "tx_q", "sod_q", "x1_n", "t0_q", "cnt"]:
    chk(not re.search(rf"\b{re.escape(dead)}\b", new_code),
        f"дельта от базы: мёртвый идентификатор <{dead}> в новом КОДЕ")

print(f"check_v2: {checks - len(fails)}/{checks} ПАСС")
if fails:
    print("Провалы:")
    for m in fails:
        print(f"  FAIL: {m}")
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПАСС")
