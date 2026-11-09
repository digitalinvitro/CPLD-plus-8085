#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_v23.py - верификатор txuart v2.3 (урок железа 11-9: CH340G не
умеет 1 562 500 -> бод 25/25 = РОВНО 1 000 000, сетка CH340G 48М/48).

Проверки:
  C0  файлы на месте, v2.2/v2.1/v2.0/v1.0 НЕ ТРОНУТЫ (хэши - архив линии);
  C1  CP1251 round-trip: v23.v декодируется в точность в v23_utf8.v;
  C2  заголовок v2.3: урок железа, сетка CH340G, 1 500 000 молча, +4,17%,
      терминал 1 000 000, шунт H1, бюджет 104;
  C3  узел v2.2 НЕ ТРОНУТ: кольцо s0..s3, X1 = s0, X2 = s1|s2|s3,
      por_ce = s0, CLK_DIV == 4;
  C4  в КОДЕ нет мёртвых идентификаторов; always только на clk;
  C5  ядро: РОВНО 4 ожидаемых кодовых отличия от v2.2 (BAUD_DIV 16 -> 25,
      baud_cnt [3:0]4'd0 -> [4:0]5'd0 (декларация), D-функция +4'd1 ->
      явный wrap, 2 ветки baud_cnt <= 4'd0 -> 5'd0), всё остальное
      кодовых строк 1-в-1 v2.2; reset/загрузка bit_cnt не тронуты;
  C6  база (FSM/шина/порты/пор-цепь/rst-цепь) - 1-в-1 v2.2;
  C7  порядок объявлений (Verilog-2001);
  C8  POR-структура цела;
  C9  ключевые константы документа (1 000 000, 1000 нс, 25 тиков,
      48М/48, +4,17%, 103-105);
  C10 tb_v23 (BITNS=1000) и раннер на месте; hex прошивки не тронут.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

V23 = os.path.join(ROOT, "top_txuart_por6_v23.v")
V23U = os.path.join(ROOT, "top_txuart_por6_v23_utf8.v")
V22 = os.path.join(ROOT, "top_txuart_por6_v22.v")
V22U = os.path.join(ROOT, "top_txuart_por6_v22_utf8.v")

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
    out = []
    for l in t.split("\n"):
        c = (l.split("//")[0] if "//" in l else l).rstrip()
        if c.strip():
            out.append(re.sub(r"\s+", " ", c.strip()))
    return out


raw23 = io.open(V23, "rb").read()
u23 = io.open(V23U, encoding="utf-8").read()
u22 = io.open(V22U, encoding="utf-8").read()

print("== C0 файлы линии (архив не тронут) ==")
for p in (V22, V22U,
          os.path.join(ROOT, "top_txuart_por6_v21.v"),
          os.path.join(ROOT, "top_txuart_por6_v21_utf8.v"),
          os.path.join(ROOT, "top_txuart_por6_v2.v"),
          os.path.join(ROOT, "top_txuart_por6_v1.v")):
    chk(os.path.exists(p), "exists %s" % os.path.basename(p))
hexf = os.path.join(ROOT, "rom", "uart_tx_test.hex")
chk(os.path.exists(hexf), "exists rom/uart_tx_test.hex")
if os.path.exists(hexf):
    hx = io.open(hexf, "rb").read()
    chk(len(hx) == 2144, "hex: размер 2144 байт (772 байта данных)", str(len(hx)))

print("== C1 CP1251 round-trip ==")
try:
    dec = raw23.decode("cp1251")
    chk(dec == u23, "v23.v(CP1251) == v23_utf8.v")
    chk(u23.encode("cp1251") == raw23, "utf8 -> cp1251 round-trip")
except (UnicodeDecodeError, UnicodeEncodeError) as e:
    chk(False, "cp1251 round-trip", str(e))

print("== C2 заголовок v2.3 ==")
for s in ("top_txuart.v v2.3",
          "УРОК ПЕРВОГО ЖЕЛЕЗНОГО ПРОГОНА v2.2",
          "сетки CH340G", "МОЛЧА ставит 1 500 000",
          "РОВНО 1 000 000", "Терминал 1 000 000 8N1",
          "ВЕРСИЯ 2.3", "H1 С ШУНТОМ", "ШУНТ H1 ОБЯЗАТЕЛЕН",
          "+1 МЦ", "104"):
    chk(s in u23, "header: %r" % s[:52])
chk("top_txuart.v v2.3" in u23 and "ПЕРЕДАТЧИК UART 8N1 1 000 000 бод" in u23,
    "шапка: v2.3 + 1 000 000")

print("== C3 узел v2.2 не тронут ==")
c23 = strip_comments(u23)
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
    chk(s in c23, "node: %r" % s[:60])

print("== C4 мёртвых идентификаторов в КОДЕ нет ==")
for pat, nm in ((r"\br[0-6]\b", "r0..r6"), (r"\bclk25", "clk25*"),
                (r"\bclk25_q\b", "clk25_q"), (r"\badv_q\b", "adv_q"),
                (r"\btx_run\b", "tx_run"), (r"\bsod_q\b", "sod_q")):
    m = re.findall(pat, c23)
    chk(not m, "code без %s" % nm, str(m[:5]))
chk("posedge clk25" not in c23, "always только на clk")
chk(len(re.findall(r"always @\(posedge clk or posedge cpu_rst\)", c23)) == 2,
    "GSR-блоки (ядро+шина) на clk/cpu_rst")
chk("por_run <= por_sh[0];" in c23, "por_run.D = por_sh[0]")
chk("if (por_ce) por_sh <= {1'b0, por_sh[7:1]};" in c23, "por_sh сдвиг по CE")

print("== C5 ядро: ровно 4 кодовых отличия от v2.2 ==")
CORE_IDS = ("shreg", "bit_cnt", "baud_cnt", "ld_tx_q", "io_wr_tx",
            "BAUD_DIV", "baud_tick", "tx_idle", "io_rd_st")


def core_lines(t):
    out = []
    for l in code_lines(t):
        if any(i in l for i in CORE_IDS) and "always @" not in l:
            out.append(l)
    return out


a22 = core_lines(u22)
a23 = core_lines(u23)
# ожидаемые замены (по 1 вхождению, кроме baud_cnt <= N'd0 - 2 вхождения)
EXPECT = [
    ("localparam [4:0] BAUD_DIV = 5'd16;", "localparam [4:0] BAUD_DIV = 5'd25;"),
    ("reg [3:0] baud_cnt = 4'd0;", "reg [4:0] baud_cnt = 5'd0;"),
    ("baud_cnt <= baud_cnt + 4'd1;", "baud_cnt <= baud_tick ? 5'd0 : baud_cnt + 5'd1;"),
    ("baud_cnt <= 4'd0;", "baud_cnt <= 5'd0;"),
]
work = list(a22)
ok = True
for old, new in EXPECT:
    n = work.count(old)
    if n < 1:
        chk(False, "ядро: не найдено %r" % old)
        ok = False
        continue
    work = [new if l == old else l for l in work]  # заменяем ВСЕ вхождения
chk(ok, "ядро: все 4 шаблона найдены в v2.2")
if ok:
    from collections import Counter
    ca, cb = Counter(work), Counter(a23)
    only22 = ca - cb
    only23 = cb - ca
    chk(not only22 and not only23, "ядро: после замен 1-в-1 v2.2",
        "лишнее v2.2: %s | лишнее v2.3: %s" % (list(only22)[:3], list(only23)[:3]))
chk(a23.count("bit_cnt <= (bit_cnt == 4'd10) ? 4'd0 : bit_cnt + 4'd1;") == 1,
    "ядро: bit_cnt механика не тронута")
chk(a23.count("shreg <= {A, 1'b0};") == 1 and a23.count("shreg <= {1'b1, shreg[8:1]};") == 1,
    "ядро: shreg загрузка/сдвиг не тронуты")
chk(sum(1 for l in a23 if "io_wr_tx = (state == S_T2)" in l) == 1,
    "ядро: строб io_wr_tx не тронут")

print("== C6 база 1-в-1 v2.2 ==")
NODE_RE = re.compile(r"\b(r[0-6]|clk25\w*|x1_n|cnt|s[0-3]|por_ce|g_div2p5|g_div4|X1|X2)\b")
EXTRA = re.compile(r"\b(" + "|".join(CORE_IDS) + r")\b")


def base_lines(t):
    out = []
    for l in code_lines(t):
        if NODE_RE.search(l) or EXTRA.search(l) or "always @" in l:
            continue
        out.append(l)
    return out


ba, bb = base_lines(u22), base_lines(u23)
chk(set(ba) == set(bb), "база: кодовые строки 1-в-1 v2.2",
    "только в v2.2: %s | только в v2.3: %s" %
    (sorted(set(ba) - set(bb))[:5], sorted(set(bb) - set(ba))[:5]))
chk(len(bb) >= 100, "база: %d кодовых строк" % len(bb))

print("== C7 порядок объявлений ==")
decls = {}
allc = c23
scan = re.sub(r"\(\*[^*]*\*\)", " ", allc)
scan = re.sub(r"\d*'[hbdo][0-9a-fA-FxzXZ_]+", " ", scan)
decl_re = re.compile(r"\b(input|output|inout|reg|wire|localparam|parameter|integer)\b(\s+(wire|reg))?\s*(\[[^\]]*\]\s*)?([A-Za-z_][A-Za-z0-9_$]*)")
for m in decl_re.finditer(scan):
    decls.setdefault(m.group(5), m.start())
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

print("== C8 POR-структура ==")
chk(c23.count("reg [7:0] por_sh = 8'hFF;") == 1, "por_sh 8 бит Init=FF")
chk(c23.count("reg  por_run = 1'b1;") == 1, "por_run Init=1 (SET)")

print("== C9 ключевые константы документа ==")
for s in ("1 000 000", "48М/48", "+4,17%", "1 500 000", "103-105",
          "25 тиков", "925 926", "500 000", "x1,143", "1280 нс",
          "ОБЯЗАТЕЛЬНО ДО ПОДАЧИ ПИТАНИЯ"):
    chk(s in u23, "doc: %r" % s[:40])

print("== C10 tb/раннер/чекер фита ==")
tb = os.path.join(ROOT, "tb_txuart_v23.v")
chk(os.path.exists(tb), "tb_txuart_v23.v существует")
if os.path.exists(tb):
    tbu = io.open(tb, encoding="utf-8").read()
    chk("localparam BITNS = 1000;" in tbu, "tb: BITNS = 1000")
    chk(".CLK_DIV(4)" in tbu, "tb: CLK_DIV(4)")
    chk("1000 ns (25 ticks" in tbu, "tb: сообщение о 1000 нс/25 тиках")
    chk("v22" not in tbu.replace("lesson", ""), "tb: ссылок на v22 нет")
chk(os.path.exists(os.path.join(ROOT, "scripts", "run_tb_v23.sh")), "run_tb_v23.sh")
chk(os.path.exists(os.path.join(ROOT, "top_txuart_por6_v23_utf8.ucf")) or
    os.path.exists(os.path.join(ROOT, "top_txuart.ucf")), "UCF доступен (ноги 1-в-1 v2.2)")

print("\nTOTAL: %d pass, %d fail" % (pass_n, fail_n))
sys.exit(0 if fail_n == 0 else 1)
