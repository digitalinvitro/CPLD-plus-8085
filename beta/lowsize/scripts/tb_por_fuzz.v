`timescale 1ns/1ps
//=====================================================================
// tb_por_fuzz.v (lowsize, 2026-11-05): fuzz-test OKNA POR s "plavajushhej"
// shinoj CPU - DOKAZATEL'NYJ TEST defekta starta v3.9.3/v3.9.4 (zhaloba
// vladel'ca 11-5: "ne stabil'no zapuskaetsja po pitaniju, 3.9.2 stabilen").
//
// SUShNOST' DELTY: v v3.9.2 blok logiki derzhalsja cpu_rst = RST|por_run
// KAZHDYJ TAKT vsemu POR - FSM prikovana k IDLE, flagi/registry v nuljah,
// ljuboj musor s plavajushhej shiny vyrivaetsja kazhdym frontom. V
// v3.9.3/v3.9.4 (mera GSR, p.18) uslovie sbrosa stalo RST (tol'ko
// knopka) - FSM ZHIVET v okne POR, a shina CPU v sbroske FLOATED
// (VM85A 3-stiruet upravlenija/adres/dannye, linii drejfujut VMESTE
// s rastrom VCC) - FSM slyshit plavajushhie ALE/RDn/WRn/IOM/A15,
// brodit po T1H/T2, pachkat rd_seen/wr_seen/addr_latch/bus_reg/seg_q/
// dig_q/kbcol_q/snd_q i vstrechaet CPU na vyhode iz sbrosa GRYAZNOJ.
//
// MODEL': kazhdaya "plavajushhaja" linija - sluchajnye perekljuchenija
// (3/8 na shag 10 ns; porogi linij shumnjat po-raznomu na kazhdoj
// plate - po-seedovaja "lotereja starta"; raspredelenie = tochka
// zrenija vzroslogo fuzzinga, ne tochnaja replika plata).
//
// ZAMERY: (a) v moment snjatija por_run KAZHDOGO dut - DIRTY = hot'
// odin floper GSR-bloka ne v sbrosnom znachenii (X tozhe grjaz');
// v v3.9.2 struktura GARANTIRUET chistotu (prikovana do poslednego
// takta POR), v v3.9.4 - net; (b) na "start CPU" (+200 ns posle
// pozdnego snjatija); (v) schetchiki "vrazhdebnyh" drajvov v okne
// POR: rd_drive (CPLD vetvit A-piny = kontention s '573) i WE_n=0
// (struktura dolzhna byt' nevozmozhna - gate !por_run).
//
// DUT: v3.9.2 (etalon stabil'nogo starta, PROSHIT) vs v3.9.4 (defekt;
// por-cepi sovpadajut s v3.9.3, poetomu vyyavlennoeklass kasaetsja
// OBEIH defectnyh versij). Imena moduliej pereimenovany sed-om v
// run_skripte (retro_pcld_top_v392 / _v394).
// Zapusk: scripts/run_tb_por_fuzz.sh [N_seedov]  (itog - agregat po
// vsem seedam; stroki RESULT razbiraet awk).
//=====================================================================
module tb_por_fuzz;

  //-------------------------------------------------------------------
  // Takt 25 MGc
  //-------------------------------------------------------------------
  reg clk = 1'b0;
  always #20 clk = ~clk;                    // period 40 ns

  //-------------------------------------------------------------------
  // Statichnye vhody (ne v fazy interesujushhej nas)
  //-------------------------------------------------------------------
  reg RST = 1'b0, SOD = 1'b0, RX = 1'b1;
  reg RSTOUT = 1'b0, INTAn = 1'b1, HLDA = 1'b0, CLKOUT = 1'b0, S0 = 1'b0, S1 = 1'b0;
  reg AH8 = 1'b0, AH9 = 1'b0, AH10 = 1'b0, AH11 = 1'b0, AH12 = 1'b0, AH13 = 1'b0, AH14 = 1'b0;
  reg row0 = 1'b1, row1 = 1'b0, row2 = 1'b1, row3 = 1'b0, row4 = 1'b1;

  //-------------------------------------------------------------------
  // Fuzzuemoe okruzhenie: vse, chto CPU v sbroske derzhit v 3-st
  //-------------------------------------------------------------------
  reg ALE = 1'b0, WRn = 1'b1, RDn = 1'b1, IOM = 1'b0, A15 = 1'b0;
  reg [7:0] cpuA = 8'h00;   // A-seti ('573/pamjat' drejfujut vmeste s pitaniem)
  reg [7:0] memD = 8'h00;   // D-seti

  // razdelnye shiny dutov; slabyj drajv "vneshnego mira" ('573/pamjat')
  wire [7:0] A392, A394, D392, D394;
  assign (weak0, weak1) A392 = cpuA;
  assign (weak0, weak1) A394 = cpuA;
  assign (weak0, weak1) D392 = memD;
  assign (weak0, weak1) D394 = memD;

  integer seed = 1;
  reg fuzz_on = 1'b1;
  reg [31:0] r;

  // sluchajnye perekljuchenija kazhdye 10 ns, veroyatnost' 3/8 na liniju;
  // edinyj potok $random(seed) - determinizm po semeni
  always #10 begin
    if (fuzz_on) begin
      r = $random(seed); if (r[2:0] < 3'd3) ALE = r[3];
      r = $random(seed); if (r[2:0] < 3'd3) WRn = r[3];
      r = $random(seed); if (r[2:0] < 3'd3) RDn = r[3];
      r = $random(seed); if (r[2:0] < 3'd3) IOM = r[3];
      r = $random(seed); if (r[2:0] < 3'd3) A15 = r[3];
      r = $random(seed); if (r[2:0] < 3'd3) cpuA = r[31:24];
      r = $random(seed); if (r[2:0] < 3'd3) memD = r[31:24];
    end
  end

  //-------------------------------------------------------------------
  // DUT (imena zavisjat ot sed-renaminga v run_skripte)
  //-------------------------------------------------------------------
  wire cs392r, oe392r, cs392n, oe392n, we392n, cs1_392, x1_392, rdy392, rsti392, sid392, tx392, snd392, x2_392;
  wire [7:0] seg392;  wire [3:0] dig392;  wire [3:0] col392;
  wire cs394r, oe394r, cs394n, oe394n, we394n, cs1_394, x1_394, rdy394, rsti394, sid394, tx394, snd394, x2_394;
  wire [7:0] seg394; wire [3:0] dig394; wire [3:0] col394;

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
  // DIRTY-funkcii: GSR-blok logiki ne v sbrosnyh znachenijah?
  // (X zaschityvaetsja kak grjaz' - !== po vsem poljam)
  // strukturnye garantii: v v3.9.2 v moment snjatija por_run vse
  // polja RAVNY sbrosnym (prikovka cpu_rst do poslednego takta POR);
  // v v3.9.4 garantii NET.
  //-------------------------------------------------------------------
  function dirty392; input dummy;
    dirty392 = (dut392.state      !== 3'd0)  || (dut392.rd_seen    !== 1'b0)
             || (dut392.wr_seen   !== 1'b0)  || (dut392.addr_latch !== 8'h00)
             || (dut392.bus_reg   !== 8'h00) || (dut392.seg_q      !== 8'hFF)
             || (dut392.dig_q     !== 4'hF)  || (dut392.snd_q      !== 1'b0)
             || (dut392.kbcol_q   !== 4'h0);
  endfunction
  function dirty394; input dummy;
    dirty394 = (dut394.state      !== 3'd0)  || (dut394.rd_seen    !== 1'b0)
             || (dut394.wr_seen   !== 1'b0)  || (dut394.addr_latch !== 8'h00)
             || (dut394.bus_reg   !== 8'h00) || (dut394.seg_q      !== 8'hFF)
             || (dut394.dig_q     !== 4'hF)  || (dut394.snd_q      !== 1'b0)
             || (dut394.kbcol_q   !== 4'h0);
  endfunction

  //-------------------------------------------------------------------
  // Zamery
  //-------------------------------------------------------------------
  time    t_fall392 = 0, t_fall394 = 0;
  integer d_fall392 = 0, d_fall394 = 0;
  integer d_stop392 = 0, d_stop394 = 0;
  integer rdrive392 = 0, rdrive394 = 0;   // rd_drive=1 v okne POR (kontention A)
  integer weviol392 = 0, weviol394 = 0;   // WE_n=0 v okne POR (dolzhno byt' 0)

  always @(negedge dut392.por_run) begin
    t_fall392 = $time;
    d_fall392 = dirty392(1'b0);
  end
  always @(negedge dut394.por_run) begin
    t_fall394 = $time;
    d_fall394 = dirty394(1'b0);
  end
  always @(posedge clk) begin
    if (dut392.por_run === 1'b1 && dut392.rd_drive) rdrive392 = rdrive392 + 1;
    if (dut394.por_run === 1'b1 && dut394.rd_drive) rdrive394 = rdrive394 + 1;
    if (dut392.por_run === 1'b1 && dut392.WE_n === 1'b0) weviol392 = weviol392 + 1;
    if (dut394.por_run === 1'b1 && dut394.WE_n === 1'b0) weviol394 = weviol394 + 1;
  end

  //-------------------------------------------------------------------
  // Scenarij odnogo seeda: fuzz vsju POR-oknu + hvost 200 ns, zamer
  // "start CPU", itog
  //-------------------------------------------------------------------
  integer seed0;
  initial begin
    if (!$value$plusargs("SEED=%d", seed0)) seed0 = 1;
    seed = seed0;
    #1;
    if (dut392.por_run !== 1'b1 || dut394.por_run !== 1'b1) begin
      $display("FATAL: por_run ne INIT=1 na t=0"); $finish;
    end
    wait (dut394.por_run === 1'b0);   // v3.9.4 snimaetsja ranshe (M1, ~1020 ns)
    wait (dut392.por_run === 1'b0);   // v3.9.2 pozdzhe (8 sdvigov, ~1140 ns)
    #200;                             // hvost: shina eshcho plavajet, CPU gotovitsya
    fuzz_on = 1'b0;
    d_stop392 = dirty392(1'b0);       // sostojanie na "start CPU"
    d_stop394 = dirty394(1'b0);
    $display("RESULT seed=%0d t_fall392=%0t t_fall394=%0t d_fall392=%0d d_fall394=%0d d_stop392=%0d d_stop394=%0d rdrive392=%0d rdrive394=%0d we392=%0d we394=%0d",
             seed0, t_fall392, t_fall394, d_fall392, d_fall394, d_stop392, d_stop394,
             rdrive392, rdrive394, weviol392, weviol394);
    $finish;
  end

endmodule
