`timescale 1ns/1ps
//=====================================================================
// top_txuart_por6_v38G09.v - финальная сборка TXUART + RXUART (1 Мбод, 8N1)
//=====================================================================

module retro_pcld_top (
    input  wire       clk,
    input  wire       RST,
    input  wire       ALE,
    input  wire       WRn,
    input  wire       RDn,
    input  wire       IOM,
    input  wire       A15,
    inout  wire [7:0] A,
    inout  wire [7:0] D,
    output wire       CSr_n,
    output wire       OEr_n,
    output wire       CS_n,
    output wire       OE_n,
    output wire       WE_n,
    output wire       CS1,
    output wire       X1,
    output wire       READY,
    output wire       RESET_IN,
    output wire       RST75,
    output wire       SID,
    output wire       TX,
    output wire [7:0] seg,
    output wire [3:0] dig,
    output wire       SND,
    (* keep = "TRUE" *) output wire X2,
    (* keep = "TRUE" *) input wire RSTOUT,
    (* keep = "TRUE" *) input wire SOD,
    (* keep = "TRUE" *) input wire INTAn,
    (* keep = "TRUE" *) input wire HLDA,
    (* keep = "TRUE" *) input wire CLKOUT,
    (* keep = "TRUE" *) input wire S0,
    (* keep = "TRUE" *) input wire S1,
    (* keep = "TRUE" *) input wire AH8,
    (* keep = "TRUE" *) input wire AH9,
    (* keep = "TRUE" *) input wire AH10,
    (* keep = "TRUE" *) input wire AH11,
    (* keep = "TRUE" *) input wire AH12,
    (* keep = "TRUE" *) input wire AH13,
    (* keep = "TRUE" *) input wire AH14,
    input  wire       RX,
    output wire       col0,
    output wire       col1,
    output wire       col2,
    output wire       col3,
    input  wire       row0,
    input  wire       row1,
    input  wire       row2,
    input  wire       row3,
    input  wire       row4
);
  reg [6:0] seg_q   = 7'h40;
  reg [3:0] dig_q   = 4'hF;
  reg       snd_q   = 1'b0;
  reg [3:0] kbcol_q = 4'h0;

  assign CS1   = 1'b1;
  assign READY = 1'b1;

  // 1. Узел тактирования: 25 МГц -> /4
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

  // 2. Сброс процессора ИМ1821ВМ85А
  RESET_CPU u_reset_cpu (
    .clk_out  (CLKOUT),
    .RST      (RST),
    .RESET_IN (RESET_IN)
  );

  // 3. Автомат шины: 8 состояний = 3 триггера
  localparam [2:0] S_IDLE  = 3'd0,
                   S_T1H   = 3'd1,
                   S_T2    = 3'd2,
                   S_T2_RD = 3'd3,
                   S_T2_WR = 3'd4,
                   S_WB1   = 3'd5,
                   S_WB2   = 3'd6,
                   S_WB3   = 3'd7;

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

  wire bus_ld_mem = in_t2_rd && !RDn && !IOM;
  wire bus_ld_rx  = in_t2_rd && !RDn &&  IOM && !addr_latch[0:0];
  wire bus_ld_wr  = in_t2_wr && !WRn;

  wire rx_rd_clr  = (state == S_T2_RD) && RDn && IOM && !addr_latch[0:0];

  wire io_rd_kb    = IOM && addr_latch[0:0];
  wire io_wr_tx_en = io_wr && addr_latch[2:2];
  wire kbcol_wr08  = io_wr && addr_latch[3:3];

  // 4. TXUART и RXUART (1 Мбод, 8N1)
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
    .ce_12m5  (t0_q),
    .rx_in    (RX),
    .rd_clr   (rx_rd_clr),
    .rx_data  (rx_data),
    .rx_ready (rx_ready)
  );

  // 5. Шинный движок и порты
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
        if (addr_latch[0:0]) seg_q <= A[6:0];
        if (addr_latch[1:1]) begin
          dig_q <= A[3:0];
          snd_q <= A[4:4];
        end
      end

      case (state)
        S_IDLE:  if (ALE) state <= S_T1H;
        S_T1H:   if (!ALE) state <= S_T2;
        S_T2:    if (!RDn) state <= S_T2_RD;
                 else if (!WRn) state <= S_T2_WR;
                 else state <= S_IDLE;
        S_T2_RD: if (RDn) state <= S_IDLE;
        S_T2_WR: if (WRn) state <= (!IOM && A15) ? S_WB1 : S_IDLE;
        S_WB1:   state <= S_WB2;
        S_WB2:   state <= S_WB3;
        S_WB3:   state <= S_IDLE;
        default: state <= S_IDLE;
      endcase
    end
  end

  // 6. Единый 10-битный таймер (1.024 мс)
  reg [9:0] tmr_cnt = 10'd0;
  reg       RST75_r = 1'b0;
  wire timer_irq_tick = tx_baud_tick && (&tmr_cnt);

  always @(posedge clk) begin
    RST75_r <= timer_irq_tick;
    if (tx_baud_tick) tmr_cnt <= tmr_cnt + 10'd1;
  end

  always @(posedge clk)
    if (kbcol_wr08) kbcol_q <= A[7:4];

  assign RST75 = RST75_r;

  // 7. Тристейт-драйверы шины и декод памяти
  assign A = rd_drive ? (io_rd_kb ? {tx_idle, rx_ready, tmr_cnt[9:9], row4, row3, row2, row1, row0}
                                  : bus_reg)
           : wb_out   ? addr_latch : 8'bZZZZZZZZ;
  assign D = wb_out ? bus_reg : 8'bZZZZZZZZ;

  assign CSr_n = A15 | IOM;
  assign CS_n  = in_wb ? 1'b0 : (!A15 | IOM);
  assign OEr_n = CSr_n | wr_phase;
  assign OE_n  = CS_n  | wr_phase;
  assign WE_n  = !in_welo;

  // 8. Выходы UART, индикации и клавиатуры
  assign SID  = RX;
  assign seg  = {1'b1, ~seg_q};
  assign dig  = ~dig_q;
  assign SND  = snd_q;
  assign col0 = kbcol_q[0:0];
  assign col1 = kbcol_q[1:1];
  assign col2 = kbcol_q[2:2];
  assign col3 = kbcol_q[3:3];
endmodule

// =============================================================================
// Модуль: TXUART_1M
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
  reg [8:0] shreg    = 9'h1FF;
  reg [3:0] bit_cnt  = 4'd0;
  reg [4:0] baud_cnt = 5'd0;
  (* keep = "true" *) wire baud_tick_i = (baud_cnt == (BAUD_DIV - 5'd1));
  assign baud_tick = baud_tick_i;
  assign tx_idle   = ~|bit_cnt;
  assign tx_out    = shreg[0:0];
  wire load = wr_en && tx_idle;

  always @(posedge clk or posedge RST) begin
    if (RST) begin
      shreg    <= 9'h1FF;
      bit_cnt  <= 4'd0;
      baud_cnt <= 5'd0;
    end else begin
      baud_cnt <= baud_tick_i ? 5'd0 : baud_cnt + 5'd1;
      if (load) begin
        shreg    <= {data_in, 1'b0};
        bit_cnt  <= 4'd1;
        baud_cnt <= 5'd0;
      end else if (baud_tick_i) begin
        shreg <= {1'b1, shreg[8:1]};
      end
      if (|bit_cnt && baud_tick_i) begin
        bit_cnt <= (bit_cnt == 4'd10) ? 4'd0 : bit_cnt + 4'd1;
      end
    end
  end
endmodule

// =============================================================================
// Модуль: RXUART_1M
// =============================================================================
module RXUART_1M (
  input  wire       clk,
  input  wire       RST,
  input  wire       ce_12m5,
  input  wire       rx_in,
  input  wire       rd_clr,
  output wire [7:0] rx_data,
  output wire       rx_ready
);
  reg [3:0] os_cnt   = 4'd0;
  reg [7:0] rx_shreg = 8'hFF;
  reg       rx_busy  = 1'b0;
  reg       ready_q  = 1'b0;

  assign rx_data  = rx_shreg;
  assign rx_ready = ready_q;

  always @(posedge clk or posedge RST) begin
    if (RST) begin
      os_cnt   <= 4'd0;
      rx_shreg <= 8'hFF;
      rx_busy  <= 1'b0;
      ready_q  <= 1'b0;
    end else begin
      if (rd_clr)
        ready_q <= 1'b0;

      if (!rx_busy) begin
        if (!rx_in) begin
          rx_busy  <= 1'b1;
          rx_shreg <= 8'b0111_1111;
          os_cnt   <= 4'd6;
        end
      end else if (ce_12m5) begin
        if (os_cnt == 4'd12) begin
          os_cnt   <= 4'd0;
          rx_shreg <= {rx_in, rx_shreg[7:1]};
          if (!rx_shreg[0:0]) begin
            rx_busy <= 1'b0;
            ready_q <= 1'b1;
          end
        end else begin
          os_cnt <= os_cnt + 4'd1;
        end
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
  assign RESET_IN = tt[2:2];
  wire count_en   = !tt[2:2];

  always @(posedge clk_out or posedge RST) begin
    if (RST) begin
      tt[2:0] <= 3'b000;
    end else if (count_en) begin
      tt[0:0] <= !tt[0:0];
      if (tt[0:0]) tt[1:1] <= !tt[1:1];
      if (tt[0:0] && tt[1:1]) tt[2:2] <= !tt[2:2];
    end
  end
endmodule
