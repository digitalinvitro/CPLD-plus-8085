#!/usr/bin/env python3
# v285_island_check.py - поведенческая проверка контракта таймера v28.5
# (П-5: tmr_cnt 6 -> 4 БИТА; решение владельца после фит-сессии 9).
# Семантика одновибратора та же (load / вниз до 0 / СТОП / ре-арм), но:
#   - INIT/RESET = 0Fh (15), N <= 15 (A[3:0]), период N x 4 мкс (4..60 мкс);
#   - слот monitor27 = 6 фронтов: N=14 -> 56 мкс x 6 = 336 мкс - КАДР ТОТ
#     ЖЕ 23.9/29.9 мс, что и при 6 битах; каденция стала CPU-независимой
#     (шаг 4 мкс - hardware-константа, единая для 3.125 и 2.5 МГц);
#   - ISR /6: налог 19.4% ЦП @3.125 / 24.3% @2.5 (было 6.5/8.2% при /2).
# 1 clk = 40 нс (clk 25 МГц); tick_step = 1 клк каждые 100 клк (4 мкс).

TICK = 100          # клк между tick_step
MASK = 0x0F         # П-5: 4 бита

class Island:
    def __init__(self, jitter=0):
        self.t = 0; self.jitter = jitter
        self.cnt = MASK; self.tick_q = 0; self.load_q = 0
        self.rst75 = 0; self.bus_reg = MASK; self.wr06_pending = None
        self.edges = []; self._prev = 0
    def out06(self, n, t=None):
        self.wr06_pending = (t if t is not None else self.t, n & MASK)  # A[3:0]
    def step(self):
        t = self.t
        tick_step = 0
        if self.jitter == 0:
            if t % TICK == TICK - 1:
                tick_step = 1
                self.next_tick = t + TICK
        else:
            if t >= self.next_tick:
                tick_step = 1
                self.next_tick = t + TICK + self.jitter()
        if self.wr06_pending and t == self.wr06_pending[0]:
            self.bus_reg = self.wr06_pending[1]
        self.load_q = 1 if (self.wr06_pending and t == self.wr06_pending[0]) else 0
        if self.wr06_pending and t == self.wr06_pending[0]: self.wr06_pending = None
        self.tick_q = tick_step
        self.rst75 = 1 if self.cnt == 0 else 0
        if self.load_q: self.cnt = self.bus_reg
        elif self.tick_q and not self.rst75: self.cnt = (self.cnt - 1) & MASK
        if self.rst75 and not self._prev: self.edges.append(t + 1)
        self._prev = self.rst75
        self.t += 1

ok = []
def chk(name, cond, detail=""):
    ok.append((name, cond)); print(("  PASS " if cond else "  FAIL ") + name + (" " + detail if detail else ""))

print("== Контракт острова v2.8.5 (П-5: 4 бита, N <= 15) ==")
# 1. RESET -> 0F: первый фронт = 15-й tick_step после загрузки (~60 мкс)
a = Island(); a.out06(MASK, 5)   # прошивка сразу перезагружает тем же 0F
for _ in range(4000): a.step()
e = a.edges[0] if a.edges else -1
nticks = (e - 1) // TICK - 5 // TICK
chk("RESET->0F: 1-й фронт на 15-м тике", nticks == 15,
    f"клк={e}, тиков после загрузки={nticks} (~60 мкс)")
chk("уровень держится после стопа (не пере-фронтирует)", len(a.edges) == 1, f"фронтов={len(a.edges)}")

# 2. OUT 06h,3 -> фронт через 3 тика
b = Island(); b.out06(3, 10)
for _ in range(2000): b.step()
e = b.edges[0] if b.edges else -1
nticks = (e - 1) // TICK - 10 // TICK
chk("N=3: фронт через N tick_step'ов", nticks == 3, f"клк={e}, тиков={nticks}")

# 3. OUT 06h,0 -> стоп + один защитный фронт
c = Island(); c.out06(0, 10)
for _ in range(5000): c.step()
chk("N=0: один защитный фронт, затем тишина", len(c.edges) == 1 and c.cnt == 0 and c.rst75 == 1,
    f"фронтов={len(c.edges)}, cnt={c.cnt}")

# 4. ре-арм после фронта: N=5 -> снова фронт через 5 тиков
d = Island(); d.out06(2, 10)
for _ in range(1500): d.step()
assert len(d.edges) == 1
d.out06(5, 1500)
for _ in range(1500): d.step()
nticks = (d.edges[1] - 1) // TICK - 1500 // TICK
chk("ре-арм N=5 после стопа: второй фронт через 5 тиков", len(d.edges) == 2 and nticks == 5,
    f"клк={d.edges[1] if len(d.edges)>1 else -1}, тиков={nticks}")

# 5. максимум диапазона: N=15 -> фронт через 15 тиков (60 мкс)
f_ = Island(); f_.out06(15, 10)
for _ in range(4000): f_.step()
nticks = (f_.edges[0] - 1) // TICK - 10 // TICK
chk("N=15 (макс): фронт через 15 тиков", nticks == 15, f"клк={f_.edges[0]}, тиков={nticks}")

# 6. A[7:4] игнорируются: OUT 06h,0xFF эквивалентен N=15
g = Island(); g.out06(0xFF, 10)
for _ in range(4000): g.step()
nticks = (g.edges[0] - 1) // TICK - 10 // TICK
chk("OUT 06h,0xFF -> N=15 (A[7:4] отброшены)", nticks == 15, f"клк={g.edges[0]}, тиков={nticks}")

# 7. джиттер базы (jam TX до 2 шагов): N=14, два цикла с ре-армом -> период 56+-16 мкс
import random; random.seed(1)
class IslJ(Island):
    """Джиттер базы по документу v2.7: фаза baud_tick блуждает в окне
    +-200 клк (=+-8 мкс, jam TX), шаг фазы +-50 клк (интервалы 50..150 клк)."""
    def __init__(s):
        super().__init__()
        random.seed(1)
        phi = 0; s.ticks = set()
        for k in range(1, 500):
            phi = max(-200, min(200, phi + random.choice([-50, 0, 50])))
            s.ticks.add(100 * k + phi)
    def out06(s, n, t=None): s.wr06_pending = (t if t is not None else s.t, n & MASK)
    def step(s):
        tick_step = 1 if s.t in s.ticks else 0
        if s.wr06_pending and s.t == s.wr06_pending[0]: s.bus_reg = s.wr06_pending[1]
        s.load_q = 1 if (s.wr06_pending and s.t == s.wr06_pending[0]) else 0
        if s.wr06_pending and s.t == s.wr06_pending[0]: s.wr06_pending = None
        s.tick_q = tick_step
        s.rst75 = 1 if s.cnt == 0 else 0
        if s.load_q: s.cnt = s.bus_reg
        elif s.tick_q and not s.rst75: s.cnt = (s.cnt - 1) & MASK
        if s.rst75 and not s._prev: s.edges.append(s.t + 1)
        s._prev = s.rst75
        s.t += 1
jj = IslJ(); jj.out06(14, 10)
last = 0
while len(jj.edges) < 2 and jj.t < 40000:
    jj.step()
    if len(jj.edges) > last:            # фронт -> ре-арм сразу после (как ISR)
        last = len(jj.edges)
        jj.out06(14, jj.t + 5)
if len(jj.edges) >= 2:
    per = (jj.edges[1] - jj.edges[0]) * 0.04  # мкс
    chk("джиттер базы: период N=14 в пределах 56+-16 мкс", abs(per - 56) <= 16.4, f"{per:.1f} мкс")
else:
    chk("джиттер базы: два фронта после ре-арма", False)

print("== Каденция monitor27 v1.2 (слот = 6 фронтов, ISR /6; слот CPU-независим) ==")
for cpu_mhz, T_ns in ((3.125, 320), (2.5, 400)):
    send = 74699 * T_ns / 1e6          # мс (посылка 2003 Б, пейсинг 36.75T/Б - CPU-зависима)
    shot = 14 * 4.0                    # мкс - фронт N=14 x 4 мкс = 56 (ОДИН для обоих CPU)
    slot = 6 * shot                    # 336 мкс - слот = 6 фронтов (ISR действует на каждый 6-й)
    isr_t = 34 * T_ns / 1000.0         # мкс - вход/выход ISR ~34T
    isr_pct = 6 * isr_t / slot * 100   # 6 входов ISR на слот (5 из них - только ре-арм)
    n_isr = int(round(send * 1000 / slot))
    fps = 1000.0 / (n_isr * slot / 1000.0) if n_isr else 0
    print(f"  CPU {cpu_mhz} МГц: посылка {send:.1f} мс, фронт {shot:.0f} мкс (N=14, шаг 4 мкс), "
          f"слот {slot:.0f} мкс, ISR-налог {isr_pct:.1f}% ЦП, кадр {n_isr} слотов = {fps:.1f} FPS")

print("ВЕРДИКТ:", "PASS (%d проверок)" % sum(1 for _, c in ok if c)
      if all(c for _, c in ok) else "FAIL")
