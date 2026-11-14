#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_fit_node.py - аудитор фит-отчёта (.rpt) по узлу тактирования v2.4+.

ПРИНЦИП (п.9 шапки): сверять ТАБЛИЦЕЙ ИСТИННОСТИ напечатанных уравнений,
не полярностью одного терма. Отчёт печатает реализованные функции - симулируем
ИМЕННО печать (t0_q/X1/X2 + строб por_sh) и требуемое поведение:
  X2 = ~X1 в КАЖДЫЙ такт (включая INIT), период X1 = 4 такта, por-строб 1 такт/период.

Режимы (2-й аргумент, по умолчанию v27):
  v27 - полный аудит: узел v2.6 (делитель) + ТИК v2.7 (tick_cnt 5 FF,
        tick_q-защёлка, TRAP P74; печать тика симулируется 6400 клк:
        tick_step каждые ровно 100 клк, фронт tick_q каждые 3200 клк,
        high 1600; МЦ = 107).
  v26 - только узел v2.6 (для регрессии старых отчётов).

Статические проверки: пины P68/P69 (I/O O), INIT-колонки (SET/RESET),
запрещённые сигналы (s0..s3, clk25_q, x1_n), пор-цепь (por_run.D=por_sh(0)).

Вердикт: ШИТЬ / НЕ ШИТЬ + причина.
"""
import io
import re
import sys

RPT = sys.argv[1] if len(sys.argv) > 1 else "/home/z/my-project/upload/retro_pcld_top.rpt"
MODE = (sys.argv[2] if len(sys.argv) > 2 else "v27").lower()
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
x1_inst = re.search(r"FTCPE_X1:\s*FTCPE port map \(X1,([^,]+),clk", txt)
t0_inst = re.search(r"FTCPE_t0_q:\s*FTCPE port map \(t0_q,([^,]+),clk", txt)
x2_tff = re.search(r"FTCPE_X2:\s*FTCPE port map \(X2,([^,]+),clk", txt)
x2_dff = re.search(r"FDCPE_X2:\s*FDCPE port map \(X2,X2_D,clk", txt)
chk(x1_inst is not None and x1_inst.group(1).strip() == "t0_q",
    "X1 = FTCPE (T = t0_q)")
chk(t0_inst is not None and t0_inst.group(1).strip() == "'1'",
    "t0_q = FTCPE (T = '1')")
t_form = x2_tff is not None and x2_tff.group(1).strip() == "t0_q"
x2d = None
if t_form:
    chk(True, "X2 = FTCPE (T = t0_q) - T-форма v2.6, комб-логики НЕТ")
    chk(x2_dff is None, "FDCPE_X2 отсутствует (D-форма не вернулась)")
elif x2_dff is not None:
    x2d = eq_of("X2_D")
    chk(x2d is not None, "X2_D найдено", "(нет уравнения в отчёте)")
    print("    X2_D = %s" % x2d)
    chk(False, "X2 в D-форме (v2.6 требует T-форму: печать XOR без NOT "
               "при любой записи RTL - фит 5 = фит 4 байт-в-байт)")
else:
    t_form = True  # чтобы сим не упал до chk ниже
    chk(False, "инстанс X2 не найден")

print("== Таблица истинности печати (25 МГц, 16 тактов) ==")
if t_form:
    print("    T-форма: X2(t+1) = X2 ^ t0; X1(t+1) = X1 ^ t0 -> X2^X1 "
          "инвариант = INIT")

def f_x2d(x1, t0):
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
        n2 = (x2 ^ t0) if t_form else f_x2d(x1, t0)
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
    if MODE == "v27":
        chk(m.group(1) == "107", "МЦ = 107 (вариант C: 101 + 6 МЦ тика)", "факт %s" % m.group(1))
chk("Fitting Status: Successful" in txt, "Fitting Status: Successful")

# ================================================================
# ТИК v2.7: печатные уравнения узла тика, симуляция 6400 клк (2 периода).
# Формат печати (калибровано по fit6): инстансы FDCPE_<имя><n>: FDCPE
# port map (Q,D/T,clk,CLR,PRE); D/T-сети уравнениями <имя>_D(n) <= ...;
# имена векторов с (n), промежуточные провода уравнениями.
# ================================================================
if MODE == "v27":
    print("== ТИК v2.7 (печать + сим 6400 клк) ==")
    IDLE0 = ("ld_tx_q",)  # холостой ход: jam загрузки UART = 0
    PARSE_CACHE = {}

    def tokenize(s):
        toks, i = [], 0
        while i < len(s):
            c = s[i]
            if c.isspace():
                i += 1
                continue
            if c in "()":
                toks.append(c)
                i += 1
                continue
            m = re.match(r"[$A-Za-z_][A-Za-z_0-9$<>/]*(:?\(\d+\))?", s[i:])
            if not m:
                raise ValueError("символ %r в %r" % (c, s[:70]))
            toks.append(m.group(0))
            i += m.end()
        return toks

    def parse_fn(s):
        if s in PARSE_CACHE:
            return PARSE_CACHE[s]
        toks = tokenize(s)
        pos = [0]

        def peek():
            return toks[pos[0]] if pos[0] < len(toks) else None

        def eat():
            t = toks[pos[0]]
            pos[0] += 1
            return t

        def expr():
            v = xt()
            while peek() == "OR":
                eat()
                b = xt()
                v = (lambda a, b: lambda env: a(env) | b(env))(v, b)
            return v

        def xt():
            v = tm()
            while peek() == "XOR":
                eat()
                b = tm()
                v = (lambda a, b: lambda env: a(env) ^ b(env))(v, b)
            return v

        def tm():
            v = fa()
            while peek() == "AND":
                eat()
                b = fa()
                v = (lambda a, b: lambda env: a(env) & b(env))(v, b)
            return v

        def fa():
            if peek() == "NOT":
                eat()
                g = fa()
                return lambda env: 1 - g(env)
            return at()

        def at():
            t = peek()
            if t == "(":
                eat()
                v = expr()
                if peek() != ")":
                    raise ValueError("нет ) в %r" % s[:70])
                eat()
                return v
            if t is None or t in ("NOT", "AND", "OR", "XOR", ")"):
                raise ValueError("токен %r в %r" % (t, s[:70]))
            eat()
            return lambda env: env_of(t, env)

        v = expr()
        if pos[0] != len(toks):
            raise ValueError("хвост %r в %r" % (toks[pos[0]:], s[:70]))
        PARSE_CACHE[s] = v
        return v

    def env_of(name, env):
        if name in IDLE0:
            return 0
        if name in env:
            return env[name]
        eq = eq_of(name)
        if eq is None:
            raise ValueError("нет уравнения для %r (печать тика не распознана)" % name)
        v = parse_fn(eq)(env)
        env[name] = v
        return v

    def ff_net(sig, n=None):
        """Имя D/T-сети FF из строки инстанса + вид (D или T)."""
        q = "%s(%d)" % (sig, n) if n is not None else sig
        m = re.search(r"F([DT])CPE_%s\S*:\s*F[DT]CPE port map \(%s,([^,]+),clk" % (re.escape(sig), re.escape(q)), txt)
        if not m:
            return None, None
        return m.group(2).strip(), ("T" if m.group(1) == "T" else "D")

    # --- инстансы и уравнения ---
    tick_ok = True
    tick_bits = {}
    for n in range(5):
        net, kind = ff_net("tick_cnt", n)
        chk(net is not None, "tick_cnt(%d): инстанс найден (%s)" % (n, kind or "-"))
        if net is None:
            tick_ok = False
            continue
        eq = eq_of(net) or net  # D может быть inline-выражением
        tick_bits[n] = (eq, kind)
    tq_net, _ = ff_net("tick_q")
    chk(tq_net is not None, "tick_q: инстанс найден")
    if tq_net is None:
        tick_ok = False
        tq_eq = None
    else:
        tq_eq = eq_of(tq_net) or tq_net
        chk("XOR" not in tq_eq, "D(tick_q) без XOR (И-ИЛИ защёлка-мукс)", tq_eq)
    baud_bits = {}
    for n in range(5):
        net, kind = ff_net("baud_cnt", n)
        if net is None:
            chk(False, "baud_cnt(%d): инстанс найден" % n)
            tick_ok = False
        else:
            baud_bits[n] = (eq_of(net) or net, kind)
    chk(re.search(r"^\s*TRAP\s+\d+\s+\d+\s+FB\d+_\d+\s+74\s+I/O\s+O\s+\S+\s+\S+ RESET\s*$", txt, re.M) is not None,
        "TRAP: P74, выход, registered, INIT=RESET")
    if tick_ok:
        # --- сим 6400 клк ---
        state = {"t0_q": 0, "x1_q": 1, "x2_q": 0, "tick_q": 0}
        for n in range(5):
            state["baud_cnt(%d)" % n] = 0
            state["tick_cnt(%d)" % n] = 0
        steps, q_edges, q_falls = [], [], []
        tc_seen = set()
        try:
            ts_eq = eq_of("tick_step")
            if ts_eq is not None:
                ts_fn = parse_fn(ts_eq)
            else:
                pc_eq, bt_eq = eq_of("por_ce"), eq_of("baud_tick")
                if pc_eq is None or bt_eq is None:
                    raise ValueError("tick_step/por_ce/baud_tick не напечатаны")
                a, b = parse_fn(pc_eq), parse_fn(bt_eq)
                ts_fn = lambda env: a(env) & b(env)
            for c in range(6400):
                env = dict(state)
                if ts_fn(env):
                    steps.append(c)
                nxt = {}
                for n, (eq, kind) in tick_bits.items():
                    v = parse_fn(eq)(env)
                    qk = "tick_cnt(%d)" % n
                    nxt[qk] = state[qk] ^ v if kind == "T" else v
                for n, (eq, kind) in baud_bits.items():
                    v = parse_fn(eq)(env)
                    qk = "baud_cnt(%d)" % n
                    nxt[qk] = state[qk] ^ v if kind == "T" else v
                vq = parse_fn(tq_eq)(env)
                if state["tick_q"] == 0 and vq == 1:
                    q_edges.append(c + 1)
                if state["tick_q"] == 1 and vq == 0:
                    q_falls.append(c + 1)
                nxt["tick_q"] = vq
                nxt["t0_q"] = 1 - state["t0_q"]
                nxt["x1_q"] = state["x1_q"] ^ state["t0_q"]
                nxt["x2_q"] = state["x2_q"] ^ state["t0_q"]
                state = nxt
        except ValueError as e:
            chk(False, "сим тика: печать разобрана", str(e))
            tick_ok = False
        if tick_ok:
            gaps = {steps[i + 1] - steps[i] for i in range(len(steps) - 1)}
            chk(len(steps) == 64 and gaps == {100},
                "tick_step: 64 строба, каждые ровно 100 клк (4 мкс)",
                "n=%d gaps=%s" % (len(steps), sorted(gaps)[:4]))
            chk(len(q_edges) == 2 and q_edges[1] - q_edges[0] == 3200,
                "фронт tick_q каждые ровно 3200 клк (128 мкс)", str(q_edges))
            chk(len(q_falls) == 1 and q_falls[0] - q_edges[0] == 1600,
                "high tick_q ровно 1600 клк (64 мкс; 2-й спад за окном 6400)",
                str(q_falls))
            tc_seen = set((state["tick_cnt(%d)" % n] for n in range(5)))
            chk(len(tc_seen) == 1 and list(tc_seen)[0] == 0,
                "tick_cnt вернулся в 0 через 2 периода (32 шага/период)")
    else:
        chk(False, "ТИК v2.7 в отчёте НЕ найден (это отчёт v2.6? шить МОЖНО только v27-отчёт)")

print("\nВЕРДИКТ: %s (PASS %d / FAIL %d)" %
      ("ШИТЬ" if fail == 0 else "НЕ ШИТЬ", ok, fail))
if fail:
    print("  Класс брака: см. FAIL выше (для X2 это класс «потеря инверсии» -")
    print("  D-форма неаудитируема: фит 5 = фит 4 байт-в-байт, печать XOR")
    print("  без NOT при любой записи RTL). Лечение (v2.6): x2_q = FTCPE")
    print("  с T = t0_q, INIT = RESET - T-форма, комб-логики нет, инвариант")
    print("  X2^X1 = 1 живёт в INIT-бите (SET/RESET-колонки отчёта). Для")
    print("  тика v2.7 класс тот же: XOR/потеря NOT в D(tick_q) = БРАК")
    print("  (защёлка-мукс должна печататься И-ИЛИ с явными NOT).")
sys.exit(1 if fail else 0)
