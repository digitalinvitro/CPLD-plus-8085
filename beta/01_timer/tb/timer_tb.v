//=====================================================================
// timer_tb.v Ч тестбенч beta/01_timer: интервальный таймер -> RST 7.5.
// «апуск: ISim (ISE 14.7, Add Source -> этот файл + top_suart.v р€дом,
// top_suart.v = Top ModuleSimulation) или iverilog:
//   iverilog -o tb timer_tb.v top_suart.v && vvp tb
//
// „“ќ ѕ–ќ¬≈–я≈“ (квант тика = 256 x 200 нс = 51,2 мкс при CLK_DIV=5):
//  T0: во врем€ сброса (RST/POR) RST75 = 0 Ч ложного фронта нет;
//  T1: инициализаци€: счЄтчик INIT = FFh -> без OUT 04h первый фронт
//      RST75 через 255 тиков = 13056000 нс от сн€ти€ cpu_rst;
//  T2: стоп-в-нуле: без ре-арма уровень RST75 держитс€ (счЄт стоит);
//  T3: OUT 04h, N=195 -> фронт RST75 через 195 тиков = 9984000 нс
//      (допуск +-1 тик 51200 нс = фаза прескалера относительно загрузки);
//  T4: ре-арм из "ISR" (OUT 04h,195 через 2 мкс после фронта) ->
//      следующий фронт снова через ~9984000 нс Ч периодичность;
//  T5: уровень RST75 снимаетс€ загрузкой N!=0 (дл€ защЄлки CPU важен
//      только фронт Ч длительность уровн€ не критична).
//=====================================================================
`timescale 1ns / 1ps

module timer_tb;

  // ---- такт 25 ћ√ц (период 40 нс) ----
  reg clk = 1'b0;
  always #20 clk = ~clk;

  // ---- CLK OUT CPU (2,5 ћ√ц, P83) Ч в beta/01_timer не используетс€, но порт есть ----
  reg clkout_r = 1'b0;
  always #200 clkout_r = ~clkout_r;

  // ---- стимулы шины ----
  reg       RST = 1'b1;          // старт в сбросе; POR дотикает сам (12,8 мкс)
  reg       ALE = 1'b0;
  reg       WRn = 1'b1;
  reg       RDn = 1'b1;
  reg       IOM = 1'b0;
  reg       A15 = 1'b0;

  // ---- AD-шина: tb управл€ет только внутри io_write ----
  reg  [7:0] a_drv = 8'h00;
  reg        a_oe  = 1'b0;
  wire [7:0] A = a_oe ? a_drv : 8'bZZZZZZZZ;
  wire [7:0] D;                   // tb D не драйвит (CPLD драйвит только в writeback)

  // ---- выходы DUT ----
  wire        CSr_n, OEr_n, CS_n, OE_n, WE_n, CS1;
  wire        X1, READY, RESET_IN, SID, TX, SND, RST75;
  wire [7:0]  seg;
  wire [3:0]  dig;
  wire        col0, col1, col2, col3;

  retro_pcld_top dut (
    .clk(clk), .RST(RST),
    .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(A), .D(D),
    .CSr_n(CSr_n), .OEr_n(OEr_n), .CS_n(CS_n), .OE_n(OE_n), .WE_n(WE_n), .CS1(CS1),
    .X1(X1), .READY(READY), .RESET_IN(RESET_IN), .RST75(RST75),
    .SID(SID), .TX(TX),
    .seg(seg), .dig(dig), .SND(SND),
    .X2(1'b0), .RSTOUT(1'b0), .SOD(1'b1), .INTAn(1'b1), .HLDA(1'b0),
    .CLKOUT(clkout_r), .S0(1'b0), .S1(1'b0),
    .AH8(1'b0), .AH9(1'b0), .AH10(1'b0), .AH11(1'b0), .AH12(1'b0), .AH13(1'b0), .AH14(1'b0),
    .RX(1'b0),
    .col0(col0), .col1(col1), .col2(col2), .col3(col3),
    .row0(1'b0), .row1(1'b0), .row2(1'b0), .row3(1'b0), .row4(1'b0)
  );

  //---- запись в порт (протокол: T1H = ALE+адрес, T2 = WR#+IOM+данные) ----
  task io_write(input [7:0] addr, input [7:0] data);
    begin
      @(negedge clk);
      a_drv = addr;  a_oe = 1'b1;  IOM = 1'b1;  ALE = 1'b1;
      @(negedge clk);                                  // posedge между: захват addr_latch (T1H && ALE)
      @(negedge clk);
      a_drv = data;  ALE = 1'b0;  WRn = 1'b0;
      @(negedge clk);                                  // posedge между: захват bus_reg (tmr_cnt Ч тактом позже через tmr_load_q)
      @(negedge clk);                                  // запас на трекинг строба
      WRn = 1'b1;
      IOM = 1'b0;    a_oe = 1'b0;
      @(negedge clk); @(negedge clk);                  // автомат досидел до IDLE
    end
  endtask

  //---- счЄтчик ошибок и моменты фронтов ----
  integer errors = 0;
  time   t_release, t_rise1, t_rise2, t_rise3, t_rearm;

  initial begin
    $display("=== beta/01_timer tb: старт (квант 51200 нс, CLK_DIV=5) ===");

    // ---------- T0: сброс ----------
    #1000;
    RST = 1'b0;                        // SW20 отпущена; cpu_rst сниметс€ вместе с POR
    wait (RESET_IN === 1'b1);          // RESET IN# подн€лс€ = cpu_rst сн€т
    t_release = $time;
    $display("cpu_rst сн€т при t=%0t", t_release);
    if (RST75 !== 1'b0) begin
      errors = errors + 1; $display("FAIL T0: RST75 != 0 в сбросе/сразу после (t=%0t)", $time);
    end else
      $display("OK   T0: RST75=0 в сбросе (ложного фронта нет)");

    // ---------- T1: INIT FFh -> первый фронт без OUT через 255 тиков ----------
    fork : t1_blk
      begin
        wait (RST75 === 1'b1);
        t_rise1 = $time;
        disable t1_blk;
      end
      begin
        #1600000;                      // таймаут 1,6 мс > ожидаемых 1305,6 мкс
        $display("FAIL T1: фронт RST75 не пришЄл за 1,6 мс (ожидалс€ ~1305,6 мкс от cpu_rst)");
        errors = errors + 1;
        disable t1_blk;
      end
    join
    if (t_rise1 >= t_release + 13056000 - 51200 && t_rise1 <= t_release + 13056000 + 51200)
      $display("OK   T1: INIT-фронт RST75 через %0d нс от cpu_rst (ожидание 13056000 +-51200)", t_rise1 - t_release);
    else begin
      errors = errors + 1;
      $display("FAIL T1: INIT-фронт через %0d нс, ожидалось 13056000 +-51200", t_rise1 - t_release);
    end

    // ---------- T2: стоп-в-нуле (ре-арма нет -> уровень держитс€) ----------
    #200000;                           // 200 мкс >> тика 51,2 мкс
    if (RST75 !== 1'b1) begin
      errors = errors + 1; $display("FAIL T2: RST75 упал без ре-арма (счЄтчик не должен был тронутьс€)");
    end else
      $display("OK   T2: стоп-в-нуле подтверждЄн (уровень держитс€ 200 мкс)");

    // ---------- T3: OUT 04h, N=195 -> фронт через 195 тиков ----------
    if (RST75 !== 1'b1) begin
      errors = errors + 1; $display("FAIL T3pre: перед ре-армом RST75 должен быть '1'");
    end
    io_write(8'h04, 8'd195);           // "ISR": ре-арм
    t_rearm = $time;
    if (RST75 !== 1'b0) begin
      errors = errors + 1; $display("FAIL T5a: RST75 не сн€лс€ загрузкой N!=0");
    end else
      $display("OK   T5a: уровень сн€т ре-армом (длительность = от фронта до OUT 04h)");

    fork : t3_blk
      begin
        wait (RST75 === 1'b1);
        t_rise2 = $time;
        disable t3_blk;
      end
      begin
        #1200000;                      // таймаут 1,2 мс > ожидаемых ~998,4 мкс
        $display("FAIL T3: фронт не пришЄл за 1,2 мс (ожидалс€ 998,4 мкс)");
        errors = errors + 1;
        disable t3_blk;
      end
    join
    if (t_rise2 >= t_rearm + 195*51200 - 51200 && t_rise2 <= t_rearm + 195*51200 + 51200)
      $display("OK   T3: фронт через %0d нс после OUT (ожидание %0d +-51200)", t_rise2 - t_rearm, 195*51200);
    else begin
      errors = errors + 1;
      $display("FAIL T3: фронт через %0d нс, ожидалось %0d +-51200", t_rise2 - t_rearm, 195*51200);
    end

    // ---------- T4: периодичность (ре-арм каждый "ISR") ----------
    #2000;                             // пролог "ISR" 2 мкс Ч уровень всЄ ещЄ высок
    io_write(8'h04, 8'd195);
    t_rearm = $time;
    fork : t4_blk
      begin
        wait (RST75 === 1'b1);
        t_rise3 = $time;
        disable t4_blk;
      end
      begin
        #1200000;
        $display("FAIL T4: второго фронта нет");
        errors = errors + 1;
        disable t4_blk;
      end
    join
    if (t_rise3 >= t_rearm + 195*51200 - 51200 && t_rise3 <= t_rearm + 195*51200 + 51200)
      $display("OK   T4: период фронт-к-фронту %0d нс (~10 мс; 50 √ц = деление на 2 в ISR)", t_rise3 - t_rise2);
    else begin
      errors = errors + 1;
      $display("FAIL T4: период %0d нс вне допуска %0d +-51200", t_rise3 - t_rise2, 195*51200);
    end

    // ---------- T5: повторный ре-арм снова снимает уровень ----------
    #2000;
    io_write(8'h04, 8'd195);
    if (RST75 !== 1'b0) begin
      errors = errors + 1; $display("FAIL T5b: RST75 не сн€лс€ вторым ре-армом");
    end else
      $display("OK   T5b: уровень сн€т вторым ре-армом");

    // ---------- вердикт ----------
    if (errors == 0)
      $display("=== ¬—≈ ѕ–ќ¬≈– » ѕ–ќ…ƒ≈Ќџ (beta/01_timer) ===");
    else
      $display("=== ѕ–ќ¬јЋ≈Ќќ ѕ–ќ¬≈–ќ : %0d ===", errors);
    $finish;
  end

  // страховка от зависани€
  initial begin
    #5000000;                          // предел симул€ции 5 мс
    $display("FAIL TIMEGUARD: симул€ци€ превысила 5 мс");
    $finish;
  end

endmodule
