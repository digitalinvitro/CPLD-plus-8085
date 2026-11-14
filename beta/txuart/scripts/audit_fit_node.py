#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_fit_node.py - аудитор фит-отчёта (.rpt) по узлу тактирования v2.4+.

ПРИНЦИП (п.9 шапки): сверять ТАБЛИЦЕЙ ИСТИННОСТИ напечатанных уравнений,
не полярностью одного терма. Отчёт печатает реализованные функции - симулируем
ИМЕННО печать (t0_q/X1/X2 + строб por_sh) и требуем поведение:
  X2 = ~X1 в КАЖДЫЙ такт (включая INIT), период X1 = 4 такта, por-строб 1 такт/период.

Статические проверки: пины P68/P69 (I/O O), INIT-колонки (SET/RESET),
запрещённые сигналы (s0..s3, clk25_q, x1_n), пор-цепь (por_run.D=por_sh(0)).

Вердикт: ШИТЬ / НЕ ШИТЬ + причина.
"""
import io
import re
import sys

RPT = sys.argv[1] if len(sys.argv) > 1 else "/home/z/my-project/upload/retro_pcld_top.rpt"
txt = io.open(RPT, "r", encoding="cp1251", errors="replace").read()
ok = fail = 0


def chk(cond, name, detail=""):
    global ok, fail
    print(("  PASS " if cond else "  FAIL ") + name + (" " + detail if detail and not cond else ""))
    ok, fail = ok + (1 if cond else 0), fail + (0 if cond else 1)


def eq_of(sig):
    """Достаёт уравнение sig из секции Equations (с учётом XOR-разбиения
    cpldfit: 'SIG <= A' <таб>XOR<таб> 'SIG <= B;')."""
    m = re.search(r"^\s*%s\s*<=\s*(.+?)\s*;\s*$" % re.escape(sig), txt, re.M | re.S)
    if not m:
        return None
    body = m.group(1)
    body = re.sub(r"%s\s*<=\s*" % re.escape(sig), " ", body)  # снятие повторных префиксов
    return re.sub(r"\s+", " ", body).strip()


print("== Печатные уравнения узла ==")
x2d = eq_of("X2_D")
chk(x2d is not None, "X2_D найдено", "(нет уравнения в отчёте)")
print("    X2_D = %s" % x2d)
x1_inst = re.search(r"FTCPE_X1:\s*FTCPE port map \(X1,([^,]+),clk", txt)
t0_inst = re.search(r"FTCPE_t0_q:\s*FTCPE port map \(t0_q,([^,]+),clk", txt)
x2_inst = re.search(r"FDCPE_X2:\s*FDCPE port map \(X2,X2_D,clk", txt)
chk(x1_inst is not None and x1_inst.group(1).strip() == "t0_q",
    "X1 = FTCPE (T = t0_q)")
chk(t0_inst is not None and t0_inst.group(1).strip() == "'1'",
    "t0_q = FTCPE (T = '1')")
chk(x2_inst is not None, "X2 = FDCPE (D = X2_D)")

print("== Таблица истинности печати (25 МГц, 16 тактов) ==")
# Печатная функция X2_D: литералы X1, t0_q; NOT по печати. XOR-разбиение: A XOR B.
def f_x2d(x1, t0):
    if x2d is None:
        return None
    parts = [p.strip() for p in x2d.split(" XOR ")]
    if len(parts) == 2:
        def val(p):
            p = p.replace("(", "").replace(")", "").strip()
            if p == "NOT X1": return 1 - x1
            if p == "X1": return x1
            if p == "NOT t0_q": return 1 - t0
            if p == "t0_q": return t0
            raise ValueError("неизвестная печать: %r" % p)
        return val(parts[0]) ^ val(parts[1])
    raise ValueError("неожиданная форма X2_D: %r" % x2d)

try:
    t0, x1, x2 = 0, 1, 0  # INIT (0,1,0)
    anti_ok, trace = True, []
    for i in range(16):
        trace.append((t0, x1, x2))
        if x2 != (1 - x1):
            anti_ok = False
        n0, n1 = 1 - t0, x1 ^ t0
        n2 = f_x2d(x1, t0)
        t0, x1, x2 = n0, n1, n2
    period = None
    seq = [s[1] for s in trace[:8]]
    for p in (2, 4, 8):
        if seq[:p] == seq[p:2 * p]:
            period = p
            break
    chk(anti_ok, "X2 = ~X1 в каждом такте печати", "печать даёт X2 в фазе/с лагом")
    chk(period == 4, "период X1 = 4 такта (160 нс)", str(period))
    ones = sum(s[1] for s in trace[:period or 4])
    chk(period == 4 and ones == 2, "duty X1 = 1/2 (80/80 нс)")
    por = sum(1 for (t0_, x1_, _) in trace[:period or 4] if t0_ == 0 and x1_ == 0)
    chk(por == 1, "строб por_ce = 1 такт за период (POR 1280 нс)")
except ValueError as e:
    chk(False, "разбор печатной функции", str(e))

print("== Статика отчёта ==")
chk(re.search(r"^X1\s+\d+\s+\d+\s+FB\d+_\d+\s+68\s+I/O\s+O\s+STD\s+FAST SET\s*$", txt, re.M) is not None,
    "X1: P68, IO-MC, FAST, INIT=SET")
chk(re.search(r"^X2\s+\d+\s+\d+\s+FB\d+_\d+\s+69\s+I/O\s+O\s+STD\s+FAST RESET\s*$", txt, re.M) is not None,
    "X2: P69, IO-MC, FAST, INIT=RESET")
chk(re.search(r"FDCPE_por_run: FDCPE port map \(por_run,por_sh\(0\),clk", txt) is not None,
    "por_run.D = por_sh(0)")
chk(txt.count("FTCPE_por_sh") == 8, "por_sh = ровно 8 FTCPE", str(txt.count("FTCPE_por_sh")))
chk(txt.count("NOT X1 AND NOT t0_q") >= 8, "строб ~X1&~t0_q свёрнут в D всех 8 бит por_sh")
for pat in (r"\bs0\b", r"\bs1\b", r"\bs2\b", r"\bs3\b", r"\bclk25_q\b", r"\bx1_n\b"):
    chk(re.search(pat, txt) is None, "в нетлисте НЕТ: %s" % pat)
m = re.search(r"Macrocells.*?\n\s*(\d+)/108", txt, re.S)
chk(m is not None, "строка бюджета найдена")
if m:
    print("    МЦ: %s/108" % m.group(1))
chk("Fitting Status: Successful" in txt, "Fitting Status: Successful")

print("\nВЕРДИКТ: %s (PASS %d / FAIL %d)" %
      ("ШИТЬ" if fail == 0 else "НЕ ШИТЬ", ok, fail))
if fail:
    print("  Класс брака: см. FAIL выше (для X2-D это класс «потеря инверсии» -")
    print("  прецеденты фит 7:31/8:55 с por-декодами). Лечение: D(x2) - явная")
    print("  И-ИЛИ форма (x1&t0)|(~x1&~t0) - печать с NOT, аудит таблицей.")
sys.exit(1 if fail else 0)
