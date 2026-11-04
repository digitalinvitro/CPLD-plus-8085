# -*- coding: utf-8 -*-
"""
fix_v400_decl_order.py (2026-11-04)
Исправление порядка объявлений в top_hwuart_por6_v400.v после ошибок ISE
HDLCompilers:28 ('state'/'S_T2'/'addr_latch' has not been declared, строки
985-989): блок ОБЪЯВЛЕНИЙ автомата шины (localparam S_IDLE..S_WB4, state,
rd_seen/wr_seen, addr_latch/bus_reg, seg_q/dig_q/snd_q/kbcol_q, io_rd_kb)
стоит в файле НИЖЕ ядра UART, а декоды io_wr_tx/io_rd_rx/io_rd_st в ядре
ссылаются на state/S_T2/addr_latch. ISE (Verilog-2001 front-end) требует
объявления ДО использования.

Правка: блок объявлений автомата ПЕРЕНОСИТСЯ вверх - сразу после POR-блока,
перед секцией UART (п.26). Комбинационные провода (in_wb..rd_drive) остаются
в блоке - их зависимости (state, rd_seen) при переносе оказываются выше.
Порядок становится: POR -> объявления автомата -> ядро UART -> шинный движок.

Синхронно правится UTF8-двойник (перегенерация из CP1251).
Запуск из каталога beta/hwuart:  python3 scripts/fix_v400_decl_order.py
"""
import io, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(HERE, "top_hwuart_por6_v400.v")     # CP1251 (эталон ISE)
TWIN = os.path.join(HERE, "top_hwuart_por6_v400_utf8.v") # UTF8-двойник

MARK_HIST   = "// ИСТОРИЯ БЛОКА (v4.0.0)"          # начало секции UART (вставка ПЕРЕД её рамкой)
MARK_AUTO   = "// Автомат шины: 7 состояний"       # заголовок переносимого блока
MARK_RDD    = "wire rd_drive = (state == S_T2)"    # последняя строка переносимого блока
MARK_ALE    = "  // от ALE)"                       # после неё - пояснение о переносе
NOTE_EXTRA  = ["  // Блок объявлений стоит ВЫШЕ ядра UART (v4.0.0): декоды io_wr_tx/",
               "  // io_rd_rx/io_rd_st ссылаются на state/S_T2/addr_latch - ISE",
               "  // (HDLCompilers:28) требует объявления ДО использования."]

def fail(msg):
    print("FAIL: " + msg); sys.exit(1)

def uniq(lines, mark):
    idx = [i for i, l in enumerate(lines) if mark in l]
    if len(idx) != 1:
        fail("маркер %r найден %d раз(а)" % (mark, len(idx)))
    return idx[0]

with io.open(SRC, "r", encoding="cp1251", newline="") as f:
    text = f.read()
lines = text.split("\n")

# --- границы переносимого блока -------------------------------------------
i_hist = uniq(lines, MARK_HIST)
i_auto = uniq(lines, MARK_AUTO)
i_rdd  = uniq(lines, MARK_RDD)
if not (i_hist < i_auto < i_rdd):
    fail("неожиданный порядок маркеров: hist=%d auto=%d rdd=%d" % (i_hist, i_auto, i_rdd))
block_lo = i_auto - 1                    # рамка //==== перед заголовком
if lines[block_lo].strip() != "//" + "=" * 61:
    fail("строка %d не открывает рамку блока: %r" % (block_lo + 1, lines[block_lo]))
if lines[i_rdd + 1].strip() != "":
    fail("после rd_drive (стр. %d) нет пустой строки: %r" % (i_rdd + 2, lines[i_rdd + 1]))
block_hi = i_rdd + 1                     # хвост блока + его пустая строка

block = lines[block_lo:block_hi + 1]     # рамка..rd_drive + пустая строка

# --- точка вставки: рамка //==== перед ИСТОРИЯ БЛОКА ----------------------
if lines[i_hist - 1].strip() != "//" + "=" * 61:
    fail("перед ИСТОРИЯ БЛОКА нет рамки: %r" % (lines[i_hist - 1],))
ins_at = i_hist - 1

# --- пояснение внутри заголовка переносимого блока -------------------------
i_ale = uniq(block, MARK_ALE)
block = block[:i_ale + 1] + NOTE_EXTRA + block[i_ale + 1:]

# --- вырезать и вставить ---------------------------------------------------
# Вставка ВЫШЕ вырезаемого диапазона (ИСТОРИЯ БЛОКА ~972 < Автомат шины ~1040):
# индексы до block_lo не сдвигаются, смещение не нужно.
if not (ins_at < block_lo):
    fail("вставка (%d) не выше вырезаемого диапазона (%d..%d)" % (ins_at, block_lo, block_hi))
rest = lines[:block_lo] + lines[block_hi + 1:]
new_lines = rest[:ins_at] + block + rest[ins_at:]

new_text = "\n".join(new_lines)
if new_text == text:
    fail("файл не изменился")
if new_text.count("localparam S_IDLE") != 1 or new_text.count(MARK_AUTO) != 1:
    fail("контроль уникальности объявлений после переноса")

with io.open(SRC, "w", encoding="cp1251", newline="") as f:
    f.write(new_text)

# --- регенерация UTF8-двойника из эталона ----------------------------------
with io.open(TWIN, "w", encoding="utf-8", newline="") as f:
    f.write(new_text)

print("OK: блок объявлений автомата перенесён: строки %d-%d -> перед строкой %d (ИСТОРИЯ БЛОКА)"
      % (block_lo + 1, block_hi + 1, i_hist + 1))
print("OK: строк в файле: было %d, стало %d" % (len(lines), len(new_lines)))
print("OK: CP1251 + UTF8-двойник синхронно обновлены")
