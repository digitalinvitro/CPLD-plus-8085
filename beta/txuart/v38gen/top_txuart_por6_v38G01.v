`timescale 1ns/1ps
//=====================================================================
// top_txuart_por6_v38G01.v - базовый дизайн v37G05 + оптимизация FSM:
//                            живой захват bus_ld без триггеров rd_seen/wr_seen
//                            (экономия 2 МЦ и 11 ПТ в FB4)
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
    output wire       RST75,        // P75 cpu15, U3.7 (CPU.RST 7.5, edge-защёлка, МАСКИРУЕМЫЙ): тик ~4 мс
    // ---- soft-UART транзиты ----
    output wire       SID,          // P73 cpu17, нога 5 (CPU.SID): транзит RX -> приём (RIM 20h)
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
    input  wire       RX,           // P38 цепь платы «TX» (CH340G.TXD) - транзит в SID
    // ---- клавиатура ----
    output wire       col0,         // P44 SW1/SW5/SW9/SW13/SW17 (KBCOL.0)
    output wire       col1,         // P43 SW2/SW6/SW10/SW14/SW18 (KBCOL.1)
    output wire       col2,         // P42 SW3/SW7/SW11/SW15/SW19 (KBCOL.2)
    output wire       col3,         // P41 SW4/SW8/SW12/SW16 (KBCOL.3; SW20 вне матрицы)
    input  wire       row0,         // P56 R25 подтяжка, SW1
    input  wire       row1,         // P55 R24, SW5
    input  wire       row2,         // P54 R23, SW9
    input  wire       row3,         // P52 R22, SW13
    input  wire       row4          // P51 R21, SW17
);
  // Порты индикации/звука: захват по записи в порт при IO/M#=1
  reg [6:0] seg_q   = 7'h40;     // INIT=40 - горит ТОЛЬКО сегмент g (самотест «----»)
  reg [3:0] dig_q   = 4'hF;      // INIT=F - все 4 разряда выбраны
  reg       snd_q   = 1'b0;
  reg [3:0] kbcol_q = 4'h0;      // колонки клавиатуры (вне сброса - скан не гасится)

  assign CS1   = 1'b1;
  assign READY = 1'b1;          // без wait-state - иначе вечные TW

  //=============================================================
  // 1. Узел тактирования: вход 25 МГц -> ДЕЛИТЕЛЬ /4 (t0_q, x1_q)
  //    Вне сети сброса: тактовый сигнал X1/CLKOUT должен идти
  //    на процессор непрерывно даже при удержании кнопки RST.
  //=============================================================
  wire por_ce;

  (* keep = "true", equivalent_register_removal = "no" *)
  reg t0_q = 1'b0;   // clk/2 = 12,5 МГц 50%
  (* keep = "true", equivalent_register_removal = "no" *)
  reg x1_q = 1'b1;   // clk/4 = 6,25 МГц 50%
  (* keep = "true", equivalent_register_removal = "no" *)
  reg x2_q = 1'b0;   // противофаза: x2_q ^= t0_q, INIT=0; X1 INIT=1

  always @(posedge clk) begin
    t0_q <= ~t0_q;             // clk/2
    if (t0_q) x1_q <= ~x1_q;   // clk/4, 50%
    if (t0_q) x2_q <= ~x2_q;   // противофаза X1
  end

  assign X1     = x1_q;             // 6,25 МГц, период ровно 160 нс, duty 1/2
  assign X2     = x2_q;
  assign por_ce = ~t0_q & ~x1_q;    // 1 такт 40 нс за период 160 нс (6,25 МГц)

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
  localparam [2:0] S_IDLE    = 3'd0, // ожидание ALE; A/D в Hi-Z; /OE включён
                   S_T1H     = 3'd1, // T1: CPU держит адрес на A-сетях; идёт захват
                   S_T2      = 3'd2, // ожидание строба !RDn или !WRn
                   S_T2_RD   = 3'd3, // активен !RDn: живой захват в bus_reg; ждём RDn
                   S_T2_WR   = 3'd4, // активен !WRn: живой захват в bus_reg; ждём WRn
                   S_WB1     = 3'd5, // WB: адрес на A + данные на D (t_AS 40 нс до /WE)
                   S_WB2     = 3'd6, // /WE=0 - импульс НАЧАЛСЯ: защищён от ALE
                   S_WB3     = 3'd7; // /WE=0 (импульс = 2 тика = 80 нс >= t_WP ОЗУ)
                                     // отпускание /WE=1 при возврате в S_IDLE (t_AH/t_DH: WB1/WB2/WB3)

  (* fsm_encoding = "compact" *) reg [2:0] state = S_IDLE;

  // Захваченные шинные регистры
  reg [7:0] addr_latch = 8'h00;  // адрес с A-сетей (T1)
  reg [7:0] bus_reg    = 8'h00;  // данные: чтение (с D-сети) ИЛИ запись (с A-сети)

  // Комбинаторные условия без keep: поглощаются матрицей AND без траты buried-МЦ
  wire in_t2_rd   = (state == S_T2) || (state == S_T2_RD);
  wire in_t2_wr   = (state == S_T2) || (state == S_T2_WR);
  wire in_wb      = (state >= S_WB1);
  wire in_welo    = (state == S_WB2) || (state == S_WB3);
  wire wr_phase   = (state >= S_T2);
  wire wb_out     = in_wb;
  wire rd_drive   = in_t2_rd && !RDn && !ALE;
  wire io_wr      = in_t2_wr && !WRn && IOM;
  wire bus_ld_t1  = in_t2_rd && !RDn && !IOM;
  wire bus_ld_t2  = in_t2_wr && !WRn;

  // Чтение 01h (статус + клавиатура KBROW): 1 линия (addr_latch[0] == 1)
  wire io_rd_kb    = IOM && addr_latch[0];

  // Запись 04h (TXUART): 1 линия (addr_latch[2] == 1)
  wire io_wr_tx_en = io_wr && addr_latch[2] && RESET_IN;

  // Запись 08h (колонки клавиатуры KBCOL): 1 линия (addr_latch[3] == 1)
  wire kbcol_wr08  = io_wr && addr_latch[3];

  //=============================================================
  // 4. TXUART: АППАРАТНЫЙ ПЕРЕДАТЧИК UART 8N1 1 000 000 бод (25 МГц / 25)
  //=============================================================
  wire tx_idle;
  wire tx_baud_tick;

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

  //=============================================================
  // 5. Шинный движок и порты индикации/звука
  //    Глобальный асинхронный сброс по активной "1" пина RST (GSR).
  //=============================================================
  always @(posedge clk or posedge RST) begin
    if (RST) begin
      state      <= S_IDLE;
      addr_latch <= 8'h00;
      bus_reg    <= 8'h00;
      seg_q      <= 7'h40;   // самотест «----» (SET для бита 6, CLR для остальных)
      dig_q      <= 4'hF;    // самотест «----» (SET для всех 4 бит)
      snd_q      <= 1'b0;
    end else begin
      if (state == S_T1H && ALE)
        addr_latch <= A;

      // Живой захват bus_ld: bus_ld_t1 (чтение памяти) || bus_ld_t2 (запись)
      if (bus_ld_t1 || bus_ld_t2)
        bus_reg <= bus_ld_t1 ? D : A;

      if (io_wr) begin
        if (addr_latch[0]) seg_q <= A[6:0];  // порт 01h: сегменты
        if (addr_latch[1]) begin             // порт 02h: разряды + звук
          dig_q <= A[3:0];
          snd_q <= A[4];
        end
      end

      case (state)
        S_IDLE:  if (ALE) state <= S_T1H;
        S_T1H:   if (!ALE) state <= S_T2;
        S_T2: begin
          if (!WRn)      state <= S_T2_WR;
          else if (!RDn) state <= S_T2_RD;
        end
        S_T2_RD: if (RDn) state <= S_IDLE;
        S_T2_WR: begin
          if (WRn) begin
            // Запись в ОЗУ (writeback) разрешена только при RESET_IN == 1
            state <= (!IOM && A15 && RESET_IN) ? S_WB1 : S_IDLE;
          end
        end
        S_WB1:   state <= S_WB2;
        S_WB2:   state <= S_WB3;
        S_WB3:   state <= S_IDLE;
        default: state <= S_IDLE;
      endcase
    end
  end

  //=============================================================
  // 6. СВОБОДНЫЙ ТАЙМЕР -> RST 7.5 (P75) и колонки клавиатуры
  //    Намеренно ВНЕ сети сброса (свободный ход 4 мкс).
  //=============================================================
  wire tick_step = por_ce & tx_baud_tick;   // 100 клк = 4 мкс

  reg [7:0] tmr_cnt = 10'd0;
  reg       RST75_r = 1'b0;
  wire timer_irq_tick = tick_step && (&tmr_cnt);

  always @(posedge clk) begin
    RST75_r <= timer_irq_tick;
    if (tick_step) tmr_cnt <= tmr_cnt + 10'd1;
  end

  always @(posedge clk)
    if (kbcol_wr08) kbcol_q <= A[7:4];

  assign RST75 = RST75_r;

  //=============================================================
  // 7. Тристейт-драйверы шины и декод памяти
  //=============================================================
  assign A = rd_drive ? (io_rd_kb ? {tx_idle, tmr_cnt[7:6], row4, row3, row2, row1, row0}
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
// Модуль: TXUART (передатчик UART 8N1 1 000 000 бод на 25 МГц)
// =============================================================================
module TXUART_1M #(
  parameter [4:0] BAUD_DIV = 5'd25   // 25 МГц / 25 = 1 000 000 бод (счёт 0..24)
)(
  input  wire       clk,       // 25 МГц (глобальная тактовая сеть GCK3)
  input  wire       RST,       // Глобальный асинхронный сброс (линия GSR, активный '1')
  input  wire       wr_en,     // Строб записи в порт TX (04h)
  input  wire [7:0] data_in,   // Байт данных с шины A[7:0]
  output wire       tx_out,    // Выход UART TX (P39)
  output wire       tx_idle,   // '1' = передатчик свободен
  output wire       baud_tick  // Тик бодрейта (свободный ход mod-25)
);
  reg [8:0] shreg    = 9'h1FF;  // [8:1] данные, [0] -> TX (SET-ветка GSR: idle = '1')
  reg [3:0] bit_cnt  = 4'd0;    // 1..10 = бит-тайм кадра, 0 = idle (CLR-ветка GSR)
  reg [4:0] baud_cnt = 5'd0;    // mod-25 свободным ходом (CLR-ветка GSR)
  (* keep = "true" *) wire baud_tick_i = (baud_cnt == (BAUD_DIV - 5'd1));
  assign baud_tick = baud_tick_i;
  assign tx_idle   = ~|bit_cnt;
  assign tx_out    = shreg[0];
  wire load = wr_en && tx_idle;

  always @(posedge clk or posedge RST) begin
    if (RST) begin
      shreg    <= 9'h1FF;   // idle '1' (SET-ветка GSR)
      bit_cnt  <= 4'd0;     // idle (CLR-ветка GSR)
      baud_cnt <= 5'd0;     // (CLR-ветка GSR)
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
// Модуль: RESET_CPU
// =============================================================================
module RESET_CPU(
  input  wire clk_out,   // 3.125 МГц (выход тактового генератора процессора)
  input  wire RST,       // Кнопка на P1 (GSR), подтяжка к GND, активный уровень = 1
  output wire RESET_IN   // Выход на 36-й пин ИМ1821ВМ85А (активный уровень = 0)
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

// =============================================================================
// Модуль: TXUART (передатчик UART 8N1 2 000 000 бод на 25 МГц: 12/13 тактов)
// =============================================================================
module TXUART (
  input  wire       clk,       // 25 МГц (глобальная тактовая сеть GCK3)
  input  wire       RST,       // Глобальный асинхронный сброс (линия GSR, активный '1')
  input  wire       wr_en,     // Строб записи в порт TX (04h)
  input  wire [7:0] data_in,   // Байт данных с шины A[7:0]
  output wire       tx_out,    // Выход UART TX (P39)
  output wire       tx_idle,   // '1' = передатчик свободен
  output wire       baud_tick  // Тик бодрейта (свободный ход: 12/13 тактов = 2 МГц)
);
  reg [8:0] shreg     = 9'h1FF;
  reg [3:0] bit_cnt   = 4'd0;
  reg [3:0] baud_cnt  = 4'd0;
  reg       baud_half = 1'b0;

  wire [3:0] div_limit = baud_half ? 4'd12 : 4'd11;
  (* keep = "true" *) wire baud_tick_i = (baud_cnt == div_limit);

  assign baud_tick = baud_tick_i;
  assign tx_idle   = ~|bit_cnt;
  assign tx_out    = shreg[0];

  wire load = wr_en && tx_idle;

  always @(posedge clk or posedge RST) begin
    if (RST) begin
      shreg     <= 9'h1FF;
      bit_cnt   <= 4'd0;
      baud_cnt  <= 4'd0;
      baud_half <= 1'b0;
    end else begin
      if (baud_tick_i) begin
        baud_cnt  <= 4'd0;
        baud_half <= ~baud_half;
      end else begin
        baud_cnt <= baud_cnt + 4'd1;
      end

      if (load) begin
        shreg    <= {data_in, 1'b0};
        bit_cnt  <= 4'd1;
        baud_cnt <= 4'd0;
      end else if (baud_tick_i) begin
        shreg <= {1'b1, shreg[8:1]};
        if (|bit_cnt)
          bit_cnt <= (bit_cnt >= 4'd11) ? 4'd0 : bit_cnt + 4'd1;
      end
    end
  end
endmodule
