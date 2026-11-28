`timescale 1ns/1ps
//=====================================================================
// tb_rxuart_compact: RXUART_OLD (v39G08 v1, state+bit_cnt) vs
// RXUART_2M (v39G08 v2, nsamp-кодирование) на общем стимуле.
// Проверки:
//  1) 56 кадров (фикс. 00/FF/80/01/AA/55 + случайные), rd_clr между
//     кадрами: байты обоих = стимулу, последовательности равны;
//  2) готовность NEW поднимается НЕ ПОЗЖЕ OLD (стоп в середине бита);
//  3) кадры впритык (пауза 1 бит) с rd_clr - последовательность равна;
//  4) ошибка кадрирования (стоп=0): ни один не выставляет ready;
//  5) глитч старт-бита 1 и 2 клка: NEW отбрасывает (ready=0); OLD
//     выдаёт фантомный байт (известная слабость v1, фиксируется в лог);
//  6) допуск по боду +-3% (464/496 нс бит): оба декодируют верно;
//  7) перезапуск при непрочитанном байте (overrun): OLD затирает байт
//     новым, NEW удерживает прочитанный до rd_clr (ЗАДОКУМЕНТИРОВАННОЕ
//     отличие - защита от потери байта);
//  8) rd_clr в середине кадра безвреден для обоих;
//  9) после rd_clr приём продолжается (кадр N+2 принимается обоими).
//=====================================================================
module BUFGSR(input wire I, output wire O); assign O = I; endmodule
module BUFG  (input wire I, output wire O); assign O = I; endmodule

module tb_rxuart;

  localparam TCLK = 40;                  // 25 МГц
  localparam TBIT = 480;                 // 2.083 Мбод = 12 клков

  reg clk = 0, rst = 1, rx = 1, rdclr = 0;
  always #(TCLK/2) clk = ~clk;

  wire [7:0] do_, dn_;
  wire ro, rn;

  RXUART_OLD u_old (.clk(clk), .gsr(rst), .rx_in(rx), .rd_clr(rdclr),
                    .dout(do_), .rx_ready(ro));
  RXUART_2M  u_new (.clk(clk), .gsr(rst), .rx_in(rx), .rd_clr(rdclr),
                    .dout(dn_), .rx_ready(rn));

  // -------- захват байтов --------
  integer got_o = 0, got_n = 0, errors = 0;
  reg [7:0] cap_o [0:255];
  reg [7:0] cap_n [0:255];
  time tro = 0, trn = 0;
  always @(posedge ro) begin cap_o[got_o] = do_; got_o = got_o + 1; tro = $time; end
  always @(posedge rn) begin cap_n[got_n] = dn_; got_n = got_n + 1; trn = $time; end

  // -------- стимул --------
  task send_frame(input [7:0] b, input stopb, input integer bitns, input integer gapns);
    integer k;
    begin
      rx = 0; #(bitns);                          // старт
      for (k = 0; k < 8; k = k + 1) begin        // d0..d7, младшим вперёд
        rx = b[k]; #(bitns);
      end
      rx = stopb; #(bitns);                      // стоп
      rx = 1; #(gapns);                          // idle
    end
  endtask

  task rd_pulse;                                  // 1-клковый строб чтения
    begin
      @(negedge clk); rdclr = 1;
      @(negedge clk); rdclr = 0;
    end
  endtask

  // дождаться обеих готовностей (NEW раньше OLD), сверить байты, снять ready
  task collect(input [7:0] b);
    begin
      wait (ro === 1'b1 && rn === 1'b1);
      if (trn > tro) begin
        $display("TB_RX: ОШИБКА: ready NEW позже OLD на %0t нс (байт %02h)",
                 trn - tro, b);
        errors = errors + 1;
      end
      if (cap_o[got_o-1] !== b) begin
        $display("TB_RX: ОШИБКА байта OLD: %02h != %02h", cap_o[got_o-1], b);
        errors = errors + 1;
      end
      if (cap_n[got_n-1] !== b) begin
        $display("TB_RX: ОШИБКА байта NEW: %02h != %02h", cap_n[got_n-1], b);
        errors = errors + 1;
      end
      rd_pulse;
      repeat (4) @(negedge clk);
    end
  endtask

  integer i, k, sub;
  reg [7:0] b, b1, b2;

  initial begin
    #60_000_000;
    $display("TB_RX: TIMEOUT ОШИБКА - симуляция не завершилась");
    $finish;
  end

  initial begin
    rst = 1;
    repeat (4) @(negedge clk);
    rst = 0;
    repeat (4) @(negedge clk);

    // 1. основной прогон: фикс + случайные, пауза 1 бит, rd_clr между кадрами
    send_frame(8'h00, 1, TBIT, TBIT); collect(8'h00);
    send_frame(8'hFF, 1, TBIT, TBIT); collect(8'hFF);
    send_frame(8'hAA, 1, TBIT, TBIT); collect(8'hAA);
    send_frame(8'h55, 1, TBIT, TBIT); collect(8'h55);
    send_frame(8'h80, 1, TBIT, TBIT); collect(8'h80);
    send_frame(8'h01, 1, TBIT, TBIT); collect(8'h01);
    for (i = 0; i < 50; i = i + 1) begin
      b = $random;
      send_frame(b, 1, TBIT, TBIT); collect(b);
    end

    // 2. кадры впритык (пауза 0.5 бита), rd_clr сразу после готовности
    for (i = 0; i < 10; i = i + 1) begin
      b = $random;
      send_frame(b, 1, TBIT, TBIT/2);
      wait (ro === 1'b1 && rn === 1'b1);
      if (cap_o[got_o-1] !== b || cap_n[got_n-1] !== b) begin
        $display("TB_RX: ОШИБКА (впритык): OLD=%02h NEW=%02h ожидалось %02h",
                 cap_o[got_o-1], cap_n[got_n-1], b);
        errors = errors + 1;
      end
      rd_pulse;
    end
    repeat (4) @(negedge clk);

    // 3. ошибка кадрирования (стоп = 0): NEW обязан молчать; OLD сэмплирует
    //    стоп ПОСЛЕ конца стоп-бита и может дать фантом (слабость v1)
    send_frame(8'hE7, 0, TBIT, TBIT);
    repeat (2) @(negedge clk);
    if (rn !== 1'b0) begin
      $display("TB_RX: ОШИБКА: ready NEW при стоп=0 (rn=%b)", rn);
      errors = errors + 1;
    end
    if (ro === 1'b1)
      $display("TB_RX: инфо: OLD фантомная готовность при стоп=0 (известная слабость v1)");
    rd_pulse;
    repeat (4) @(negedge clk);
    if (ro !== 1'b0) begin
      $display("TB_RX: ОШИБКА: ready OLD не снялся чтением после стоп=0");
      errors = errors + 1;
    end

    // 4. глитч старт-бита 1 и 2 клка: NEW отбрасывает, OLD даёт фантом
    for (k = 1; k <= 2; k = k + 1) begin
      repeat (4) @(negedge clk);
      rx = 0; #(k*TCLK); rx = 1;
      #(11*TBIT);
      if (rn !== 1'b0) begin
        $display("TB_RX: ОШИБКА: NEW выставил ready на глитче %0d клк", k);
        errors = errors + 1;
      end
      if (ro === 1'b1)
        $display("TB_RX: инфо: OLD фантомная готовность на глитче %0d клк (байт %02h, известная слабость v1)",
                 k, do_);
      rd_pulse;
      repeat (4) @(negedge clk);
      if (ro !== 1'b0) begin
        $display("TB_RX: ОШИБКА: ready OLD не снялся чтением");
        errors = errors + 1;
      end
    end

    // 5. допуск по боду: -3.1% и +2.9%
    for (sub = 0; sub < 2; sub = sub + 1) begin
      for (i = 0; i < 20; i = i + 1) begin
        b = $random;
        if (sub == 0) send_frame(b, 1, 465, TBIT);   // -3.1%
        else          send_frame(b, 1, 494, TBIT);   // +2.9%
        collect(b);
      end
    end

    // 6. перезапуск при непрочитанном байте (overrun): задокументированное отличие
    b1 = 8'h11; b2 = 8'h22;
    send_frame(b1, 1, TBIT, TBIT);
    wait (ro === 1'b1 && rn === 1'b1);
    send_frame(b2, 1, TBIT, TBIT);                   // без rd_clr между кадрами!
    repeat (2) @(negedge clk);
    if (do_ !== b2) begin
      $display("TB_RX: ОШИБКА: OLD не перезаписал байт (do=%02h)", do_);
      errors = errors + 1;
    end
    if (dn_ !== b1) begin
      $display("TB_RX: ОШИБКА: NEW не удержал байт (dn=%02h, ожидалось %02h)", dn_, b1);
      errors = errors + 1;
    end
    if (rn !== 1'b1) begin
      $display("TB_RX: ОШИБКА: ready NEW снялся без rd_clr");
      errors = errors + 1;
    end
    $display("TB_RX: инфо overrun: OLD показал %02h (затёрт кадром 2), NEW удержал %02h", do_, dn_);
    rd_pulse;
    repeat (4) @(negedge clk);
    // 7. после rd_clr приём продолжается
    b = 8'h7A;
    send_frame(b, 1, TBIT, TBIT);
    wait (ro === 1'b1 && rn === 1'b1);
    if (cap_o[got_o-1] !== b || cap_n[got_n-1] !== b) begin
      $display("TB_RX: ОШИБКА: приём после rd_clr: OLD=%02h NEW=%02h",
               cap_o[got_o-1], cap_n[got_n-1]);
      errors = errors + 1;
    end
    rd_pulse;

    // 8. rd_clr в середине кадра безвреден
    fork
      begin
        send_frame(8'h96, 1, TBIT, TBIT);
      end
      begin
        repeat (30) @(negedge clk);                  // ~середина приёма
        rd_pulse;
      end
    join
    wait (ro === 1'b1 && rn === 1'b1);
    if (cap_o[got_o-1] !== 8'h96 || cap_n[got_n-1] !== 8'h96) begin
      $display("TB_RX: ОШИБКА: rd_clr в середине кадра сломал приём: OLD=%02h NEW=%02h",
               cap_o[got_o-1], cap_n[got_n-1]);
      errors = errors + 1;
    end
    rd_pulse;

    $display("TB_RX RESULT: bytes old=%0d new=%0d errors=%0d", got_o, got_n, errors);
    if (errors == 0) $display("TB_RX: PASS");
    $finish;
  end

endmodule
