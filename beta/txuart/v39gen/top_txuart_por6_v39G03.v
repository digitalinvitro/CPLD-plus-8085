`timescale 1ns/1ps

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

  wire gsr_net = RST;

  reg [3:0] kbcol_q = 4'h0;

  assign CS1   = 1'b1;
  assign READY = 1'b1;

  // 1. Узел тактирования: 25 МГц -> /4 (противофазная регистровая пара X1/X2)
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
    .RST      (gsr_net),
    .RESET_IN (RESET_IN)
  );

  // 3. Автомат шины: 7 состояний = 3 триггера, 1-в-1 с железно proven v37G07
  //    (WB1..WB4 защищены от ALE; S_IDLE: A/D в Hi-Z - БОЯ С ЦП НЕТ)
  localparam [2:0] S_IDLE = 3'd0,   // ожидание ALE; A/D в Hi-Z; /OE включён
                   S_T1H  = 3'd1,   // T1: CPU держит адрес на A-сетях; захват
                   S_T2   = 3'd2,   // строб: чтение - мост D->A; запись - захват
                   S_WB1  = 3'd3,   // WB: адрес на A + данные на D (t_AS до /WE)
                   S_WB2  = 3'd4,   // /WE=0: импульс НАЧАЛСЯ (защищён от ALE)
                   S_WB3  = 3'd5,   // /WE=0 (импульс 2 тика = 80 нс >= t_WP ОЗУ)
                   S_WB4  = 3'd6;   // /WE=1: удержание адреса/данных (t_AH/t_DH)

  (* fsm_encoding = "compact" *) reg [2:0] state = S_IDLE;
  reg       rd_seen = 1'b0;        // строб чтения замечен в T2 (как в G07)
  reg       wr_seen = 1'b0;        // строб записи замечен в T2 (как в G07)
  reg [7:0] addr_latch = 8'h00;    // адрес с A-сетей (T1)
  reg [7:0] bus_reg    = 8'h00;    // данные: чтение (с D) ИЛИ запись (с A) ИЛИ RX

  wire in_wb      = (state >= S_WB1);
  wire in_welo    = (state == S_WB2) || (state == S_WB3);
  wire wr_phase   = (state >= S_T2);
  wire wb_out     = in_wb;         // ФИКС(1): только WB1..WB4, S_IDLE - Hi-Z
  wire rd_drive   = (state == S_T2) && rd_seen && !RDn && !ALE;
  wire fsm_wrdone = wr_seen && WRn;
  wire fsm_rddone = rd_seen && RDn;
  wire io_wr      = (state == S_T2) && !WRn && IOM;
  wire bus_ld_mem = (state == S_T2) && !RDn && !IOM;    // захват D (ROM/RAM)
  wire bus_ld_rx  = (state == S_T2) && !RDn &&  IOM && !addr_latch[0]; // v39: IN 00h
  wire bus_ld_wr  = (state == S_T2) && !WRn;            // захват A (данные записи)

  // Дешифратор портов v39 (1 линия на порт, канонический список - как G02)
  wire io_rd_kb    = IOM && addr_latch[0];               // IN 01h: статус+KBROW
  // ФИКС(5): io_wr_disp ОДНОТАКТОВЫЙ (!wr_seen): в структуре G07 S_T2 держится
  // весь строб (6 клков) - io_wr стрелял бы 6 раз, а конвейер Rdig<-Rseg<-BUS
  // НЕ идемпотентен (у G07 регистры идемпотентны, G02 с однотактным S_T2
  // писал 1 раз). !wr_seen = ровно 1 клк на строб.
  wire io_wr_disp  = io_wr && addr_latch[0] && !wr_seen; // OUT 01h: конвейер
  wire io_wr_tx_en = io_wr && addr_latch[1];             // OUT 02h: TXDATA (busy-вентиль в TXUART)
  wire kbcol_wr08  = io_wr && addr_latch[3];             // OUT 08h: колонки
  wire rx_rd_clr   = (state == S_T2) && rd_seen && RDn && IOM && !addr_latch[0]; // v39: снятие ready

  // 4. Конвейерный модуль дисплея (Rdig <- Rseg <- BUS)
  wire [6:0] seg_q_n;
  wire [3:0] dig_q_n;

  DISP_PIPELINE u_disp (
    .clk     (clk),
    .RST     (gsr_net),
    .wr_en   (io_wr_disp),
    .data_in (A[6:0]),
    .seg_n   (seg_q_n),
    .dig_n   (dig_q_n)
  );

  // 5. TXUART_CLKOUT (1.0417 Мбод, 8N1 от CLKOUT)
  wire       tx_idle;
  wire       tx_baud_tick;
  wire [7:0] rx_data;
  wire       rx_ready;

  TXUART_CLKOUT u_txuart (
    .clk       (clk),
    .RST       (gsr_net),
    .clkout    (CLKOUT),
    .wr_en     (io_wr_tx_en),
    .data_in   (A),
    .tx_out    (TX),
    .tx_idle   (tx_idle),
    .baud_tick (tx_baud_tick)
  );

  // 6. RXUART_1M (2.083 Мбод, без лишнего keep на sample_tick)
  RXUART_1M u_rxuart (
    .clk      (clk),
    .RST      (gsr_net),
    .ce_12m5  (t0_q),
    .rx_in    (RX),
    .rd_clr   (rx_rd_clr),
    .rx_data  (rx_data),
    .rx_ready (rx_ready)
  );

  // 7. Шинный движок: 1-в-1 с v37G07 (флаги стробов + защита ALE-в-T2 + WB4)
  always @(posedge clk or posedge gsr_net) begin
    if (gsr_net) begin
      state      <= S_IDLE;
      rd_seen    <= 1'b0;
      wr_seen    <= 1'b0;
      addr_latch <= 8'h00;
      bus_reg    <= 8'h00;
    end else begin
      if (state == S_T1H && ALE)
        addr_latch <= A;

      if (bus_ld_mem)
        bus_reg <= D;
      else if (bus_ld_rx)
        bus_reg <= rx_data;
      else if (bus_ld_wr)
        bus_reg <= A;

      if (state == S_T2 && !RDn) rd_seen <= 1'b1;
      if (state == S_T2 && !WRn) wr_seen <= 1'b1;

      if (ALE && state == S_T2 && !(fsm_wrdone || fsm_rddone)) begin
        state   <= S_IDLE;              // ФИКС(3): новый цикл раньше строба
        rd_seen <= 1'b0;
        wr_seen <= 1'b0;
      end else begin
        case (state)
          S_IDLE: if (ALE) state <= S_T1H;
          S_T1H:  if (!ALE) state <= S_T2;
          S_T2: begin
            if (fsm_wrdone) begin
              wr_seen <= 1'b0;
              // WB только вне сброса (1-в-1 с G07)
              state <= (!IOM && A15 && RESET_IN) ? S_WB1 : S_IDLE;
            end else if (fsm_rddone) begin
              rd_seen <= 1'b0;
              state   <= S_IDLE;
            end
          end
          S_WB1: state <= S_WB2;
          S_WB2: state <= S_WB3;
          S_WB3: state <= S_WB4;
          S_WB4: state <= S_IDLE;       // ФИКС(2): удержание после /WE
          default: state <= S_IDLE;
        endcase
      end
    end
  end

  // 8. Таймер: 1.041667 МГц / 128 = 8.138 кГц. ФИКС(4): инкремент ПО ФРОНТУ
  //    тика (btd): тик - УРОВЕНЬ 320 нс = 8 тактов clk; G02 давал +8 за тик
  //    => RST75 32.6 кГц вместо 8.138 кГц.
  reg       btd     = 1'b0;
  reg [6:0] tmr_cnt = 7'd0;

  always @(posedge clk or posedge gsr_net) begin
    if (gsr_net) begin
      btd     <= 1'b0;
      tmr_cnt <= 7'd0;
    end else begin
      btd <= tx_baud_tick;
      if (tx_baud_tick && !btd)
        tmr_cnt <= tmr_cnt + 7'd1;
    end
  end

  assign RST75 = tmr_cnt[6];

  // 9. Регистр столбцов клавиатуры - ВНЕ сброса (1-в-1 с G07: скан не гасится)
  always @(posedge clk)
    if (kbcol_wr08) kbcol_q <= A[7:4];

  // 10. Тристейт-драйверы шины и декод памяти (1-в-1 с v37G07)
  assign A = rd_drive ? (io_rd_kb ? {1'b1, tx_idle, rx_ready, row4, row3, row2, row1, row0}
                                  : bus_reg)
           : wb_out   ? addr_latch : 8'bZZZZZZZZ;
  assign D = wb_out ? bus_reg : 8'bZZZZZZZZ;

  assign CSr_n = A15 | IOM;
  assign CS_n  = in_wb ? 1'b0 : (!A15 | IOM);
  assign OEr_n = CSr_n | wr_phase;
  assign OE_n  = CS_n  | wr_phase;
  assign WE_n  = !in_welo;

  // 11. Выходы UART, индикации, звука (байпас SOD) и клавиатуры
  assign SID  = RX;
  assign seg  = {1'b1, seg_q_n};
  assign dig  = dig_q_n;
  assign SND  = SOD;
  assign col0 = kbcol_q[0];
  assign col1 = kbcol_q[1];
  assign col2 = kbcol_q[2];
  assign col3 = kbcol_q[3];
endmodule


// =============================================================================
// Модуль: DISP_PIPELINE (Конвейер дисплея Rdig <- Rseg <- BUS, активный 0)
// =============================================================================
module DISP_PIPELINE (
  input  wire       clk,
  input  wire       RST,
  input  wire       wr_en,
  input  wire [6:0] data_in,
  output wire [6:0] seg_n,
  output wire [3:0] dig_n
);
  reg [6:0] r_seg_n = 7'h00;
  reg [3:0] r_dig_n = 4'h0;

  always @(posedge clk or posedge RST) begin
    if (RST) begin
      r_seg_n <= 7'h00;
      r_dig_n <= 4'h0;
    end else if (wr_en) begin
      r_dig_n <= r_seg_n[3:0];
      r_seg_n <= ~data_in;
    end
  end

  assign seg_n = r_seg_n;
  assign dig_n = r_dig_n;
endmodule


// =============================================================================
// Модуль: TXUART_CLKOUT (1.0417 Мбод 8N1 от фронтов CLKOUT)
// =============================================================================
module TXUART_CLKOUT (
  input  wire       clk,
  input  wire       RST,
  input  wire       clkout,
  input  wire       wr_en,
  input  wire [7:0] data_in,
  output wire       tx_out,
  output wire       tx_idle,
  output wire       baud_tick
);
  reg [9:0] shreg_n   = 10'h000;
  reg       ck_q      = 1'b1;
  reg       ck_d      = 1'b1;
  reg [1:0] bo_cnt    = 2'd0;
  reg       tx_busy_q = 1'b0;

  wire bo_edge     = ck_q & ~ck_d;
  (* keep = "true" *) wire baud_tick_i = bo_edge && (bo_cnt == 2'd2);
  (* keep = "true" *) wire load        = wr_en && ~tx_busy_q;

  assign baud_tick = baud_tick_i;
  assign tx_idle   = ~tx_busy_q;
  assign tx_out    = ~shreg_n[0];

  always @(posedge clk or posedge RST) begin
    if (RST) begin
      shreg_n   <= 10'h000;
      ck_q      <= 1'b1;
      ck_d      <= 1'b1;
      bo_cnt    <= 2'd0;
      tx_busy_q <= 1'b0;
    end else begin
      ck_q <= clkout;
      ck_d <= ck_q;
      if (load) begin
        bo_cnt    <= 2'd0;
        shreg_n   <= {1'b0, ~data_in, 1'b1};
        tx_busy_q <= 1'b1;
      end else begin
        if (bo_edge)
          bo_cnt <= (bo_cnt == 2'd2) ? 2'd0 : (bo_cnt + 2'd1);
        if (baud_tick_i) begin
          shreg_n <= {1'b0, shreg_n[9:1]};
          if (shreg_n[9:1] == 9'd0)
            tx_busy_q <= 1'b0;
        end
      end
    end
  end
endmodule


// =============================================================================
// Модуль: RXUART_1M (walking-one, без лишнего keep на sample_tick)
// =============================================================================
module RXUART_1M (
  input  wire       clk,
  input  wire       RST,
  input  wire       ce_12m5,
  input  wire       rx_in,
  input  wire       rd_clr,
  output wire [7:0] rx_data,
  (* keep = "true" *) output wire rx_ready
);
  reg [2:0] os_cnt     = 3'd0;
  reg [7:0] rx_shreg_n = 8'h00;
  reg       rx_busy    = 1'b0;
  reg       ready_q    = 1'b0;

  wire sample_tick = ce_12m5 && (os_cnt == 3'd5);
  assign rx_data   = ~rx_shreg_n;
  assign rx_ready  = ready_q;

  always @(posedge clk or posedge RST) begin
    if (RST) begin
		os_cnt     <= 3'd0;
		rx_shreg_n <= 8'h00;
		rx_busy    <= 1'b0;
		ready_q    <= 1'b0;
	end else begin
		if (rd_clr)
			ready_q <= 1'b0;
			if (!rx_busy) begin
				if (!rx_in) begin
					rx_busy    <= 1'b1;
					rx_shreg_n <= 8'b1000_0000;
					os_cnt     <= 3'd3;
				end            
			end else if (sample_tick) begin
					os_cnt     <= 3'd0;
					rx_shreg_n <= {~rx_in, rx_shreg_n[7:1]};
					if (rx_shreg_n[0]) begin
						rx_busy <= 1'b0;
						ready_q <= 1'b1;
					end
			end else if (ce_12m5) begin
					os_cnt <= os_cnt + 3'd1;
			end
	end
end
endmodule
// =============================================================================
// Модуль: RESET_CPU (1-в-1 с v38G14)
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