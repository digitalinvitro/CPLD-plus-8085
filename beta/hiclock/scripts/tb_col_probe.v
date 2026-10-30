`timescale 1ns/1ps
//=====================================================================
// tb_col_probe.v (clk10-63): PROBNIK predlozheniya kollegi
// «slit zakhvat adresa s perekhodom IDLE->T1H» (zakhvat v ветке
// perekhoda, T1H - chistoe ozhidanie !ALE) protiv базy v3.9.1
// (zakhvat povtornym semplirovaniem v T1H, poslednij sempel validen).
//   dut391 - база v3.9.1;  dutColA - полн. перенос (addr+bus_reg);
//   dutColB - только addr_latch в переход, bus_reg остаётся в T1H.
// MODEL SHINY: adres/dannye pamyati stanovyatsya validnymi POZHE
// pod'ema ALE (po datashitu 8085: t_AD (adres valid) > t_ALE (ALE verkh) -
// pervye semply 25 MGc chitayut ustarevshee soderzhimoe seti).
//   aset - zaderzhka v tikakh 25 MGc ot vkhoda v T1H do vystavleniya
//          novogo adresa (0 = optimistichnoe «adres uzhe validen»);
//   dset - to zhe dlya dannykh chteniya na D-shine.
// Metriki: raskhozhdeniya addr_latch (ierarkhicheski), logi OZU,
// porty (seg/col/dig/snd), A-shina v T2 chteniya.
//=====================================================================
module tb_col_probe;

  reg clk = 1'b0;
  always #20 clk = ~clk;

  reg RST=0, ALE=0, WRn=1, RDn=1, IOM=0, A15=0, SOD=0, RX=1;
  reg RSTOUT=0, INTAn=1, HLDA=0, CLKOUT=0, S0=0, S1=0;
  reg AH8=0,AH9=0,AH10=0,AH11=0,AH12=0,AH13=0,AH14=0;
  reg row0=1, row1=0, row2=1, row3=0, row4=1;

  // razdelnye shiny
  wire [7:0] Ab, Db, Aa, Da, Ab2, Db2;
  reg  [7:0] cpuA = 8'h00;  reg cpuA_en = 0;
  reg  [7:0] memD = 8'h00;  reg memD_en = 0;
  assign (weak0, weak1) Ab  = cpuA_en ? cpuA : 8'hZZ;
  assign (weak0, weak1) Aa  = cpuA_en ? cpuA : 8'hZZ;
  assign (weak0, weak1) Ab2 = cpuA_en ? cpuA : 8'hZZ;
  assign (weak0, weak1) Db  = memD_en ? memD : 8'hZZ;
  assign (weak0, weak1) Da  = memD_en ? memD : 8'hZZ;
  assign (weak0, weak1) Db2 = memD_en ? memD : 8'hZZ;

  wire csbr, oebr, csbn, oebn, webn, cs1b, x1b, rdyb, rstib, sidb, txb, sndb, x2b;
  wire [7:0] segb; wire [3:0] digb, colb;
  wire csar, oear, csan, oean, wean, cs1a, x1a, rdya, rstia, sida, txa, snda, x2a;
  wire [7:0] sega; wire [3:0] diga, cola;
  wire csb2r, oeb2r, csb2n, oeb2n, web2n, cs1b2, x1b2, rdyb2, rstib2, sidb2, txb2, sndb2, x2b2;
  wire [7:0] segb2; wire [3:0] digb2, colb2;

  retro_pcld_top_v391 dut391 (
    .clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(Ab), .D(Db), .CSr_n(csbr), .OEr_n(oebr), .CS_n(csbn), .OE_n(oebn), .WE_n(webn), .CS1(cs1b),
    .X1(x1b), .READY(rdyb), .RESET_IN(rstib), .SID(sidb), .TX(txb), .seg(segb), .dig(digb), .SND(sndb),
    .X2(x2b), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA), .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12), .AH13(AH13), .AH14(AH14), .RX(RX),
    .col0(colb[0]), .col1(colb[1]), .col2(colb[2]), .col3(colb[3]),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

  retro_pcld_top_cola dutColA (
    .clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(Aa), .D(Da), .CSr_n(csar), .OEr_n(oear), .CS_n(csan), .OE_n(oean), .WE_n(wean), .CS1(cs1a),
    .X1(x1a), .READY(rdya), .RESET_IN(rstia), .SID(sida), .TX(txa), .seg(sega), .dig(diga), .SND(snda),
    .X2(x2a), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA), .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12), .AH13(AH13), .AH14(AH14), .RX(RX),
    .col0(cola[0]), .col1(cola[1]), .col2(cola[2]), .col3(cola[3]),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

  retro_pcld_top_colb dutColB (
    .clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(Ab2), .D(Db2), .CSr_n(csb2r), .OEr_n(oeb2r), .CS_n(csb2n), .OE_n(oeb2n), .WE_n(web2n), .CS1(cs1b2),
    .X1(x1b2), .READY(rdyb2), .RESET_IN(rstib2), .SID(sidb2), .TX(txb2), .seg(segb2), .dig(digb2), .SND(sndb2),
    .X2(x2b2), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA), .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12), .AH13(AH13), .AH14(AH14), .RX(RX),
    .col0(colb2[0]), .col1(colb2[1]), .col2(colb2[2]), .col3(colb2[3]),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

  // ---------------- virtualnye OZU ----------------
  reg [15:0] logb [0:8191]; integer nb = 0;
  reg [15:0] loga [0:8191]; integer na = 0;
  reg [15:0] logb2[0:8191]; integer nb2 = 0;
  always @(posedge webn)  begin #1; if (csbn  === 1'b0) begin logb [nb ] = {Ab,  Db };  nb  = nb  + 1; end end
  always @(posedge wean)  begin #1; if (csan  === 1'b0) begin loga [na ] = {Aa,  Da };  na  = na  + 1; end end
  always @(posedge web2n) begin #1; if (csb2n === 1'b0) begin logb2[nb2] = {Ab2, Db2}; nb2 = nb2 + 1; end end

  // ---------------- schetchiki ----------------
  integer bad_alA = 0, bad_alB = 0;      // addr_latch otlichaetsya ot базy
  integer bad_wA  = 0, bad_wB  = 0;      // log OZU otlichaetsya ot базy
  integer bad_ioA = 0, bad_ioB = 0;      // seg/col/dig/snd otlichaetsya
  integer busA    = 0, busB    = 0;      // A-shina razoshlas
  integer cycles  = 0;
  reg [7:0] alb, ala, alb2;

  initial forever begin
    #5;
    if (Ab !== Aa)   busA = busA + 1;
    if (Ab !== Ab2)  busB = busB + 1;
  end

  task tick(input integer n);
    begin repeat (n) @(posedge clk); #1; end
  endtask

  // cikl s modelyu zaderzhki validnosti: aset tika posle vkhoda v T1H
  // adres na A-shine menyaetsya so stale_na na addr; dset - to zhe dlya D.
  task cyc(input iom_i, input a15_i, input do_wr, input do_rd,
           input [7:0] addr, input [7:0] wdata, input [7:0] rdata,
           input integer t_ale, input integer t_str, input integer t_gap,
           input integer aset, input integer dset, input [7:0] stale_a, input [7:0] stale_d);
    integer q;
    begin
      cycles = cycles + 1;
      cpuA_en = 1'b1; IOM = iom_i; A15 = a15_i; ALE = 1'b1;
      if (aset == 0) cpuA = addr; else cpuA = stale_a;
      if (!iom_i && do_rd) begin
        if (dset == 0) memD = rdata; else memD = stale_d;
        memD_en = 1'b1;
      end
      // vystavlyaem novyj adres cherez aset tikov POSLE vkhoda v T1H
      for (q = 0; q < t_ale; q = q + 1) begin
        @(posedge clk); #1;
        if (q + 1 == aset) cpuA = addr;
        if (!iom_i && do_rd && (q + 1 == dset)) memD = rdata;
      end
      ALE = 1'b0;
      if (do_wr) begin cpuA = wdata; WRn = 1'b0; end
      if (do_rd) begin RDn = 1'b0; end
      tick(t_str);
      if (do_wr) WRn = 1'b1;
      if (do_rd) RDn = 1'b1;
      cpuA_en = 1'b0;
      if (do_rd) begin memD_en = 1'b0; memD = 8'h00; end
      tick(t_gap);
      #1;
      // kontrol: addr_latch bazovogo DUT dolzhen raven addr (esli tsikl ne pogloshchen);
      // schitaem raskhozhdeniya variantov ot базy
      alb  = dut391.addr_latch;  ala  = dutColA.addr_latch;  alb2 = dutColB.addr_latch;
      if (ala !== alb) bad_alA = bad_alA + 1;
      if (alb2 !== alb) bad_alB = bad_alB + 1;
      if (nb !== na)  bad_wA = bad_wA + 1;
      if (nb !== nb2) bad_wB = bad_wB + 1;
      if (sega !== segb || diga !== digb || cola !== colb || snda !== sndb) bad_ioA = bad_ioA + 1;
      if (segb2 !== segb || digb2 !== digb || colb2 !== colb || sndb2 !== sndb) bad_ioB = bad_ioB + 1;
    end
  endtask

  integer i, k, ty, t_ale, t_str, t_gap, aset, dset, seed;
  reg [7:0] ad, dt, rdt, sta, std;
  integer wcA = 0, wcB = 0, j, nmin;

  initial begin
    tick(40);   // POR

    // ---------------- FAZA 1: aset=0 (optimist: adres validen do ALE) --
    for (i = 0; i < 8; i = i + 1)
      cyc(1'b0, 1'b1, 1'b1, 1'b0, 8'h40 + i[7:0], 8'h10 + i[7:0], 8'h00, 4, 3, 4, 0, 0, 8'h00, 8'h00);
    $display("FAZA aset=0: tsiklov=8, raskhozhdeny A: %0d, B: %0d (ozhidalos 0/0)",
             bad_alA, bad_alB);

    // ---------------- FAZA 2: aset=2, dset=4 (realistichnyj 8085) ------
    // RAM-zapisi: у базы adres=zakhvachennyj (poslednij sempel), у variantov
    // - PERVYJ sempel = ustarevshee soderzhimoe seti (stale)
    sta = 8'h77; std = 8'h88;   // «predydushhee soderzhimoe shiny»
    for (i = 0; i < 8; i = i + 1) begin
      cyc(1'b0, 1'b1, 1'b1, 1'b0, 8'h50 + i[7:0], 8'hA0 + i[7:0], 8'h00, 4, 3, 4, 2, 4, sta, std);
      sta = 8'h50 + i[7:0]; std = 8'hA0 + i[7:0];
    end
    // chteniya PZU (variant A zakhvatyvaet bus_reg pervym semploom = musor)
    for (i = 0; i < 4; i = i + 1)
      cyc(1'b0, 1'b0, 1'b0, 1'b1, 8'h20 + i[7:0], 8'h00, 8'hC0 + i[7:0], 4, 3, 4, 2, 4, sta, std);
    // IO-zapisi port 00h (varianty pishut seg ot musornogo adresa/data)
    for (i = 0; i < 4; i = i + 1)
      cyc(1'b1, 1'b0, 1'b1, 1'b0, 8'h00, 8'h3C + i[7:0], 8'h00, 4, 3, 4, 2, 4, sta, std);
    $display("FAZA aset=2 posle 16 tsiklov: raskhozhdeny addr_latch A=%0d B=%0d, logi OZU A=%0d B=%0d, porty A=%0d B=%0d, A-shina A=%0d B=%0d",
             bad_alA, bad_alB, bad_wA, bad_wB, bad_ioA, bad_ioB, busA, busB);

    // ---------------- FAZA 3: random s realistichnoj modelyu -----------
    for (k = 0; k < 2; k = k + 1) begin
      seed = 32'hBEEF0000 + k;
      for (i = 0; i < 2000; i = i + 1) begin
        ty = $random(seed) & 7;
        ad = $random(seed); dt = $random(seed); rdt = $random(seed);
        sta = $random(seed); std = $random(seed);
        t_ale = 3 + ($random(seed) & 3);
        t_str = 2 + ($random(seed) & 3);
        t_gap = 2 + ($random(seed) & 3);
        aset  = 1 + ($random(seed) & 3);      // 1..4 tika do validnosti adresa
        dset  = 3 + ($random(seed) & 3);      // 3..6 tikov do dannykh pamyati
        case (ty)
          0, 1, 2: cyc(1'b0, 1'b1, 1'b1, 1'b0, ad, dt, 8'h00, t_ale, t_str, t_gap, aset, dset, sta, std);
          3, 4:    cyc(1'b0, 1'b1, 1'b0, 1'b1, ad, 8'h00, rdt, t_ale, t_str, t_gap, aset, dset, sta, std);
          5:       cyc(1'b1, 1'b0, 1'b1, 1'b0, ad & 8'h03, dt, 8'h00, t_ale, t_str, t_gap, aset, dset, sta, std);
          6:       cyc(1'b0, 1'b0, 1'b0, 1'b1, ad, 8'h00, rdt, t_ale, t_str, t_gap, aset, dset, sta, std);
          default: cyc(1'b0, 1'b1, 1'b1, 1'b0, ad, dt, 8'h00, t_ale, t_str, t_gap, 0, 0, sta, std);
        endcase
      end
    end

    // ---------------- ITogi -------------------------------------------
    // soderzhatelnoe sravnenie logov OZU (pozicionno, do min dliny)
    nmin = (nb < na) ? nb : na;
    for (j = 0; j < nmin; j = j + 1) if (loga[j] !== logb[j]) wcA = wcA + 1;
    nmin = (nb < nb2) ? nb : nb2;
    for (j = 0; j < nmin; j = j + 1) if (logb2[j] !== logb[j]) wcB = wcB + 1;
    $display("=====================================================================");
    $display("PROBNIK predlozheniya kollegi (slitie zakhvata s perekhodom IDLE->T1H)");
    $display("  tsiklov vsego                     : %0d", cycles);
    $display("  zapisej v virtualnuyu OZU: baza=%0d A=%0d B=%0d", nb, na, nb2);
    $display("  VARIANT A (polnyj perenos):");
    $display("    addr_latch raznitsya s bazoj    : %0d", bad_alA);
    $display("    logi OZU: chislo / soderzhanie  : %0d / %0d", bad_wA, wcA);
    $display("    porty (seg/dig/col/snd)         : %0d", bad_ioA);
    $display("    A-shina raskhozhdenij           : %0d", busA);
    $display("  VARIANT B (tolko addr_latch):");
    $display("    addr_latch raznitsya s bazoj    : %0d", bad_alB);
    $display("    logi OZU: chislo / soderzhanie  : %0d / %0d", bad_wB, wcB);
    $display("    porty                           : %0d", bad_ioB);
    $display("    A-shina raskhozhdenij           : %0d", busB);
    if (bad_alA == 0 && bad_alB == 0 && bad_wA == 0 && bad_wB == 0 && busA == 0 && busB == 0 && wcA == 0 && wcB == 0)
      $display("=== PRI DANNYKH MODELI SHINY VARIANTY EKVIVALENTNY BAZE ===");
    else
      $display("=== VARIANTY NE EKVIVALENTNY BAZE: zakhvat PERVOGO sempla lovit ustarevshuyu shinu ===");
    $display("=====================================================================");
    $finish;
  end

  initial begin
    #60_000_000;
    $display("!!! WATCHDOG !!!");
    $finish;
  end

endmodule
