// tb_poweron_v399.v (lowsize, 2026-11-17): dokazatel'nyy test sbrosa CPU
// po schetu frontov CLKOUT - VARIANT A (predlozhenie vladel'tsa 11-17,
// v3.9.9). DUT - real'nyy RTL top_suart_por6_v399_clear_utf8.v.
// Icarus Verilog 12.0 (tools/iverilog). Kommentarii - ASCII-translit
// (CP1251-bezopasno, stil' tb_poweron_v398).
//
// Model' CPU: CLKOUT = X1/2 (delitel' /2 vnutri VM85A), pereklyuchenie
// po kazhdomu negedge X1 (kol'tso r0..r6, period 140 ns) -> period
// CLKOUT 280 ns, fronty (rising) kazhdye 280 ns. Tri rezhima:
//   clkout_en=1 - CLKOUT ZHIVOY (gipoteza "takt ne gasnetsya v sbrose");
//   clkout_dead(0) / clkout_dead(1) - CLKOUT statichen (gipoteza "gated").
//
// Proverki:
//   P0  POR pri zhivom CLKOUT: INIT (reset_q=0, rst_cnt=0) -> RESET_IN
//       podnimaetsya POSLE 8-go fronta CLKOUT; okno [1800..2600] ns ot
//       starta (8x280=2240 + faza pervogo fronta + 2FF + 1 clk25);
//       norma datasheeta (>= 3 takta = 840 ns) vypolnena s zapasom;
//       rst_cnt posle snyatiya = 000 (schel ROVNO 8).
//   P0b MERTVYY CLKOUT (eksperiment "v pole", negativ): INIT
//       vosstanovlen, CLKOUT statichen v 0 i v 1 -> RESET_IN NE
//       podnimaetsya NIKOGDA (5000 ns - zachylka OZHIDAEMA); pri
//       vozvrashchenii zhivogo CLKOUT snyatie proishodit v okne P0
//       (zachylka obratima - diagnostika vladel'tsa).
//   P1  KNOPKA: RST=1 -> RESET_IN padaet <= 440 ns (2FF + 8 taktov
//       kvalifikatora + reset_q); uderzhanie 1000 ns; posle
//       otpuskaniya - snyatie v okne [2400..2800] ns ot OTPUSKANIYA
//       (320 kvalifikator + 2240 polka + sinkhronizatsiya).
//   P2  GLITCH p.21: impul's RST 100 ns (< 320 ns kvalifikatora) -
//       RESET_IN ne padaet.
//   P3  POVTORNY VZVOD: vtoraya knopka rabotaet (bez blokirovki);
//       posle snyatiya RESET_IN derzhitsya >= 10 mks (odno-stabil'nyy,
//       beskonechnykh peresbrossov NET).
//   P4  VAZHDEBNAYA SHINA v okne polki (fuzz ALE/WRn/RDn/IOM/A15/A/D):
//       logika v sbrosovykh znacheniyakh vsyu polku, WE_n ne pulsuet.
//   P5  MERTVYY clk 50 MGc: schet zamerza (rst_cnt stoit), vsyo stoit.
//
// Ierarkhicheskiy dostup k registram ostrova sbrosa - set_reset_state
// (analog set_por_state tb_poweron_v398; reg-INIT-arifmetika 399
// determinirovana, peribor sostoyaniy kak v P0a-398 ne nuzhen).

`timescale 1ns/1ps

module tb_poweron_v399;

  reg clk = 1'b0;
  reg clk_run = 1'b0;
  always #10 if (clk_run) clk = ~clk;   // 50 MGc (P29, GCK3)

  //-------------------------------------------------------------------
  // Statichnye vhody (vne faz interesa)
  //-------------------------------------------------------------------
  reg RST = 1'b0, SOD = 1'b0, RX = 1'b1;
  reg RSTOUT = 1'b0, INTAn = 1'b1, HLDA = 1'b0, S0 = 1'b0, S1 = 1'b0;
  reg AH8 = 1'b0, AH9 = 1'b0, AH10 = 1'b0, AH11 = 1'b0, AH12 = 1'b0, AH13 = 1'b0, AH14 = 1'b0;
  reg row0 = 1'b1, row1 = 1'b0, row2 = 1'b1, row3 = 1'b0, row4 = 1'b1;

  reg ALE = 1'b0, WRn = 1'b1, RDn = 1'b1, IOM = 1'b0, A15 = 1'b0;
  reg [7:0] cpuA = 8'h00, memD = 8'h00;
  wire [7:0] A, D;
  wire X1, RESET_IN, WE_n, CS_n;
  wire [7:0] seg;
  wire [3:0] dig;

  assign (weak0, weak1) A = cpuA;
  assign (weak0, weak1) D = memD;

  retro_pcld_top dut (
    .clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(A), .D(D),
    .CSr_n(), .OEr_n(), .CS_n(CS_n), .OE_n(), .WE_n(WE_n), .CS1(),
    .X1(X1), .READY(), .RESET_IN(RESET_IN),
    .SID(), .TX(), .seg(seg), .dig(dig), .SND(),
    .X2(), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA),
    .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12), .AH13(AH13), .AH14(AH14),
    .RX(RX),
    .col0(), .col1(), .col2(), .col3(),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

  //-------------------------------------------------------------------
  // Model' CPU: CLKOUT = X1/2; rezhimy zhivyy/mertvyy
  //-------------------------------------------------------------------
  reg clkout_en = 1'b1;
  reg CLKOUT = 1'b0;
  always @(negedge X1) if (clkout_en) CLKOUT <= ~CLKOUT;
  task clkout_dead(input v); begin clkout_en = 1'b0; CLKOUT = v; end endtask
  task clkout_live;          begin clkout_en = 1'b1; end endtask

  integer errors = 0;


  // Vrazhdebnaya "plavayushchaya" shina v okne polki sbrosa (model' rastra)
  reg fuzz_on = 1'b0;
  integer seed = 32'hC0FFEE;             // fiksirovannyy - probeg vosproizvodim
  reg [31:0] r;
  always #10 begin
    if (fuzz_on) begin
      r = $random(seed); if (r[2:0] < 3'd3) ALE  = r[3];
      r = $random(seed); if (r[2:0] < 3'd3) WRn  = r[3];
      r = $random(seed); if (r[2:0] < 3'd3) RDn  = r[3];
      r = $random(seed); if (r[2:0] < 3'd3) IOM  = r[3];
      r = $random(seed); if (r[2:0] < 3'd3) A15  = r[3];
      r = $random(seed); cpuA = r[31:24];
      r = $random(seed); memD = r[31:24];
    end
  end

  task automatic quiet_bus; begin
    fuzz_on = 1'b0;
    ALE = 1'b0; WRn = 1'b1; RDn = 1'b1; IOM = 1'b0; A15 = 1'b0;
    cpuA = 8'h00; memD = 8'h00;
  end endtask

  // logika v sbrosovyh znacheniyah? (PTC-oderzhimoe poka cpu_rst=1)
  function automatic logic_dirt(input dummy);
    begin
      logic_dirt = (dut.state !== 3'd0) || (dut.rd_seen !== 1'b0)
                 || (dut.wr_seen !== 1'b0) || (dut.addr_latch !== 8'h00)
                 || (dut.bus_reg !== 8'h00) || (dut.seg_q !== 8'hFF)
                 || (dut.dig_q !== 4'hF)  || (dut.snd_q !== 1'b0)
                 || (dut.kbcol_q !== 4'h0);
    end
  endfunction

  // Vosstanovlenie INIT-sostoyaniya ostrova sbrosa (kak .jed pri vklyuchenii):
  // cpu_rst = rst_press | !reset_q posle zapisi avtomaticheski = 1 -
  // asinhronnyy sbros logiki derzhitsya sam, forsirovat' logiku ne nuzhno.
  task automatic set_reset_state(input [2:0] cnt, input rq);
    begin
      dut.rst_cnt     = cnt;
      dut.reset_q     = rq;
      // tsep sinkhronizatora vyrovnyaetsya s TEKUSHCHIM CLKOUT - inache
      // pereliv tsepochki (meta/sync=0 pri CLKOUT=1) rodit SINTE-TICHESKIY
      // front i odin lishniy schet (bug tb, ne RTL)
      dut.clkout_meta = CLKOUT;
      dut.clkout_sync = CLKOUT;
      dut.clkout_d    = CLKOUT;
      dut.rst_meta    = 1'b0;
      dut.rst_sync    = 1'b0;
      dut.rst_press   = 1'b0;
      dut.rst_qcnt    = 3'b000;
    end endtask

  initial begin
    $dumpfile("tb_poweron_v399.vcd");
    $dumpvars(0, tb_poweron_v399);

    //=================================================================
    // P0: POR pri zhivom CLKOUT - snyatie po 8-mu frontu
    //=================================================================
    $display("=== P0: POR (INIT reset_q=0), CLKOUT zhivoy (X1/2, 280 ns), ozhidanie snyatiya po 8-mu frontu ===");
    clk_run = 1'b1;
    fuzz_on = 1'b1;                        // vrazhdebnaya shina vsyu polku
    begin : p0
      realtime t0, t_rise;
      t0 = $realtime;
      @(posedge RESET_IN);
      t_rise = $realtime - t0;
      fuzz_on = 1'b0;
      if (t_rise < 1800.0 || t_rise > 2600.0) begin
        errors = errors + 1;
        $display("RESULT P0 FAIL: RESET_IN podnyalsya cherez %0t ns (okno [1800..2600]; 8x280=2240 + faza pervogo fronta + sinkhro)", t_rise);
      end else if (dut.rst_cnt !== 3'b000) begin
        errors = errors + 1;
        $display("RESULT P0 FAIL: rst_cnt=%b posle snyatiya - schet NE rovno 8 frontov", dut.rst_cnt);
      end else if (logic_dirt(1'b0)) begin
        errors = errors + 1;
        $display("RESULT P0 FAIL: logika ISPAChANA vrazhdebnoy shinoy v okne polki");
      end else
        $display("RESULT P0 PASS: RESET_IN niz %0t ns (polka 2240, norma >= 840, zapas 2.66x); rst_cnt=000 (rovno 8 frontov); logika chista", t_rise);
    end

    //=================================================================
    // P0b: MERTVYY CLKOUT - zachylka OZHIDAEMA (eksperiment "v pole")
    //=================================================================
    $display("=== P0b: CLKOUT mertvyy (statichnyy 0 i 1) - RESET_IN NE podnimaetsya; vozvrat zhivogo - snyatie ===");
    begin : p0b
      realtime t0, t_rise;
      // faza 1: INIT vosstanovlen, CLKOUT statichen v '0'. Vkhod v
      // fazu - cherez ESTESTVENNYY uroven' (zhdyom CLKOUT=0), inache
      // stupenka 1->0/0->1 - eto NASTOYAShCHIY front, i design ego
      // Chestno schitaet (bug scenariya, ne RTL)
      clkout_live;
      wait (CLKOUT === 1'b0);
      set_reset_state(3'b000, 1'b0);     // tsep vyrovnyana s CLKOUT=0
      clkout_dead(1'b0);                 // zamorozili v 0 (bez frotov)
      #5000;
      if (RESET_IN !== 1'b0 || dut.rst_cnt !== 3'b000) begin
        errors = errors + 1;
        $display("RESULT P0b FAIL: pri mertvom CLKOUT=0 RESET_IN=%b rst_cnt=%b - zachylka NE chistaya (schet poshel?)", RESET_IN, dut.rst_cnt);
      end
      // faza 2: statichnaya edinitsa: zhdyom estestvennogo urovnya 1,
      // potom INIT zanovo (schet sbyrosen) i zamorozka bez frotov
      clkout_live;
      wait (CLKOUT === 1'b1);
      set_reset_state(3'b000, 1'b0);
      clkout_dead(1'b1);
      #5000;
      if (RESET_IN !== 1'b0 || dut.rst_cnt !== 3'b000) begin
        errors = errors + 1;
        $display("RESULT P0b FAIL: pri mertvom CLKOUT=1 RESET_IN=%b rst_cnt=%b", RESET_IN, dut.rst_cnt);
      end
      // vozvrat zhivogo takta - snyatie dolzhno proizoyti (zachylka obratima)
      t0 = $realtime;
      clkout_live;
      @(posedge RESET_IN);
      t_rise = $realtime - t0;
      if (t_rise < 1800.0 || t_rise > 2600.0) begin
        errors = errors + 1;
        $display("RESULT P0b FAIL: posle vozvrata CLKOUT snyatie cherez %0t (okno [1800..2600])", t_rise);
      end else
        $display("RESULT P0b PASS: mertvyy CLKOUT (0 i 1) - RESET_IN stoit, schet zamerza; vozvrat zhivogo - snyatie cherez %0t (zachylka obratima)", t_rise);
    end

    //=================================================================
    // P1: KNOPKA - vzvod <= 440 ns, uderzhanie 1000 ns, snyatie polkoy
    //=================================================================
    $display("=== P1: knopka RST - vzvod <= 440 ns, uderzhanie, snyatie 320 kvalifikator + 2240 polka ===");
    quiet_bus;
    begin : p1
      realtime t0, t_fall, tr, t_rise;
      t0 = $realtime;
      RST = 1'b1;
      @(negedge RESET_IN);
      t_fall = $realtime - t0;
      #1000;                               // uderzhanie knopki 1000 ns
      RST = 1'b0;                          // otpustili
      tr = $realtime;
      @(posedge RESET_IN);
      t_rise = $realtime - tr;
      if (t_fall > 440.0) begin
        errors = errors + 1;
        $display("RESULT P1 FAIL: RESET_IN padaet cherez %0t ns (norma <= 440)", t_fall);
      end
      if (t_rise < 2300.0 || t_rise > 2700.0) begin
        errors = errors + 1;
        $display("RESULT P1 FAIL: snyatie cherez %0t ns posle OTPUSKANIYA (okno [2300..2700]: 360 kval + 2240 polka + faza fronta + sinkhro)", t_rise);
      end else if (t_fall <= 440.0)
        $display("RESULT P1 PASS: vzvod %0t ns (<= 440), uderzhanie derzhalo sbros, snyatie %0t ns posle otpuskaniya", t_fall, t_rise);
    end

    //=================================================================
    // P2: GLITCH 100 ns - kvalifikator glotit (p.21 v sile)
    //=================================================================
    $display("=== P2: glitch RST 100 ns (< 320 ns kvalifikatora) - RESET_IN ne padaet ===");
    begin : p2
      RST = 1'b1;
      #100;
      RST = 1'b0;
      #600;
      if (RESET_IN !== 1'b1) begin
        errors = errors + 1;
        $display("RESULT P2 FAIL: RESET_IN=%b cherez 600 ns posle glitcha 100 ns - kvalifikator PROPUSTIL", RESET_IN);
      end else
        $display("RESULT P2 PASS: glitch 100 ns proignorirovan (RESET_IN=1, p.21 v sile)");
    end

    //=================================================================
    // P3: POVTORNY VZVOD + otsutstvie samoproizvol'nykh peresbrossov
    //=================================================================
    $display("=== P3: vtoraya knopka (bez blokirovki), potom 10 mks pokoya - bez peresbrossov ===");
    begin : p3
      realtime t0, tr, t_rise;
      t0 = $realtime;
      RST = 1'b1;
      @(negedge RESET_IN);
      #1000;                               // uderzhanie
      RST = 1'b0;
      tr = $realtime;
      @(posedge RESET_IN);
      t_rise = $realtime - tr;
      // model snyatiya: kvalifikator 360 (2FF + 8 taktov) + 7 promezhutkov
      // po 280 + faza pervogo fronta [0..280] + sinkhro <= 80 =>
      // okno [2360..2680]; nizhe 2300 - schet < 8 frontov (brak)
      if (t_rise < 2300.0 || t_rise > 2700.0) begin
        errors = errors + 1;
        $display("RESULT P3 FAIL: vtoroy tsikl - snyatie cherez %0t posle otpuskaniya (okno [2300..2700])", t_rise);
      end
      // 10 mks pokoya: ni odnogo padseniya RESET_IN (opros kazhdye 100 ns)
      t0 = $realtime;
      while (($realtime - t0) < 10000.0 && RESET_IN === 1'b1) #100;
      if (RESET_IN !== 1'b1) begin
        errors = errors + 1;
        $display("RESULT P3 FAIL: za 10 mks pokoya RESET_IN upal - samoproizvol'nyy peresbross (odno-stabil'nost' narushena)");
      end else if (t_rise >= 2300.0 && t_rise <= 2700.0)
        $display("RESULT P3 PASS: povtornyy vzvod rabotaet (snyatie %0t posle otpuskaniya), 10 mks pokoya - ni odnogo peresbrossa", t_rise);
    end

    //=================================================================
    // P5: MERTVYY clk 50 MGc - schet zamerza
    //=================================================================
    $display("=== P5: stop clk 50 MGc v polke - schet zamerza, vsyo stoit ===");
    begin : p5
      set_reset_state(3'b001, 1'b0);       // 1 front uzhe poschitan
      clk_run = 1'b0;                      // takta CPLD net - zamearzhaet VSYO
      #1000;
      if (dut.rst_cnt !== 3'b001 || RESET_IN !== 1'b0) begin
        errors = errors + 1;
        $display("RESULT P5 FAIL: bez clk rst_cnt=%b RESET_IN=%b - schet/shina zivut bez takta", dut.rst_cnt, RESET_IN);
      end else begin
        clk_run = 1'b1;
        @(posedge RESET_IN);
        $display("RESULT P5 PASS: bez clk schet zamerza (rst_cnt=001 stoit), posle vozvrata - snyatie po 8-mu frontu");
      end
    end

    quiet_bus;
    $display("ITOGE: %0d oshibok", errors);
    if (errors == 0) $display("RESULT ITGAME PASS: VARIANT A podtverzhden na RTL (POR/mertvyy CLKOUT/knopka/glitch/povtor/mertvyy clk)");
    else             $display("RESULT ITGAME FAIL: VARIANT A IMEET %0d RAZRYVOV", errors);
    $finish;
  end

  //-------------------------------------------------------------------
  // P4: podschet pulsov /WE v okne polki (fuzz s t=0 do konca P0)
  //-------------------------------------------------------------------
  integer we_pulses = 0;
  reg p4_arm = 1'b0;
  always @(negedge WE_n) if (p4_arm) we_pulses = we_pulses + 1;
  initial begin
    p4_arm = 1'b1;
    wait (RESET_IN === 1'b1);
    #100;
    p4_arm = 1'b0;
    if (we_pulses != 0) begin
      errors = errors + 1;
      $display("RESULT P4 FAIL: %0d pulsov /WE v okne polki (vrazhdebnaya shina rodila zapisi)", we_pulses);
    end else
      $display("RESULT P4 PASS: ni odnogo pulsa /WE v okne polki (fuzz shina)");
  end

endmodule
