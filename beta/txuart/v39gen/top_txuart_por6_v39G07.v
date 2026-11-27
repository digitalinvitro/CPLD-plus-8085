`timescale 1ns/1ps
//=====================================================================
// v39G07 (2026-11-27): G06 + 5 правок. Цель: фит сходится + приём RX
// 0x00..0xFF. Ожидание по ресурсам: ~107/108 МЦ (G06 требовал 106 и
// НЕ РАЗМЕСТИЛСЯ: rx_busy 6ПТ/14вх, D4/D5_BUFR - входы ФБ1/ФБ3 36/36).
//
//  1. RXUART_1M: завершение приёма - по даун-счётчику выборок nsamp
//     (0=покой, 8=верификация старта, 7..0 = выборки d0..d7),
//     rx_busy = |nsamp без отдельного триггера. В G05/G06 ready/busy
//     взводились на ПЕРВОЙ выборке данных: тест по сдвиговому регистру
//     (walking-one / shreg==0) не отличает маркер от данных, pre-shift
//     0x80 != 0 уже на d0 -> фантомный перезапуск, байт не принимался.
//  2. tmr_cnt 8->7 бит, RST75 = tmr_cnt[6]: период тика 122.88 мкс
//     (8138 Гц) - как в G02/G03 и под джиффи fw_monitor v3.0.
//     G06 дал 245.76 мкс (/256) - вдвое реже монитора, исправлено.
//  3. RESET_CPU: 2 триггера (было 3), RESET_IN = tt[1], растяжка сброса
//     2 такта CLKOUT = 4 периода X1 >= 3 по даташиту. -1 МЦ.
//  4. bus_ld_rx: тест addr==0x00 (8 вх.) -> !addr_latch[0]: чтение RX
//     на портах 00h И 02h, согласовано с rx_rd_clr. -5 входов ФБ.
//  5. BUFG/BUFGSR убраны: cpldfit их игнорирует (в отчёте G06
//     "Global clock/set/reset net(s) unused"); GCK/GSR назначаются
//     сами по пинам 29/1, как в G05 (там сети легли корректно).
//  6. Статус TX на A-шине (D6): в G06 провод tx_idle был подключён к
//     выходу tx_busy - полярность статуса инвертирована против G05.
//     Восстановлено: D6=1 = ГОТОВ к загрузке (TXRDY монитора).
//
//  Карта IO (без изменений от G06): запись 01h=дисплей, 02h=TX,
//  03h=дисплей+TX ОДНОВРЕМЕННО (не использовать); чтение 00h/02h=RX
//  (сброс готовности), 01h/03h=клавиатура+tx_idle(D6); RX-флаг = SID
//  (команда RIM). TX 1.0417 Мбод 8N1 от CLKOUT/3; RX 2.083 Мбод.
//=====================================================================
module retro_pcld_top (
    input  wire       cpld_clk,
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

  // Пин 29 = GCK1, пин 1 = GSR: cpldfit назначает глобальные сети GCK/GSR
  // сам по пинам (примитивы BUFG/BUFGSR для XC9500 не поддерживаются -
  // в отчёте G06 с ними глобальные сети остались "unused").
  wire clk     = cpld_clk;
  wire gsr_net = RST;

  assign CS1   = 1'b1;
  assign READY = 1'b1;

  // 1. Узел тактирования: 25 МГц -> /4 (противофазная регистровая пара X1/X2)
  // Все триггеры сбрасываются строго в 0 (CLR по GSR), для X1 - инверсия на выходе
  (* keep = "true", equivalent_register_removal = "no" *)
  reg t0_q = 1'b0;
  (* keep = "true", equivalent_register_removal = "no" *)
  reg x1_q_n = 1'b0;  // При сбросе = 0, на выход X1 пойдет инверсия (1)
  (* keep = "true", equivalent_register_removal = "no" *)
  reg x2_q = 1'b0;    // При сбросе = 0, на выход X2 пойдет прямое значение (0)

  always @(posedge clk or posedge gsr_net) begin
    if (gsr_net) begin
      t0_q   <= 1'b0;
      x1_q_n <= 1'b0;
      x2_q   <= 1'b0;
    end else begin
      t0_q <= ~t0_q;
      if (t0_q) begin
        x1_q_n <= ~x1_q_n;
        x2_q   <= ~x2_q;
      end
    end
  end

  assign X1 = ~x1_q_n;
  assign X2 = x2_q;

  // 2. Сброс процессора ИМ1821ВМ85А (растяжка: сброс держится 2 такта
  //    CLKOUT = 4 периода X1 после отпускания RST, затем RESET_IN=1)
  RESET_CPU u_reset_cpu (
    .clk_out  (CLKOUT),
    .RST      (gsr_net),
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
  wire wb_out     = in_wb || ((state == S_IDLE) && !ALE);
  wire rd_drive   = in_t2_rd && !RDn && !ALE;
  wire io_wr      = (state == S_T2) && !WRn && IOM;

  (* keep = "true" *) wire bus_ld_mem = (state == S_T2) && !RDn && !IOM;
  (* keep = "true" *) wire bus_ld_rx  = (state == S_T2) && !RDn &&  IOM && !addr_latch[0];
  (* keep = "true" *) wire bus_ld_wr  = (state == S_T2) && !WRn;

  wire rx_rd_clr   = (state == S_T2_RD) && RDn && IOM && !addr_latch[0];

  wire io_rd_kb    = IOM && addr_latch[0];
  wire io_wr_disp  = io_wr && addr_latch[0];
  wire io_wr_tx_en = io_wr && addr_latch[1];

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

  // 5. TXUART_CLKOUT (1.0417 Мбод, 8N1 от CLKOUT; load гейтится !tx_busy)
  // ВНИМАНИЕ (находка симуляции G07): в G06 выход tx_busy подключён прямо
  // к проводу tx_idle - бит D6 статуса на A-шине был ИНВЕРТИРОВАН против
  // семантики G05 (D6=1 = ГОТОВ к загрузке). Здесь полярность восстановлена.
  wire       tx_busy_w;
  wire       tx_idle = ~tx_busy_w;
  wire       tx_baud_tick;
  wire [7:0] rx_data;
  wire       rx_ready;

  TXUART_CLKOUT_RALL u_txuart (
    .clk       (clk),
    .gsr       (gsr_net),
    .clkout_in (CLKOUT),
    .wr_en     (io_wr_tx_en),
    .din       (A),
    .tx_out    (TX),
    .tx_busy   (tx_busy_w),
    .baud_tick (tx_baud_tick)
  );

  // 6. RXUART_1M (2.083 Мбод, приём 0x00..0xFF по счётчику выборок)
  RXUART_1M u_rxuart (
    .clk      (clk),
    .RST      (gsr_net),
    .ce_12m5  (t0_q),
    .rx_in    (RX),
    .rd_clr   (rx_rd_clr),
    .rx_data  (rx_data),
    .rx_ready (rx_ready)
  );

  // 7. Шинный движок (с ожиданием RDn/WRn в S_T2)
  always @(posedge clk or posedge gsr_net) begin
    if (gsr_net) begin
      state      <= S_IDLE;
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

      case (state)
        S_IDLE:  if (ALE) state <= S_T1H;
        S_T1H:   if (!ALE) state <= S_T2;
        S_T2:    if (!RDn) state <= S_T2_RD;
                 else if (!WRn) state <= S_T2_WR;
                 else if (ALE) state <= S_T1H;
        S_T2_RD: if (RDn) state <= S_IDLE;
        S_T2_WR: if (WRn) state <= (!IOM && A15) ? S_WB1 : S_IDLE;
        S_WB1:   state <= S_WB2;
        S_WB2:   state <= S_WB3;
        S_WB3:   state <= S_IDLE;
        default: state <= S_IDLE;
      endcase
    end
  end

  // 8. Синхронный 7-битный делитель таймера на GCK (clk) от tx_baud_tick
  //    1.041667 МГц / 128 = 8138.02 Гц (период 122.88 мкс = 384 такта
  //    CLKOUT) - джиффи fw_monitor v3.0, как в G02/G03.
  reg [6:0] tmr_cnt = 7'd0;

  always @(posedge clk or posedge gsr_net) begin
    if (gsr_net)
      tmr_cnt <= 7'd0;
    else if (tx_baud_tick)
      tmr_cnt <= tmr_cnt + 7'd1;
  end

  assign RST75 = tmr_cnt[6];

  // 9. Тристейт-драйверы шины и декод памяти (rx_ready снят с A, на SID)
  assign A = rd_drive ? (io_rd_kb ? {1'b1, tx_idle, 1'b1, row4, row3, row2, row1, row0}
                                  : bus_reg)
           : wb_out   ? addr_latch : 8'bZZZZZZZZ;
  assign D = wb_out ? bus_reg : 8'bZZZZZZZZ;

  assign CSr_n = A15 | IOM;
  assign CS_n  = in_wb ? 1'b0 : (!A15 | IOM);
  assign OEr_n = CSr_n | wr_phase;
  assign OE_n  = CS_n  | wr_phase;
  assign WE_n  = !in_welo;

  // 10. Выходы UART, статуса RX (SID), индикации, звука и клавиатуры
  assign SID  = rx_ready;
  assign seg  = {1'b1, seg_q_n};
  assign dig  = dig_q_n;
  assign SND  = SOD;
  assign {col3, col2, col1, col0} = dig_q_n[3:0];
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
  (* keep = "true" *) reg [6:0] r_seg_n = 7'h00;
  (* keep = "true" *) reg [3:0] r_dig_n = 4'h0;

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
// Модуль: TXUART_CLKOUT_RALL (1.0417 Мбод 8N1 от фронтов CLKOUT)
// v39G07: вход переименован wr_en, внутренний load = wr_en && !tx_busy_q -
// повторный OUT 02h в фазе передачи не перезаписывает кадр (как в G05).
// =============================================================================
module TXUART_CLKOUT_RALL (
    input  wire       clk,        // 25 МГц
    input  wire       gsr,        // Активный высокий сброс
    input  wire       clkout_in,  // 3.125 МГц (выход процессора CLKOUT)
    input  wire       wr_en,      // Строб записи байта (порт 02h)
    input  wire [7:0] din,        // Байт данных для передачи
    output wire       tx_out,     // Линия TX (Idle = 1)
    output wire       tx_busy,    // Флаг занятости передатчика
    output wire       baud_tick   // Выход тактирования (1.0417 МГц)
);

    // Детектор нарастающего фронта CLKOUT
    reg ck_q = 1'b0;
    reg ck_d = 1'b0;
    wire ck_rise = ck_q & ~ck_d;

    always @(posedge clk or posedge gsr) begin
        if (gsr) begin
            ck_q <= 1'b0;
            ck_d <= 1'b0;
        end else begin
            ck_q <= clkout_in;
            ck_d <= ck_q;
        end
    end

    // Делитель CLKOUT на 3 (для формирования бодрейта)
    reg [1:0] bo_cnt = 2'b00;
    assign baud_tick = ck_rise & (bo_cnt == 2'd2);

    always @(posedge clk or posedge gsr) begin
        if (gsr) begin
            bo_cnt <= 2'b00;
        end else if (load) begin
            bo_cnt <= 2'b00;
        end else if (ck_rise) begin
            if (bo_cnt == 2'd2)
                bo_cnt <= 2'b00;
            else
                bo_cnt <= bo_cnt + 2'd1;
        end
    end

    // Сдвиговый регистр (инвертированная полярность хранения, сброс всех бит в 0)
    // В состоянии покоя (Idle) shreg = 9'h000, поэтому tx_out = ~shreg[0] = 1
    // Кадр при загрузке: {стоп-бит (0), инверсные данные (~din[7:0]), старт-бит (1)}
    (* keep = "true" *) reg [8:0] shreg     = 9'h000;
    reg       tx_busy_q = 1'b0;

    // Гейт загрузки: в фазе передачи запись игнорируется (кадр не рвётся)
    wire load = wr_en && !tx_busy_q;

    always @(posedge clk or posedge gsr) begin
        if (gsr) begin
            shreg     <= 9'h000;
            tx_busy_q <= 1'b0;
        end else if (load) begin
            // Старт-бит = 1 (на выходе TX станет 0), данные инвертированы (~din)
            shreg     <= {~din, 1'b1};
            tx_busy_q <= 1'b1;
        end else if (baud_tick) begin
            // Сдвиг вправо, старший бит заполняется 0 (на выходе TX станет 1)
            shreg     <= {1'b0, shreg[8:1]};
            // Как только в регистре остался только последний передаваемый бит
            // (shreg[8:1] == 0), передача завершена
            if (shreg[8:1] == 8'h00)
                tx_busy_q <= 1'b0;
        end
    end

    assign tx_out  = ~shreg[0];
    assign tx_busy = tx_busy_q;

endmodule


// =============================================================================
// Модуль: RXUART_1M (2.083 Мбод, приём 0x00..0xFF по счётчику выборок)
// v39G07: walking-one маркер и тест shreg==0 УДАЛЕНЫ - они не отличают
// маркер от данных (pre-shift 0x80 != 0 уже на d0 => ready/busy на первом
// же бите, фантомный перезапуск, потеря байта). Теперь: nsamp 9 = ждём
// середину старт-бита (верификация линии), 8..1 = счёт выборок d0..d7,
// 15 = ожидание высокого стоп-бита (при d7=0 без него ре-детект на
// оставшихся 240 нс d7 затирал байт), 0 = покой; rx_busy = |nsamp
// (отдельного триггера нет), повторный старт внутри кадра невозможен.
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
  reg [3:0] nsamp      = 4'd0;
  reg [7:0] rx_shreg_n = 8'h00;
  reg       ready_q    = 1'b0;

  wire sample_tick = ce_12m5 && (os_cnt == 3'd5);
  wire rx_busy     = |nsamp;

  assign rx_data  = ~rx_shreg_n;
  assign rx_ready = ready_q;

  always @(posedge clk or posedge RST) begin
    if (RST) begin
      os_cnt     <= 3'd0;
      nsamp      <= 4'd0;
      rx_shreg_n <= 8'h00;
      ready_q    <= 1'b0;
    end else begin
      if (rd_clr)
        ready_q <= 1'b0;

      if (!rx_busy) begin
        if (!rx_in) begin
          nsamp      <= 4'd9;
          rx_shreg_n <= 8'h00;
          os_cnt     <= 3'd3;
        end
      end else if (sample_tick) begin
        os_cnt <= 3'd0;
        if (nsamp == 4'd9) begin
          // Середина старт-бита: линия обязана быть ещё низка
          if (!rx_in)
            nsamp <= 4'd8;
          else
            nsamp <= 4'd0;   // глитч - ложный старт, обратно в покой
        end else if (nsamp == 4'd15) begin
          // Ждём высокого стоп-бита (иначе при d7=0 линия низкая ещё 240 нс
          // и мгновенный ре-детект затирал бы принятый байт - баг G05/G06)
          if (rx_in)
            nsamp <= 4'd0;   // стоп подтверждён - в покой
        end else begin
          // Выборки данных d0..d7 (каждые 480 нс)
          rx_shreg_n <= {~rx_in, rx_shreg_n[7:1]};
          if (nsamp == 4'd1) begin
            nsamp   <= 4'd15; // это была d7 - байт готов, ждём стоп
            ready_q <= 1'b1;
          end else begin
            nsamp <= nsamp - 4'd1;
          end
        end
      end else if (ce_12m5) begin
        os_cnt <= os_cnt + 3'd1;
      end
    end
  end
endmodule


// =============================================================================
// Модуль: RESET_CPU (v39G07: 2 триггера, растяжка 2 такта CLKOUT)
// RESET_IN = ~(RST|POR) на плате: LOW = ЦП в сбросе, HIGH = работает.
// После отпускания RST счётчик tt держит RESET_IN в 0 ещё 2 такта CLKOUT
// (= 4 периода X1, минимум 3 по даташиту), затем RELEASE навсегда.
// =============================================================================
module RESET_CPU(
  input  wire clk_out,
  input  wire RST,
  output wire RESET_IN
);
  reg [1:0] tt = 2'b00;
  assign RESET_IN = tt[1];
  wire count_en   = !tt[1];

  always @(posedge clk_out or posedge RST) begin
    if (RST) begin
      tt[1:0] <= 2'b00;
    end else if (count_en) begin
      tt[0] <= !tt[0];
      if (tt[0]) tt[1] <= !tt[1];
    end
  end
endmodule
