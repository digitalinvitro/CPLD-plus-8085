//=====================================================================
// tb_txclient.v - testbench for v3.10 txclient (beta/txclient).
// NOTES:
//  - ASCII-only comments (encoding-safe for ISE and iverilog);
//  - the PRIMARY verification tool is the cycle-exact sim_txclient.py
//    (33/33 PASS, including the structural "no reload inside b7"
//    check); this tb repeats the functional scenarios for ISE/iverilog;
//  - every frame check runs in a fork branch TOGETHER with the CPU
//    write, because the frame starts ~2 clks after WR# falls.
// Run:  iverilog -o tb_txclient.vvp tb_txclient.v top_txclient_por6_v310_utf8.v
//       vvp tb_txclient.vvp
// Expect: "TOTAL: N pass, 0 fail" + "SIMULATION PASSED".
//=====================================================================
`timescale 1ns/1ps

module tb_txclient;

  localparam CLKP  = 40;      // 25 MHz tick: 40 ns
  localparam BITNS = 8680;    // 217 ticks = 8.68 us = 115207.4 baud
  localparam T     = 280;     // CPU T-state (7 ticks)

  reg         clk = 0;
  always #(CLKP/2) clk = ~clk;

  reg  RST = 1, ALE = 0, WRn = 1, RDn = 1, IOM = 0, A15 = 0;
  reg  SOD = 0, RX = 1;
  reg  [7:0] A_tb = 8'h00;  reg A_en = 0;
  reg  [7:0] D_tb = 8'h00;  reg D_en = 0;
  reg  r0 = 0, r1 = 0, r2 = 0, r3 = 0, r4 = 0;

  wire [7:0] A = A_en ? A_tb : 8'bZZZZZZZZ;
  wire [7:0] D = D_en ? D_tb : 8'bZZZZZZZZ;

  wire CSr_n, OEr_n, CS_n, OE_n, WE_n, CS1, X1, X2, READY, RESET_IN, SID, TX, SND;
  wire [7:0] seg;  wire [3:0] dig;  wire col0, col1, col2, col3;

  retro_pcld_top #(.POR_W(6), .CLK_DIV(2), .CLK_HALF(1)) dut (
    .clk(clk), .RST(RST),
    .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(A), .D(D),
    .CSr_n(CSr_n), .OEr_n(OEr_n), .CS_n(CS_n), .OE_n(OE_n), .WE_n(WE_n), .CS1(CS1),
    .X1(X1), .READY(READY), .RESET_IN(RESET_IN),
    .SID(SID), .TX(TX),
    .seg(seg), .dig(dig), .SND(SND),
    .X2(), .RSTOUT(1'b0), .SOD(SOD), .INTAn(1'b0), .HLDA(1'b0),
    .CLKOUT(1'b0), .S0(1'b0), .S1(1'b0),
    .AH8(1'b0), .AH9(1'b0), .AH10(1'b0), .AH11(1'b0),
    .AH12(1'b0), .AH13(1'b0), .AH14(1'b0),
    .RX(RX),
    .col0(col0), .col1(col1), .col2(col2), .col3(col3),
    .row0(r0), .row1(r1), .row2(r2), .row3(r3), .row4(r4)
  );

  integer pass_cnt = 0, err_cnt = 0;
  integer fall_cnt = 0, n0 = 0;
  reg [63:0] t_neg = 0;         // last TX falling edge time
  reg [63:0] w_start = 0;       // last low->high run started by a fall

  always @(negedge TX) begin fall_cnt = fall_cnt + 1; t_neg = $time; end
  always @(posedge TX)  w_start = $time - t_neg;

  task chk(input cond);
    begin
      if (cond === 1'b1) pass_cnt = pass_cnt + 1;
      else begin
        err_cnt = err_cnt + 1;
        $display("  FAIL at %0t ns (check #%0d)", $time, pass_cnt + err_cnt);
      end
    end
  endtask

  // ---------- CPU bus tasks (T-state realistic) ----------
  task cpu_out(input [7:0] port, input [7:0] data);
    begin
      IOM = 1; A_tb = port; A_en = 1; ALE = 1; #(7*CLKP);   // T1
      ALE = 0; #(2*CLKP);                                   // T2
      A_tb = data; WRn = 0; #(12*CLKP);                     // WR# low
      WRn = 1; A_en = 0; #(2*CLKP);                         // release at WR# up
      IOM = 0; #(6*CLKP);
    end
  endtask

  task cpu_in(input [7:0] port, output [7:0] data);
    begin
      IOM = 1; A_tb = port; A_en = 1; ALE = 1; #(7*CLKP);   // T1
      ALE = 0; A_en = 0; #(2*CLKP);                         // CPU releases AD
      RDn = 0; #(8*CLKP);                                   // T2..T3
      data = A;
      RDn = 1; #(2*CLKP); IOM = 0; #(4*CLKP);
    end
  endtask

  task mem_write(input a15v, input [7:0] lo, input [7:0] data);
    begin
      IOM = 0; A15 = a15v; A_tb = lo; D_tb = 8'h00; D_en = 1;
      ALE = 1; #(7*CLKP);
      ALE = 0; D_en = 0; #(2*CLKP);
      A_tb = data; WRn = 0; #(12*CLKP);
      WRn = 1; A_en = 0; #(2*CLKP);
      A15 = 0; #(6*CLKP);
    end
  endtask

  // ---------- UART frame checker (bit centers, LSB first) ----------
  task chk_frame(input [7:0] exp);
    integer k; reg ok; reg [63:0] w_cap;
    begin
      ok = 1;
      @(negedge TX);
      #(BITNS/2); if (TX !== 1'b0) ok = 0;                  // start center
      #(BITNS);                                             // +1.5 bit
      if (exp[0] === 1'b1) begin                            // start width (b0=1 only)
        w_cap = w_start;
        if (!(w_cap >= BITNS - 80 && w_cap <= BITNS + 80)) ok = 0;
      end
      for (k = 0; k < 8; k = k + 1) begin
        if (TX !== exp[k]) ok = 0;                          // b_k center
        #(BITNS);
      end
      if (TX !== 1'b1) ok = 0;                              // stop center
      #(BITNS/2);
      chk(ok === 1'b1);
    end
  endtask

  // canonical firmware putchar: IN; RRC; JC; OUT (T-exact pacing)
  task fw_putchar(input [7:0] ch);
    reg [7:0] d;
    begin
      cpu_in(8'h07, d);
      #(1880);                       // IN tail (to 10T)
      #(1120);                       // RRC (4T)
      while (!d[0]) begin
        #(1960);                     // JC not taken (7T)
        cpu_in(8'h07, d);
        #(1880); #(1120);
      end
      #(2800);                       // JC taken (10T)
      cpu_out(8'h07, ch);
    end
  endtask

  // ================= scenarios =================
  reg [7:0] d;
  reg [7:0] wb_a, wb_d;
  integer k, we_lo;
  initial begin
    $display("T0: POR, TX=1, RESET_IN, TXRDY=1");
    #(60*CLKP);
    chk(RESET_IN === 1'b0);                       // POR running
    chk(TX === 1'b1);                             // idle from INIT
    RST = 0;
    #(80*CLKP);                                   // POR 1120 ns + margin
    chk(RESET_IN === 1'b1);
    cpu_in(8'h07, d); chk(d === 8'h01);           // TXRDY=1

    $display("T1: OUT 07h,55h -> frame; TXRDY busy mid-frame");
    fork
      cpu_out(8'h07, 8'h55);
      begin #(40*CLKP); cpu_in(8'h07, d); chk(d === 8'h00); end
      chk_frame(8'h55);
    join
    cpu_in(8'h07, d); chk(d === 8'h01);           // ready again

    $display("T2: poll-paced stream Hi! 00h FFh");
    fork fw_putchar(8'h48); chk_frame(8'h48); join
    fork fw_putchar(8'h69); chk_frame(8'h69); join
    fork fw_putchar(8'h21); chk_frame(8'h21); join
    fork fw_putchar(8'h00); chk_frame(8'h00); join
    fork fw_putchar(8'hFF); chk_frame(8'hFF); join
    chk(TX === 1'b1);

    $display("T3: blind double OUT -> 1 frame, second byte dropped");
    n0 = fall_cnt;
    fork
      begin cpu_out(8'h07, "A"); #(120*CLKP); cpu_out(8'h07, "B"); end
      begin #(40*CLKP); cpu_in(8'h07, d); chk(d === 8'h00); end
      chk_frame(8'h41);
    join
    chk(fall_cnt - n0 == 1);                      // exactly one frame
    n0 = fall_cnt;
    fork fw_putchar(8'h43); chk_frame(8'h43); join

    $display("T4: SOD dead (transit removed)");
    SOD = 1; #(80*CLKP); SOD = 0; #(200*CLKP);
    chk(TX === 1'b1);                             // v3.7 would drive 0 here

    $display("T5: SID = RX transit alive");
    RX = 0; #(3*CLKP); chk(SID === 1'b0);
    RX = 1; #(3*CLKP); chk(SID === 1'b1);

    $display("T6: ports 00h/01h/02h/03h regression, TX silent");
    n0 = fall_cnt;
    cpu_out(8'h00, 8'hA5); chk(seg === ~8'hA5);
    cpu_out(8'h01, 8'h1F); chk(dig === 4'h0 && SND === 1'b1);
    cpu_out(8'h02, 8'h05); chk({col3,col2,col1,col0} === 4'b0101);
    {r4,r3,r2,r1,r0} = 5'b10101;
    cpu_in(8'h03, d); chk(d === 8'h15);
    cpu_in(8'h04, d);                             // reserve port: no hang
    #(40*CLKP);
    chk(fall_cnt - n0 == 0);                      // no frames from ports
    {r4,r3,r2,r1,r0} = 5'b00000;

    $display("T7: RAM write (A15=1): WE pulse 2 clks, A/D in WB, TX silent");
    n0 = fall_cnt;
    A15 = 1; IOM = 0; A_tb = 8'h34; D_tb = 8'h00; D_en = 1;
    ALE = 1; #(7*CLKP);
    ALE = 0; D_en = 0; #(2*CLKP);
    A_tb = 8'h5A; WRn = 0; #(12*CLKP);
    WRn = 1; A_en = 0;
    we_lo = 0; wb_a = 8'hxx; wb_d = 8'hxx;
    for (k = 0; k < 10; k = k + 1) begin
      #(CLKP);
      if (WE_n === 1'b0) begin
        we_lo = we_lo + 1;
        if (wb_a === 8'hxx) begin wb_a = A; wb_d = D; end
      end
    end
    chk(we_lo == 2);                              // exactly 2 clks = 80 ns
    chk(wb_a === 8'h34 && wb_d === 8'h5A);        // sampled inside WB
    #(40*CLKP);
    chk(fall_cnt - n0 == 0);
    A15 = 0;

    $display("T8: ROM write (A15=0) discarded: no WE, TX silent");
    n0 = fall_cnt;
    mem_write(1'b0, 8'h11, 8'h99);
    chk(WE_n === 1'b1);
    chk(fall_cnt - n0 == 0);

    $display("T9: RESET mid-frame: frame completes, no BREAK");
    n0 = fall_cnt;
    fork
      begin
        fw_putchar(8'h58);
        wait (TX === 1'b0);                       // frame start edge
        #(BITNS*3);                               // 3 bits in = mid-frame
        RST = 1; #(50*CLKP); RST = 0; #(80*CLKP); // button 2 us + POR
      end
      chk_frame(8'h58);
    join
    chk(fall_cnt - n0 == 1);
    chk(TX === 1'b1);

    $display("T10: OUT 0Fh = alias of 07h (A2-A0 decode)");
    n0 = fall_cnt;
    fork fw_putchar(8'h5A); chk_frame(8'h5A); join
    fork cpu_out(8'h0F, 8'h77); chk_frame(8'h77); join

    $display("T11: frame with SOD=1 - independent");
    n0 = fall_cnt;
    fork
      begin SOD = 1; fw_putchar(8'h3C); SOD = 0; end
      chk_frame(8'h3C);
    join

    $display("=============================================");
    $display("TOTAL: %0d pass, %0d fail", pass_cnt, err_cnt);
    if (err_cnt == 0) $display("SIMULATION PASSED");
    else              $display("SIMULATION FAILED");
    $finish;
  end

  // safety watchdog
  initial begin
    #(BITNS*400);
    $display("WATCHDOG TIMEOUT");
    $finish;
  end

endmodule
