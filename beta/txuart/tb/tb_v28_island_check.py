#!/usr/bin/env python3
# v28_island_check.py - поведенческая проверка контракта таймера v28
# (модель RTL-семантики: tick_step/tmr_tick_q/tmr_load_q/tmr_cnt/RST75_r)
# + кадровость для monitor27 v1.2 при обоих вариантах часов CPU.
# 1 clk = 40 нс (clk 25 МГц); tick_step = 1 клк каждые 100 клк (4 мкс).

TICK = 100          # клк между tick_step
NCLK = 200000       # длительность основного теста

class Island:
    def __init__(self, jitter=0):
        self.t = 0; self.jitter = jitter
        self.cnt = 0xFF; self.tick_q = 0; self.load_q = 0
        self.rst75 = 0; self.bus_reg = 0xFF; self.wr06_pending = None
        self.edges = []; self._prev = 0
    def out06(self, n, t=None):
        self.wr06_pending = (t if t is not None else self.t, n)
    def step(self):
        t = self.t
        # tick_step: каждые 100 клк; с джиттером - сетка +-до 2 шагов (jam TX)
        tick_step = 0
        if self.jitter == 0:
            if t % TICK == TICK - 1:
                tick_step = 1
                self.next_tick = t + TICK
        else:
            if t >= self.next_tick:
                tick_step = 1
                self.next_tick = t + TICK + self.jitter()
        # OUT 06h: захват bus_reg на wr_cap, строб load тактом позже
        if self.wr06_pending and t == self.wr06_pending[0]:
            self.bus_reg = self.wr06_pending[1]
        self.load_q = 1 if (self.wr06_pending and t == self.wr06_pending[0]) else 0
        if self.wr06_pending and t == self.wr06_pending[0]: self.wr06_pending = None
        self.tick_q = tick_step
        # RST75_r <= (cnt == 0), кроме RESET
        self.rst75 = 1 if self.cnt == 0 else 0
        # счётчик
        if self.load_q: self.cnt = self.bus_reg
        elif self.tick_q and not self.rst75: self.cnt = (self.cnt - 1) & 0xFF
        # фронт RST75 (0->1) - то, что защёлкивает CPU
        if self.rst75 and not self._prev: self.edges.append(t + 1)
        self._prev = self.rst75
        self.t += 1

ok = []
def chk(name, cond, detail=""):
    ok.append((name, cond)); print(("  PASS " if cond else "  FAIL ") + name + (" " + detail if detail else ""))

print("== Контракт острова v2.8 (база 4 мкс, без джиттера) ==")
# 1. RESET -> FF: первый фронт = 255-й tick_step после загрузки (1,02 мс)
a = Island(); a.out06(0xFF, 5)   # прошивка сразу перезагружает тем же FF
for _ in range(40000): a.step()
e = a.edges[0] if a.edges else -1
nticks = (e - 1) // TICK - 5 // TICK   # число тиков между загрузкой (t=5) и фронтом
chk("RESET->FF: 1-й фронт на 255-м тике", nticks == 255,
    f"клк={e}, тиков после загрузки={nticks} (1,02 мс)")
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

# 5. джиттер базы (jam TX до 2 шагов): N=85, два цикла с ре-армом -> период 340+-8 мкс
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
    def out06(s, n, t=None): s.wr06_pending = (t if t is not None else s.t, n)
    def step(s):
        tick_step = 1 if s.t in s.ticks else 0
        if s.wr06_pending and s.t == s.wr06_pending[0]: s.bus_reg = s.wr06_pending[1]
        s.load_q = 1 if (s.wr06_pending and s.t == s.wr06_pending[0]) else 0
        if s.wr06_pending and s.t == s.wr06_pending[0]: s.wr06_pending = None
        s.tick_q = tick_step
        s.rst75 = 1 if s.cnt == 0 else 0
        if s.load_q: s.cnt = s.bus_reg
        elif s.tick_q and not s.rst75: s.cnt = (s.cnt - 1) & 0xFF
        if s.rst75 and not s._prev: s.edges.append(s.t + 1)
        s._prev = s.rst75
        s.t += 1
jj = IslJ(); jj.out06(85, 10)
last = 0
while len(jj.edges) < 2 and jj.t < 40000:
    jj.step()
    if len(jj.edges) > last:            # фронт -> ре-арм сразу после (как ISR)
        last = len(jj.edges)
        jj.out06(85, jj.t + 5)
if len(jj.edges) >= 2:
    per = (jj.edges[1] - jj.edges[0]) * 0.04  # мкс
    # граница модели: разность двух фаз из окна +-8 мкс = до +-16 мкс;
    # в реальном цикле каденции ре-арм попадает на чистую сетку (посылка
    # уже кончилась) -> фактически +-8 мкс, для счётчика ISR - <0,05%
    chk("джиттер базы: период N=85 в пределах 340+-16 мкс", abs(per - 340) <= 16.4, f"{per:.1f} мкс")
else:
    chk("джиттер базы: два фронта после ре-арма", False)

print("== Каденция monitor27 v1.2 (ISR-слот по таймеру) ==")
for cpu_mhz, T_ns in ((3.125, 320), (2.5, 400)):
    send = 74699 * T_ns / 1e6          # мс (посылка 2003 Б, пейсинг 36.75T/Б)
    slot_us = 1036 * T_ns / 1000       # мкс (слот скана)
    per = 255 * 4e-3                   # мс, ре-арм N=255
    isr_load = slot_us / 1000 / per * 100
    fps = 1000 / (46 * per)            # кадр = 46 ISR
    print(f"  CPU {cpu_mhz} МГц: посылка {send:.1f} мс, слот {slot_us:.0f} мкс, "
          f"ре-арм {per:.2f} мс, ISR-слот {isr_load:.0f}% ЦП, кадр 46 ISR = {fps:.1f} FPS")

nf = sum(1 for _, c in ok if not c)
print(f"ВЕРДИКТ: {'PASS' if nf == 0 else 'FAIL(%d)' % nf} ({len(ok)} проверок)")
