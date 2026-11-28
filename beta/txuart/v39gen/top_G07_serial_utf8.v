`timescale 1ns/1ps
//=====================================================================
// v39G07_serial (2026-11-28): G07 + полностью последовательный
// одноразрядный порт записи в дисплей/клавиатуру (идея владельца).
//
//  Принцип (по ТЗ): порт 01h - однобитный. Бит D7 шины данных
//  задвигается в цепочку  SND <- seg[6:0] <- col[3:0] <- dig[3:0]  -
//  это КОЛЬЦЕВОЙ 16-битный регистр. Спад SOD 1->0 (формируется
//  командой SIM) сдвигает ВСЕ секции одновременно на одну позицию.
//  Спад SOD без свежей записи = чистое вращение кольца (хвост
//  возвращается в голову). Бит, записанный в голову, после 16 спадов
//  возвращается в голову и замещается следующим.
//  GSR-инициализация ("b'41000" на 4-битных секциях): SND=0, сегменты
//  погашены (7'b1111111 - единственное безопасное значение для
//  7-битной секции), col_n = dig_n = 4'b1000 (активна одна позиция):
//      sreg = 16'b0_1111111_1000_1000 = 16'h7F88.  Все 16 бит кольца
//  и оба синхронизатора SOD сидят на ГЛОБАЛЬНОМ сбросе (GSR, пин 1):
//  для бит с инициализацией '1' это PRE=RST (GSR-установка), для '0' -
//  CLR=RST; неподключенных к GSR триггеров в кольце нет.
//
//  Структура кольца (все выходы активны 0):
//      sreg[15]   = SND      (звук - голова кольца, сюда входит D7)
//      sreg[14:8] = seg_n[6:0] (сегменты индикатора)
//      sreg[7:4]  = col_n[3:0] (столбцы клавиатуры)
//      sreg[3:0]  = dig_n[3:0] (выбор цифры дисплея)
//
//  vs G07: убран DISP_PIPELINE (11 МЦ; 7 линий данных A[6:0] из ФБ),
//  добавлено кольцо (16 МЦ) + 2 синхронизатора SOD. Итого +7 МЦ к G07
//  (~111 требуемых) => оценка ~118 требуемых МЦ против 108 в
//  XC95108XL (113, если фиттеру удастся отказаться от буферов
//  col0-3_BUFR/A4_BUFR) - БЕЗ дополнительных сокращений дизайн НЕ
//  влезает; варианты см. DEVLOG 11-28. Включён keep-фикс load TXUART
//  (рецепт G08): без него cpldfit разворачивает load в каждый
//  shreg_D(k) (4->12-13 вх.) и tx_busy_T (->21 вх.) - причина провала
//  G07 по входам ФБ.
//  Протокол софта (8085):
//    записать бит:  OUT 01h, D7 = бит (D6..D0 игнорируются);
//    сдвиг кольца:  MVI A,0C0h / SIM (SOD=1) ... MVI A,040h / SIM
//    (SOD=0) - спад 1->0 = один такт цепочки; без OUT перед этим -
//    чистое вращение (шаг скана/перемещение по кольцу).
//    ЗАГРУЗКА КАДРА 16 бит: последний спад цикла тоже вращает кольцо
//    (хвост -> в голову), поэтому порядок записи: ПЕРВЫМ бит W[15],
//    затем W[0], W[1], ..., W[14] - тогда после 16 пар (OUT+спад)
//    кольцо = W. Проверено поведенческой моделью (scripts/).
//    чтение строк клавиатуры: IN 01h (row0..4 на A-шине, как в G07).
//
//  Карта IO: запись 01h/03h = бит D7 в кольцо; 02h = TX как в G07.
//  Чтение 00h/02h = RX (сброс готовности), 01h/03h = клавиатура +
//  tx_idle(D6); RX-флаг = SID (RIM). Звук: SND = sreg[15]; между OUT
//  и спадом SOD на SND коротко появляется записанный бит (глюк
//  бипера во время загрузки дисплея - не критично). TX 1.0417 Мбод
//  8N1 от CLKOUT/3; RX 2.083 Мбод.
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
  wire io_wr_tx_en = io_wr && addr_latch[1];

  // 4. v39G07_serial: последовательный порт дисплея/клавиатуры.
  //    Кольцевой 16-битный регистр, все секции сдвигаются ОДНОВРЕМЕННО
  //    на одну позицию по спаду SOD 1->0 (синхронизированный импульс
  //    sod_fall). Запись порта 01h (io_wr && addr_latch[0], порты 01h и
  //    03h) замещает голову кольца битом D7: он входит через SND и
  //    "продвигается" по цепочке последующими спадами SOD. Спад SOD
  //    без свежей записи = чистое вращение (хвост -> в голову).
  //    Запись и спад SOD в один такт не совпадают никогда (порядок
  //    команд софта: OUT, затем SIM); при совпадении приоритет записи.
  //    Бит данных берётся с A[7]: в фазе T2 I/O-записи это и есть D7
  //    шины данных (AD-шина несёт байт записи; disp/TX в G07 брали
  //    данные записи с тех же A-ног).
  (* keep = "true" *) reg [15:0] sreg = 16'h7F88;
  reg sod_s0 = 1'b0;                  // синхронизация асинхронного SOD
  reg sod_s1 = 1'b0;
  wire sod_fall = sod_s1 & ~sod_s0;   // спад 1->0, импульс 1 такт clk

  always @(posedge clk or posedge gsr_net) begin
    if (gsr_net) begin
      sreg   <= 16'h7F88;  // 0_SND | 1111111_seg | 1000_col | 1000_dig
      sod_s0 <= 1'b0;
      sod_s1 <= 1'b0;
    end else begin
      sod_s0 <= SOD;
      sod_s1 <= sod_s0;
      if (io_wr && addr_latch[0])
        sreg[15] <= A[7];              // порт 01h: D7 -> в голову (SND)
      else if (sod_fall)
        sreg <= {sreg[0], sreg[15:1]}; // спад SOD: сдвиг всей цепочки
    end
  end

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

  // 10. Выходы UART, статуса RX (SID), кольца дисплея/клавиатуры и звука
  assign SID  = rx_ready;
  assign SND  = sreg[15];
  assign seg  = {1'b1, sreg[14:8]};
  assign dig  = sreg[3:0];
  assign {col3, col2, col1, col0} = sreg[7:4];
endmodule


// =============================================================================
// Модуль: TXUART_CLKOUT_RALL (1.0417 Мбод 8N1 от фронтов CLKOUT)
// v39G07: вход переименован wr_en, внутренний load = wr_en && !tx_busy_q -
// повторный OUT 02h в фазе передачи не перезаписывает кадр (как в G05).
// v39G07_serial: на load поставлен keep - load остаётся ОБЩИМ МЦ-узлом
// (рецепт G08). Без keep cpldfit разворачивает его в каждого потребителя:
// shreg_D(k) 4->12-13 вх., tx_busy_T -> 21 вх., bo_cnt -> 11 вх.; общий
// узел load (2ПТ/11вх) сам не размещался - причина провала фита G07
// по входам ФБ (FB1/2/3/5 = 36/36, не разместились shreg<0..5> и D5_BUFR).
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

    // Гейт загрузки: в фазе передачи запись игнорируется (кадр не рвётся).
    // keep = узел не сворачивается в потребителей (см. шапку модуля).
    (* keep = "true" *) wire load = wr_en && !tx_busy_q;

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
