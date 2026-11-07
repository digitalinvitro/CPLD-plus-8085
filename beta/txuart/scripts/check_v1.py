#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_v1.py - верификатор top_txuart_por6_v1 (TXUART v1.0, beta/txuart).

Проверки:
  1. Кодировка: CP1251-оригинал декодируется строго; _utf8-двойник ==
     декодированному CP1251 байт-в-байт (синхронность двойников).
  2. Обязательные фразы шапки (титул TXUART v1.0, п.26-п.31, чек-лист).
  3. Мёртвые идентификаторы выпиленного транзита ОТСУТСТВУЮТ В КОДЕ
     (без комментариев): sod_q/tx_pass/tx_q/cpu_rst - точка приёмки
     Xst:1780 (класс v398_clear ред.2). Порт SOD при этом ЕСТЬ
     (вход-наблюдатель с keep).
  4. Структура ядра TXUART: BAUD_DIV=5'd16; натуральный wrap счётчика
     (инкремент БЕЗ декода терминального счёта); jam <= 1 в ветке
     ld_tx_q; однократный io_wr_tx (!tx_run && !ld_tx_q && !por_run);
     загрузка {A,1'b0}; инжекция '1'; закрытие кадра bit_cnt==9;
     io_rd_st (05h); статус {6'b000000, ~tx_run, 1'b0}; TX = shreg[0];
     GSR (posedge clk or posedge RST) + SET-ветка shreg.
  5. База бит-в-бит: контрольные строки v3.9.3 (делитель mod-7, POR
     8 бит, строб (cnt==1)|(cnt==6), FSM, декоды памяти, KBROW,
     SID = RX) присутствуют ДОСЛОВНО.
  6. Порядок объявлений (HDLCompilers:28): ядро после объявлений FSM
     (state/addr_latch), до «Шинный движок»; io_rd_st до A-драйва.
  7. Хвост: endmodule без завершающего перевода строки - как у базы.

Запуск: python3 scripts/check_v1.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ  = os.path.dirname(HERE)
CP   = os.path.join(PRJ, "top_txuart_por6_v1.v")
UTF8 = os.path.join(PRJ, "top_txuart_por6_v1_utf8.v")
BASE = os.path.normpath(os.path.join(PRJ, "..", "lowsize", "top_suart_por6_v393_utf8.v"))

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
    "top_txuart.v v1.0",
    "ИСКЛЮЧИТЕЛЬНО АППАРАТНЫЙ ПЕРЕДАТЧИК UART 8N1 1 562 500 бод",
    "директива владельца 11-8",
    "Хорошо давай попробуем организовать",
    "TXUART v1.0 (п.26-п.31)",
    "п.26 СПЕКА",
    "п.27 SOD (P72)",
    "п.28 РЕГИСТРОВЫЙ СТРОБ ЗАГРУЗКИ ld_tx_q",
    "п.29 ТАЙМИНГ КАДРА",
    "п.30 БЮДЖЕТ/ПРОГНОЗ ФИТА",
    "п.31 ЧЕК-ЛИСТ ФИТА",
    "ЧЕК-ЛИСТ ФИТА (владельцу, после прогона ISE",
    "WARNING:Xst:1780 БЫТЬ НЕ ДОЛЖНО",
    "TODO: 1) фит владельца в ISE",
]:
    chk(phrase in utf8_text, f"шапка: нет фразы <{phrase[:60]}>")

code = strip_comments(utf8_text)

# ---- 3. мёртвые идентификаторы транзита в КОДЕ отсутствуют
for dead in ["sod_q", "tx_pass", "tx_q", "cpu_rst"]:
    chk(not re.search(rf"\b{re.escape(dead)}\b", code),
        f"код: мёртвый идентификатор <{dead}> присутствует (точка приёмки Xst:1780)")
# порт SOD жив (наблюдатель, keep)
chk(re.search(r'\(\* keep = "TRUE" \*\) input wire SOD,', utf8_text) is not None,
    "порт SOD: нет входа-наблюдателя с keep")
chk("SOD" in utf8_text.split("endmodule")[0].split("input")[0] or "SOD" in utf8_text[:9000],
    "порт SOD: объявление не найдено в зоне портов")

# ---- 4. структура ядра
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
    ("&& !tx_run && !ld_tx_q && !por_run;", "гейты !tx_run/!ld_tx_q/!por_run"),
    ("wire io_rd_st = IOM & addr_latch[2] & ~addr_latch[1] & addr_latch[0];", "io_rd_st 05h"),
    ("always @(posedge clk or posedge RST) begin", "GSR-домен ядра (posedge RST)"),
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
    ("  assign SID = RX;", "SID = RX транзит"),
    ("  assign RESET_IN = ~(RST | por_run);", "RESET_IN (cpu_rst развёрнут на месте)"),
]
for frag, what in core_facts:
    chk(frag in code, f"ядро: нет <{what}>")

for frag, what in [
    ("shreg    <= 9'h1FF;   // idle '1' (SET-ветка GSR)", "SET-ветка shreg"),
    ("wire io_rd_kb = IOM & ~addr_latch[2] & addr_latch[1] & addr_latch[0]; // чтение 03h (KBROW)", "KBROW 03h (строка с комментарием)"),
    ("// synthesis attribute fsm_encoding of state is \"compact\"", "прагма FSM Task 46"),
    ("always @(posedge clk or posedge RST) begin // п.26: асинхронный сброс ядра -> СЕТЬ GSR", "пометка GSR-домена ядра"),
]:
    chk(frag in utf8_text, f"шапка/комментарий: нет <{what}>")
base_facts = [
    ("if (cnt == 3'd6) cnt <= 3'd0;", "делитель mod-7 wrap"),
    ("always @(negedge clk)", "x1_n NEGEDGE"),
    ("assign X1 = (cnt != 3'd0) ^ x1_n;", "X1"),
    ("assign X2 = (cnt == 3'd0) ^ x1_n;", "X2"),
    ("assign por_ce = (cnt == 3'd1) | (cnt == 3'd6);", "строб POR фазы r1|r6"),
    ("reg [7:0] por_sh = 8'hFF;", "por_sh 8 бит Init=FF (БЕЗ М1)"),
    ("if (por_ce) por_sh <= {1'b0, por_sh[7:1]};", "сдвиг por_sh 8 бит"),
    ("localparam S_IDLE = 3'd0,", "FSM localparams"),
    ("reg  [2:0] state  = S_IDLE;", "state 3 триггера"),
    ("reg [7:0] addr_latch = 8'h00;", "addr_latch"),
    ("wire io_rd_kb = IOM & ~addr_latch[2] & addr_latch[1] & addr_latch[0];", "KBROW 03h"),
    ("wire rd_drive = (state == S_T2) && rd_seen && !RDn && !ALE;", "rd_drive"),
    ("state <= (!IOM && A15 && !por_run) ? S_WB1 : S_IDLE;", "гейт POR в WB"),
    ("assign CSr_n = A15 | IOM;", "CSr_n"),
    ("assign CS_n  = in_wb ? 1'b0 : (!A15 | IOM);", "CS_n от FSM"),
    ("assign WE_n  = !in_welo;", "WE_n"),
    ("assign READY = 1'b1;", "READY"),
    ("assign seg = ~seg_q;", "seg инверсия"),
    ("assign col0 = kbcol_q[0];", "колонки"),
]
for frag, what in base_facts:
    chk(frag in code, f"база: нет контрольной строки <{what}> (база должна быть бит-в-бит)")

# ---- 6. порядок объявлений (HDLCompilers:28)
i_state  = code.index("reg  [2:0] state  = S_IDLE;")
i_core   = code.index("localparam [4:0] BAUD_DIV = 5'd16;")
i_engine = utf8_text.index("// Шинный движок")
i_ardrv  = utf8_text.index("assign A = rd_drive ?")
chk(i_state < i_core, "порядок: ядро TXUART стоит ДО объявлений state (HDLCompilers:28)")
chk(i_core < utf8_text.index("always @(posedge clk or posedge RST) begin // v3.9.3: асинхронный сброс логики"),
    "порядок: ядро TXUART стоит ПОСЛЕ объявлений FSM, но ДО шинного движка")
i_core_end = utf8_text.index("end\n\n  //=============================================================\n  // Шинный движок")
chk(i_core < i_core_end < i_ardrv, "порядок: ядро < движок < A-драйв (io_rd_st объявлен раньше использования)")

# ---- 7. хвост
chk(utf8_text.endswith("endmodule"), "хвост: файл должен кончаться endmodule без \\n (как база)")

print(f"check_v1: {checks - len(fails)}/{checks} ПАСС")
if fails:
    print("Провалы:")
    for m in fails:
        print(f"  FAIL: {m}")
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПАСС")
