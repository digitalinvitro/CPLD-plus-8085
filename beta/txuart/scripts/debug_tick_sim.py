#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debug_tick_sim.py - трассировка симулятора тика аудитора на синтетике."""
import io
import re

txt = io.open("/tmp/synth_v27.rpt", encoding="cp1251", errors="replace").read()


def eq_of(sig):
    m = re.search(r"^\s*%s\s*<=\s*(.+?)\s*;\s*$" % re.escape(sig), txt, re.M | re.S)
    if not m:
        return None
    body = m.group(1)
    body = re.sub(r"%s\s*<=\s*" % re.escape(sig), " ", body)
    return re.sub(r"\s+", " ", body).strip()


IDLE0 = ("ld_tx_q",)


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
            raise ValueError("sym %r in %r" % (c, s[:70]))
        toks.append(m.group(0))
        i += m.end()
    return toks


def parse_fn(s):
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
            v = (lambda a, b: lambda e: a(e) | b(e))(v, b)
        return v

    def xt():
        v = tm()
        while peek() == "XOR":
            eat()
            b = tm()
            v = (lambda a, b: lambda e: a(e) ^ b(e))(v, b)
        return v

    def tm():
        v = fa()
        while peek() == "AND":
            eat()
            b = fa()
            v = (lambda a, b: lambda e: a(e) & b(e))(v, b)
        return v

    def fa():
        if peek() == "NOT":
            eat()
            g = fa()
            return lambda e: 1 - g(e)
        return at()

    def at():
        t = peek()
        if t == "(":
            eat()
            v = expr()
            if peek() != ")":
                raise ValueError("no )")
            eat()
            return v
        if t is None or t in ("NOT", "AND", "OR", "XOR", ")"):
            raise ValueError("tok %r" % t)
        eat()
        return lambda e: env_of(t, e)

    v = expr()
    if pos[0] != len(toks):
        raise ValueError("tail %r" % toks[pos[0]:])
    return v


def env_of(name, env):
    if name in IDLE0:
        return 0
    if name in env:
        return env[name]
    eq = eq_of(name)
    if eq is None:
        raise ValueError("no eq %r" % name)
    v = parse_fn(eq)(env)
    env[name] = v
    return v


def bits(v):
    return "".join(str(v["baud_cnt(%d)" % n]) for n in (4, 3, 2, 1, 0))


state = {"t0_q": 0, "x1_q": 1, "x2_q": 0, "tick_q": 0}
for n in range(5):
    state["baud_cnt(%d)" % n] = 0
    state["tick_cnt(%d)" % n] = 0
bnet, bkind = {}, {}
for n in range(5):
    m = re.search(r"F([DT])CPE_baud_cnt\S*:\s*F[DT]CPE port map \(baud_cnt\(%d\),([^,]+),clk" % n, txt)
    bnet[n] = (m.group(2).strip(), "T" if m.group(1) == "T" else "D")
ts = parse_fn(eq_of("tick_step"))
print("tick_step eq:", eq_of("tick_step"))
for c in range(110):
    env = dict(state)
    try:
        s = ts(env)
    except ValueError as e:
        print("ENV KEYS:", sorted(env.keys()))
        raise
    if c < 8 or s:
        print("clk %3d t0=%d x1=%d bc=%s step=%d" % (c, state["t0_q"], state["x1_q"], bits(state), s))
    nxt = {}
    for n in range(5):
        net, kind = bnet[n]
        v = parse_fn(eq_of(net))(env)
        qk = "baud_cnt(%d)" % n
        nxt[qk] = state[qk] ^ v if kind == "T" else v
    nxt["t0_q"] = 1 - state["t0_q"]
    nxt["x1_q"] = state["x1_q"] ^ state["t0_q"]
    nxt["x2_q"] = state["x2_q"] ^ state["t0_q"]
    nxt["tick_q"] = 0
    for n in range(5):
        nxt["tick_cnt(%d)" % n] = 0
    state = nxt
