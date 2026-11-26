// top_txuart_por6_v38G15.v - кандидат G15: TXUART от CLKOUT + таймер на
//   baud-счётчике TX (раздел 16.17). База: G14 (полная RTL-версия).
//   Мотивация владельца (16.17): самый выгодный по ресурсам вариант
//   тактирования TXUART - 1 Мбод 8N1 от цепочки CLKOUT; делитель таймера
//   завести на baud-счётчик TXUART.
//   Пакет G15:
//   1) TXUART_CLKOUT: baud_cnt mod-25 (5 МЦ; декоды baud_cnt<1,2> 22 вх -
//      класс unmapped G10) удалён. Вместо него в домене clk: синхронизатор
//      ck_q + прежнее значение ck_d (детект фронтa CLKOUT) и счётчик
//      фронтов bo_cnt mod-3. Бит = 3 фронта CLKOUT = 960 нс =
//      1.0417 Мбод (+4.17%). CLKOUT = clk/8 на плате (X1/X2 = clk/4,
//      8085 делит на 2), фазы связаны: ширина бита ровно 24 клк при любой
//      статической фазе; детект фронтa не позже 40 нс (1 клк). shreg,
//      load, tx_idle, walking-one - 1-в-1 с G14. Экономия: -1 МЦ (15->14),
//      -30-40 FB-вх (умирает сумматор mod-25 и его декоды).
//   2) Делитель таймера div0..div7 снят с CLKOUT и заведён на
//      tx_baud_tick (выход TXUART): период RST75 = 256 x 960 нс =
//      245.76 мкс (4069 Гц) - класс частоты, одобренный владельцем
//      в 16.13 (было 3906 Гц; G14-ripple от CLKOUT давал 81.92 мкс -
//      втрое чаще). Ответ на вопрос 16.17: таймер = 8 триггеров
//      (div0..div7), количество не меняется; меняется источник.
//      Меню по звеньям (если фит зажмёт): N звеньев = 0.96 x 2^N мкс:
//      div5 = 61.44 мкс (16.3 кГц), div6 = 122.88 мкс (8.1 кГц),
//      div7 = 245.76 мкс (4.07 кГц). Slip фазы тика при load <= 960 нс:
//      период IRQ не меняется, край сдвигается на < 1 тик - потери/удвоения
//      IRQ нет (RST7.5 8085 - edge-triggered).
//   3) Допуск по боду: пир TX должен принимать 1.0417 М. При пире 1.000 М
//      (x1-сэмпл по фронту старта) запас на 10-м бите 100 нс из 480
//      (дрейф 0.40 бита из бюджета 0.5) - тот же класс допуска, что
//      зафиксирован в 16.13 для RX (+4.2%). RX-звено не тронуто (2.083 М).
//   4) Дефект, пойманный симуляцией до фита (16.17): после GSR при
//      CLKOUT=1 пара ck_q/ck_d=00 давала ложный bo_edge (счёт лишнего
//      фронта, тик на 320 нс рано). Фикс: сброс ck_q/ck_d в 1 (SET-тип,
//      GSR ведёт в 1) - первый засчитанный фронт = первый настоящий
//      фронт после сброса при любом уровне CLKOUT; цена 0.
//   5) GSR (правило R1): ck_q, ck_d, bo_cnt, div0..div7 - под GSR
//      (в G14 цепочка div была без сброса; теперь RST75 после GSR
//      детерминирован: все div = 0). Таблица вне-GSR - при первом rpt
//      фита G15 (ожидаем: t0_q/x1_q/x2_q - свободная противофаза).
//   Арифметика МЦ: -1 от G14-full; дефицит ~4-5 МЦ сохраняется, рычаги
//   те же (16.16): SOD-динамик -1, RESET_CPU -3, семантические срезы.
//   Выигрыш главного порядка - входы FB: mod-25-сумматор и декоды 22 вх
//   исчезают, что разгружает TX-FB (класс unmapped baud_cnt<1,2> G10).
//   ПРАВИЛА ПРОЕКТА (16.16, действуют во всех дальнейших дизайнах):
//   R1. GSR-аудит обязателен в каждом обзоре отчёта: таблица регистров,
//       не попавших под глобальную линию асинхронного сброса. Признак
//       в rpt - у FTCPE/FDCPE порты PRE/CLR подключены к RST; колонка
//       SET/RESET в таблице сигналов означает только тип инициализации,
//       а НЕ подключение к GSR. Формат таблицы: имя, такт, причина,
//       решение. Цель - 100% охват регистров состояния; свободные
//       делители (t0_q/x1_q/x2_q, div*) допустимы без сброса сознательно.
//   R2. Делители/счётчики: если каскадная форма (цепочка T-триггеров
//       друг от друга либо каскад малых модулей) освобождает ресурс
//       (FB-входы, птермы, МЦ) - применять везде, где семантика
//       позволяет; экономию фиксировать в разборе. Для модулей не
//       степени 2 выигрыш мал и с оговорками - документировать отказ.
//   История: G14 - tmr 10->8 + RX mod-6 @2.083М (пути б+а), x2
//   регистровый; противофаза x1_q/x2_q - регистровая пара (assign-инверсия
//   отменена владельцем в 16.13). G11/G12: keeps стробов в МЦ, bus_ld_*.
//   TXUART_1M G09-G14: 10-битный shreg, walking-one, стоп >= 960 нс.
//   RXUART_1M: os_cnt mod-6 @ ce_12m5 (бит 480 нс = 2.083 Мбод).
//   bus_reg, FSM, порты, статусы - 1-в-1 с G09..G14.
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

  wire gsr_net = RST;

  reg [6:0] seg_q_n   = 7'h00;
  reg [3:0] dig_q_n   = 4'h0;

  reg       snd_q   = 1'b0;
  reg [3:0] kbcol_q = 4'h0;

  assign CS1   = 1'b1;
  assign READY = 1'b1;

  // 1. Узел тактирования: 25 МГц -> /4 (G14: противофаза — регистровая пара,
  //    x2_q восстановлен; assign-инверсия отменена владельцем, 16.13)
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
  wire wb_out = in_wb || ((state == S_IDLE) && !ALE);
  wire rd_drive   = in_t2_rd && !RDn && !ALE;
  wire io_wr      = (state == S_T2) && !WRn && IOM;

  (* keep = "true" *) wire bus_ld_mem = in_t2_rd && !RDn && !IOM;
  (* keep = "true" *) wire bus_ld_rx  = in_t2_rd && !RDn &&  IOM && !addr_latch[0:0];
  (* keep = "true" *) wire bus_ld_wr  = in_t2_wr && !WRn;

  wire rx_rd_clr  = (state == S_T2_RD) && RDn && IOM && !addr_latch[0:0];

  wire io_rd_kb    = IOM && addr_latch[0:0];
  wire io_wr_tx_en = io_wr && addr_latch[2:2];
  wire kbcol_wr08  = io_wr && addr_latch[3:3];

  // 4. TXUART и RXUART (1 Мбод, 8N1)
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

  RXUART_1M u_rxuart (
    .clk      (clk),
    .RST      (gsr_net),
    .ce_12m5  (t0_q),
    .rx_in    (RX),
    .rd_clr   (rx_rd_clr),
    .rx_data  (rx_data),
    .rx_ready (rx_ready)
  );

  // 5. Шинный движок и порты
  always @(posedge clk or posedge gsr_net) begin
    if (gsr_net) begin
      state      <= S_IDLE;
      addr_latch <= 8'h00;
      bus_reg    <= 8'h00;
      seg_q_n    <= 7'h00;
      dig_q_n    <= 4'h0;
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
        if (addr_latch[0:0]) seg_q_n <= ~A[6:0];
        if (addr_latch[1:1]) begin
          dig_q_n <= ~A[3:0];
          snd_q   <= A[4:4];
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

  // 6. Делитель таймера от baud-счётчика TXUART (16.17):
  // тик 960 нс x 256 = 245.76 мкс (4069 Гц) - класс 16.13; div0 - в домене
  // clk с разрешением tx_baud_tick, звенья 1..7 - ripple T-цепочка, все
  // под GSR (RST75 после сброса детерминирован: RST75 = 0)
  reg div0 = 1'b0;
  reg div1 = 1'b0;
  reg div2 = 1'b0;
  reg div3 = 1'b0;
  reg div4 = 1'b0;
  reg div5 = 1'b0;
  reg div6 = 1'b0;
  reg div7 = 1'b0;

  always @(posedge clk or posedge gsr_net)
    if (gsr_net)           div0 <= 1'b0;
    else if (tx_baud_tick) div0 <= ~div0;

  always @(posedge div0 or posedge gsr_net)
    if (gsr_net) div1 <= 1'b0; else div1 <= ~div1;
  always @(posedge div1 or posedge gsr_net)
    if (gsr_net) div2 <= 1'b0; else div2 <= ~div2;
  always @(posedge div2 or posedge gsr_net)
    if (gsr_net) div3 <= 1'b0; else div3 <= ~div3;
  always @(posedge div3 or posedge gsr_net)
    if (gsr_net) div4 <= 1'b0; else div4 <= ~div4;
  always @(posedge div4 or posedge gsr_net)
    if (gsr_net) div5 <= 1'b0; else div5 <= ~div5;
  always @(posedge div5 or posedge gsr_net)
    if (gsr_net) div6 <= 1'b0; else div6 <= ~div6;
  always @(posedge div6 or posedge gsr_net)
    if (gsr_net) div7 <= 1'b0; else div7 <= ~div7;

  assign RST75 = div7;

  always @(posedge clk)
    if (kbcol_wr08) kbcol_q <= A[7:4];


  // 7. Тристейт-драйверы шины и декод памяти
  assign A = rd_drive ? (io_rd_kb ? {tx_idle, rx_ready, row4, row3, row2, row1, row0}
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
  assign seg  = {1'b1, seg_q_n};
  assign dig  = dig_q_n;
  assign SND  = snd_q;
  assign col0 = kbcol_q[0:0];
  assign col1 = kbcol_q[1:1];
  assign col2 = kbcol_q[2:2];
  assign col3 = kbcol_q[3:3];
endmodule

// =============================================================================
// Модуль: TXUART_CLKOUT (16.17) - бит = 3 фронта CLKOUT = 960 нс (1.0417 Мбод)
//   ck_q/ck_d - синхронизатор CLKOUT и прежнее значение (детект фронтa в clk,
//   не позже 40 нс от фронта); bo_cnt - счёт фронтов mod-3; baud_tick_i -
//   строб каждого третьего фронта (сброс счёта при load: старт-бит ровно
//   960 нс после загрузки). shreg/load/tx_idle/walking-one - 1-в-1 с G14.
//   На плате CLKOUT = clk/8 (X1/X2 = clk/4, 8085 /2) - ширина бита ровно
//   24 клк при любой статической фазе CLKOUT.
// =============================================================================
module TXUART_CLKOUT (
  input  wire       clk,
  input  wire       RST,
  input  wire       clkout,
  input  wire       wr_en,
  input  wire [7:0] data_in,
  output wire       tx_out,
  (* keep = "true" *) output wire tx_idle,
  output wire       baud_tick
);
  reg [9:0] shreg_n = 10'h000;
  reg       ck_q   = 1'b1;   // сброс в 1 (SET): без ложного фронта после GSR
  reg       ck_d   = 1'b1;   // (первый засчитанный фронт - первый настоящий)
  reg [1:0] bo_cnt = 2'd0;
  (* keep = "true" *) wire bo_edge = ck_q & ~ck_d;
  (* keep = "true" *) wire baud_tick_i = bo_edge && (bo_cnt == 2'd2);
  (* KEEP = "TRUE", S = "TRUE" *) wire tx_n = shreg_n[0:0];
  assign baud_tick = baud_tick_i;
  assign tx_idle   = ~(|shreg_n);
  assign tx_out    = ~tx_n;

  (* keep = "true" *) wire load = wr_en && tx_idle;

  always @(posedge clk or posedge RST) begin
    if (RST) begin
      shreg_n <= 10'h000;
      ck_q    <= 1'b1;
      ck_d    <= 1'b1;
      bo_cnt  <= 2'd0;
    end else begin
      ck_q <= clkout;
      ck_d <= ck_q;
      if (load)
        bo_cnt <= 2'd0;
      else if (bo_edge)
        bo_cnt <= (bo_cnt == 2'd2) ? 2'd0 : bo_cnt + 2'd1;
      if (load) begin
        shreg_n <= {1'b0, ~data_in, 1'b1};
      end else if (baud_tick_i) begin
        shreg_n <= {1'b0, shreg_n[9:1]};
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
  (* keep = "true" *) output wire rx_ready
);
  // G14 (путь а): os_cnt 3 бита, mod-6 на ce_12m5 — бит = 6 тиков = 480 нс
  //   = 2.083 Мбод (было 4 бита mod-13, 26 клк = 961.5 кбод); полубит = 3
  //   тика ровно; -1 МЦ (os_cnt<3> с 8 вх) + упрощение декодов.
  reg [2:0] os_cnt   = 3'd0;
  reg [7:0] rx_shreg_n = 8'h00;
  reg       rx_busy  = 1'b0;
  reg       ready_q  = 1'b0;

  (* keep = "true" *) wire sample_tick = ce_12m5 && (os_cnt == 3'd5);
  assign rx_data  = ~rx_shreg_n;
  assign rx_ready = ready_q;

  always @(posedge clk or posedge RST) begin
    if (RST) begin
      os_cnt   <= 3'd0;
      rx_shreg_n <= 8'h00;
      rx_busy  <= 1'b0;
      ready_q  <= 1'b0;
    end else begin
      if (rd_clr)
        ready_q <= 1'b0;

      if (!rx_busy) begin
        if (!rx_in) begin
          rx_busy  <= 1'b1;
          rx_shreg_n <= 8'b1000_0000;
          os_cnt   <= 3'd3;
        end
      end else if (sample_tick) begin
        os_cnt   <= 3'd0;
        rx_shreg_n <= {~rx_in, rx_shreg_n[7:1]};
        if (rx_shreg_n[0:0]) begin
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
