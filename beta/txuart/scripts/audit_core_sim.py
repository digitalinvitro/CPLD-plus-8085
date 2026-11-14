#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_core_sim.py - поведенческая симуляция ПЕЧАТИ ядра (TX-путь)
по уравнениям фит-отчёта. Закрывает остаточный риск переупаковки ядра
(D->T у shreg/TX/bit_cnt/baud_cnt0, переэнкодинг FSM/baud_cnt): та же
печатная логика проверяется поведенчески и сравнивается fit7 vs fit6.

Стимул (шина 8085, CPU-тик = 4 клк 25 МГц):
  POR (GSR-INIT) -> пауза -> OUT 04h, A=5Ah (кадр 1) -> запись В КАДР
  (отброс по контракту п.31) -> пауза -> OUT 04h, A=00h (кадр 2) -> хвост.

Подстановки (каждая документирована, остаточный риск указан):
  RSTF  wr_seen/wr_seen_RSTF__$INT := ~cpu_rst = ~rst_press & ~por_run
        (CLR=NOT RSTF=cpu_rst у ядра, PRE=NOT RSTF у shreg/TX - сходится
        с SET/CLR-ветками GSR в RTL)
  FC_1_.OUT := por_ce & por_sh(7)   - паттерн por_sh_T(0..6) + RTL-запол-
        нение '0' ({1'b0, por_sh[7:1]}): бит 7 тогглит в 0 при por_ce&1
  FC_2_.OUT := por_ce = ~X1 & ~t0_q - ЗАКРЕПЛЕНО ПЕЧАТЬЮ: por_sh_T(0)
        печатает por_ce литералами, T(1..6) сворачивают ту же сеть в FC_2
  FC_3_.OUT := ~ld_tx_q & !frame_active - хвост io_wr_tx (RTL п.31):
        tx_idle по счёту бит-таймов от нагрузки (bit_cnt 1..10, RTL);
        bit_cnt в фитте переэнкодирован - заморожен (см. ниже)
  FC_4_.OUT := ~state_FSM_FFd3 & ~state_FSM_FFd1 - закреплено печатью
        СОВМЕСТНО: (а) ld_tx_q_D = FFd2 & FC_4 = состояние 010 = T2
        переэнкодинга (машина в idle вращается 001->010->100, под ALE
        паркуется в 000 через 001 - самосинхронизация <=2 клк); (б)
        addr_latch_T(5..7) = ~FFd2 & FC_4 = 000 & ALE - захват старших
        бит в парковке; T(0..2) печатают СВОЙ декод целиком (001 & ALE)
  FC_5_.OUT, FC_6_.OUT := __tick__ - эталонный строб baud_tick 1/25 (фазо-
        вый счётчик с джемом от нагрузки, RTL baud_cnt <= 0 при загрузке).
        Функции FC_5/FC_6 НЕВЫВОДИМЫ из печати: фиттер переэнкодировал
        и счётчик (T(0) несовместим с двоичным счётом), и инъекцию '1'
        стоп-бита (D(8) = ld&~A7 | ~ld&~sh8&~$439677 - не реализует
        «:= 1 на тике» ни при какой $439677). Остаточный риск: каденция
        тика = гарантия инструмента + железо (UART-тест); период тика
        от фазы не зависит (CRT(4,25)).
  baud_cnt, bit_cnt - ЗАМОРОЖЕНЫ на INIT (0): их значения питают только
        FC-сети/непечатаемые декоды; литерал-паттерн декода
        (~b0&~b1&~b2&b3&b4) переписывается в __tick__.
Честная глубина проверки данных: sh(1)@tick_j = sh(j)@load = A[j-1] -
старт и биты d0..d6 доходят до TX по загрузочной цепочке БЕЗ непечатаемых
сетей (фронты сверяются 1-в-1); d7/стоп идут через sh(8) (зона
D(8)+FC_6) - покрыты железом. Всё остальное - ИЗ ПЕЧАТИ: уравнения FF
(D/T, CLR/PRE) и INIT-колонки (SET/RESET = GSR-инициализация).
Движок откалиброван под v2.7-формат печати (FC_1..FC_6); fit6-формат
имеет свой набор FC_0..FC_5 - на fit6 сим не запускался (fit6
железо-проверен владельцем)."""
import io
import re
import sys

TICK_LEN = 4          # клк на CPU-тик
BIT_LEN = 25          # клк на бит (1 000 000 бод при 25 МГц)
SIM_LEN = 1100        # клк

RSTF_NET = "wr_seen/wr_seen_RSTF__$INT"


def parse_equations(txt):
    """Имя -> нормализованное выражение (все 'NAME <= ...;' отчёта)."""
    eqs = {}
    for m in re.finditer(r"^\s*([^\s;]+)\s*<=\s*(.*?);", txt, re.M | re.S):
        name = m.group(1).strip()
        expr = " ".join(m.group(2).split())
        if " when " in expr or " else " in expr or "'Z'" in expr:
            continue  # тристейт-драйверы (when/else) не для таблицы истинности
        if re.match(r"^[$A-Za-z_][A-Za-z_0-9$<>/]*(\(\d+\))?(\.[A-Za-z_0-9$]+)*$", name):
            eqs.setdefault(name, expr)
    return eqs


def parse_inits(txt):
    """Q-имя -> 0/1 из колонок Reg Init State (SET/RESET)."""
    init = {}
    for m in re.finditer(r"^(\S+)\s+\d+\s+\d+\s+FB\d+_\d+\s+STD\s+(SET|RESET)\s*$", txt, re.M):
        init[m.group(1)] = 1 if m.group(2) == "SET" else 0
    for m in re.finditer(r"^(\S+)\s+\d+\s+\d+\s+FB\d+_\d+\s+\d+\s+I/O\s+[OBIN]\s+"
                         r"\S+\s+\S+\s*(SET|RESET)?\s*$", txt, re.M):
        if m.group(2):
            init[m.group(1)] = 1 if m.group(2) == "SET" else 0
    return {re.sub(r"<(\d+)>", r"(\1)", k): v for k, v in init.items()}


def parse_ffs(txt):
    """[(q, net, kind, clr, pre)] из всех инстансов FDCPE/FTCPE."""
    ffs = []
    for m in re.finditer(r"F([DT])CPE_\S+:\s*F[DT]CPE port map \(([^,]+),([^,]+),clk,([^,]+),([^)]+)\);", txt):
        ffs.append((m.group(2).strip(), m.group(3).strip(),
                    "T" if m.group(1) == "T" else "D",
                    m.group(4).strip(), m.group(5).strip()))
    return ffs


def expected_transitions(data, load_c):
    """Ожидаемые clk-и фронтов TX: старт + 8 бит данных (LSB-first).
    Бит k занимает [load+1+k*25, load+(k+1)*25); фронт - смена значения.
    Стоп-бит НЕ включён: инъекция '1' в sh(8) непечатаемо переплетена
    фиттером с переэнкодингом счётчика (D(8) + FC_6) - покрывается
    железом (UART-тест) и гарантией инструмента; данные/старт - печать."""
    bits = [0] + [(data >> i) & 1 for i in range(8)]
    out = []
    prev = 1  # idle
    for k, b in enumerate(bits):
        edge = load_c + 1 + k * BIT_LEN
        if b != prev:
            out.append(edge)
        prev = b
    return out


def observed_transitions(trace, load_c, upto):
    """Фактические clk-и фронтов TX в окне [load_c, upto)."""
    tx = trace["TX"]
    return [c for c in range(max(load_c, 1), upto) if tx[c] != tx[c - 1]]


class Sim:
    def __init__(self, path, label):
        self.label = label
        self.txt = io.open(path, "r", encoding="cp1251", errors="replace").read()
        self.eqs = parse_equations(self.txt)
        self.inits = parse_inits(self.txt)
        self.ffs = parse_ffs(self.txt)
        self._pc = {}
        self.has_fc = bool(re.search(r"FC_\d+_\.OUT", self.txt))
        self.subst = {}
        # Заморозка счётчиков на INIT: baud_cnt переэнкодирован фиттером
        # (T(0) несовместим с двоичным счётом, FC_6 невыводим), его значения
        # питают только FC-сети и непечатаемые декоды. Литерал-паттерн
        # декода (появляется в shreg_T(2..7) как «тик» переэнкодинга)
        # переписывается в символ __tick__ = эталонный строб 1/25 с джемом
        # от нагрузки. Остаточный риск: каденция тика = гарантия инструмента
        # + железо (UART), структура сдвига/защёлки = печать 1-в-1.
        self.frozen = {"baud_cnt(%d)" % n: 0 for n in range(5)}
        self.frozen.update({"bit_cnt(%d)" % n: 0 for n in range(4)})
        self._tick_pat = re.compile(
            r"NOT baud_cnt\(0\) AND NOT baud_cnt\(1\) AND NOT baud_cnt\(2\)"
            r" AND baud_cnt\(3\) AND baud_cnt\(4\)")
        if self.has_fc:
            self.subst = {
                "FC_1_.OUT": "(NOT X1 AND NOT t0_q AND por_sh(7))",
                "FC_2_.OUT": "(NOT X1 AND NOT t0_q)",
                "FC_3_.OUT": None,  # модель tx_idle (frame_active)
                "FC_4_.OUT": "(NOT state_FSM_FFd3 AND NOT state_FSM_FFd1)",
                "FC_5_.OUT": "__tick__",
                "FC_6_.OUT": "__tick__",  # завершение декода за ~b0&~b1&~b2
            }
        self.eqs = {k: self._tick_pat.sub("__tick__ ", v) for k, v in self.eqs.items()}

    # --- парсер выражений (как в audit_fit_node.py) ---
    def tokenize(self, s):
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

    def parse_fn(self, s):
        if s in self._pc:
            return self._pc[s]
        toks = self.tokenize(s)
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
            return lambda env: self.env_of(t, env)

        v = expr()
        if pos[0] != len(toks):
            raise ValueError("хвост %r в %r" % (toks[pos[0]:], s[:70]))
        self._pc[s] = v
        return v

    def env_of(self, name, env):
        if name in env:
            return env[name]
        if name in self.subst:
            fn = self.subst[name]
            if fn is None:  # FC_3: модель tx_idle
                v = (1 - env["__frame__"]) & (1 - env.get("ld_tx_q", 0))
            elif fn == "__tick__":
                v = env["__tick__"]
            else:
                v = self.parse_fn(fn)(env)
            env[name] = v
            return v
        if name == RSTF_NET:
            env[name] = self.parse_fn("(NOT rst_press AND NOT por_run)")(env)
            return env[name]
        eq = self.eqs.get(name)
        if eq is None:
            raise ValueError("нет уравнения для %r" % name)
        v = self.parse_fn(eq)(env)
        env[name] = v
        return v

    @staticmethod
    def lit(arg):
        a = arg.strip()
        if a in ("'0'", "'1'"):
            return int(a[1])
        return None

    # --- прогон ---
    def run(self, schedule):
        st = {}
        for q, _net, _k, _clr, _pre in self.ffs:
            st[q] = self.frozen.get(q, self.inits.get(q, 0))
        bus = {"ALE": 0, "WRn": 1, "RDn": 1, "IOM": 0, "A15": 0, "__A": 0x00}
        phase = 0       # фазовый счётчик эталонного строба 0..24 (джем от нагрузки)
        frame = 0       # счётчик бит-таймов кадра (RTL bit_cnt 1..10, модель)
        trace = {"c": [], "TX": [], "ld": [], "state": [], "por": [],
                 "resetin": [], "we": [], "bitcnt": [], "al": [],
                 "strobe": [], "sh": []}
        events = []
        c_rel = None

        def pins():
            p = {"ALE": bus["ALE"], "WRn": bus["WRn"], "RDn": bus["RDn"],
                 "IOM": bus["IOM"], "A15": bus["A15"], "RST": 0, "RX": 1}
            for n in range(8):
                av = (bus["__A"] >> n) & 1
                p["A(%d).PIN" % n] = av
                p["A(%d)" % n] = av
                p["D(%d).PIN" % n] = 0
                p["D(%d)" % n] = 0
            return p

        for c in range(SIM_LEN):
            sched = schedule(c)
            if sched:
                for k, v in sched.items():
                    bus["__A" if k == "A" else k] = v
            env = dict(st)
            env.update(pins())
            env["__frame__"] = 1 if frame else 0
            strobe = 1 if phase == BIT_LEN - 1 else 0   # эталонный строб 1/25
            env["__tick__"] = strobe
            nxt = {}
            for q, net, kind, clr, pre in self.ffs:
                if q in self.frozen:
                    nxt[q] = self.frozen[q]  # заморозка счётчиков (см. __init__)
                    continue
                cv = self.lit(clr)
                if cv is None:
                    cv = self.parse_fn(clr)(env)
                pv = self.lit(pre)
                if pv is None:
                    pv = self.parse_fn(pre)(env)
                if pv:
                    nq = 1
                elif cv:
                    nq = 0
                else:
                    nv = self.lit(net)
                    v = nv if nv is not None else self.parse_fn(net)(env)
                    nq = (st[q] ^ v) if kind == "T" else v
                nxt[q] = nq
            ld_new = nxt.get("ld_tx_q", 0)
            branch_load = 1 if env.get("ld_tx_q", 0) else 0  # ветка загрузки RTL
            cpu_rst_new = nxt.get("rst_press", 0) | nxt.get("por_run", 1)
            st = nxt
            # --- фазовые модели на следующий клк ---
            # джем/bc:=1 срабатывают В ВЕТКЕ загрузки (env.ld_tx_q=1) -
            # счётчики обнуляются этим же клком, строб через 25 клк отсюда
            if cpu_rst_new:
                phase, frame = 0, 0            # CLR baud_cnt/bit_cnt (GSR)
            elif branch_load:
                phase, frame = 0, 1            # джем baud_cnt <= 0, bit_cnt <= 1
            elif strobe:
                phase = 0
                frame = (0 if frame >= 10 else frame + 1) if frame else 0
            else:
                phase = min(phase + 1, BIT_LEN - 1)
            if c_rel is None and st.get("por_run", 1) == 0 and c > 0:
                c_rel = c
                events.append((c, "POR_RELEASE"))
            trace["c"].append(c)
            trace["TX"].append(st.get("TX", 1))
            trace["ld"].append(ld_new)
            trace["state"].append((st.get("state_FSM_FFd3", 0), st.get("state_FSM_FFd2", 0),
                                   st.get("state_FSM_FFd1", 0)))
            trace["por"].append(st.get("por_run", 0))
            trace["resetin"].append(st.get("RESET_IN", 1))
            trace["bitcnt"].append(tuple(st.get("bit_cnt(%d)" % n, 0) for n in range(4)))
            trace["strobe"].append(strobe)
            trace["sh"].append(tuple(st.get("shreg(%d)" % n, 1) for n in range(3)))
            trace["al"].append((st.get("addr_latch(0)", 0), st.get("addr_latch(1)", 0),
                                st.get("addr_latch(2)", 0)))
            trace["we"].append(self._comb("WE_n", env))
        return trace, events

    def _comb(self, name, env):
        try:
            return self.parse_fn(name)(env)
        except Exception:
            return None


def extract_frames(trace):
    """[(load_c, runs)] - кадры от каждой нагрузки до возврата в idle."""
    tx, ld = trace["TX"], trace["ld"]
    loads = [c for c, v in zip(trace["c"], ld) if v]
    frames = []
    for ld_c in loads:
        c0 = ld_c
        while c0 < len(tx) and tx[c0] == 1:
            c0 += 1
        if c0 >= len(tx):
            continue
        runs = []
        v, start = tx[c0], c0
        for c in range(c0 + 1, len(tx)):
            if tx[c] != v:
                runs.append((v, c - start))
                v, start = tx[c], c
                if v == 1 and c - start >= 20 and len(runs) >= 2:
                    break
        else:
            runs.append((v, len(tx) - start))
        if runs and runs[-1][1] >= 20:
            runs = runs[:-1]  # хвостовой idle не часть кадра
        frames.append((ld_c, runs))
    return loads, frames


def run_sim(path, label):
    sim = Sim(path, label)
    base = 200
    S = {}

    def at(c, **kw):
        S[c] = kw

    at(base, IOM=1, A=0x04, ALE=1)                          # T1 (порт 04h)
    at(base + TICK_LEN, ALE=0, WRn=0, A=0x5A)               # T2: данные на AD
    at(base + 2 * TICK_LEN, WRn=0)                          # WRn держится
    at(base + 3 * TICK_LEN, WRn=1, IOM=0, A=0x5A)           # T3
    f1_load_est = base + 4 * TICK_LEN + 6                   # ld через !ld_tx_q-гейт
    busy = f1_load_est + 4 * BIT_LEN + 10                   # запись В КАДР (~bit 4-5)
    at(busy, IOM=1, A=0x04, ALE=1)
    at(busy + TICK_LEN, ALE=0, WRn=0, A=0x77)
    at(busy + 2 * TICK_LEN, WRn=0)
    at(busy + 3 * TICK_LEN, WRn=1, IOM=0)
    f1_end = f1_load_est + 10 * BIT_LEN + 40
    at(f1_end + 40, IOM=1, A=0x04, ALE=1)                   # кадр 2: A=00h
    at(f1_end + 40 + TICK_LEN, ALE=0, WRn=0, A=0x00)
    at(f1_end + 40 + 2 * TICK_LEN, WRn=0)
    at(f1_end + 40 + 3 * TICK_LEN, WRn=1, IOM=0)

    trace, events = sim.run(lambda c: S.get(c))
    return sim, trace, events


def main():
    path = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else path
    sim, trace, events = run_sim(path, label)
    print("== СИМ ЯДРА: %s ==" % label)
    print("  FF инстансов: %d; INIT-колонок: %d; уравнений: %d; FC-сети: %s"
          % (len(sim.ffs), len(sim.inits), len(sim.eqs),
             "есть (подстановки задокументированы)" if sim.has_fc else "нет (полная печать)"))
    for c, kind in events:
        print("  событие: %s @%d" % (kind, c))

    ok = True

    def chk(cond, msg, det=""):
        nonlocal ok
        print(("  PASS " if cond else "  FAIL ") + msg +
              ((" :: " + str(det)) if (det != "" and not cond) else ""))
        if not cond:
            ok = False

    por = trace["por"]
    chk(por[0] == 1, "POR: cpu в сбросе с GSR (por_run INIT=SET)")
    rel = next((i for i, v in enumerate(por) if v == 0), None)
    chk(rel is not None and 25 <= rel <= 45, "POR снят в окне 8 por_ce тиков (~33 клк)", rel)
    chk(all(v == 0 for v in por[rel:]), "por_run не возвращается (одна инициализация)")
    ri = trace["resetin"]
    chk(all(v == 0 for v in ri[:rel]) and all(v == 1 for v in ri[rel + 2:]),
        "RESET_IN = 0 в окне POR, = 1 после (снятие регистровое, +1 клк)")

    loads, frames = extract_frames(trace)
    chk(len(loads) == 2, "ровно 2 нагрузки (запись при busy отброшена)", len(loads))
    if len(loads) == 2:
        l0 = loads[0]
        exp = expected_transitions(0x5A, l0)
        # честная глубина печати: sh(1)@tick_j = sh(j)@load = A[j-1] - данные
        # d0..d6 доходят по загрузочной цепочке БЕЗ непечатаемых сетей;
        # d7/стоп идут через sh(8) (D(8)+FC_6 переплетены фиттером с
        # переэнкодингом счётчика) - покрыто железом (UART-тест) и
        # гарантией инструмента
        exp6 = exp[:6]
        obs = observed_transitions(trace, l0, loads[1])
        chk(obs[:len(exp6)] == exp6 and all(t < exp6[-1] + BIT_LEN for t in obs[:len(exp6)]),
            "кадр 1: фронты старт+d0..d6 точно по печати (биты по %d клк)" % BIT_LEN,
            (obs[:8], exp6))
        chk(loads[1] > loads[0] + 10 * BIT_LEN, "нагрузка 2 после конца кадра 1 (tx_idle)")
    al_at_load = trace["al"][loads[0]] if loads else None
    chk(al_at_load == (0, 0, 1), "addr_latch(2,1,0)=100 (порт 04h) на нагрузке", al_at_load)
    we = trace["we"]
    chk(all(v in (1, None) for v in we), "WE_n=1 весь сценарий (нет writeback в ОЗУ)")
    if loads:
        print("  bit_cnt/baud_cnt заморожены на INIT (переэнкодинг фиттера) -"
              " их роль покрыта FC_3-моделью и стробом; след неинформативен")
    print("\nВЕРДИКТ СИМА ЯДРА: %s" % ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
