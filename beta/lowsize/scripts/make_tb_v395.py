#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_tb_v395.py (lowsize, 2026-11-05): tb_v394_diff.v -> tb_v395_diff.v
(дифсим v3.9.4 vs v3.9.5 - мера п.20: GSR-источник = cpu_rst = RST|por_run).

Метод адаптации: тело тб (после шапки) - сдвиг идентификаторов
394->395, 393->394 (в т.ч. dut393/dut394, имена проводов, иерархические
ссылки, строки печати); шапка переписана целиком; точечные правки
комментариев, где сдвиг даёт устаревший текст (por-цепи у обеих версий
теперь бит-в-бит, моменты снятия por_run СОВПАДАЮТ).
Запуск: python3 scripts/make_tb_v395.py (из beta/lowsize).
"""
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.normpath(os.path.join(HERE, ".."))
FIN  = os.path.join(SRC, "scripts", "tb_v394_diff.v")
FOUT = os.path.join(SRC, "scripts", "tb_v395_diff.v")

NEW_HEADER = """`timescale 1ns/1ps
//=====================================================================
// tb_v395_diff.v (lowsize, 2026-11-05): DIFFerencial'naya simulyaciya
// v3.9.4 vs v3.9.5 (defekt starta v3.9.3/v3.9.4 - zhaloba vladel'ca
// 11-5; mera p.20: GSR-istochnik rasshiren RST -> cpu_rst = RST|por_run,
// struktura p.18 sohranena). Metod: oba RTL v odnom testbenche,
// OBSHCHIJ stimul, sravnenie VSEH vyhodov i obeih shin kazhdye 5 ns
// (4-znachnaya logika ===). ETALON = v3.9.4 (fit 11-4 10:15PM, .jed
// chekpointa «zapasnaya proshivka»). Otlichiya ot tb_v394_diff.v:
//  1) POR-cepi u OBEIH bit-v-bit (M1 v obeih) - moment snjatija
//     por_run SOVPADAET (~1020 ns); okno sravneniya derzhitsya DO
//     KONCA bloka vrazhdebnyh plavanij (do 1200 ns, resinkhronizaciya
//     RST): v plavaniyah v3.9.4 vhodit s "startovym preimuschestvom"
//     brodeniya (FSM zhila vsyo POR), v3.9.5 - chistym iz IDLE,
//     traktorii pod plavajuschej shine razhodyatsya - ETO SVOJSTVO
//     MERY (imenno tot musor, kotoryj ubiraet fix), ne defekt;
//     pokrytie - cmp_hold_n;
//  2) RST-OKNA STROGO: povedenie sbrosa u obeih IDENTICHNO (uslovie
//     cpu_rst = RST|por_run pri por_run=0 daet tot zhe RST; znacheniya
//     sbrosnyh polej odni i te zhe) - okon maskirovki bol'she net,
//     lyuboe raskhozhdenie pri RST - defekt;
//  3) T0: ciklo-tochnaya proverka POR-cepi v3.9.5 po RTL (INIT F/1,
//     rovno 4 sdviga F->7->3->1->0, por_run >= 840 ns normy,
//     povtornogo POR net) - vhodit v verdikt; por-cepi v3.9.5 =
//     bit-v-bit v3.9.4 (delta p.20 ih NE trogaet).
// Ostal'noe - scenarii i spek-proverki tb_v394_diff.v bez izmenenij.
//====================================================================="""

def main():
    t = open(FIN, encoding="utf-8").read()
    lines = t.splitlines(keepends=True)
    # тело = после шапки (первая строка модуля tb_v394_diff и далее)
    idx = next(i for i, l in enumerate(lines) if l.startswith("module tb_v394_diff"))
    body = "".join(lines[idx:])
    # сдвиг идентификаторов: СНАЧАЛА 394->395, ПОТОМ 393->394
    body = body.replace("394", "395").replace("393", "394")
    # точечные правки упоминаний версий в комментариях/печати (сдвиг
    # "394"->"395" их НЕ трогает: в "v3.9.4" есть точки)
    vfix = [
        ("  // T0 (v3.9.4, M1): ciklo-tochnaya proverka POR-cepi dut395 po RTL:",
         "  // T0 (v3.9.5, M1): ciklo-tochnaya proverka POR-cepi dut395 po RTL:"),
        ("  // etalona v3.9.3 - 8 sdvigov (moment snjatija drugoj - OZHIDAEMO,\n  // eto i est' mera M1).",
         "  // por-cepi u obeih bit-v-bit (M1 v obeih): moment snjatija\n  // SOVPADAET, sdvigov rovno 4 u oboih."),
        ('$display("T0 PASS: por_run#vnis v3.9.4 na %0t ns (>= 840), sdvigov rovno 4 (F->7->3->1->0)", t_fall395);',
         '$display("T0 PASS: por_run#vnis v3.9.5 na %0t ns (>= 840), sdvigov rovno 4 (F->7->3->1->0)", t_fall395);'),
        ("  // v3.9.4: OKNO ASINHRONNOGO SBROSA. Pri RST=1 znachenija fiksirujutsya\n  // MGNOVENNO (etalon v3.9.3 - sync, na takt pozzhe), pri RST#vnis -\n  // snimajutsja MGNOVENNO (etalon - na takt pozzhe). Okno: ves' period\n  // RST=1 + 45 ns posle kroma RST#vnis - OZHIDAEMOE razlichie mery\n  // (ne defekt): sravnenie derzhitsya zakrytym.",
         "  // v3.9.5 i v3.9.4: sbros u obeih ASINHRONNYJ (GSR), uslovie pri\n  // por_run=0 odno i to zhe (RST), znacheniya sbrosnyh polej te zhe -\n  // povedenie BIT-V-BIT. Okon maskirovki vokrug RST NET (strahovochny\n  // komentar pervoistochnika udalen za nenuadnost'yu)."),
        ("  // v3.9.4: RST-okna STROGO (GSR u obeih identichen); zakryto tol'ko\n  // okno POR - moment snjatija por_run razlichaetsya po postroeniyu\n  // (M1: 4 sdviga protiv 8), +45 ns zapas na kromku posle snjatija.",
         "  // RST-okna STROGO (GSR u obeih identichen); zakryto tol'ko okno\n  // plavanij POR (do resinkhronizacii 1200 ns) - sm. cmp_hold."),
        ("  reg cmp_hold = 1'b1;        // start: okno POR (FAZA 0a)\n  integer cmp_hold_n = 0;     // pokrytie: propushhennye proverki\n  always @(rsti394 or rsti395) begin\n    if (cmp_hold && rsti394 === 1'b1 && rsti395 === 1'b1) begin\n      #45;\n      if (rsti394 === 1'b1 && rsti395 === 1'b1) cmp_hold = 1'b0;\n    end\n  end",
         "  reg cmp_hold = 1'b1;        // start: okno POR (FAZA 0a)\n  integer cmp_hold_n = 0;     // pokrytie: propushhennye proverki\n  // v395: POR-cepi obeih bit-v-bit (snimajutsya odnovremenno ~1020),\n  // NO okno derzhitsya do KONCA bloka vrazhdebnyh plavanij (1150 ns)\n  // i resinkhronizacii RST (1200 ns): v plavaniyah v3.9.4 vhodit s\n  // \"startovym preimuschestvom\" brodeniya (FSM zhila vsyo POR),\n  // v3.9.5 - chistym iz IDLE: traktorii pod odnoj plavajuschej shine\n  // razhodyatsya - ETO SVOJSTVO MERY (tot musor, kotoryj ubiraet\n  // fix), ne defekt; posle resinkhronizacii sravnenie strogoe.\n  always @(posedge clk) begin\n    if (cmp_hold && $time >= 1200 && rsti394 === 1'b1 && rsti395 === 1'b1)\n      cmp_hold = 1'b0;\n  end"),
        ('$display("ITOG dif-simulyacii v3.9.3 vs v3.9.4:");',
         '$display("ITOG dif-simulyacii v3.9.4 vs v3.9.5:");'),
        ('$display("  T0 POR (v3.9.4)          : sdvigov %0d, oshibok %0d", sh_cnt, t0_err);',
         '$display("  T0 POR (v3.9.5)          : sdvigov %0d, oshibok %0d", sh_cnt, t0_err);'),
        ('$display("=== EQUIVALENCE v3.9.4 == v3.9.3 CONFIRMED (differential sim + T0 POR) ===");',
         '$display("=== EQUIVALENCE v3.9.5 == v3.9.4 CONFIRMED (differential sim + T0 POR) ===");'),
        ('$display("!!! MISMATCHES PRESENT - v3.9.4 NOT EQUIVALENT TO v3.9.3 !!!");',
         '$display("!!! MISMATCHES PRESENT - v3.9.5 NOT EQUIVALENT TO v3.9.4 !!!");'),
        ('$display("RAM LOG: non-shadow tail DIFF: v3.9.3 %0d/%0d, v3.9.4 %0d/%0d", i2, n394, i3, n395);',
         '$display("RAM LOG: non-shadow tail DIFF: v3.9.4 %0d/%0d, v3.9.5 %0d/%0d", i2, n394, i3, n395);'),
        ('$display("  virtual RAM entries      : %0d (v3.9.3, teni %0d) / %0d (v3.9.4, teni %0d), ne-teni %s",',
         '$display("  virtual RAM entries      : %0d (v3.9.4, teni %0d) / %0d (v3.9.5, teni %0d), ne-teni %s",'),
        ('if (mism <= 50) $display("[%0t] MISMATCH %s: v3.9.3=%b v3.9.4=%b", $time, nm, a, b);',
         'if (mism <= 50) $display("[%0t] MISMATCH %s: v3.9.4=%b v3.9.5=%b", $time, nm, a, b);', 3),
        ("  // Spek-monitory (v3.9.4; zerkala v3.9.3 pokryvayutsya ravenstvom)",
         "  // Spek-monitory (v3.9.5; zerkala v3.9.4 pokryvayutsya ravenstvom)"),
        ("  // SPEC: /WE nizok, poka RESET_IN=0 - narushenie (v3.9.4, gate POR)",
         "  // SPEC: /WE nizok, poka RESET_IN=0 - narushenie (gate POR, obe)"),
        ('      $display("[%0t] SPEC FAIL: /WE=0 while RESET_IN=0 (POR-gate v3.9.4)", $time);',
         '      $display("[%0t] SPEC FAIL: /WE=0 while RESET_IN=0 (POR-gate)", $time);'),
        ('      $display("[%0t] SPEC FAIL: /WE=0 while RESET_IN=0 (etalon v3.9.3)", $time);',
         '      $display("[%0t] SPEC FAIL: /WE=0 while RESET_IN=0 (etalon v3.9.4)", $time);'),
        ("    // zapis OZU, zatem srazu IO-zapis s A15=1: v v3.9.3 wb_ram_q staying 1,\n    // no in_wb=0 -> CS_n=1; v3.9.4 obyazan vesti sebya tak zhe",
         "    // zapis OZU, zatem srazu IO-zapis s A15=1: istoricheskiy komment\n    // wb_ram_q (v3.9.3); v obeih tekuschih versiyah povedenie odinakovo"),
        ("    // to zhe u v3.9.3 - proveryaetsya ravenstvom)",
         "    // to zhe u etalona - proveryaetsya ravenstvom)"),
    ]
    for item in vfix:
        old, new = item[0], item[1]
        cnt = item[2] if len(item) > 2 else 1
        found = body.count(old)
        assert found == cnt, f"якорь найден {found} раз (ожидалось {cnt}): {old[:60]}"
        body = body.replace(old, new)
    out = NEW_HEADER + "\n" + body
    with open(FOUT, "w", encoding="utf-8") as f:
        f.write(out)
    # контроль: пары имён модулей
    assert "retro_pcld_top_v394" in out and "retro_pcld_top_v395" in out
    assert "module tb_v395_diff;" in out
    assert "retro_pcld_top_v393" not in out and "dut393" not in out and "394_diff" not in out.replace("tb_v394_diff", "")
    print("OK: tb_v395_diff.v записан (шапка переписана, тело сдвинуто 393->394->395)")

if __name__ == "__main__":
    main()
