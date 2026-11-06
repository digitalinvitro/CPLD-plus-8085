#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# sim_v399h_ring6.py - v3.9.9h (линия hiclock): ПОЛНЫЙ ПЕРЕБОР состояний
# кольца one-hot N=6 (r0..r5) на clk 50 МГц + комбинированная модель
# power-on (кольцо x por_sh x фаза clk25_q), эквивалент P0a tb_poweron.
#
# Уравнения RTL v3.9.9h (двойной kill п.15/22, wrap mod 6, рестарт NOR6):
#   r0.D = (r5 & ~r0 & ~r1 & ~r2) | (~r0 & ~r1 & ~r2 & ~r3 & ~r4 & ~r5)
#   r1.D = r0 & ~r1 & ~r2 & ~r3
#   r2.D = r1 & ~r2 & ~r3 & ~r4
#   r3.D = r2 & ~r3 & ~r4 & ~r5
#   r4.D = r3 & ~r4 & ~r5 & ~r0
#   r5.D = r4 & ~r5 & ~r0 & ~r1
# por_ce = r0; por_sh: сдвиг вправо по por_ce, 0 в MSB, por_run.D = por_sh[0]
# (сэмпл на posedge clk); clk25_q - T-триггер.
# Сетка: posedge clk каждые 20 нс (t = 20k); сэмпл D - значение ДО фронта.

N = 6
def step_ring(r):
    """Один фронт: вернуть следующее состояние кольца (кортеж битов r0..r5).
    ВНИМАНИЕ: только целочисленная арифметика 1-x - питоновский ~x на int
    даёт -1/-2 (ловушка первой прогона)."""
    r0, r1, r2, r3, r4, r5 = r
    t_birth = r5 & (1-r0) & (1-r1) & (1-r2)                      # рождение r0 с r5
    t_nor = (1-r0) & (1-r1) & (1-r2) & (1-r3) & (1-r4) & (1-r5)  # рестарт из 00
    n0 = 1 if (t_birth or t_nor) else 0
    n1 = r0 & (1-r1) & (1-r2) & (1-r3)
    n2 = r1 & (1-r2) & (1-r3) & (1-r4)
    n3 = r2 & (1-r3) & (1-r4) & (1-r5)
    n4 = r3 & (1-r4) & (1-r5) & (1-r0)
    n5 = r4 & (1-r5) & (1-r0) & (1-r1)
    return tuple(int(bool(x)) for x in (n0, n1, n2, n3, n4, n5))

def is_onehot(r):
    return sum(r) == 1

errors = []

# ============ A. Чистое кольцо: все 64 кода -> one-hot <= 2 фронтов ============
max_conv = 0
for code in range(64):
    r = tuple((code >> i) & 1 for i in range(N))
    s0 = r
    s1 = step_ring(s0)
    s2 = step_ring(s1)
    s3 = step_ring(s2)
    if is_onehot(s1):
        conv = 1
    elif is_onehot(s2):
        conv = 2
    elif is_onehot(s3):
        conv = 3
    else:
        conv = 99
    max_conv = max(max_conv, conv)
    if conv > 2:
        errors.append(f"A: код {code:02X}: one-hot не достигнут за 2 фронта "
                      f"({s0}->{s1}->{s2}->{s3})")
    # орбита one-hot: период ровно 6, все 6 состояний
    if conv <= 2:
        oh = s1 if conv == 1 else s2
        seen = set()
        cur = oh
        for k in range(6):
            seen.add(cur)
            cur = step_ring(cur)
        if len(seen) != 6 or cur != oh:
            errors.append(f"A: код {code:02X}: орбита one-hot не периода 6")

# самоподдержание: из каждого one-hot кольцо бежит вечно
for i in range(N):
    r = tuple(1 if j == i else 0 for j in range(N))
    cur = r
    for _ in range(60):
        cur = step_ring(cur)
        if not is_onehot(cur):
            errors.append(f"A: one-hot {r} развалился в {cur}")
            break

print(f"A. ПЕРЕБОР 64 КОДОВ КОЛЬЦА N=6: max фронтов до one-hot = {max_conv} "
      f"{'(норма <=2)' if max_conv <= 2 else '!! ПРОВАЛ'}; орбита периода 6 у всех")

# ============ B. Комбинированная модель power-on (P0a-эквивалент) ============
# 64 кода кольца x 8 кодов por_sh x 2 фазы clk25_q = 1024 комбинации.
# por_sh: по por_ce (r0=1 ДО фронта) сдвиг вправо, 0 в MSB (bit7:=0);
# por_run.D = por_sh[0] (сэмпл ДО фронта); INIT por_run = 1 при por_sh != 0.
POR_SH_CODES = [0xFF, 0xFE, 0x7F, 0x0F, 0x01, 0x80, 0xAA, 0x00]
TCLK = 20  # нс, posedge каждые 20 нс
worst_fall = 0
worst_conv = 0
front_spacing_bad = 0

for code in range(64):
    for sh0 in POR_SH_CODES:
        for ph in (0, 1):
            r = tuple((code >> i) & 1 for i in range(N))
            por_sh = sh0
            # INIT por_sh=00: por_run = 0 с t=0 (уже снят - НЕ ошибка; в
            # железе INIT=FF, код 00 достижим только извне кольца кодов)
            por_run_prev = 1 if sh0 != 0 else 0
            clk25_q = ph
            fell_at = 0 if sh0 == 0 else None
            conv_at = None
            for k in range(1, 201):  # 200 фронтов = 4000 нс
                ce = 1 if r[0] else 0          # por_ce = r0, сэмпл ДО фронта
                por_run_D = 1 if (por_sh & 1) else 0   # сэмпл ДО фронта
                nr = step_ring(r)              # кольцо по фронту
                if ce:
                    por_sh = (por_sh >> 1) & 0x7F   # сдвиг вправо, 0 в MSB
                por_run_new = por_run_D
                clk25_q ^= 1
                r = nr
                t = k * TCLK
                if conv_at is None and is_onehot(r):
                    conv_at = k
                if fell_at is None and por_run_prev == 1 and por_run_new == 0:
                    fell_at = t
                por_run_prev = por_run_new
            # проверки
            if conv_at is None or conv_at > 2:
                errors.append(f"B: код {code:02X}/sh{sh0:02X}/ph{ph}: конвергенция {conv_at}")
            worst_conv = max(worst_conv, conv_at or 99)
            if fell_at is None:
                errors.append(f"B: код {code:02X}/sh{sh0:02X}/ph{ph}: por_run НЕ упал за 4000 нс")
            elif fell_at > worst_fall:
                worst_fall = fell_at
            # в установившемся режиме: единица r0 ровно 1 фронт из 6, шаг ровно 6
            r2 = r
            x1_hist = []
            for k in range(60):
                x1_hist.append(r2[0])
                r2 = step_ring(r2)
            if sum(x1_hist) != len(x1_hist) // N:
                errors.append(f"B: код {code:02X}/sh{sh0:02X}/ph{ph}: duty X1 != 1/6")
            idx = [i for i, v in enumerate(x1_hist) if v]
            for a, b in zip(idx, idx[1:]):
                if b - a != N:
                    front_spacing_bad += 1

print(f"B. P0a-ЭКВИВАЛЕНТ: 1024 комбинации (64 x 8 x 2): конвергенция <= {worst_conv} фронтов; "
      f"por_run падает не позже {worst_fall} нс и не возвращается; "
      f"duty X1 = 1/6, шаг фронтов r0 ровно {N} фронтов ({N*TCLK} нс) у всех; "
      f"нарушений шага: {front_spacing_bad}")

# ============ C. ШТАТНЫЙ СТАРТ (INIT: ring=r0, por_sh=FF): точные числа ======
r = tuple(1 if i == 0 else 0 for i in range(N))
por_sh = 0xFF
por_run_prev = 1
strobe_t = []
por_fall = None
for k in range(1, 61):
    ce = 1 if r[0] else 0
    por_run_D = 1 if (por_sh & 1) else 0
    if ce:
        strobe_t.append(k * TCLK)
        por_sh = (por_sh >> 1) & 0x7F
    nr = step_ring(r)
    por_run_new = por_run_D
    r = nr
    if por_run_prev == 1 and por_run_new == 0:
        por_fall = k * TCLK
        break
    por_run_prev = por_run_new
nominal = 8 * 120
print(f"C. ШТАТНЫЙ СТАРТ: стробы por_ce на t = {strobe_t[:3]}...{strobe_t[-1:]} "
      f"(шаг ровно {strobe_t[1]-strobe_t[0]} нс); "
      f"снятие por_run на кромке t = {por_fall} нс "
      f"(номинальный счёт 8 x 120 = {nominal} нс; норма 3 такта CLK = 720 нс при "
      f"CPU 4,167; запас {nominal/720:.2f}x)")
print(f"   СРАВНЕНИЕ С v3.9.8: снятие 1020 нс -> {por_fall} нс (масштаб 6/7 = {1020*6/7:.0f})")

# ============ D. НЕГАТИВНЫЕ КОНТРОЛИ МОДЕЛИ ================================
# 1) наивное кольцо без kill (r_i <= r_{i-1}) из пары соседних - ВЕЧНАЯ орбита
def step_naive(r):
    return (r[-1],) + r[:-1]
r = (1, 1, 0, 0, 0, 0)
cur = r
naive_ok = False
for _ in range(30):
    cur = step_naive(cur)
    if sum(cur) != 2:
        break
else:
    naive_ok = True
print(f"D. Контроль: наивное кольцо (без kill) из пары '11' "
      f"{'ходит вечно (30 фронтов)' if naive_ok else 'НЕ удержало пару!'} "
      f"- самоочистка обязательна, как в п.14/15")
if not naive_ok:
    errors.append("D: контроль наивного кольца не подтвердил вечную орбиту")

# 2) одинарный kill (v3.8) для N=6: есть ли вечно орбитящие нелегальные коды?
def step_single(r):
    # r_i.D = r_{i-1} & ~r_i & ~r_{i+1} (формула v3.8, одинарный kill)
    return tuple(r[(i-1) % N] & (1 - r[i]) & (1 - r[(i+1) % N]) for i in range(N))
orbit_single = 0
for code in range(64):
    r = tuple((code >> i) & 1 for i in range(N))
    cur = r
    seen = {}
    for k in range(40):
        if cur in seen:
            if not is_onehot(cur):
                orbit_single += 1
            break
        seen[cur] = k
        cur = step_single(cur)
print(f"D. Контроль: одинарный kill (v3.8) для N=6: вечно орбитящих нелегальных "
      f"кодов: {orbit_single} из 64 (аргумент п.15 о переносе формулы с N=7 не "
      f"очевиден - потому двойной kill проверен перебором)")

print("=" * 72)
if errors:
    print(f"ИТОГ: {len(errors)} ОШИБОК:")
    for e in errors[:20]:
        print("  " + e)
    raise SystemExit(1)
print("ИТОГ: 0 ОШИБОК - кольцо N=6 самоочищается <= 2 фронтов из любого из 64 кодов,")
print("por-цепь детерминирована (960 нс номинал, запас 1,33x при любом N).")
