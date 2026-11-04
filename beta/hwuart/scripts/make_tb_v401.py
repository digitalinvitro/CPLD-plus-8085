#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_tb_v401.py — генератор диф-тб: tb_v394_diff.v (lowsize) -> tb_v401_diff.v
(hwuart, 2026-11-05).

v4.0.1 = v4.0.0 + М1 (POR 8->4, строб x1_n, п.27 шапки RTL). ЭТАЛОН = v4.0.0
(RTL + симы 75/75; фит 3 - Placement Failed 11-4), кандидат - v4.0.1.
База сценариев - tb_v394_diff.v линий lowsize (шина, ALE-глюки, сбросы,
«плавания», виртуальные ОЗУ). Адаптация:
  1) переименования версий/идентификаторов (v3.9.4->v4.0.1 кандидат,
     v3.9.3->v4.0.0 эталон; dut394->dut401, dut393->dut400, суффиксы
     сигналов 394->401, 393->400; строки 'v3.9.x' не содержат '392'-'394');
  2) заголовок;
  3) rx_int (IRQ RST 7.5, P75 = rx_full) - провод, порт, cmp1 в общем цикле
     сравнения, спек в FAZA 0 (в lowsize P75 была PGND, сигнала нет);
  4) D13 низвергнут (TX-транзит v3.7 в hwuart ВЫПИЛЕН, SOD - наблюдатель):
     вместо него hwuart-сценарии: D13 TX-кадр OUT 04h 55h (старт-бит РОВНО
     520 нс, PC-приёмник декодирует, shreg сам в idle 1FF), D13c-e OUT при
     busy - тихий отброс, D14 RX 5Ah -> rx_full/IRQ -> IN 05h статус ->
     IN 04h байт -> чтение гасит IRQ; старый «долгий idle» -> D15;
  5) случайный инжектор RX-линии в фазе randoma (оба dut на одной линии);
  6) окно POR: момент снятия por_run ОЖИДАЕМО различается (4 сдвига
     против 8) - сравнение закрыто, пока хоть один dut в POR (+45 ns);
  7) RST-окна СТРОГО (GSR у обеих идентичен);
  8) T0: цикл-точная проверка POR-цепи v4.0.1 по RTL (INIT F/1, ровно 4
     сдвига F->7->3->1->0, por_run >= 840 нс, повторного POR нет).

Запуск: python3 scripts/make_tb_v401.py; затем scripts/run_tb_v401.sh.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = '/home/z/my-project/CPLD-plus-8085/beta/lowsize/scripts/tb_v394_diff.v'
OUT = os.path.join(HERE, 'tb_v401_diff.v')

HEADER = "\n".join([
"`timescale 1ns/1ps",
"//=====================================================================",
"// tb_v401_diff.v (hwuart, 2026-11-05): DIFFerencial'naya simulyaciya",
"// v4.0.0 vs v4.0.1 (POR-schetchik 8->4 so strobom x1_n - mera M1 iz",
"// lowsize v3.9.4, p.27 shapki RTL). Metod: oba RTL v odnom testbenche,",
"// OBSHCHIJ stimul, sravnenie VSEH vyhodov i obeih shin kazhdye 5 ns",
"// (4-znachnaya logika ===). ETALON = v4.0.0 (RTL + symy 75/75; fit 3",
"// Placement Failed 11-4). Baza scenariev - tb_v394_diff.v linii lowsize",
"// (shinnye cikly, ALE-glyuki, sbrosy v WB, vrazhdebnye plavaniya,",
"// virtual'nye OZU); dobavleno hwuart-spetsifichnoe:",
"//  - sravnenie rx_int (IRQ RST 7.5, P75 = rx_full) v obschem cikle;",
"//  - D13: TX-kadr OUT 04h 55h (start-bit ROVNO 520 ns, PC-priemnik",
"//    dekodiruet, shreg sam v idle 1FF); D13c-e: OUT pri busy - tihij",
"//    sbros (kadr TSel);",
"//  - D14: RX 5A -> rx_full/IRQ -> IN 05h status -> IN 04h bajt ->",
"//    chtenie gasit IRQ;",
"//  - sluchajnyj ingektor RX-linii v faze randoma (oba dut na odnoj",
"//    linii, sravnenie polnost'yu differencial'noe);",
"//  - OKNO POR: moment snjatija por_run OZHIDAEMO razlichaetsya",
"//    (v4.0.0 - 8 sdvigov por_ce, v4.0.1 - 4 sdviga so strobom x1_n) -",
"//    sravnenie derzhitsya zakrytym, poka hot' odin dut v POR (+45 ns",
"//    zapas na kromku); pokrytie - smotchik cmp_hold_n;",
"//  - RST-OKNA STROGO: povedenie sbrosa (async GSR, p.18) u obeih",
"//    versii IDENTICHNO - lyuboe raskhozhdenie pri RST - defekt;",
"//  - T0: ciklo-tochnaya proverka POR-cepi v4.0.1 po RTL (INIT F/1,",
"//    rovno 4 sdviga F->7->3->1->0, por_run >= 840 ns normy,",
"//    povtornogo POR net) - vhodit v verdikt.",
"// Zapusk: scripts/run_tb_v401.sh (Icarus 12.0 iz tools/iverilog).",
"//=====================================================================",
""])

# Каждый old обязан встречаться в ПЕРЕИМЕНОВАННОМ тексте РОВНО ОДИН раз.
EDITS = []

# E1. Провода rx_int у обоих dut.
EDITS.append((
"sid400, tx400, snd400, x2_400;",
"sid400, tx400, snd400, x2_400, ri400;",
"provod ri400"))
EDITS.append((
"sid401, tx401, snd401, x2_401;",
"sid401, tx401, snd401, x2_401, ri401;",
"provod ri401"))

# E2. Порты dut.
EDITS.append((
"    .SID(sid400), .TX(tx400), .seg(seg400), .dig(dig400), .SND(snd400),",
"    .SID(sid400), .TX(tx400), .rx_int(ri400), .seg(seg400), .dig(dig400), .SND(snd400),",
"port ri400"))
EDITS.append((
"    .SID(sid401), .TX(tx401), .seg(seg401), .dig(dig401), .SND(snd401),",
"    .SID(sid401), .TX(tx401), .rx_int(ri401), .seg(seg401), .dig(dig401), .SND(snd401),",
"port ri401"))

# E3. Сравнение rx_int в общем цикле.
EDITS.append((
'      cmp1(tx400,    tx401,    "TX");',
'      cmp1(tx400,    tx401,    "TX");\n'
'      cmp1(ri400,    ri401,    "rx_int");',
"cmp1 rx_int"))

# E4. Спек idle-IRQ в FAZA 0.
EDITS.append((
'    spec_chk(tx401  === 1\'b1,  "D1d TX=1 idle");',
'    spec_chk(tx401  === 1\'b1,  "D1d TX=1 idle");\n'
'    spec_chk(ri401  === 1\'b0,  "D1d2 rx_int=0 (no IRQ)");',
"spec D1d2"))

# E5. hwuart-хелперы: PC-приёмник TX, pc_send, io_rd - перед виртуальными ОЗУ.
HELPERS = """  //-------------------------------------------------------------------
  // hwuart: PC-priemnik TX-linii (kandidat v4.0.1; etalon pokryt
  // ravenstvom cmp1 TX), peredacha kadra PC->RX, chtenie IO-porta.
  //-------------------------------------------------------------------
  integer pc_byte = 0;
  event   pc_byte_ev;
  reg [7:0] val8;
  time    t_ri;

  // Standardnyj UART-priemnik 8N1, bit 520 ns (25 MGc/13): vyborki v
  // centrah bitov; fejkovyj start (liniya vernulas v '1' k centru) -
  // ignoriruetsya.
  always @(negedge tx401) begin : pc_rx
    integer i, b;
    begin
      #(520/2);
      if (tx401 === 1'b0) begin
        b = 0;
        for (i = 0; i < 8; i = i + 1) begin
          #(520);
          b = b | (tx401 << i);
        end
        #(520);
        pc_byte = b;
        -> pc_byte_ev;
      end
    end
  end

  task pc_send(input [7:0] byte);
    integer i;
    begin
      RX = 1'b0; #(520);                // start
      for (i = 0; i < 8; i = i + 1) begin
        RX = byte[i]; #(520);           // LSB first
      end
      RX = 1'b1; #(520);                // stop
    end
  endtask

  // IO-chtenie (mekhanizm KBROW): CPLD otdaet bajt na A-piny v T2.
  task io_rd(input [7:0] port, output [7:0] val);
    begin
      cpuA = port; cpuA_en = 1'b1; IOM = 1'b1; A15 = 1'b0; ALE = 1'b1;
      tick(4); ALE = 1'b0; RDn = 1'b0;
      tick(2);
      val = A401;                       // semypl pered RD#vverh
      tick(1); RDn = 1'b1; cpuA_en = 1'b0;
      tick(6);
    end
  endtask

  //-------------------------------------------------------------------
  // Virtualnye OZU: log fakticheskih zapisej (verh /WE pri aktivnom /CE)
  //-------------------------------------------------------------------
"""
EDITS.append((
"  //-------------------------------------------------------------------\n"
"  // Virtualnye OZU: log fakticheskih zapisej (verh /WE pri aktivnom /CE)\n"
"  //-------------------------------------------------------------------\n",
HELPERS,
"hwuart-helpers"))

# E6. D13: TX-транзит v3.7 -> hwuart-сценарии (кадр OUT 04h, busy-drop, RX).
D13 = """    // ---------------- D13 (hwuart): TX-kadr OUT 04h ---------------------
    // (v4.0.0/4.0.1: TX-tranzit v3.7 VYPILEN - SOD nablyudatel'. Kadr
    // startuet OUT 04h; start-bit ROVNO 520 ns - jam baud_cnt<=1;
    // PC-priemnik dekodiruet 55h; shreg sam v idle 1FF.)
    fork
      begin : tx_start55
        @(negedge tx401);
        tp1 = $time;
        @(posedge tx401);
        tp2 = $time;
        if ((tp2 - tp1) !== 520) begin
          specf = specf + 1;
          $display("[%0t] SPEC FAIL: TX start bit = %0t ns (expected 520)", $time, tp2 - tp1);
        end
      end
      begin
        cyc(1'b1, 1'b0, 1'b1, 1'b0, 8'h04, 8'h55, 8'h00, 4, 3, 4); // OUT 04h 55h
      end
    join
    fork
      begin : pc_wait55
        @(pc_byte_ev);
        if (pc_byte !== 8'h55) begin
          specf = specf + 1;
          $display("[%0t] SPEC FAIL: PC decoded %02h (expected 55)", $time, pc_byte);
        end
      end
      begin
        #(520*12);
      end
    join
    spec_chk(tx401 === 1'b1, "D13a TX idle '1' after frame");
    spec_chk(dut401.shreg === 9'h1FF, "D13b shreg self-idle all-ones");

    // ---------------- D13c-e (hwuart): OUT 04h pri busy ------------------
    // Zapis pri zanyatom yadre - bajt TIHO otbrasyvaetsya (kontrakt
    // poludupleksa): kadr C3 prohodit tselikom, 99h v terminal NE uhodit.
    cyc(1'b1, 1'b0, 1'b1, 1'b0, 8'h04, 8'hC3, 8'h00, 4, 3, 4); // kadr C3
    #(520);                        // vnutri kadra
    spec_chk(dut401.tx_run === 1'b1, "D13c frame active");
    cyc(1'b1, 1'b0, 1'b1, 1'b0, 8'h04, 8'h99, 8'h00, 4, 3, 4); // zapis pri busy
    #(520*11);
    spec_chk(pc_byte === 8'hC3, "D13d busy byte dropped, frame C3 intact");
    spec_chk(dut401.tx_run === 1'b0 && dut401.shreg === 9'h1FF, "D13e core idle after frame");

    // ---------------- D13f (hwuart): predchitanie statusa IN 05h ---------
    // VAZHNO: dekod io_rd_rx KOMBINATSIONNYJ ot zhivogo IOM i
    // zatshelknutogo addr_latch - posle OUT 04h on aktivnyj v KAZHDYJ tik
    // (IOM=1, addr_latch=04h) i Derzhit rx_full v nule, poka sledujushchij
    // cikl shiny ne smenit adres. Real'nyj firmware pered priemom polliruet
    // status (IN 05h) - delaem to zhe: dekod uhodit s 04h, rx_full
    // razreshaetsya. Poputno: TXRDY=1 (yadro v idle).
    io_rd(8'h05, val8);
    spec_chk(val8 === 8'h02, "D13f status TXRDY=1 before RX (decode off 04h)");

    // ---------------- D14 (hwuart): RX 5Ah -> IRQ -> IN 04h --------------
    // PC shit 5Ah; na stop-bite rx_full=1 -> rx_int (RST 7.5); IN 05h -
    // RXRDY=1; IN 04h - bajt 5A, chtenie gasit IRQ.
    t_ri = 0;
    fork
      begin : rx_irq
        @(posedge ri401);
        t_ri = $time;
      end
      begin
        pc_send(8'h5A);
      end
    join
    spec_chk(t_ri !== 0, "D14a rx_int (RST7.5) pulsed at stop");
    begin : rd_status_data
      io_rd(8'h05, val8);
      spec_chk(val8[0] === 1'b1, "D14b status RXRDY=1");
      io_rd(8'h04, val8);
      spec_chk(val8 === 8'h5A, "D14c IN 04h returns 5A");
      spec_chk(ri401 === 1'b0, "D14d read cleared IRQ");
    end
"""
EDITS.append((
"    // ---------------- D13: TX-zakhvat v3.7 -----------------------------\n"
"    SOD = 1'b1; tick(3);              // zakhvat po pervomu SOD='1'\n"
"    SOD = 1'b0; tick(2);\n"
"    spec_chk(tx401 === 1'b0, \"D13a TX=0 transit after capture\");\n"
"    SOD = 1'b1; tick(2);\n"
"    spec_chk(tx401 === 1'b1, \"D13b TX=1 transit back\");\n"
"    spec_chk(sid401 === RX, \"D13c SID=RX transit\");\n",
D13,
"D13 hwuart"))

# E7. Старый «долгий idle» D14 -> D15 (имя занято hwuart-RX-сценарием).
EDITS.append((
"    // ---------------- D14: dolgij idle -------------------------------",
"    // ---------------- D15: dolgij idle -------------------------------",
"D14->D15"))

# E8. Случайный инжектор RX-линии (после SOD-инжектора).
EDITS.append((
"  initial forever begin\n"
"    @(posedge clk); #1;\n"
"    if (rnd_sod_en && (($random(seed_sod) & 31) == 0)) SOD = ~SOD;\n"
"  end\n",
"  initial forever begin\n"
"    @(posedge clk); #1;\n"
"    if (rnd_sod_en && (($random(seed_sod) & 31) == 0)) SOD = ~SOD;\n"
"  end\n"
"\n"
"  // hwuart: sluchajnyj ingektor RX-linii (oba dut na odnoj linii;\n"
"  // priemnoe yadro uprazhnyaetsya musorom - glitki/lzhStarty/kadry,\n"
"  // vse raskhozhdeniya - defekt; pered itogami liniya dovoditsya\n"
"  // do idle).\n"
"  reg rnd_rx_en = 1'b0;\n"
"  integer seed_rx = 32'h5EED_0003;\n"
"  initial forever begin\n"
"    @(posedge clk); #1;\n"
"    if (rnd_rx_en && (($random(seed_rx) & 15) == 0)) RX = ~RX;\n"
"  end\n",
"ingektor RX"))

# E9. Включение инжектора в фазе randoma.
EDITS.append((
"    verbose = 1'b0;\n"
"    rnd_rst_en = 1'b1;\n"
"    rnd_sod_en = 1'b1;\n",
"    verbose = 1'b0;\n"
"    rnd_rst_en = 1'b1;\n"
"    rnd_sod_en = 1'b1;\n"
"    rnd_rx_en = 1'b1;\n",
"vklyuchenie rnd_rx"))

# E10. Выключение + доводка линии до idle.
EDITS.append((
"    rnd_rst_en = 1'b0;\n"
"    rnd_sod_en = 1'b0;\n",
"    rnd_rst_en = 1'b0;\n"
"    rnd_sod_en = 1'b0;\n"
"    rnd_rx_en = 1'b0;\n"
"    RX = 1'b1; #(520*12);   // dovesti nachatye kadry RX do kontsa (oba dut videli odnu liniyu)\n",
"vyklyuchenie rnd_rx"))

# E11. Итоги: строка hwuart-сценариев.
EDITS.append((
'    $display("  T0 POR (v4.0.1)          : sdvigov %0d, oshibok %0d", sh_cnt, t0_err);',
'    $display("  T0 POR (v4.0.1)          : sdvigov %0d, oshibok %0d", sh_cnt, t0_err);\n'
'    $display("  hwuart directed          : D13 TX 55h/busy-drop C3, D14 RX 5A -> IRQ");',
"itogi hwuart"))


def main():
    src = io.open(SRC, encoding='utf-8').read()

    # Шаг 1: переименования. Строки 'v3.9.x' не содержат подстрок
    # '392'/'393'/'394' (точки!) - версии переименовываем ЯВНО, затем
    # идентификаторы. Порядок: кандидат (394->401), потом эталон (393->400).
    s = src.replace('v3.9.4', 'v4.0.1').replace('v3.9.3', 'v4.0.0')
    s = s.replace('394', '401').replace('393', '400')
    print('ок: переименования (dut400=%d, dut401=%d)'
          % (s.count('dut400'), s.count('dut401')))
    if 'v3.9.' in s:
        print('ОШИБКА: осталось упоминание v3.9.x')
        sys.exit(1)

    # Шаг 2: заголовок (всё до module tb_v401_diff; заменяем).
    idx = s.find('module tb_v401_diff;')
    if idx < 0:
        print('ОШИБКА: не найден module tb_v401_diff;')
        sys.exit(1)
    s = HEADER + s[idx:]
    print('ок: заголовок')

    # Шаг 3: точечные правки.
    for old, new, tag in EDITS:
        n = s.count(old)
        if n != 1:
            print('ОШИБКА: якорь %r встречается %d раз (ожидался 1)' % (tag, n))
            sys.exit(1)
        s = s.replace(old, new)
        print('ок: %s' % tag)

    # Контроль: иерархические ссылки por-цепи только у dut401;
    # rx_int сравнивается; старые SOD-транзитные проверки исчезли.
    if s.count('dut401.por_sh') < 3 or s.count('dut401.por_run') < 2:
        print('ОШИБКА: T0-ссылки на por-цепь потеряны')
        sys.exit(1)
    if s.count('cmp1(ri400') != 1 or 'D13a TX idle' not in s or 'D14c IN 04h' not in s:
        print('ОШИБКА: hwuart-сценарии потеряны')
        sys.exit(1)
    if 'TX-zakhvat' in s or 'D13c SID=RX transit' in s:
        print('ОШИБКА: остался сценарий TX-транзита v3.7 (в hwuart выпилен)')
        sys.exit(1)
    print('ок: T0-ссылки и hwuart-сценарии на месте')

    io.open(OUT, 'w', encoding='utf-8', newline='').write(s)
    print('создано: %s (%d строк)' % (OUT, s.count('\n')))


if __name__ == '__main__':
    main()
