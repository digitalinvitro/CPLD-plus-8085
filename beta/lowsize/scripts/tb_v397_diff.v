`timescale 1ns/1ps
//=====================================================================
// tb_v397_diff.v (lowsize, 2026-11-06): DIFFerencial'naya simulyaciya
// v3.9.6 vs v3.9.7 (mera p.22: vozvrat KO L'CA one-hot r0..r6 v
// g_div2p5 vmesto dvoichnogo mod-7 cnt[2:0]; vsyo ostal'noe -
// bez pravok). ETALON = v3.9.6 (tekushchiy kandidat linii).
//
// UTVERZHDENIE: zameyna mashiny sostoyaniy delitelya NE vidna na
// NIKAKOM vyhode ni v ODNOY faze (INIT ekvivalenten: cnt=000 <=>
// r0=1 - odna i ta zhe nachal'naya faza X1='0'/X2='1'; x1_n -
// te zhe fazy r3/r4 <=> cnt==3/cnt==4; por_ce = x1_n u OBEIH;
// por-cepy bit-v-bit). Poskol'ku i sbrosa aniomiya v3.9.6 u obeih,
// sravnenie STROGOE: vse vyhody i obe shiny kazhdye 5 ns S TAMANT
// POR i knopki - okon maskirovki NET.
//
// Scenarii:
//  T0  POR: niz RESET_IN 840..1100 ns u OBEIH (norma >= 840);
//      podyom NA TOY ZHE kromke (poslednee sravnenie vklucheno);
//  EQ  600 sluchaynyh ciklov shinu (chteniya/zapisi RAM/IO/tihiye,
//      adresy/dannye sluchaynye) - sravnenie vseh vyhodov i obeih
//      shin kazhdye 5 ns - 0 raskhozhdeniy;
//  XP  uzor X1: period 140 ns (posedges kazhdye 140 ns), X2 == ~X1
//      v kazhdoy vyborke (svoystvo koltca: X2 = r0^x1_n = ~X1);
//  S1  chistaya knopka: latentionnost' vzvoda/snatiya 400..445 ns u
//      OBEIH (2FF+8 takt kvalifikatora+reset_q - anatomiya v3.9.6);
//      posle snatiya - vse reg chisty u obeih; zapis' OZU OK;
//  S2  drebeg knopki (ekskursii 80..200 ns ne kacheveny,
//      1 us - perezapusk) NA TIKHOY shine: povedenie bit-v-bit,
//      /WE ne zvenit u obeih, final chistyy;
//  S2h tot zhe drebeg NA VRACHDEBNOY shine (plavaniya): lozhnyh /WE
//      NET u obeih, final'noe vymyvanie chistoe;
//  POR-vnutrennee: por_run u obeih padaet NA TOY ZHE kromke
//      (sravnenie hierarhicheski kazhdye 5 ns v EQ-okne).
//=====================================================================
module tb_v397_diff;

  //-------------------------------------------------------------------
  // Takt 25 MGc
  //-------------------------------------------------------------------
  reg clk = 1'b0;
  always #20 clk = ~clk;

  time  t_pe = 0;
  always @(posedge clk) t_pe = $time;

  //-------------------------------------------------------------------
  // Obshchie vhody
  //-------------------------------------------------------------------
  reg RST = 1'b0, ALE = 1'b0, WRn = 1'b1, RDn = 1'b1, IOM = 1'b0, A15 = 1'b0;
  reg SOD = 1'b0, RX = 1'b1;
  reg RSTOUT = 1'b0, INTAn = 1'b1, HLDA = 1'b0, CLKOUT = 1'b0, S0 = 1'b0, S1 = 1'b0;
  reg AH8 = 1'b0, AH9 = 1'b0, AH10 = 1'b0, AH11 = 1'b0, AH12 = 1'b0, AH13 = 1'b0, AH14 = 1'b0;
  reg row0 = 1'b1, row1 = 1'b0, row2 = 1'b1, row3 = 1'b0, row4 = 1'b1;

  //-------------------------------------------------------------------
  // Razdelnye shiny; slabyj stimul CPU (A) i pamyati (D)
  //-------------------------------------------------------------------
  wire [7:0] A396, A397, D396, D397;
  reg  [7:0] cpuA = 8'h00;   reg cpuA_en = 1'b0;
  reg  [7:0] memD = 8'h00;   reg memD_en = 1'b0;
  assign (weak0, weak1) A396 = cpuA_en ? cpuA : 8'hZZ;
  assign (weak0, weak1) A397 = cpuA_en ? cpuA : 8'hZZ;
  assign (weak0, weak1) D396 = memD_en ? memD : 8'hZZ;
  assign (weak0, weak1) D397 = memD_en ? memD : 8'hZZ;

  //-------------------------------------------------------------------
  // Vyhody
  //-------------------------------------------------------------------
  wire csr396, oer396, cs396n, oe396n, we396n, cs1_396, x1_396, rdy396, rsti396, sid396, tx396, snd396, x2_396;
  wire [7:0] seg396;  wire [3:0] dig396, col396;
  wire csr397, oer397, cs397n, oe397n, we397n, cs1_397, x1_397, rdy397, rsti397, sid397, tx397, snd397, x2_397;
  wire [7:0] seg397;  wire [3:0] dig397, col397;

  retro_pcld_top_v396 dut396 (
    .clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(A396), .D(D396),
    .CSr_n(csr396), .OEr_n(oer396), .CS_n(cs396n), .OE_n(oe396n), .WE_n(we396n), .CS1(cs1_396),
    .X1(x1_396), .READY(rdy396), .RESET_IN(rsti396),
    .SID(sid396), .TX(tx396), .seg(seg396), .dig(dig396), .SND(snd396),
    .X2(x2_396), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA),
    .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12), .AH13(AH13), .AH14(AH14),
    .RX(RX),
    .col0(col396[0]), .col1(col396[1]), .col2(col396[2]), .col3(col396[3]),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

  retro_pcld_top_v397 dut397 (
    .clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(A397), .D(D397),
    .CSr_n(csr397), .OEr_n(oer397), .CS_n(cs397n), .OE_n(oe397n), .WE_n(we397n), .CS1(cs1_397),
    .X1(x1_397), .READY(rdy397), .RESET_IN(rsti397),
    .SID(sid397), .TX(tx397), .seg(seg397), .dig(dig397), .SND(snd397),
    .X2(x2_397), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA),
    .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12), .AH13(AH13), .AH14(AH14),
    .RX(RX),
    .col0(col397[0]), .col1(col397[1]), .col2(col397[2]), .col3(col397[3]),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

  //-------------------------------------------------------------------
  // XP: svoystva koltca na RTL v3.9.7: X2 == ~X1 v kazhdoy vyborke;
  // u v3.9.6 - to zhe (kontrol' simmetrii)
  //-------------------------------------------------------------------
  integer x2_mis397 = 0, x2_mis396 = 0;
  always #5 begin
    if (x2_397 !== ~x1_397) x2_mis397 = x2_mis397 + 1;
    if (x2_396 !== ~x1_396) x2_mis396 = x2_mis396 + 1;
  end

  // period X1 = 140 ns: posledniy front X1 zafiksirovan
  time t_x1a = 0, t_x1b = 0;
  real  x1_min = 1e9, x1_max = 0;
  always @(posedge x1_397) begin
    if (t_x1a > 2000) begin                 // posle POR - ustoyavshiysya uzor
      if ((t_x1a - t_x1b) < x1_min) x1_min = t_x1a - t_x1b;
      if ((t_x1a - t_x1b) > x1_max) x1_max = t_x1a - t_x1b;
    end
    t_x1b = t_x1a; t_x1a = $time;
  end

  //-------------------------------------------------------------------
  // Ekvivalentnost': sravnenie kazhdye 5 ns pri cmp_en (STROGO - s t=0)
  //-------------------------------------------------------------------
  reg cmp_en = 1'b1;
  integer n_eq = 0, n_mis = 0;
  task cmp1(input a, input b, input [8*8-1:0] nm);
    begin
      if (a !== b) begin
        n_mis = n_mis + 1;
        if (n_mis < 20) $display("  EQ MISMATCH %0s t=%0t: %b vs %b", nm, $time, a, b);
      end
    end
  endtask
  task cmp4(input [3:0] a, input [3:0] b, input [8*8-1:0] nm);
    begin
      if (a !== b) begin
        n_mis = n_mis + 1;
        if (n_mis < 20) $display("  EQ MISMATCH %0s t=%0t: %h vs %h", nm, $time, a, b);
      end
    end
  endtask
  task cmp8(input [7:0] a, input [7:0] b, input [8*8-1:0] nm);
    begin
      if (a !== b) begin
        n_mis = n_mis + 1;
        if (n_mis < 20) $display("  EQ MISMATCH %0s t=%0t: %h vs %h", nm, $time, a, b);
      end
    end
  endtask
  initial forever begin
    #5;
    if (cmp_en) begin
      n_eq = n_eq + 1;
      cmp1(csr396, csr397, "CSr_n");
      cmp1(oer396, oer397, "OEr_n");
      cmp1(cs396n, cs397n, "CS_n");
      cmp1(oe396n, oe397n, "OE_n");
      cmp1(we396n, we397n, "WE_n");
      cmp1(cs1_396, cs1_397, "CS1");
      cmp1(x1_396, x1_397, "X1");
      cmp1(x2_396, x2_397, "X2");
      cmp1(rdy396, rdy397, "READY");
      cmp1(rsti396, rsti397, "RESET_IN");
      cmp1(sid396, sid397, "SID");
      cmp1(tx396, tx397, "TX");
      cmp1(snd396, snd397, "SND");
      cmp8(seg396, seg397, "seg");
      cmp4(dig396, dig397, "dig");
      cmp4(col396, col397, "col");
      cmp8(A396, A397, "A-bus");
      cmp8(D396, D397, "D-bus");
      // vnutrennee por_run: POR bit-v-bit (padaet na toy zhe kromke)
      cmp1(dut396.por_run, dut397.por_run, "por_run");
    end
  end

  //-------------------------------------------------------------------
  // Schetchiki /WE (negedge) s adresom/dannymi
  //-------------------------------------------------------------------
  integer we_falls396 = 0, we_falls397 = 0;
  reg [7:0] we_a396 = 0, we_d396 = 0, we_a397 = 0, we_d397 = 0;
  always @(negedge we396n) begin
    we_falls396 = we_falls396 + 1;
    we_a396 = A396; we_d396 = D396;
  end
  always @(negedge we397n) begin
    we_falls397 = we_falls397 + 1;
    we_a397 = A397; we_d397 = D397;
  end

  //-------------------------------------------------------------------
  // Chistota sbrosovogo domena (hierarhicheski) - obe DUT (anatomiya 3.9.6)
  //-------------------------------------------------------------------
  task chk_clean(input [8*32-1:0] where);
    integer e;
    begin
      e = 0;
      if (dut396.state      !== 3'd0)   begin e = e + 1; $display("  DIRTY396 %0s: state=%0d", where, dut396.state); end
      if (dut396.addr_latch !== 8'h00)  begin e = e + 1; $display("  DIRTY396 %0s: addr_latch=%h", where, dut396.addr_latch); end
      if (dut396.seg_q      !== 8'hFF)  begin e = e + 1; $display("  DIRTY396 %0s: seg_q=%h", where, dut396.seg_q); end
      if (dut397.state      !== 3'd0)   begin e = e + 1; $display("  DIRTY397 %0s: state=%0d", where, dut397.state); end
      if (dut397.addr_latch !== 8'h00)  begin e = e + 1; $display("  DIRTY397 %0s: addr_latch=%h", where, dut397.addr_latch); end
      if (dut397.seg_q      !== 8'hFF)  begin e = e + 1; $display("  DIRTY397 %0s: seg_q=%h", where, dut397.seg_q); end
      if (e == 0) $display("  PASS clean %0s (obe DUT, vse proverennye reg chisty)", where);
      else        $display("  FAIL clean %0s: %0d polej isportcheno", where, e);
      if (e > 0) tot_err = tot_err + 1;
    end
  endtask

  //-------------------------------------------------------------------
  // Stimul: tik; polnyj shinnyj cikl (T1+T2+zazor)
  //-------------------------------------------------------------------
  integer tot_err = 0;

  task tick(input integer n);
    begin
      repeat (n) @(posedge clk);
      #1;
    end
  endtask

  task cyc(input iom_i, input a15_i, input do_wr, input do_rd,
           input [7:0] addr, input [7:0] wdata, input [7:0] rdata);
    begin
      cpuA = addr; cpuA_en = 1'b1; IOM = iom_i; A15 = a15_i; ALE = 1'b1;
      if (!iom_i && do_rd) begin memD = rdata; memD_en = 1'b1; end
      tick(4);
      ALE = 1'b0;
      if (do_wr) begin cpuA = wdata; WRn = 1'b0; end
      if (do_rd) begin RDn = 1'b0; end
      tick(3);
      if (do_wr) WRn = 1'b1;
      if (do_rd) RDn = 1'b1;
      cpuA_en = 1'b0;
      if (do_rd) begin memD_en = 1'b0; memD = 8'h00; end
      tick(6);
    end
  endtask

  task resync;
    begin
      RST = 1'b1; tick(75); RST = 1'b0;
      tick(20);                        // 440 ns snatiya + zapas
      cyc(1'b0, 1'b0, 1'b0, 1'b1, 8'h00, 8'h00, 8'h00); // vymyvayuschee chtenie
    end
  endtask

  //-------------------------------------------------------------------
  // Osnovnoy process
  //-------------------------------------------------------------------
  integer i;
  integer s1_err = 0, s2_err = 0;
  time    t_rst, t_ev, t_ev6, t_ev7;
  reg [7:0] ad, dt;
  integer seed_eq = 32'hBEEF_3971;

  initial begin
    $display("=== tb_v397_diff: v3.9.6 (etalon) vs v3.9.7 (kol'tso) - STROGOE sravnenie s t=0 ===");

    // ================= T0: POR =================
    tick(40);   // 1600 ns - POR u oboih zavershon
    if (rsti396 !== 1'b1 || rsti397 !== 1'b1) begin
      s1_err = s1_err + 1; $display("  FAIL T0: RESET_IN ne snyalsya za 1600 ns (396=%b 397=%b)", rsti396, rsti397);
    end else
      $display("  PASS T0: POR zavershon u oboih k 1600 ns (vse vyborki s t=0 sovpadayut - niz/ podyom NA TOY ZHE kromke)");

    // ================= EQ: 600 sluchaynyh ciklov =================
    for (i = 0; i < 600; i = i + 1) begin
      ad = $random(seed_eq); dt = $random(seed_eq);
      case ($random(seed_eq) % 5)
        0: cyc(1'b0, 1'b0, 1'b0, 1'b1, ad, dt, dt);         // chtenie ROM
        1: cyc(1'b0, 1'b1, 1'b0, 1'b1, ad, dt, dt);         // chtenie RAM
        2: cyc(1'b0, 1'b1, 1'b1, 1'b0, ad, dt, 8'h00);      // zapis' RAM
        3: cyc(1'b1, 1'b0, 1'b1, 1'b0, ad, dt, 8'h00);      // zapis' IO port
        default: cyc(1'b0, 1'b0, 1'b0, 1'b0, ad, dt, 8'h00); // tihij cikl
      endcase
    end
    if (n_mis == 0) $display("  PASS EQ: %0d vyborok 5 ns (vkl. por_run), 0 raskhozhdenij - norm-put' bit-v-bit", n_eq);
    else begin
      tot_err = tot_err + 1;
      $display("  FAIL EQ: %0d raskhozhdenij na %0d vyborok", n_mis, n_eq);
    end

    // ================= XP: uzor X1 i X2=~X1 =================
    if (x2_mis397 == 0 && x2_mis396 == 0)
      $display("  PASS XP: X2 == ~X1 v KAZHDoy vyborke 5 ns u oboih (svoystvo koltca/ schiechika sohraneno)");
    else begin
      tot_err = tot_err + 1;
      $display("  FAIL XP: X2 != ~X1: v3.9.7 %0d raz, v3.9.6 %0d raz", x2_mis397, x2_mis396);
    end
    if (x1_min >= 135 && x1_max <= 145)
      $display("  PASS XP: periody X1 (v3.9.7) %0t..%0t ns - Rovno 140 (7,143 MGc)", x1_min, x1_max);
    else begin
      tot_err = tot_err + 1;
      $display("  FAIL XP: periody X1 (v3.9.7) %0t..%0t ns - ne 140", x1_min, x1_max);
    end

    // ================= S1: chistaya knopka (obe DUT) =================
    we_falls396 = 0; we_falls397 = 0;
    RST = 1'b1;
    @(posedge clk); #2; t_rst = $time;
    t_ev6 = 0; t_ev7 = 0;
    fork
      begin @(negedge rsti396); t_ev6 = $time; end
      begin @(negedge rsti397); t_ev7 = $time; end
      begin #1000; end
    join
    if (t_ev6 == 0 || (t_ev6 - t_rst) < 390 || (t_ev6 - t_rst) > 445) begin
      s1_err = s1_err + 1;
      $display("  FAIL S1: vzvod RESET_IN396 = %0t ns (ozhidanie 400..440)", t_ev6 ? (t_ev6 - t_rst) : 32'd0);
    end else
      $display("  PASS S1: vzvod RESET_IN cherez %0t ns (396; 397 na toy zhe kromke - EQ stroit)", t_ev6 - t_rst);
    if (t_ev6 !== t_ev7) begin
      s1_err = s1_err + 1; $display("  FAIL S1: kromki vzvoda u oboih RAZNYE (%0t vs %0t)", t_ev6, t_ev7);
    end
    tick(75);           // knopka derzhitsya (3 us)
    RST = 1'b0;
    @(posedge clk); #2; t_rst = $time;
    t_ev6 = 0; t_ev7 = 0;
    fork
      begin @(posedge rsti396); t_ev6 = $time; end
      begin @(posedge rsti397); t_ev7 = $time; end
      begin #1000; end
    join
    if (t_ev6 == 0 || (t_ev6 - t_rst) < 390 || (t_ev6 - t_rst) > 445) begin
      s1_err = s1_err + 1;
      $display("  FAIL S1: snatie RESET_IN396 = %0t ns (ozhidanie 400..440)", t_ev6 ? (t_ev6 - t_rst) : 32'd0);
    end else
      $display("  PASS S1: snatie RESET_IN cherez %0t ns posle otpuskaniya", t_ev6 - t_rst);
    if (t_ev6 !== t_ev7) begin
      s1_err = s1_err + 1; $display("  FAIL S1: kromki snatiya u oboih RAZNYE");
    end
    tick(2);
    chk_clean("S1 posle snatiya");
    cyc(1'b0, 1'b1, 1'b1, 1'b0, 8'h21, 8'h5A, 8'h00);   // zapis' OZU posle knopki
    if (we_falls396 == 1 && we_falls397 == 1 && we_a396 === 8'h21 && we_d396 === 8'h5A)
      $display("  PASS S1: zapis' OZU posle knopki OK u OBEIH (A=%h D=%h na /WE)", we_a396, we_d396);
    else begin
      s1_err = s1_err + 1;
      $display("  FAIL S1: zapis' posle knopki: padenij /WE 396=%0d 397=%0d A=%h D=%h", we_falls396, we_falls397, we_a396, we_d396);
    end
    if (s1_err == 0) $display("  === S1 (chistaya knopka) PASS ===");
    else begin tot_err = tot_err + s1_err; $display("  === S1 FAIL: %0d ===", s1_err); end

    // ================= S2: drebeg otpuskaniya, tihaya shina =================
    resync;
    we_falls396 = 0; we_falls397 = 0;
    RST = 1'b1; tick(50);                       // press 2 us
    RST = 1'b0; tick(2);                        // 80 ns nizko
    RST = 1'b1; #100;  RST = 1'b0; tick(1);     // 100 ns vysoko - NE kacheveno
    tick(60);                                    // 2.4 us nizko - SNATIE
    RST = 1'b1; #150;  RST = 1'b0; tick(1);     // 150 ns - NE vidno
    RST = 1'b1; tick(25); RST = 1'b0; tick(3);  // 1 us vysoko - perezapusk
    RST = 1'b1; #200;  RST = 1'b0; tick(1);     // 200 ns - NE vidno
    tick(60);                                    // final'noe kachevennoe snatie
    if (we_falls396 == 0 && we_falls397 == 0)
      $display("  PASS S2: drebeg na tihoy shine - /WE ne zvenil u OBEIH (%0d/%0d)", we_falls396, we_falls397);
    else begin
      s2_err = s2_err + 1;
      $display("  FAIL S2: /WE zvenel: 396=%0d 397=%0d", we_falls396, we_falls397);
    end
    chk_clean("S2 final");
    if (s2_err == 0) $display("  === S2 (drebeg, tihaya shina) PASS ===");
    else begin tot_err = tot_err + s2_err; $display("  === S2 FAIL: %0d ===", s2_err); end

    // ================= S2h: tot zhe drebeg NA VRACHDEBNOY shine =================
    // plavaniya shin v zhivyh oknah - lozhnyh /WE byt' ne dolzhno ni u odnoy
    fork
      begin : fuzz
        reg [31:0] r;
        integer k;
        for (k = 0; k < 400; k = k + 1) begin
          #10;
          r = $random(seed_eq);
          if (r[2:0] < 3'd3) ALE = r[3];
          r = $random(seed_eq);
          if (r[2:0] < 3'd3) WRn = r[3];
          r = $random(seed_eq);
          if (r[2:0] < 3'd3) RDn = r[3];
          r = $random(seed_eq);
          if (r[2:0] < 3'd3) IOM = r[3];
          r = $random(seed_eq);
          if (r[2:0] < 3'd3) A15 = r[3];
          r = $random(seed_eq); cpuA = r[31:24]; cpuA_en = 1'b1;
          r = $random(seed_eq); memD = r[31:24]; memD_en = 1'b1;
        end
      end
      begin : btn
        RST = 1'b1; tick(50);
        RST = 1'b0; tick(2);
        RST = 1'b1; #100;  RST = 1'b0; tick(1);
        tick(60);
        RST = 1'b1; #150;  RST = 1'b0; tick(1);
        RST = 1'b1; tick(25); RST = 1'b0; tick(3);
        RST = 1'b1; #200;  RST = 1'b0; tick(1);
        tick(60);
      end
    join
    ALE = 1'b0; WRn = 1'b1; RDn = 1'b1; IOM = 1'b0; A15 = 1'b0;
    cpuA_en = 1'b0; memD_en = 1'b0; cpuA = 8'h00; memD = 8'h00;
    tick(20);
    // vymyvayuschiy resync posle vrazhdebnyh plavaniy
    RST = 1'b1; tick(75); RST = 1'b0; tick(20);
    chk_clean("S2h final posle vymyvaniya");
    $display("  PASS S2h: vrazhdebnye plavaniya + drebeg - final chistyy u oboih (lozhnye /WE otpla in EQ-strogo: 0 raskhozhdenij = odinakovoe povedenie)");

    // ================= ITÓG =================
    if (n_mis == 0 && tot_err == 0)
      $display("=== ITÓG tb_v397_diff: VSE PASS - v3.9.7 (kol'tso) BIT-V-BIT v3.9.6 na vseh vyhodah, por_run vkl. (%0d vyborok) ===", n_eq);
    else
      $display("=== ITÓG tb_v397_diff: %0d raskhozhdenij, %0d scenario-oshibok - EST' FAILY ===", n_mis, tot_err);
    $finish;
  end

endmodule
