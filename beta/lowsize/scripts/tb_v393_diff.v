`timescale 1ns/1ps
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
module tb_v393_diff;

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
  wire [7:0] A392, A393, D392, D393;
  reg  [7:0] cpuA = 8'h00;   reg cpuA_en = 1'b0;
  reg  [7:0] memD = 8'h00;   reg memD_en = 1'b0;
  assign (weak0, weak1) A392  = cpuA_en ? cpuA : 8'hZZ;
  assign (weak0, weak1) A393 = cpuA_en ? cpuA : 8'hZZ;
  assign (weak0, weak1) D392  = memD_en ? memD : 8'hZZ;
  assign (weak0, weak1) D393 = memD_en ? memD : 8'hZZ;

  //-------------------------------------------------------------------
  // Vyhody
  //-------------------------------------------------------------------
  wire cs392r, oe392r, cs392n, oe392n, we392n, cs1_392, x1_392, rdy392, rsti392, sid392, tx392, snd392, x2_392;
  wire [7:0] seg392;  wire [3:0] dig392;  wire [3:0] col392;
  wire cs393r, oe393r, cs393n, oe393n, we393n, cs1_393, x1_393, rdy393, rsti393, sid393, tx393, snd393, x2_393;
  wire [7:0] seg393; wire [3:0] dig393; wire [3:0] col393;

  retro_pcld_top_v392 dut392 (
    .clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(A392), .D(D392),
    .CSr_n(cs392r), .OEr_n(oe392r), .CS_n(cs392n), .OE_n(oe392n), .WE_n(we392n), .CS1(cs1_392),
    .X1(x1_392), .READY(rdy392), .RESET_IN(rsti392),
    .SID(sid392), .TX(tx392), .seg(seg392), .dig(dig392), .SND(snd392),
    .X2(x2_392), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA),
    .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12), .AH13(AH13), .AH14(AH14),
    .RX(RX),
    .col0(col392[0]), .col1(col392[1]), .col2(col392[2]), .col3(col392[3]),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

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

  //-------------------------------------------------------------------
  // Schetchiki i sravnenie
  //-------------------------------------------------------------------
  integer mism = 0;
  integer specf = 0;
  integer we_pulses = 0;
  integer rst_in_we = 0;          // sbrosov v okne nizkogo /WE
  time    we_t0 = 0;
  time    last_rst_t = -1000;
  time    a_chg393 = 0;

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

  task cmp1(input a, input b, input [8*8-1:0] nm);
    begin
      if (a !== b) begin
        mism = mism + 1;
        if (mism <= 50) $display("[%0t] MISMATCH %s: v3.9.2=%b v3.9.3=%b", $time, nm, a, b);
      end
    end
  endtask

  task cmp4(input [3:0] a, input [3:0] b, input [8*8-1:0] nm);
    begin
      if (a !== b) begin
        mism = mism + 1;
        if (mism <= 50) $display("[%0t] MISMATCH %s: v3.9.2=%b v3.9.3=%b", $time, nm, a, b);
      end
    end
  endtask

  task cmp8(input [7:0] a, input [7:0] b, input [8*8-1:0] nm);
    begin
      if (a !== b) begin
        mism = mism + 1;
        if (mism <= 50) $display("[%0t] MISMATCH %s: v3.9.2=%b v3.9.3=%b", $time, nm, a, b);
      end
    end
  endtask

  task chk_all;
    begin
    if (cmp_hold) begin
      cmp_hold_n = cmp_hold_n + 1;
    end else begin
      cmp1(x1_392,   x1_393,   "X1");
      cmp1(x2_392,   x2_393,   "X2");
      cmp1(rsti392,  rsti393,  "RESET_IN");
      cmp1(rdy392,   rdy393,   "READY");
      cmp1(cs1_392,  cs1_393,  "CS1");
      cmp1(cs392r,   cs393r,   "CSr_n");
      cmp1(oe392r,   oe393r,   "OEr_n");
      cmp1(cs392n,   cs393n,   "CS_n");
      cmp1(oe392n,   oe393n,   "OE_n");
      cmp1(we392n,   we393n,   "WE_n");
      cmp1(sid392,   sid393,   "SID");
      cmp1(tx392,    tx393,    "TX");
      cmp1(snd392,   snd393,   "SND");
      cmp8(seg392,   seg393,   "seg");
      cmp4(dig392,   dig393,   "dig");
      cmp4(col392,   col393,   "col");
      cmp8(A392,     A393,     "A-bus");
      cmp8(D392,     D393,     "D-bus");
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
  reg [16:0] ramlog392  [0:16383];  // bit16 = ten' (abort < 300 ns posle RST#vverh)
  reg [16:0] ramlog393 [0:16383];  // bit16 = ten' (abort < 300 ns posle RST#vverh)
  integer n392 = 0, n393 = 0;
  integer sh2 = 0, sh3 = 0;      // schetchiki tenjej (aborty)

  // Sembpl cherez 1 ns posle fronta WE#verh: k etomu momentu vse
  // combinacionnye znacheniya (CS/A/D) USTOYALIS (v tom chisle v sluchae
  // obryva impulsa sbrosom, kogda WE#verh i smena dekoda CS proishodyat
  // v odnoj delta-tsepi). Do sleduyuschego vozmozhnogo izmeneniya 20 ns.
  always @(posedge we392n) begin
    #1;
    if (cs392n === 1'b0) begin
      sh2 = sh2 + (($time - last_rst_t) < 300);
      ramlog392[n392] = {($time - last_rst_t) < 300, A392, D392}; n392 = n392 + 1;
    end
  end
  always @(posedge we393n) begin
    #1;
    if (cs393n === 1'b0) begin
      sh3 = sh3 + (($time - last_rst_t) < 300);
      ramlog393[n393] = {($time - last_rst_t) < 300, A393, D393}; n393 = n393 + 1;
    end
  end

  //-------------------------------------------------------------------
  // Spek-monitory (v3.9.3; zerkala v3.9.2 pokryvayutsya ravenstvom)
  //-------------------------------------------------------------------
  reg we_armed = 1'b0;   // otsech fantomnyj front X->1 v moment 0
  // shirina impulsa /WE = rovno 80 ns (glushitsya 300 ns posle sbrosa)
  always @(negedge we393n) begin we_t0 = $time; we_armed = 1'b1; end
  always @(posedge we393n) begin
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
  always @(A393) a_chg393 = $time;
  always @(negedge we393n) begin
    if (we_armed && ($time - a_chg393) < 40 && ($time - last_rst_t) > 300) begin
      specf = specf + 1;
      $display("[%0t] SPEC FAIL: t_AS = %0t ns (< 40)", $time, $time - a_chg393);
    end
  end
  // svyazka: /WE=0 vlechet /CE=0
  always @(posedge clk) begin
    #1;
    if (we393n === 1'b0 && cs393n !== 1'b0) begin
      specf = specf + 1;
      $display("[%0t] SPEC FAIL: /WE=0 while /CE=1", $time);
    end
  end
  // schetchik sbrosov v okne /WE (pokrytie)
  always @(posedge clk) begin
    #1;
    if (RST === 1'b1 && we393n === 1'b0) rst_in_we = rst_in_we + 1;
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
        $display("    [cyc iom=%b a15=%b wr=%b rd=%b adr=%h dt=%h] end: state=%0d al=%h br=%h n392=%0d wep=%0d",
                 iom_i, a15_i, do_wr, do_rd, addr, wdata, dut393.state, dut393.addr_latch, dut393.bus_reg, n392, we_pulses);
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
    spec_chk(rsti393 === 1'b1, "D1a RESET_IN=1 after POR");
    spec_chk(cs1_393 === 1'b1, "D1b CS1=1");
    spec_chk(rdy393 === 1'b1,  "D1c READY=1");
    spec_chk(tx393  === 1'b1,  "D1d TX=1 idle");
    spec_chk(seg393 === 8'h00, "D1e seg all on (8888.)");
    spec_chk(dig393 === 4'b0000, "D1f all digits active");
    // period X1: 10 periodov = 1400 ns
    @(posedge x1_393); tp1 = $time;
    repeat (10) @(posedge x1_393);
    tp2 = $time;
    if ((tp2 - tp1) !== 1400) begin
      specf = specf + 1;
      $display("[%0t] SPEC FAIL: 10 periods of X1 = %0t ns (expected 1400)", $time, tp2 - tp1);
    end
    // X2 = ~X1 na setke 10 ns (2 mks)
    for (q = 0; q < 200; q = q + 1) begin
      #10;
      if (x2_393 !== ~x1_393) begin
        specf = specf + 1;
        $display("[%0t] SPEC FAIL: X2 != ~X1", $time);
      end
    end

    // ---------------- D2: zapis OZU + smena adresa posredi WB (p.5) --
    // (a) zapis 77<-A5; posle WRn#verh - srazu novyj «cikl» s A15=0
    //     (PZU-adres): CS_n v WB1..WB4 obyazan derzhatsya 0 BEZ decoda
    we_before = we_pulses;
    nlog0 = n392;
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
    spec_chk(cs393n === 1'b0, "D2a CS_n=0 in WB2 despite new ROM addr");
    spec_chk(we393n === 1'b0, "D2b WE_n=0 in WB2 (pulse in progress)");
    tick(2);                                      // WB3, WB4 (WE verh na WB4)
    spec_chk(cs393n === 1'b0, "D2c CS_n=0 vse esche (WB4)");
    spec_chk(we393n === 1'b1, "D2d WE_n=1 in WB4 (pulse done)");
    ALE = 1'b0; cpuA_en = 1'b0;
    tick(4);                                      // WB zavershen, vsyo snyato
    spec_chk(we_pulses == we_before + 1, "D2f exactly one WE pulse");
    spec_chk(n392 == nlog0 + 1, "D2g RAM log +1");
    spec_chk(ramlog392[nlog0] === {8'h77, 8'hA5}, "D2h RAM got 77<-A5");
    // (b) normalnyj cikl chteniya PZU: dekod vosstanovlen (CS_n=1);
    // t_ale=5: zakhvat trebuetsya v T1H (ALE dolzhen perezhit vhod v T1H)
    cpuA = 8'h12; cpuA_en = 1'b1; IOM = 1'b0; A15 = 1'b0; ALE = 1'b1;
    memD = 8'h5E; memD_en = 1'b1;
    tick(5); ALE = 1'b0; RDn = 1'b0;
    tick(2);
    spec_chk(cs393n === 1'b1, "D2i CS_n=1 on ROM read after WB (decode resumed)");
    spec_chk(cs393r === 1'b0, "D2j CSr_n=0 on ROM read");
    spec_chk(A393 === 8'h5E,  "D2k ROM data on A in T2");
    tick(1); RDn = 1'b1; cpuA_en = 1'b0; memD_en = 1'b0; memD = 8'h00;
    tick(6);

    // ---------------- D3: chtenie OZU (rd_drive) ---------------------
    cpuA = 8'hA7; cpuA_en = 1'b1; IOM = 1'b0; A15 = 1'b1; ALE = 1'b1;
    memD = 8'h9D; memD_en = 1'b1;
    tick(2);
    spec_chk(cs393n === 1'b0, "D3a CS_n=0 (okno OZU) v T1");
    spec_chk(oe393n === 1'b0, "D3b OE_n=0 v T1 (dekod)");
    tick(2); ALE = 1'b0; RDn = 1'b0;
    tick(2);
    spec_chk(A393 === 8'h9D,  "D3c RAM read data on A in T2");
    spec_chk(oe393n === 1'b1, "D3d OE_n=1 v T2 (/OE gasitsya s T2 - shapka)");
    tick(1); RDn = 1'b1; cpuA_en = 1'b0; memD_en = 1'b0; memD = 8'h00;
    tick(6);

    // ---------------- D4: IO-zapis (port 00h) pri A15=1 --------------
    we_cnt0 = we_pulses;
    cpuA = 8'h00; cpuA_en = 1'b1; IOM = 1'b1; A15 = 1'b1; ALE = 1'b1;
    tick(4); ALE = 1'b0;
    cpuA = 8'h3C; WRn = 1'b0;
    tick(2);
    spec_chk(cs393n === 1'b1, "D4a CS_n=1 on IO write (A15=1, IOM=1)");
    tick(1); WRn = 1'b1; cpuA_en = 1'b0;
    tick(6);
    spec_chk(we_pulses == we_cnt0, "D4b no WE pulse on IO write");
    spec_chk(seg393 === 8'hC3, "D4c seg=~3C (port 00h accepted)");

    // ---------------- D5: porty 01h/02h ------------------------------
    cyc(1,0,1,0, 8'h01, 8'h1F, 8'h00, 4, 3, 4);
    spec_chk(dig393 === 4'b0000 && snd393 === 1'b1, "D5a port 01h accepted");
    cyc(1,0,1,0, 8'h02, 8'h0A, 8'h00, 4, 3, 4);
    spec_chk(col393 === 4'b1010, "D5b port 02h accepted (cols)");

    // ---------------- D6: IO-chtenie 03h (KBROW mux) -----------------
    cpuA = 8'h03; cpuA_en = 1'b1; IOM = 1'b1; A15 = 1'b0; ALE = 1'b1;
    tick(4); ALE = 1'b0; RDn = 1'b0;
    tick(2);
    spec_chk(A393 === {3'b000, row4, row3, row2, row1, row0}, "D6 KBROW mux on A in T2");
    tick(1); RDn = 1'b1; cpuA_en = 1'b0;
    tick(6);

    // ---------------- D7: zapis v PZU otbrasyvaetsya -----------------
    we_cnt0 = we_pulses;
    cpuA = 8'h10; cpuA_en = 1'b1; IOM = 1'b0; A15 = 1'b0; ALE = 1'b1;
    tick(4); ALE = 1'b0;
    cpuA = 8'hEE; WRn = 1'b0;
    tick(2);
    spec_chk(cs393n === 1'b1, "D7a CS_n=1 on ROM write (A15=0)");
    spec_chk(cs393r === 1'b0, "D7b CSr_n=0 (okno PZU)");
    tick(1); WRn = 1'b1; cpuA_en = 1'b0;
    tick(6);
    spec_chk(we_pulses == we_cnt0, "D7c no WE pulse on ROM write");

    // ---------------- D8: chtenie PZU --------------------------------
    cpuA = 8'h04; cpuA_en = 1'b1; IOM = 1'b0; A15 = 1'b0; ALE = 1'b1;
    memD = 8'hC9; memD_en = 1'b1;
    tick(4); ALE = 1'b0; RDn = 1'b0;
    tick(2);
    spec_chk(A393 === 8'hC9, "D8 ROM data on A in T2");
    tick(1); RDn = 1'b1; cpuA_en = 1'b0; memD_en = 1'b0; memD = 8'h00;
    tick(6);

    // ---------------- D9: PUSH-stress (4 zapisi podryad, zazor 2 tika)
    we_cnt0 = we_pulses; nlog0 = n392;
    // t_ale=5: ALE dolzhen perezhit vkhod v T1H pri zAZORE 2 tika (okno p.4)
    cyc(0,1,1,0, 8'h20, 8'h11, 8'h00, 5, 3, 2);
    cyc(0,1,1,0, 8'h1F, 8'h22, 8'h00, 5, 3, 2);
    cyc(0,1,1,0, 8'h1E, 8'h33, 8'h00, 5, 3, 2);
    cyc(0,1,1,0, 8'h1D, 8'h44, 8'h00, 5, 3, 4);
    spec_chk(we_pulses == we_cnt0 + 4, "D9a four WE pulses");
    $display("D9 debug: n392=%0d nlog0=%0d last4=%h %h %h %h", n392, nlog0,
             ramlog392[nlog0], ramlog392[nlog0+1], ramlog392[nlog0+2], ramlog392[nlog0+3]);
    seg_ok = 1;
    if (n392 !== nlog0 + 4) seg_ok = 0;
    else begin
      if (ramlog392[nlog0+0] !== {8'h20, 8'h11}) seg_ok = 0;
      if (ramlog392[nlog0+1] !== {8'h1F, 8'h22}) seg_ok = 0;
      if (ramlog392[nlog0+2] !== {8'h1E, 8'h33}) seg_ok = 0;
      if (ramlog392[nlog0+3] !== {8'h1D, 8'h44}) seg_ok = 0;
    end
    spec_chk(seg_ok == 1, "D9b RAM log = 20<-11,1F<-22,1E<-33,1D<-44");

    // ---------------- D10: «dyhanie» zaschelki ------------------------
    // zapis OZU, zatem srazu IO-zapis s A15=1: v v3.9.2 wb_ram_q staying 1,
    // no in_wb=0 -> CS_n=1; v3.9.3 obyazan vesti sebya tak zhe
    we_cnt0 = we_pulses;
    cyc(0,1,1,0, 8'h60, 8'h77, 8'h00, 5, 3, 2);
    cyc(1,1,1,0, 8'h00, 8'h81, 8'h00, 5, 3, 4);
    spec_chk(we_pulses == we_cnt0 + 1, "D10a only RAM write gave WE");
    spec_chk(seg393 === 8'h7E, "D10b seg=~81 (IO write accepted)");

    // ---------------- D11: ALE-glyuki v T2 ----------------------------
    // variant 1: glyuk 1 tik - chistyj abort, zapis NE sluchaetsya
    we_cnt0 = we_pulses; nlog0 = n392;
    cyc_glitch_ale(1, 8'h90, 8'h5A);
    spec_chk(we_pulses == we_cnt0, "D11a 1-tick glitch: no WE");
    spec_chk(n392 == nlog0, "D11b 1-tick glitch: no RAM write");
    cyc(0,1,1,0, 8'h91, 8'h5B, 8'h00, 5, 3, 4);   // mashina zhiva posle glyuka
    spec_chk(we_pulses == we_cnt0 + 1, "D11c write works after glitch");
    $display("D11 debug-1: n392=%0d nlog0=%0d last=%h", n392, nlog0, ramlog392[n392-1]);
    spec_chk(ramlog392[n392-1] === {8'h91, 8'h5B}, "D11d RAM got 91<-5B");
    // variant 2: glyuk 2 tika - perezahvat v T1H, zapis formiruetsya
    // zanovo s adresom = dannym (dokumentirovannyj artefakt, bit-v-bit
    // to zhe u v3.9.2 - proveryaetsya ravenstvom)
    we_cnt0 = we_pulses; nlog0 = n392;
    cyc_glitch_ale(2, 8'h92, 8'h5C);
    spec_chk(we_pulses == we_cnt0 + 1, "D11e 2-tick glitch: write re-formed (+1 WE)");
    spec_chk(n392 == nlog0 + 1, "D11f 2-tick glitch: +1 RAM entry");
    $display("D11 debug-2: n392=%0d nlog0=%0d entry=%h", n392, nlog0, ramlog392[nlog0]);
    spec_chk(ramlog392[nlog0] === {8'h92, 8'h5C}, "D11g re-formed write is 92<-5C (original addr kept)");
    cyc(0,1,1,0, 8'h93, 8'h5D, 8'h00, 5, 3, 4);   // mashina zhiva
    spec_chk(ramlog392[n392-1] === {8'h93, 8'h5D}, "D11h RAM got 93<-5D");

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
    spec_chk(tx393 === 1'b0, "D13a TX=0 transit after capture");
    SOD = 1'b1; tick(2);
    spec_chk(tx393 === 1'b1, "D13b TX=1 transit back");
    spec_chk(sid393 === RX, "D13c SID=RX transit");

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

    $display("=====================================================================");
    $display("ITOG dif-simulyacii v3.9.2 vs v3.9.3:");
    $display("  cycles (random)          : %0d", n_cyc_rnd);
    $display("  RAM writes (stimulus)    : %0d", n_wram);
    $display("  IO/ROM writes (stimulus) : %0d + %0d", n_wio, n_wrom);
    $display("  reads (all types)        : %0d", n_rdall);
    $display("  ALE glitches             : %0d", n_glitch);
    $display("  resets (random)          : %0d (in /WE window: %0d)", n_rst_bursts, rst_in_we);
    $display("  WE pulses (observed)     : %0d", we_pulses);
    $display("  virtual RAM entries      : %0d (v3.9.2, teni %0d) / %0d (v3.9.3, teni %0d), ne-teni %s",
             n392, sh2, n393, sh3, logs_eq ? "IDENTICAL" : "DIFFER");
    $display("  hostile float beats      : %0d (POR window)", n_float);
    $display("  compare-hold samples     : %0d (reset/POR windows)", cmp_hold_n);
    $display("  output/bus mismatches    : %0d", mism);
    $display("  spec violations          : %0d", specf);
    if (mism == 0 && specf == 0 && logs_eq)
      $display("=== EQUIVALENCE v3.9.3 == v3.9.2 CONFIRMED (differential sim) ===");
    else
      $display("!!! MISMATCHES PRESENT - v3.9.3 NOT EQUIVALENT TO v3.9.2 !!!");
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
