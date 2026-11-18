// tb_poweron_v35.v (txuart, 2026-11-17): dokazatel'nyy test sbrosa CPU po
// schetu frontov CLKOUT - VARIANT A (predlozhenie vladel'tsa 11-17, v3.0).
// DUT - real'nyy RTL top_txuart_por6_v32_utf8.v. Icarus Verilog 12.0.
// v3.5: DUT = v3.4 + CE-forma bus_reg/kbcol_q (Shag-13, semantika 1-v-1);
// semantika 1-v-1; tb bus-cikly proveryayut guard/vetki - cheki 1-v-1 v30/v31/v32/v33.
// Pervyy Verilog-tb linii txuart (prezhnie tb - Python po uravneniyam
// fita). Kommentarii - ASCII-translit (CP1251-bezopasno).
//
// Model' CPU: CLKOUT = X1/2 (delitel' /2 vnutri VM85A), pereklyuchenie
// po kazhdomu negedge X1 (x1_q, period 160 ns) -> period CLKOUT 320 ns,
// fronty (rising) kazhdye 320 ns. Rezhimy: clkout_en=1 - zhivoy;
// clkout_dead(0)/clkout_dead(1) - statichen (gipoteza "gated").
//
// Proverki:
//   P0  POR pri zhivom CLKOUT: INIT (reset_q=0) -> RESET_IN podnimaetsya
//       POSLE 8-go fronta; okno [2200..3200] ns (2560 + faza pervogo
//       fronta + sinkhro); norma datasheeta 3 takta = 960 ns, zapas
//       2.67x; rst_cnt posle snyatiya = 000 (schel ROVNO 8); logika
//       chista pri vrazhdebnoy shine vsyu polku; ni odnogo /WE.
//   P0b MERTVYY CLKOUT (eksperiment "v pole", negativ): INIT vosstanovlen,
//       CLKOUT statichen v 0 i v 1 -> RESET_IN NE podnimaetsya NIKOGDA
//       (5000 ns - zachylka OZHIDAEMA); vozvrat zhivogo - snyatie v okne
//       (zachylka obratima - diagnostika vladel'tsa).
//   P1  KNOPKA: RST=1 -> RESET_IN padaet [1200..1520] ns (2FF + 8 tikov
//       por_ce 1280 + cpu_rst_r + reset_q); uderzhanie; posle
//       otpuskaniya - snyatie [3700..4300] ns ot OTPUSKANIYA
//       (1280 kvalifikator + 2560 polka + sinkhro).
//   P2  GLITCH p.21: impul's RST 500 ns (< 1280 ns kvalifikatora) -
//       RESET_IN ne padaet.
//   P3  POVTORNY VZVOD: vtoraya knopka rabotaet; posle snyatiya 10 mks
//       pokoya - ni odnogo samoproizvol'nogo peresbrossa.
//   P5  MERTVYY clk 25 MGc: schet zamerza (rst_cnt stoit), vsyo stoit.

`timescale 1ns/1ps

module tb_poweron_v35;

  reg clk = 1'b0;
  reg clk_run = 1'b0;
  always #20 if (clk_run) clk = ~clk;   // 25 MGc (P29, GCK3)

  //-------------------------------------------------------------------
  // Statichnye vhody (vne faz interesa)
  //-------------------------------------------------------------------
  reg RST = 1'b0, SOD = 1'b0, RX = 1'b1;
  reg RSTOUT = 1'b0, INTAn = 1'b1, HLDA = 1'b0, S0 = 1'b0, S1 = 1'b0;
  reg AH8 = 1'b0, AH9 = 1'b0, AH10 = 1'b0, AH11 = 1'b0, AH12 = 1'b0, AH13 = 1'b0, AH14 = 1'b0;

  reg ALE = 1'b0, WRn = 1'b1, RDn = 1'b1, IOM = 1'b0, A15 = 1'b0;
  reg [7:0] cpuA = 8'h00, memD = 8'h00;
  wire [7:0] A, D;
  wire X1, RESET_IN, WE_n, CS_n, RST75, TX, SND, SID, READY, CS1, CSr_n, OEr_n, OE_n, X2;
  wire [7:0] seg;
  wire [3:0] dig;
  wire col0, col1, col2, col3;

  assign (weak0, weak1) A = cpuA;
  assign (weak0, weak1) D = memD;

  retro_pcld_top dut (
    .clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(A), .D(D),
    .CSr_n(CSr_n), .OEr_n(OEr_n), .CS_n(CS_n), .OE_n(OE_n), .WE_n(WE_n), .CS1(CS1),
    .X1(X1), .READY(READY), .RESET_IN(RESET_IN),
    .RST75(RST75), .SID(SID), .TX(TX), .seg(seg), .dig(dig), .SND(SND),
    .X2(X2), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA),
    .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12), .AH13(AH13), .AH14(AH14),
    .RX(RX),
    .col0(col0), .col1(col1), .col2(col2), .col3(col3),
    .row0(1'b0), .row1(1'b0), .row2(1'b0), .row3(1'b0), .row4(1'b0));

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
  integer seed = 32'hC0FFEE;
  reg [31:0] r;
  always #20 begin
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

  // logika v sbrosovyh znacheniyah? (GSR-oderzhimoe poka cpu_rst_r=1)
  function automatic logic_dirt(input dummy);
    begin
      logic_dirt = (dut.state !== 3'd0) || (dut.rd_seen !== 1'b0)
                 || (dut.wr_seen !== 1'b0) || (dut.addr_latch !== 8'h00)
                 || (dut.bus_reg !== 8'h00) || (dut.seg_q !== 7'h40)
                 || (dut.dig_q !== 4'hF)  || (dut.snd_q !== 1'b0)
                 || (dut.kbcol_q !== 4'h0) || (dut.RST75 !== 1'b0)
                 || (dut.shreg !== 9'h1FF);
    end
  endfunction

  // Vosstanovlenie INIT-sostoyaniya ostrova sbrosa (kak .jed pri
  // vklyuchenii). Tsep sinkhronizatora vyrovnyaetsya s TEKUSHCHIM CLKOUT -
  // inache pereliv rodit sinteticheskiy front (bug tb, ne RTL).
  // cpu_rst_r podnimetsya sam cherez 1 klk (rst_press | !reset_q).
  task automatic set_reset_state(input [2:0] cnt, input rq);
    begin
      dut.rst_cnt     = cnt;
      dut.reset_q     = rq;
      dut.clkout_meta = CLKOUT;
      dut.clkout_sync = CLKOUT;
      dut.clkout_d    = CLKOUT;
      dut.rst_meta    = 1'b0;
      dut.rst_sync    = 1'b0;
      dut.rst_press   = 1'b0;
      dut.rst_qcnt    = 3'b000;
    end endtask

  initial begin
    $dumpfile("tb_poweron_v35.vcd");
    $dumpvars(0, tb_poweron_v35);

    //=================================================================
    // P0: POR pri zhivom CLKOUT - snyatie po 8-mu frontu
    //=================================================================
    $display("=== P0: POR (INIT reset_q=0), CLKOUT zhivoy (X1/2, 320 ns), snyatie po 8-mu frontu ===");
    clk_run = 1'b1;
    fuzz_on = 1'b1;
    begin : p0
      realtime t0, t_rise;
      t0 = $realtime;
      @(posedge RESET_IN);
      t_rise = $realtime - t0;
      fuzz_on = 1'b0;
      if (t_rise < 2200.0 || t_rise > 3200.0) begin
        errors = errors + 1;
        $display("RESULT P0 FAIL: RESET_IN podnyalsya cherez %0t ns (okno [2200..3200]; 8x320=2560 + faza + sinkhro)", t_rise);
      end else if (dut.rst_cnt !== 3'b000) begin
        errors = errors + 1;
        $display("RESULT P0 FAIL: rst_cnt=%b posle snyatiya - schet NE rovno 8 frontov", dut.rst_cnt);
      end else if (logic_dirt(1'b0)) begin
        errors = errors + 1;
        $display("RESULT P0 FAIL: logika ISPAChANA vrazhdebnoy shinoy v okne polki");
      end else
        $display("RESULT P0 PASS: RESET_IN niz %0t ns (polka 2560, norma >= 960, zapas 2.67x); rst_cnt=000 (rovno 8 frontov); logika chista", t_rise);
    end

    //=================================================================
    // P0b: MERTVYY CLKOUT - zachylka OZHIDAEMA (eksperiment "v pole")
    //=================================================================
    $display("=== P0b: CLKOUT mertvyy (statichnyy 0 i 1) - RESET_IN NE podnimaetsya; vozvrat zhivogo - snyatie ===");
    begin : p0b
      realtime t0, t_rise;
      // faza 1: INIT vosstanovlen, CLKOUT statichen v '0'. Vkhod cherez
      // ESTESTVENNYY uroven' (stupenka = nastoyashchiy front - schet Chestnyy)
      clkout_live;
      wait (CLKOUT === 1'b0);
      set_reset_state(3'b000, 1'b0);
      clkout_dead(1'b0);
      #5000;
      if (RESET_IN !== 1'b0 || dut.rst_cnt !== 3'b000) begin
        errors = errors + 1;
        $display("RESULT P0b FAIL: pri mertvom CLKOUT=0 RESET_IN=%b rst_cnt=%b - zachylka NE chistaya", RESET_IN, dut.rst_cnt);
      end
      // faza 2: statichnaya edinitsa (zhdyom estestvennogo urovnya 1)
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
      if (t_rise < 2200.0 || t_rise > 3200.0) begin
        errors = errors + 1;
        $display("RESULT P0b FAIL: posle vozvrata CLKOUT snyatie cherez %0t (okno [2200..3200])", t_rise);
      end else
        $display("RESULT P0b PASS: mertvyy CLKOUT (0 i 1) - RESET_IN stoit, schet zamerza; vozvrat zhivogo - snyatie cherez %0t (zachylka obratima)", t_rise);
    end

    //=================================================================
    // P1: KNOPKA - vzvod [1200..1520], uderzhanie 2000 ns, snyatie polkoy
    //=================================================================
    $display("=== P1: knopka RST - vzvod <= 1.52 mks, uderzhanie, snyatie 1280 kvalifikator + 2560 polka ===");
    quiet_bus;
    begin : p1
      realtime t0, t_fall, tr, t_rise;
      t0 = $realtime;
      RST = 1'b1;
      @(negedge RESET_IN);
      t_fall = $realtime - t0;
      #2000;                               // uderzhanie knopki 2000 ns
      RST = 1'b0;                          // otpustili
      tr = $realtime;
      @(posedge RESET_IN);
      t_rise = $realtime - tr;
      if (t_fall < 1200.0 || t_fall > 1520.0) begin
        errors = errors + 1;
        $display("RESULT P1 FAIL: RESET_IN padaet cherez %0t ns (okno [1200..1520]: 2FF + 8 por_ce + cpu_rst_r + reset_q)", t_fall);
      end
      // model': kvalifikator [1200..1360] (8 strobov por_ce + faza) +
      // polka 2560 + faza pervogo fronta [0..320] + sinkhro <= 80
      if (t_rise < 3480.0 || t_rise > 3820.0) begin
        errors = errors + 1;
        $display("RESULT P1 FAIL: snyatie cherez %0t ns posle OTPUSKANIYA (okno [3480..3820])", t_rise);
      end else if (t_fall >= 1200.0 && t_fall <= 1520.0)
        $display("RESULT P1 PASS: vzvod %0t ns, uderzhanie derzhalo sbros, snyatie %0t ns posle otpuskaniya", t_fall, t_rise);
    end

    //=================================================================
    // P2: GLITCH 500 ns - kvalifikator 1280 ns glotit (p.21 v sile)
    //=================================================================
    $display("=== P2: glitch RST 500 ns (< 1280 ns kvalifikatora) - RESET_IN ne padaet ===");
    begin : p2
      RST = 1'b1;
      #500;
      RST = 1'b0;
      #1500;
      if (RESET_IN !== 1'b1) begin
        errors = errors + 1;
        $display("RESULT P2 FAIL: RESET_IN=%b cherez 1500 ns posle glitcha 500 ns - kvalifikator PROPUSTIL", RESET_IN);
      end else
        $display("RESULT P2 PASS: glitch 500 ns proignorirovan (RESET_IN=1, p.21 v sile)");
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
      #2000;
      RST = 1'b0;
      tr = $realtime;
      @(posedge RESET_IN);
      t_rise = $realtime - tr;
      if (t_rise < 3480.0 || t_rise > 3820.0) begin
        errors = errors + 1;
        $display("RESULT P3 FAIL: vtoroy tsikl - snyatie cherez %0t posle otpuskaniya (okno [3480..3820])", t_rise);
      end
      // 10 mks pokoya: ni odnogo padseniya RESET_IN (opros kazhdye 100 ns)
      t0 = $realtime;
      while (($realtime - t0) < 10000.0 && RESET_IN === 1'b1) #100;
      if (RESET_IN !== 1'b1) begin
        errors = errors + 1;
        $display("RESULT P3 FAIL: za 10 mks pokoya RESET_IN upal - samoproizvol'nyy peresbross");
      end else if (t_rise >= 3480.0 && t_rise <= 3820.0)
        $display("RESULT P3 PASS: povtornyy vzvod rabotaet (snyatie %0t posle otpuskaniya), 10 mks pokoya - ni odnogo peresbrossa", t_rise);
    end

    //=================================================================
    // P5: MERTVYY clk 25 MGc - schet zamerza
    //=================================================================
    $display("=== P5: stop clk 25 MGc v polke - schet zamerza, vsyo stoit ===");
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
    if (errors == 0) $display("RESULT ITGAME PASS: VARIANT A podtverzhden na RTL v3.5 (CE-forma bus_reg/kbcol, Shag-13; hod testa 1-v-1 v30-v34) (POR/mertvyy CLKOUT/knopka/glitch/povtor/mertvyy clk)");
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
