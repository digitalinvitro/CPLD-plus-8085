`timescale 1ns/1ps
//=====================================================================
// tb_v396_rst.v (lowsize, 2026-11-06): differential'naya simulyaciya
// v3.9.5 vs v3.9.6 po TSEPI SBROSA (mera p.21: hardrening - RST vhodit
// v kristall tol'ko cherez registry: 2FF-sinhronizator + kvalifikator
// 8 taktov + registrovyj RESET_IN = reset_q). Etalon = v3.9.5 (fit
// 11-5, zhaloba vladel'ca: "tol'ko vyk-vkl pitaniya vozvrashaet
// rabotosposobnost' po sbrosu").
//
// Scenarioi:
//  T0 POR: RESET_IN niz >= 840 ns (norma), podyom <= 1100 ns - u OBEIH;
//  EQ  ekvivalentnost' norm-puti: 600 sluchajnyh ciklov, sravnenie
//      vseh vyhodov i obeih shin kazhdye 5 ns (RST=0) - 0 raskhozhdenij;
//  S1 chistaya knopka: nazhatie 3 us, bystryj front: u v3.9.6
//      RESET_IN padaet/podnimaetsya cherez 440..480 ns (2FF+8 takt+
//      reset_q), tol'ko na kromke clk; posle otpuskaniya - vse 40 reg
//      v sbrosovom znachenii (chistyj start), polnaya zapis' OZU OK;
//  S3 glitchi 100/250 ns (< 280 ns = 8 taktov): u v3.9.6 NE sbasyvayut
//      NICHEGO (novoe svojstvo; v3.9.5 sbasyvaet - kontrast INFO);
//  S2 drebeg otpuskaniya (8 ekshkursij, tihaya shina): u v3.9.6
//      perezapusk tol'ko ot ekshkursij >= ~440 ns; WE_n==1 vsyo vremya
//      u obeih; final'noe snjatie - chistoe, odin front;
//  S2h tot zhe drebeg NA VRAZHDEBNOJ shine (plavaniya ALE/RDn/WRn/
//      IOM/A15/A/D v zhivyh oknah): lozhnyh /WE u v3.9.6 NE BOL'SHE
//      chem u v3.9.5; final'nyj peresbros (dlinnaya ekshkursiya)
//      VYCHISCHAET - vse reg chisty na final'nom snjatii - u obeih;
//  S4 sbros posredi /WE-impul'sa (WB2): v3.9.5 obryvaet mgnovenno;
//      v3.9.6 - impul's 80 ns DOVODITSYA DO KONCA (kvalifikator 400 ns
//      dleechem, polnyj t_WP), sbros vstupaet srazu posle (p.21f);
//      posle snjatya - chisto.
//  REG registrovost' RESET_IN v3.9.6: smena tol'ko na kromkah clk
//      (schetchik narushenij reg_viol396 == 0 za vsyo vremya).
//=====================================================================
module tb_v396_rst;

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
  wire [7:0] A395, A396, D395, D396;
  reg  [7:0] cpuA = 8'h00;   reg cpuA_en = 1'b0;
  reg  [7:0] memD = 8'h00;   reg memD_en = 1'b0;
  assign (weak0, weak1) A395 = cpuA_en ? cpuA : 8'hZZ;
  assign (weak0, weak1) A396 = cpuA_en ? cpuA : 8'hZZ;
  assign (weak0, weak1) D395 = memD_en ? memD : 8'hZZ;
  assign (weak0, weak1) D396 = memD_en ? memD : 8'hZZ;

  //-------------------------------------------------------------------
  // Vyhody
  //-------------------------------------------------------------------
  wire csr395, oer395, cs395n, oe395n, we395n, cs1_395, x1_395, rdy395, rsti395, sid395, tx395, snd395, x2_395;
  wire [7:0] seg395;  wire [3:0] dig395, col395;
  wire csr396, oer396, cs396n, oe396n, we396n, cs1_396, x1_396, rdy396, rsti396, sid396, tx396, snd396, x2_396;
  wire [7:0] seg396;  wire [3:0] dig396, col396;

  retro_pcld_top_v395 dut395 (
    .clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(A395), .D(D395),
    .CSr_n(csr395), .OEr_n(oer395), .CS_n(cs395n), .OE_n(oe395n), .WE_n(we395n), .CS1(cs1_395),
    .X1(x1_395), .READY(rdy395), .RESET_IN(rsti395),
    .SID(sid395), .TX(tx395), .seg(seg395), .dig(dig395), .SND(snd395),
    .X2(x2_395), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA),
    .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12), .AH13(AH13), .AH14(AH14),
    .RX(RX),
    .col0(col395[0]), .col1(col395[1]), .col2(col395[2]), .col3(col395[3]),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

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

  //-------------------------------------------------------------------
  // REG: registrovost' RESET_IN v3.9.6 - smena tol'ko na kromke clk
  // (v sim reset_q - NBA-registr: $time sobytiya == $time posedge).
  // U v3.9.5 RESET_IN kombinacionnyj ot RST - narusheniya OZHIDAYUTSYA
  // (otmechaem kak INFO, v verdikt ne vhodit).
  //-------------------------------------------------------------------
  integer reg_viol396 = 0;
  integer reg_viol395 = 0;
  always @(rsti396)
    if ($time > 1 && rsti396 !== 1'bx && $time != t_pe)
      reg_viol396 = reg_viol396 + 1;
  always @(rsti395)
    if ($time > 1 && rsti395 !== 1'bx && $time != t_pe)
      reg_viol395 = reg_viol395 + 1;

  //-------------------------------------------------------------------
  // T0: POR u obeih - niz RESET_IN >= 840 ns (norma 3 takta CLK OUT),
  // podyom <= 1100 ns (1020 ns po RTL, u v3.9.6 do +40 ns reset_q).
  //-------------------------------------------------------------------
  time t_rise395 = 0, t_rise396 = 0;
  integer por_err = 0;
  always @(posedge rsti395) if ($time <= 2000) t_rise395 = $time;
  always @(posedge rsti396) if ($time <= 2000) t_rise396 = $time;

  //-------------------------------------------------------------------
  // Ekvivalentnost' norm-puti: sravnenie kazhdye 5 ns pri cmp_en
  //-------------------------------------------------------------------
  reg cmp_en = 1'b0;
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
      cmp1(csr395, csr396, "CSr_n");
      cmp1(oer395, oer396, "OEr_n");
      cmp1(cs395n, cs396n, "CS_n");
      cmp1(oe395n, oe396n, "OE_n");
      cmp1(we395n, we396n, "WE_n");
      cmp1(cs1_395, cs1_396, "CS1");
      cmp1(x1_395, x1_396, "X1");
      cmp1(x2_395, x2_396, "X2");
      cmp1(rdy395, rdy396, "READY");
      cmp1(rsti395, rsti396, "RESET_IN");
      cmp1(sid395, sid396, "SID");
      cmp1(tx395, tx396, "TX");
      cmp1(snd395, snd396, "SND");
      cmp8(seg395, seg396, "seg");
      cmp4(dig395, dig396, "dig");
      cmp4(col395, col396, "col");
      cmp8(A395, A396, "A-bus");
      cmp8(D395, D396, "D-bus");
    end
  end

  //-------------------------------------------------------------------
  // Schetchiki /WE (vsplesk = negedge) i legkie logi zapisej
  //-------------------------------------------------------------------
  integer we_falls395 = 0, we_falls396 = 0;
  reg [7:0] we_a395 = 0, we_d395 = 0, we_a396 = 0, we_d396 = 0;
  always @(negedge we395n) begin
    we_falls395 = we_falls395 + 1;
    we_a395 = A395; we_d395 = D395;
  end
  always @(negedge we396n) begin
    we_falls396 = we_falls396 + 1;
    we_a396 = A396; we_d396 = D396;
  end

  //-------------------------------------------------------------------
  // Chistota 40 registrov sbrosovogo domena (ierarhicheski)
  //-------------------------------------------------------------------
  task chk_clean396(input [8*32-1:0] where);
    integer e;
    begin
      e = 0;
      if (dut396.state      !== 3'd0)   begin e = e + 1; $display("  DIRTY396 %0s: state=%0d", where, dut396.state); end
      if (dut396.rd_seen    !== 1'b0)   begin e = e + 1; $display("  DIRTY396 %0s: rd_seen=%b", where, dut396.rd_seen); end
      if (dut396.wr_seen    !== 1'b0)   begin e = e + 1; $display("  DIRTY396 %0s: wr_seen=%b", where, dut396.wr_seen); end
      if (dut396.addr_latch !== 8'h00)  begin e = e + 1; $display("  DIRTY396 %0s: addr_latch=%h", where, dut396.addr_latch); end
      if (dut396.bus_reg    !== 8'h00)  begin e = e + 1; $display("  DIRTY396 %0s: bus_reg=%h", where, dut396.bus_reg); end
      if (dut396.seg_q      !== 8'hFF)  begin e = e + 1; $display("  DIRTY396 %0s: seg_q=%h", where, dut396.seg_q); end
      if (dut396.dig_q      !== 4'hF)   begin e = e + 1; $display("  DIRTY396 %0s: dig_q=%h", where, dut396.dig_q); end
      if (dut396.snd_q      !== 1'b0)   begin e = e + 1; $display("  DIRTY396 %0s: snd_q=%b", where, dut396.snd_q); end
      if (dut396.kbcol_q    !== 4'h0)   begin e = e + 1; $display("  DIRTY396 %0s: kbcol_q=%h", where, dut396.kbcol_q); end
      if (dut396.tx_pass    !== 1'b0)   begin e = e + 1; $display("  DIRTY396 %0s: tx_pass=%b", where, dut396.tx_pass); end
      if (dut396.tx_q       !== 1'b1)   begin e = e + 1; $display("  DIRTY396 %0s: tx_q=%b", where, dut396.tx_q); end
      if (e == 0) $display("  PASS clean396 %0s (vse reg v sbrosovom znachenii)", where);
      else        $display("  FAIL clean396 %0s: %0d polej isportcheno", where, e);
    end
  endtask

  task chk_clean395(input [8*32-1:0] where);
    integer e;
    begin
      e = 0;
      if (dut395.state      !== 3'd0)   e = e + 1;
      if (dut395.rd_seen    !== 1'b0)   e = e + 1;
      if (dut395.wr_seen    !== 1'b0)   e = e + 1;
      if (dut395.addr_latch !== 8'h00)  e = e + 1;
      if (dut395.bus_reg    !== 8'h00)  e = e + 1;
      if (dut395.seg_q      !== 8'hFF)  e = e + 1;
      if (dut395.dig_q      !== 4'hF)   e = e + 1;
      if (dut395.snd_q      !== 1'b0)   e = e + 1;
      if (dut395.kbcol_q    !== 4'h0)   e = e + 1;
      if (dut395.tx_pass    !== 1'b0)   e = e + 1;
      if (dut395.tx_q       !== 1'b1)   e = e + 1;
      if (e == 0) $display("  PASS clean395 %0s", where);
      else        $display("  FAIL clean395 %0s: %0d polej", where, e);
    end
  endtask

  //-------------------------------------------------------------------
  // Stimul: tik; polnyj shinnyj cikl (T1+T2+zazor)
  //-------------------------------------------------------------------
  integer verbose = 0;

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

  //-------------------------------------------------------------------
  // Resinkh posle scenariya: polnyj kvalificirovannyj sbros u obeih
  // (knopka 3 us, bystryj front) + vymyvayuschij cikl chteniya
  //-------------------------------------------------------------------
  task resync;
    begin
      RST = 1'b1; tick(75); RST = 1'b0;
      tick(20);                        // 440 ns snjatija + zapas
      cyc(1'b0, 1'b0, 1'b0, 1'b1, 8'h00, 8'h00, 8'h00); // vymyvayuschee chtenie
    end
  endtask

  //-------------------------------------------------------------------
  // Osnovnoj process
  //-------------------------------------------------------------------
  integer i;
  integer s1_err = 0, s2_err = 0, s2h_err = 0, s3_err = 0, s4_err = 0;
  time    t_rst, t_ev, t_r4;
  reg     dip395, hold396;
  reg [2:0] st_before;
  reg [7:0] al_before, br_before;
  integer seed_eq = 32'hABCD_6001;
  integer seed_h = 32'hF0A0_B0C0;
  reg [7:0] ad, dt;

  initial begin
    // ================= T0: POR =================
    tick(40);   // 1600 ns - POR u oboih zavershon
    if (t_rise395 < 840 || t_rise395 > 1100) begin
      por_err = por_err + 1; $display("  FAIL POR395: podyom na %0t ns", t_rise395);
    end else $display("  PASS POR395: niz RESET_IN %0t ns (norma >= 840)", t_rise395);
    if (t_rise396 < 840 || t_rise396 > 1100) begin
      por_err = por_err + 1; $display("  FAIL POR396: podyom na %0t ns", t_rise396);
    end else $display("  PASS POR396: niz RESET_IN %0t ns (norma >= 840)", t_rise396);

    // ================= EQ: 600 sluchajnyh ciklov =================
    cmp_en = 1'b1;
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
    cmp_en = 1'b0;
    if (n_mis == 0) $display("  PASS EQ: %0d vyborok 5 ns, 0 raskhozhdenij (norm-put' bit-v-bit)", n_eq);
    else            $display("  FAIL EQ: %0d raskhozhdenij na %0d vyborok", n_mis, n_eq);

    // ================= S1: chistaya knopka =================
    we_falls396 = 0; we_falls395 = 0;
    RST = 1'b1;
    @(posedge clk); #2; t_rst = $time;
    t_ev = 0;
    fork
      begin @(negedge rsti396); if (t_ev == 0) t_ev = $time; end
      begin #1000; end
    join
    if (t_ev == 0 || (t_ev - t_rst) < 390 || (t_ev - t_rst) > 445) begin
      s1_err = s1_err + 1;
      $display("  FAIL S1: latentionnost' vzvoda RESET_IN396 = %0t ns (ozhidanie 400..440)", t_ev ? (t_ev - t_rst) : 32'd0);
    end else
      $display("  PASS S1: vzvod RESET_IN396 cherez %0t ns posle RST (2FF+8takt+reset_q)", t_ev - t_rst);
    tick(75);           // knopka derzhitsya (3 us)
    RST = 1'b0;
    @(posedge clk); #2; t_rst = $time;
    t_ev = 0;
    fork
      begin @(posedge rsti396); if (t_ev == 0) t_ev = $time; end
      begin #1000; end
    join
    if (t_ev == 0 || (t_ev - t_rst) < 390 || (t_ev - t_rst) > 445) begin
      s1_err = s1_err + 1;
      $display("  FAIL S1: latentionnost' snjatija RESET_IN396 = %0t ns (ozhidanie 400..440)", t_ev ? (t_ev - t_rst) : 32'd0);
    end else
      $display("  PASS S1: snjatie RESET_IN396 cherez %0t ns posle otpuskaniya knopki", t_ev - t_rst);
    tick(2);            // +1 tik posle snjatija
    chk_clean396("S1 posle snjatija");
    chk_clean395("S1 posle snjatija");
    // polnaya zapis' OZU posle knopki - adres/dannye na /WE
    cyc(1'b0, 1'b1, 1'b1, 1'b0, 8'h21, 8'h5A, 8'h00);
    if (we_falls396 == 1 && we_a396 === 8'h21 && we_d396 === 8'h5A)
      $display("  PASS S1: zapis' OZU posle knopki OK (A=%h D=%h na /WE)", we_a396, we_d396);
    else begin
      s1_err = s1_err + 1;
      $display("  FAIL S1: zapis' posle knopki: padenij /WE=%0d A=%h D=%h", we_falls396, we_a396, we_d396);
    end
    if (s1_err == 0) $display("  === S1 (chistaya knopka) PASS ===");
    else             $display("  === S1 (chistaya knopka) FAIL: %0d ===", s1_err);

    // ================= S3: glitchi 100/250 ns =================
    resync;
    st_before = dut396.state; al_before = dut396.addr_latch; br_before = dut396.bus_reg;
    // glitch 100 ns (seredina cikla, NE na kromke)
    @(negedge clk); #7; RST = 1'b1; #10;
    hold396 = (rsti396 === 1'b1);   // v3.9.6 derzhit v mid-glitch
    dip395  = (rsti395 === 1'b0);   // v3.9.5 padaet mgnovenno (kontrast)
    #90; RST = 1'b0;
    tick(3);
    if (hold396)
      $display("  PASS S3: glitch 100 ns - RESET_IN396 ne drognul (i v mid-glitch)");
    else begin
      s3_err = s3_err + 1; $display("  FAIL S3: glitch 100 ns sbrosil RESET_IN396");
    end
    if (dip395)
      $display("  INFO S3: v3.9.5 na tot zhe glitch 100 ns OTREAGIROVAL mgnovenno (kontrast mer)");
    if (dut396.state === st_before[2:0] && dut396.addr_latch === al_before && dut396.bus_reg === br_before)
      $display("  PASS S3: sostoyanie396 ne izmenilos' posle glitch 100 ns");
    else begin
      s3_err = s3_err + 1; $display("  FAIL S3: sostoyanie396 izmenilos' ot glitch 100 ns");
    end
    // glitch 250 ns na shume vsyo to zhe
    @(negedge clk); #13; RST = 1'b1; #10;
    hold396 = (rsti396 === 1'b1);
    #240; RST = 1'b0;
    tick(3);
    if (hold396)
      $display("  PASS S3: glitch 250 ns - RESET_IN396 ne drognul");
    else begin
      s3_err = s3_err + 1; $display("  FAIL S3: glitch 250 ns sbrosil RESET_IN396");
    end
    tick(3);
    if (s3_err == 0) $display("  === S3 (glitchi < 280 ns) PASS ===");
    else             $display("  === S3 (glitchi) FAIL: %0d ===", s3_err);

    // ================= S2: drebeg otpuskaniya, tihaya shina =================
    resync;
    we_falls396 = 0; we_falls395 = 0;
    RST = 1'b1; tick(50);                       // press 2 us
    RST = 1'b0; tick(2);                        // 80 ns nizko - ne zaschitano
    RST = 1'b1; #100;  RST = 1'b0; tick(1);     // 100 ns vysoko - NE kvalificiruetsya
    tick(60);                                    // 2.4 us nizko - KVALIFICIROVANNOE snjatie
    RST = 1'b1; #150;  RST = 1'b0; tick(1);     // 150 ns - NE vidno
    RST = 1'b1; tick(25); RST = 1'b0; tick(3);  // 1 us vysoko - perezapusk
    RST = 1'b1; #200;  RST = 1'b0; tick(1);     // 200 ns - NE vidno
    RST = 1'b1; tick(15); RST = 1'b0; tick(2);  // 600 ns - perezapusk
    RST = 1'b1; #120;  RST = 1'b0; tick(1);     // 120 ns - NE vidno
    RST = 1'b1; tick(20); RST = 1'b0;           // 800 ns - perezapusk, dalee final'noe nizko
    tick(14);                                    // dozhit'sya kvalificirovannogo snjatija (400 ns + zapas)
    if (we_falls396 != 0 || we_falls395 != 0) begin
      s2_err = s2_err + 1;
      $display("  FAIL S2: lozhnye /WE pri tihoy shine (395: %0d, 396: %0d)", we_falls395, we_falls396);
    end else
      $display("  PASS S2: /WE ne zvenel u obeih za vsyo fazu drebega");
    chk_clean396("S2 final'noe snjatie");
    chk_clean395("S2 final'noe snjatie");
    cyc(1'b0, 1'b1, 1'b1, 1'b0, 8'h33, 8'hC3, 8'h00);
    if (we_a396 === 8'h33 && we_d396 === 8'hC3)
      $display("  PASS S2: zapis' posle drebega OK (A=%h D=%h)", we_a396, we_d396);
    else begin
      s2_err = s2_err + 1; $display("  FAIL S2: zapis' posle drebega slomana (A=%h D=%h)", we_a396, we_d396);
    end
    if (s2_err == 0) $display("  === S2 (drebeg, tihaya shina) PASS ===");
    else             $display("  === S2 FAIL: %0d ===", s2_err);

    // ================= S2h: drebeg NA VRAZHDEBNOJ shine =================
    // zhivye okna: posle kvalificirovannyh proyashkov nizko FSM zhivet
    // na sluchajnoj shine (model' plavayushej shiny CPU). Final'naya
    // dlinnaya ekshkursiya (800 ns vysoko) vychischaet: na final'nom
    // snjatii vse reg chisty - u OBEIH. Vrazhdebnaya shina ostanavlivaetsya
    // DO final'nogo peresbrosa; schetchiki /WE - INFO (zavisyat od sida).
    resync;
    we_falls396 = 0; we_falls395 = 0;
    fork
      begin : hostile
        repeat (120) begin
          #37;
          ALE = $random(seed_h) & 1; WRn = $random(seed_h) & 1;
          RDn = $random(seed_h) & 1; IOM = $random(seed_h) & 1;
          A15 = $random(seed_h) & 1;
          cpuA = $random(seed_h); cpuA_en = 1'b1;
          memD = $random(seed_h); memD_en = 1'b1;
        end
        ALE = 0; WRn = 1; RDn = 1; IOM = 0; A15 = 0; cpuA_en = 0; memD_en = 0;
      end
      begin : bounce
        RST = 1'b1; tick(50);
        RST = 1'b0; tick(14);          // kvalific. snjatie - zhivoe okno na vrazhdebnoj shine
        RST = 1'b1; #150; RST = 1'b0; tick(1);
        RST = 1'b1; tick(25); RST = 1'b0; tick(8);   // perezapusk - vychischaet
        RST = 1'b0; tick(10);          // zhivoe okno
        RST = 1'b1; #200; RST = 1'b0; tick(1);       // korotko - ne vidno
        RST = 1'b1; tick(20); RST = 1'b0;            // final'nyj dlinnyj peresbros
      end
    join
    tick(14);                          // dozhit'sya final'nogo snjatija (400 ns + zapas)
    chk_clean396("S2h final'noe snjatie");
    chk_clean395("S2h final'noe snjatie");
    $display("  INFO S2h: lozhnyh /WE za fazu: 395=%0d 396=%0d (ne invariant - zavisit ot sida)", we_falls395, we_falls396);
    if (s2h_err == 0) $display("  === S2h (drebeg, vrazhdebnaya shina) PASS ===");
    else              $display("  === S2h FAIL: %0d ===", s2h_err);

    // ================= S4: sbros posredi /WE-impul'sa =================
    resync;
    we_falls396 = 0;
    cpuA = 8'h44; cpuA_en = 1'b1; IOM = 1'b0; A15 = 1'b1; ALE = 1'b1;
    tick(4); ALE = 1'b0;
    cpuA = 8'h77; WRn = 1'b0; tick(3); WRn = 1'b1; cpuA_en = 1'b0;
    tick(2);                                   // e9: WB2 - /WE nizko
    if (we396n === 1'b0 && we395n === 1'b0)
      $display("  PASS S4: /WE nizko u obeih (impul's WB idet)");
    else begin
      s4_err = s4_err + 1;
      $display("  FAIL S4: /WE ne vstal nizko k WB2 (396=%b 395=%b)", we396n, we395n);
    end
    RST = 1'b1; t_r4 = $time; #10;          // sbros na ah /WE
    if (we395n === 1'b1)
      $display("  PASS S4a: v3.9.5 gasit /WE mgnovenno (10 ns)");
    else begin
      s4_err = s4_err + 1; $display("  FAIL S4a: v3.9.5 ne gasit /WE za 10 ns");
    end
    t_ev = 0;
    fork
      begin @(posedge we396n); if (t_ev == 0) t_ev = $time; end
      begin #800; end
    join
    // Semantika v3.9.6: impul's /WE (80 ns, WB2+WB3) NE OBRYVAETSYA -
    // kvalifikator (400 ns) dleechem impul'sa; on dovoditsya do konca
    // (dazhe bezopasnee obryva - polnyj t_WP pamyati), sbros vstupit
    // srazu posle. v3.9.5 obryvaet mgnovenno.
    if (t_ev != 0 && (t_ev - t_r4) >= 60 && (t_ev - t_r4) <= 130)
      $display("  PASS S4b: v3.9.6 dovodit /WE do konca (%0t ps, 80 ns impul's), sbros vstupit posle", t_ev - t_r4);
    else begin
      s4_err = s4_err + 1; $display("  FAIL S4b: /WE396 upal na %0t ps (ozhidanie 60..130 - estestvennyj konec impul'sa)", t_ev ? (t_ev - t_r4) : 32'd0);
    end
    if (rsti396 === 1'b0 && dut396.state === 3'd0)
      $display("  PASS S4c: sbros396 vstupil k +800 ns (RESET_IN=0, FSM=IDLE)");
    else begin
      s4_err = s4_err + 1; $display("  FAIL S4c: sbros396 ne vstupil k +800 ns (rsti=%b state=%0d)", rsti396, dut396.state);
    end
    tick(75); RST = 1'b0; tick(20);
    chk_clean396("S4 posle snjatija");
    cyc(1'b0, 1'b1, 1'b1, 1'b0, 8'h55, 8'hAE, 8'h00);
    if (we_a396 === 8'h55 && we_d396 === 8'hAE)
      $display("  PASS S4: zapis' posle sbrosa-posredi-/WE OK");
    else begin
      s4_err = s4_err + 1; $display("  FAIL S4: zapis' posle sbrosa-posredi-/WE slomana (A=%h D=%h)", we_a396, we_d396);
    end
    if (s4_err == 0) $display("  === S4 (sbros posredi /WE) PASS ===");
    else             $display("  === S4 FAIL: %0d ===", s4_err);

    // ================= ITOG =================
    $display("");
    $display("================ ITOG tb_v396_rst ================");
    $display("  T0  POR (oba) .............. %s", por_err ? "FAIL" : "PASS");
    $display("  EQ  norm-put' 600 ciklov ... %s", n_mis ? "FAIL" : "PASS");
    $display("  S1  chistaya knopka ........ %s", s1_err ? "FAIL" : "PASS");
    $display("  S3  glitchi 100/250 ns ..... %s", s3_err ? "FAIL" : "PASS");
    $display("  S2  drebeg (tihaya shina) .. %s", s2_err ? "FAIL" : "PASS");
    $display("  S2h drebeg (vrazhdeb.shina)  %s", s2h_err ? "FAIL" : "PASS");
    $display("  S4  sbros posredi /WE ...... %s", s4_err ? "FAIL" : "PASS");
    $display("  REG narushenij registrovosti RESET_IN396: %0d (dolzhno byt' 0)", reg_viol396);
    $display("  INFO: narushenij u kombinacionnogo RESET_IN395: %0d", reg_viol395);
    if (por_err == 0 && n_mis == 0 && s1_err == 0 && s2_err == 0 && s2h_err == 0 &&
        s3_err == 0 && s4_err == 0 && reg_viol396 == 0)
      $display("VERDIKT: VSE PASS");
    else
      $display("VERDIKT: EST' PROVALY");
    $finish;
  end

  //-------------------------------------------------------------------
  // Strahovka po vremeni
  //-------------------------------------------------------------------
  initial begin
    #2_000_000;
    $display("TIMEOUT");
    $finish;
  end
endmodule
