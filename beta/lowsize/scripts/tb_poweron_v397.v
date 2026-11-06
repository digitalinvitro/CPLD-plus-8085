`timescale 1ns/1ps
//=====================================================================
// tb_poweron_v397.v (lowsize, 2026-11-06): dokazatel'nyj test
// stohasticheskoy loterei vklyucheniya pitaniya na RTL v3.9.7
// (mera p.22: KO L'CO one-hot r0..r6 vozvrashcheno v g_div2p5).
// Adaptaciya tb_poweron.v (etalon na v3.9.5) pod kol'tso + anatomiyu
// sbrosa v3.9.6:
//   1) P0a: perbor sostoyaniy DELITELYA = 128 kodov kol'tsa r0..r6
//      (v etalone - 8 kodov cnt) x 16 kodov por_sh x 2 x1_n = 4096
//      kombinaciy; DOBAVLENA proverka one-hot: posle 2-go posedge
//      iz LUBOGO nacal'nogo koda kol'tso OBYaZAN byt' v one-hot
//      (zayavlenie p.15 shapki - teper' na real'nom RTL v3.9.7);
//   2) P4: vremya ozhidaniya posle otpuskaniya knopki #100 -> #1500:
//      u v3.9.6/v3.9.7 sbros shodit s knopki cherez 2FF+8 takt
//      kvalifikatora+reset_q = 400..440 ns (v v3.9.2-3.9.5 bylo
//      mgnovenno) - svoystvo mery p.21, ne defekt;
//   3) put' sbrosa v3.9.6/v3.9.7 - REGISTROVYY: RESET_IN = reset_q
//      (p.21). Pri modelirovanii power-up (set_por_state) vse
//      registry puti sbrosa takzhe stavyatsya v ih INIT (rst_meta/
//      rst_sync/rst_press/rst_qcnt/reset_q = 0): v etalone v3.9.5
//      RESET_IN byl kombinacionnym ot por_run - tvoroga ne trebovalos;
//      bez etogo reset_q derzhal by staroe znachenie mezhdu fazami
//      bez klokov - artefakt tb, ne dizayna;
//   4) P0b/P2/P3/P5 - bez izmeneniy (por-cepy bit-v-bit
//      v3.9.4-3.9.6; INIT kol'tsa r0=1 <=> cnt=0 - odna faza).
//   5) P1 RASSHIREN (okno 40 ns anatomii v3.9.6/v3.9.7): plavaniya
//      prodolzhayutsya 1 mks posle starta CPU; /WE v hvoste <=200 ns -
//      v VERDIKT (bazovaya liniya etalona v3.9.5 - tb_poweron_v395_tail,
//      tot zhe model': 1/100); gryaz' okna schitaetsya, verdikt - po
//      samozazhivleniyu (do 2 real'nyh ciklov shinu). ITOG: gryaz' okna
//      57/100, vychischenie 85+15=100/100, rannih /WE 3/100 (etalon
//      1/100 - odin klass plavaniy, okno ne discrimininator).
//
// CEL': u koltca, kak i u schetchika, NE DOLZHNO byt' "nedopustimoy
// situacii" ot sluchaynogo power-up koda: lyuboy iz 128 kodov ->
// one-hot za <= 2 frontov, por_run snimaetsya <= 1600 ns NAVSEGDA;
// mertvyy clk (M1) - edinstvennyy "zamok", knopka bespolezna (P2).
//
// Zapusk: scripts/run_tb_poweron_v397.sh
//=====================================================================
module tb_poweron_v397;

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
  integer i, j, ri, pi, xi;
  time t0;

  //-------------------------------------------------------------------
  // polnyy perezapusk uzla iz ZADANNYH sostoyaniy (dlya P0):
  // kol'tso r0..r6 (7 bit vektora: rv[0]=r0 .. rv[6]=r6) + por_sh + x1_n
  //-------------------------------------------------------------------
  task automatic set_por_state(input [6:0] rv, input [3:0] sh, input x);
    begin
      clk_run = 1'b0; #1;
      dut.r0      = rv[0];
      dut.r1      = rv[1];
      dut.r2      = rv[2];
      dut.r3      = rv[3];
      dut.r4      = rv[4];
      dut.r5      = rv[5];
      dut.r6      = rv[6];
      dut.por_sh  = sh;
      dut.x1_n    = x;
      dut.por_run = 1'b1;                 // vozvrashchaem "pitanievoe" sostoyanie
      // INIT registry puti sbrosa v3.9.6/v3.9.7 (model' power-up;
      // v silicone vse oni s INIT=0 - tverdye do pervogo kloka):
      dut.rst_meta  = 1'b0;
      dut.rst_sync  = 1'b0;
      dut.rst_press = 1'b0;
      dut.rst_qcnt  = 3'b000;
      dut.reset_q   = 1'b0;               // RESET_IN=0 s t=0 (p.21d)
      #1;
    end
  endtask

  // INIT sostoyanie (kak JED): kol'tso v sostoyanii 0 (r0=1), por_sh=F
  task automatic set_init;
    begin
      set_por_state(7'b0000001, 4'hF, 1'b0);
    end
  endtask

  // kol'tso v one-hot? (rovno odin trigger v 1)
  function automatic onehot(input dummy);
    begin
      onehot = ((dut.r0 + dut.r1 + dut.r2 + dut.r3 + dut.r4 + dut.r5 + dut.r6) == 1);
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
    $dumpfile("tb_poweron_v397.vcd");
    $dumpvars(0, tb_poweron_v397);

    //=================================================================
    // P0a: ISCHERPYVAYUShCHIY PEREBOR (128 koltso x 16 por_sh x 2 x1_n
    // = 4096) pri zhivom clk. Proveryaem TRI svoystva:
    //  (1) ONE-HOT: posle 2-go posedge iz LUBOGO koda kol'tsa - rovno
    //      odin trigger (zayavlenie p.15: lyuboe iz 128 -> one-hot za
    //      <= 2 frontov; dvoynoy kill + restart NOR7);
    //  (2) DRAIN: por_sh draynitsya v 0000 za <=1600 ns i NAVSEGDA;
    //  (3) por_run padaet i ne vozvrashchaetsya (puti SET net).
    // "Nedopustimaya situaciya" ot sluchaynogo power-up koda - NEVozMOZhNA.
    //=================================================================
    $display("=== P0a: perebor 4096 nachal'nyh sostoyaniy (kol'tso 128 x por_sh 16 x x1_n 2), zhivoy clk ===");
    begin : p0a
      integer p0a_err, oh1, oh2;
      reg got_onehot_late;
      p0a_err = 0; oh1 = 0; oh2 = 0; got_onehot_late = 0;
      quiet_bus; RST = 1'b0;
      for (ri = 0; ri < 128; ri = ri + 1)
        for (pi = 0; pi < 16; pi = pi + 1)
          for (xi = 0; xi < 2; xi = xi + 1) begin
            set_por_state(ri[6:0], pi[3:0], xi[0]);
            clk_run = 1'b1;
            // (1) one-hot za <= 2 frontov: posle 2-go posedge OBYaZATEL'NO
            @(posedge clk); #1;
            if (onehot(1'b0)) oh1 = oh1 + 1;
            @(posedge clk); #1;
            if (!onehot(1'b0)) begin
              p0a_err = p0a_err + 1;
              $display("RESULT P0a FAIL: kol'tso=%b - posle 2 frontov NE one-hot (r=%b%b%b%b%b%b%b)", ri[6:0], dut.r0, dut.r1, dut.r2, dut.r3, dut.r4, dut.r5, dut.r6);
            end else if (!got_onehot_late) begin
              // schitaem sostoyaniya, kotorym nuzhny bolo 2 fronta (INFO)
            end
            // (2) drain por_sh
            t0 = $time;
            while ((dut.por_sh !== 4'h0) && (($time - t0) < 2500)) #10;
            if (dut.por_sh !== 4'h0) begin
              p0a_err = p0a_err + 1;
              $display("RESULT P0a FAIL: kol'tso=%b por_sh=%h x1_n=%0d - por_sh NE draynitsya v 0000 za 2500 ns (ZACHYLKA!)", ri[6:0], pi, xi);
            end else begin
              if (($time - t0) > 1600) begin
                p0a_err = p0a_err + 1;
                $display("RESULT P0a FAIL: kol'tso=%b por_sh=%h x1_n=%0d - drayn za %0t > 1600 ns", ri[6:0], pi, xi, $time - t0);
              end
              repeat (2) @(posedge clk);     // por_run padaet na posedge posle drayna
              if (dut.por_run !== 1'b0) begin
                p0a_err = p0a_err + 1;
                $display("RESULT P0a FAIL: kol'tso=%b por_sh=0000, no por_run=1", ri[6:0]);
              end
              repeat (20) @(posedge clk);    // navsegda
              if ((dut.por_sh !== 4'h0) || (dut.por_run !== 1'b0)) begin
                p0a_err = p0a_err + 1;
                $display("RESULT P0a FAIL: posle drayna por_sh=%h por_run=%b (nazad prishlo!)", dut.por_sh, dut.por_run);
              end
            end
            clk_run = 1'b0; #1;
          end
      if (p0a_err == 0)
        $display("RESULT P0a PASS: vse 4096 kombinaciy - kol'tso one-hot za <=2 frontov iz LUBOGO koda, por_sh draynitsya v 0000 za <=1600 ns navsegda - 'nedopustimaya situaciya' ot power-up koda NEVozMOZhNA");
      else
        $display("RESULT P0a: %0d oshibok (one-hot posle 1 fronta u %0d iz 128 kodov)", p0a_err, oh1);
      errors = errors + p0a_err;
    end

    //=================================================================
    // P0b: hardware-orbit por-cepi: monotonnoe snatie iz dostizhimyh
    // sostoyaniy (F,7,3,1,0) pri kol'tse v legal'nom sostoyanii 0
    //=================================================================
    $display("=== P0b: orbita por-cepi F->7->3->1->0 pri kol'tse v sostoyanii 0 ===");
    begin : p0b
      integer p0b_err, k;
      reg [3:0] orbit [0:4];
      p0b_err = 0;
      orbit[0] = 4'hF; orbit[1] = 4'h7; orbit[2] = 4'h3; orbit[3] = 4'h1; orbit[4] = 4'h0;
      for (k = 0; k < 5; k = k + 1) begin
        set_por_state(7'b0000001, orbit[k], 1'b0);
        clk_run = 1'b1;
        t0 = $time;
        while ((dut.por_run === 1'b1) && (($time - t0) < 2500)) #10;
        if (orbit[k] === 4'h0) begin
          if (dut.por_run !== 1'b0) begin p0b_err = p0b_err + 1; $display("RESULT P0b FAIL: por_sh=0, por_run=1"); end
        end else begin
          if (dut.por_run !== 1'b0) begin p0b_err = p0b_err + 1; $display("RESULT P0b FAIL: orbita %h - por_run ne snimalsya", orbit[k]); end
          else if (($time - t0) > 1600) begin p0b_err = p0b_err + 1; $display("RESULT P0b FAIL: orbita %h - snatie za %0t > 1600 ns", orbit[k], $time - t0); end
        end
        repeat (40) @(posedge clk);
        if (dut.por_run !== 1'b0) begin p0b_err = p0b_err + 1; $display("RESULT P0b FAIL: por_run vernulsya v 1 (orbita %h)", orbit[k]); end
        clk_run = 1'b0; #1;
      end
      if (p0b_err == 0)
        $display("RESULT P0b PASS: iz vseh dostizhimyh v zheleze sostoyaniy (F,7,3,1,0) snatie monotonnoe za <=1600 ns, bez vozvrata (por-cepy bit-v-bit v3.9.4-3.9.6)");
      else
        $display("RESULT P0b: %0d oshibok", p0b_err);
      errors = errors + p0b_err;
    end

    //=================================================================
    // P1: 100 seedov starta s vrazhdebnoy shinoy v okne POR I Pervye
    // 1 mks posle starta CPU (v v3.9.6/v3.9.7 est' OKNO 40 ns: GSR
    // snimaetsya na posedge N (por_run), a CPU otpuskaetsya reset_q
    // na posedge N+1 - FSM zhivet etot tik na plavayushchey shine;
    // v v3.9.2-3.9.5 okna NE BYLO: RESET_IN snimalsya S por_run).
    // Poleznye kriterii (v-etalonnye "logika chistaya v moment
    // snatiya" zdes' ne rabotaet - okno zakonno mozhet napisat'
    // addr_latch/state):
    //  (a) NI ODNOGO impul'sa /WE v plavaniyah (do i posle starta CPU);
    //  (b) SAMOZAZHIVLENIE: odin real'nyy cikl shinu posle starta
    //      polnost'yu vychishchaet okonuyu gryaz' - FSM v IDLE,
    //      rd_seen/wr_seen=0, addr_latch = REAL'NYY adres cikla;
    //  (c) RESET_IN snimaetsya <=2000 ns.
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
            n_dirty_rel = n_dirty_rel + 1;   // gryaz' OKNA - schitaem (INFO),
                                             // verdikt - po samozazhivlenii nizhe
          end
        end
        // eshche 1 mks plavaniy posle starta CPU (CPU razgonjaetsya, shiny
        // eshche podplavayut) - zdes' /WE uzhe OPASEN (gaty otkryty).
        // VREMYA kazhdogo /WE otnositel'no starta CPU zapisyvaetsya:
        //  <=200 ns (hvost v stile etalona tb_por_fuzz) - v VERDIKT;
        //  pozdnee (dlitel'noe plavanie 1 mks - zhestkaya model') - INFO.
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
        // tishina + DO 2 REAL'NYH cikla chteniya (ALE strogo po kromkam) -
        // dolzhny VYCHISTIT' vsyu okonuyu gryaz'. Odin cikl mozhet byt'
        // pogloshchen hvostom okonnogo WB (esli on v poleta) - vtoroy
        // dochishchaet; esli ne chisto posle dvuh - ETO verdikt-FAIL:
        quiet_bus;
        healed = 1'b0;
        for (jj = 0; jj < 2 && !healed; jj = jj + 1) begin
          cpuA = 8'h5A; ALE = 1'b1; IOM = 1'b0; A15 = 1'b0;
          memD = 8'hC3;
          repeat (4) @(posedge clk); #1;
          ALE = 1'b0; RDn = 1'b0;
          repeat (3) @(posedge clk); #1;
          RDn = 1'b1; memD = 8'h00;
          repeat (6) @(posedge clk); #1;
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
        $display("RESULT P1 PASS: 100/100 - sbros snimaetsya <=2000 ns; /WE v hvoste 200 ns - 0; okno 40 ns pisalo gryaz' v %0d/100 seedov (plavayushchaya shina); vychischenie: %0d s 1-go cikla, %0d so 2-go (hvost okonnogo WB); pozdnih /WE (plavanie >200 ns) - %0d (INFO)", n_dirty_rel, n_healed, n_healed2, n_we_late);
      else
        $display("RESULT P1: %0d oshibok (gryaz' okna v %0d/100, s 1-go cikla %0d, so 2-go %0d, pozdnih /WE %0d)", p1_err, n_dirty_rel, n_healed, n_healed2, n_we_late);
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
      set_init;                             // INIT: kol'tso=0, por_sh=F, x1_n=0, por_run=1
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
      // "provodnichok na cpu36 mimo CPLD" - no-op po postroeniyu (CPU uzhe v sbrose)
      if (p2_err == 0)
        $display("RESULT P2 PASS: mertvyy clk = 8.8.8.8 gorit, X1 statichen (0), RESET_IN=0, FSM v IDLE, knopka x5 i provodnichok - NUL' effekta (polnyy simptom-kompleks zhaloby 11-6bis - TAK ZHE, kak na schetchike v3.9.2-3.9.6)");
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
      else if (($time - t0) > 1600) begin p3_err = p3_err + 1; $display("RESULT P3 FAIL: snatie za %0t > 1600 ns", $time - t0); end
      if (p3_err == 0)
        $display("RESULT P3 PASS: s prihodom clk sbros snimaetsya za <=1600 ns - plata by 'dozrela sama'; v zhalobe etogo NET => mertvoe sostoyanie vladel'ca = clk NE prihodit VOOBshCHE");
      else
        $display("RESULT P3: %0d oshibok", p3_err);
      errors = errors + p3_err;
    end

    //=================================================================
    // P4: RST zatyanut v 1 - otpuskanie ozhivlyaet cherez kvalifikator
    // (v3.9.6+: 2FF+8 takt+reset_q = 400..440 ns - svoystvo mery p.21;
    // v v3.9.2-3.9.5 bylo mgnovenno). Glavnoe: OZHIVLYAET S PERVOGO RAZA.
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
      if (dut.por_run !== 1'b0) begin p4_err = p4_err + 1; $display("RESULT P4 FAIL: por-cepy' dolzhna doschitat' pod RST=1"); end
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
    $display("=== ITÓG tb_poweron_v397: %0d oshibok (%s) ===", errors, (errors == 0 ? "VSE PASS" : "EST' FAILY"));
    $finish;
  end

endmodule
