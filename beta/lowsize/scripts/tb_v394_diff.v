`timescale 1ns/1ps
//=====================================================================
// tb_v394_diff.v (lowsize, 2026-11-05): DIFFerencial'naya simulyaciya
// v3.9.3 vs v3.9.4 (POR-schetchik 8->4 so strobom x1_n - mera M1 iz
// txclient v8, p.19 shapki RTL). Metod: oba RTL v odnom testbenche,
// OBSHCHIJ stimul, sravnenie VSEH vyhodov i obeih shin kazhdye 5 ns
// (4-znachnaya logika ===). ETALON = v3.9.3 (prinyat vladelcem, fit
// 11-2 9:54PM, PROSHIT i rabotaet). Otlichiya ot tb_v393_diff.v:
//  1) OKNO POR: moment snjatija por_run OZHIDAEMO razlichaetsya
//     (v3.9.3 - 8 sdvigov por_ce, v3.9.4 - 4 sdviga so strobom x1_n) -
//     sravnenie derzhitsya zakrytym, poka hot' odin dut v POR (+45 ns
//     zapas na kromku); pokrytie - smotchik cmp_hold_n;
//  2) RST-OKNA STROGO: povedenie sbrosa (async GSR, p.18) u obeih
//     versii IDENTICHNO - okon maskirovki bol'she net, lyuboe
//     raskhozhdenie pri RST - defekt;
//  3) OKNO PLAVERNIJ rasshireno 1040 -> 1150 ns (pokryt' POR obeih
//     versij pri faze clk etogo tb; posle - vymyvayushchij cikl
//     chteniya + pressiya RST, resinkhronizatsiya);
//  4) T0: ciklo-tochnaya proverka POR-cepi v3.9.4 po RTL (INIT F/1,
//     rovno 4 sdviga F->7->3->1->0, por_run >= 840 ns normy,
//     povtornogo POR net) - vhodit v verdikt.
// Ostal'noe - scenarii i spek-proverki tb_v393_diff.v bez izmenenij.
//=====================================================================
module tb_v394_diff;

  //-------------------------------------------------------------------
  // Takt 25 MGc
  //-------------------------------------------------------------------
  reg clk = 1'b0;
  always #20 clk = ~clk;                    // period 40 ns

  //-------------------------------------------------------------------
  // Obshchie vhody
  //-------------------------------------------------------------------
  reg RST = 1'b0, ALE = 1'b0, WRn = 1'b1, RDn = 1'b1, IOM = 1'b0, A15 = 1'b0;
  reg SOD = 1'b0, RX = 1'b1;
  reg RSTOUT = 1'b0, INTAn = 1'b1, HLDA = 1'b0, CLKOUT = 1'b0, S0 = 1'b0, S1 = 1'b0;
  reg AH8 = 1'b0, AH9 = 1'b0, AH10 = 1'b0, AH11 = 1'b0, AH12 = 1'b0, AH13 = 1'b0, AH14 = 1'b0;
  reg row0 = 1'b1, row1 = 1'b0, row2 = 1'b1, row3 = 1'b0, row4 = 1'b1;

  //-------------------------------------------------------------------
  // Razdelnye shiny; slabyj stimul CPU (adres/dannye) i pamyati (D)
  //-------------------------------------------------------------------
  wire [7:0] A393, A394, D393, D394;
  reg  [7:0] cpuA = 8'h00;   reg cpuA_en = 1'b0;
  reg  [7:0] memD = 8'h00;   reg memD_en = 1'b0;
  assign (weak0, weak1) A393  = cpuA_en ? cpuA : 8'hZZ;
  assign (weak0, weak1) A394 = cpuA_en ? cpuA : 8'hZZ;
  assign (weak0, weak1) D393  = memD_en ? memD : 8'hZZ;
  assign (weak0, weak1) D394 = memD_en ? memD : 8'hZZ;

  //-------------------------------------------------------------------
  // Vyhody
  //-------------------------------------------------------------------
  wire cs393r, oe393r, cs393n, oe393n, we393n, cs1_393, x1_393, rdy393, rsti393, sid393, tx393, snd393, x2_393;
  wire [7:0] seg393;  wire [3:0] dig393;  wire [3:0] col393;
  wire cs394r, oe394r, cs394n, oe394n, we394n, cs1_394, x1_394, rdy394, rsti394, sid394, tx394, snd394, x2_394;
  wire [7:0] seg394; wire [3:0] dig394; wire [3:0] col394;

  retro_pcld_top_v393 dut393 (
    .clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(A393), .D(D393),
    .CSr_n(cs393r), .OEr_n(oe393r), .CS_n(cs393n), .OE_n(oe393n), .WE_n(we393n), .CS1(cs1_393),
    .X1(x1_393), .READY(rdy393), .RESET_IN(rsti393),
    .SID(sid393), .TX(tx393), .seg(seg393), .dig(dig393), .SND(snd393),
    .X2(x2_393), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA),
    .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12), .AH13(AH13), .AH14(AH14),
    .RX(RX),
    .col0(col393[0]), .col1(col393[1]), .col2(col393[2]), .col3(col393[3]),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

  retro_pcld_top_v394 dut394 (
    .clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(A394), .D(D394),
    .CSr_n(cs394r), .OEr_n(oe394r), .CS_n(cs394n), .OE_n(oe394n), .WE_n(we394n), .CS1(cs1_394),
    .X1(x1_394), .READY(rdy394), .RESET_IN(rsti394),
    .SID(sid394), .TX(tx394), .seg(seg394), .dig(dig394), .SND(snd394),
    .X2(x2_394), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA),
    .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12), .AH13(AH13), .AH14(AH14),
    .RX(RX),
    .col0(col394[0]), .col1(col394[1]), .col2(col394[2]), .col3(col394[3]),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

  //-------------------------------------------------------------------
  // T0 (v3.9.4, M1): ciklo-tochnaya proverka POR-cepi dut394 po RTL:
  // INIT por_sh=4'hF / por_run=1; rovno 4 sdviga F->7->3->1->0 (stroby
  // x1_n kazhdye 280 ns); por_run padaet posle 4-go sdviga i ne ran'she
  // normy 840 ns; povtornogo POR net (eshe 500 tikov tishiny). U
  // etalona v3.9.3 - 8 sdvigov (moment snjatija drugoj - OZHIDAEMO,
  // eto i est' mera M1).
  //-------------------------------------------------------------------
  integer t0_err = 0;
  integer sh_cnt = 0;
  reg [3:0] sh_prev = 4'hX;
  reg sh_zero = 1'b0;
  time  t_fall394 = 0;
  always @(dut394.por_sh) begin
    if (sh_zero) begin
      t0_err = t0_err + 1;  // izmenenie posle 0000 - povtornyj POR!
    end else if (sh_prev === 4'hX) begin
      // sobytie inicializacii (X -> INIT) na t=0 - ETO NE SDVIG
      if (dut394.por_sh !== 4'hF) t0_err = t0_err + 1;
      sh_prev = dut394.por_sh;
    end else begin
      if (sh_prev === 4'hF && dut394.por_sh !== 4'h7)      t0_err = t0_err + 1;
      else if (sh_prev === 4'h7 && dut394.por_sh !== 4'h3) t0_err = t0_err + 1;
      else if (sh_prev === 4'h3 && dut394.por_sh !== 4'h1) t0_err = t0_err + 1;
      else if (sh_prev === 4'h1 && dut394.por_sh !== 4'h0) t0_err = t0_err + 1;
      if (dut394.por_sh === 4'h0) sh_zero = 1'b1;
      sh_cnt = sh_cnt + 1;
      sh_prev = dut394.por_sh;
    end
  end
  always @(negedge dut394.por_run) t_fall394 = $time;
  initial begin
    #1;
    if (dut394.por_sh !== 4'hF) begin
      t0_err = t0_err + 1;
      $display("T0 FAIL: por_sh INIT=%h (expected F)", dut394.por_sh);
    end
    if (dut394.por_run !== 1'b1) begin
      t0_err = t0_err + 1;
      $display("T0 FAIL: por_run INIT=%b (expected 1)", dut394.por_run);
    end
    #1300;   // konec POR obeih versij + zapas
    if (sh_cnt !== 4) begin
      t0_err = t0_err + 1;
      $display("T0 FAIL: sdvigov por_sh %0d (expected 4)", sh_cnt);
    end
    if (t_fall394 < 840) begin
      t0_err = t0_err + 1;
      $display("T0 FAIL: por_run padaet na %0t ns < normy 840", t_fall394);
    end
    if (t0_err == 0)
      $display("T0 PASS: por_run#vnis v3.9.4 na %0t ns (>= 840), sdvigov rovno 4 (F->7->3->1->0)", t_fall394);
    repeat (500) @(posedge clk);   // 20 mks: povtornogo POR byt' ne dolzhno
    if (dut394.por_run !== 1'b0 || dut394.por_sh !== 4'h0) begin
      t0_err = t0_err + 1;
      $display("T0 FAIL: povtornyj POR!");
    end else if (t0_err == 0)
      $display("T0 PASS: povtornogo POR net (500 tikov)");
  end

  //-------------------------------------------------------------------
  // Schetchiki i sravnenie
  //-------------------------------------------------------------------
  integer mism = 0;
  integer specf = 0;
  integer we_pulses = 0;
  integer rst_in_we = 0;          // sbrosov v okne nizkogo /WE
  time    we_t0 = 0;
  time    last_rst_t = -1000;
  time    a_chg394 = 0;

  //-------------------------------------------------------------------
  // v3.9.4: OKNO ASINHRONNOGO SBROSA. Pri RST=1 znachenija fiksirujutsya
  // MGNOVENNO (etalon v3.9.3 - sync, na takt pozzhe), pri RST#vnis -
  // snimajutsja MGNOVENNO (etalon - na takt pozzhe). Okno: ves' period
  // RST=1 + 45 ns posle kroma RST#vnis - OZHIDAEMOE razlichie mery
  // (ne defekt): sravnenie derzhitsya zakrytym.
  //-------------------------------------------------------------------
  // v3.9.4: RST-okna STROGO (GSR u obeih identichen); zakryto tol'ko
  // okno POR - moment snjatija por_run razlichaetsya po postroeniyu
  // (M1: 4 sdviga protiv 8), +45 ns zapas na kromku posle snjatija.
  reg cmp_hold = 1'b1;        // start: okno POR (FAZA 0a)
  integer cmp_hold_n = 0;     // pokrytie: propushhennye proverki
  always @(rsti393 or rsti394) begin
    if (cmp_hold && rsti393 === 1'b1 && rsti394 === 1'b1) begin
      #45;
      if (rsti393 === 1'b1 && rsti394 === 1'b1) cmp_hold = 1'b0;
    end
  end

  task cmp1(input a, input b, input [8*8-1:0] nm);
    begin
      if (a !== b) begin
        mism = mism + 1;
        if (mism <= 50) $display("[%0t] MISMATCH %s: v3.9.3=%b v3.9.4=%b", $time, nm, a, b);
      end
    end
  endtask

  task cmp4(input [3:0] a, input [3:0] b, input [8*8-1:0] nm);
    begin
      if (a !== b) begin
        mism = mism + 1;
        if (mism <= 50) $display("[%0t] MISMATCH %s: v3.9.3=%b v3.9.4=%b", $time, nm, a, b);
      end
    end
  endtask

  task cmp8(input [7:0] a, input [7:0] b, input [8*8-1:0] nm);
    begin
      if (a !== b) begin
        mism = mism + 1;
        if (mism <= 50) $display("[%0t] MISMATCH %s: v3.9.3=%b v3.9.4=%b", $time, nm, a, b);
      end
    end
  endtask

  task chk_all;
    begin
    if (cmp_hold) begin
      cmp_hold_n = cmp_hold_n + 1;
    end else begin
      cmp1(x1_393,   x1_394,   "X1");
      cmp1(x2_393,   x2_394,   "X2");
      cmp1(rsti393,  rsti394,  "RESET_IN");
      cmp1(rdy393,   rdy394,   "READY");
      cmp1(cs1_393,  cs1_394,  "CS1");
      cmp1(cs393r,   cs394r,   "CSr_n");
      cmp1(oe393r,   oe394r,   "OEr_n");
      cmp1(cs393n,   cs394n,   "CS_n");
      cmp1(oe393n,   oe394n,   "OE_n");
      cmp1(we393n,   we394n,   "WE_n");
      cmp1(sid393,   sid394,   "SID");
      cmp1(tx393,    tx394,    "TX");
      cmp1(snd393,   snd394,   "SND");
      cmp8(seg393,   seg394,   "seg");
      cmp4(dig393,   dig394,   "dig");
      cmp4(col393,   col394,   "col");
      cmp8(A393,     A394,     "A-bus");
      cmp8(D393,     D394,     "D-bus");
    end
    end
  endtask

  initial forever begin
    #5;
    chk_all;
  end

  task spec_chk(input cond, input [8*48-1:0] nm);
    begin
      if (cond !== 1'b1) begin
        specf = specf + 1;
        $display("[%0t] SPEC FAIL: %s", $time, nm);
      end
    end
  endtask

  //-------------------------------------------------------------------
  // Virtualnye OZU: log fakticheskih zapisej (verh /WE pri aktivnom /CE)
  //-------------------------------------------------------------------
  reg [16:0] ramlog393  [0:16383];  // bit16 = ten' (abort < 300 ns posle RST#vverh)
  reg [16:0] ramlog394 [0:16383];  // bit16 = ten' (abort < 300 ns posle RST#vverh)
  integer n393 = 0, n394 = 0;
  integer sh2 = 0, sh3 = 0;      // schetchiki tenjej (aborty)

  // Sembpl cherez 1 ns posle fronta WE#verh: k etomu momentu vse
  // combinacionnye znacheniya (CS/A/D) USTOYALIS (v tom chisle v sluchae
  // obryva impulsa sbrosom, kogda WE#verh i smena dekoda CS proishodyat
  // v odnoj delta-tsepi). Do sleduyuschego vozmozhnogo izmeneniya 20 ns.
  always @(posedge we393n) begin
    #1;
    if (cs393n === 1'b0) begin
      sh2 = sh2 + (($time - last_rst_t) < 300);
      ramlog393[n393] = {($time - last_rst_t) < 300, A393, D393}; n393 = n393 + 1;
    end
  end
  always @(posedge we394n) begin
    #1;
    if (cs394n === 1'b0) begin
      sh3 = sh3 + (($time - last_rst_t) < 300);
      ramlog394[n394] = {($time - last_rst_t) < 300, A394, D394}; n394 = n394 + 1;
    end
  end

  //-------------------------------------------------------------------
  // Spek-monitory (v3.9.4; zerkala v3.9.3 pokryvayutsya ravenstvom)
  //-------------------------------------------------------------------
  reg we_armed = 1'b0;   // otsech fantomnyj front X->1 v moment 0
  // shirina impulsa /WE = rovno 80 ns (glushitsya 300 ns posle sbrosa)
  always @(negedge we394n) begin we_t0 = $time; we_armed = 1'b1; end
  always @(posedge we394n) begin
    if (we_armed) begin
      we_pulses = we_pulses + 1;
      if (($time - we_t0) !== 80 && ($time - last_rst_t) > 300) begin
        specf = specf + 1;
        $display("[%0t] SPEC FAIL: WE width = %0t ns (expected 80)", $time, $time - we_t0);
      end
      we_armed = 1'b0;
    end
  end
  // t_AS: adres na A stabilen >= 40 ns do spada /WE
  always @(A394) a_chg394 = $time;
  always @(negedge we394n) begin
    if (we_armed && ($time - a_chg394) < 40 && ($time - last_rst_t) > 300) begin
      specf = specf + 1;
      $display("[%0t] SPEC FAIL: t_AS = %0t ns (< 40)", $time, $time - a_chg394);
    end
  end
  // svyazka: /WE=0 vlechet /CE=0
  always @(posedge clk) begin
    #1;
    if (we394n === 1'b0 && cs394n !== 1'b0) begin
      specf = specf + 1;
      $display("[%0t] SPEC FAIL: /WE=0 while /CE=1", $time);
    end
  end
  // schetchik sbrosov v okne /WE (pokrytie)
  always @(posedge clk) begin
    #1;
    if (RST === 1'b1 && we394n === 1'b0) rst_in_we = rst_in_we + 1;
  end

  //-------------------------------------------------------------------
  // Sluchajnye injektory (faza randoma): sbros i SOD
  //-------------------------------------------------------------------
  reg rnd_rst_en = 1'b0, rnd_sod_en = 1'b0;
  integer n_rst_bursts = 0;
  integer seed_rst = 32'h5EED_0001;
  integer seed_sod = 32'h5EED_0002;

  initial forever begin
    @(posedge clk); #1;
    if (rnd_rst_en && (($random(seed_rst) & 255) == 0)) begin
      RST = 1'b1; last_rst_t = $time; n_rst_bursts = n_rst_bursts + 1;
      repeat (1 + ($random(seed_rst) & 1)) @(posedge clk);
      #1 RST = 1'b0;
    end
  end

  initial forever begin
    @(posedge clk); #1;
    if (rnd_sod_en && (($random(seed_sod) & 31) == 0)) SOD = ~SOD;
  end

  //-------------------------------------------------------------------
  // OBE versii (p.18, GSR): vrazhdebnye "plavaniya" shiny v okne POR
  // (0..1150 ns) - imitatsiya "floated" linij CPU v RESET (upravleniya/
  // adres/dannye VM85A v 3-m sostoyanii). FSM v okne POR zhivoj u OBEIH
  // (GSR v okne ne aktiven), gate por_run na vhode v WB obyazan derzhat
  // /WE vysoko u OBEIH. SPEC nizhe proveryaet OBE versii.
  //-------------------------------------------------------------------
  integer n_float = 0;
  integer seed_flt = 32'hF10A_7001;
  initial begin
    while ($time < 1150) begin
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
  // SPEC: /WE nizok, poka RESET_IN=0 - narushenie (v3.9.4, gate POR)
  always @(negedge we394n) begin
    #1;
    if (rsti394 === 1'b0) begin
      specf = specf + 1;
      $display("[%0t] SPEC FAIL: /WE=0 while RESET_IN=0 (POR-gate v3.9.4)", $time);
    end
  end
  // SPEC: to zhe dlya etalona (zamorozhen - dolzhno byt tryvial'no)
  always @(negedge we393n) begin
    #1;
    if (rsti393 === 1'b0) begin
      specf = specf + 1;
      $display("[%0t] SPEC FAIL: /WE=0 while RESET_IN=0 (etalon v3.9.3)", $time);
    end
  end

  //-------------------------------------------------------------------
  // Stimul: tiki i shinnye cikly
  //-------------------------------------------------------------------
  task tick(input integer n);
    begin
      repeat (n) @(posedge clk);
      #1;
    end
  endtask

  // Polnyj shinnyj cikl: T1 (ALE=1, adres) + T2 (strob) + zazor.
  // do_wr/do_rd mogut byt lyubymi (v t.ch. oba/ni odnogo - glyuk-rezhim).
  task cyc(input iom_i, input a15_i, input do_wr, input do_rd,
           input [7:0] addr, input [7:0] wdata, input [7:0] rdata,
           input integer t_ale, input integer t_str, input integer t_gap);
    begin
      cpuA = addr; cpuA_en = 1'b1; IOM = iom_i; A15 = a15_i; ALE = 1'b1;
      if (!iom_i && do_rd) begin memD = rdata; memD_en = 1'b1; end
      tick(t_ale);
      ALE = 1'b0;
      if (do_wr) begin cpuA = wdata; WRn = 1'b0; end
      if (do_rd) begin RDn = 1'b0; end
      tick(t_str);
      if (do_wr) WRn = 1'b1;
      if (do_rd) RDn = 1'b1;
      cpuA_en = 1'b0;
      if (do_rd) begin memD_en = 1'b0; memD = 8'h00; end
      tick(t_gap);
      #1;   // ustupit monitoru loga OZU (on pishet na +1 ns ot WE#verh)
      if (verbose)
        $display("    [cyc iom=%b a15=%b wr=%b rd=%b adr=%h dt=%h] end: state=%0d al=%h br=%h n393=%0d wep=%0d",
                 iom_i, a15_i, do_wr, do_rd, addr, wdata, dut394.state, dut394.addr_latch, dut394.bus_reg, n393, we_pulses);
    end
  endtask

  // ALE-glyuk v T2 pri aktivnoj zapisi, dlitelnost glyuka 1 ili 2 tika.
  // 1 tik: chistyj abort - zapis NE dolzhna sluchitsya.
  // 2 tika: abort, no ALE derzhitsya do granicy -> FSM vozvrashaetsya
  //   IDLE->T1H->T2 i po WRn#verh zapis zavershaetsya SHtatno, s ISHODNYM
  //   adresom (zashchita p.6: addr_latch NE perezapisyvaetsya, ALE umiraet
  //   do pervogo zakhvata v T1H). Zapis NE teryaetsya i NE iskazhaetsya.
  task cyc_glitch_ale(input integer glen, input [7:0] addr, input [7:0] wdata);
    begin
      cpuA = addr; cpuA_en = 1'b1; IOM = 1'b0; A15 = 1'b1; ALE = 1'b1;
      tick(4);
      ALE = 1'b0;
      tick(1);
      cpuA = wdata; WRn = 1'b0;
      tick(1);
      ALE = 1'b1;                       // GLYUK: ALE pri nizkom WRn v T2
      tick(glen);
      ALE = 1'b0;
      tick(2);
      WRn = 1'b1; cpuA_en = 1'b0;
      tick(8);
    end
  endtask

  // Zapis OZU so sbrosom posredi WB: phase 0..3 = sbros v WB1..WB4
  task cyc_rst_in_wb(input integer phase, input [7:0] addr, input [7:0] wdata);
    begin
      cpuA = addr; cpuA_en = 1'b1; IOM = 1'b0; A15 = 1'b1; ALE = 1'b1;
      tick(4);
      ALE = 1'b0;
      cpuA = wdata; WRn = 1'b0;
      tick(3);
      WRn = 1'b1; cpuA_en = 1'b0;       // zapis zavershena -> sleduyuschaya kromka = WB1
      tick(phase);                      // 0 -> WB1, 1 -> WB2, 2 -> WB3, 3 -> WB4
      RST = 1'b1; last_rst_t = $time;   // sbros posredi WB
      tick(2);
      RST = 1'b0;
      tick(8);
    end
  endtask

  //-------------------------------------------------------------------
  // Osnovnoj process: napravlennye scenarii + random
  //-------------------------------------------------------------------
  integer i, j, k, q, i2, i3;
  integer we_cnt0, nlog0, seg_ok, we_before;
  time    tp1, tp2;
  integer seed = 32'hC0FF_EE01;
  integer ty;
  reg [7:0] ad, dt, rdt;
  integer t_ale, t_str, t_gap;
  integer n_cyc_rnd = 0, n_wram = 0, n_wio = 0, n_wrom = 0, n_rdall = 0, n_glitch = 0;
  integer logs_eq;
  reg verbose = 1'b1;             // tressirovka cyc - tolko v napravlennyh scenariyah

  initial begin
    // ---------------- FAZA 0a: POR + vrazhdebnye plavaniya ------------
    // (FSM OBEIH versii zhiv v okne POR - gate por_run p.18; sravnenie
    //  zakryto tol'ko iz-za momenta snjatija por_run (M1: 4 sdviga vs 8).
    //  Razlichiya OZHIDAEMY, compare zakryt (cmp_hold=1 iznachal'no).
    //  Posle vymyvayushchego cikla chteniya i pressii RST mashiny
    //  resinkhronizuyutsya - dalshe sravnenie strogoe.)
    #1200;   // konec okna plavanij (driver zakonchil v 1150 ns)
    cyc(1'b0, 1'b0, 1'b0, 1'b1, 8'h00, 8'h00, 8'h00, 4, 2, 4); // vymyvayushchij cikl chteniya
    RST = 1'b1; last_rst_t = $time; n_rst_bursts = n_rst_bursts + 1;
    tick(2);
    RST = 1'b0;              // resinkhronizatsiya: sbros pishet VSE znacheniya
    tick(4);                 // zapas na okno 45 ns cmp_hold
    // ---------------- FAZA 0: POR i konstanty ----------------
    tick(40);                                     // vyderzhka posle resinkhronizatsii
    spec_chk(rsti394 === 1'b1, "D1a RESET_IN=1 after POR");
    spec_chk(cs1_394 === 1'b1, "D1b CS1=1");
    spec_chk(rdy394 === 1'b1,  "D1c READY=1");
    spec_chk(tx394  === 1'b1,  "D1d TX=1 idle");
    spec_chk(seg394 === 8'h00, "D1e seg all on (8888.)");
    spec_chk(dig394 === 4'b0000, "D1f all digits active");
    // period X1: 10 periodov = 1400 ns
    @(posedge x1_394); tp1 = $time;
    repeat (10) @(posedge x1_394);
    tp2 = $time;
    if ((tp2 - tp1) !== 1400) begin
      specf = specf + 1;
      $display("[%0t] SPEC FAIL: 10 periods of X1 = %0t ns (expected 1400)", $time, tp2 - tp1);
    end
    // X2 = ~X1 na setke 10 ns (2 mks)
    for (q = 0; q < 200; q = q + 1) begin
      #10;
      if (x2_394 !== ~x1_394) begin
        specf = specf + 1;
        $display("[%0t] SPEC FAIL: X2 != ~X1", $time);
      end
    end

    // ---------------- D2: zapis OZU + smena adresa posredi WB (p.5) --
    // (a) zapis 77<-A5; posle WRn#verh - srazu novyj «cikl» s A15=0
    //     (PZU-adres): CS_n v WB1..WB4 obyazan derzhatsya 0 BEZ decoda
    we_before = we_pulses;
    nlog0 = n393;
    cpuA = 8'h77; cpuA_en = 1'b1; IOM = 1'b0; A15 = 1'b1; ALE = 1'b1;
    tick(4);
    ALE = 1'b0;
    cpuA = 8'hA5; WRn = 1'b0;
    tick(3);
    // VAZHNO: A15/IOM dolzhny derzhatsya STARYMI do kromki zaversheniya
    // zapisi (front WB1 sampliruet !IOM&&A15); novyj cikl - tolko POSLE
    // etoj kromki (takt na WB1), kak na realnoj plate (CPU menyaet shim
    // v sleduyushchem cikle, ne v techenie tekushchego)
    WRn = 1'b1;                                   // kromka zaversheniya -> WB1
    tick(1);                                      // teper FSM v WB1 (A15 esche =1)
    cpuA = 8'h12; A15 = 1'b0; ALE = 1'b1;         // novyj cikl PZU pri active WB
    tick(1);                                      // WB1->WB2: /WE nizkij, A15=0 uzhe 1 tik
    spec_chk(cs394n === 1'b0, "D2a CS_n=0 in WB2 despite new ROM addr");
    spec_chk(we394n === 1'b0, "D2b WE_n=0 in WB2 (pulse in progress)");
    tick(2);                                      // WB3, WB4 (WE verh na WB4)
    spec_chk(cs394n === 1'b0, "D2c CS_n=0 vse esche (WB4)");
    spec_chk(we394n === 1'b1, "D2d WE_n=1 in WB4 (pulse done)");
    ALE = 1'b0; cpuA_en = 1'b0;
    tick(4);                                      // WB zavershen, vsyo snyato
    spec_chk(we_pulses == we_before + 1, "D2f exactly one WE pulse");
    spec_chk(n393 == nlog0 + 1, "D2g RAM log +1");
    spec_chk(ramlog393[nlog0] === {8'h77, 8'hA5}, "D2h RAM got 77<-A5");
    // (b) normalnyj cikl chteniya PZU: dekod vosstanovlen (CS_n=1);
    // t_ale=5: zakhvat trebuetsya v T1H (ALE dolzhen perezhit vhod v T1H)
    cpuA = 8'h12; cpuA_en = 1'b1; IOM = 1'b0; A15 = 1'b0; ALE = 1'b1;
    memD = 8'h5E; memD_en = 1'b1;
    tick(5); ALE = 1'b0; RDn = 1'b0;
    tick(2);
    spec_chk(cs394n === 1'b1, "D2i CS_n=1 on ROM read after WB (decode resumed)");
    spec_chk(cs394r === 1'b0, "D2j CSr_n=0 on ROM read");
    spec_chk(A394 === 8'h5E,  "D2k ROM data on A in T2");
    tick(1); RDn = 1'b1; cpuA_en = 1'b0; memD_en = 1'b0; memD = 8'h00;
    tick(6);

    // ---------------- D3: chtenie OZU (rd_drive) ---------------------
    cpuA = 8'hA7; cpuA_en = 1'b1; IOM = 1'b0; A15 = 1'b1; ALE = 1'b1;
    memD = 8'h9D; memD_en = 1'b1;
    tick(2);
    spec_chk(cs394n === 1'b0, "D3a CS_n=0 (okno OZU) v T1");
    spec_chk(oe394n === 1'b0, "D3b OE_n=0 v T1 (dekod)");
    tick(2); ALE = 1'b0; RDn = 1'b0;
    tick(2);
    spec_chk(A394 === 8'h9D,  "D3c RAM read data on A in T2");
    spec_chk(oe394n === 1'b1, "D3d OE_n=1 v T2 (/OE gasitsya s T2 - shapka)");
    tick(1); RDn = 1'b1; cpuA_en = 1'b0; memD_en = 1'b0; memD = 8'h00;
    tick(6);

    // ---------------- D4: IO-zapis (port 00h) pri A15=1 --------------
    we_cnt0 = we_pulses;
    cpuA = 8'h00; cpuA_en = 1'b1; IOM = 1'b1; A15 = 1'b1; ALE = 1'b1;
    tick(4); ALE = 1'b0;
    cpuA = 8'h3C; WRn = 1'b0;
    tick(2);
    spec_chk(cs394n === 1'b1, "D4a CS_n=1 on IO write (A15=1, IOM=1)");
    tick(1); WRn = 1'b1; cpuA_en = 1'b0;
    tick(6);
    spec_chk(we_pulses == we_cnt0, "D4b no WE pulse on IO write");
    spec_chk(seg394 === 8'hC3, "D4c seg=~3C (port 00h accepted)");

    // ---------------- D5: porty 01h/02h ------------------------------
    cyc(1,0,1,0, 8'h01, 8'h1F, 8'h00, 4, 3, 4);
    spec_chk(dig394 === 4'b0000 && snd394 === 1'b1, "D5a port 01h accepted");
    cyc(1,0,1,0, 8'h02, 8'h0A, 8'h00, 4, 3, 4);
    spec_chk(col394 === 4'b1010, "D5b port 02h accepted (cols)");

    // ---------------- D6: IO-chtenie 03h (KBROW mux) -----------------
    cpuA = 8'h03; cpuA_en = 1'b1; IOM = 1'b1; A15 = 1'b0; ALE = 1'b1;
    tick(4); ALE = 1'b0; RDn = 1'b0;
    tick(2);
    spec_chk(A394 === {3'b000, row4, row3, row2, row1, row0}, "D6 KBROW mux on A in T2");
    tick(1); RDn = 1'b1; cpuA_en = 1'b0;
    tick(6);

    // ---------------- D7: zapis v PZU otbrasyvaetsya -----------------
    we_cnt0 = we_pulses;
    cpuA = 8'h10; cpuA_en = 1'b1; IOM = 1'b0; A15 = 1'b0; ALE = 1'b1;
    tick(4); ALE = 1'b0;
    cpuA = 8'hEE; WRn = 1'b0;
    tick(2);
    spec_chk(cs394n === 1'b1, "D7a CS_n=1 on ROM write (A15=0)");
    spec_chk(cs394r === 1'b0, "D7b CSr_n=0 (okno PZU)");
    tick(1); WRn = 1'b1; cpuA_en = 1'b0;
    tick(6);
    spec_chk(we_pulses == we_cnt0, "D7c no WE pulse on ROM write");

    // ---------------- D8: chtenie PZU --------------------------------
    cpuA = 8'h04; cpuA_en = 1'b1; IOM = 1'b0; A15 = 1'b0; ALE = 1'b1;
    memD = 8'hC9; memD_en = 1'b1;
    tick(4); ALE = 1'b0; RDn = 1'b0;
    tick(2);
    spec_chk(A394 === 8'hC9, "D8 ROM data on A in T2");
    tick(1); RDn = 1'b1; cpuA_en = 1'b0; memD_en = 1'b0; memD = 8'h00;
    tick(6);

    // ---------------- D9: PUSH-stress (4 zapisi podryad, zazor 2 tika)
    we_cnt0 = we_pulses; nlog0 = n393;
    // t_ale=5: ALE dolzhen perezhit vkhod v T1H pri zAZORE 2 tika (okno p.4)
    cyc(0,1,1,0, 8'h20, 8'h11, 8'h00, 5, 3, 2);
    cyc(0,1,1,0, 8'h1F, 8'h22, 8'h00, 5, 3, 2);
    cyc(0,1,1,0, 8'h1E, 8'h33, 8'h00, 5, 3, 2);
    cyc(0,1,1,0, 8'h1D, 8'h44, 8'h00, 5, 3, 4);
    spec_chk(we_pulses == we_cnt0 + 4, "D9a four WE pulses");
    $display("D9 debug: n393=%0d nlog0=%0d last4=%h %h %h %h", n393, nlog0,
             ramlog393[nlog0], ramlog393[nlog0+1], ramlog393[nlog0+2], ramlog393[nlog0+3]);
    seg_ok = 1;
    if (n393 !== nlog0 + 4) seg_ok = 0;
    else begin
      if (ramlog393[nlog0+0] !== {8'h20, 8'h11}) seg_ok = 0;
      if (ramlog393[nlog0+1] !== {8'h1F, 8'h22}) seg_ok = 0;
      if (ramlog393[nlog0+2] !== {8'h1E, 8'h33}) seg_ok = 0;
      if (ramlog393[nlog0+3] !== {8'h1D, 8'h44}) seg_ok = 0;
    end
    spec_chk(seg_ok == 1, "D9b RAM log = 20<-11,1F<-22,1E<-33,1D<-44");

    // ---------------- D10: «dyhanie» zaschelki ------------------------
    // zapis OZU, zatem srazu IO-zapis s A15=1: v v3.9.3 wb_ram_q staying 1,
    // no in_wb=0 -> CS_n=1; v3.9.4 obyazan vesti sebya tak zhe
    we_cnt0 = we_pulses;
    cyc(0,1,1,0, 8'h60, 8'h77, 8'h00, 5, 3, 2);
    cyc(1,1,1,0, 8'h00, 8'h81, 8'h00, 5, 3, 4);
    spec_chk(we_pulses == we_cnt0 + 1, "D10a only RAM write gave WE");
    spec_chk(seg394 === 8'h7E, "D10b seg=~81 (IO write accepted)");

    // ---------------- D11: ALE-glyuki v T2 ----------------------------
    // variant 1: glyuk 1 tik - chistyj abort, zapis NE sluchaetsya
    we_cnt0 = we_pulses; nlog0 = n393;
    cyc_glitch_ale(1, 8'h90, 8'h5A);
    spec_chk(we_pulses == we_cnt0, "D11a 1-tick glitch: no WE");
    spec_chk(n393 == nlog0, "D11b 1-tick glitch: no RAM write");
    cyc(0,1,1,0, 8'h91, 8'h5B, 8'h00, 5, 3, 4);   // mashina zhiva posle glyuka
    spec_chk(we_pulses == we_cnt0 + 1, "D11c write works after glitch");
    $display("D11 debug-1: n393=%0d nlog0=%0d last=%h", n393, nlog0, ramlog393[n393-1]);
    spec_chk(ramlog393[n393-1] === {8'h91, 8'h5B}, "D11d RAM got 91<-5B");
    // variant 2: glyuk 2 tika - perezahvat v T1H, zapis formiruetsya
    // zanovo s adresom = dannym (dokumentirovannyj artefakt, bit-v-bit
    // to zhe u v3.9.3 - proveryaetsya ravenstvom)
    we_cnt0 = we_pulses; nlog0 = n393;
    cyc_glitch_ale(2, 8'h92, 8'h5C);
    spec_chk(we_pulses == we_cnt0 + 1, "D11e 2-tick glitch: write re-formed (+1 WE)");
    spec_chk(n393 == nlog0 + 1, "D11f 2-tick glitch: +1 RAM entry");
    $display("D11 debug-2: n393=%0d nlog0=%0d entry=%h", n393, nlog0, ramlog393[nlog0]);
    spec_chk(ramlog393[nlog0] === {8'h92, 8'h5C}, "D11g re-formed write is 92<-5C (original addr kept)");
    cyc(0,1,1,0, 8'h93, 8'h5D, 8'h00, 5, 3, 4);   // mashina zhiva
    spec_chk(ramlog393[n393-1] === {8'h93, 8'h5D}, "D11h RAM got 93<-5D");

    // ---------------- D12: cpu_rst v kazhdoj faze WB -------------------
    for (j = 0; j <= 3; j = j + 1) begin
      cyc_rst_in_wb(j, 8'h30 + j[7:0], 8'hB0 + j[7:0]);
      // mashina zhiva: kontrolnaya zapis
      we_cnt0 = we_pulses;
      cyc(0,1,1,0, 8'h4A, 8'h55, 8'h00, 4, 3, 4);
      spec_chk(we_pulses == we_cnt0 + 1, "D12a write works after WB reset");
    end
    // sbros v T2 pri aktivnoj zapisi (do WB)
    cpuA = 8'h31; cpuA_en = 1'b1; IOM = 1'b0; A15 = 1'b1; ALE = 1'b1;
    tick(4); ALE = 1'b0;
    cpuA = 8'hB7; WRn = 1'b0;
    tick(1);
    RST = 1'b1; last_rst_t = $time;
    tick(2);
    WRn = 1'b1; RST = 1'b0; cpuA_en = 1'b0;
    tick(8);
    we_cnt0 = we_pulses;
    cyc(0,1,1,0, 8'h4B, 8'h66, 8'h00, 4, 3, 4);
    spec_chk(we_pulses == we_cnt0 + 1, "D12b write works after T2 reset");

    // ---------------- D13: TX-zakhvat v3.7 -----------------------------
    SOD = 1'b1; tick(3);              // zakhvat po pervomu SOD='1'
    SOD = 1'b0; tick(2);
    spec_chk(tx394 === 1'b0, "D13a TX=0 transit after capture");
    SOD = 1'b1; tick(2);
    spec_chk(tx394 === 1'b1, "D13b TX=1 transit back");
    spec_chk(sid394 === RX, "D13c SID=RX transit");

    // ---------------- D14: dolgij idle -------------------------------
    tick(200);

    // ---------------- FAZA 2: sluchajnyj stimul ------------------------
    verbose = 1'b0;
    rnd_rst_en = 1'b1;
    rnd_sod_en = 1'b1;
    for (k = 0; k < 4; k = k + 1) begin
      seed = 32'hA5F0_0000 + k;
      for (i = 0; i < 2500; i = i + 1) begin
        ty = $random(seed) & 15;
        ad = $random(seed); dt = $random(seed); rdt = $random(seed);
        t_ale = 3 + ($random(seed) & 3);           // 3..6 tikov ALE
        t_str = 2 + ($random(seed) & 3);           // 2..5 tikov strob
        t_gap = 1 + ($random(seed) & 7);           // 1..8 tikov zazor
        case (ty)
          0, 1, 2, 3, 4, 5: begin                  // zapis OZU (37.5%)
            cyc(1'b0, 1'b1, 1'b1, 1'b0, ad, dt, 8'h00, t_ale, t_str, t_gap);
            n_wram = n_wram + 1;
          end
          6, 7, 8: begin                           // chtenie OZU
            cyc(1'b0, 1'b1, 1'b0, 1'b1, ad, 8'h00, rdt, t_ale, t_str, t_gap);
            n_rdall = n_rdall + 1;
          end
          9: begin                                 // IO-zapis (lyuboj A15)
            cyc(1'b1, ($random(seed) & 1), 1'b1, 1'b0, ad, dt, 8'h00, t_ale, t_str, t_gap);
            n_wio = n_wio + 1;
          end
          10: begin                                // IO-chtenie
            cyc(1'b1, ($random(seed) & 1), 1'b0, 1'b1, ad, 8'h00, rdt, t_ale, t_str, t_gap);
            n_rdall = n_rdall + 1;
          end
          11: begin                                // zapis PZU
            cyc(1'b0, 1'b0, 1'b1, 1'b0, ad, dt, 8'h00, t_ale, t_str, t_gap);
            n_wrom = n_wrom + 1;
          end
          12: begin                                // chtenie PZU
            cyc(1'b0, 1'b0, 1'b0, 1'b1, ad, 8'h00, rdt, t_ale, t_str, t_gap);
            n_rdall = n_rdall + 1;
          end
          13: begin                                // ALE-glyuk v T2 (1..2 tika)
            cyc_glitch_ale(1 + ($random(seed) & 1), ad, dt);
            n_glitch = n_glitch + 1;
          end
          14: begin                                // chtenie+zapis odnovremenno (glyuk-rezhim)
            cyc(1'b0, ($random(seed) & 1), 1'b1, 1'b1, ad, dt, rdt, t_ale, t_str, t_gap);
            n_cyc_rnd = n_cyc_rnd + 1;
          end
          default: begin                           // 15: dolgij idle
            tick(5 + ($random(seed) & 31));
          end
        endcase
        n_cyc_rnd = n_cyc_rnd + 1;
      end
    end
    rnd_rst_en = 1'b0;
    rnd_sod_en = 1'b0;

    // ---------------- ITOGI ------------------------------------------
    // Sravnenie logov OZU: teni (aborty v okne 300 ns posle RST#vverh)
    // propuskajutsya (strakhovka; v tb_v394 GSR u obeih versii - teni
    // ozhidajutsya IDENTICHnymi, propusk ne dolzhen srabotat').
    // Obychnye zapisi sravnivajutsja PARNO, bez propuskov.
    logs_eq = 1;
    i2 = 0; i3 = 0;
    while (i2 < n393 && i3 < n394) begin
      if (ramlog393[i2][16]) begin i2 = i2 + 1; end
      else if (ramlog394[i3][16]) begin i3 = i3 + 1; end
      else begin
        if (ramlog393[i2][15:0] !== ramlog394[i3][15:0]) begin
          logs_eq = 0;
          $display("RAM LOG DIFF @%0d/%0d: %h vs %h", i2, i3, ramlog393[i2][15:0], ramlog394[i3][15:0]);
        end
        i2 = i2 + 1; i3 = i3 + 1;
      end
    end
    // hvost: teni v konce otbrosim, ne-teni - rassinhron (defekt)
    while (i2 < n393 && ramlog393[i2][16]) i2 = i2 + 1;
    while (i3 < n394 && ramlog394[i3][16]) i3 = i3 + 1;
    if (i2 !== n393 || i3 !== n394) begin
      logs_eq = 0;
      $display("RAM LOG: non-shadow tail DIFF: v3.9.3 %0d/%0d, v3.9.4 %0d/%0d", i2, n393, i3, n394);
    end

    $display("=====================================================================");
    $display("ITOG dif-simulyacii v3.9.3 vs v3.9.4:");
    $display("  cycles (random)          : %0d", n_cyc_rnd);
    $display("  RAM writes (stimulus)    : %0d", n_wram);
    $display("  IO/ROM writes (stimulus) : %0d + %0d", n_wio, n_wrom);
    $display("  reads (all types)        : %0d", n_rdall);
    $display("  ALE glitches             : %0d", n_glitch);
    $display("  resets (random)          : %0d (in /WE window: %0d)", n_rst_bursts, rst_in_we);
    $display("  WE pulses (observed)     : %0d", we_pulses);
    $display("  virtual RAM entries      : %0d (v3.9.3, teni %0d) / %0d (v3.9.4, teni %0d), ne-teni %s",
             n393, sh2, n394, sh3, logs_eq ? "IDENTICAL" : "DIFFER");
    $display("  hostile float beats      : %0d (POR window)", n_float);
    $display("  compare-hold samples     : %0d (POR window)", cmp_hold_n);
    $display("  T0 POR (v3.9.4)          : sdvigov %0d, oshibok %0d", sh_cnt, t0_err);
    $display("  output/bus mismatches    : %0d", mism);
    $display("  spec violations          : %0d", specf);
    if (mism == 0 && specf == 0 && logs_eq && t0_err == 0)
      $display("=== EQUIVALENCE v3.9.4 == v3.9.3 CONFIRMED (differential sim + T0 POR) ===");
    else
      $display("!!! MISMATCHES PRESENT - v3.9.4 NOT EQUIVALENT TO v3.9.3 !!!");
    $display("=====================================================================");
    $finish;
  end

  // storozhevoj tajmer
  initial begin
    #40_000_000;
    $display("!!! WATCHDOG: simulyaciya ne zavershilas za 40 ms modelnogo vremeni !!!");
    $finish;
  end

endmodule
