#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_tb_v394.py — адаптер диф-тб: tb_v393_diff.v -> tb_v394_diff.v
(линия lowsize, 2026-11-05).

v3.9.4 = v3.9.3 + М1 (POR 8->4, строб x1_n). ЭТАЛОН диф-симуляции теперь
v3.9.3 (прошит и работает), кандидат - v3.9.4. Отличия адаптации:
  1) переименование версий (ЯВНЫЕ замены v3.9.3->v3.9.4, v3.9.2->v3.9.3 -
     строки 'v3.9.x' НЕ содержат подстрок '392'/'393'!) и идентификаторов
     (393->394, затем 392->393);
  2) заголовок;
  3) окно сравнения: RST-окна теперь СТРОГИЕ (поведение GSR у обеих
     версий идентично), закрыто ТОЛЬКО окно POR (момент снятия por_run
     ожидаемо отличается: 4 сдвига против 8);
  4) окно враждебных «плаваний» расширено 1040 -> 1150 ns (покрыть POR
     обеих версий при фазе clk этого тб);
  5) НОВОЕ T0: цикл-точная проверка POR-цепи v3.9.4 по RTL (INIT F/1,
     ровно 4 сдвига F->7->3->1->0, por_run >= 840 нс, повторного POR
     нет) - иерархические ссылки dut394.por_sh/por_run;
  6) итоги: T0 входит в вердикт.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'tb_v393_diff.v')
OUT = os.path.join(HERE, 'tb_v394_diff.v')

HDR1 = "`timescale 1ns/1ps"
Q = '"'

HEADER = "\n".join([
HDR1,
"//=====================================================================",
"// tb_v394_diff.v (lowsize, 2026-11-05): DIFFerencial'naya simulyaciya",
"// v3.9.3 vs v3.9.4 (POR-schetchik 8->4 so strobom x1_n - mera M1 iz",
"// txclient v8, p.19 shapki RTL). Metod: oba RTL v odnom testbenche,",
"// OBSHCHIJ stimul, sravnenie VSEH vyhodov i obeih shin kazhdye 5 ns",
"// (4-znachnaya logika ===). ETALON = v3.9.3 (prinyat vladelcem, fit",
"// 11-2 9:54PM, PROSHIT i rabotaet). Otlichiya ot tb_v393_diff.v:",
"//  1) OKNO POR: moment snjatija por_run OZHIDAEMO razlichaetsya",
"//     (v3.9.3 - 8 sdvigov por_ce, v3.9.4 - 4 sdviga so strobom x1_n) -",
"//     sravnenie derzhitsya zakrytym, poka hot' odin dut v POR (+45 ns",
"//     zapas na kromku); pokrytie - smotchik cmp_hold_n;",
"//  2) RST-OKNA STROGO: povedenie sbrosa (async GSR, p.18) u obeih",
"//     versii IDENTICHNO - okon maskirovki bol'she net, lyuboe",
"//     raskhozhdenie pri RST - defekt;",
"//  3) OKNO PLAVERNIJ rasshireno 1040 -> 1150 ns (pokryt' POR obeih",
"//     versij pri faze clk etogo tb; posle - vymyvayushchij cikl",
"//     chteniya + pressiya RST, resinkhronizatsiya);",
"//  4) T0: ciklo-tochnaya proverka POR-cepi v3.9.4 po RTL (INIT F/1,",
"//     rovno 4 sdviga F->7->3->1->0, por_run >= 840 ns normy,",
"//     povtornogo POR net) - vhodit v verdikt.",
"// Ostal'noe - scenarii i spek-proverki tb_v393_diff.v bez izmenenij.",
"//=====================================================================",
""])

# Каждый old обязан встречаться в переименованном тексте РОВНО ОДИН раз.
EDITS = []

# E1. Окно сравнения: RST-окна строгие, закрыто только POR.
EDITS.append((
"  reg cmp_hold = 1'b1;        // start: okno zhivogo FSM v POR (FAZA 0a)\n"
"  integer cmp_hold_n = 0;     // pokrytie: propushhennye proverki\n"
"  always @(posedge RST) cmp_hold = 1'b1;\n"
"  always @(negedge RST) begin\n"
"    #45;\n"
"    if (RST !== 1'b1) cmp_hold = 1'b0;\n"
"  end\n",
"  // v3.9.4: RST-okna STROGO (GSR u obeih identichen); zakryto tol'ko\n"
"  // okno POR - moment snjatija por_run razlichaetsya po postroeniyu\n"
"  // (M1: 4 sdviga protiv 8), +45 ns zapas na kromku posle snjatija.\n"
"  reg cmp_hold = 1'b1;        // start: okno POR (FAZA 0a)\n"
"  integer cmp_hold_n = 0;     // pokrytie: propushhennye proverki\n"
"  always @(rsti393 or rsti394) begin\n"
"    if (cmp_hold && rsti393 === 1'b1 && rsti394 === 1'b1) begin\n"
"      #45;\n"
"      if (rsti393 === 1'b1 && rsti394 === 1'b1) cmp_hold = 1'b0;\n"
"    end\n"
"  end\n",
"okno sravneniya"))

# E2. T0 - вставка перед счётчиками сравнения.
T0 = "\n".join([
"  //-------------------------------------------------------------------",
"  // T0 (v3.9.4, M1): ciklo-tochnaya proverka POR-cepi dut394 po RTL:",
"  // INIT por_sh=4'hF / por_run=1; rovno 4 sdviga F->7->3->1->0 (stroby",
"  // x1_n kazhdye 280 ns); por_run padaet posle 4-go sdviga i ne ran'she",
"  // normy 840 ns; povtornogo POR net (eshe 500 tikov tishiny). U",
"  // etalona v3.9.3 - 8 sdvigov (moment snjatija drugoj - OZHIDAEMO,",
"  // eto i est' mera M1).",
"  //-------------------------------------------------------------------",
"  integer t0_err = 0;",
"  integer sh_cnt = 0;",
"  reg [3:0] sh_prev = 4'hX;",
"  reg sh_zero = 1'b0;",
"  time  t_fall394 = 0;",
"  always @(dut394.por_sh) begin",
"    if (sh_zero) begin",
"      t0_err = t0_err + 1;  // izmenenie posle 0000 - povtornyj POR!",
"    end else if (sh_prev === 4'hX) begin",
"      // sobytie inicializacii (X -> INIT) na t=0 - ETO NE SDVIG",
"      if (dut394.por_sh !== 4'hF) t0_err = t0_err + 1;",
"      sh_prev = dut394.por_sh;",
"    end else begin",
"      if (sh_prev === 4'hF && dut394.por_sh !== 4'h7)      t0_err = t0_err + 1;",
"      else if (sh_prev === 4'h7 && dut394.por_sh !== 4'h3) t0_err = t0_err + 1;",
"      else if (sh_prev === 4'h3 && dut394.por_sh !== 4'h1) t0_err = t0_err + 1;",
"      else if (sh_prev === 4'h1 && dut394.por_sh !== 4'h0) t0_err = t0_err + 1;",
"      if (dut394.por_sh === 4'h0) sh_zero = 1'b1;",
"      sh_cnt = sh_cnt + 1;",
"      sh_prev = dut394.por_sh;",
"    end",
"  end",
"  always @(negedge dut394.por_run) t_fall394 = $time;",
"  initial begin",
"    #1;",
"    if (dut394.por_sh !== 4'hF) begin",
"      t0_err = t0_err + 1;",
"      $display(\"T0 FAIL: por_sh INIT=%h (expected F)\", dut394.por_sh);",
"    end",
"    if (dut394.por_run !== 1'b1) begin",
"      t0_err = t0_err + 1;",
"      $display(\"T0 FAIL: por_run INIT=%b (expected 1)\", dut394.por_run);",
"    end",
"    #1300;   // konec POR obeih versij + zapas",
"    if (sh_cnt !== 4) begin",
"      t0_err = t0_err + 1;",
"      $display(\"T0 FAIL: sdvigov por_sh %0d (expected 4)\", sh_cnt);",
"    end",
"    if (t_fall394 < 840) begin",
"      t0_err = t0_err + 1;",
"      $display(\"T0 FAIL: por_run padaet na %0t ns < normy 840\", t_fall394);",
"    end",
"    if (t0_err == 0)",
"      $display(\"T0 PASS: por_run#vnis v3.9.4 na %0t ns (>= 840), sdvigov rovno 4 (F->7->3->1->0)\", t_fall394);",
"    repeat (500) @(posedge clk);   // 20 mks: povtornogo POR byt' ne dolzhno",
"    if (dut394.por_run !== 1'b0 || dut394.por_sh !== 4'h0) begin",
"      t0_err = t0_err + 1;",
"      $display(\"T0 FAIL: povtornyj POR!\");",
"    end else if (t0_err == 0)",
"      $display(\"T0 PASS: povtornogo POR net (500 tikov)\");",
"  end",
"",
"  //-------------------------------------------------------------------",
"  // Schetchiki i sravnenie",
"  //-------------------------------------------------------------------",
])
EDITS.append((
"  //-------------------------------------------------------------------\n"
"  // Schetchiki i sravnenie\n"
"  //-------------------------------------------------------------------\n",
T0 + "\n",
"T0 POR-cep"))

# E3. Блок комментариев плаваний: обе версии живые (GSR у обеих).
EDITS.append((
"  // v3.9.4 (p.18): vrazhdebnye \"plavaniya\" shiny v okne POR (0..1040 ns)\n"
"  // - imitatsiya \"floated\" linij CPU v RESET (upravlenija/adres/dannye\n"
"  // VM85A v 3-m sostoyanii). Etalon v3.9.3 v etom okne zamorozhen\n"
"  // sync-sbroson; FSM v3.9.4 zhivoj - gate por_run na vhode v WB obyazan\n"
"  // derzhat /WE vysoko. SPEC nizhe proveryaet OBE versii.\n",
"  // OBE versii (p.18, GSR): vrazhdebnye \"plavaniya\" shiny v okne POR\n"
"  // (0..1150 ns) - imitatsiya \"floated\" linij CPU v RESET (upravleniya/\n"
"  // adres/dannye VM85A v 3-m sostoyanii). FSM v okne POR zhivoj u OBEIH\n"
"  // (GSR v okne ne aktiven), gate por_run na vhode v WB obyazan derzhat\n"
"  // /WE vysoko u OBEIH. SPEC nizhe proveryaet OBE versii.\n",
"zagolovok plavanij"))

# E4. Цикл плаваний.
EDITS.append((
"    while ($time < 1040) begin",
"    while ($time < 1150) begin",
"cikl plavanij"))

# E5. Конец окна в главном процессе.
EDITS.append((
"    #1100;   // konec okna plavanij (driver zakonchil v 1040 ns)",
"    #1200;   // konec okna plavanij (driver zakonchil v 1150 ns)",
"konec okna plavanij"))

# E6. FAZA 0a: обе версии живые.
EDITS.append((
"    // (FSM v3.9.4 zhivoj v okne POR - gate por_run; etalon zamorozhen.\n",
"    // (FSM OBEIH versii zhiv v okne POR - gate por_run p.18; sravnenie\n"
"    //  zakryto tol'ko iz-za momenta snjatija por_run (M1: 4 sdviga vs 8).\n",
"FAZA 0a"))

# E7. Итоги: строка T0.
EDITS.append((
"    $display(\"  compare-hold samples     : %0d (reset/POR windows)\", cmp_hold_n);",
"    $display(\"  compare-hold samples     : %0d (POR window)\", cmp_hold_n);\n"
"    $display(\"  T0 POR (v3.9.4)          : sdvigov %0d, oshibok %0d\", sh_cnt, t0_err);",
"itogi T0"))

# E8. Комментарий сравнения логов ОЗУ.
EDITS.append((
"    // Sravnenie logov OZU: teni (aborty v okne 300 ns posle RST#vverh)\n"
"    // propuskajutsya - moment obryva impulsa /WE otlichaetsja na 0..40 ns\n"
"    // (async GSR vs sync D-gating) - ozhidaemoe svojstvo mery p.18.\n"
"    // Obychnye zapisi sravnivajutsja PARNO, bez propuskov.\n",
"    // Sravnenie logov OZU: teni (aborty v okne 300 ns posle RST#vverh)\n"
"    // propuskajutsya (strakhovka; v tb_v394 GSR u obeih versii - teni\n"
"    // ozhidajutsya IDENTICHnymi, propusk ne dolzhen srabotat').\n"
"    // Obychnye zapisi sravnivajutsja PARNO, bez propuskov.\n",
"logi OZU"))

# E9. Вердикт: T0 входит в условие.
EDITS.append((
"    if (mism == 0 && specf == 0 && logs_eq)\n"
"      $display(\"=== EQUIVALENCE v3.9.4 == v3.9.3 CONFIRMED (differential sim) ===\");\n"
"    else\n"
"      $display(\"!!! MISMATCHES PRESENT - v3.9.4 NOT EQUIVALENT TO v3.9.3 !!!\");",
"    if (mism == 0 && specf == 0 && logs_eq && t0_err == 0)\n"
"      $display(\"=== EQUIVALENCE v3.9.4 == v3.9.3 CONFIRMED (differential sim + T0 POR) ===\");\n"
"    else\n"
"      $display(\"!!! MISMATCHES PRESENT - v3.9.4 NOT EQUIVALENT TO v3.9.3 !!!\");",
"verdikt"))


def main():
    src = io.open(SRC, encoding='utf-8').read()

    # Шаг 1: переименования. Строки 'v3.9.x' НЕ содержат подстрок
    # '392'/'393' (точки!) - версии переименовываем ЯВНО, затем
    # идентификаторы. Порядок: кандидат, потом эталон.
    s = src.replace('v3.9.3', 'v3.9.4').replace('v3.9.2', 'v3.9.3')
    s = s.replace('393', '394').replace('392', '393')
    print('ок: переименования (dut393=%d, dut394=%d)'
          % (s.count('dut393'), s.count('dut394')))
    if 'v3.9.2' in s:
        print('ОШИБКА: осталось упоминание v3.9.2')
        sys.exit(1)

    # Шаг 2: заголовок.
    idx = s.find('module tb_v394_diff;')
    if idx < 0:
        print('ОШИБКА: не найден module tb_v394_diff;')
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

    # Контроль: иерархические ссылки por-цепи только у dut394.
    if s.count('dut394.por_sh') < 3 or s.count('dut394.por_run') < 2:
        print('ОШИБКА: T0-ссылки на por-цепь потеряны')
        sys.exit(1)
    print('ок: T0-ссылки на месте')

    io.open(OUT, 'w', encoding='utf-8', newline='').write(s)
    print('создано: %s (%d строк)' % (OUT, s.count('\n')))


if __name__ == '__main__':
    main()
