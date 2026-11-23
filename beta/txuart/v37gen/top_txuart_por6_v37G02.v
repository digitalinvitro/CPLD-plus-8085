`timescale 1ns/1ps
//=====================================================================
// top_txuart_por6_v37G02.v - retro_pcld_top + TXUART (домен CLKOUT) +
// СВОБОДНЫЙ ТАЙМЕР->RST 7.5 + АППАРАТНЫЙ ПЕРЕДАТЧИК UART 8N1 625 000 бод
// (такт ядра передатчика - пин CLKOUT 3,125 МГц / 5, BAUD_DIV=5; mod-25
// предделитель clk-домена остаётся ТОЛЬКО для tick_step джиффи-таймера).
//
// ИЗМЕНЕНИЯ ВЕРСИИ v37G02 (TXUART в домене CLKOUT, 625 000 бод):
//  1. Ядро передатчика перенесено в домен CLKOUT (пин P83/нога 37,
//     3,125 МГц = X1/2): новый модуль TXUART в конце файла - shreg 9 +
//     bit_cnt 4 + baud_cnt(mod-5) 3 = 16 МЦ, бит-тайм ровно 5 тактов
//     CLKOUT = 1600 нс, кадр 8N1 16 мкс. Старое clk-ядро UART
//     (shreg + bit_cnt + старый io_wr_tx, всего 19 МЦ) удалено.
//  2. Новый строб загрузки io_wr_tx = !WRn && IOM && addr_latch[2:0]==100
//     && tx_idle && RESET_IN - по УРОВНЮ !WRn: процессор держит WRn# в
//     T2..T3 дольше периода CLKOUT, в окно записи попадает ровно один
//     край CLKOUT (симуляция S2: 144/144, свип WRn# 330-640 нс). Старый
//     строб (state==S_T2)&&!WRn&&IOM шириной 40-120 нс накрывал край
//     CLKOUT лишь в 10/32/38% записей - TX терялся бы в 62-90% случаев
//     (S6). keep снят: decode идёт комбинацией в T/D-птермы CLKOUT-FF.
//  3. Данные загружаются напрямую с A-сетей ({A,1'b0}), НЕ через bus_reg
//     (тот захватывается позже и только на чтениях): 8085A выставляет
//     данные ДО падения WRn# (порядок по t_DC даташита).
//  4. mod-25 baud_cnt/baud_tick в clk-домене СОХРАНЕНЫ - только ради
//     tick_step (джиффи-таймер 4,096 мс), удалять нельзя (раздел 4
//     v37G02_txuart_clkout_analysis.md).
//  5. tx_idle читается назад на шину A (статус-бит порта 03h) - теперь
//     выход модуля TXUART. Ресурсы: 102 + 2 = 104/108 МЦ (с снятием
//     keep в v37G03 - 100/108). Метка таймера «1,024 мс» исправлена
//     на 4,096 мс (DEVLOG 2026-11-22-1, п.3).
//  6. Ре-фит cpldfit у владельца обязателен (пара jed+hex - новая,
//     retro_pcld_top.jed v37G01 остаётся fallback); UCF не меняется
//     (пин 83 остаётся входом CLKOUT). tb-регресс: tb_v37g02.v
//     (beta/txuart/v37gen, Icarus 12.0).
//
// ИЗМЕНЕНИЯ ВЕРСИИ v37G01 (переход на глобальный асинхронный сброс GSR):
//  1. Глобальный асинхронный сброс (GSR) от пина RST (P1, активная "1"):
//     Удалена 8-триггерная схема синхронизации/окна сброса (rst_meta,
//     rst_sync, rst_press, rst_win, clkout_d, cpu_rst_r -> -8 МЦ).
//     Все сбрасываемые регистры ядра TXUART и шинного движка переведены
//     на прямой асинхронный сброс `always @(posedge clk or posedge RST)`
//     с активной единицей `if (RST)`, что позволяет фиттеру завести
//     RST на выделенную глобальную сеть GSR без траты входов FB и термов.
//  2. Модуль RESET_CPU (+3 МЦ, чистая экономия 5 макроячеек):
//     Формирует сигнал RESET_IN (активный "0") для процессора ИМ1821ВМ85А
//     (вывод 36) на базе 3-битного синхронного счетчика (3 счетных T-триггера
//     FTCPE, тактируемых от CLKOUT 3.125 МГц), обеспечивая гарантированную
//     длительность сброса 3.03..4.00 полных такта CLKOUT после отпускания
//     кнопки RST, а также при включении питания (POR, INIT=3'b000).
//  3. Защита шинных операций в окне сброса CPU:
//     В условиях `io_wr_tx` и перехода автомата в `S_WB1` (запись в ОЗУ)
//     вместо `!cpu_rst_r` используется `RESET_IN` (блокировка шинных
//     операций в течение всех 4 тактов удержания процессора в сбросе).
//=====================================================================
// СОСТАВ ФАЙЛА (сверху вниз):
//  1. Такт и строб: делитель /4 (t0_q/x1_q), X1/por_ce;
//  2. Сброс CPU (модуль RESET_CPU на 3 счетных T-триггерах FTCPE);
//  3. FSM шины i8085 (T1H/T2/WB1..WB4, writeback в ОЗУ);
//  4. Ядро TXUART (домен CLKOUT): OUT 04h -> кадр 8N1 625 000 бод;
//  5. Тристейт-драйверы A/D, декод памяти;
//  6. Остров свободного таймера RST 7.5 (шаг 4 мкс, вне сети сброса);
//  7. Порты индикации/звука/клавиатуры;
//  8. Модуль RESET_CPU с подробным описанием трассировки GSR и UCF.
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
    output wire       RST75,        // P75 cpu15, U3.7 (CPU.RST 7.5, edge-защёлка, МАСКИРУЕМЫЙ): импульс 1 клк на каждый тик 4 мкс
    // ---- soft-UART транзиты ----
    output wire       SID,          // P73 cpu17, нога 5 (CPU.SID): транзит RX -> приём (RIM 20h)
    output wire       TX,           // P39: цепь платы «RX» -> CH340G.RXD; выход модуля TXUART (домен CLKOUT, 625000)
    // ---- индикация и звук (выходы активным 0) ----
    output wire [7:0] seg,          // {dp56,g,f,e,d,c,b,a} = P60/5/66/58/57/61/62/45
    output wire [3:0] dig,          // dig0..3 = P6/63/65/48 -> R -> VT1..VT4
    output wire       SND,          // P67 -> BUZZER1.1 (пассивный, прямой бит; A4 порта 01h)
    // ---- наблюдатели: «мёртвые» пины как Hi-Z входы (* keep *) ----
    (* keep = "TRUE" *) output wire X2,        // P69 cpu20, нога 2: ОТКРЫТЫЙ ВХОД (Hi-Z)
    (* keep = "TRUE" *) input wire RSTOUT,    // P70 cpu19, нога 3
    (* keep = "TRUE" *) input wire SOD,       // P72 cpu18, нога 4 (CPU.SOD): наблюдатель без нагрузки
    (* keep = "TRUE" *) input wire INTAn,     // P80 cpu11, нога 11
    (* keep = "TRUE" *) input wire HLDA,      // P82 cpu9,  нога 38
    (* keep = "true" *) input wire CLKOUT,    // P83 cpu8,  нога 37: 3,125 МГц = X1/2 (тактирует модули RESET_CPU и TXUART)
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
  reg x2_q = 1'b0;   // противофаза: x2_q ^= t0_q, INIT=0; X1 INIT=1 ->
                     // инвариант x2^x1 = 1 с 1-го такта; БРАК = INIT X2=SET

  always @(posedge clk) begin
    t0_q <= ~t0_q;             // clk/2
    if (t0_q) x1_q <= ~x1_q;   // clk/4, 50%
    if (t0_q) x2_q <= ~x2_q;   // v2.8.7: противофаза (T = t0_q - ТОТ ЖЕ провод, что у x1_q -> X2^X1 инвариант, 0^1 = 1; БРАК = INIT X2 = SET)
  end

  assign X1     = x1_q;             // 6,25 МГц, период ровно 160 нс, duty 1/2
  assign X2 = x2_q; 

  assign por_ce = ~t0_q & ~x1_q;    // 1 такт 40 нс за период 160 нс

  //=============================================================
  // 2. Сброс процессора ИМ1821ВМ85А (модуль RESET_CPU)
  //    Выдает задержанный на 3.03..4.00 полных такта CLKOUT сигнал
  //    RESET_IN (активный 0) после отпускания RST и при старте (POR).
  //=============================================================
  RESET_CPU u_reset_cpu (
    .clk_out  (CLKOUT),
    .RST      (RST),
    .RESET_IN (RESET_IN)
  );

  //=============================================================
  // 3. Автомат шины: 7 состояний = 3 триггера (WB1..WB4 ЗАЩИЩЕНЫ от ALE)
  //=============================================================
  localparam [2:0] S_IDLE = 3'd0,   // ожидание ALE; A/D в Hi-Z; /OE включён
                   S_T1H  = 3'd1,   // T1: CPU держит адрес на A-сетях; идёт захват
                   S_T2   = 3'd2,   // строб: чтение - выдача данных на A; запись - захват
                   S_WB1  = 3'd3,   // WB: адрес на A + данные на D (t_AS 40 нс до /WE)
                   S_WB2  = 3'd4,   // /WE=0 - импульс НАЧАЛСЯ: защищён от ALE
                   S_WB3  = 3'd5,   // /WE=0 (импульс = 2 тика = 80 нс >= t_WP ОЗУ)
                   S_WB4  = 3'd6;   // /WE=1: удержание адреса/данных (t_AH/t_DH памяти)

  (* fsm_encoding = "compact" *) reg [2:0] state = S_IDLE;
  reg       rd_seen = 1'b0;    // строб чтения замечен в T2
  reg       wr_seen = 1'b0;    // строб записи замечен в T2

  // Захваченные шинные регистры
  reg [7:0] addr_latch = 8'h00;  // адрес с A-сетей (T1)
  reg [7:0] bus_reg    = 8'h00;  // данные: чтение (с D-сети в T1) ИЛИ запись (с A-сети в T2)

  // Порты индикации/звука: захват по записи в порт при IO/M#=1
  reg [6:0] seg_q   = 7'h40;     // INIT=40 - горит ТОЛЬКО сегмент g (самотест «----»)
  reg [3:0] dig_q   = 4'hF;      // INIT=F - все 4 разряда выбраны
  reg       snd_q   = 1'b0;
  reg [3:0] kbcol_q = 4'h0;      // колонки клавиатуры (вне сброса - скан не гасится)

  wire io_rd_kb = IOM & ~addr_latch[2] & addr_latch[1] & addr_latch[0]; // чтение 03h (KBROW)

  (* keep = "true" *) wire in_wb      = (state >= S_WB1);
  wire                     in_welo    = (state == S_WB2) || (state == S_WB3);
  wire                     wr_phase   = (state >= S_T2);
  wire                     wb_out     = in_wb;
  (* keep = "true" *) wire rd_drive   = (state == S_T2) && rd_seen && !RDn && !ALE;
  (* keep = "true" *) wire fsm_wrdone = wr_seen && WRn;
  (* keep = "true" *) wire fsm_rddone = rd_seen && RDn;
  (* keep = "true" *) wire io_wr      = (state == S_T2) && !WRn && IOM;
  
    // СТАЛО (правильно: защелкиваем данные из ПЗУ/ОЗУ во время активного RDn = 0):
  (* keep = "true" *) wire bus_ld_t1  = (state == S_T2) && !RDn && !IOM;
  (* keep = "true" *) wire bus_ld_t2  = (state == S_T2) && !WRn;
   //  БЫЛО (ошибка: защелкивает данные с D еще во время ALE, до прихода RDn!):
  //(* keep = "true" *) wire bus_ld_t1  = (state == S_T1H) && ALE && !IOM;
  //(* keep = "true" *) wire bus_ld_t2  = (state == S_T2) && !WRn;

  //=============================================================
  // 4. TXUART: АППАРАТНЫЙ ПЕРЕДАТЧИК UART 8N1 625 000 бод (домен CLKOUT)
  //    v37G02: ядро передатчика тактируется пином CLKOUT (3,125 МГц);
  //    mod-25 предделитель clk-домена сохранён ТОЛЬКО для tick_step.
  //=============================================================

  // --- mod-25 предделитель clk-домена: только для tick_step (таймер!) ---
  // Удаление mod-25 ради "-5 МЦ" убивает tick_step и джиффи 4,096 мс
  // (v37G02_txuart_clkout_analysis.md, раздел 4).
  localparam [4:0] BAUD_DIV = 5'd25;  // clk 25 МГц / 25 = тик 1 мкс (tick_step)
  reg [4:0] baud_cnt = 5'd0;    // mod-25 свободным ходом (CLR-ветка GSR)

  (* keep = "true" *) wire baud_tick = (baud_cnt == (BAUD_DIV - 5'd1));

  always @(posedge clk or posedge RST) begin
    if (RST) begin
      baud_cnt <= 5'd0;     // (CLR-ветка GSR)
    end else begin
      baud_cnt <= baud_tick ? 5'd0 : baud_cnt + 5'd1;
    end
  end

  // --- ядро TXUART в домене CLKOUT (модуль TXUART - в конце файла) ---
  // Новый строб загрузки TXDATA (порт 04h): по УРОВНЮ !WRn (процессор
  // держит его в T2..T3, дольше периода CLKOUT - ровно одна загрузка,
  // симуляция S2 144/144). Старый строб io_wr (1-3 такта clk = 40-120 нс)
  // промахивался бы мимо края CLKOUT в 62-90% записей (S6). Без keep:
  // decode идёт комбинацией в T/D-птермы CLKOUT-триггеров модуля.
  wire tx_idle;   // выход модуля TXUART; читается назад на шину A (порт 03h)

  wire io_wr_tx = !WRn
              && IOM
              && addr_latch[2] && !addr_latch[1] && !addr_latch[0]
              && tx_idle && RESET_IN;

  TXUART u_txuart (
    .clk_out (CLKOUT),
    .RST     (RST),         // GSR: кадр рвётся, TX -> idle '1' (SET-ветка)
    .wr_en   (io_wr_tx),
    .data_in (A),           // данные напрямую с A-сетей (НЕ bus_reg)
    .tx_idle (tx_idle),
    .tx      (TX)
  );

  //=============================================================
  // 5. Шинный движок и порты индикации/звука
  //    Глобальный асинхронный сброс по активной "1" пина RST (GSR).
  //=============================================================
  always @(posedge clk or posedge RST) begin
    if (RST) begin
      state      <= S_IDLE;
      rd_seen    <= 1'b0;
      wr_seen    <= 1'b0;
      addr_latch <= 8'h00;
      bus_reg    <= 8'h00;
      seg_q      <= 7'h40;   // самотест «----» (SET для бита 6, CLR для остальных)
      dig_q      <= 4'hF;    // самотест «----» (SET для всех 4 бит)
      snd_q      <= 1'b0;
    end else begin
      if (state == S_T1H && ALE)
        addr_latch <= A;

      if (bus_ld_t1 || bus_ld_t2)
        bus_reg <= bus_ld_t1 ? D : A;

      if (io_wr) begin
        case (addr_latch[2:0])
          3'b000: seg_q <= A[6:0];
          3'b001: begin
            dig_q <= A[3:0];
            snd_q <= A[4];
          end
          default: ;
        endcase
      end

      if (state == S_T2 && !RDn) rd_seen <= 1'b1;
      if (state == S_T2 && !WRn) wr_seen <= 1'b1;

      if (ALE && state == S_T2 && !(fsm_wrdone || fsm_rddone)) begin
        state   <= S_IDLE;
        rd_seen <= 1'b0;
        wr_seen <= 1'b0;
      end else begin
        case (state)
          S_IDLE: if (ALE) state <= S_T1H;
          S_T1H:  if (!ALE) state <= S_T2;
          S_T2: begin
            if (fsm_wrdone) begin
              wr_seen <= 1'b0;
              // Запись в ОЗУ (writeback) разрешена только при RESET_IN == 1
              state <= (!IOM && A15 && RESET_IN) ? S_WB1 : S_IDLE;
            end else if (fsm_rddone) begin
              rd_seen <= 1'b0;
              state   <= S_IDLE;
            end
          end
          S_WB1: state <= S_WB2;
          S_WB2: state <= S_WB3;
          S_WB3: state <= S_WB4;
          S_WB4: state <= S_IDLE;
          default: state <= S_IDLE;
        endcase
      end
    end
  end

  //=============================================================
  // 6. СВОБОДНЫЙ ТАЙМЕР -> RST 7.5 (P75) и колонки клавиатуры
  //    Намеренно ВНЕ сети сброса (свободный ход 4 мкс).
  //=============================================================
  wire tick_step = por_ce & baud_tick;   // 100 клк = 4 мкс; baud_tick от mod-25 clk-домена (v37G02: сохранён только ради этой строки)

  // 10-битный счетчик: джиффи = 1024 x 4 мкс = 4,096 мс (244,14 Гц).
  // (Метка «1,024 мс» = 256 x 4 мкс была арифметической ошибкой -
  // исправлено в v37G02, DEVLOG 2026-11-22-1 п.3.)
  reg [9:0] tmr_cnt = 10'd0;
  reg       RST75_r = 1'b0;

  // Импульс 1 такт clk (40 нс) ровно 1 раз в 4,096 мс при переполнении 10-битного счетчика:
  wire timer_irq_tick = tick_step && (&tmr_cnt);

  always @(posedge clk) begin
    RST75_r <= timer_irq_tick;
    if (tick_step)
      tmr_cnt <= tmr_cnt + 10'd1;
  end
/*
  reg [1:0] tmr_cnt = 2'h0;
  reg       RST75_r = 1'b0;


  always @(posedge clk)
    RST75_r <= tick_step;

  always @(posedge clk) begin
    if (tick_step) tmr_cnt <= tmr_cnt + 2'd1;
  end
*/
  (* keep = "true" *) wire kbcol_wr06 = io_wr && (addr_latch[2:0] == 3'b110);

  always @(posedge clk)
    if (kbcol_wr06)
      kbcol_q <= A[7:4];

  assign RST75 = RST75_r;

  //=============================================================
  // 7. Тристейт-драйверы шины и декод памяти
  //=============================================================
  assign A = rd_drive ? (io_rd_kb ? {tx_idle, tmr_cnt[9:8], row4, row3, row2, row1, row0}
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
// Модуль: RESET_CPU
// Назначение: Формирователь задержанного сигнала сброса RESET_IN (активный "0",
//             длительность 3.03..4.00 полных такта clk_out) для процессора
//             ИМ1821ВМ85А (вывод 36) на базе 3-битного синхронного счетчика.
// Целевая ПЛИС: Xilinx XC95108 (корпус PQ100)
//
// -----------------------------------------------------------------------------
// РЕКОМЕНДАЦИИ ПО ЗАВЕДЕНИЮ АСИНХРОННОГО СБРОСА И НАСТРОЙКЕ .UCF ФАЙЛА:
// -----------------------------------------------------------------------------
// 1. Привязка в файле ограничений (.ucf):
//    В корпусе PQ100 выделенный вход глобальной сети сброса/установки (GSR)
//    находится на 1-м выводе микросхемы (P1). Для гарантированного захвата
//    глобальной линии GSR пропишите в .ucf файле:
//
//      NET "RST" LOC = "P1" | BUFG = SR;
//
// 2. Плюсы использования глобальной сети GSR в XC95108:
//    - Сигнал сброса разводится по выделенной аппаратной шине ко всем 108
//      макроячейкам кристалла с минимальным перекосом фронтов (skew).
//    - Не расходуются входы функциональных блоков (36 входов FB) и термы-
//      произведения (Product Terms) в матрице AND.
//
// 3. ПОДВОДНЫЕ КАМНИ АРХИТЕКТУРЫ XC9500 (5-вольтовая серия), КОТОРЫЕ ВАЖНО УЧЕСТЬ:
//    - Единая полярность GSR на весь кристалл: В отличие от более новых семейств
//      XC9500XL/XV, в базовом XC95108 инвертор полярности GSR общий для всех
//      макроячеек. Во ВСЕХ модулях вашего проекта асинхронный сброс должен
//      срабатывать строго по одному уровню (здесь — по активной "1":
//      always @(posedge clk or posedge RST) if (RST) ...). Если хотя бы один
//      триггер в проекте написать с сбросом по "0" (if (!RST)), фиттер вынесет
//      его на обычную матрицу FastCONNECT, потратив вход FB и терм-произведение.
//    - Одновременная установка в "1" (Preset) и сброс в "0" (Clear) разрешены:
//      Внутри одного и того же условия `if (RST)` одни регистры проекта можно
//      сбрасывать в 1'b0, а другие — устанавливать в 1'b1. В каждой макроячейке
//      есть отдельные мультиплексоры для входов AR и AP, поэтому оба действия
//      пройдут по одной глобальной сети GSR без потери ресурсов.
//    - Свободный вывод P1 при внутреннем управлении: Если в будущем вместо
//      внешней кнопки на P1 вы решите завести на GSR внутренний сигнал ПЛИС
//      через BUFG=SR, физический вывод P1 на плате обязан висеть в воздухе
//      (не подключаться ни к земле, ни к питанию), так как буфер GSR сделает
//      его активным выходом. При подаче кнопки снаружи на P1 конфликта нет.
//    - Проверка в отчете фиттера (.rpt): После компиляции откройте файл отчета
//      и в разделе "Global Resources" убедитесь в наличии строки:
//      "RST mapped to global set/reset net GSR."
// =============================================================================
module RESET_CPU(
  input  wire clk_out,   // 3.125 МГц (выход тактового генератора процессора)
  input  wire RST,       // Кнопка на P1 (GSR), подтяжка к GND, активный уровень = 1
  output wire RESET_IN   // Выход на 36-й пин ИМ1821ВМ85А (активный уровень = 0)
);
  // При включении питания (POR) стартуем с 3'b000, чтобы выдать стартовый
  // импульс сброса процессору. Если POR не нужен, замените на 3'b100.
  reg [2:0] tt = 3'b000;

  assign RESET_IN = tt[2];      // Прямой выход со старшего триггера (без глитчей!)
  wire count_en   = !tt[2];     // Считаем, пока tt[2] == 0

  always @(posedge clk_out or posedge RST) begin
    if (RST) begin
      tt[2:0] <= 3'b000;        // Асинхронный сброс через GSR, RESET_IN падает в 0
    end else if (count_en) begin
      tt[0] <= !tt[0];          // FTCPE (T = !tt[2])
      if (tt[0])
        tt[1] <= !tt[1];        // FTCPE (T = !tt[2] & tt[0])
      if (tt[0] && tt[1])
        tt[2] <= !tt[2];        // FTCPE (T = !tt[2] & tt[0] & tt[1]) -> стоп на 1
    end
  end
endmodule


// =============================================================================
// Модуль: TXUART (v37G02)
// Назначение: аппаратный передатчик UART 8N1 625 000 бод в домене CLKOUT.
//             Тактируется пином CLKOUT процессора (3,125 МГц = X1/2, P83),
//             бит-тайм ровно 5 тактов CLKOUT = 1600 нс, кадр 8N1 16 мкс.
//             Регистры: shreg 9 + bit_cnt 4 + baud_cnt(mod-5) 3 = 16 МЦ.
// Строб загрузки (wr_en = io_wr_tx): !WRn && IOM && адрес 04h && tx_idle
//             && RESET_IN - по УРОВНЮ !WRn: процессор держит WRn# в T2..T3
//             дольше периода CLKOUT, поэтому в каждом окне записи край
//             CLKOUT попадает внутрь ровно один раз (симуляция S2: свип
//             WRn# 330-640 нс x офсеты падения x фазы CLKOUT = 144/144;
//             под-периодная ширина WRn# гарантии НЕ даёт). Данные берутся
//             напрямую с A-сетей: 8085A выставляет данные ДО падения WRn#
//             (порядок по t_DC даташита). Загрузка игнорируется во время
//             кадра (tx_idle) и в окне сброса (RESET_IN=0).
// Глобальный асинхронный сброс: RST (GSR, активная "1") -> shreg = all '1'
//             (TX = idle '1'), bit_cnt = 0, baud_cnt = 0; кадр рвётся.
// Проверено: сквозная симуляция RTL 1:1 с моделью цикла записи 8085A и
//             приёмником CH340 - сценарии S1-S8 PASS
//             (v37G02_txuart_clkout_analysis.md, scripts/txuart_clkout_sim.py);
//             tb-регресс этого файла: beta/txuart/v37gen/tb_v37g02.v
//             (Icarus 12.0, сценарии T1-T4 PASS).
// Целевая ПЛИС: Xilinx XC95108 (корпус PQ100); CLKOUT-триггеры должны
//             лечь в FB2/FB3/FB4 с Product-Term Clock (ёмкость 21 >= 19 МЦ,
//             PTC на стр. 741 rpt). GSR-полярность: активная "1", как и
//             во всех модулях проекта (см. примечания у RESET_CPU).
// =============================================================================
module TXUART(
  input  wire       clk_out,   // 3,125 МГц CLKOUT процессора (P83, нога 37)
  input  wire       RST,       // GSR (P1), активная "1"
  input  wire       wr_en,     // io_wr_tx: !WRn && IOM && addr 04h && tx_idle && RESET_IN
  input  wire [7:0] data_in,   // данные с A-сетей напрямую (AD0-AD7 в T2)
  output wire       tx_idle,   // 1 = передатчик свободен (статус-бит порта 03h)
  output wire       tx         // последовательный выход -> CH340G.RXD (P39)
);
  localparam [2:0] BAUD_DIV = 3'd5;   // 3,125 МГц / 5 = 625 000 бод 8N1

  reg [8:0] shreg    = 9'h1FF;  // [8:1] данные, [0] -> TX (SET-ветка GSR: idle = '1')
  reg [3:0] bit_cnt  = 4'd0;    // 1..10 = бит-тайм кадра, 0 = idle (CLR-ветка GSR)
  reg [2:0] baud_cnt = 3'd0;    // mod-5 свободным ходом (CLR-ветка GSR)

  wire baud_tick = (baud_cnt == (BAUD_DIV - 3'd1));
  assign tx_idle = ~|bit_cnt;

  always @(posedge clk_out or posedge RST) begin
    if (RST) begin
      shreg    <= 9'h1FF;   // idle '1' (SET-ветка GSR)
      bit_cnt  <= 4'd0;     // idle (CLR-ветка GSR)
      baud_cnt <= 3'd0;     // (CLR-ветка GSR)
    end else begin
      baud_cnt <= baud_tick ? 3'd0 : baud_cnt + 3'd1;

      if (wr_en && tx_idle) begin
        shreg    <= {data_in, 1'b0};   // старт-бит '0' в [0], данные в [8:1]
        bit_cnt  <= 4'd1;
        baud_cnt <= 3'd0;
      end else if (baud_tick) begin
        shreg <= {1'b1, shreg[8:1]};   // LSB-first; бит-8 и стоп = '1'
      end

      if (|bit_cnt && baud_tick) begin
        bit_cnt <= (bit_cnt == 4'd10) ? 4'd0 : bit_cnt + 4'd1;
      end
    end
  end

  assign tx = shreg[0];
endmodule
