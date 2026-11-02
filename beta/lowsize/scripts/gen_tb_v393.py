#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_tb_v393.py — адаптация диф-тестбенча tb_v392_diff.v (v3.9.1 vs v3.9.2)
в tb_v393_diff.v (v3.9.2 vs v3.9.3, линия lowsize, 2026-11-02).

v3.9.3 = сброс логики -> сеть GSR (п.18 шапки RTL). Отличия TB от
tb_v392_diff.v (всё остальное - сценарии и спецификации без изменений):
  1) OKNO SBROSA: при RST=1 и до 45 ns после кромки RST#вниз выходы
     могут отличаться на 0..40 ns (async GSR vs sync D-gating) -
     ОЖИДАЕМОЕ свойство меры: сравнение держится закрытым (cmp_hold,
     счётчик cmp_hold_n);
  2) FAZA 0a: враждебные «плавания» шины в окне POR (0..1040 ns,
     имитация «floated» линий CPU в RESET - управления/адрес/данные
     ВМ85А в 3-м состоянии): FSM v3.9.3 живой, гейт por_run на входе
     в writeback обязан держать /WE высокой; эталон v3.9.2 заморожен.
     Ресинхронизация после окна: вымывающий цикл чтения + нажатие RST
     (сброс пишет ВСЕ значения) - дальше сравнение строгое;
  3) SPEC: /WE НИКОГДА не низок, пока RESET_IN=0 (ОБЕ версии).

Метод: однопроходная замена ПО ТОКЕНАМ-ИДЕНТИФИКАТОРАМ (токен,
содержащий '392' -> '393'; иначе содержащий '39' -> '392'; числа не
трогаются), затем метки версий через плейсхолдеры, затем заголовок и
функциональные вставки по якорям (каждый якорь обязан быть 1 раз).

Использование: python3 gen_tb_v393.py
Создаёт: tb_v393_diff.v (UTF-8; текст - ASCII-транслит, как в v392).
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'tb_v392_diff.v')
DST = os.path.join(HERE, 'tb_v393_diff.v')

HEADER_NEW = """`timescale 1ns/1ps
//=====================================================================
// tb_v393_diff.v (lowsize, 2026-11-02): DIFFerencial'naya simulyaciya
// v3.9.2 vs v3.9.3 (sbros logiki -> SET' GSR, mera snizheniya resursov,
// p.18 shapki RTL). Metod: oba RTL v odnom testbenche, OBSHCHIJ stimul,
// sravnenie VSEH vyhodov i obeih shin kazhdye 5 ns (4-znachnaya logika
// ===). ETALON = v3.9.2 (prinyat vladelcem, fit 10-30 8:32PM). Novoe:
//  1) OKNO SBROSA: pri RST=1 i do 45 ns posle kroma RST#vnis vyhody
//     mogut otlichat'sya na 0..40 ns (async GSR vs sync D-gating) -
//     OZHIDAEMOE svojstvo mery, ne defekt: sravnenie derzhitsya
//     zakrytym (cmp_hold; pokrytie - smotchik cmp_hold_n);
//  2) FAZA 0a: vrazhdebnye "plavaniya" shiny v okne POR (0..1040 ns,
//     imitatsiya "floated" linij CPU v RESET - upravleniya/adres/
//     dannye VM85A v 3-m sostoyanii): FSM v3.9.3 zhivoj, gate por_run
//     na vhode v WB obyazan derzhat /WE vysokoj; etalon zamorozhen
//     sync-sbroson. Resinkhronizatsiya posle okna: vymyvayushchij
//     cikl chteniya + pressiya RST (sbros pishet VSE znacheniya);
//  3) SPEC: /WE NIKOGDA ne nizok, poka RESET_IN=0 (OBE versii).
// Ostal'noe - scenarii i spek-proverki tb_v392_diff.v bez izmenenij.
//=====================================================================
"""

# ------------------------------------------------------------- вставки
# (old, new, tag). Якоря - в ТЕКСТЕ ПОСЛЕ токен-прохода (эталон *_392,
# новый *_393). Каждый old обязан встречаться РОВНО ОДИН раз.
EDITS = []

# T1. Блок cmp_hold (после объявления a_chg393).
EDITS.append((
"  time    a_chg393 = 0;\n",
"""  time    a_chg393 = 0;

  //-------------------------------------------------------------------
  // v3.9.3: OKNO ASINHRONNOGO SBROSA. Pri RST=1 znachenija fiksirujutsya
  // MGNOVENNO (etalon v3.9.2 - sync, na takt pozzhe), pri RST#vnis -
  // snimajutsja MGNOVENNO (etalon - na takt pozzhe). Okno: ves' period
  // RST=1 + 45 ns posle kroma RST#vnis - OZHIDAEMOE razlichie mery
  // (ne defekt): sravnenie derzhitsya zakrytym.
  //-------------------------------------------------------------------
  reg cmp_hold = 1'b1;        // start: okno zhivogo FSM v POR (FAZA 0a)
  integer cmp_hold_n = 0;     // pokrytie: propushhennye proverki
  always @(posedge RST) cmp_hold = 1'b1;
  always @(negedge RST) begin
    #45;
    if (RST !== 1'b1) cmp_hold = 1'b0;
  end
""",
"cmp_hold"))

# T2. Заголовок chk_all - открытие if (cmp_hold).
EDITS.append((
"  task chk_all;\n    begin\n",
"""  task chk_all;
    begin
    if (cmp_hold) begin
      cmp_hold_n = cmp_hold_n + 1;
    end else begin
""",
"chk_all open"))

# T3. chk_all - закрытие else-ветки.
EDITS.append((
"      cmp8(D392,     D393,     \"D-bus\");\n    end\n  endtask",
"""      cmp8(D392,     D393,     "D-bus");
    end
    end
  endtask""",
"chk_all close"))

# T4. Враждебные плавания в окне POR + SPEC /WE-при-сбросе (после
# случайного инжектора SOD, перед задачами стимула).
EDITS.append((
"""  initial forever begin
    @(posedge clk); #1;
    if (rnd_sod_en && (($random(seed_sod) & 31) == 0)) SOD = ~SOD;
  end
""",
"""  initial forever begin
    @(posedge clk); #1;
    if (rnd_sod_en && (($random(seed_sod) & 31) == 0)) SOD = ~SOD;
  end

  //-------------------------------------------------------------------
  // v3.9.3 (p.18): vrazhdebnye "plavaniya" shiny v okne POR (0..1040 ns)
  // - imitatsiya "floated" linij CPU v RESET (upravlenija/adres/dannye
  // VM85A v 3-m sostoyanii). Etalon v3.9.2 v etom okne zamorozhen
  // sync-sbroson; FSM v3.9.3 zhivoj - gate por_run na vhode v WB obyazan
  // derzhat /WE vysoko. SPEC nizhe proveryaet OBE versii.
  //-------------------------------------------------------------------
  integer n_float = 0;
  integer seed_flt = 32'hF10A_7001;
  initial begin
    while ($time < 1040) begin
      @(posedge clk); #1;
      ALE = $random(seed_flt) & 1;
      WRn = $random(seed_flt) & 1;
      RDn = $random(seed_flt) & 1;
      IOM = $random(seed_flt) & 1;
      A15 = $random(seed_flt) & 1;
      n_float = n_float + 1;
    end
    ALE = 1'b0; WRn = 1'b1; RDn = 1'b1; IOM = 1'b0; A15 = 1'b0;
  end
  // SPEC: /WE nizok, poka RESET_IN=0 - narushenie (v3.9.3, gate POR)
  always @(negedge we393n) begin
    #1;
    if (rsti393 === 1'b0) begin
      specf = specf + 1;
      $display("[%0t] SPEC FAIL: /WE=0 while RESET_IN=0 (POR-gate v3.9.3)", $time);
    end
  end
  // SPEC: to zhe dlya etalona (zamorozhen - dolzhno byt tryvial'no)
  always @(negedge we392n) begin
    #1;
    if (rsti392 === 1'b0) begin
      specf = specf + 1;
      $display("[%0t] SPEC FAIL: /WE=0 while RESET_IN=0 (etalon v3.9.2)", $time);
    end
  end
""",
"float driver + WE spec"))

# T5. Main initial: FAZA 0a (ресинхронизация) перед FAZA 0.
EDITS.append((
"""  initial begin
    // ---------------- FAZA 0: POR i konstanty ----------------
    tick(40);                                     // 1600 ns: POR (1120 ns) zavershon
""",
"""  initial begin
    // ---------------- FAZA 0a: POR + vrazhdebnye plavaniya ------------
    // (FSM v3.9.3 zhivoj v okne POR - gate por_run; etalon zamorozhen.
    //  Razlichiya OZHIDAEMY, compare zakryt (cmp_hold=1 iznachal'no).
    //  Posle vymyvayushchego cikla chteniya i pressii RST mashiny
    //  resinkhronizuyutsya - dalshe sravnenie strogoe.)
    #1100;   // konec okna plavanij (driver zakonchil v 1040 ns)
    cyc(1'b0, 1'b0, 1'b0, 1'b1, 8'h00, 8'h00, 8'h00, 4, 2, 4); // vymyvayushchij cikl chteniya
    RST = 1'b1; last_rst_t = $time; n_rst_bursts = n_rst_bursts + 1;
    tick(2);
    RST = 1'b0;              // resinkhronizatsiya: sbros pishet VSE znacheniya
    tick(4);                 // zapas na okno 45 ns cmp_hold
    // ---------------- FAZA 0: POR i konstanty ----------------
    tick(40);                                     // vyderzhka posle resinkhronizatsii
""",
"FAZA 0a"))

# T6. Логи ОЗУ: бит-тень для записей, обрывающихся сбросом.
# Аборт /WE (reset посреди writeback) у v3.9.3 мгновенен (GSR), у v3.9.2 -
# на такт позже (sync): состояние шины через 1 ns после фронта WE#вверх
# отличается - записи-«тени» (WE#вверх < 300 ns после RST#вверх)
# ПОМЕЧАЮТСЯ и при сравнении ПРОПУСКАЮТСЯ (свойство меры п.18, не дефект).
# Обычные записи сравниваются парно, без пропусков.
EDITS.append((
"  reg [15:0] ramlog392  [0:16383];",
"  reg [16:0] ramlog392  [0:16383];  // bit16 = ten' (abort < 300 ns posle RST#vverh)",
"ramlog392 17bit"))
EDITS.append((
"  reg [15:0] ramlog393 [0:16383];",
"  reg [16:0] ramlog393 [0:16383];  // bit16 = ten' (abort < 300 ns posle RST#vverh)",
"ramlog393 17bit"))
EDITS.append((
"  integer n392 = 0, n393 = 0;",
"  integer n392 = 0, n393 = 0;\n  integer sh2 = 0, sh3 = 0;      // schetchiki tenjej (aborty)",
"shadow counters"))
EDITS.append((
"    if (cs392n === 1'b0) begin ramlog392[n392] = {A392, D392}; n392 = n392 + 1; end",
"    if (cs392n === 1'b0) begin\n      sh2 = sh2 + (($time - last_rst_t) < 300);\n      ramlog392[n392] = {($time - last_rst_t) < 300, A392, D392}; n392 = n392 + 1;\n    end",
"monitor 392 shadow"))
EDITS.append((
"    if (cs393n === 1'b0) begin ramlog393[n393] = {A393, D393}; n393 = n393 + 1; end",
"    if (cs393n === 1'b0) begin\n      sh3 = sh3 + (($time - last_rst_t) < 300);\n      ramlog393[n393] = {($time - last_rst_t) < 300, A393, D393}; n393 = n393 + 1;\n    end",
"monitor 393 shadow"))
EDITS.append((
"  integer i, j, k, q;",
"  integer i, j, k, q, i2, i3;",
"integer i2 i3"))
EDITS.append((
"""    logs_eq = (n392 === n393);
    if (logs_eq) begin
      for (j = 0; j < n392; j = j + 1)
        if (ramlog392[j] !== ramlog393[j]) begin logs_eq = 0; $display("RAM LOG DIFF @%0d: %h vs %h", j, ramlog392[j], ramlog393[j]); end
    end else begin
      $display("RAM LOG COUNT DIFF: v3.9.2=%0d v3.9.3=%0d", n392, n393);
    end
""",
"""    // Sravnenie logov OZU: teni (aborty v okne 300 ns posle RST#vverh)
    // propuskajutsya - moment obryva impulsa /WE otlichaetsja na 0..40 ns
    // (async GSR vs sync D-gating) - ozhidaemoe svojstvo mery p.18.
    // Obychnye zapisi sravnivajutsja PARNO, bez propuskov.
    logs_eq = 1;
    i2 = 0; i3 = 0;
    while (i2 < n392 && i3 < n393) begin
      if (ramlog392[i2][16]) begin i2 = i2 + 1; end
      else if (ramlog393[i3][16]) begin i3 = i3 + 1; end
      else begin
        if (ramlog392[i2][15:0] !== ramlog393[i3][15:0]) begin
          logs_eq = 0;
          $display("RAM LOG DIFF @%0d/%0d: %h vs %h", i2, i3, ramlog392[i2][15:0], ramlog393[i3][15:0]);
        end
        i2 = i2 + 1; i3 = i3 + 1;
      end
    end
    // hvost: teni v konce otbrosim, ne-teni - rassinhron (defekt)
    while (i2 < n392 && ramlog392[i2][16]) i2 = i2 + 1;
    while (i3 < n393 && ramlog393[i3][16]) i3 = i3 + 1;
    if (i2 !== n392 || i3 !== n393) begin
      logs_eq = 0;
      $display("RAM LOG: non-shadow tail DIFF: v3.9.2 %0d/%0d, v3.9.3 %0d/%0d", i2, n392, i3, n393);
    end
""",
"logs compare shadow-aware"))
EDITS.append((
"    $display(\"  virtual RAM entries      : %0d (v3.9.2) / %0d (v3.9.3), logs %s\",\n             n392, n393, logs_eq ? \"IDENTICAL\" : \"DIFFER\");",
"    $display(\"  virtual RAM entries      : %0d (v3.9.2, teni %0d) / %0d (v3.9.3, teni %0d), ne-teni %s\",\n             n392, sh2, n393, sh3, logs_eq ? \"IDENTICAL\" : \"DIFFER\");",
"ITOGI RAM display"))

# T7. ITOGI: новые счётчики.
EDITS.append((
"""    $display("  output/bus mismatches    : %0d", mism);
""",
"""    $display("  hostile float beats      : %0d (POR window)", n_float);
    $display("  compare-hold samples     : %0d (reset/POR windows)", cmp_hold_n);
    $display("  output/bus mismatches    : %0d", mism);
""",
"ITOGI"))


def tok_repl(m):
    t = m.group(0)
    if '392' in t:
        return t.replace('392', '393')
    if '391' in t:
        return t.replace('391', '392')
    return t


def main():
    s = io.open(SRC, encoding='utf-8').read()

    # 1) Токен-проход (идентификаторы; числа не матчатся).
    s = re.sub(r'\b[A-Za-z_]\w*\b', tok_repl, s)

    # 2) Метки версий через плейсхолдеры:
    #    v3.9.2 (новый в исходнике) -> v3.9.3; v3.9.1 и голое v3.9 -> v3.9.2.
    s = s.replace('v3.9.2', '\x01')
    s = s.replace('v3.9.1', '\x02')
    s = s.replace('v3.9', '\x02')
    s = s.replace('\x02', 'v3.9.2')
    s = s.replace('\x01', 'v3.9.3')

    # 3) Заголовок: всё до 'module tb_v393_diff;' заменить.
    anchor = 'module tb_v393_diff;'
    i = s.index(anchor)
    s = HEADER_NEW + s[i:]

    # 4) Функциональные вставки по якорям.
    for old, new, tag in EDITS:
        n = s.count(old)
        if n != 1:
            print('ОШИБКА: якорь %r встречается %d раз (ожидался 1)' % (tag, n))
            sys.exit(1)
        s = s.replace(old, new)
        print('ок: %s' % tag)

    # Контроль.
    assert 'retro_pcld_top_v393' in s, 'нет нового DUT v393'
    assert 'retro_pcld_top_v392' in s, 'нет эталона v392'
    assert re.search(r'retro_pcld_top_v39[^23]', s) is None, 'остался голый v39x'
    assert 'tb_v393_diff' in s and 'module tb_v392_diff' not in s
    assert 'cmp_hold' in s and s.count('cmp_hold_n = cmp_hold_n + 1') == 1
    assert 'negedge we393n' in s and 'negedge we392n' in s
    assert 'v3.9.2.2' not in s and '\x01' not in s and '\x02' not in s
    io.open(DST, 'w', encoding='utf-8', newline='').write(s)
    print('ок: tb_v393_diff.v сгенерирован (%d строк)' % s.count('\n'))


if __name__ == '__main__':
    main()
