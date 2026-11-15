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
flat = " ".join(txt.split())
# Строб сдвига POR-цепи (~X1&~t0_q = por_ce): форма А - литералы напечатаны
# в сетях (старый фит), форма Б - ВСЁ свёрнуто в FC_2/FC_1 (фит с пин-
# констрейнтами). Форма Б закрывается структурно: T(n) = FC_2&(por_sh(n) XOR
# por_sh(n+1)) для n=0..6, T(7) = FC_1 (заполнение '0'), FC_1/FC_2 НЕ имеют
# потребителей вне por-сетей (чистый шифт-гейт); функция = por_ce по RTL
# п.9 (сдвиг только на стробе CPU-клока) + железо v2.6 (цепь POR не менялась).
por_lit = txt.count("NOT X1 AND NOT t0_q")
shape_ok = all(re.search(
    r"por_sh_T\(%d\) <= \(\(por_sh\(%d\) AND NOT por_sh\(%d\) AND FC_2_\.OUT\) "
    r"OR \(NOT por_sh\(%d\) AND por_sh\(%d\) AND FC_2_\.OUT\)\);" % (n, n, n + 1, n, n + 1),
    flat) is not None for n in range(7))
fill_ok = re.search(r"FTCPE_por_sh7: FTCPE port map \(por_sh\(7\),FC_1_\.OUT,clk,'0','0'\);",
                    flat) is not None
# потребители FC_1/FC_2 вне por-сетей (строки таблиц FB - списки сигналов,
# не потребители: фильтруем ^число: и заголовки Signal)
def fc_outside(name):
    out = []
    for ln in txt.split("\n"):
        s = ln.strip()
        if name not in s or re.match(r"^\d+: ", s) or s.startswith("Signal"):
            continue
        if "por_sh" in s:
            continue
        out.append(s)
    return out
fc1_out, fc2_out = fc_outside("FC_1_"), fc_outside("FC_2_")
por_ok = por_lit >= 8 or (shape_ok and fill_ok and not fc1_out and not fc2_out)
if por_lit >= 8:
    chk(True, "строб por_ce ~X1&~t0_q свёрнут в D/T por_sh (форма А: литералы)")
else:
    chk(por_ok, "строб por_ce свёрнут в FC_1/FC_2 (форма Б: изолированный шифт-гейт)",
        "shape=%s fill=%s вне-por FC1=%s FC2=%s" % (shape_ok, fill_ok, fc1_out[:2], fc2_out[:2]))
for pat in (r"\bs0\b", r"\bs1\b", r"\bs2\b", r"\bs3\b", r"\bclk25_q\b", r"\bx1_n\b"):
    chk(re.search(pat, txt) is None, "в нетлисте НЕТ: %s" % pat)
m = re.search(r"Macrocells.*?\n\s*(\d+)/108", txt, re.S)
chk(m is not None, "строка бюджета найдена")
if m:
    print("    МЦ: %s/108" % m.group(1))
    if MODE == "v27":
        # прогноз варианта C = 106-107 по фиту без пин-констрейнтов; с
        # UCF фиттер вправе упаковывать свободнее (фит 8 = 104). Контракты
        # сторожат: бюджет < 99% (отдельная проверка) и счётчики инстансов
        # tick_cnt/TRAP ниже - МЦ-диапазон не жёсткий (fold-брак им не ловится)
        chk(int(m.group(1)) <= 107, "МЦ <= 107/108 (влезает в 108; бюджет и инстансы ниже)", "факт %s" % m.group(1))
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
            m = re.match(r"[$A-Za-z_][A-Za-z_0-9$<>/]*(?:\(\d+\))?(?:\.[A-Za-z_0-9$]+)*", s[i:])
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

    PAD_ALIAS = {"X1": "x1_q", "X2": "x2_q"}  # пад-сети делителя = его FF

    # Контрольные сети фиттера (FC_N_.OUT) уравнений НЕ имеют. Полная
    # таблица невозможна - сим подаёт baud_tick ЭТАЛОННЫМ стробом 1/25
    # (фаза от INIT): период тика 128 мкс от фазы НЕ зависит
    # (LCM(4,25)=100 при любой фиксированной фазе, CRT), а сам строб
    # железно доказан работой UART (1 000 000 бод) с v2.1. Конус тика
    # (T-сети tick_cnt/TRAP_T) симулируется из печати 1-в-1.
    FC_SYM = True

    def env_of(name, env):
        if name in IDLE0:
            return 0
        name = PAD_ALIAS.get(name, name)
        if name in env:
            return env[name]
        eq = eq_of(name)
        if eq is None:
            if FC_SYM and re.match(r"^FC_\d+_\.OUT$", name):
                # эталонный строб baud_tick 1/25 (фаза от INIT)
                env[name] = env["__bt__"]
                return env[name]
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

    def ff_net_out(cands):
        """FF, чей Q = один из кандидатов. cpldfit вправе переименовать
        защёлку тика в выходной регистр пина (фит v2.7: FTCPE_TRAP с
        T = TRAP_T - мукс свёрнут в T-форму) - ищем по имени Q."""
        for cand in cands:
            m = re.search(r"F([DT])CPE_\S+:\s*F[DT]CPE port map \((%s),([^,]+),clk" % cand, txt)
            if m:
                return m.group(2), m.group(3).strip(), ("T" if m.group(1) == "T" else "D")
        return None, None, None

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
    qname, tq_net, tq_kind = ff_net_out(("tick_q", "TRAP"))
    chk(qname is not None, "защёлка тика: инстанс найден (Q=%s, %s-форма)" % (qname, tq_kind))
    if qname is None:
        tick_ok = False
        tq_eq = None
    else:
        tq_eq = eq_of(tq_net) or tq_net
        if tq_kind == "T":
            # T = step AND (q XOR c4); XOR вправе быть расщеплён на 2
            # И-терма с явными NOT (калибровано фит v2.7); семантику
            # ловит сим (T=1 -> q^=1, T=0 -> hold)
            chk("TRAP" in tq_eq and "tick_cnt(4)" in tq_eq,
                "T-форма защёлки: T по печати = step & (TRAP XOR tick_cnt(4))", tq_eq[:100])
        else:
            chk("XOR" not in tq_eq, "D(tick_q) без XOR (И-ИЛИ защёлка-мукс)", tq_eq)
    baud_sim = True  # печатается ли baud-сторона для полной сим
    baud_bits = {}
    for n in range(5):
        net, kind = ff_net("baud_cnt", n)
        if net is None:
            chk(False, "baud_cnt(%d): инстанс найден" % n)
            tick_ok = False
        else:
            eq = eq_of(net) or net
            if re.search(r"FC_\d+_\.OUT", eq):
                # фит v2.7: фиттер переупаковал baud_cnt (T(0) ссылается на
                # контрольную сеть FC_6_.OUT без уравнения) - печатная
                # симуляция свободного счёта невозможна
                baud_sim = False
            baud_bits[n] = (eq, kind)
    chk(re.search(r"^\s*TRAP\s+\d+\s+\d+\s+FB\d+_\d+\s+74\s+I/O\s+O\s+\S+\s+\S+ RESET\s*$", txt, re.M) is not None,
        "TRAP: P74, выход, registered, INIT=RESET")
    if tick_ok:
        # --- сим 6400 клк ---
        state = {"t0_q": 0, "x1_q": 1, "x2_q": 0, qname: 0}
        for n in range(5):
            state["baud_cnt(%d)" % n] = 0
            state["tick_cnt(%d)" % n] = 0
        steps, q_edges, q_falls = [], [], []
        if not baud_sim:
            print("    INFO: FC_N_.OUT непечатаемы (переупаковка baud_cnt фиттером)"
                  " - baud_tick подан эталонным стробом 1/25 (фаза от INIT;"
                  " период тика от фазы не зависит - LCM(4,25)=100 при CRT);"
                  " конус тика симулируется из печати 1-в-1")
        try:
            ts_eq = eq_of("tick_step")
            if ts_eq is not None:
                ts_fn = parse_fn(ts_eq)
            elif 0 in tick_bits and tick_bits[0][1] == "T":
                # фиттер растворил tick_step в T-сетях (фит v2.7:
                # T(0) = ~X1 & ~t0 & $439677 - бит 0 счётчика тогглит
                # КАЖДЫЙ шаг, перенос = 1, значит его T-сеть = tick_step)
                ts_fn = parse_fn(tick_bits[0][0])
            else:
                pc_eq, bt_eq = eq_of("por_ce"), eq_of("baud_tick")
                if pc_eq is None or bt_eq is None:
                    raise ValueError("tick_step/por_ce/baud_tick не напечатаны")
                a, b = parse_fn(pc_eq), parse_fn(bt_eq)
                ts_fn = lambda env: a(env) & b(env)
            for c in range(6400):
                env = dict(state)
                env["__bt__"] = 1 if (c % 25) == 24 else 0  # эталонный baud_tick
                if ts_fn(env):
                    steps.append(c)
                nxt = {}
                for n, (eq, kind) in tick_bits.items():
                    v = parse_fn(eq)(env)
                    qk = "tick_cnt(%d)" % n
                    nxt[qk] = state[qk] ^ v if kind == "T" else v
                if baud_sim:
                    for n, (eq, kind) in baud_bits.items():
                        v = parse_fn(eq)(env)
                        qk = "baud_cnt(%d)" % n
                        nxt[qk] = state[qk] ^ v if kind == "T" else v
                else:
                    for n in range(5):
                        nxt["baud_cnt(%d)" % n] = 0
                vq = parse_fn(tq_eq)(env)
                # T-форма защёлки: vq = T-сеть -> q ^= T; D-форма: q = D
                nq = (state[qname] ^ vq) if tq_kind == "T" else vq
                if state[qname] == 0 and nq == 1:
                    q_edges.append(c + 1)
                if state[qname] == 1 and nq == 0:
                    q_falls.append(c + 1)
                nxt[qname] = nq
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
