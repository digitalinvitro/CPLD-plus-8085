`timescale 1ns/1ps
//=====================================================================
// top_txuart_por6_v38G07.v - база v38G06 (93/108 МЦ) + аппаратный RXUART_1M
//   - RXUART_1M (1 000 000 бод, 8N1, P38): 8-бит Walking-Zero + rx_busy
//   - Чтение принятого байта по IN 00h (IOM && !addr_latch[0]) через bus_reg
//   - Флаг готовности rx_ready в бите 6 статуса IN 01h (сброс по завершению IN 00h)
//=====================================================================

module retro_pcld_top (
    // ---- такт и глобальный сброс ----
    input  wire       clk,          // 25 МГц (перемычка H1 С ШУНТОМ ОБЯЗАТЕЛЬНА - DIV=/4 генератора U7), U1.29 (P29, GCK3)
    input  wire       RST,          // SW20, U1.1 (P1, GSR): покой = 0, нажатие = 1 (активная "1" -> глобальная сеть GSR)
    // ---- шина i8085 (входы автомата) ----
    input  wire       ALE,          // cpu1 U1.93 (P93), нога 30
    input  wire       WRn,          // cpu2 U1.92 (P92), нога 31 (активный 0)
    input  wire       RDn,          // cpu3 U1.91 (P91), нога 32 (активный 0)
    input  wire       IOM,          // cpu5 U1.88 (P88), нога 34: 1=IO, 0=память
    input  wire       A15,          // U1.97 (P97) - декод памяти
    // ---- мультиплексированная шина AD0-AD7 = сети A0..A7 (bidir) ----
    inout  wire [7:0] A,            // A0=P26 A1=P21 A2=P19 A3=P17 A4=P15 A5=P13 A6=P11 A7=P9
    // ---- шина данных памяти (bidir) ----
    inout  wire [7:0] D,            // D0=P30 D1=P32 D2=P35 D3=P36 D4=P34 D5=P31 D6=P27 D7=P22
    // ---- управление памятью (активный 0) ----
    output wire       CSr_n,        // P20 /CE_ROM -> U10.22 (flash /CE)
    output wire       OEr_n,        // P16 /OE_ROM -> U10.24
    output wire       CS_n,         // P25 /CE_RAM -> U4.22  (RAM /CE)
    output wire       OE_n,         // P37 /OE_RAM -> U4.24
    output wire       WE_n,         // P24 /WE_RAM -> U4.29 (только writeback!)
    output wire       CS1,          // P99 CS(CE2) -> U4.30, константа '1'
    // ---- поддержка процессора ----
    output wire       X1,           // P68 cpu21, нога 1: 6,25 МГц (x1_q, duty 1/2: high 80 / low 80 нс) -> CPU 3,125 МГц
    output wire       READY,        // P87 cpu6, нога 35: константа '1' (без wait)
    output wire       RESET_IN,     // P84 cpu7, нога 36: активный 0 = сброс CPU (выход модуля RESET_CPU)
    output wire       RST75,        // P75 cpu15, U3.7 (CPU.RST 7.5, edge-защёлка, МАСКИРУЕМЫЙ): тик ~1.024 мс
    // ---- UART и транзит ----
    output wire       SID,          // P73 cpu17, нога 5 (CPU.SID): транзит RX (сохранён для совместимости)
    output wire       TX,           // P39: цепь платы «RX» -> CH340G.RXD; выход модуля TXUART (1 000 000 бод)
    // ---- индикация и звук (выходы активным 0) ----
    output wire [7:0] seg,          // {dp56,g,f,e,d,c,b,a} = P60/5/66/58/57/61/62/45
    output wire [3:0] dig,          // dig0..3 = P6/63/65/48 -> R -> VT1..VT4
    output wire       SND,          // P67 -> BUZZER1.1 (пассивный, прямой бит; A4 порта 01h)
    // ---- наблюдатели: «мёртвые» пины как Hi-Z входы (* keep *) ----
    (* keep = "TRUE" *) output wire X2,        // P69 cpu20, нога 2: противофаза X1
    (* keep = "TRUE" *) input wire RSTOUT,    // P70 cpu19, нога 3
    (* keep = "TRUE" *) input wire SOD,       // P72 cpu18, нога 4 (CPU.SOD): наблюдатель без нагрузки
    (* keep = "TRUE" *) input wire INTAn,     // P80 cpu11, нога 11
    (* keep = "TRUE" *) input wire HLDA,      // P82 cpu9,  нога 38
    (* keep = "TRUE" *) input wire CLKOUT,    // P83 cpu8,  нога 37: 3,125 МГц = X1/2 (тактирует модуль RESET_CPU)
    (* keep = "TRUE" *) input wire S0,        // P94 cpu0,  нога 29
    (* keep = "TRUE" *) input wire S1,        // P89 cpu4,  нога 33
    (* keep = "TRUE" *) input wire AH8,       // P10 цепь A8,  нога 21
    (* keep = "TRUE" *) input wire AH9,       // P12 цепь A9,  нога 22
    (* keep = "TRUE" *) input wire AH10,      // P18 цепь A10, нога 23
    (* keep = "TRUE" *) input wire AH11,      // P14 цепь A11, нога 24
    (* keep = "TRUE" *) input wire AH12,      // P4  цепь A12, нога 25
    (* keep = "TRUE" *) input wire AH13,      // P8  цепь A13, нога 26
    (* keep = "TRUE" *) input wire AH14,      // P3  цепь A14, нога 27
    input  wire       RX,           // P38 цепь платы «TX» (CH340G.TXD) -> вход RXUART_1M
    // ---- клавиатура ----
    output wire       col0,         // P44 SW1/SW5/SW9/SW13/SW17 (KBCOL.0)
    output wire       col1,         // P43 SW2/SW6/SW10/SW14/SW18 (KBCOL.1)
    output wire       col2,         // P42 SW3/SW7/SW11/SW15/SW19 (KBCOL.2)
    output wire       col3,         // P41 SW4/SW8/SW12/SW16/SW20 (KBCOL.3; SW20 вне матрицы)
    input  wire       row0,         // P56 R25 подтяжка, SW1
    input  wire       row1,         // P55 R24, SW5
    input  wire       row2,         // P54 R23, SW9
    input  wire       row3,         // P52 R22, SW13
    input  wire       row4          // P51 R21, SW17
);
  reg [6:0] seg_q   = 7'h40;
  reg [3:0] dig_q   = 4'hF;
  reg       snd_q   = 1'b0;
  reg [3:0] kbcol_q = 4'h0;

  assign CS1   = 1'b1;
  assign READY = 1'b1;

  //=============================================================
  // 1. Узел тактирования: вход 25 МГц -> ДЕЛИТЕЛЬ /4 (t0_q, x1_q)
  //=============================================================
  (* keep = "true", equivalent_register_removal = "no" *)
  reg t0_q = 1'b0;
  (* keep = "true", equivalent_register_removal = "no" *)
  reg x1_q = 1'b1;
  (* keep = "true", equivalent_register_removal = "no" *)
  reg x2_q = 1'b0;

  always @(posedge clk) begin
    t0_q <= ~t0_q;
    if (t0_q) x1_q <= ~x1_q;
    if (t0_q) x2_q <= ~x2_q;
  end

  assign X1 = x1_q;
  assign X2 = x2_q;

  //=============================================================
  // 2. Сброс процессора ИМ1821ВМ85А (модуль RESET_CPU)
  //=============================================================
  RESET_CPU u_reset_cpu (
    .clk_out  (CLKOUT),
    .RST      (RST),
    .RESET_IN (RESET_IN)
  );

  //=============================================================
  // 3. Автомат шины: 8 состояний = 3 триггера (без rd_seen / wr_seen)
  //=============================================================
  localparam [2:0] S_IDLE    = 3'd0,
                   S_T1H     = 3'd1,
                   S_T2      = 3'd2,
                   S_T2_RD   = 3'd3,
                   S_T2_WR   = 3'd4,
                   S_WB1     = 3'd5,
                   S_WB2     = 3'd6,
                   S_WB3     = 3'd7;

  (* fsm_encoding = "sequential" *) reg [2:0] state = S_IDLE;

  reg [7:0] addr_latch = 8'h00;
  reg [7:0] bus_reg    = 8'h00;

  wire in_t2_rd   = (state == S_T2) || (state == S_T2_RD);
  wire in_t2_wr   = (state == S_T2) || (state == S_T2_WR);
  wire in_wb      = (state == S_WB1) || (state == S_WB2) || (state == S_WB3);
  wire in_welo    = (state == S_WB2) || (state == S_WB3);
  wire wr_phase   = in_t2_wr || in_wb;
  wire wb_out     = in_wb || ((state == S_IDLE) && !ALE && !RST);
  wire rd_drive   = in_t2_rd && !RDn && !ALE;
  wire io_wr      = (state == S_T2) && !WRn && IOM;

  // Декод чтения IO:
  // IN 01h (addr_latch[0]==1) -> статус + клавиатура
  // IN 00h (addr_latch[0]==0) -> принятый байт RXUART через bus_reg
  wire io_rd_kb   = IOM && addr_latch[0];
  wire io_rd_rx   = IOM && !addr_latch[0];

  // Живой захват bus_reg:
  // - чтение памяти (!IOM) -> с шины D
  // - чтение IN 00h (io_rd_rx) -> с выхода приёмника rx_data
  // - запись (!WRn) -> с шины A
  wire bus_ld_mem = in_t2_rd && !RDn && !IOM;
  wire bus_ld_rx  = in_t2_rd && !RDn && io_rd_rx;
  wire bus_ld_wr  = in_t2_wr && !WRn;

  // Сброс флага rx_ready строго при завершении цикла чтения IN 00h (RDn отпущен)
  wire rx_rd_done = (state == S_T2_RD) && RDn && io_rd_rx;

  wire io_wr_tx_en = io_wr && addr_latch[2] && RESET_IN;
  wire kbcol_wr08  = io_wr && addr_latch[3];

  //=============================================================
  // 4. TXUART_1M и RXUART_1M: 1 000 000 бод (8N1) от 25 МГц
  //=============================================================
  wire       tx_idle;
  wire       tx_baud_tick;
  wire [7:0] rx_data;
  wire       rx_ready;

  TXUART_1M #(
    .BAUD_DIV(5'd25)
  ) u_txuart (
    .clk       (clk),
    .RST       (RST),
    .wr_en     (io_wr_tx_en),
    .data_in   (A),
    .tx_out    (TX),
    .tx_idle   (tx_idle),
    .baud_tick (tx_baud_tick)
  );

  RXUART_1M u_rxuart (
    .clk      (clk),
    .RST      (RST),
    .rx_in    (RX),
    .rd_clr   (rx_rd_done),
    .rx_data  (rx_data),
    .rx_ready (rx_ready)
  );

  //=============================================================
  // 5. Шинный движок и порты индикации/звука
  //=============================================================
  always @(posedge clk or posedge RST) begin
    if (RST) begin
      state      <= S_IDLE;
      addr_latch <= 8'h00;
      bus_reg    <= 8'h00;
      seg_q      <= 7'h40;
      dig_q      <= 4'hF;
      snd_q      <= 1'b0;
    end else begin
      if (state == S_T1H && ALE)
        addr_latch <= A;

      if (bus_ld_mem)
        bus_reg <= D;
      else if (bus_ld_rx)
        bus_reg <= rx_data;
      else if (bus_ld_wr)
        bus_reg <= A;

      if (io_wr) begin
        if (addr_latch[0]) seg_q <= A[6:0];
        if (addr_latch[1]) begin
          dig_q <= A[3:0];
          snd_q <= A[4];
        end
      end

      case (state)
        S_IDLE: begin
          if (ALE) state <= S_T1H;
        end
        S_T1H: begin
          if (!ALE) state <= S_T2;
        end
        S_T2: begin
          if (!RDn)
            state <= S_T2_RD;
          else if (!WRn)
            state <= S_T2_WR;
          else
            state <= S_IDLE;
        end
        S_T2_RD: begin
          if (RDn) state <= S_IDLE;
        end
        S_T2_WR: begin
          if (WRn)
            state <= (!IOM && A15 && RESET_IN) ? S_WB1 : S_IDLE;
        end
        S_WB1:   state <= S_WB2;
        S_WB2:   state <= S_WB3;
        S_WB3:   state <= S_IDLE;
        default: state <= S_IDLE;
      endcase
    end
  end

  //=============================================================
  // 6. Единый 10-битный свободный таймер (1024 * 1 мкс = 1.024 мс)
  //=============================================================
  reg [9:0] tmr_cnt = 10'd0;
  reg       RST75_r = 1'b0;
  wire timer_irq_tick = tx_baud_tick && (&tmr_cnt);

  always @(posedge clk) begin
    RST75_r <= timer_irq_tick;
    if (tx_baud_tick)
      tmr_cnt <= tmr_cnt + 10'd1;
  end

  always @(posedge clk)
    if (kbcol_wr08) kbcol_q <= A[7:4];

  assign RST75 = RST75_r;

  //=============================================================
  // 7. Тристейт-драйверы шины и декод памяти
  //    IN 01h: [7]=tx_idle, [6]=rx_ready, [5]=tmr_cnt[9], [4:0]=row4..row0
  //    IN 00h: bus_reg (загружен rx_data)
  //=============================================================
  assign A = rd_drive ? (io_rd_kb ? {tx_idle, rx_ready, tmr_cnt[9], row4, row3, row2, row1, row0}
                                  : bus_reg)
           : wb_out   ? addr_latch : 8'bZZZZZZZZ;
  assign D = wb_out ? bus_reg : 8'bZZZZZZZZ;

  assign CSr_n = A15 | IOM;
  assign CS_n  = in_wb ? 1'b0 : (!A15 | IOM);
  assign OEr_n = CSr_n | wr_phase;
  assign OE_n  = CS_n  | wr_phase;
  assign WE_n  = !in_welo;

  //=============================================================
  // 8. Выходы UART, индикации и клавиатуры
  //=============================================================
  assign SID  = RX;
  assign seg  = {1'b1, ~seg_q};
  assign dig  = ~dig_q;
  assign SND  = snd_q;
  assign col0 = kbcol_q[0];
  assign col1 = kbcol_q[1];
  assign col2 = kbcol_q[2];
  assign col3 = kbcol_q[3];
endmodule

// =============================================================================
// Модуль: TXUART_1M (передатчик UART 8N1 1 000 000 бод на 25 МГц)
// =============================================================================
module TXUART_1M #(
  parameter [4:0] BAUD_DIV = 5'd25
)(
  input  wire       clk,
  input  wire       RST,
  input  wire       wr_en,
  input  wire [7:0] data_in,
  output wire       tx_out,
  output wire       tx_idle,
  output wire       baud_tick
);
  reg [7:0] shreg    = 8'hFF;
  reg       tx_bit   = 1'b1;
  reg [3:0] bit_cnt  = 4'd0;
  reg [4:0] baud_cnt = 5'd0;

  (* keep = "true" *) wire baud_tick_i = (baud_cnt == (BAUD_DIV - 5'd1));
  assign baud_tick = baud_tick_i;
  assign tx_idle   = ~|bit_cnt;
  assign tx_out    = tx_bit;
  wire load = wr_en && tx_idle;

  always @(posedge clk or posedge RST) begin
    if (RST) begin
      shreg    <= 8'hFF;
      tx_bit   <= 1'b1;
      bit_cnt  <= 4'd0;
      baud_cnt <= 5'd0;
    end else begin
      baud_cnt <= baud_tick_i ? 5'd0 : baud_cnt + 5'd1;
      if (load) begin
        shreg    <= data_in;
        tx_bit   <= 1'b0;
        bit_cnt  <= 4'd1;
        baud_cnt <= 5'd0;
      end else if (baud_tick_i) begin
        tx_bit <= shreg[0];
        shreg  <= {1'b1, shreg[7:1]};
      end
      if (|bit_cnt && baud_tick_i) begin
        bit_cnt <= (bit_cnt == 4'd10) ? 4'd0 : bit_cnt + 4'd1;
      end
    end
  end
endmodule

// =============================================================================
// Модуль: RXUART_1M (приёмник UART 8N1 1 000 000 бод на 25 МГц, 8-бит Walking-Zero)
// Ресурсы: 1 (rx_q) + 5 (os_cnt) + 8 (rx_shreg) + 1 (rx_busy) + 1 (ready_q) = 16 МЦ
// =============================================================================
module RXUART_1M (
  input  wire       clk,       // 25 МГц (GCK3)
  input  wire       RST,       // GSR (активный '1')
  input  wire       rx_in,     // P38 (линия RX)
  input  wire       rd_clr,    // строб завершения чтения IN 00h
  output wire [7:0] rx_data,   // принятый байт (удерживается в rx_shreg)
  output wire       rx_ready   // флаг готовности (бит 6 статуса IN 01h)
);
  reg       rx_q     = 1'b1;
  reg       rx_busy  = 1'b0;
  reg [4:0] os_cnt   = 5'd0;
  reg [7:0] rx_shreg = 8'hFF;
  reg       ready_q  = 1'b0;

  (* keep = "true" *) wire rx_tick = (os_cnt == 5'd24);

  assign rx_data  = rx_shreg;
  assign rx_ready = ready_q;

  always @(posedge clk or posedge RST) begin
    if (RST) begin
      rx_q     <= 1'b1;
      rx_busy  <= 1'b0;
      os_cnt   <= 5'd0;
      rx_shreg <= 8'hFF;
      ready_q  <= 1'b0;
    end else begin
      rx_q <= rx_in;

      if (rd_clr)
        ready_q <= 1'b0;

      if (!rx_busy) begin
        // Ожидание старт-бита (спад rx_q == 0)
        if (!rx_q) begin
          rx_busy  <= 1'b1;
          os_cnt   <= 5'd12;        // 12 тактов (480 нс) до середины старт-бита
          rx_shreg <= 8'b01111111;  // маркер Walking-Zero в бите [7]
        end
      end else if (rx_tick) begin
        os_cnt <= 5'd0;
        if (!rx_shreg[0]) begin
          // Ноль дошёл до бита [0]: в rx_shreg[7:1] биты D6..D0, на rx_q стоит D7
          rx_shreg <= {rx_q, rx_shreg[7:1]};
          rx_busy  <= 1'b0;
          ready_q  <= 1'b1;
        end else begin
          rx_shreg <= {rx_q, rx_shreg[7:1]};
        end
      end else begin
        os_cnt <= os_cnt + 5'd1;
      end
    end
  end
endmodule

// =============================================================================
// Модуль: RESET_CPU
// =============================================================================
module RESET_CPU(
  input  wire clk_out,
  input  wire RST,
  output wire RESET_IN
);
  reg [2:0] tt = 3'b000;
  assign RESET_IN = tt[2];
  wire count_en   = !tt[2];

  always @(posedge clk_out or posedge RST) begin
    if (RST) begin
      tt[2:0] <= 3'b000;
    end else if (count_en) begin
      tt[0] <= !tt[0];
      if (tt[0]) tt[1] <= !tt[1];
      if (tt[0] && tt[1]) tt[2] <= !tt[2];
    end
  end
endmodule
