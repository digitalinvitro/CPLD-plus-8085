#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_v7_sim_tb.py — генератор верификационного комплекта txclient v7:
scripts/sim_txclient_v7.py (из sim_txclient_v6.py) и
scripts/tb_txclient_v7.v (из tb_txclient_v6.v).

Все сценарии v6 сохранены (норм-путь бит-в-бит v6), добавлены сценарии
п.24: GSR-сброс мгновенно (не на такт) и hostile-шина в окне POR
(гейты !por_run: ноль /WE, ноль HOLD, ноль TX).

Использование: python3 gen_v7_sim_tb.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ============================================================ SIM v7
SIM_SRC = os.path.join(HERE, 'sim_txclient_v6.py')
SIM_OUT = os.path.join(HERE, 'sim_txclient_v7.py')

SIM_EDITS = []

# S1. Докстринг: заголовок.
SIM_EDITS.append((
'"""sim_txclient_v6.py - верификация TXCLIENT v6 ДО фита (Icarus в песочнице\n'
'недоступен). Цикл-точная модель РОВНО по RTL beta/txclient/top_txclient_v6_utf8.v:',
'"""sim_txclient_v7.py - верификация TXCLIENT v7 ДО фита (Icarus в песочнице\n'
'недоступен). Цикл-точная модель РОВНО по RTL beta/txclient/top_txclient_v7_utf8.v\n'
'(v7 = v6 + СБРОС -> СЕТЬ GSR, п.24: ОБА always-блока асинхронные по RST,\n'
'cpu_rst удалён, ДВА гейта !por_run - вход в WB и взвод hold_req; por_run\n'
'смоделирован - dut.por_run, GSR-семантика сброса - dut.rst()):',
'S1 заголовок'))

# S2. Докстринг: сценарии - добавить v7-строку.
SIM_EDITS.append((
'бэку-ту-бэк, сброс в фазе захвата и посреди пакета, гейты CS в\n'
'tx_hold, границы окна BFFF (захват) и C000 (мимо)."""',
'бэку-ту-бэк, сброс в фазе захвата и посреди пакета, гейты CS в\n'
'tx_hold, границы окна BFFF (захват) и C000 (мимо).\n'
'НОВОЕ (v7, п.24): T8/T9 сброс = dut.rst() (GSR - МГНОВЕННО, ещё ДО\n'
'такта); T13 - hostile-«плавания» шины в окне POR (por_run=1): ноль /WE,\n'
'ноль HOLD, ноль TX-активности (гейты !por_run), после POR штатный пакет;\n'
'T14 - сброс посреди пакета гасит HOLD мгновенно (GSR, не на такт)."""',
'S2 сценарии'))

# S3. import random.
SIM_EDITS.append((
"BAUD_DIV = 13\nWIN_HI, WIN_LO = 0x8000, 0xBFFF   # окно захвата (п.22)",
"import random\n\nBAUD_DIV = 13\nWIN_HI, WIN_LO = 0x8000, 0xBFFF   # окно захвата (п.22)",
'S3 import random'))

# S4. DUT: por_run + метод rst().
SIM_EDITS.append((
"    def tick(self, ale, wrn, rdn, iom, a, d, ah, hl, s0, s1):",
"    def rst(self):\n"
"        \"\"\"v7 (п.24): GSR-сброс - АСИНХРОННЫЙ, мгновенный (не на такт):\n"
"        все 62 регистра логики и сериализатора в значения RST-ветки RTL\n"
"        (por_sh/por_run вне домена - в модели не ведутся). Выходные\n"
"        комбинационные сети обновляются сразу (HOLD = f(hold_req),\n"
"        TX = f(shreg, cap_run)).\"\"\"\n"
"        self.state, self.rd_seen, self.wr_seen = 0, 0, 0\n"
"        self.addr_latch, self.bus_reg = 0x00, 0x00\n"
"        self.hold_req = self.hlda_q = self.cap_run = 0\n"
"        self.tx_byte = self.bit_cnt = self.baud_cnt = 0\n"
"        self.shreg = 0x1FF\n"
"        self.adv_q = self.ld_q = 0\n"
"        self.hold = 0\n"
"        self.tx = 1\n"
"\n"
"    def tick(self, ale, wrn, rdn, iom, a, d, ah, hl, s0, s1):",
'S4 метод rst()'))

# S5. tick(): por_run в init DUT (поле).
SIM_EDITS.append((
"        self.cs_n = self.csr_n = self.we_n = self.oe_n = self.oer_n = 1\n"
"        self.hold = 0\n"
"        self.tx = 1\n"
"        self.ah = 0                       # последний сэмпл AH (для отладки)",
"        self.cs_n = self.csr_n = self.we_n = self.oe_n = self.oer_n = 1\n"
"        self.hold = 0\n"
"        self.tx = 1\n"
"        self.ah = 0                       # последний сэмпл AH (для отладки)\n"
"        self.por_run = 0                  # v7 (п.24): окно POR (1 = гейты активны)",
'S5 поле por_run'))

# S6. Гейт взвода hold_req.
SIM_EDITS.append((
"        if s == 1 and ale and win_hit: self.hold_req = 1",
"        # v7 (п.24): гейт POR - floated A/S0/S1 в окне POR не взводят\n"
"        # hold_req (иначе HOLD/HLDA в окне POR и мусорный кадр в TX)\n"
"        if s == 1 and ale and win_hit and not self.por_run: self.hold_req = 1",
'S6 гейт hold_req'))

# S7. Гейт входа в WB.
SIM_EDITS.append((
"                    ns = 3 if (not iom and (ah & 0x80)) else 0",
"                    # v7 (п.24): гейт POR - вход в WB запрещён (как v3.9.3)\n"
"                    ns = 3 if (not iom and (ah & 0x80) and not self.por_run) else 0",
'S7 гейт WB'))

# S8. T8: сброс = dut.rst() (мгновенно).
SIM_EDITS.append((
"# RST: cpu_rst = RST | por_run; в модели DUT нет RST -\n"
"# эмулируем прямой записью (синхронный сброс тех же регистров)\n"
"dut.state, dut.rd_seen, dut.wr_seen = 0, 0, 0\n"
"dut.hold_req = dut.hlda_q = dut.cap_run = 0\n"
"dut.tx_byte = dut.bit_cnt = dut.baud_cnt = 0\n"
"dut.shreg = 0x1FF\n"
"dut.adv_q = dut.ld_q = 0\n"
"bus.tick()\n"
"chk(\"T8: после сброса HOLD=0, cap_run=0, TX='1'\", dut.hold == 0 and dut.cap_run == 0 and dut.tx == 1)",
"# v7 (п.24): RST = асинхронный GSR-сброс (dut.rst() - мгновенно, не на такт)\n"
"dut.rst()\n"
"chk(\"T8: GSR мгновенно: HOLD=0, cap_run=0, TX='1' (ещё ДО такта)\",\n"
"    dut.hold == 0 and dut.cap_run == 0 and dut.tx == 1)\n"
"bus.tick()\n"
"chk(\"T8: после тика HOLD=0, cap_run=0, TX='1'\", dut.hold == 0 and dut.cap_run == 0 and dut.tx == 1)",
'S8 T8'))

# S9. T9: сброс = dut.rst() (мгновенно).
SIM_EDITS.append((
"dut.state, dut.rd_seen, dut.wr_seen = 0, 0, 0\n"
"dut.hold_req = dut.hlda_q = dut.cap_run = 0\n"
"dut.tx_byte = dut.bit_cnt = dut.baud_cnt = 0\n"
"dut.shreg = 0x1FF\n"
"dut.adv_q = dut.ld_q = 0\n"
"bus.tick()\n"
"chk(\"T9: после сброса HOLD=0 и TX='1'\", dut.hold == 0 and dut.tx == 1)",
"dut.rst()                                 # v7 (п.24): GSR мгновенно\n"
"chk(\"T9: GSR мгновенно: HOLD=0 и TX='1' (ещё ДО такта)\", dut.hold == 0 and dut.tx == 1)\n"
"bus.tick()\n"
"chk(\"T9: после тика HOLD=0 и TX='1'\", dut.hold == 0 and dut.tx == 1)",
'S9 T9'))

# S10. T13/T14 перед финалом.
SIM_EDITS.append((
"print()\n"
"print(\"ИТОГ:\", \"ВСЕ ПАСС\" if ok_all else \"ЕСТЬ ПРОВАЛЫ\")",
"""# ================= T13: hostile-шина В ОКНЕ POR (п.24) =================
# v7: FSM и сериализатор в окне POR ЖИВЫЕ (GSR не активен), шина CPU
# "floated" (ВМ85А: управления/адрес/данные в 3-м состоянии) - гейты
# !por_run обязаны держать ноль /WE (гейт S_T2->WB1), ноль HOLD (гейт
# взвода hold_req), ноль TX-активности (cap_run возможен только при
# hold_req=1). 3000 тактов случайных «плаваний» - методика sim_v393_gsr.py.
dut, bus = DUT(), None; bus = Bus(dut)
dut.por_run = 1
we_lo = hold_hi = tx_act = cap_se = hr_se = wb_se = 0
random.seed(20261103)
for _ in range(3000):
    bus.ale = random.randint(0, 1)
    bus.wrn = random.randint(0, 1)
    bus.rdn = random.randint(0, 1)
    bus.iom = random.randint(0, 1)
    bus.a, bus.ah = random.randint(0, 255), random.randint(0, 255)
    bus.s0, bus.s1 = random.randint(0, 1), random.randint(0, 1)
    bus.hl = random.randint(0, 1)
    bus.tick()
    we_lo += (bus.dut.we_n == 0)
    hold_hi += (bus.dut.hold == 1)
    tx_act += (bus.dut.tx == 0)
    cap_se += (bus.dut.cap_run == 1)
    hr_se += (bus.dut.hold_req == 1)
    wb_se += (bus.dut.state in (3, 4, 5, 6))
chk("T13: POR-окно: /WE НИКОГДА (гейт S_T2->WB1, п.24)", we_lo == 0, str(we_lo))
chk("T13: POR-окно: HOLD НИКОГДА (гейт взвода hold_req, п.24)", hold_hi == 0, str(hold_hi))
chk("T13: POR-окно: TX-активности НЕТ", tx_act == 0, str(tx_act))
chk("T13: POR-окно: cap_run/hold_req НИКОГДА", cap_se == 0 and hr_se == 0,
    "cap=%d hr=%d" % (cap_se, hr_se))
chk("T13: POR-окно: FSM живая (WB1..4 недостижимы)", wb_se == 0, str(wb_se))
dut.por_run = 0                            # POR кончился (por_run -> 0)
bus.idle(5)
bus.cycle(0x8012, 0x5A, write=1, label="post-por")
bus.idle(600)
fr = frames(bus.log_tx)
chk("T13: после POR штатная запись -> пакет [80][12][5A]",
    len(fr) == 3 and [f[1] for f in fr] == [0x80, 0x12, 0x5A],
    str([(hex(f[1]), f[3]) for f in fr[:4]]))
chk("T13: ОЗУ приняло запись", bus.mem.get(0x8012) == 0x5A)

# ================= T14: сброс посреди пакета - GSR МГНОВЕННО (п.24) =====
# В RTL сброс асинхронный (posedge clk or posedge RST): нажатие SW20 гасит
# FSM/пакет БЕЗ ожидания такта (v6 - на такт позже). Проверяем ДО такта.
dut, bus = DUT(), None; bus = Bus(dut); bus.idle(5)
bus.ah, bus.a, bus.iom = 0x80, 0x99, 0
bus.s0, bus.s1 = 1, 0
bus.ale, bus.wrn, bus.rdn = 1, 1, 1
for _ in range(T_T1): bus.tick()
bus.ale = 0; bus.a = 0x66; bus.wrn = 0
for _ in range(T_STROBE + 2): bus.tick()
bus.wrn = 1; bus.s0 = bus.s1 = 0; bus.tick()
for _ in range(2): bus.tick()
bus.hl = 1
for _ in range(40): bus.tick()
chk("T14: до сброса пакет идёт (tx_byte != IDLE, HOLD=1)",
    bus.dut.tx_byte != 0 and bus.dut.hold == 1,
    "txb=%d hold=%d" % (bus.dut.tx_byte, bus.dut.hold))
dut.rst()                                  # GSR: без такта
chk("T14: GSR мгновенно: HOLD=0, TX='1', state=IDLE, shreg=1FF (ДО такта)",
    dut.hold == 0 and dut.tx == 1 and dut.state == 0 and dut.shreg == 0x1FF)
bus.tick()
chk("T14: после тика состояние держится", dut.hold == 0 and dut.tx == 1 and dut.state == 0)
bus.hl = 0
bus.idle(20)

print()
print("ИТОГ:", "ВСЕ ПАСС" if ok_all else "ЕСТЬ ПРОВАЛЫ")""",
'S10 T13/T14'))

# ============================================================ TB v7
TB_SRC = os.path.join(HERE, 'tb_txclient_v6.v')
TB_OUT = os.path.join(HERE, 'tb_txclient_v7.v')

TB_EDITS = []

# B1. Шапка.
TB_EDITS.append((
"""//=====================================================================
// tb_txclient_v6.v - тестбенч TXCLIENT v6 (beta/txclient) для Icarus Verilog.
// В песочнице разработки iverilog недоступен - ПРОГНАТЬ У ВЛАДЕЛЬЦА:
//   iverilog -o tb_v6.vvp scripts/tb_txclient_v6.v top_txclient_v6_utf8.v
//   vvp tb_v6.vvp""",
"""//=====================================================================
// tb_txclient_v7.v - тестбенч TXCLIENT v7 (beta/txclient) для Icarus Verilog.
// В песочнице разработки iverilog недоступен - ПРОГНАТЬ У ВЛАДЕЛЬЦА:
//   iverilog -o tb_v7.vvp scripts/tb_txclient_v7.v top_txclient_v7_utf8.v
//   vvp tb_v7.vvp""",
'B1 шапка'))

# B2. Описание проверок.
TB_EDITS.append((
"""// - у v5 они оставались с данными записи; обнуление = признак именно v6).
// Порты/делитель/POR v3.9.2 не проверяются (там свой TB).""",
"""// обнуление = признак именно v6).
// НОВОЕ v7 (п.24, база v3.9.3/GSR): T6 - hostile-«плавания» шины в окне
// POR (force dut.por_run, LFSR-возбуждение 2000 тиков): гейты !por_run
// обязаны держать ноль /WE, ноль HOLD, ноль TX; после POR - штатный
// пакет [80][12][5A]; T7 - сброс ПОСРЕДИ ПАКЕТА: GSR гасит HOLD/TX
// МГНОВЕННО (до такта; v6 - на такт позже).
// Порты/делитель/POR v3.9.2 не проверяются (там свой TB).""",
'B2 описание'))

# B3. Имя модуля.
TB_EDITS.append(("module tb_txclient_v6();", "module tb_txclient_v7();", 'B3 модуль'))

# B4. Доп. объявления для T6/T7.
TB_EDITS.append((
"  integer f1_t, f2_t, f3_t, k, errors;\n"
"  reg fok; reg [7:0] fval;",
"  integer f1_t, f2_t, f3_t, k, errors;\n"
"  integer i6, n6, t6_mark, we0, h1, tx0, z6_0, z6_1, z6_2;  // v7 T6/T7\n"
"  reg [15:0] lfsr; reg fok6; reg [7:0] fval6;               // v7 T6\n"
"  reg fok; reg [7:0] fval;",
'B4 объявления'))

# B5. T6/T7 перед финалом.
TB_EDITS.append((
"""    if (errors == 0) $display("TXCLIENT v6 TB: ВСЕ ПАСС");
    else             $display("TXCLIENT v6 TB: ПРОВАЛОВ %0d", errors);
    $finish;""",
"""    // T6 (v7, п.24): hostile-«плавания» шины В ОКНЕ POR: FSM и
    // сериализатор живые (GSR не активен), гейты !por_run обязаны
    // держать ноль /WE, ноль HOLD, ноль TX-активности (модель -
    // sim_txclient_v7.py T13). Возбуждение - 16-бит LFSR (детерминизм).
    force dut.por_run = 1'b1;
    we0 = 0; h1 = 0; tx0 = 0; lfsr = 16'hACE1;
    for (i6 = 0; i6 < 2000; i6 = i6 + 1) begin
      lfsr = {lfsr[14:0], lfsr[15]^lfsr[13]^lfsr[12]^lfsr[10]};
      ALE  = lfsr[0]; WRn = lfsr[1]; RDn = lfsr[2]; IOM = lfsr[3];
      S0   = lfsr[4]; S1 = lfsr[5]; HLDA = lfsr[6];
      A    = lfsr[7:0]; AH = lfsr[15:8];
      tick;
      if (WE_n === 1'b0) we0 = we0 + 1;
      if (HOLD === 1'b1) h1  = h1 + 1;
      if (TX  === 1'b0) tx0 = tx0 + 1;
    end
    if (we0 !== 0 || h1 !== 0 || tx0 !== 0)
      begin $display("FAIL T6: POR-окно /WE=%0d HOLD=%0d TX0=%0d (гейты п.24)", we0, h1, tx0); errors = errors + 1; end
    release dut.por_run;
    ALE = 0; WRn = 1; RDn = 1; IOM = 0; S0 = 0; S1 = 0; HLDA = 0; A = 8'h00; AH = 8'h00;
    repeat (10) tick;
    t6_mark = t;
    // T6b: после POR штатная запись -> пакет [80][12][5A]
    cycle(16'h8012, 8'h5A, 1'b0, 1'b1);
    repeat (600) tick;
    n6 = 0; z6_0 = 0; z6_1 = 0; z6_2 = 0;
    for (k = 1; k < 8180; k = k + 1)
      if (k > t6_mark && tx_log[k] === 1'b0 && tx_log[k-1] === 1'b1) begin
        if (n6 == 0) z6_0 = k; else if (n6 == 1) z6_1 = k; else if (n6 == 2) z6_2 = k;
        n6 = n6 + 1;
      end
    if (n6 !== 3)
      begin $display("FAIL T6b: кадров %0d после POR (ожидалось 3)", n6); errors = errors + 1; end
    else begin
      frame_at(z6_0, fok6, fval6); if (!fok6 || fval6 !== 8'h80) begin $display("FAIL T6b: байт1=%h ok=%b", fval6, fok6); errors = errors + 1; end
      frame_at(z6_1, fok6, fval6); if (!fok6 || fval6 !== 8'h12) begin $display("FAIL T6b: байт2=%h ok=%b", fval6, fok6); errors = errors + 1; end
      frame_at(z6_2, fok6, fval6); if (!fok6 || fval6 !== 8'h5A) begin $display("FAIL T6b: байт3=%h ok=%b", fval6, fok6); errors = errors + 1; end
    end

    // T7 (v7, п.24): сброс ПОСРЕДИ ПАКЕТА - GSR МГНОВЕННО (до такта):
    // HOLD падает сразу, TX -> '1', shreg -> 1FF (v6 - на такт позже)
    AH = 8'h80; A = 8'h99; IOM = 0; S0 = 1; S1 = 0;
    ALE = 1; WRn = 1; RDn = 1;
    for (k = 0; k < T_T1; k = k + 1) tick;
    ALE = 0; A = 8'h66; WRn = 0;
    for (k = 0; k < T_STROBE + 2; k = k + 1) tick;
    WRn = 1; S0 = 0; S1 = 0; tick; tick;
    HLDA = 1;
    repeat (40) tick;
    if (dut.tx_byte === 2'd0 || HOLD !== 1'b1)
      begin $display("FAIL T7: пакет не идёт к моменту сброса (txb=%0d hold=%b)", dut.tx_byte, HOLD); errors = errors + 1; end
    RST = 1; #1;                               // GSR: асинхронно, БЕЗ такта
    if (HOLD !== 1'b0 || TX !== 1'b1 || dut.state !== 3'd0 || dut.shreg !== 9'h1FF || dut.hold_req !== 1'b0)
      begin $display("FAIL T7: GSR не мгновенный (hold=%b tx=%b state=%0d shreg=%h)", HOLD, TX, dut.state, dut.shreg); errors = errors + 1; end
    RST = 0; HLDA = 0; A = 8'h00; AH = 8'h00; S0 = 0; S1 = 0;
    repeat (10) tick;
    if (HOLD !== 1'b0 || TX !== 1'b1)
      begin $display("FAIL T7: после сброса активность (hold=%b tx=%b)", HOLD, TX); errors = errors + 1; end

    if (errors == 0) $display("TXCLIENT v7 TB: ВСЕ ПАСС");
    else             $display("TXCLIENT v7 TB: ПРОВАЛОВ %0d", errors);
    $finish;""",
'B5 T6/T7'))


def apply(path_src, path_out, edits, label):
    src = io.open(path_src, encoding='utf-8').read()
    s = src
    for old, new, tag in edits:
        n = s.count(old)
        if n != 1:
            print('ОШИБКА [%s]: якорь %r встречается %d раз (ожидался 1)' % (label, tag, n))
            sys.exit(1)
        s = s.replace(old, new)
        print('ок [%s]: %s' % (label, tag))
    io.open(path_out, 'w', encoding='utf-8', newline='').write(s)
    print('создан %s (%d строк)' % (path_out, s.count('\n') + 1))


def main():
    apply(SIM_SRC, SIM_OUT, SIM_EDITS, 'sim')
    apply(TB_SRC, TB_OUT, TB_EDITS, 'tb')


if __name__ == '__main__':
    main()
