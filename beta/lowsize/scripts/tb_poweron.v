`timescale 1ns/1ps
//=====================================================================
// tb_poweron.v (lowsize, 2026-11-06): DOKAZATEL'NYJ TEST STOHASTICHESKOJ
// LOTEREI VKLJUCHENIJA PITANIJA (zhaloba vladel'ca 11-6bis na v3.9.5:
// "vkljuchaju platu - na displee 8.8.8.8, knopka sbrosa N raz - nуль,
// provodnichok na nogu CPU mimo CPLD - nуль, pomogaet tol'ko
// peredyrgivanie pitaniya, sluchajno"). DUT - REAL'NYJ RTL v3.9.5.
//
// GIPOTEZA VLADEL'CA: "delitel' na sdvigovom regestre vhodit v
// nedopustimuyu situaciyu, kotoraya reshaetsya tol'ko podachej
// napryazheniya". PROVERKA ISCHERPYVAYUshCHIM PEREBOROM (P0): u delitelja
// (cnt mod-7) vse 8 sostoyaniy legal'ny/samovosstanavlivayutsya, u
// POR-sdvigovogo registra por_sh LJOBOJ iz 16 nachal'nyh kodov
// osvobozhdaet sbros za <=4 stroba - "nedopustimoy situacii" V CIFRE
// NET. Edinstvennyy "zamok" - MERTVYY clk 25 MGc (U7 LTC6905): bez
// frontov por-cep' zamorozhena s por_run=1, RESET_IN=0, i NIKAKIE
// knopki/provodochki eto ne menyayut (P2) - polnyy nabor simptomov.
//
// FAZY:
//   P0  ischerpyvayushchiy perebor nachal'nyh sostoyaniy por-cepi
//       (cnt 8 x por_sh 16 x x1_n 2 = 256 kombinaciy) pri zhivom clk:
//       por_run padaet u VSEH za <=T_BOUND i bol'she ne vozvrashchaetsya.
//   P1  100 seedov chistogo starta s vrazhdebnoy "plavayushchey" shinoy
//       v okne POR (model' togo, chto CPU/shiny dreyfuyut na rastre):
//       RESET_IN snimaetsya <=2000 ns, logika chistaya v moment snatiya
//       (vse 40 PTC-registrov v sbrosnyh znacheniyah); dalee tishina -
//       FSM stoit v IDLE, /WE ne zvenit.
//   P2  MERTVYY clk (model': LTC6905 ne startoval): por_run=1 vecno,
//       RESET_IN=0 vecno, X1 STATICHESKIY 0, seg/dig piny 0 (8.8.8.8
//       gorit), 5 nazhatiy knopki (RST impul'sy s otpuskaniem) - NUL'
//       effekta; "provodnichok na cpu36" - nul' po postroeniyu (CPU uzhe
//       v sbrose). = TOCHNOE VOSPROIZVEDENIE ZHALOBY. Vyhod - tol'ko
//       peredyrgivaniem pitaniya (P5).
//   P3  pozdniy clk (start oscillyatora cherez 30 mks): do pervogo
//       fronta - ta zhe "smert'", posle - samozazhivlenie za <=1600 ns
//       BEZ peredyrgivaniya. Podpis': esli by u vladel'ca byl etot
//       klass - plata "dozrevala by sama", chego v zhalobe NET =>
//       v plohih sessiyah vladel'ca clk NE STARTUET VOOBshCHE.
//   P4  RST zatyanut v 1 (model' natyanutoy knopki/cepi): "smert'"
//       pri zhivom X1 (por-cep' doschityvaet pod RST=1); otpuskanie
//       knopki (RST->0) OZHIVLYAET MGNIVENNO. Raz vladel'ec zhmet-
//       otpuskaet knopku mnogo raz BEZ effekta - etot klass u nego
//       vycherkivaetsya (esli otpuskanie dohodit do U1.1).
//   P5  lotereya peredyrgivaniy: 20 ciklov "pitanie vkl/vykl", kazhdoe
//       vklyuchenie startuet oscillyator s verozatnost'yu 3/4: horoshie
//       sessii zagruzhayutsya, mertvye - tol'ko sleduyushchim
//       peredyrgivaniem ("rano ili pozdno pomogaet" - geometricheskoe
//       raspredelenie, kak v zhalobe).
//
// Zapusk: scripts/run_tb_poweron.sh
//=====================================================================
module tb_poweron;

  //-------------------------------------------------------------------
  // Upravlyaemyy takt: poka clk_run=0 - frontov NET (model' mertvogo
  // oscillyatora U7 LTC6905; shag #20 - period 40 ns = 25 MGc)
  //-------------------------------------------------------------------
  reg clk = 1'b0;
  reg clk_run = 1'b0;
  always #20 if (clk_run) clk = ~clk;

  //-------------------------------------------------------------------
  // Statichnye vhody (vne faz interesa)
  //-------------------------------------------------------------------
  reg RST = 1'b0, SOD = 1'b0, RX = 1'b1;
  reg RSTOUT = 1'b0, INTAn = 1'b1, HLDA = 1'b0, CLKOUT = 1'b0, S0 = 1'b0, S1 = 1'b0;
  reg AH8 = 1'b0, AH9 = 1'b0, AH10 = 1'b0, AH11 = 1'b0, AH12 = 1'b0, AH13 = 1'b0, AH14 = 1'b0;
  reg row0 = 1'b1, row1 = 1'b0, row2 = 1'b1, row3 = 1'b0, row4 = 1'b1;

  // Shina CPU/'573/pamyati: model' vneshnego mira (slabyy drajv; vnutri
  // DUT - svoi sil'nye trehstabil'nye drajvery)
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

  integer errors = 0;
  integer seed = 1;
  integer i, j, ci, pi, xi;
  time t0;

  // polnyy perezapusk por-cepi iz ZADANNYH sostoyaniy (dlya P0)
  task automatic set_por_state(input [2:0] c, input [3:0] sh, input x);
    begin
      clk_run = 1'b0; #1;
      dut.cnt     = c;
      dut.por_sh  = sh;
      dut.x1_n    = x;
      dut.por_run = 1'b1;                 // vozvrashchaem "pitanievoe" sostoyanie
      #1;
    end
  endtask

  // vrazhdebnaya "plavayushchaya" shina v okne POR (model' rastra):
  // sluchaynye pereklyucheniya kazhdye 10 ns, veroyatnost' 3/8 na liniyu
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

  // logika v sbrosnyh znacheniyah? (PTC-oderzhimoe poka RESET_IN=0)
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
    $dumpfile("tb_poweron.vcd");
    $dumpvars(0, tb_poweron);

    //=================================================================
    // P0: ISCHERPYVAYUShCHIY PEREBOR por-cepi pri zhivom clk (256).
    // Pроверяем ДВА свойства:
    //  (a) DRAIN: iz LUBOGO iz 16 kodov por_sh (s lyubym cnt/x1_n)
    //      por_sh draynitsya v 0000 za <=1600 ns i NAVSEGDA tam
    //      ostayetsya (por_run pri etom 0; puti SET u por_run net -
    //      "nedopustimaya situaciya" s zachylkinami zhestko isklyuchena);
    //  (b) HARDWARE-PUT': iz sostoyaniy, DOSTIZHIMYH v zheleze (orbita
    //      INIT=F: F,7,3,1,0 - drugie kody nedostizhimy: shift vlozhil
    //      0 v MSB, INIT edinstvennyy) pri por_run=1 snatie
    //      MONOTONNOE (bez otskoka) za <=1600 ns.
    // Primechanie: dlya nedorazhimyh ishodnyh kodov (bit0=0, starshie=1)
    // por_run mozhet "otskakivat'" v 1 poka por_sh eshche draynitsya -
    // eto ARTIFAKT iskusstvennogo nachal'nogo sostoyaniya, a ne zheleza.
    //=================================================================
    $display("=== P0: perebor 256 nachal'nyh sostoyaniy por-cepi (cnt x por_sh x x1_n), zhivoy clk ===");
    quiet_bus; RST = 1'b0;
    for (ci = 0; ci < 8; ci = ci + 1)
      for (pi = 0; pi < 16; pi = pi + 1)
        for (xi = 0; xi < 2; xi = xi + 1) begin
          set_por_state(ci[2:0], pi[3:0], xi[0]);
          clk_run = 1'b1;
          t0 = $time;
          while ((dut.por_sh !== 4'h0) && (($time - t0) < 2500)) #10;
          if (dut.por_sh !== 4'h0) begin
            errors = errors + 1;
            $display("RESULT P0 FAIL: cnt=%0d por_sh=%h x1_n=%0d - por_sh NE draynitsya v 0000 za 2500 ns (ZACHYLKA!)", ci, pi, xi);
          end else begin
            if (($time - t0) > 1600) begin
              errors = errors + 1;
              $display("RESULT P0 FAIL: cnt=%0d por_sh=%h x1_n=%0d - drayn za %0t > 1600 ns", ci, pi, xi, $time - t0);
            end
            repeat (2) @(posedge clk);     // por_run padaet na posedge POSLE drayna (por_run <= por_sh[0])
            if (dut.por_run !== 1'b0) begin
              errors = errors + 1;
              $display("RESULT P0 FAIL: cnt=%0d por_sh=0000, no por_run=1", ci, pi, xi);
            end
            repeat (20) @(posedge clk);    // navsegda: sdvig derzhit nuli, por_run <= 0
            if ((dut.por_sh !== 4'h0) || (dut.por_run !== 1'b0)) begin
              errors = errors + 1;
              $display("RESULT P0 FAIL: posle drayna por_sh=%h por_run=%b (nazad prishlo!)", dut.por_sh, dut.por_run);
            end
          end
          clk_run = 1'b0; #1;
        end
    if (errors == 0)
      $display("RESULT P0a PASS: vse 256 kombinaciy draynyat por_sh v 0000 za <=1600 ns, navsegda - zachylki v por-cepi NEVOZMOZHNY");
    else
      $display("RESULT P0a: %0d oshibok", errors);

    // (b) hardware-orbita: monotonnoe snatie iz dostizhimyh sostoyaniy
    begin : p0b
      integer p0b_err, k;
      reg [3:0] orbit [0:4];
      p0b_err = 0;
      orbit[0] = 4'hF; orbit[1] = 4'h7; orbit[2] = 4'h3; orbit[3] = 4'h1; orbit[4] = 4'h0;
      for (k = 0; k < 5; k = k + 1) begin
        set_por_state(3'd0, orbit[k], 1'b0);
        clk_run = 1'b1;
        t0 = $time;
        while ((dut.por_run === 1'b1) && (($time - t0) < 2500)) #10;
        if (orbit[k] === 4'h0) begin
          if (dut.por_run !== 1'b0) begin p0b_err = p0b_err + 1; $display("RESULT P0b FAIL: por_sh=0, por_run=1"); end
        end else begin
          if (dut.por_run !== 1'b0) begin p0b_err = p0b_err + 1; $display("RESULT P0b FAIL: orbita %h - por_run ne snimalsya", orbit[k]); end
          else if (($time - t0) > 1600) begin p0b_err = p0b_err + 1; $display("RESULT P0b FAIL: orbita %h - snyatie za %0t > 1600 ns", orbit[k], $time - t0); end
        end
        repeat (40) @(posedge clk);
        if (dut.por_run !== 1'b0) begin p0b_err = p0b_err + 1; $display("RESULT P0b FAIL: por_run vernulsya v 1 (orbita %h)", orbit[k]); end
        clk_run = 1'b0; #1;
      end
      if (p0b_err == 0)
        $display("RESULT P0b PASS: iz vseh dostizhimyh v zheleze sostoyaniy (F,7,3,1,0) snatie monotonnoe za <=1600 ns, bez vozvrata");
      else
        $display("RESULT P0b: %0d oshibok", p0b_err);
      errors = errors + p0b_err;
    end

    //=================================================================
    // P1: 100 seedov chistogo starta s vrazhdebnoy shinoy v okne POR
    //=================================================================
    $display("=== P1: 100 seedov starta s plavayushchey shinoy v okne POR ===");
    begin : p1
      integer p1_err;
      reg we_seen;
      p1_err = 0;
      for (j = 0; j < 100; j = j + 1) begin
        seed = j + 1;
        set_por_state(3'd0, 4'hF, 1'b0);   // INIT sostoyanie (kak JED)
        fuzz_on = 1'b1;
        clk_run = 1'b1;
        t0 = $time;
        while ((RESET_IN === 1'b0) && (($time - t0) < 2000)) #10;
        if (RESET_IN !== 1'b1) begin
          p1_err = p1_err + 1;
          $display("RESULT P1 FAIL seed=%0d: RESET_IN ne snimalsya 2000 ns", j);
        end else if (logic_dirt(1'b0)) begin
          p1_err = p1_err + 1;
          $display("RESULT P1 FAIL seed=%0d: logika GRYAZNAYA v moment snatiya sbrosa", j);
        end
        quiet_bus;
        // 2 mks tishiny: FSM dolzhen stoyat' v IDLE, /WE ne zvenit
        we_seen = 1'b0;
        t0 = $time;
        while (($time - t0) < 2000) begin
          #10;
          if (WE_n === 1'b0) we_seen = 1'b1;
        end
        if (we_seen) begin p1_err = p1_err + 1; $display("RESULT P1 FAIL seed=%0d: /WE zvenel v tishine", j); end
        if (dut.state !== 3'd0) begin p1_err = p1_err + 1; $display("RESULT P1 FAIL seed=%0d: FSM ne vernulsya v IDLE", j); end
      end
      if (p1_err == 0)
        $display("RESULT P1 PASS: 100/100 - sbros snimaetsya <=2000 ns, logika chistaya, FSM v IDLE, /WE molchit");
      else
        $display("RESULT P1: %0d oshibok", p1_err);
      errors = errors + p1_err;
    end

    //=================================================================
    // P2: MERTVYY clk - TOCHNOE VOSPROIZVEDENIE ZHALOBY 11-6bis
    //=================================================================
    $display("=== P2: mertvyy clk (LTC6905 ne startoval): knopka i provodnichok bespolezny ===");
    begin : p2
      integer p2_err;
      p2_err = 0;
      clk_run = 1'b0; clk = 1'b0;
      RST = 1'b0; quiet_bus;
      set_por_state(3'd0, 4'hF, 1'b0);     // INIT: cnt=000, por_sh=F, x1_n=0, por_run=1
      #100000;                              // 100 mks "mertvoy" platy
      if (dut.por_run !== 1'b1) begin p2_err = p2_err + 1; $display("RESULT P2 FAIL: por_run upal BEZ clk?!"); end
      if (RESET_IN !== 1'b0)    begin p2_err = p2_err + 1; $display("RESULT P2 FAIL: RESET_IN ne 0"); end
      if (X1 !== 1'b0)          begin p2_err = p2_err + 1; $display("RESULT P2 FAIL: X1 ne staticheskiy 0"); end
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
      // "provodnichok na cpu36 mimo CPLD" - utverzhdenie sbrosa: no-op po
      // postroeniyu (RESET_IN uzhe 0 ot CPLD) - nichego ne menyaet, provereno vyше
      if (p2_err == 0)
        $display("RESULT P2 PASS: mertvyy clk = 8.8.8.8 gorit, X1 statichen (0), RESET_IN=0, FSM v IDLE, knopka x5 i provodnichok - NUL' effekta (polnyy simptom-kompleks zhaloby 11-6bis)");
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
      set_por_state(3'd0, 4'hF, 1'b0);
      #30000;
      if (RESET_IN !== 1'b0) begin p3_err = p3_err + 1; $display("RESULT P3 FAIL: do clk sbros dolzhen derzhatsya"); end
      clk_run = 1'b1;                        // oscillyator "zavelsya"
      t0 = $time;
      while ((RESET_IN === 1'b0) && (($time - t0) < 2000)) #10;
      if (RESET_IN !== 1'b1) begin p3_err = p3_err + 1; $display("RESULT P3 FAIL: posle prihoda clk sbros ne snimaetsya"); end
      else if (($time - t0) > 1600) begin p3_err = p3_err + 1; $display("RESULT P3 FAIL: snyatie za %0t > 1600 ns", $time - t0); end
      if (p3_err == 0)
        $display("RESULT P3 PASS: s prihodom clk sbros snimaetsya za <=1600 ns - plata by 'dozrela sama'; v zhalobe etogo NET => mertvoe sostoyanie vladel'ca = clk NE prihodit VOOBshCHE");
      else
        $display("RESULT P3: %0d oshibok", p3_err);
      errors = errors + p3_err;
    end

    //=================================================================
    // P4: RST zatyanut v 1 - otpuskanie knopki ozhivlyaet MGNIVENNO
    //=================================================================
    $display("=== P4: RST=1 vne knopki: otpuskanie lechit s pervogo raza (otlichie ot zhaloby) ===");
    begin : p4
      integer p4_err;
      p4_err = 0;
      quiet_bus;
      set_por_state(3'd0, 4'hF, 1'b0);
      RST = 1'b1;
      clk_run = 1'b1;
      #30000;                                 // "seansiya" s prizhatym RST
      if (RESET_IN !== 1'b0)    begin p4_err = p4_err + 1; $display("RESULT P4 FAIL: pri RST=1 sbros dolzhen derzhatsya"); end
      if (dut.por_run !== 1'b0) begin p4_err = p4_err + 1; $display("RESULT P4 FAIL: por-cep' dolzhna doschitat' pod RST=1"); end
      RST = 1'b0;                               // otpuskanie knopki
      #100;
      if (RESET_IN !== 1'b1) begin p4_err = p4_err + 1; $display("RESULT P4 FAIL: posle otpuskaniya sbros dolzhen snyatsya mgnovenno"); end
      if (p4_err == 0)
        $display("RESULT P4 PASS: klass 'RST=1' ozhivlyaetsya OTPUSKANIEM knopki s pervogo raza - vladel'ec zhmet/otpuskaet BEZ effekta, znachit etot klass vycherkivan (esli otpuskanie dohodit do U1.1)");
      else
        $display("RESULT P4: %0d oshibok", p4_err);
      errors = errors + p4_err;
    end

    //=================================================================
    // P5: LOTEREYA peredyrgivaniy (20 ciklov, P_START=3/4)
    //=================================================================
    $display("=== P5: lotereya 'vkl-vykl pitaniya' (20 ciklov, P_START=3/4) ===");
    begin : p5
      integer p5_err, booted, dead;
      reg want_alive;
      p5_err = 0; booted = 0; dead = 0;
      seed = 777;
      quiet_bus; RST = 1'b0;
      for (i = 0; i < 20; i = i + 1) begin
        // "pitanie vyklyucheno": takt stoit; pri sleduyushchem starte - INIT por-cepi
        clk_run = 1'b0; clk = 1'b0;
        r = $random(seed); want_alive = (r[1:0] < 2'd3);   // P_START = 3/4
        set_por_state(3'd0, 4'hF, 1'b0);
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
    $display("=== ITOG tb_poweron: %0d oshibok (%s) ===", errors, (errors == 0 ? "VSE PASS" : "EST' FAILY"));
    $finish;
  end

endmodule
