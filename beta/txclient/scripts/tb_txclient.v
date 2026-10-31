//=====================================================================
// tb_txclient.v - тестбенч TXCLIENT v1 (beta/txclient) для Icarus Verilog.
// В песочнице разработки iverilog недоступен - ПРОГНАТЬ У ВЛАДЕЛЬЦА:
//   iverilog -o tb_txclient.vvp tb_txclient.v ../top_txclient_v1_utf8.v
//   vvp tb_txclient.vvp
// Эталонная модель - scripts/sim_txclient.py (29/29 ПАСС); при расхождении
// смотреть сначала её. Проверяет: окно-запись (пакет [lo][data], бит ровно
// 13 тиков, HOLD в T1, релиз на 2-м байте), не-окно, IO, чтение окна,
// бэку-ту-бэк. Порты/делитель/POR v3.9.2 не проверяются (там свой TB).
`timescale 1ns/1ns
module tb_txclient();
  localparam BAUD_DIV = 13;
  localparam T_T1 = 7, T_STROBE = 9;

  reg clk = 0; always #20 clk = ~clk;          // 25 МГц
  reg RST = 1, ALE = 0, WRn = 1, RDn = 1, IOM = 0, HLDA = 0;
  reg  [7:0] A  = 8'h00;                        // AD0-AD7 (A-сети)
  reg  [7:0] AH = 8'h00;                        // A15,AH14..AH8 (наблюдатели)
  wire [7:0] D;  assign D = 8'hZZ;              // чтения не проверяем данные
  wire [7:0] seg; wire [3:0] dig; wire SND, SNDd;
  wire CSr_n, OEr_n, CS_n, OE_n, WE_n, CS1, X1, X2, READY, RESET_IN;
  wire SID, TX, HOLD, RSTOUT, INTAn, CLKOUT, S0, S1, RX;
  wire col0, col1, col2, col3; reg row0 = 1, row1 = 1, row2 = 1, row3 = 1, row4 = 1;

  retro_pcld_top dut(.clk(clk), .RST(RST), .ALE(ALE), .WRn(WRn), .RDn(RDn),
    .IOM(IOM), .A15(AH[7]), .A(A), .D(D), .CSr_n(CSr_n), .OEr_n(OEr_n),
    .CS_n(CS_n), .OE_n(OE_n), .WE_n(WE_n), .CS1(CS1), .X1(X1), .READY(READY),
    .RESET_IN(RESET_IN), .SID(SID), .TX(TX), .HOLD(HOLD), .seg(seg), .dig(dig),
    .SND(SND), .X2(X2), .RSTOUT(RSTOUT), .SOD(1'b0), .INTAn(INTAn),
    .HLDA(HLDA), .CLKOUT(CLKOUT), .S0(S0), .S1(S1),
    .AH8(AH[6]), .AH9(AH[5]), .AH10(AH[4]), .AH11(AH[3]), .AH12(AH[2]),
    .AH13(AH[1]), .AH14(AH[0]), .RX(RX),
    .col0(col0), .col1(col1), .col2(col2), .col3(col3),
    .row0(row0), .row1(row1), .row2(row2), .row3(row3), .row4(row4));

  integer t = 0;
  always @(posedge clk) t = t + 1;
  reg [255:0] tx_log [0:4095];                  // бит TX по тикам (0/1)
  always @(posedge clk) begin tx_log[t] = TX; end

  task tick; begin @(posedge clk); end endtask

  // машинный цикл записи/чтения + HOLD/HLDA рукопожатие (как sim_txclient.py)
  task cycle(input [15:0] addr, input [7:0] data, input iom, input wr);
    integer k;
    begin
      AH = addr[15:8]; A = addr[7:0]; IOM = iom;
      ALE = 1; WRn = 1; RDn = 1;
      for (k = 0; k < T_T1; k = k + 1) tick;
      ALE = 0;
      if (wr) begin WRn = 0; A = data; end else RDn = 0;
      for (k = 0; k < T_STROBE - 1; k = k + 1) tick;
      WRn = 1; RDn = 1; tick;
      if (HOLD) begin
        tick; tick; HLDA = 1;
        while (HOLD) tick;
        tick; tick; HLDA = 0;                    // релиз - на загрузке 2-го байта
      end
    end
  endtask

  // декод кадра, начавшегося в t0: start, data (LSB-первый), stop + сетка фронтов
  task frame_at(input integer t0, output ok, output [7:0] val);
    integer k, e_prev, e_cur; reg prev, cur; reg grid;
    begin
      ok = (tx_log[t0 + 6] == 0);                // старт-бит в середине ячейки
      for (k = 0; k < 8; k = k + 1)
        if (tx_log[t0 + (k+1)*BAUD_DIV + 6]) val[k] = 1'b1; else val[k] = 1'b0;
      ok = ok && (tx_log[t0 + 9*BAUD_DIV + 6] == 1'b1);  // стоп
      // все фронты кадра - на сетке t0 + m*BAUD_DIV
      grid = 1; prev = 1'b1; e_prev = 0;
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

  integer f1_t, f2_t, k, errors;
  reg fok; reg [7:0] fval;
  initial begin
    errors = 0;
    RST = 1; repeat (20) tick; RST = 0; repeat (10) tick;
    if (HOLD !== 1'b0 || TX !== 1'b1) begin $display("FAIL idle: HOLD/TX"); errors = errors + 1; end

    // T1: окно-запись F012h <- 5Ah
    cycle(16'hF012, 8'h5A, 1'b0, 1'b1);
    // найти старты кадров (передние фронты TX 1->0 после цикла)
    f1_t = 0; f2_t = 0;
    for (k = 1; k < 4090; k = k + 1)
      if (tx_log[k] === 1'b0 && tx_log[k-1] === 1'b1) begin
        if (f1_t == 0) f1_t = k; else if (f2_t == 0) f2_t = k;
      end
    if (f1_t == 0 || f2_t == 0) begin $display("FAIL T1: пакет не найден"); errors = errors + 1; end
    else begin
      frame_at(f1_t, fok, fval);
      if (!fok || fval !== 8'h12) begin $display("FAIL T1: байт1=%h ok=%b", fval, fok); errors = errors + 1; end
      frame_at(f2_t, fok, fval);
      if (!fok || fval !== 8'h5A) begin $display("FAIL T1: байт2=%h ok=%b", fval, fok); errors = errors + 1; end
      if (f2_t - f1_t !== 10*BAUD_DIV) begin $display("FAIL T1: зазор %0d", f2_t - f1_t); errors = errors + 1; end
      if (HOLD !== 1'b0) begin $display("FAIL T1: HOLD не отпущен на 2-м байте"); errors = errors + 1; end
    end
    repeat (300) tick;                            // хвост пакета

    // T2: запись вне окна
    cycle(16'h8012, 8'h5A, 1'b0, 1'b1); repeat (100) tick;
    if (HOLD !== 1'b0 || TX !== 1'b1) begin $display("FAIL T2: активность вне окна"); errors = errors + 1; end

    // T3: IO-запись
    cycle(16'h0000, 8'hAA, 1'b1, 1'b1); repeat (100) tick;
    if (HOLD !== 1'b0 || TX !== 1'b1) begin $display("FAIL T3: активность на IO"); errors = errors + 1; end

    // T4: чтение окна - пинг-понг без пакета
    cycle(16'hF040, 8'h00, 1'b0, 1'b0); repeat (100) tick;
    if (TX !== 1'b1) begin $display("FAIL T4: пакет после чтения окна"); errors = errors + 1; end
    if (HOLD !== 1'b0) begin $display("FAIL T4: HOLD завис"); errors = errors + 1; end

    // T5: бэку-ту-бэк F001<-11, F002<-22
    cycle(16'hF001, 8'h11, 1'b0, 1'b1);
    cycle(16'hF002, 8'h22, 1'b0, 1'b1);
    repeat (300) tick;
    begin : t5
      integer z [0:7]; integer n; reg [7:0] v; reg ok5;
      n = 0;
      for (k = 1; k < 4090; k = k + 1)
        if (tx_log[k] === 1'b0 && tx_log[k-1] === 1'b1 && (n == 0 || k > z[n-1] + 10*BAUD_DIV + 4)) begin
          z[n] = k; n = n + 1;
        end
      if (n !== 4) begin $display("FAIL T5: кадров %0d (ожидалось 4)", n); errors = errors + 1; end
      else begin
        frame_at(z[0], fok, v); if (v !== 8'h01) begin $display("FAIL T5: кадр1=%h", v); errors = errors + 1; end
        frame_at(z[1], fok, v); if (v !== 8'h11) begin $display("FAIL T5: кадр2=%h", v); errors = errors + 1; end
        frame_at(z[2], fok, v); if (v !== 8'h02) begin $display("FAIL T5: кадр3=%h", v); errors = errors + 1; end
        frame_at(z[3], fok, v); if (v !== 8'h22) begin $display("FAIL T5: кадр4=%h", v); errors = errors + 1; end
      end
    end

    if (errors == 0) $display("TXCLIENT TB: ВСЕ ПАСС");
    else             $display("TXCLIENT TB: ПРОВАЛОВ %0d", errors);
    $finish;
  end
endmodule
