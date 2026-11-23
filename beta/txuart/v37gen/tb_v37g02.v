`timescale 1ns/1ps
//=====================================================================
// tb_v37g02.v - tb-регресс свежего дизайна v37G02 (TXUART в домене
// CLKOUT, 625 000 бод 8N1). Icarus Verilog 12.0:
//   iverilog -g2001 -o tb_v37g02.vvp tb_v37g02.v top_txuart_por6_v37G02.v
//   vvp tb_v37g02.vvp
//
// Модель записи ИМ1821ВМ85А (по структуре даташита): T1 - ALE=1, адрес
// на A; T2 - данные на A (ДО WRn#, порядок по t_DC), WRn# 400 нс;
// T3 - удержание. CLKOUT независим от clk (фазы перекрываются от теста
// к тесту - как в свипе S2 python-симуляции).
//
// Сценарии:
//   T1  кадры 55h/AAh/00h/FFh - байт принят, старт ровно 1
//   T2  запись в чужой порт 05h - 0 стартов
//   T3  запись в середине кадра игнорируется (tx_idle), после кадра
//       следующая запись грузится
//   T4  GSR в середине кадра: TX -> '1', новых стартов нет
//=====================================================================
module tb_v37g02;
  reg clk = 0, RST = 0, ALE = 0, WRn = 1, RDn = 1, IOM = 0, A15 = 0;
  reg CLKOUT = 0;                 // 3,125 МГц, фаза не привязана к clk
  reg RSTOUT = 1, SOD = 1, INTAn = 1, HLDA = 1, S0 = 1, S1 = 1;
  reg AH8 = 0, AH9 = 0, AH10 = 0, AH11 = 0, AH12 = 0, AH13 = 0, AH14 = 0;
  reg RX = 1, row0 = 0, row1 = 0, row2 = 0, row3 = 0, row4 = 0;
  wire [7:0] A, D;
  wire CSr_n, OEr_n, CS_n, OE_n, WE_n, CS1, X1, READY, RESET_IN, RST75, SID, TX, SND;
  wire [7:0] seg;
  wire [3:0] dig;
  wire col0, col1, col2, col3;

  reg [7:0] a_val = 8'hFF;
  reg       a_drv = 0;
  assign A = a_drv ? a_val : 8'bZZ;

  retro_pcld_top dut (
    .clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM),
    .A15(A15), .A(A), .D(D), .CSr_n(CSr_n), .OEr_n(OEr_n), .CS_n(CS_n),
    .OE_n(OE_n), .WE_n(WE_n), .CS1(CS1), .X1(X1), .READY(READY),
    .RESET_IN(RESET_IN), .RST75(RST75), .SID(SID), .TX(TX),
    .seg(seg), .dig(dig), .SND(SND),
    .X2(), .RSTOUT(RSTOUT), .SOD(SOD), .INTAn(INTAn), .HLDA(HLDA),
    .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH8), .AH9(AH9), .AH10(AH10), .AH11(AH11), .AH12(AH12),
    .AH13(AH13), .AH14(AH14), .RX(RX),
    .col0(col0), .col1(col1), .col2(col2), .col3(col3),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4)
  );

  always #20   clk    = ~clk;     // 25 МГц, такт 40 нс
  always #160  CLKOUT = ~CLKOUT;  // 3,125 МГц, период 320 нс

  integer loads = 0;              // фактические загрузки TXUART: io_wr_tx=1 на краю CLKOUT
  always @(posedge dut.CLKOUT) if (dut.io_wr_tx) loads = loads + 1;

  integer errors = 0;
  integer rx_done = 0;            // флаг завершения rx_frame

  // Цикл записи IO: ALE 320 нс, данные за 80 нс до WRn#, WRn# 400 нс
  task cpu_write(input [7:0] addr, input [7:0] byte_v);
    begin
      a_drv = 1; a_val = addr; IOM = 1; ALE = 1;
      #320; ALE = 0;
      #60;  a_val = byte_v;
      #20;  WRn = 0;
      #400; WRn = 1;
      #100; a_drv = 0; a_val = 8'hFF; IOM = 0;
      #400;
    end
  endtask

  // Приём кадра 8N1: ждём фронта старта (поллинг, окно 6 мкс), семпл
  // центра каждого бита. rx_done = 1 всегда (ok=0, если кадра не было).
  task rx_frame(output [7:0] byte_v, output integer ok);
    integer k, tw;
    begin
      ok = 1;
      tw = 0;
      while (TX === 1'b1 && tw < 60) begin #100; tw = tw + 1; end
      if (TX !== 1'b0) begin
        ok = 0; byte_v = 8'hXX;   // загрузки не было
      end else begin
        #750;                     // ~центр старт-бита (лаг поллинга <= 100 нс)
        if (TX !== 1'b0) ok = 0;
        for (k = 0; k < 8; k = k + 1) begin
          #1600;
          byte_v[k] = TX;         // LSB-first
        end
        #1600;                    // стоп-бит
        if (TX !== 1'b1) ok = 0;
        #800;
      end
      rx_done = 1;
    end
  endtask

  reg [7:0] got;
  integer ok, s0;

  initial begin
    wait (RESET_IN === 1'b1);     // RESET_CPU: счёт tt на CLKOUT, ~1 мкс
    #2000;

    // -------- T1: кадры --------
    s0 = loads;
    fork
      begin cpu_write(8'h04, 8'h55); end
      begin rx_frame(got, ok); end
    join
    if (ok && got === 8'h55 && loads == s0 + 1)
      $display("T1a PASS: 0x55, загрузок +%0d", loads - s0);
    else begin
      errors = errors + 1; $display("T1a FAIL: got=%h ok=%b загрузок +%0d", got, ok, loads - s0);
    end

    s0 = loads;
    fork
      begin cpu_write(8'h04, 8'hAA); end
      begin rx_frame(got, ok); end
    join
    if (ok && got === 8'hAA && loads == s0 + 1)
      $display("T1b PASS: 0xAA");
    else begin
      errors = errors + 1; $display("T1b FAIL: got=%h ok=%b", got, ok);
    end

    s0 = loads;
    fork
      begin cpu_write(8'h04, 8'h00); end
      begin rx_frame(got, ok); end
    join
    if (ok && got === 8'h00 && loads == s0 + 1)
      $display("T1c PASS: 0x00");
    else begin
      errors = errors + 1; $display("T1c FAIL: got=%h ok=%b", got, ok);
    end

    s0 = loads;
    fork
      begin cpu_write(8'h04, 8'hFF); end
      begin rx_frame(got, ok); end
    join
    if (ok && got === 8'hFF && loads == s0 + 1)
      $display("T1d PASS: 0xFF");
    else begin
      errors = errors + 1; $display("T1d FAIL: got=%h ok=%b", got, ok);
    end

    // -------- T2: чужой порт 05h --------
    s0 = loads;
    cpu_write(8'h05, 8'h55);
    #3000;
    if (loads == s0)
      $display("T2 PASS: порт 05h не грузит UART");
    else begin
      errors = errors + 1; $display("T2 FAIL: лишних загрузок +%0d", loads - s0);
    end

    // -------- T3: запись в середине кадра игнорируется --------
    s0 = loads;
    rx_done = 0;
    fork
      begin cpu_write(8'h04, 8'h55); end
      begin rx_frame(got, ok); end
    join_none
    #2500;                        // середина кадра 0x55
    cpu_write(8'h04, 8'hC3);      // busy - должен игнорироваться
    wait (rx_done === 1'b1);
    if (ok && got === 8'h55 && loads == s0 + 1)
      $display("T3a PASS: 0x55 принят, busy-запись 0xC3 проигнорирована");
    else begin
      errors = errors + 1; $display("T3a FAIL: got=%h ok=%b загрузок +%0d", got, ok, loads - s0);
    end

    // -------- T3b: после кадра следующая запись грузится --------
    s0 = loads;
    fork
      begin cpu_write(8'h04, 8'h99); end
      begin rx_frame(got, ok); end
    join
    if (ok && got === 8'h99 && loads == s0 + 1)
      $display("T3b PASS: 0x99 после кадра принят");
    else begin
      errors = errors + 1; $display("T3b FAIL: got=%h ok=%b", got, ok);
    end

    // -------- T4: GSR в середине кадра --------
    s0 = loads;
    rx_done = 0;
    fork
      begin cpu_write(8'h04, 8'hAA); end
      begin rx_frame(got, ok); end
    join_none
    #2500;                        // кадр 0xAA идёт
    RST = 1;                      // GSR (активная 1)
    #100;
    if (TX === 1'b1)
      $display("T4a PASS: GSR -> TX idle '1'");
    else begin
      errors = errors + 1; $display("T4a FAIL: TX=%b после GSR", TX);
    end
    RST = 0;
    wait (RESET_IN === 1'b1);     // окно счёта RESET_CPU после отпускания
    #5000;
    if (loads == s0 + 1)
      $display("T4b PASS: загрузка была 1 (до GSR), после сброса новых нет");
    else begin
      errors = errors + 1; $display("T4b FAIL: загрузок +%0d (надо 1)", loads - s0);
    end
    wait (rx_done === 1'b1);      // rx_frame дозвонится (байт искажён GSR - не проверяем)

    $display("");
    if (errors == 0) $display("ИТОГ: TB PASS (T1a-d, T2, T3a-b, T4a-b)");
    else             $display("ИТОГ: %0d ошибок", errors);
    $finish;
  end
endmodule
