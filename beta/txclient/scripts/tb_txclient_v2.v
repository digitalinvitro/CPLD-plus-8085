//=====================================================================
// tb_txclient_v2.v - тестбенч TXCLIENT v2 (beta/txclient) для Icarus Verilog.
// В песочнице разработки iverilog недоступен - ПРОГНАТЬ У ВЛАДЕЛЬЦА:
//   iverilog -o tb_v2.vvp tb_txclient_v2.v ../top_txclient_v2_utf8.v
//   vvp tb_v2.vvp
// Эталонная модель - scripts/sim_txclient_v2.py (37/37 ПАСС); при расхождении
// смотреть сначала её. Проверяет: запись ОЗУ (пакет [hi][lo][data], бит ровно
// 13 тиков, HOLD в T1 и ДО КОНЦА ПАКЕТА, релиз в стоп-бите 3-го кадра),
// страницу-исключение FFxx, IO, ЧТЕНИЕ ОЗУ (без HOLD вовсе), бэку-ту-бэк.
// Порты/делитель/POR v3.9.2 не проверяются (там свой TB).
`timescale 1ns/1ns
module tb_txclient_v2();
  localparam BAUD_DIV = 13;
  localparam T_T1 = 7, T_STROBE = 9;

  reg clk = 0; always #20 clk = ~clk;          // 25 МГц
  reg RST = 1, ALE = 0, WRn = 1, RDn = 1, IOM = 0, HLDA = 0;
  reg S0 = 0, S1 = 0;                           // статус ВМ85А: MW = S0=1,S1=0
  reg  [7:0] A  = 8'h00;                        // AD0-AD7 (A-сети)
  reg  [7:0] AH = 8'h00;                        // A15,AH14..AH8 (наблюдатели + hi-байт пакета)
  wire [7:0] D;  assign D = 8'hZZ;              // чтения не проверяем данные
  wire [7:0] seg; wire [3:0] dig; wire SND, SNDd;
  wire CSr_n, OEr_n, CS_n, OE_n, WE_n, CS1, X1, X2, READY, RESET_IN;
  wire SID, TX, HOLD, RSTOUT, INTAn, CLKOUT, S0w, S1w, RX;
  wire col0, col1, col2, col3; reg row0 = 1, row1 = 1, row2 = 1, row3 = 1, row4 = 1;

  retro_pcld_top dut(.clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn),
    .IOM(IOM), .A15(AH[7]), .A(A), .D(D), .CSr_n(CSr_n), .OEr_n(OEr_n),
    .CS_n(CS_n), .OE_n(OE_n), .WE_n(WE_n), .CS1(CS1), .X1(X1), .READY(READY),
    .RESET_IN(RESET_IN), .SID(SID), .TX(TX), .HOLD(HOLD), .seg(seg), .dig(dig),
    .SND(SND), .X2(X2), .RSTOUT(RSTOUT), .SOD(1'b0), .INTAn(INTAn),
    .HLDA(HLDA), .CLKOUT(CLKOUT), .S0(S0w), .S1(S1w),
    .AH8(AH[6]), .AH9(AH[5]), .AH10(AH[4]), .AH11(AH[3]), .AH12(AH[2]),
    .AH13(AH[1]), .AH14(AH[0]), .RX(RX),
    .col0(col0), .col1(col1), .col2(col2), .col3(col3),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

  integer t = 0;
  always @(posedge clk) t = t + 1;
  reg [255:0] tx_log   [0:8191];                // бит TX по тикам (0/1)
  reg [255:0] hold_log [0:8191];                // HOLD по тикам (v2: релиз в конце пакета!)
  always @(posedge clk) begin tx_log[t] = TX; hold_log[t] = HOLD; end

  task tick; begin @(posedge clk); end endtask

  // машинный цикл записи/чтения + HOLD/HLDA рукопожатие (как sim_txclient_v2.py)
  task cycle(input [15:0] addr, input [7:0] data, input iom, input wr);
    integer k;
    begin
      AH = addr[15:8]; A = addr[7:0]; IOM = iom;
      if (wr) begin S0 = 1; S1 = 0; end         // статус: запись
      else    begin S0 = 0; S1 = 1; end         // статус: чтение
      ALE = 1; WRn = 1; RDn = 1;
      for (k = 0; k < T_T1; k = k + 1) tick;
      ALE = 0;
      if (wr) begin WRn = 0; A = data; end else RDn = 0;
      for (k = 0; k < T_STROBE - 1; k = k + 1) tick;
      WRn = 1; RDn = 1; S0 = 0; S1 = 0; tick;
      if (HOLD) begin
        tick; tick; HLDA = 1;
        while (HOLD) tick;                       // v2: грант активен ВЕСЬ пакет (30 бит)
        tick; tick; HLDA = 0;
      end
    end
  endtask

  // декод кадра, начавшегося в t0: start, data (LSB-первый), stop + сетка фронтов
  task frame_at(input integer t0, output ok, output [7:0] val);
    integer k; reg prev, cur; reg grid;
    begin
      ok = (tx_log[t0 + 6] == 0);                // старт-бит в середине ячейки
      for (k = 0; k < 8; k = k + 1)
        if (tx_log[t0 + (k+1)*BAUD_DIV + 6]) val[k] = 1'b1; else val[k] = 1'b0;
      ok = ok && (tx_log[t0 + 9*BAUD_DIV + 6] == 1'b1);  // стоп
      grid = 1; prev = 1'b1;
      for (k = 0; k <= 10*BAUD_DIV + 2; k = k + 1) begin
        cur = (k == 0) ? 1'b1 : tx_log[t0 + k - 1];
        if (k > 0 && cur !== prev) begin
          if ((k - 1) % BAUD_DIV != 0) grid = 0;
          prev = cur;
        end
      end
      ok = ok && grid;
    end
  endtask

  integer f1_t, f2_t, f3_t, k, errors;
  reg fok; reg [7:0] fval;
  initial begin
    errors = 0;
    RST = 1; repeat (20) tick; RST = 0; repeat (10) tick;
    if (HOLD !== 1'b0 || TX !== 1'b1) begin $display("FAIL idle: HOLD/TX"); errors = errors + 1; end

    // T1: запись ОЗУ 8012h <- 5Ah
    cycle(16'h8012, 8'h5A, 1'b0, 1'b1);
    f1_t = 0; f2_t = 0; f3_t = 0;
    for (k = 1; k < 8180; k = k + 1)
      if (tx_log[k] === 1'b0 && tx_log[k-1] === 1'b1) begin
        if (f1_t == 0) f1_t = k; else if (f2_t == 0) f2_t = k; else if (f3_t == 0) f3_t = k;
      end
    if (f1_t == 0 || f2_t == 0 || f3_t == 0) begin $display("FAIL T1: пакет не найден"); errors = errors + 1; end
    else begin
      frame_at(f1_t, fok, fval);
      if (!fok || fval !== 8'h80) begin $display("FAIL T1: байт1(hi)=%h ok=%b", fval, fok); errors = errors + 1; end
      frame_at(f2_t, fok, fval);
      if (!fok || fval !== 8'h12) begin $display("FAIL T1: байт2(lo)=%h ok=%b", fval, fok); errors = errors + 1; end
      frame_at(f3_t, fok, fval);
      if (!fok || fval !== 8'h5A) begin $display("FAIL T1: байт3(data)=%h ok=%b", fval, fok); errors = errors + 1; end
      if (f2_t - f1_t !== 10*BAUD_DIV || f3_t - f2_t !== 10*BAUD_DIV)
        begin $display("FAIL T1: зазоры %0d/%0d", f2_t - f1_t, f3_t - f2_t); errors = errors + 1; end
      // v2: HOLD держится ВЕСЬ пакет (в v1 отпускался на 2-м байте)
      if (hold_log[f2_t] !== 1'b1 || hold_log[f3_t] !== 1'b1)
        begin $display("FAIL T1: HOLD снят ДО конца пакета"); errors = errors + 1; end
      if (hold_log[f3_t + 10*BAUD_DIV + 3] !== 1'b0)
        begin $display("FAIL T1: HOLD не снят после пакета"); errors = errors + 1; end
    end
    repeat (500) tick;                            // хвост пакета

    // T2: запись в страницу-исключение FFxx (стек) - HOLD/пакета нет
    cycle(16'hFF34, 8'h77, 1'b0, 1'b1); repeat (100) tick;
    if (HOLD !== 1'b0 || TX !== 1'b1) begin $display("FAIL T2: активность на исключённой странице"); errors = errors + 1; end

    // T3: IO-запись
    cycle(16'h0000, 8'hAA, 1'b1, 1'b1); repeat (100) tick;
    if (HOLD !== 1'b0 || TX !== 1'b1) begin $display("FAIL T3: активность на IO"); errors = errors + 1; end

    // T4: чтение ОЗУ - БЕЗ HOLD ВОВСЕ (S0/S1)
    cycle(16'h9000, 8'h00, 1'b0, 1'b0); repeat (100) tick;
    if (TX !== 1'b1) begin $display("FAIL T4: пакет после чтения"); errors = errors + 1; end
    if (HOLD !== 1'b0) begin $display("FAIL T4: HOLD после чтения"); errors = errors + 1; end

    // T5: бэку-ту-бэк 8001<-11, 8002<-22
    cycle(16'h8001, 8'h11, 1'b0, 1'b1);
    cycle(16'h8002, 8'h22, 1'b0, 1'b1);
    repeat (600) tick;
    begin : t5
      integer z [0:7]; integer n; reg [7:0] v;
      n = 0;
      for (k = 1; k < 8180; k = k + 1)
        if (tx_log[k] === 1'b0 && tx_log[k-1] === 1'b1 && (n == 0 || k > z[n-1] + 10*BAUD_DIV + 4)) begin
          z[n] = k; n = n + 1;
        end
      if (n !== 6) begin $display("FAIL T5: кадров %0d (ожидалось 6)", n); errors = errors + 1; end
      else begin
        frame_at(z[0], fok, v); if (v !== 8'h80) begin $display("FAIL T5: кадр1=%h", v); errors = errors + 1; end
        frame_at(z[1], fok, v); if (v !== 8'h01) begin $display("FAIL T5: кадр2=%h", v); errors = errors + 1; end
        frame_at(z[2], fok, v); if (v !== 8'h11) begin $display("FAIL T5: кадр3=%h", v); errors = errors + 1; end
        frame_at(z[3], fok, v); if (v !== 8'h80) begin $display("FAIL T5: кадр4=%h", v); errors = errors + 1; end
        frame_at(z[4], fok, v); if (v !== 8'h02) begin $display("FAIL T5: кадр5=%h", v); errors = errors + 1; end
        frame_at(z[5], fok, v); if (v !== 8'h22) begin $display("FAIL T5: кадр6=%h", v); errors = errors + 1; end
      end
    end

    if (errors == 0) $display("TXCLIENT v2 TB: ВСЕ ПАСС");
    else             $display("TXCLIENT v2 TB: ПРОВАЛОВ %0d", errors);
    $finish;
  end
endmodule
