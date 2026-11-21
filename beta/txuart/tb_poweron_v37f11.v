// tb_poweron_v37f11.v (txuart, 2026-11-21): regress tb sbrosa + TXUART dlya
// top_txuart_por6_v37f11.v. Baza - tb_poweron_v35.v (VARIANT A, Icarus 12.0).
// Adaptatsiya pod v37F-11:
//   - CS1/READY - VhODY (v37F: output->input, vneshnie 10K) - tb zhmyhaet '1';
//   - rst_qcnt/rst_cnt SLITY v odin schetchik rst_win (p.35a) - set_reset_state
//     i cheki P0/P0b/P5 dvigayut dut.rst_win; reset_q -> dut.RESET_IN (v37F-2);
//   - okna P1/P3 pereschitany: snyatie = 1280 (perekvalifikatsiya) + 2560
//     (polka) + faza <= 320 + sinkhro <= 80 -> [3700..4500] ot otpuskaniya;
//   - NOVYE cheki T1-T4 (kontur ld_tx_q -> kombinatsionnyy uzel io_wr_tx,
//     p.30a): kadry na zhivyh A-pinah, LSB pervyy, odnokratnost' (zapis pri
//     busy otbrasyvaetsya), perevzvod TXRDY, stop='1' PRI d7=1 (0xFF - lovit
//     toggovuyu anomaliju bita 8); vse izmeneniya shiny - na negedge clk.
// Pervoocherednoy chek sliyaniya schetchikov - P0 (POR po 8 frontov CLKOUT),
// P0b (mertvyy CLKOUT), P1/P2/P3 (k hopka/glitch/perevzvod), P5 (mertvyy clk).
// Kommentarii - ASCII-translit (CP1251-bezopasno).
//
// Model' CPU: CLKOUT = X1/2 (delitel' /2 vnutri VM85A) - period 320 ns.
// Shinnyy tsikl zapisi: ALE 1 tak CPU (320 ns, adres na A) -> T2: dannye na
// A-setyah (multipleks), WRn nizh 2 takta (640 ns) -> WB CPLD -> IDLE.
//
// Cheki:
//   P0  POR pri zhivom CLKOUT: INIT -> RESET_IN podnimaetsya POSLE 8-go
//       fronta; okno [2200..3200] ns; rst_win posle snyatiya = 000 (rovno 8);
//   P0b MERTVYY CLKOUT (statichnyy 0 i 1) - RESET_IN NE podnimaetsya NIKOGDA;
//       vozvrat zhivogo - snyatie v okne (zachylka obratima);
//   P1  KNOPKA: vzvod [1200..1520] ns (2FF + 8 por_ce + vyvod), uderzhanie,
//       snyatie [3700..4500] ns ot otpuskaniya (1280 perekvalifikatsiya +
//       2560 polka + faza + sinkhro);
//   P2  GLITCH 500 ns (< 1280 kvalifikatora) - RESET_IN ne padaet;
//   P3  POVTORNY VZVOD + 10 mks pokoya - ni odnogo peresbrossa;
//   P4  ni odnogo pulsa /WE v okne polki (fuzz vrazhdebnoy shiny);
//   P5  MERTVYY clk 25 MGc: schet zamerza (rst_win=001 stoit);
//   P6  KOROTKOE nazhatie 1600 ns (perevorot NADEZHNO v okne [1200..1520],
//       derzhanie korotkoe): polnyy tsikl sbrosa - vetka rst_press=1 v okne
//       kvalifikatsii SNIYATIYA derzhit RESET_IN=0 (ugol (d) p.35a);
//   T1  OUT 04h 55h: kadr 8N1 (start 1000 ns, d0..d7 LSB pervyy, stop,
//       idle); zapis 04h AAh SEREDINU kadra - OTBRASYVAETSYA (tx_idle=0),
//       kadr 55h doigrivaetsya bez iskazheniy i bez restarta;
//   T2  OUT 07h (snd) - TX NE zagruzhaetsya (dekod tol'ko 04h);
//   T3  OUT 04h FFh posle busy - perevzvod TXRDY; stop='1' PRI d7=1
//       (inzhektsiya '1', NE toggan anomaliya bita 8).

`timescale 1ns/1ps

module tb_poweron_v37f11;

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
  wire X1, RESET_IN, WE_n, CS_n, RST75, TX, SND, SID, OEr_n, OE_n, X2;
  wire CSr_n, CS1, READY;   // CS1/READY - vhody DUT (v37F): drayvyaetsya nizhe
  wire [7:0] seg;
  wire [3:0] dig;
  wire col0, col1, col2, col3;

  assign (weak0, weak1) A = cpuA;
  assign (weak0, weak1) D = memD;

  retro_pcld_top dut (
    .clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(A), .D(D),
    .CSr_n(CSr_n), .OEr_n(OEr_n), .CS_n(CS_n), .OE_n(OE_n), .WE_n(WE_n),
    .CS1(1'b1),                                   // v37F: vhod (vneshnyaya 10K)
    .X1(X1),
    .READY(1'b1),                                 // v37F: vhod (wait-zaprescheny)
    .RESET_IN(RESET_IN),
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
  // v37F-11: odin schetchik rst_win (kvalifikator + polka); RESET_IN - sam
  // registr (v37F-2); sinkhronizatora CLKOUT net (clk/8, fazovo stabilen).
  task automatic set_reset_state(input [2:0] cnt, input rq);
    begin
      dut.rst_win     = cnt;
      dut.RESET_IN    = rq;
      dut.clkout_d    = CLKOUT;
      dut.rst_meta    = 1'b0;
      dut.rst_sync    = 1'b0;
      dut.rst_press   = 1'b0;
    end
  endtask

  //-------------------------------------------------------------------
  // SHINNYY TSIKL ZAPISI v port (model' CPU; vse izmeneniya na negedge clk -
  // DUT sampliruet na posedge - bez gonok): ALE 8 negedgov = 320 ns s adresom
  // na A; T2: dannye na A-setyah + WRn nizh 16 negedgov = 640 ns; WB CPLD.
  //-------------------------------------------------------------------
  task automatic io_write(input [7:0] addr, input [7:0] b);
    begin
      @(negedge clk); cpuA = addr; IOM = 1'b1;
      @(negedge clk); ALE = 1'b1;
      repeat (8) @(negedge clk);                 // T1H: adres zapischelkan
      @(negedge clk); begin ALE = 1'b0; cpuA = b; WRn = 1'b0; end  // T2
      repeat (16) @(negedge clk);                // WRn nizh 640 ns
      @(negedge clk); WRn = 1'b1;                // zapis zavershena
      repeat (8) @(negedge clk);                 // WB1..WB4 + zapas
      @(negedge clk); begin IOM = 1'b0; cpuA = 8'h00; end
      repeat (2) @(negedge clk);
    end
  endtask

  // Proverka kadra 8N1: start 1000 ns, d0..d7 (LSB pervyy) po 1000 ns,
  // stop='1' (VSEGDA - inzhektsiya '1'), idle='1'. Semply - v seredinakh
  // bit-taymov (t0+500+1000k - vne krontov, bez gonok).
  task automatic check_frame(input [7:0] b, input [8*8-1:0] tag);
    integer k;
    realtime t0, tw;
    reg exp;
    begin
      @(negedge TX);                             // registr front start-bita
      t0 = $realtime;
      @(posedge TX);                             // konets starta
      tw = $realtime - t0;
      if (tw < 940.0 || tw > 1060.0) begin
        errors = errors + 1;
        $display("RESULT %0s FAIL: shirina start-bita %0t ns (norma 1000)", tag, tw);
      end
      for (k = 0; k < 8; k = k + 1) begin
        #(500.0);                                // seredina d_k
        exp = b[k];
        if (TX !== exp) begin
          errors = errors + 1;
          $display("RESULT %0s FAIL: bit d%0d=%b (ozhidalos %b) na %0t ns ot starta", tag, k, TX, exp, $realtime - t0);
        end
        #(500.0);
      end
      #(500.0);                                  // seredina stopa
      if (TX !== 1'b1) begin
        errors = errors + 1;
        $display("RESULT %0s FAIL: stop=%b (dolzhen byt '1' VSEGDA - inzhektsiya '1', ne toggnutaya!)", tag, TX);
      end
      #(1000.0);                                 // idle za stopom
      if (TX !== 1'b1) begin
        errors = errors + 1;
        $display("RESULT %0s FAIL: posle kadra TX=%b (idle '1')", tag, TX);
      end
    end
  endtask

  initial begin
    $dumpfile("tb_poweron_v37f11.vcd");
    $dumpvars(0, tb_poweron_v37f11);

    //=================================================================
    // P0: POR pri zhivom CLKOUT - snyatie po 8-mu frontu
    //=================================================================
    $display("=== P0: POR (INIT), CLKOUT zhivoy (X1/2, 320 ns), snyatie po 8-mu frontu ===");
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
      end else if (dut.rst_win !== 3'b000) begin
        errors = errors + 1;
        $display("RESULT P0 FAIL: rst_win=%b posle snyatiya - schet NE rovno 8 frontov", dut.rst_win);
      end else if (logic_dirt(1'b0)) begin
        errors = errors + 1;
        $display("RESULT P0 FAIL: logika ISPAChANA vrazhdebnoy shinoy v okne polki");
      end else
        $display("RESULT P0 PASS: RESET_IN niz %0t ns (polka 2560, norma >= 960); rst_win=000 (rovno 8 frontov); logika chista", t_rise);
    end

    //=================================================================
    // P0b: MERTVYY CLKOUT - zachylka OZHIDAEMA
    //=================================================================
    $display("=== P0b: CLKOUT mertvyy (0 i 1) - RESET_IN NE podnimaetsya; vozvrat zhivogo - snyatie ===");
    begin : p0b
      realtime t0, t_rise;
      clkout_live;
      wait (CLKOUT === 1'b0);
      set_reset_state(3'b000, 1'b0);
      clkout_dead(1'b0);
      #5000;
      if (RESET_IN !== 1'b0 || dut.rst_win !== 3'b000) begin
        errors = errors + 1;
        $display("RESULT P0b FAIL: pri mertvom CLKOUT=0 RESET_IN=%b rst_win=%b - zachylka NE chistaya", RESET_IN, dut.rst_win);
      end
      clkout_live;
      wait (CLKOUT === 1'b1);
      set_reset_state(3'b000, 1'b0);
      clkout_dead(1'b1);
      #5000;
      if (RESET_IN !== 1'b0 || dut.rst_win !== 3'b000) begin
        errors = errors + 1;
        $display("RESULT P0b FAIL: pri mertvom CLKOUT=1 RESET_IN=%b rst_win=%b", RESET_IN, dut.rst_win);
      end
      t0 = $realtime;
      clkout_live;
      @(posedge RESET_IN);
      t_rise = $realtime - t0;
      if (t_rise < 2200.0 || t_rise > 3200.0) begin
        errors = errors + 1;
        $display("RESULT P0b FAIL: posle vozvrata CLKOUT snyatie cherez %0t (okno [2200..3200])", t_rise);
      end else
        $display("RESULT P0b PASS: mertvyy CLKOUT (0 i 1) - schet zamerza; vozvrat zhivogo - snyatie cherez %0t (zachylka obratima)", t_rise);
    end

    //=================================================================
    // P1: KNOPKA - vzvod [1200..1520], uderzhanie 2000 ns, snyatie polkoy
    //=================================================================
    $display("=== P1: knopka RST - vzvod <= 1.52 mks, uderzhanie, snyatie 1280 perekvalifikatsiya + 2560 polka ===");
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
        $display("RESULT P1 FAIL: RESET_IN padaet cherez %0t ns (okno [1200..1520]: 2FF + 8 por_ce + vyvod)", t_fall);
      end
      // model': perekvalifikatsiya snyatiya 1280 + [0..160] + polka 2560 +
      // faza pervogo fronta [0..320] + sinkhro <= 80
      if (t_rise < 3700.0 || t_rise > 4500.0) begin
        errors = errors + 1;
        $display("RESULT P1 FAIL: snyatie cherez %0t ns posle OTPUSKANIYA (okno [3700..4500])", t_rise);
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
      if (t_rise < 3700.0 || t_rise > 4500.0) begin
        errors = errors + 1;
        $display("RESULT P3 FAIL: vtoroy tsikl - snyatie cherez %0t posle otpuskaniya (okno [3700..4500])", t_rise);
      end
      t0 = $realtime;
      while (($realtime - t0) < 10000.0 && RESET_IN === 1'b1) #100;
      if (RESET_IN !== 1'b1) begin
        errors = errors + 1;
        $display("RESULT P3 FAIL: za 10 mks pokoya RESET_IN upal - samoproizvol'nyy peresbross");
      end else if (t_rise >= 3700.0 && t_rise <= 4500.0)
        $display("RESULT P3 PASS: povtornyy vzvod rabotaet (snyatie %0t posle otpuskaniya), 10 mks pokoya - ni odnogo peresbrossa", t_rise);
    end

    //=================================================================
    // P6: KOROTKOE nazhatie 1600 ns - perevorot NADEZHNO sostoyalsya
    // ([1200..1520]), derzhanie korotkoe: polnyy tsikl sbrosa (ugol (d)
    // p.35a: vetka rst_press=1 v okne perekvalifikatsii derzhit sbros)
    //=================================================================
    $display("=== P6: korotkoe nazhatie 1600 ns - sbros VSYO RAVNO polnyy (vetka rst_press=1 derzhit RESET_IN=0) ===");
    begin : p6
      realtime t0, t_fall, tr, t_rise;
      t0 = $realtime;
      RST = 1'b1;
      @(negedge RESET_IN);
      t_fall = $realtime - t0;
      #1600;                               // korotkoe derzhanie posle perevorota
      RST = 1'b0;
      tr = $realtime;
      @(posedge RESET_IN);
      t_rise = $realtime - tr;
      if (t_fall < 1200.0 || t_fall > 1520.0) begin
        errors = errors + 1;
        $display("RESULT P6 FAIL: vzvod cherez %0t ns - perevorot ne sostoyalsya v okne", t_fall);
      end
      if (t_rise < 3700.0 || t_rise > 4500.0) begin
        errors = errors + 1;
        $display("RESULT P6 FAIL: snyatie cherez %0t posle otpuskaniya (okno [3700..4500]) - korotkoe nazhatie NE dalo polnyy tsikl", t_rise);
      end else if (t_fall >= 1200.0 && t_fall <= 1520.0 && t_rise >= 3700.0 && t_rise <= 4500.0)
        $display("RESULT P6 PASS: korotkoe nazhatie 1600 ns dalo polnyy tsikl (vzvod %0t, snyatie %0t)", t_fall, t_rise);
    end

    //=================================================================
    // T1: kadr 0x55 + zapis pri busy otbrasyvaetsya (kontrakt p.30a)
    //=================================================================
    $display("=== T1: OUT 04h 55h - kadr 8N1 LSB pervyy; OUT 04h AAh serediny kadra - otbrasyvaetsya ===");
    quiet_bus;
    begin : t1
      realtime t0;
      integer errs0;
      errs0 = errors;
      fork
        io_write(8'h04, 8'h55);          // tsikl zapisi - KADR STARTUET VNUTRI nego
        begin
          @(negedge TX);                 // registr front start-bita (vo vremya tsikla)
          t0 = $realtime;
          #2500.0;                       // seredina kadra (~d1.5)
          io_write(8'h04, 8'hAA);        // zapis pri busy - DOLZHNA otbrasyvatsya
          #(5500.0 - ($realtime - t0));  // seredina d4
          if (TX !== 1'b1) begin         // 55h: bit4=1; 0xAA daval by 0
            errors = errors + 1;
            $display("RESULT T1 FAIL: d4=%b - zapis pri busy ISKAZILA kadr (ozhidalos 1 ot 55h)", TX);
          end
          #(1000.0);                     // seredina d5
          if (TX !== 1'b0) begin         // 55h: bit5=0; 0xAA daval by 1
            errors = errors + 1;
            $display("RESULT T1 FAIL: d5=%b - zapis pri busy ISKAZILA kadr (ozhidalos 0 ot 55h)", TX);
          end
          #(1000.0);                     // seredina d6
          if (TX !== 1'b1) begin
            errors = errors + 1;
            $display("RESULT T1 FAIL: d6=%b (ozhidalos 1 ot 55h)", TX);
          end
          #(1000.0);                     // seredina d7
          if (TX !== 1'b0) begin
            errors = errors + 1;
            $display("RESULT T1 FAIL: d7=%b (ozhidalos 0 ot 55h)", TX);
          end
          #(1000.0);                     // seredina stopa
          if (TX !== 1'b1) begin
            errors = errors + 1;
            $display("RESULT T1 FAIL: stop=%b (ozhidalos 1)", TX);
          end
          #(1000.0);                     // idle
          if (TX !== 1'b1) begin
            errors = errors + 1;
            $display("RESULT T1 FAIL: posle kadra TX=%b (idle '1')", TX);
          end
          // bez restarta: 3 mks TX='1' (AAh otbrasen)
          begin : t1q
            realtime tq;
            tq = $realtime;
            while (($realtime - tq) < 3000.0 && TX === 1'b1) #50;
            if (TX !== 1'b1) begin
              errors = errors + 1;
              $display("RESULT T1 FAIL: novyy start posle kadra - zapis pri busy PROSHELA");
            end
          end
        end
      join
      if (errors == errs0)
        $display("RESULT T1 PASS: kadr 55h chistyy (d4/d5/d6/d7/stop/idle), zapis AAh pri busy otbrasivaetsya, restarta net");
      else
        $display("RESULT T1 FAIL: kadr/drop-test s razryvami (sm. vyshe)");
    end

    //=================================================================
    // T2: OUT 07h - TX NE zagruzhaetsya (dekod tol'ko 04h)
    //=================================================================
    $display("=== T2: OUT 07h (snd) - TX dolzhen ostat'sya idle '1' ===");
    begin : t2
      realtime t0;
      io_write(8'h07, 8'h00);
      t0 = $realtime;
      while (($realtime - t0) < 3000.0 && TX === 1'b1) #50;
      if (TX !== 1'b1) begin
        errors = errors + 1;
        $display("RESULT T2 FAIL: TX upal posle zapisi v 07h - dekod portov POVREZHDEN");
      end else
        $display("RESULT T2 PASS: zapisi v 07h ne zagruzhayut TX (dekod 04h tol'ko)");
    end

    //=================================================================
    // T3: perevzvod TXRDY + kadr 0xFF - stop='1' PRI d7=1 (inzhektsiya
    // '1'; togglnaya anomaliya bita 8 dala by stop=!d7=0)
    //=================================================================
    $display("=== T3: OUT 04h FFh - perevzvod TXRDY, stop='1' pri d7=1 ===");
    begin : t3
      integer errs0;
      errs0 = errors;
      fork
        io_write(8'h04, 8'hFF);          // kadr FFh - start vnutri tsikla
        check_frame(8'hFF, "T3");        // start semepliruetsya iz paralleli
      join
      if (errors == errs0)
        $display("RESULT T3 PASS: kadr FFh chistyy (vse 8 bitov '1', stop '1') - inzhektsiya '1' podtverzhdena, perevzvod rabotaet");
      else
        $display("RESULT T3 FAIL: kadr FFh s razryvami (sm. vyshe)");
    end

    //=================================================================
    // P5: MERTVYY clk 25 MGc - schet zamerza
    //=================================================================
    $display("=== P5: stop clk 25 MGc v polke - schet zamerza, vsyo stoit ===");
    begin : p5
      set_reset_state(3'b001, 1'b0);       // 1 front uzhe poschitan
      clk_run = 1'b0;                      // takta CPLD net - zamerzaet VSYO
      #1000;
      if (dut.rst_win !== 3'b001 || RESET_IN !== 1'b0) begin
        errors = errors + 1;
        $display("RESULT P5 FAIL: bez clk rst_win=%b RESET_IN=%b - schet/shina zhivut bez takta", dut.rst_win, RESET_IN);
      end else begin
        clk_run = 1'b1;
        @(posedge RESET_IN);
        $display("RESULT P5 PASS: bez clk schet zamerza (rst_win=001 stoit), posle vozvrata - snyatie po 8-mu frontu");
      end
    end

    quiet_bus;
    $display("ITOGE: %0d oshibok", errors);
    if (errors == 0) $display("RESULT ITGAME PASS: v37F-11 podtverzhden (sliyanie schetchikov p.35a: POR/mertvyy CLKOUT/knopka/glitch/povtor/korotkoe nazhatie/mertvyy clk; p.30a: kadry/odnokratnost'/perevzvod/stop pri d7=1)");
    else             $display("RESULT ITGAME FAIL: v37F-11 IMEET %0d RAZRYVOV", errors);
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
