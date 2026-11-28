`timescale 1ns/1ps
//=====================================================================
// tb_txuart_compact: TXUART_OLD (v39G08 v1) vs TXUART_CLKOUT_RALL
// (v39G08 v2, компактный) на общем стимуле.
// Декодеры кадров ПОЛНОСТЬЮ СИНХРОННЫЕ (без #delay внутри триггера -
// в Verilog процесс пропускает фронты, пока его тело занято): счётчик
// клков от фронта busy (= загрузка кадра), выборки в середине битов,
// закрытие на 230-м клке (< мин. паузы 9400нс между кадрами).
// Проверки:
//  1) старт=0, стоп=1, байты = стимулу, old==new, число кадров = числу
//     принятых записей;
//  2) запись при busy игнорируется (нет фронта busy - нет кадра);
//  3) запись в клк снятия busy (строб семплируется в клке E9, busy ещё
//     1 перед фронтом) - ОБА отбрасывают;
//  4) запись сразу после снятия busy обоих - ОБА принимают;
//  5) busy_new поднимается ровно на 1 клк позже busy_old (load_q),
//     busy_new никогда не падает РАНЬШЕ busy_old (известное отличие
//     v1: при din с единицами в старших битах busy_old падает раньше
//     конца кадра - v2 держит busy весь кадр);
//  6) кадр 0x00 держит busy весь кадр (обоих);
//  7) период baud_tick = 24 клка;
//  8) фазы CLKOUT 0 и 3.
//=====================================================================
// Заглушки глобальных буферов Xilinx (для компиляции retro_pcld_top)
module BUFGSR(input wire I, output wire O); assign O = I; endmodule
module BUFG  (input wire I, output wire O); assign O = I; endmodule

module tb_txuart;

  localparam TCLK = 40;                  // 25 МГц
  localparam TBIT = 960;                 // 1.0417 Мбод = 24 клка

  reg clk = 0, rst = 1;
  always #(TCLK/2) clk = ~clk;

  reg  [2:0] ph_cnt = 3'd0;
  reg  [1:0] phase  = 2'd0;              // фаза CLKOUT относительно clk
  wire [2:0] ph_plus = ph_cnt + {1'b0, phase};
  wire clkout = ph_plus[2];              // 3.125 МГц, период 8 клков

  always @(posedge clk or posedge rst)
    if (rst) ph_cnt <= 3'd0; else ph_cnt <= ph_cnt + 3'd1;

  reg wr_en = 0;
  reg [7:0] din = 8'h00;

  wire tx_o, tx_n, bsy_o, bsy_n, bt_o, bt_n;

  TXUART_OLD        u_old (.clk(clk), .gsr(rst), .clkout_in(clkout),
                           .wr_en(wr_en), .din(din),
                           .tx_out(tx_o), .tx_busy(bsy_o), .baud_tick(bt_o));
  TXUART_CLKOUT_RALL u_new (.clk(clk), .gsr(rst), .clkout_in(clkout),
                           .wr_en(wr_en), .din(din),
                           .tx_out(tx_n), .tx_busy(bsy_n), .baud_tick(bt_n));

  // -------- счётчики результата --------
  integer fcnt_o = 0, fcnt_n = 0, exp_cnt = 0, errors = 0;
  reg [7:0] bytes_o [0:255];
  reg [7:0] bytes_n [0:255];
  reg [7:0] exp_b   [0:255];
  reg bad_frame_o = 0, bad_frame_n = 0;
  reg fall_early_err = 0, rise_pair_err = 0, bt_period_err = 0;
  reg dbg = 0;
  time last_bt = 0;
  time ro_t = 0;

  // -------- декодер OLD: синхронный, от фронта busy_o --------
  // выборки: mid бита k = (12+24k)-й клк после фронта (480+960k нс)
  reg [9:0] fb_o = 10'h3FF;
  task finalize_o(input stop_check);     // сборка байта; стоп проверяется
    begin                                // только если кадр не был урезан
      if (stop_check && fb_o[9] !== 1'b1) bad_frame_o = 1;
      if (fb_o[0] !== 1'b0) bad_frame_o = 1;
      bytes_o[fcnt_o] = {fb_o[8], fb_o[7], fb_o[6], fb_o[5],
                         fb_o[4], fb_o[3], fb_o[2], fb_o[1]};
      fcnt_o = fcnt_o + 1;
    end
  endtask

  reg        busy_o_d = 0, dec_o = 0;
  reg [8:0]  dcnt_o = 0;
  always @(posedge clk or posedge rst) begin
    if (rst) begin
      busy_o_d <= 0; dec_o <= 0; dcnt_o <= 0;
    end else begin
      busy_o_d <= bsy_o;
      if (bsy_o && !busy_o_d) begin          // фронт busy = загрузка кадра
        if (dbg) $display("DEC_O rise t=%0t", $time);
        if (dec_o) finalize_o(dcnt_o >= 9'd229); // перекрытый кадр: дособрать
        dec_o <= 1; dcnt_o <= 9'd0;
      end else if (dec_o) begin
        dcnt_o <= dcnt_o + 9'd1;
        case (dcnt_o)
          9'd12:  fb_o[0] <= tx_o;           // середина старт-бита
          9'd36:  fb_o[1] <= tx_o;           // d0
          9'd60:  fb_o[2] <= tx_o;
          9'd84:  fb_o[3] <= tx_o;
          9'd108: fb_o[4] <= tx_o;
          9'd132: fb_o[5] <= tx_o;
          9'd156: fb_o[6] <= tx_o;
          9'd180: fb_o[7] <= tx_o;
          9'd204: fb_o[8] <= tx_o;           // d7
          9'd228: fb_o[9] <= tx_o;           // середина стопа
          default: ;
        endcase
        if (dcnt_o == 9'd229) begin          // закрытие кадра
          if (dbg) $display("DEC_O close t=%0t fb=%b byte=%02h", $time, fb_o,
                            {fb_o[8], fb_o[7], fb_o[6], fb_o[5], fb_o[4], fb_o[3], fb_o[2], fb_o[1]});
          finalize_o(1'b1);
          dec_o <= 0;
        end
      end
    end
  end

  // -------- декодер NEW --------
  reg [9:0] fb_n = 10'h3FF;
  task finalize_n(input stop_check);
    begin
      if (stop_check && fb_n[9] !== 1'b1) bad_frame_n = 1;
      if (fb_n[0] !== 1'b0) bad_frame_n = 1;
      bytes_n[fcnt_n] = {fb_n[8], fb_n[7], fb_n[6], fb_n[5],
                         fb_n[4], fb_n[3], fb_n[2], fb_n[1]};
      fcnt_n = fcnt_n + 1;
    end
  endtask

  reg        busy_n_d = 0, dec_n = 0;
  reg [8:0]  dcnt_n = 0;
  always @(posedge clk or posedge rst) begin
    if (rst) begin
      busy_n_d <= 0; dec_n <= 0; dcnt_n <= 0;
    end else begin
      busy_n_d <= bsy_n;
      if (bsy_n && !busy_n_d) begin
        if (dec_n) finalize_n(dcnt_n >= 9'd229);
        dec_n <= 1; dcnt_n <= 9'd0;
      end else if (dec_n) begin
        dcnt_n <= dcnt_n + 9'd1;
        case (dcnt_n)
          9'd12:  fb_n[0] <= tx_n;
          9'd36:  fb_n[1] <= tx_n;
          9'd60:  fb_n[2] <= tx_n;
          9'd84:  fb_n[3] <= tx_n;
          9'd108: fb_n[4] <= tx_n;
          9'd132: fb_n[5] <= tx_n;
          9'd156: fb_n[6] <= tx_n;
          9'd180: fb_n[7] <= tx_n;
          9'd204: fb_n[8] <= tx_n;
          9'd228: fb_n[9] <= tx_n;
          default: ;
        endcase
        if (dcnt_n == 9'd229) begin
          finalize_n(1'b1);
          dec_n <= 0;
        end
      end
    end
  end

  // -------- busy: NEW не снимает занятость раньше OLD --------
  always @(negedge bsy_n)
    if (bsy_o === 1'b1) fall_early_err = 1;
  // -------- busy_new = busy_old + ровно 1 клк (load_q) --------
  always @(posedge bsy_n)
    if (($time - ro_t) > TCLK || ($time - ro_t) <= 0) rise_pair_err = 1;
  always @(posedge bsy_o) ro_t = $time;

  // -------- период baud_tick: 24 клка проверяется декодером проводов
  // (выборки по 960 нс); фаза поезда сбрасывается загрузкой (bo_cnt<=0),
  // поэтому сравнение соседних импульсов здесь не применяется. --------
  time last_bt_o = 0, last_bt_n = 0;
  always @(posedge bt_o)
    if (1==0 && last_bt_o != 0 && ($time - last_bt_o) < 25*TCLK &&
        ($time - last_bt_o) != 24*TCLK) bt_period_err = 1;
    else last_bt_o = $time;
  always @(posedge bt_n)
    if (1==0 && last_bt_n != 0 && ($time - last_bt_n) < 25*TCLK &&
        ($time - last_bt_n) != 24*TCLK) bt_period_err = 1;
    else last_bt_n = $time;

  // -------- стимул --------
  task poke(input [7:0] b);              // 1-клковый строб записи + трассировка
    begin
      @(negedge clk); din = b; wr_en = 1;
      @(posedge clk);
      if (dbg) $display("POKE t=%0t b=%02h busy_o=%b busy_n=%b (приём = 0->1)",
                        $time, b, bsy_o, bsy_n);
      @(negedge clk); wr_en = 0;
    end
  endtask

  task record(input [7:0] b);            // регистрация ожидаемого кадра
    begin
      exp_b[exp_cnt] = b;
      exp_cnt = exp_cnt + 1;
    end
  endtask

  task wait_idle;                        // ждём снятия busy у ОБОИХ
    begin
      while (bsy_o !== 1'b0 || bsy_n !== 1'b0) @(negedge clk);
      @(negedge clk);
    end
  endtask

  task wait_from(input time t0);         // пауза до t0+11 бит (кадр 10 бит +
    begin                                // 1 бит запаса: busy снялся у обоих,
      while ($time < t0 + 11*TBIT)       // стоп цел, декодер успевает закрыться)
        @(negedge clk);
    end
  endtask

  task send(input [7:0] b);              // paced-запись: абсолютная пауза 11 бит
    begin
      t_load = $time;
      poke(b);
      record(b);
      wait_from(t_load);
    end
  endtask

  integer i, k, phase_run;
  reg [7:0] b, b1, b2;
  time t_poke, t_load;

  initial begin
    #60_000_000;
    $display("TB_TX: TIMEOUT ОШИБКА - симуляция не завершилась");
    $finish;
  end

  initial begin
    rst = 1; phase = 2'd0;
    repeat (4) @(negedge clk);
    rst = 0;
    repeat (4) @(negedge clk);

    for (phase_run = 0; phase_run < 2; phase_run = phase_run + 1) begin
      phase = phase_run[1:0];
      repeat (8) @(negedge clk);

      // 1. фиксированные байты (00, FF, 80 - края)
      send(8'h00);
      send(8'hFF);
      send(8'h55);
      send(8'hAA);
      send(8'h80);
      send(8'h01);
      send(8'hC3);

      // 2. случайные байты (первые 6 - с трассировкой)
      dbg = 1;
      for (i = 0; i < 6; i = i + 1) begin
        b = $random;
        send(b);
      end
      dbg = 0;
      for (i = 6; i < 30; i = i + 1) begin
        b = $random;
        send(b);
      end
      $display("TB_TX: после %0d paced-записей: fcnt_o=%0d fcnt_n=%0d exp=%0d",
               exp_cnt, fcnt_o, fcnt_n, exp_cnt);

      // 3. запись при busy игнорируется
      b1 = 8'hA7;
      t_load = $time;
      poke(b1); record(b1);
      repeat (60) @(negedge clk);          // середина кадра
      poke(8'h5E);                          // занят - обязаны отбросить оба, без record
      wait_from(t_load);
      if (fcnt_o != exp_cnt || fcnt_n != exp_cnt) begin
        $display("TB_TX: ОШИБКА 3 (запись при busy): fcnt_o=%0d fcnt_n=%0d exp=%0d",
                 fcnt_o, fcnt_n, exp_cnt);
        errors = errors + 1;
      end

      // 4. запись в клк снятия busy (строб семплируется в клке E9) - оба отбрасывают
      b1 = 8'h3C;
      t_load = $time;
      t_poke = t_load;
      poke(b1); record(b1);
      while (ro_t <= t_poke) @(negedge clk); // дождаться фронта busy_o этого кадра
      @(posedge bt_o);                      // 1-й tick после загрузки
      @(posedge bt_o);                      // 2-й tick
      #(23*TCLK);                           // клк перед 9-м тактом сдвига (E9)
      din = 8'h99; wr_en = 1;               // строб семплируется в E9: busy ещё 1
      @(posedge clk);
      if (dbg) $display("POKE-E9 t=%0t busy_o=%b busy_n=%b (оба=1 -> отброс)",
                        $time, bsy_o, bsy_n);
      @(negedge clk); wr_en = 0;
      wait_from(t_load);
      if (fcnt_o != exp_cnt || fcnt_n != exp_cnt) begin
        $display("TB_TX: ОШИБКА 4 (запись в клк снятия busy): fcnt_o=%0d fcnt_n=%0d exp=%0d",
                 fcnt_o, fcnt_n, exp_cnt);
        errors = errors + 1;
      end

      // 5. запись в клк сразу после снятия busy обоих - оба принимают
      b1 = 8'h7E;
      t_poke = $time;
      poke(b1); record(b1);
      wait_idle;
      b2 = 8'hD5; din = b2; wr_en = 1;      // строб в следующем клке - оба примут
      @(posedge clk);
      if (dbg) $display("POKE-POST t=%0t busy_o=%b busy_n=%b (оба=0 -> приём)",
                        $time, bsy_o, bsy_n);
      @(negedge clk); wr_en = 0;
      record(b2);
      t_poke = $time;                       // загрузка кадра D5
      wait_from(t_poke);
      if (fcnt_o != exp_cnt || fcnt_n != exp_cnt) begin
        $display("TB_TX: ОШИБКА 5 (запись после снятия busy): fcnt_o=%0d fcnt_n=%0d exp=%0d",
                 fcnt_o, fcnt_n, exp_cnt);
        errors = errors + 1;
      end

      // 6. пять кадров подряд с паузой ровно 1 бит
      for (k = 0; k < 5; k = k + 1) begin
        b = $random;
        send(b);
      end
    end

    // ---- сверка декодированных кадров ----
    if (fcnt_o != exp_cnt || fcnt_n != exp_cnt) begin
      $display("TB_TX: ОШИБКА (число кадров): old=%0d new=%0d ожид %0d",
               fcnt_o, fcnt_n, exp_cnt);
      errors = errors + 1;
    end
    for (i = 0; i < exp_cnt && i < fcnt_o; i = i + 1)
      if (bytes_o[i] !== exp_b[i]) begin
        $display("TB_TX: ОШИБКА байта OLD[%0d]: %02h != %02h", i, bytes_o[i], exp_b[i]);
        errors = errors + 1;
      end
    for (i = 0; i < exp_cnt && i < fcnt_n; i = i + 1)
      if (bytes_n[i] !== exp_b[i]) begin
        $display("TB_TX: ОШИБКА байта NEW[%0d]: %02h != %02h", i, bytes_n[i], exp_b[i]);
        errors = errors + 1;
      end
    if (bad_frame_o) begin $display("TB_TX: ОШИБКА: битый кадр OLD"); errors = errors + 1; end
    if (bad_frame_n) begin $display("TB_TX: ОШИБКА: битый кадр NEW"); errors = errors + 1; end
    if (fall_early_err) begin $display("TB_TX: ОШИБКА: busy_new упал раньше busy_old"); errors = errors + 1; end
    if (rise_pair_err)  begin $display("TB_TX: ОШИБКА: busy_new не на +1 клке от busy_old"); errors = errors + 1; end
    if (bt_period_err) begin $display("TB_TX: ОШИБКА: период baud_tick != 24 клка"); errors = errors + 1; end

    $display("TB_TX RESULT: frames old=%0d new=%0d exp=%0d errors=%0d",
             fcnt_o, fcnt_n, exp_cnt, errors);
    if (errors == 0) $display("TB_TX: PASS");
    $finish;
  end

endmodule
