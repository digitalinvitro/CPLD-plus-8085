`timescale 1ns/1ps
//=====================================================================
// tb_poweron_v399h.v (hiclock, 2026-11-07): dokazatel'nyy test
// stohasticheskoy loterei vklyucheniya pitaniya na RTL v3.9.9h
// (liniya hiclock: kol'tco r0..r5 N=6 na clk 50 MGc, X1 = r0 duty 1/6,
// CPU 4,167 MGc; clk25 = /2; por-cep' v 50-domene so stroboom r0).
// Adaptaciya tb_poweron_v398.v (etalon na v3.9.8):
//   1) P0a: perbor sostoyaniy = 64 koda kol'tca r0..r5 x 10 kodov
//      por_sh x 2 fazy clk25_q = 1280 kombinaciy; proverki: one-hot
//      <= 2 frontov iz LUBOGO koda; dreyne por_sh v 00000000 za
//      <= 1400 ns NAVSEGDA (8 strobov x 120 ns + samoocistka);
//      por_run padaet i ne vozvrashchaetsya; clk25_q TOGGELITSYA;
//   2) P0b: orbita por-cepi FF->7F->3F->1F->0F->07->03->01->00
//      pri kol'tse v sostoyanii 0 (granica dreyne 1400 ns);
//   3) PX (NOVOE): pattern uzla posle snatiya sbrosa - shag frontov
//      X1 ROVNO 120 ns, high X1 ROVNO 20 ns, X2 == ~X1 v kazhdom
//      legel'nom one-hot, por_ce - ROVNO ODIN strobe 20 ns za 120 ns;
//   4) P1/P2/P3/P4/P5 - po smyslu kak v etalone (stimuly shiny
//      ostavleny v3.9.8 - FSM/logika na clk25 NE MENYALIS', odna
//      peremennaya = dlina kol'tca);
//   5) P2: X1 statichen v '1' (r0 INIT=1) - kak v etalone;
//   6) put' sbrosa - REGISTROVYY (p.21), INIT-registry stavyatsya
//      yavno (kak v etalone); clk25_q - faza 0/1, obe legal'nye.
//
// CEL': u kol'tca N=6, kak i u N=7, NE DOLZHNO byt' "nedopustimoy
// situacii" ot sluchaynogo power-up koda: lyuboy iz 64 kodov ->
// one-hot za <= 2 frontov; por_run snimaetsya <= 1400 ns NAVSEGDA.
//
// Zapusk: scripts/run_tb_poweron_v399h.sh (VCD - tol'ko s +dump)
//=====================================================================
module tb_poweron_v399h;

  //-------------------------------------------------------------------
  // Upravlyaemyy takt 50 MGc (poka clk_run=0 - frontov NET; shag #10 -
  // period 20 ns = 50 MGc, node takta v3.9.9h)
  //-------------------------------------------------------------------
  reg clk = 1'b0;
  reg clk_run = 1'b0;
  always #10 if (clk_run) clk = ~clk;

  //-------------------------------------------------------------------
  // Statichnye vhody (vne faz interesa)
  //-------------------------------------------------------------------
  reg RST = 1'b0, SOD = 1'b0, RX = 1'b1;
  reg RSTOUT = 1'b0, INTAn = 1'b1, HLDA = 1'b0, CLKOUT = 1'b0, S0 = 1'b0, S1 = 1'b0;
  reg AH8 = 1'b0, AH9 = 1'b0, AH10 = 1'b0, AH11 = 1'b0, AH12 = 1'b0, AH13 = 1'b0, AH14 = 1'b0;
  reg row0 = 1'b1, row1 = 1'b0, row2 = 1'b1, row3 = 1'b0, row4 = 1'b1;

  reg ALE = 1'b0, WRn = 1'b1, RDn = 1'b1, IOM = 1'b0, A15 = 1'b0;
  reg [7:0] cpuA = 8'h00, memD = 8'h00;
  wire [7:0] A, D;
  wire X1, X2, RESET_IN, WE_n, CS_n;
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
    .X2(X2), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA),
    .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12), .AH13(AH13), .AH14(AH14),
    .RX(RX),
    .col0(), .col1(), .col2(), .col3(),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

  integer errors = 0;
  integer seed = 1;
  integer i, j, ri, pi, xi;
  time t0;
  integer c25_toggles = 0;
  always @(dut.clk25_q) c25_toggles = c25_toggles + 1;

  //-------------------------------------------------------------------
  // TIK = 40 ns = 1 takt clk25 (takt LOGIKI): na tb-clk 50 MGc eto
  // dva posedge. Semantika tikovyh konstant - 25 MGc v3.9.2-3.9.8.
  //-------------------------------------------------------------------
  task automatic tick(input integer n);
    begin
      repeat (2 * n) @(posedge clk);
      #1;
    end
  endtask

  //-------------------------------------------------------------------
  // polnyy perezapusk uzla iz ZADANNYH sostoyaniy (dlya P0):
  // kol'tco r0..r5 (6 bit vektora: rv[0]=r0 .. rv[5]=r5) + por_sh
  // (8 BIT) + faza clk25_q
  //-------------------------------------------------------------------
  task automatic set_por_state(input [5:0] rv, input [7:0] sh, input c25);
    begin
      clk_run = 1'b0; #1;
      dut.r0      = rv[0];
      dut.r1      = rv[1];
      dut.r2      = rv[2];
      dut.r3      = rv[3];
      dut.r4      = rv[4];
      dut.r5      = rv[5];
      dut.por_sh  = sh;
      dut.clk25_q = c25;
      dut.por_run = 1'b1;                 // vozvrashchaem "pitanievoe" sostoyanie
      // INIT registry puti sbrosa v3.9.6+ (model' power-up; v silicone
      // vse oni s INIT=0 - tverdye do pervogo kloka):
      dut.rst_meta  = 1'b0;
      dut.rst_sync  = 1'b0;
      dut.rst_press = 1'b0;
      dut.rst_qcnt  = 3'b000;
      dut.reset_q   = 1'b0;               // RESET_IN=0 s t=0 (p.21d)
      #1;
    end
  endtask

  // INIT sostoyanie (kak JED): kol'tco v sostoyanii 0 (r0=1), por_sh=FF,
  // faza clk25_q=0 (pervyy posedge clk25 - vtoroy posedge clk pina)
  task automatic set_init;
    begin
      set_por_state(6'b000001, 8'hFF, 1'b0);
    end
  endtask

  // kol'tco v one-hot? (rovno odin trigger v 1)
  function automatic onehot(input dummy);
    begin
      onehot = ((dut.r0 + dut.r1 + dut.r2 + dut.r3 + dut.r4 + dut.r5) == 1);
    end
  endfunction

  // vrazhdebnaya "plavayushchaya" shina v okne POR (model' rastra)
  reg fuzz_on = 1'b0;
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

  // logika v sbrosovyh znacheniyah? (PTC-oderzhimoe poka RESET_IN=0)
  function automatic logic_dirt(input dummy);
    begin
      logic_dirt = (dut.state !== 3'd0) || (dut.rd_seen !== 1'b0)
                 || (dut.wr_seen !== 1'b0) || (dut.addr_latch !== 8'h00)
                 || (dut.bus_reg !== 8'h00) || (dut.seg_q !== 8'hFF)
                 || (dut.dig_q !== 4'hF)  || (dut.snd_q !== 1'b0)
                 || (dut.kbcol_q !== 4'h0);
    end
  endfunction

  initial begin
    $timeformat(-9, 0, " ns", 10);   // %0t v nanosekundah (chitaemye logi)
    if ($test$plusargs("dump")) begin
      $dumpfile("tb_poweron_v399h.vcd");
      $dumpvars(0, tb_poweron_v399h);
    end

    //=================================================================
    // P0a: ISCHERPYVAYUShCHIY PEREBOR (64 kol'tco x 10 kodov por_sh x
    // 2 fazy clk25_q = 1280) pri zhivom clk 50 MGc. Proveryaem CHETYRE
    // svoystva:
    //  (1) ONE-HOT: posle 2-go posedge iz LUBOGO koda kol'tca - rovno
    //      odin trigger (dvoynoy kill + restart NOR6, p.15/22/24);
    //  (2) DRAIN: por_sh draynitsya v 00000000 za <= 1400 ns i NAVSEGDA
    //      (8 strobov r0 x 120 ns + zapas na samoocistku kol'tca);
    //  (3) por_run padaet i ne vozvrashchaetsya (puti SET net);
    //  (4) clk25_q togglitsya (takt logiki zhiv pri lyuboy faze).
    // "Nedopustimaya situaciya" ot sluchaynogo power-up koda - NEVozMOZhNA.
    //=================================================================
    $display("=== P0a: perebor 1280 nachal'nyh sostoyaniy (kol'tco 64 x por_sh 10 x faza clk25 2), zhivoy clk 50 MGc ===");
    begin : p0a
      integer p0a_err, oh2, c25_seen0, c25_seen1;
      reg c25_0;
      reg [7:0] shorb [0:9];
      p0a_err = 0; oh2 = 0; c25_seen0 = 0; c25_seen1 = 0;
      shorb[0] = 8'hFF; shorb[1] = 8'h7F; shorb[2] = 8'h3F; shorb[3] = 8'h1F;
      shorb[4] = 8'h0F; shorb[5] = 8'h07; shorb[6] = 8'h03; shorb[7] = 8'h01;
      shorb[8] = 8'hA5; shorb[9] = 8'h5A;
      quiet_bus; RST = 1'b0;
      for (ri = 0; ri < 64; ri = ri + 1)
        for (pi = 0; pi < 10; pi = pi + 1)
          for (xi = 0; xi < 2; xi = xi + 1) begin
            set_por_state(ri[5:0], shorb[pi], xi[0]);
            c25_toggles = 0;
            clk_run = 1'b1;
            // (1) one-hot za <= 2 frontov
            @(posedge clk); #1;
            @(posedge clk); #1;
            if (!onehot(1'b0)) begin
              p0a_err = p0a_err + 1;
              $display("RESULT P0a FAIL: kol'tco=%b - posle 2 frontov NE one-hot (r=%b%b%b%b%b%b)", ri[5:0], dut.r0, dut.r1, dut.r2, dut.r3, dut.r4, dut.r5);
            end
            // (2) drain por_sh (8 bit)
            t0 = $time;
            while ((dut.por_sh !== 8'h0) && (($time - t0) < 2500)) #10;
            if (dut.por_sh !== 8'h0) begin
              p0a_err = p0a_err + 1;
              $display("RESULT P0a FAIL: kol'tco=%b por_sh=%h faza=%0d - por_sh NE draynitsya v 00 za 2500 ns (ZACHYLKA!)", ri[5:0], pi, xi);
            end else begin
              if (($time - t0) > 1400) begin
                p0a_err = p0a_err + 1;
                $display("RESULT P0a FAIL: kol'tco=%b por_sh=%h faza=%0d - drayn za %0t > 1400 ns", ri[5:0], pi, xi, $time - t0);
              end
              repeat (2) @(posedge clk);     // por_run padaet na posedge posle drayna
              if (dut.por_run !== 1'b0) begin
                p0a_err = p0a_err + 1;
                $display("RESULT P0a FAIL: kol'tco=%b por_sh=00, no por_run=1", ri[5:0]);
              end
              repeat (20) @(posedge clk);    // navsegda
              if ((dut.por_sh !== 8'h0) || (dut.por_run !== 1'b0)) begin
                p0a_err = p0a_err + 1;
                $display("RESULT P0a FAIL: posle drayna por_sh=%h por_run=%b (nazad prishlo!)", dut.por_sh, dut.por_run);
              end
            end
            // (4) clk25_q togglilsya (pri lyuboy nachal'noy faze):
            if (c25_toggles >= 2) begin
              if (xi == 0) c25_seen0 = c25_seen0 + 1;
              else         c25_seen1 = c25_seen1 + 1;
            end else begin
              p0a_err = p0a_err + 1;
              $display("RESULT P0a FAIL: kol'tco=%b faza=%0d - clk25_q NE togglilsya (toggl=%0d, takt logiki mertv?)", ri[5:0], xi, c25_toggles);
            end
            clk_run = 1'b0; #1;
          end
      if (p0a_err == 0)
        $display("RESULT P0a PASS: vse 1280 kombinaciy - kol'tco one-hot za <=2 frontov iz LUBOGO koda, por_sh draynitsya v 00 za <=1400 ns navsegda, clk25_q togglitsya pri obeih fazah (%0d/%0d) - 'nedopustimaya situaciya' ot power-up koda NEVozMOZhNA", c25_seen0, c25_seen1);
      else
        $display("RESULT P0a: %0d oshibok", p0a_err);
      errors = errors + p0a_err;
    end

    //=================================================================
    // P0b: hardware-orbit por-cepi: monotonnoe snatie iz dostizhimyh
    // sostoyaniy (FF,7F,3F,1F,0F,07,03,01,00) pri kol'tse v sostoyanii 0
    //=================================================================
    $display("=== P0b: orbita por-cepi FF->7F->...->00 pri kol'tse v sostoyanii 0 ===");
    begin : p0b
      integer p0b_err, k;
      reg [7:0] orbit [0:8];
      p0b_err = 0;
      orbit[0] = 8'hFF; orbit[1] = 8'h7F; orbit[2] = 8'h3F; orbit[3] = 8'h1F;
      orbit[4] = 8'h0F; orbit[5] = 8'h07; orbit[6] = 8'h03; orbit[7] = 8'h01;
      orbit[8] = 8'h00;
      for (k = 0; k < 9; k = k + 1) begin
        set_por_state(6'b000001, orbit[k], 1'b0);
        clk_run = 1'b1;
        t0 = $time;
        while ((dut.por_run === 1'b1) && (($time - t0) < 2500)) #10;
        if (orbit[k] === 8'h00) begin
          if (dut.por_run !== 1'b0) begin p0b_err = p0b_err + 1; $display("RESULT P0b FAIL: por_sh=0, por_run=1"); end
        end else begin
          if (dut.por_run !== 1'b0) begin p0b_err = p0b_err + 1; $display("RESULT P0b FAIL: orbita %h - por_run ne snimalsya", orbit[k]); end
          else if (($time - t0) > 1400) begin p0b_err = p0b_err + 1; $display("RESULT P0b FAIL: orbita %h - snatie za %0t > 1400 ns", orbit[k], $time - t0); end
        end
        repeat (80) @(posedge clk);            // zapas posle drayna
        if (dut.por_run !== 1'b0) begin p0b_err = p0b_err + 1; $display("RESULT P0b FAIL: por_run vernulsya v 1 (orbita %h)", orbit[k]); end
        clk_run = 1'b0; #1;
      end
      if (p0b_err == 0)
        $display("RESULT P0b PASS: iz vseh dostizhimyh v zheleze sostoyaniy (FF,7F,3F,1F,0F,07,03,01,00) snatie monotonnoe za <=1400 ns, bez vozvrata (50-domennaya por-cep', strobe r0, N=6)");
      else
        $display("RESULT P0b: %0d oshibok", p0b_err);
      errors = errors + p0b_err;
    end

    //=================================================================
    // PX: PATTERN UZLA posle snatiya sbrosa (verifikaciya N=6):
    // shag voshodyashchih frontov X1 ROVNO 120 ns; high X1 ROVNO 20 ns;
    // X2 == ~X1 v KAZHDOM legel'nom one-hot; por_ce - ROVNO ODIN strobe
    // 20 ns za period kol'tca 120 ns; duty X1 = 1/6 tochno (setka 10 ns).
    //=================================================================
    $display("=== PX: pattern uzla (X1 8,33 MGc shag 120 ns duty 1/6, X2=~X1, por_ce 1 raz za 120 ns) ===");
    begin : px
      integer px_err, n_edges, n_samp, ones, n_ce;
      time t_prev_rise, t_rise, t_ce_prev;
      reg x1_q, pc_q;
      px_err = 0; n_edges = 0; n_samp = 0; ones = 0; n_ce = 0;
      t_prev_rise = 0; t_rise = 0; t_ce_prev = 0; pc_q = 1'b0;
      quiet_bus; RST = 1'b0;
      set_init;
      clk_run = 1'b1;
      t0 = $time;
      while ((RESET_IN === 1'b0) && (($time - t0) < 2000)) #10;
      if (RESET_IN !== 1'b1) begin
        px_err = px_err + 1;
        $display("RESULT PX FAIL: RESET_IN ne snivalsya 2000 ns");
      end else begin
        $display("RESULT PX INFO: RESET_IN snyalsya cherez %0t ns (model': ~900 - dreyne 880 + kromka clk25)", $time - t0);
      end
      repeat (40) @(posedge clk);          // 800 ns posle snatiya - ustanovivshiyся rezhim
      #3;                                   // sdvig setki s kromek (vnutr perioda)
      x1_q = X1;
      for (i = 0; i < 600; i = i + 1) begin  // 6000 ns = 50 periodov kol'tca
        #10;
        if (X1 === 1'b1 && x1_q === 1'b0) begin   // voshodyashchiy front
          if (n_edges > 0) begin
            if (($time - t_prev_rise) !== 120) begin
              px_err = px_err + 1;
              $display("RESULT PX FAIL: shag frontov X1 = %0t ns (ozhidanie ROVNO 120)", $time - t_prev_rise);
            end
          end
          t_prev_rise = $time;
          n_edges = n_edges + 1;
        end
        if (X1 === 1'b0 && x1_q === 1'b1) begin   // nishodyashchiy front
          if (($time - t_rise) !== 20) begin
            px_err = px_err + 1;
            $display("RESULT PX FAIL: high X1 = %0t ns (ozhidanie ROVNO 20)", $time - t_rise);
          end
        end
        if (X1 === 1'b1 && x1_q === 1'b0) t_rise = $time;
        x1_q = X1;
        if (X1 === 1'b1) ones = ones + 1;
        // X2 == ~X1 v legel'nom one-hot (posle samoocistki - VSEGDA)
        if (X2 !== ~X1) begin
          px_err = px_err + 1;
          if (px_err < 5) $display("RESULT PX FAIL: X2(%b) != ~X1(%b) na t=%0t", X2, X1, $time);
        end
        // por_ce: ROVNO ODIN strobe 20 ns za period 120 ns (kontrol' PO
        // FRONTU stroba - 20-ns okno setka 10 ns lovit dvazhdy)
        if (dut.por_ce === 1'b1 && pc_q === 1'b0) begin
          if (t_ce_prev !== 0) begin
            if (($time - t_ce_prev) !== 120) begin
              px_err = px_err + 1;
              $display("RESULT PX FAIL: shag strobov por_ce = %0t (ozhidanie ROVNO 120)", $time - t_ce_prev);
            end
          end
          t_ce_prev = $time;
          n_ce = n_ce + 1;
        end
        pc_q = dut.por_ce;
        n_samp = n_samp + 1;
      end
      if (ones * 6 !== n_samp) begin
        px_err = px_err + 1;
        $display("RESULT PX FAIL: duty X1 = %0d/%0d (ozhidanie ROVNO 1/6 = %0d)", ones, n_samp, n_samp / 6);
      end
      if (n_ce < 45) begin
        px_err = px_err + 1;
        $display("RESULT PX FAIL: strobov por_ce za okno = %0d (ozhidanie ~50)", n_ce);
      end
      if (px_err == 0)
        $display("RESULT PX PASS: %0d frontov X1, shag ROVNO 120 ns, high ROVNO 20 ns (duty %0d/%0d = 1/6), X2 == ~X1 v kazhdom sample, por_ce %0d strobov shag 120 ns - pattern N=6 TOCHEN", n_edges, ones, n_samp, n_ce);
      else
        $display("RESULT PX: %0d oshibok", px_err);
      errors = errors + px_err;
    end

    //=================================================================
    // P1: 100 seedov starta s vrazhdebnoy shinoy v okne POR i pervye
    // 1 mks posle starta CPU (stimuly v3.9.8 - logika na clk25 ne
    // menyas').  (a) /WE v hvoste 200 ns - NET; (b) SAMOZAZHIVLENIE
    // dvumya real'nymi ciklami; (c) RESET_IN snimaetsya <=2000 ns.
    //=================================================================
    $display("=== P1: 100 seedov starta s plavayushchey shinoy (okno POR + 1 mks posle) s proverkoy samozazhivleniya ===");
    begin : p1
      integer p1_err, n_dirty_rel, n_healed, n_healed2, n_we_late, jj;
      reg we_seen, healed;
      time we_t_rel, t_rel_boot;
      p1_err = 0; n_dirty_rel = 0; n_healed = 0; n_healed2 = 0; n_we_late = 0;
      for (j = 0; j < 100; j = j + 1) begin
        seed = j + 1;
        set_init;                            // INIT sostoyanie (kak JED)
        fuzz_on = 1'b1;
        clk_run = 1'b1;
        t0 = $time;
        while ((RESET_IN === 1'b0) && (($time - t0) < 2000)) #10;
        if (RESET_IN !== 1'b1) begin
          p1_err = p1_err + 1;
          $display("RESULT P1 FAIL seed=%0d: RESET_IN ne snimalsya 2000 ns", j);
        end else begin
          t_rel_boot = $time;
          if (logic_dirt(1'b0)) begin
            n_dirty_rel = n_dirty_rel + 1;   // gryaz' OKNA - schitaem (INFO)
          end
        end
        // eshche 1 mks plavaniy posle starta CPU
        t0 = $time;
        we_seen = 1'b0;
        while (($time - t0) < 1000) begin
          #10;
          if (WE_n === 1'b0 && !we_seen) begin
            we_seen = 1'b1;
            we_t_rel = $time - t_rel_boot;
          end
        end
        if (we_seen) begin
          if (we_t_rel <= 200) begin
            p1_err = p1_err + 1;
            $display("RESULT P1 FAIL seed=%0d: /WE cherez %0t posle starta CPU (v hvoste 200 ns etalona - OKNO RODILO ZAPIS', klass defekta 11-5)", j, we_t_rel);
          end else begin
            n_we_late = n_we_late + 1;
            $display("RESULT P1 INFO seed=%0d: /WE cherez %0t posle starta (tol'ko pri DOLGOM plavanii >200 ns - pole vreda ne pokazyvaet, no svidetel'stvo okna)", j, we_t_rel);
          end
        end
        // tishina + DO 2 REAL'NYH cikla chteniya - dolzhny VYCHISTIT'
        quiet_bus;
        healed = 1'b0;
        for (jj = 0; jj < 2 && !healed; jj = jj + 1) begin
          cpuA = 8'h5A; ALE = 1'b1; IOM = 1'b0; A15 = 1'b0;
          memD = 8'hC3;
          repeat (8) @(posedge clk); #1;   // ALE = T1 (forma stimula v3.9.8)
          ALE = 1'b0; RDn = 1'b0;
          repeat (6) @(posedge clk); #1;   // T2
          RDn = 1'b1; memD = 8'h00;
          repeat (12) @(posedge clk); #1;  // zazor
          if ((dut.state === 3'd0) && (dut.rd_seen === 1'b0) && (dut.wr_seen === 1'b0)
              && (dut.addr_latch === 8'h5A))
            healed = 1'b1;
        end
        if (healed) begin
          if (jj == 1) n_healed = n_healed + 1;      // s pervogo cikla
          else         n_healed2 = n_healed2 + 1;    // so vtorogo (hvost WB)
        end else begin
          p1_err = p1_err + 1;
          $display("RESULT P1 FAIL seed=%0d: NE vychistilos' dvumya real'nymi ciklami: state=%0d rd_seen=%b wr_seen=%b addr_latch=%h (ozhidanie 0/0/0/5a)", j, dut.state, dut.rd_seen, dut.wr_seen, dut.addr_latch);
        end
        // 1,5 mks tishiny: FSM v IDLE, /WE molchit
        we_seen = 1'b0;
        t0 = $time;
        while (($time - t0) < 1500) begin
          #10;
          if (WE_n === 1'b0) we_seen = 1'b1;
        end
        if (we_seen) begin p1_err = p1_err + 1; $display("RESULT P1 FAIL seed=%0d: /WE zvenel v tishine", j); end
        if (dut.state !== 3'd0) begin p1_err = p1_err + 1; $display("RESULT P1 FAIL seed=%0d: FSM ne vernulsya v IDLE", j); end
      end
      if (p1_err == 0)
        $display("RESULT P1 PASS: 100/100 - sbros snimaetsya <=2000 ns; /WE v hvoste 200 ns - 0; okno pisalo gryaz' v %0d/100 seedov; vychischenie: %0d s 1-go cikla, %0d so 2-go; pozdnih /WE - %0d (INFO)", n_dirty_rel, n_healed, n_healed2, n_we_late);
      else
        $display("RESULT P1: %0d oshibok (gryaz' okna v %0d/100, s 1-go cikla %0d, so 2-go %0d, pozdnih /WE %0d)", p1_err, n_dirty_rel, n_healed, n_healed2, n_we_late);
      errors = errors + p1_err;
    end

    //=================================================================
    // P2: MERTVYY clk - TOCHNOE VOSPROIZVEDENIE ZHALOBY 11-6bis
    // (X1 statichen v '1' - r0 INIT=1)
    //=================================================================
    $display("=== P2: mertvyy clk (LTC6905 ne startoval): knopka i provodnichok bespolezny ===");
    begin : p2
      integer p2_err;
      p2_err = 0;
      clk_run = 1'b0; clk = 1'b0;
      RST = 1'b0; quiet_bus;
      set_init;                             // INIT: kol'tco=0 (r0=1), por_sh=FF, por_run=1
      #100000;                              // 100 mks "mertvoy" platy
      if (dut.por_run !== 1'b1) begin p2_err = p2_err + 1; $display("RESULT P2 FAIL: por_run upal BEZ clk?!"); end
      if (RESET_IN !== 1'b0)    begin p2_err = p2_err + 1; $display("RESULT P2 FAIL: RESET_IN ne 0"); end
      if (X1 !== 1'b1)          begin p2_err = p2_err + 1; $display("RESULT P2 FAIL: X1 ne statichen (ozhidanie '1' - r0 INIT=1)"); end
      if (dut.clk25_q !== 1'b0) begin p2_err = p2_err + 1; $display("RESULT P2 FAIL: clk25_q ne statichen"); end
      if (seg !== 8'h00)        begin p2_err = p2_err + 1; $display("RESULT P2 FAIL: seg piny ne 00 (8.8.8.8 dolzhen GORET')"); end
      if (dig !== 4'h0)         begin p2_err = p2_err + 1; $display("RESULT P2 FAIL: dig piny ne 0"); end
      if (dut.state !== 3'd0)   begin p2_err = p2_err + 1; $display("RESULT P2 FAIL: FSM ne v IDLE"); end
      // 5 nazhatiy knopki (RST=1 10 mks, otpuskanie 50 mks) - "zhmu mnogo raz"
      for (i = 0; i < 5; i = i + 1) begin
        RST = 1'b1; #10000;
        RST = 1'b0; #50000;                  // OTPUSKANIE - moment istiny
        if (RESET_IN !== 1'b0) begin p2_err = p2_err + 1; $display("RESULT P2 FAIL: nazhatie %0d - posle otpuskaniya RESET_IN VYSOK, a dolzhen ostavat'sya 0 (por_run=1)", i); end
        if (dut.por_run !== 1'b1) begin p2_err = p2_err + 1; $display("RESULT P2 FAIL: knopka sdvinula por_run?!"); end
      end
      if (p2_err == 0)
        $display("RESULT P2 PASS: mertvyy clk = 8.8.8.8 gorit, X1 statichen ('1'), RESET_IN=0, FSM v IDLE, knopka x5 i provodnichok - NUL' effekta (simptom-kompleks zhaloby 11-6bis - TAK ZHE, kak v v3.9.2-3.9.8)");
      else
        $display("RESULT P2: %0d oshibok", p2_err);
      errors = errors + p2_err;
    end

    //=================================================================
    // P3: POZDNIY clk - samozazhivlenie bez peredyrgivaniya
    //=================================================================
    $display("=== P3: pozdniy start clk (30 mks): dozrevanie BEZ peredyrgivaniya ===");
    begin : p3
      integer p3_err;
      p3_err = 0;
      clk_run = 1'b0; clk = 1'b0; RST = 1'b0; quiet_bus;
      set_init;
      #30000;
      if (RESET_IN !== 1'b0) begin p3_err = p3_err + 1; $display("RESULT P3 FAIL: do clk sbros dolzhen derzhatsya"); end
      clk_run = 1'b1;                        // oscillyator "zavelsya"
      t0 = $time;
      while ((RESET_IN === 1'b0) && (($time - t0) < 2000)) #10;
      if (RESET_IN !== 1'b1) begin p3_err = p3_err + 1; $display("RESULT P3 FAIL: posle prihoda clk sbros ne snimaetsya"); end
      else if (($time - t0) > 1400) begin p3_err = p3_err + 1; $display("RESULT P3 FAIL: snatie za %0t > 1400 ns", $time - t0); end
      if (p3_err == 0)
        $display("RESULT P3 PASS: s prihodom clk sbros snimaetsya za <=1400 ns - plata by 'dozrela sama'; v zhalobe etogo NET => mertvoe sostoyanie vladel'ca = clk NE prihodit VOOBshCHE");
      else
        $display("RESULT P3: %0d oshibok", p3_err);
      errors = errors + p3_err;
    end

    //=================================================================
    // P4: RST zatyanut v 1 - otpuskanie ozhivlyaet cherez kvalifikator
    // (2FF + 8 takt kvalifikatora + reset_q = 400..440 ns - anatomia
    // p.21 na clk25; v 50-domene por-cep' doschityvaet pod RST=1)
    //=================================================================
    $display("=== P4: RST=1 vne knopki: otpuskanie lechit s pervogo raza (latentnost' ~440 ns - anatomiya v3.9.6) ===");
    begin : p4
      integer p4_err;
      time t_rel;
      p4_err = 0;
      quiet_bus;
      set_init;
      RST = 1'b1;
      clk_run = 1'b1;
      #30000;                                 // "seansiya" s prizhatym RST
      if (RESET_IN !== 1'b0)    begin p4_err = p4_err + 1; $display("RESULT P4 FAIL: pri RST=1 sbros dolzhen derzhatsya"); end
      if (dut.por_run !== 1'b0) begin p4_err = p4_err + 1; $display("RESULT P4 FAIL: por-cep' dolzhna doschitat' pod RST=1"); end
      RST = 1'b0;                               // otpuskanie knopki
      t_rel = $time;
      t0 = $time;
      while ((RESET_IN === 1'b0) && (($time - t0) < 1500)) #10;
      if (RESET_IN !== 1'b1) begin p4_err = p4_err + 1; $display("RESULT P4 FAIL: posle otpuskaniya sbros ne snyalsya dazhe za 1500 ns"); end
      else $display("RESULT P4 INFO: snatie cherez %0t ns posle otpuskaniya (2FF+8 takt kvalifikatora+reset_q - norma mery p.21)", $time - t_rel);
      if (p4_err == 0)
        $display("RESULT P4 PASS: klass 'RST=1' ozhivlyaetsya OTPUSKANIEM knopki s pervogo raza - vladelec zhmet/otpuskaet BEZ effekta, znachit etot klass vycherkivan (esli otpuskanie dohodit do U1.1)");
      else
        $display("RESULT P4: %0d oshibok", p4_err);
      errors = errors + p4_err;
    end

    //=================================================================
    // P5: LOTEREYa peredyrgivaniy (20 ciklov, P_START=3/4)
    //=================================================================
    $display("=== P5: lotereya 'vkl-vykl pitaniya' (20 ciklov, P_START=3/4) ===");
    begin : p5
      integer p5_err, booted, dead;
      reg want_alive;
      p5_err = 0; booted = 0; dead = 0;
      seed = 777;
      quiet_bus; RST = 1'b0;
      for (i = 0; i < 20; i = i + 1) begin
        clk_run = 1'b0; clk = 1'b0;
        r = $random(seed); want_alive = (r[1:0] < 2'd3);   // P_START = 3/4
        set_init;
        if (want_alive) begin
          clk_run = 1'b1;
          t0 = $time;
          while ((RESET_IN === 1'b0) && (($time - t0) < 2000)) #10;
          if (RESET_IN !== 1'b1) begin p5_err = p5_err + 1; $display("RESULT P5 FAIL cikl=%0d: 'zhivoy' start ne zagruzilsya", i); end
          booted = booted + 1;
        end else begin
          #5000;                                 // 5 mks mertvoy sessii
          if (RESET_IN !== 1'b0) begin p5_err = p5_err + 1; $display("RESULT P5 FAIL cikl=%0d: mertvaya sessiya sama ozhila?!", i); end
          dead = dead + 1;
        end
      end
      if (p5_err == 0)
        $display("RESULT P5 PASS: zagruzok=%0d, mertvyh=%0d - kazhdoe mertvoe vyzdoravlivaet tol'ko SLEDUYUshCHIM peredyrgivaniem ('rano ili pozdno', geometriya zhaloby)", booted, dead);
      else
        $display("RESULT P5: %0d oshibok", p5_err);
      errors = errors + p5_err;
    end

    //=================================================================
    $display("=== ITOG tb_poweron_v399h: %0d oshibok (%s) ===", errors, (errors == 0 ? "VSE PASS" : "EST' FAILY"));
    $finish;
  end

endmodule
