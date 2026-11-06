`timescale 1ns/1ps
//=====================================================================
// tb_v398_diff.v (lowsize, 2026-11-06): DIFFerencial'naya simulyaciya
// v3.9.7 vs v3.9.8 (mera p.23: vhod CPLD 50 MGc, kol'tso r0..r6 na
// clk 50, X1 = r0, X2 = OR(r1..r6), clk25 = /2 - takt logiki, por-cep'
// v 50-domene so stroboom r0). ETALON = v3.9.7 (kol'tso na 25 + x1_n).
//
// UTVERZHDENIE: pererabotka uzla takktirovaniya NE vidna na NIKAKOM
// vyhode logiki ni v ODNOY faze:
//   - logika (rst/TX/FSM/porty) taktiruetsya clk25 = /2-triggers s
//     TEM ZHE periodom 40 ns i NOLEVYM sdvigom fazy otnositel'no
//     stimulusa tb (clk25 posedge sovpadayut s posedge tb-clk 25 MGc:
//     clk50 INIT=1 daet posedge 20+20k, clk25_q INIT=0 - pod'emy na
//     20+40k);
//   - por-cep': drayn 8 strrobov r0 = 1000 ns (u v3.9.7: 4 strroba
//     x1_n = 1000 ns) - por_run padaet NA TOY ZHE kromke 1020 ns,
//     reset_q podnimaetsya na TOY ZHE kromke 1060 ns u OBEIH;
//   - sravnenie STROGOE s t=0: vse vyhody logiki i obe shiny kazhdye
//     5 ns, POR i knopka vklyuchitel'no, okon maskirovki NET.
// X1/X2 iz sravneniya ISKLYUCHENY ZAKONOMERNO: menyaetsya duty
// (v3.9.7: 100/40, v3.9.8: 20/120 - v_otv na skhemu vladel'ca);
// proveryayutsya ODEL'NO (XP): period 140 ns u OBEIH, X2 == ~X1
// posle POR, duty monitor na kazhdom.
//
// Scenarii:
//  T0  POR: niz RESET_IN 840..1100 ns u OBEIH (norma >= 840);
//  EQ  600 sluchaynyh ciklov shiny - 0 raskhozhdeniy;
//  XP  X1: period 140 ns u oboih; duty: v3.9.7 100/40, v3.9.8
//      20/120 (duty 1/7); X2 == ~X1 posle POR u oboih; clk25_q
//      togglitsya (takt logiki zhiv);
//  S1  chistaya knopka: 400..445 ns u OBEIH, zapis' OZU posle knopki;
//  S2/S2h drebeg na tihoy/vrazhdebnoy shine - bit-v-bit.
//=====================================================================
module tb_v398_diff;

  //-------------------------------------------------------------------
  // Takt: tb/dut397 - 25 MGc (etakonnyy domEN logiki); dut398 - 50 MGc
  // (INIT=1: posedge 20+20k - sovpadaet s kromkami tb-clk)
  //-------------------------------------------------------------------
  reg clk = 1'b0;
  always #20 clk = ~clk;
  reg clk50 = 1'b1;
  always #10 clk50 = ~clk50;

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
  wire [7:0] A397, A398, D397, D398;
  reg  [7:0] cpuA = 8'h00;   reg cpuA_en = 1'b0;
  reg  [7:0] memD = 8'h00;   reg memD_en = 1'b0;
  assign (weak0, weak1) A397 = cpuA_en ? cpuA : 8'hZZ;
  assign (weak0, weak1) A398 = cpuA_en ? cpuA : 8'hZZ;
  assign (weak0, weak1) D397 = memD_en ? memD : 8'hZZ;
  assign (weak0, weak1) D398 = memD_en ? memD : 8'hZZ;

  //-------------------------------------------------------------------
  // Vyhody
  //-------------------------------------------------------------------
  wire csr397, oer397, cs397n, oe397n, we397n, cs1_397, x1_397, rdy397, rsti397, sid397, tx397, snd397, x2_397;
  wire [7:0] seg397;  wire [3:0] dig397, col397;
  wire csr398, oer398, cs398n, oe398n, we398n, cs1_398, x1_398, rdy398, rsti398, sid398, tx398, snd398, x2_398;
  wire [7:0] seg398;  wire [3:0] dig398, col398;

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

  retro_pcld_top_v398 dut398 (
    .clk(clk50), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(A398), .D(D398),
    .CSr_n(csr398), .OEr_n(oer398), .CS_n(cs398n), .OE_n(oe398n), .WE_n(we398n), .CS1(cs1_398),
    .X1(x1_398), .READY(rdy398), .RESET_IN(rsti398),
    .SID(sid398), .TX(tx398), .seg(seg398), .dig(dig398), .SND(snd398),
    .X2(x2_398), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA),
    .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12), .AH13(AH13), .AH14(AH14),
    .RX(RX),
    .col0(col398[0]), .col1(col398[1]), .col2(col398[2]), .col3(col398[3]),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

  //-------------------------------------------------------------------
  // XP: X2 == ~X1 - schet posle POR (v illegal-kodah kol'tca na
  // samoocistke X2=OR(r1..r6) mozhet otlichat'sya ot ~X1 do 2 frontov
  // - zhaloby net: CPU v POR; v ustoyavshemsya rezhime ravno TOL'KO
  // v legal'nom one-hot). U v3.9.7 ravno vsegda.
  //-------------------------------------------------------------------
  reg xp_en = 1'b0;
  integer x2_mis397 = 0, x2_mis398 = 0;
  always #5 begin
    if (xp_en) begin
      if (x2_397 !== ~x1_397) x2_mis397 = x2_mis397 + 1;
      if (x2_398 !== ~x1_398) x2_mis398 = x2_mis398 + 1;
    end
  end

  // period X1 (posedges) i duty (high/low width) - u OBEIH, posle POR.
  // t_x1a - vremya predydushchego POSEDGE, t_x1r - vremya poslednego
  // KRAYA (lyubogo): na posedge period = t - t_x1a, low = t - t_x1r
  // (t_x1r = negedge); na negedge high = t - t_x1r.
  time t_x1a397 = 0, t_x1r397 = 0;
  time t_x1a398 = 0, t_x1r398 = 0;
  real  p_min397 = 1e9, p_max397 = 0, h_min397 = 1e9, h_max397 = 0, l_min397 = 1e9, l_max397 = 0;
  real  p_min398 = 1e9, p_max398 = 0, h_min398 = 1e9, h_max398 = 0, l_min398 = 1e9, l_max398 = 0;
  always @(posedge x1_397) begin
    if (xp_en && t_x1r397 > 0) begin
      if (($time - t_x1a397) < p_min397) p_min397 = $time - t_x1a397;
      if (($time - t_x1a397) > p_max397) p_max397 = $time - t_x1a397;
      if (($time - t_x1r397) < l_min397) l_min397 = $time - t_x1r397;
      if (($time - t_x1r397) > l_max397) l_max397 = $time - t_x1r397;
    end
    t_x1a397 = $time; t_x1r397 = $time;
  end
  always @(negedge x1_397) begin
    if (xp_en && t_x1r397 > 0) begin
      if (($time - t_x1r397) < h_min397) h_min397 = $time - t_x1r397;
      if (($time - t_x1r397) > h_max397) h_max397 = $time - t_x1r397;
    end
    t_x1r397 = $time;
  end
  always @(posedge x1_398) begin
    if (xp_en && t_x1r398 > 0) begin
      if (($time - t_x1a398) < p_min398) p_min398 = $time - t_x1a398;
      if (($time - t_x1a398) > p_max398) p_max398 = $time - t_x1a398;
      if (($time - t_x1r398) < l_min398) l_min398 = $time - t_x1r398;
      if (($time - t_x1r398) > l_max398) l_max398 = $time - t_x1r398;
    end
    t_x1a398 = $time; t_x1r398 = $time;
  end
  always @(negedge x1_398) begin
    if (xp_en && t_x1r398 > 0) begin
      if (($time - t_x1r398) < h_min398) h_min398 = $time - t_x1r398;
      if (($time - t_x1r398) > h_max398) h_max398 = $time - t_x1r398;
    end
    t_x1r398 = $time;
  end

  // clk25_q dut398: togglit'sya (takt logiki zhiv)
  integer c25_tog = 0;
  always @(dut398.clk25_q) c25_tog = c25_tog + 1;

  //-------------------------------------------------------------------
  // Gasim artefakt Icarus: INIT clk50=1 - eto perehod x->1 v t=0,
  // kotoruyu simulyator schitaet POSEDGE - uzel v3.9.8 delaet "lishnij"
  // sdvig kol'ca/por_cepi i clk25_q vzleta na 20 ns ranshe etalona.
  // Vozvrashaem d8 v INIT-sostoyanie (kak JED) posle fantomnogo fronta:
  // dalee vse kromki clk25 sovpadayut s kromkami clk etalona (20+40k).
  //-------------------------------------------------------------------
  initial begin
    #1;
    dut398.r0 = 1'b1; dut398.r1 = 1'b0; dut398.r2 = 1'b0; dut398.r3 = 1'b0;
    dut398.r4 = 1'b0; dut398.r5 = 1'b0; dut398.r6 = 1'b0;
    dut398.por_sh = 8'hFF;
    dut398.por_run = 1'b1;
    dut398.clk25_q = 1'b0;
  end

  //-------------------------------------------------------------------
  // Ekvivalentnost': sravnenie kazhdye 5 ns pri cmp_en (STROGO - s t=0)
  // X1/X2 ISKLYUCHENY (zakonomernaya delta duty - proveryayutsya v XP)
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
      cmp1(csr397, csr398, "CSr_n");
      cmp1(oer397, oer398, "OEr_n");
      cmp1(cs397n, cs398n, "CS_n");
      cmp1(oe397n, oe398n, "OE_n");
      cmp1(we397n, we398n, "WE_n");
      cmp1(cs1_397, cs1_398, "CS1");
      cmp1(rdy397, rdy398, "READY");
      cmp1(rsti397, rsti398, "RESET_IN");
      cmp1(sid397, sid398, "SID");
      cmp1(tx397, tx398, "TX");
      cmp1(snd397, snd398, "SND");
      cmp8(seg397, seg398, "seg");
      cmp4(dig397, dig398, "dig");
      cmp4(col397, col398, "col");
      cmp8(A397, A398, "A-bus");
      cmp8(D397, D398, "D-bus");
      // vnutrennee por_run: padaet NA TOY ZHE kromke 1020 ns u oboih
      cmp1(dut397.por_run, dut398.por_run, "por_run");
    end
  end

  //-------------------------------------------------------------------
  // Schetchiki /WE (negedge) s adresom/dannymi
  //-------------------------------------------------------------------
  integer we_falls397 = 0, we_falls398 = 0;
  reg [7:0] we_a397 = 0, we_d397 = 0, we_a398 = 0, we_d398 = 0;
  always @(negedge we397n) begin
    we_falls397 = we_falls397 + 1;
    we_a397 = A397; we_d397 = D397;
  end
  always @(negedge we398n) begin
    we_falls398 = we_falls398 + 1;
    we_a398 = A398; we_d398 = D398;
  end

  //-------------------------------------------------------------------
  // Chistota sbrosovogo domena (hierarhicheski) - obe DUT
  //-------------------------------------------------------------------
  task chk_clean(input [8*32-1:0] where);
    integer e;
    begin
      e = 0;
      if (dut397.state      !== 3'd0)   begin e = e + 1; $display("  DIRTY397 %0s: state=%0d", where, dut397.state); end
      if (dut397.addr_latch !== 8'h00)  begin e = e + 1; $display("  DIRTY397 %0s: addr_latch=%h", where, dut397.addr_latch); end
      if (dut397.seg_q      !== 8'hFF)  begin e = e + 1; $display("  DIRTY397 %0s: seg_q=%h", where, dut397.seg_q); end
      if (dut398.state      !== 3'd0)   begin e = e + 1; $display("  DIRTY398 %0s: state=%0d", where, dut398.state); end
      if (dut398.addr_latch !== 8'h00)  begin e = e + 1; $display("  DIRTY398 %0s: addr_latch=%h", where, dut398.addr_latch); end
      if (dut398.seg_q      !== 8'hFF)  begin e = e + 1; $display("  DIRTY398 %0s: seg_q=%h", where, dut398.seg_q); end
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
  time    t_rst, t_ev, t_ev7, t_ev8;
  reg [7:0] ad, dt;
  integer seed_eq = 32'hBEEF_3981;

  initial begin
    $display("=== tb_v398_diff: v3.9.7 (etalon, 25 MGc) vs v3.9.8 (50 MGc + clk25) - STROGOE sravnenie s t=0 ===");

    // ================= T0: POR =================
    tick(40);   // 1600 ns - POR u oboih zavershon
    if (rsti397 !== 1'b1 || rsti398 !== 1'b1) begin
      s1_err = s1_err + 1; $display("  FAIL T0: RESET_IN ne snyalsya za 1600 ns (397=%b 398=%b)", rsti397, rsti398);
    end else
      $display("  PASS T0: POR zavershon u oboih k 1600 ns (niz/ podyom NA TEH ZHE kromkah - sravnenie strogoe s t=0)");

    // ================= EQ: 600 sluchaynyh ciklov =================
    xp_en = 1'b1;                        // X2==~X1 i duty-monitory - posle POR
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
    if (n_mis == 0) $display("  PASS EQ: %0d vyborok 5 ns (vkl. por_run), 0 raskhozhdenij - logika bit-v-bit", n_eq);
    else begin
      tot_err = tot_err + 1;
      $display("  FAIL EQ: %0d raskhozhdenij na %0d vyborok", n_mis, n_eq);
    end

    // ================= XP: X1/X2 u oboih =================
    if (x2_mis397 == 0 && x2_mis398 == 0)
      $display("  PASS XP: X2 == ~X1 v KAZHDOJ vyborke posle POR u oboih");
    else begin
      tot_err = tot_err + 1;
      $display("  FAIL XP: X2 != ~X1 posle POR: v3.9.7 %0d raz, v3.9.8 %0d raz", x2_mis397, x2_mis398);
    end
    if (p_min397 >= 135 && p_max397 <= 145 && p_min398 >= 135 && p_max398 <= 145)
      $display("  PASS XP: periody X1 397: %0t..%0t, 398: %0t..%0t - Rovno 140 (7,143 MGc) u OBEIH", p_min397, p_max397, p_min398, p_max398);
    else begin
      tot_err = tot_err + 1;
      $display("  FAIL XP: periody X1 397: %0t..%0t, 398: %0t..%0t - ne 140", p_min397, p_max397, p_min398, p_max398);
    end
    if (h_min397 >= 95 && h_max397 <= 105 && l_min397 >= 35 && l_max397 <= 45)
      $display("  PASS XP: duty X1 v3.9.7 high %0t..%0t / low %0t..%0t - etalon 100/40", h_min397, h_max397, l_min397, l_max397);
    else begin
      tot_err = tot_err + 1;
      $display("  FAIL XP: duty X1 v3.9.7 high %0t..%0t / low %0t..%0t - ne 100/40", h_min397, h_max397, l_min397, l_max397);
    end
    if (h_min398 >= 15 && h_max398 <= 25 && l_min398 >= 115 && l_max398 <= 125)
      $display("  PASS XP: duty X1 v3.9.8 high %0t..%0t / low %0t..%0t - skhema vladel'ca 20/120 (duty 1/7)", h_min398, h_max398, l_min398, l_max398);
    else begin
      tot_err = tot_err + 1;
      $display("  FAIL XP: duty X1 v3.9.8 high %0t..%0t / low %0t..%0t - ne 20/120", h_min398, h_max398, l_min398, l_max398);
    end
    if (c25_tog > 100)
      $display("  PASS XP: clk25_q togglilsya %0d raz (takt logiki 25 MGc zhiv)", c25_tog);
    else begin
      tot_err = tot_err + 1;
      $display("  FAIL XP: clk25_q togglov malo (%0d) - takt logiki pod voprosom", c25_tog);
    end

    // ================= S1: chistaya knopka (obe DUT) =================
    we_falls397 = 0; we_falls398 = 0;
    RST = 1'b1;
    @(posedge clk); #2; t_rst = $time;
    t_ev7 = 0; t_ev8 = 0;
    fork
      begin @(negedge rsti397); t_ev7 = $time; end
      begin @(negedge rsti398); t_ev8 = $time; end
      begin #1000; end
    join
    if (t_ev7 == 0 || (t_ev7 - t_rst) < 390 || (t_ev7 - t_rst) > 445) begin
      s1_err = s1_err + 1;
      $display("  FAIL S1: vzvod RESET_IN397 = %0t ns (ozhidanie 400..440)", t_ev7 ? (t_ev7 - t_rst) : 32'd0);
    end else
      $display("  PASS S1: vzvod RESET_IN cherez %0t ns (397; 398 na toy zhe kromke - EQ stroit)", t_ev7 - t_rst);
    if (t_ev7 !== t_ev8) begin
      s1_err = s1_err + 1; $display("  FAIL S1: kromki vzvoda u oboih RAZNYE (%0t vs %0t)", t_ev7, t_ev8);
    end
    tick(75);           // knopka derzhitsya (3 us)
    RST = 1'b0;
    @(posedge clk); #2; t_rst = $time;
    t_ev7 = 0; t_ev8 = 0;
    fork
      begin @(posedge rsti397); t_ev7 = $time; end
      begin @(posedge rsti398); t_ev8 = $time; end
      begin #1000; end
    join
    if (t_ev7 == 0 || (t_ev7 - t_rst) < 390 || (t_ev7 - t_rst) > 445) begin
      s1_err = s1_err + 1;
      $display("  FAIL S1: snatie RESET_IN397 = %0t ns (ozhidanie 400..440)", t_ev7 ? (t_ev7 - t_rst) : 32'd0);
    end else
      $display("  PASS S1: snatie RESET_IN cherez %0t ns posle otpuskaniya", t_ev7 - t_rst);
    if (t_ev7 !== t_ev8) begin
      s1_err = s1_err + 1; $display("  FAIL S1: kromki snatiya u oboih RAZNYE");
    end
    tick(2);
    chk_clean("S1 posle snatiya");
    cyc(1'b0, 1'b1, 1'b1, 1'b0, 8'h21, 8'h5A, 8'h00);   // zapis' OZU posle knopki
    if (we_falls397 == 1 && we_falls398 == 1 && we_a397 === 8'h21 && we_d397 === 8'h5A)
      $display("  PASS S1: zapis' OZU posle knopki OK u OBEIH (A=%h D=%h na /WE)", we_a397, we_d397);
    else begin
      s1_err = s1_err + 1;
      $display("  FAIL S1: zapis' posle knopki: padenij /WE 397=%0d 398=%0d A=%h D=%h", we_falls397, we_falls398, we_a397, we_d397);
    end
    if (s1_err == 0) $display("  === S1 (chistaya knopka) PASS ===");
    else begin tot_err = tot_err + s1_err; $display("  === S1 FAIL: %0d ===", s1_err); end

    // ================= S2: drebeg otpuskaniya, tihaya shina =================
    resync;
    we_falls397 = 0; we_falls398 = 0;
    RST = 1'b1; tick(50);                       // press 2 us
    RST = 1'b0; tick(2);                        // 80 ns nizko
    RST = 1'b1; #100;  RST = 1'b0; tick(1);     // 100 ns vysoko - NE kacheveno
    tick(60);                                    // 2.4 us nizko - SNATIE
    RST = 1'b1; #150;  RST = 1'b0; tick(1);     // 150 ns - NE vidno
    RST = 1'b1; tick(25); RST = 1'b0; tick(3);  // 1 us vysoko - perezapusk
    RST = 1'b1; #200;  RST = 1'b0; tick(1);     // 200 ns - NE vidno
    tick(60);                                    // final'noe kachevennoe snatie
    if (we_falls397 == 0 && we_falls398 == 0)
      $display("  PASS S2: drebeg na tihoy shine - /WE ne zvenil u OBEIH (%0d/%0d)", we_falls397, we_falls398);
    else begin
      s2_err = s2_err + 1;
      $display("  FAIL S2: /WE zvenel: 397=%0d 398=%0d", we_falls397, we_falls398);
    end
    chk_clean("S2 final");
    if (s2_err == 0) $display("  === S2 (drebeg, tihaya shina) PASS ===");
    else begin tot_err = tot_err + s2_err; $display("  === S2 FAIL: %0d ===", s2_err); end

    // ================= S2h: tot zhe drebeg NA VRACHDEBNOY shine =================
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
    $display("  PASS S2h: vrazhdebnye plavaniya + drebeg - final chistyy u oboih (lozhnye /WE ot sluchaya EQ-strogo: 0 raskhozhdenij = odinakovoe povedenie)");

    // ================= ITÓG =================
    if (n_mis == 0 && tot_err == 0)
      $display("=== ITOG tb_v398_diff: VSE PASS - v3.9.8 BIT-V-BIT v3.9.7 na vseh vyhodah logiki, por_run vklyucheno (%0d vyborok); X1/X2 - zakonomernaya delta duty ===", n_eq);
    else
      $display("=== ITOG tb_v398_diff: %0d raskhozhdenij, %0d scenario-oshibok - EST' FAILY ===", n_mis, tot_err);
    $finish;
  end

endmodule
