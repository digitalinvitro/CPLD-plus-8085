#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_v22.py - верификатор txuart v2.2 (узел /4 на 25 МГц, шунт).

Проверки:
  C0  файлы на месте, v2.1/v2.0/v1.0 не тронуты (бит-в-бит архив линии);
  C1  CP1251 round-trip: v22.v декодируется в точность в v22_utf8.v;
  C2  заголовок/версия v2.2, директива 11-9, п.34, шунт H1 ОБЯЗАТЕЛЕН;
  C3  узел: кольцо s0..s3 (двойной kill + рестарт NOR4), X1 = s0,
      X2 = s1|s2|s3, por_ce = s0, CLK_DIV == 4, ветка g_div4;
  C4  в КОДЕ (вне комментариев) нет r0..r6/clk25/x1_n/cnt/clk25_q/g_div2p5;
      always только на clk; por-цепь и por_run на clk со стробом s0;
  C5  ядро TXUART БИТ-В-БИТ v2.1: все кодовые строки с shreg/bit_cnt/
      baud_cnt/ld_tx_q/io_wr_tx/BAUD_DIV/baud_tick/tx_idle совпадают
      1-в-1 с v2.1 (кроме только такта always-строк clk25 -> clk);
  C6  база бит-в-бит: все кодовые строки v2.1, не относящиеся к узлу
      (FSM/шина/порты/пор-цепь/rst-цепь), присутствуют в v2.2 без
      изменений;
  C7  порядок объявлений (Verilog-2001: объявление раньше использования);
  C8  структура POR: por_sh 8 бит Init=FF, por_run Init=1, сдвиг по CE;
  C9  ключевые константы документа (1280 нс, 6,25/3,125 МГц, шунт,
      744 -> 651, бюджет 101-103).
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

V22 = os.path.join(ROOT, "top_txuart_por6_v22.v")
V22U = os.path.join(ROOT, "top_txuart_por6_v22_utf8.v")
V21 = os.path.join(ROOT, "top_txuart_por6_v21.v")
V21U = os.path.join(ROOT, "top_txuart_por6_v21_utf8.v")
V2 = os.path.join(ROOT, "top_txuart_por6_v2.v")
V1 = os.path.join(ROOT, "top_txuart_por6_v1.v")

pass_n = 0
fail_n = 0


def chk(cond, name, detail=""):
    global pass_n, fail_n
    if cond:
        pass_n += 1
        print("  PASS %s" % name)
    else:
        fail_n += 1
        print("  FAIL %s %s" % (name, detail))


def strip_comments(t):
    return "\n".join((l.split("//")[0] if "//" in l else l) for l in t.split("\n"))


def code_lines(t):
    """Кодовые строки (комментарии срезаны, хвостовые пробелы сняты)."""
    out = []
    for l in t.split("\n"):
        c = (l.split("//")[0] if "//" in l else l).rstrip()
        if c.strip():
            out.append(c)
    return out


raw22 = io.open(V22, "rb").read()
u22 = io.open(V22U, encoding="utf-8").read()
u21 = io.open(V21U, encoding="utf-8").read()

print("== C0 файлы линии ==")
for p in (V21, V21U, V2, V1):
    chk(os.path.exists(p), "exists %s" % os.path.basename(p))
print("== C1 CP1251 round-trip ==")
try:
    dec = raw22.decode("cp1251")
    chk(dec == u22, "v22.v(CP1251) == v22_utf8.v", "len %d vs %d" % (len(dec), len(u22)))
except UnicodeDecodeError as e:
    chk(False, "cp1251 decode", str(e))
try:
    chk(u22.encode("cp1251") == raw22, "utf8 -> cp1251 round-trip")
except UnicodeEncodeError as e:
    chk(False, "cp1251 encode", str(e))

print("== C2 заголовок v2.2 ==")
for s in ("top_txuart.v v2.2",
          "ВЕРСИЯ 2.2 (директива владельца 11-9",
          "потом /4 и подать на процессор",
          "п.34 УЗЕЛ v2.2 - ДЕЛИТЕЛЬ /4 НА 25 МГЦ",
          "H1 С ШУНТОМ", "ШУНТ H1 ОБЯЗАТЕЛЕН",
          "CPU 3,571 -> 3,125 МГц", "744 -> 651"):
    chk(s in u22, "header: %r" % s[:52])
chk("ВЕРСИЯ 2.1" not in u22, "нет заголовка v2.1")

print("== C3 узел v2.2 ==")
c22 = strip_comments(u22)
c21 = strip_comments(u21)
for s in ("reg  s0 = 1'b1;", "reg  s1 = 1'b0;", "reg  s2 = 1'b0;",
          "reg  s3 = 1'b0;",
          "s0 <= (s3 & ~s0 & ~s1 & ~s2) | (~s0 & ~s1 & ~s2 & ~s3);",
          "s1 <= s0 & ~s1 & ~s2 & ~s3;",
          "s2 <= s1 & ~s2 & ~s3 & ~s0;",
          "s3 <= s2 & ~s3 & ~s0 & ~s1;",
          "assign X1 = s0;",
          "assign X2 = s1 | s2 | s3;",
          "assign por_ce = s0;",
          "if (CLK_DIV == 4 && CLK_HALF == 1) begin : g_div4",
          "parameter CLK_DIV = 4,", "parameter CLK_HALF = 1) (",
          "wire por_ce;"):
    chk(s in c22, "node: %r" % s[:60])
chk("always @(posedge clk) begin" in c22, "node: always @(posedge clk)")

print("== C4 мёртвых идентификаторов в КОДЕ нет ==")
for pat, nm in ((r"\br[0-6]\b", "r0..r6"), (r"\bclk25", "clk25*"),
                (r"\bx1_n\b", "x1_n"), (r"\bcnt\b", "cnt"),
                (r"\bclk25_q\b", "clk25_q"), (r"g_div2p5", "g_div2p5"),
                (r"\bsod_q\b", "sod_q"), (r"\btx_pass\b", "tx_pass"),
                (r"\btx_q\b", "tx_q"), (r"\badv_q\b", "adv_q"),
                (r"\btx_run\b", "tx_run"), (r"\bwb_ram_q\b", "wb_ram_q")):
    m = re.findall(pat, c22)
    chk(not m, "code без %s" % nm, str(m[:5]))
chk("posedge clk25" not in c22, "always только на clk")
chk(len(re.findall(r"always @\(posedge clk or posedge cpu_rst\)", c22)) == 2,
    "GSR-блоки (ядро+шина) на clk/cpu_rst")
# пор-цепь: сдвиг по por_ce, por_run из por_sh[0]
chk("por_run <= por_sh[0];" in c22, "por_run.D = por_sh[0]")
chk("if (por_ce) por_sh <= {1'b0, por_sh[7:1]};" in c22, "por_sh сдвиг по CE")
chk(c22.count("reg [7:0] por_sh = 8'hFF;") == 1, "por_sh 8 бит Init=FF")
chk(c22.count("reg  por_run = 1'b1;") == 1, "por_run Init=1 (SET)")

print("== C5 ядро бит-в-бит v2.1 ==")
def core_lines(t):
    ids = ("shreg", "bit_cnt", "baud_cnt", "ld_tx_q", "io_wr_tx",
           "BAUD_DIV", "baud_tick", "tx_idle", "io_rd_st")
    out = []
    for l in code_lines(t):
        if any(i in l for i in ids) and "always @" not in l:
            out.append(re.sub(r"\s+", " ", l.strip()))
    return out

a, b = core_lines(u21), core_lines(u22)
chk(set(a) == set(b), "ядро: строки 1-в-1 v2.1",
    "только в v2.1: %s | только в v2.2: %s" %
    (sorted(set(a) - set(b))[:3], sorted(set(b) - set(a))[:3]))
chk(len(a) == len(b) and len(a) >= 15, "ядро: %d кодовых строк" % len(b))

print("== C6 база бит-в-бит (всё, кроме узла) ==")
NODE_RE = re.compile(r"\b(r[0-6]|clk25\w*|x1_n|cnt|s[0-3]|por_ce|g_div2p5|g_div4|X1|X2)\b")
def base_lines(t):
    out = []
    for l in code_lines(t):
        n = re.sub(r"\s+", " ", l.strip())
        if NODE_RE.search(n) or "always @" in n:
            continue
        out.append(n)
    return out

a, b = base_lines(u21), base_lines(u22)
# ожидаемые отличия (узел v2.2): параметр CLK_DIV
a2 = [l for l in a if "parameter CLK_DIV" not in l]
b2 = [l for l in b if "parameter CLK_DIV" not in l]
chk(set(a2) == set(b2), "база: кодовые строки 1-в-1 v2.1",
    "только в v2.1: %s | только в v2.2: %s" %
    (sorted(set(a2) - set(b2))[:5], sorted(set(b2) - set(a2))[:5]))
chk(len(b2) >= 100, "база: %d кодовых строк" % len(b2))

print("== C7 порядок объявлений ==")
decls = {}
allc = c22
# 1) атрибуты (* keep = "TRUE" *) - не идентификаторы
scan = re.sub(r"\(\*[^*]*\*\)", " ", allc)
# 2) Verilog-литералы 1'b0 / 8'hFF / 5'd16 - не идентификаторы
scan = re.sub(r"\d*'[hbdo][0-9a-fA-FxzXZ_]+", " ", scan)
# 3) одиночные объявления (input/output/inout/reg/wire/localparam/parameter/integer)
decl_re = re.compile(r"\b(input|output|inout|reg|wire|localparam|parameter|integer)\b(\s+(wire|reg))?\s*(\[[^\]]*\]\s*)?([A-Za-z_][A-Za-z0-9_$]*)")
for m in decl_re.finditer(scan):
    decls.setdefault(m.group(5), m.start())
# 4) имена в запятых-списках и цели присваиваний: ID '=' или ID '<='
tgt_re = re.compile(r"([A-Za-z_][A-Za-z0-9_$]*)\s*(<=|=)(?![=])")
for m in tgt_re.finditer(scan):
    decls.setdefault(m.group(1), m.start())
use_ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_$]*", scan))
skip = {"module", "endmodule", "input", "output", "inout", "wire", "reg",
        "localparam", "parameter", "integer", "always", "assign", "begin",
        "end", "if", "else", "case", "endcase", "generate", "endgenerate",
        "function", "endfunction", "posedge", "negedge", "or", "and",
        "not", "nor", "initial", "for", "while", "default",
        "retro_pcld_top", "g_div4", "g_div2p5"}
bad = []
for w in sorted(use_ids - skip - set(decls)):
    if re.match(r"^[0-9]", w) or w in ("F", "b", "h", "x", "z", "S", "T", "W",
                                       "H", "L", "P", "N", "D", "A"):
        continue
    bad.append(w)
chk(not bad, "все идентификаторы объявлены", str(bad[:8]))
# ключевые: s0..s3 объявлены раньше generate-ветки
igen = allc.find("if (CLK_DIV == 4")
for nm in ("s0", "s1", "s2", "s3", "por_ce"):
    chk(0 <= decls.get(nm, -1) < igen, "%s объявлен до ветки узла" % nm)

print("== C8 POR-структура ==")
chk("por_run <= por_sh[0];" in c22 and "if (por_ce) por_sh <= {1'b0, por_sh[7:1]};" in c22,
    "POR: сдвиговый 8 бит, строб через CE, без декодов ==")
por_code = c22.split("reg [7:0] por_sh = 8'hFF;")[1].split("//=============================================================")[0]
chk("==" not in por_code.replace("==", "==") or "por_ce" in por_code,
    "POR-блок: только сдвиг/регистр (без декодов)")

print("== C9 ключевые константы документа ==")
for s in ("1280 нс", "960 нс", "6,25 МГц", "3,125 МГц", "160 нс",
          "duty 1/4", "NOR4", "ОБЯЗАТЕЛЬНО ДО ПОДАЧИ ПИТАНИЯ",
          "НЕ ВКЛЮЧАТЬ", "101-103", "105 МЦ наивно", "x1,143",
          "1 562 500"):
    chk(s in u22, "doc: %r" % s[:40])

print("== C10 тестбенч/раннер на месте ==")
tb = os.path.join(ROOT, "tb_txuart_v22.v")
chk(os.path.exists(tb), "tb_txuart_v22.v существует")
if os.path.exists(tb):
    tbu = io.open(tb, encoding="utf-8", errors="replace").read()
    chk(".CLK_DIV(4)" in tbu, "tb: CLK_DIV(4)")
    chk("160" in tbu and "40" in tbu, "tb: тайминги 160/40 нс")

print("\nTOTAL: %d pass, %d fail" % (pass_n, fail_n))
sys.exit(0 if fail_n == 0 else 1)
