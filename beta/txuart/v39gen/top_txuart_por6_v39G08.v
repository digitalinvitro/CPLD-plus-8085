`timescale 1ns / 1ps
//=====================================================================
// v39G08 v2 (2026-11-29): КОМПАКТИЗАЦИЯ UART по итогам разбора отчёта
// фита retro_pcld_top.rpt (11-29, 1:01). Диагноз: по МЦ дизайн ВЛЕЗАЕТ
// (103+1 = 104 <= 108), фит валится по ФБ-ВХОДАМ: 208/216, свободно 8,
// а u_txuart/shreg<1> (5ПТ/11вх) разместить негде. Причина разворота
// входов: литерал записи (load = !tx_busy & addr2 & io_wr) и условие
// сдвига (baud_tick & !load) развёрнуты в КАЖДЫЙ бит shreg (5ПТ/11-13вх
// x9 бит ~ 100 ФБ-входов), busy_T - 17 вх., литерал baud_tick вшит во
// все 5 МЦ таймера.
// Изменения (всё проверено поведенческой симуляцией old-vs-new,
// scripts/tb_txuart_compact.v, tb_rxuart_compact.v):
//  1) TXUART: load зарегистрирован (load_q) -> D-вход бита shreg =
//     чистый мукс load_q ? ~din(k) : shreg(k+1) (2ПТ/3вх); tx_busy_q
//     УДАЛЁН (busy = |shreg: {~din,1} != 0 при любой din, включая 00 -
//     бит старта держит busy; сброс тем же тактом - 9-й baud_tick
//     обнуляет shreg); baud_tick остался общим комбинационным узлом,
//     сдвиг shreg - тем же тактом, что в v1. 15 -> 14 МЦ, ~-75 ФБ-вх.
//  2) RXUART_2M: state[1:0]+bit_cnt[2:0] (5 МЦ, bit_cnt 3-4ПТ/9вх)
//     заменены одним 4-битным nsamp {0,9,8..1,14,15}; ready = (nsamp==15)
//     (готовность удерживается до rd_clr, новый кадр в непрочитанный
//     байт не пишется); добавлена верификация старт-бита (глитч 1 клк
//     больше не даёт фантомный 0xFF - слабость старого RXUART_2M).
//     17 -> 16 МЦ, ~-15 ФБ-вх. Стоп проверяется в середине бита ->
//     SID на полбита раньше; d0..d7 и бодрейт без изменений.
//  3) keep на tx_baud_tick в top: таймер INTERVAL_TIMER получает общий
//     узел вместо развёрнутого в 5 МЦ литерала (bo1&!bo0&ck_q&!ck_d),
//     ~-12 ФБ-вх, +0 МЦ (узел и так нужен shreg-CE).
//  Отклонённые варианты: TX-такт от clk делителем /24 вместо ck_q/ck_d/
//  bo_cnt (5 МЦ против 4, +1 МЦ без выигрыша по входам); асинхронная
//  загрузка shreg через PRE/CLR (глитчи декода WRn на асинхронных
//  входах - риск порчи кадра); nsamp с отдельным ready_q (+1 МЦ без
//  защиты от перезаписи). DISP_PIPELINE (Т-триггеры 2ПТ/4вх), шинный
//  движок, FSM, RESET_CPU - уже минимальны, не тронуты.
//  Ожидаемый итог фита: ~104-105 требуемых МЦ (<=108), ФБ-входы
//  ~110-130/216 - запас, узкий shreg<1> размещается без проблем.
//=====================================================================

module retro_pcld_top(
    input  wire       cpld_clk,
    input  wire       cpld_rst,
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
    (* keep = "TRUE" *) input wire SND,
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

  BUFGSR u_bufgsr_rst (
      .I (cpld_rst),     // Входной пин 1 (GSR)
      .O (RST)  // Глобальная сеть сброса GSR
  );
  
  BUFG u_bufg_clk (
      .I (cpld_clk),     // Входной пин 29 (GCK1)
      .O (clk)           // Глобальная тактовая сеть GCK
  );


  assign CS1   = 1'b1;
  assign READY = 1'b1;

    reg t0_q;
    reg x1_q;
    reg x2_q;

    always @(posedge clk or posedge RST) begin
        if (RST) begin
            t0_q <= 1'b0;
            x1_q <= 1'b1; // Предустановка в 1 (PRE = RST) -> чистый FTCPE!
            x2_q <= 1'b0; // Сброс в 0 (CLR = RST) -> чистый FTCPE!
        end else begin
            t0_q <= ~t0_q;
            if (t0_q) begin
                x1_q <= ~x1_q;
                x2_q <= ~x2_q;
            end
        end
    end

    assign X1 = x1_q;
    assign X2 = x2_q;
     
    localparam [2:0] S_IDLE  = 3'd0,
                     S_ALE   = 3'd1,
                     S_T2    = 3'd2,
                     S_T2_RD = 3'd3,
                     S_T3_WR = 3'd4;
    reg [2:0] state      = S_IDLE;
    reg [7:0] addr_latch = 8'h00;
    reg [7:0] bus_reg    = 8'h00;
    wire bus_cycle = !RDn || !WRn;
     
    always @(posedge clk or posedge RST) begin
        if (RST) begin
            state      <= S_IDLE;
            addr_latch <= 8'h00;
        end else begin
            if (ALE)
                addr_latch <= A;
            case (state)
                S_IDLE: begin
                    if (ALE)
                        state <= S_ALE;
                    else if (bus_cycle)
                        state <= S_T2;
                end
                S_ALE: begin
                    if (!ALE) begin
                        if (bus_cycle)
                            state <= S_T2;
                        else
                            state <= S_IDLE;
                    end
                end
                S_T2: begin
                    if (!RDn)
                        state <= S_T2_RD;
                    else if (!WRn)
                        state <= S_T3_WR;
                    else
                        state <= S_IDLE;
                end
                S_T2_RD: begin
                    if (RDn)
                        state <= S_IDLE;
                end
                S_T3_WR: begin
                    if (WRn)
                        state <= S_IDLE;
                end
                default: state <= S_IDLE;
            endcase
        end
    end
     
    (* keep = "true" *) wire bus_ld_mem = (state == S_T2) && !RDn && !IOM;
    (* keep = "true" *) wire bus_ld_rx  = (state == S_T2) && !RDn &&  IOM && !addr_latch[1:1];
    (* keep = "true" *) wire bus_ld_wr  = (state == S_T2) && !WRn;
    (* keep = "true" *) wire io_wr      = (state == S_T2) && !WRn && IOM;
    wire rx_rd_clr = (state == S_T2_RD) && RDn && IOM && !addr_latch[1:1];
    wire io_rd_kb  = IOM && addr_latch[1:1];
    wire io_sh_seg   = io_wr && addr_latch[0:0];
    wire io_sh_dig   = io_wr && addr_latch[1:1];
    wire io_wr_tx_en = io_wr && addr_latch[2:2];
    
     wire [6:0] seg_q_n;
     DISP_PIPELINE u_disp (
        .clk       (clk),
        .gsr       (RST),
        .sh_seg_en (io_sh_seg),
        .sh_dig_en (io_sh_dig),
        .sod_in    (A[4]),
        .seg_out   (seg_q_n),
        .dig_out   (dig),
        .col_out   ({col3, col2, col1, col0})
    );
     
    assign seg = {1'b1, seg_q_n};
    wire       tx_busy_w;
    wire       tx_idle = ~tx_busy_w;
    (* keep = "true" *) wire tx_baud_tick; // общий узел: shreg-CE + INTERVAL_TIMER
                                           // (без keep литерал ck_rise&bo_cnt==2
                                           // разворачивается в 5 МЦ таймера)
    wire [7:0] rx_data;
    wire       rx_ready;
     
    TXUART_CLKOUT_RALL u_txuart (
        .clk       (clk),
        .gsr       (RST),
        .clkout_in (CLKOUT),
        .wr_en     (io_wr_tx_en),
        .din       (A),
        .tx_out    (TX),
        .tx_busy   (tx_busy_w),
        .baud_tick (tx_baud_tick)
    );
    
     RXUART_2M u_rxuart (
        .clk      (clk),
        .gsr      (RST),
        .rx_in    (RX),
        .rd_clr   (rx_rd_clr),
        .dout     (rx_data),
        .rx_ready (rx_ready)
    );
    assign SID = rx_ready;
    
     always @(posedge clk or posedge RST) begin
        if (RST) begin
            bus_reg <= 8'h00;
        end else begin
            if (bus_ld_mem)
                bus_reg <= D;
            else if (bus_ld_rx)
                bus_reg <= rx_data;
            else if (bus_ld_wr)
                bus_reg <= A;
        end
    end
     
    wire rd_drive = (state == S_T2_RD) && !RDn;
    wire wb_out   = ((state == S_T2) || (state == S_T3_WR)) && !WRn && !IOM;
    wire [7:0] kb_stat_byte = {rx_ready, tx_idle, 2'b11, row3, row2, row1, row0};
    
     assign A = rd_drive ? (io_rd_kb ? kb_stat_byte : bus_reg) : wb_out ? addr_latch : 8'bZZZZZZZZ;
    assign D = wb_out ? bus_reg : 8'bZZZZZZZZ;
    
     assign CSr_n = !(!IOM && !AH14);
    assign CS_n  = !(!IOM &&  AH14);
    assign OEr_n = !(!IOM && !AH14 && !RDn);
    assign OE_n  = !(!IOM &&  AH14 && !RDn);
    assign WE_n  = !(!IOM &&  AH14 && !WRn);
    assign READY = 1'b1;
     
    RESET_CPU u_reset_cpu (
        .clkout_in (CLKOUT),
        .gsr       (RST),
        .reset_in  (RESET_IN)
    );
/*     
    reg [4:0] tmr_cnt = 5'd0;
    always @(posedge clk or posedge RST) begin
        if (RST)
            tmr_cnt <= 5'd0;
        else if (tx_baud_tick)
            tmr_cnt <= tmr_cnt + 5'd1;
    end
    assign RST75 = tmr_cnt[4:4];
*/
INTERVAL_TIMER u_timer (
    .clk     (clk),
    .gsr     (RST),
    .tick_in (tx_baud_tick),
    .irq_out (RST75)
);	 
endmodule

module DISP_PIPELINE(
    input  wire       clk,
    input  wire       gsr,
    input  wire       sh_seg_en,
    input  wire       sh_dig_en,
    input  wire       sod_in,
    output wire [6:0] seg_out,
    output wire [3:0] dig_out,
    output wire [3:0] col_out
);
    reg [6:0] r_seg_n = 7'h00;
    reg [3:0] r_dig = 4'b0000;
    reg [3:0] r_col = 4'b0000;
    always @(posedge clk or posedge gsr) begin
        if (gsr) begin
            r_seg_n <= 7'h00;
            r_dig   <= 4'b0000;
            r_col   <= 4'b0000;
        end else begin
            if (sh_seg_en)
                r_seg_n <= {r_seg_n[5:0], sod_in};
            if (sh_dig_en) begin
                r_dig <= {~r_dig[0:0], ~r_dig[3:3], r_dig[2:2], r_dig[1:1]};
                r_col <= {~r_col[0:0], ~r_col[3:3], r_col[2:2], r_col[1:1]};
            end
        end
    end
    assign seg_out = ~r_seg_n;
    assign dig_out = {~r_dig[3:3], r_dig[2:0]};
    assign col_out = {~r_col[3:3], r_col[2:0]};
endmodule

// =============================================================================
// Модуль: TXUART_CLKOUT_RALL (1.0417 Мбод 8N1 от фронтов CLKOUT)
// v39G08 v2 (компактизация, см. шапку файла):
//  - load_q зарегистрирован: D бита shreg = мукс load_q ? ~din(k) : shreg(k+1);
//    литерал записи больше не разворачивается в каждый бит (5ПТ/11-13вх -> 2ПТ/3вх).
//    Запись срабатывает на 1 клк позже OUT: A-ноги несут данные весь T2/T3,
//    окно 1 клк недостижимо для софта (мин. машинный цикл 8085 >> 1 клк).
//  - tx_busy_q удалён: busy = |shreg. {~din,1'b1} != 0 при любой din (бит
//    старта), сброс - тем же тактом (9-й baud_tick обнуляет shreg).
//  - shreg[8:0]: кадр = {стоп(0), ~din, старт(1)}; Idle shreg=0 -> TX=1.
//  Регистры: ck_q, ck_d, bo_cnt[1:0], load_q, shreg[8:0] = 14 МЦ.
// =============================================================================
module TXUART_CLKOUT_RALL (
    input  wire       clk,        // 25 МГц
    input  wire       gsr,        // Активный высокий сброс (GSR)
    input  wire       clkout_in,  // 3.125 МГц (выход процессора CLKOUT)
    input  wire       wr_en,      // Строб записи байта (порт 04h)
    input  wire [7:0] din,        // Байт данных для передачи
    output wire       tx_out,     // Линия TX (Idle = 1)
    output wire       tx_busy,    // Флаг занятости передатчика
    output wire       baud_tick   // Выход тактирования (1.0417 МГц)
);
    // Сдвиговый регистр (инвертированная полярность хранения, сброс всех бит в 0)
    // В состоянии покоя (Idle) shreg = 9'h000, поэтому tx_out = ~shreg[0] = 1
    // Кадр при загрузке: {стоп-бит (0), инверсные данные (~din[7:0]), старт-бит (1)}
    (* keep = "true" *) reg [8:0] shreg = 9'h000;
    reg ck_q = 1'b0;
    reg ck_d = 1'b0;
    reg load_q = 1'b0;
    reg [1:0] bo_cnt = 2'b00;

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
    // busy = |shreg: после загрузки {~din,1'b1} != 0 (бит старта), кадр 0x00
    // тоже занят; сброс - такт, когда shreg обнулился (9-й baud_tick).
    wire tx_busy_w = |shreg;
    assign tx_busy = tx_busy_w;

    // Общий узел такта сдвига (3.125/3 = 1.0417 Мбод); keep в top.
    assign baud_tick = ck_rise & (bo_cnt == 2'd2);

    // Регистрируем строб записи: D-входы shreg становятся чистым муксом.
    always @(posedge clk or posedge gsr) begin
        if (gsr)
            load_q <= 1'b0;
        else
            load_q <= wr_en && !tx_busy_w;
    end

    // Делитель CLKOUT на 3 (для формирования бодрейта)
    always @(posedge clk or posedge gsr) begin
        if (gsr) begin
            bo_cnt <= 2'b00;
        end else if (load_q) begin
            bo_cnt <= 2'b00;
        end else if (ck_rise) begin
            if (bo_cnt == 2'd2)
                bo_cnt <= 2'b00;
            else
                bo_cnt <= bo_cnt + 2'd1;
        end
    end

    always @(posedge clk or posedge gsr) begin
        if (gsr) begin
            shreg <= 9'h000;
        end else if (load_q) begin
            // Старт-бит = 1 (на выходе TX станет 0), данные инвертированы (~din)
            shreg <= {~din, 1'b1};
        end else if (baud_tick) begin
            // Сдвиг вправо, старший бит заполняется 0 (на выходе TX станет 1)
            shreg <= {1'b0, shreg[8:1]};
        end
    end

    assign tx_out  = ~shreg[0:0];

endmodule

module RXUART_1M_OLD (
    input  wire       clk,
    input  wire       gsr,
    input  wire       rx_in,
    input  wire       rd_clr,
    output wire [7:0] dout,
    output wire       rx_ready
);
    reg [2:0] os_cnt     = 3'd0;
    reg [3:0] nsamp      = 4'd0;
    reg [7:0] rx_shreg_n = 8'h00;
    reg       ready_q    = 1'b0;
    wire os_tick = (os_cnt == 3'd7);
    always @(posedge clk or posedge gsr) begin
        if (gsr) begin
            os_cnt     <= 3'd0;
            nsamp      <= 4'd0;
            rx_shreg_n <= 8'h00;
            ready_q    <= 1'b0;
        end else begin
            if (rd_clr)
                ready_q <= 1'b0;
            if (nsamp == 4'd0) begin
                os_cnt <= 3'd0;
                if (!rx_in) nsamp <= 4'd9;
            end else begin
                if (os_tick) begin
                    os_cnt <= 3'd0;
                    if (nsamp == 4'd9) begin
                        if (!rx_in)
                            nsamp <= 4'd8;
                        else
                            nsamp <= 4'd0;
                    end else if (nsamp > 4'd1) begin
                        rx_shreg_n <= {~rx_in, rx_shreg_n[7:1]};
                        nsamp      <= nsamp - 4'd1;
                    end else if (nsamp == 4'd1) begin
                        rx_shreg_n <= {~rx_in, rx_shreg_n[7:1]};
                        nsamp      <= 4'd15;
                    end else begin
                        nsamp <= 4'd0;
                        if (rx_in)
                            ready_q <= 1'b1;
                    end
                end else begin
                    os_cnt <= os_cnt + 3'd1;
                end
            end
        end
    end
    assign dout     = ~rx_shreg_n;
    assign rx_ready = ready_q;
endmodule

// =============================================================================
// Модуль: RXUART_2M (2.083 Мбод, приём 0x00..0xFF, выборка в середине бита)
// v39G08 v2 (компактизация, см. шапку файла): state[1:0]+bit_cnt[2:0]+ready_q
// заменены ОДНИМ 4-битным счётчиком состояний nsamp:
//   0  = покой (ждём спад линии),
//   9  = верификация старта в середине старт-бита (глитч отсекается),
//   8..1 = выборки d0..d7 в середине каждого бита (каждые 480 нс),
//   14 = ожидание стопа, 15 = БАЙТ ГОТОВ - удерживается до rd_clr.
// ready = (nsamp==15): отдельный ready_q не нужен (-1 МЦ); кадр, пришедший
// при непрочитанном байте, игнорируется (защита от перезаписи - старый
// вариант затирал shreg). Стоп проверяется в середине бита -> готовность
// на полбита раньше, данные к этому моменту стабильно приняты.
// Регистры: os_cnt[3:0], nsamp[3:0], rx_shreg_n[7:0] = 16 МЦ.
// =============================================================================
module RXUART_2M (
    input  wire       clk,       // 25 МГц
    input  wire       gsr,
    input  wire       rx_in,
    input  wire       rd_clr,
    output wire [7:0] dout,
    output wire       rx_ready
);
    reg [3:0] os_cnt     = 4'd0; // фаза бита 0..11 (480 нс = 12 клоков, CH340G)
    reg [3:0] nsamp      = 4'd0; // счётчик состояний приёма (см. шапку модуля)
    reg [7:0] rx_shreg_n = 8'h00;

    wire os_half = (os_cnt == 4'd5);  // середина бита
    wire os_end  = (os_cnt == 4'd11); // конец бита

    always @(posedge clk or posedge gsr) begin
        if (gsr) begin
            os_cnt     <= 4'd0;
            nsamp      <= 4'd0;
            rx_shreg_n <= 8'h00;
        end else begin
            if (nsamp == 4'd0) begin
                os_cnt <= 4'd0;
                if (!rx_in)
                    nsamp <= 4'd9;                        // спад линии - старт
            end else begin
                if (os_half) begin
                    case (nsamp)
                        4'd9:  nsamp <= (!rx_in) ? 4'd8 : 4'd0;      // верификация старта
                        4'd1:  begin                                 // d7 - последний бит данных
                                   rx_shreg_n <= {~rx_in, rx_shreg_n[7:1]};
                                   nsamp      <= 4'd14;
                               end
                        4'd14: nsamp <= (rx_in) ? 4'd15 : 4'd0;      // стоп валиден -> READY
                        4'd15: ;                                     // READY держится до rd_clr
                        default: begin                               // выборки d0..d6
                                   rx_shreg_n <= {~rx_in, rx_shreg_n[7:1]};
                                   nsamp      <= nsamp - 4'd1;
                               end
                    endcase
                end
                os_cnt <= os_end ? 4'd0 : (os_cnt + 4'd1);
            end
            if (rd_clr && (nsamp == 4'd15))
                nsamp <= 4'd0;                        // чтение порта 00h снимает готовность
        end
    end

    assign dout     = ~rx_shreg_n;
    assign rx_ready = (nsamp == 4'd15);
endmodule

module RXUART_1M (
    input  wire       clk,       // 25 МГц
    input  wire       gsr,
    input  wire       rx_in,
    input  wire       rd_clr,
    output wire [7:0] dout,
    output wire       rx_ready
);
    reg [4:0] os_cnt     = 5'd0; // делитель 0..24 (ровно 1.000 Мбод при 25 МГц!)
    reg [3:0] nsamp      = 4'd0; // 0=ожидание, 1=старт, 2..9=данные, 10=стоп
    reg [7:0] rx_shreg_n = 8'h00;
    reg       ready_q    = 1'b0;

    wire os_half = (os_cnt == 5'd12); // середина бита (480 нс)
    wire os_end  = (os_cnt == 5'd24); // конец бита (1000 нс = 1 Мбод)

    always @(posedge clk or posedge gsr) begin
        if (gsr) begin
            os_cnt     <= 5'd0;
            nsamp      <= 4'd0;
            rx_shreg_n <= 8'h00;
            ready_q    <= 1'b0;
        end else begin
            if (rd_clr)
                ready_q <= 1'b0;

            if (nsamp == 4'd0) begin
                os_cnt <= 5'd0;
                if (!rx_in)
                    nsamp <= 4'd1; // старт-бит
            end else begin
                if (os_half) begin
                    if (nsamp == 4'd1) begin
                        if (rx_in) nsamp <= 4'd0; // помеха
                    end else if (nsamp == 4'd10) begin
                        if (rx_in) ready_q <= 1'b1; // стоп-бит -> SID = 1
                    end else begin
                        rx_shreg_n <= {~rx_in, rx_shreg_n[7:1]};
                    end
                end

                if (os_end) begin
                    os_cnt <= 5'd0;
                    if (nsamp == 4'd10)
                        nsamp <= 4'd0;
                    else
                        nsamp <= nsamp + 4'd1;
                end else begin
                    os_cnt <= os_cnt + 5'd1;
                end
            end
        end
    end

    assign dout     = ~rx_shreg_n;
    assign rx_ready = ready_q;
endmodule

module RESET_CPU(

    input  wire clkout_in,
    input  wire gsr,
    output wire reset_in
);
    reg [1:0] tt = 2'b00;
    always @(posedge clkout_in or posedge gsr) begin
        if (gsr)
            tt <= 2'b00;
        else if (tt != 2'b11)
            tt <= tt + 2'b01;
    end
    assign reset_in = (tt == 2'b11);
endmodule

module INTERVAL_TIMER (
    input  wire clk,
    input  wire gsr,
    input  wire tick_in,   // Входной строб (tx_baud_tick ~1,04 МГц)
    output wire irq_out    // Выход на пин RST75 (~4,07 кГц)
);
    // Младший 4-битный каскад (?16) привязываем к FB4, где есть сигналы tick_in
    reg [2:0] tmr_lo = 3'd0;

    // Старший 4-битный каскад (ещё ?16, итого ?256) привязываем к FB6 к пину RST75
    reg [1:0] tmr_hi = 2'd0;

    // Общий строб переноса между каскадами (экономит входы в FB6)
    wire carry_lo = tick_in && (&tmr_lo);

    always @(posedge clk or posedge gsr) begin
        if (gsr) begin
            tmr_lo <= 3'd0;
            tmr_hi <= 2'd0;
        end else begin
            if (tick_in)
                tmr_lo <= tmr_lo + 3'd1;
            if (carry_lo)
                tmr_hi <= tmr_hi + 2'd1;
        end
    end

    assign irq_out = tmr_hi[1];
endmodule
