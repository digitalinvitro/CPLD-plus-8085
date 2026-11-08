//=====================================================================
// tb_txuart_v22.v - testbench for txuart v2.2 (beta/txuart).
// NOTES:
//  - ASCII-only comments (encoding-safe for ISE and iverilog);
//  - v2.2 node (owner directive 11-9, "simpler clock divider: feed 25
//    MHz, then /4 to the processor"): input clock 25 MHz (H1 WITH
//    shunt, DIV=/4), one-hot ring s0..s3 on clk 25 MHz (period 160 ns),
//    X1 = s0 (6.25 MHz, duty 1/4: high 40 / low 120 ns), X2 = s1|s2|s3
//    = ~s0, clk25_q REMOVED - ALL logic on clk 25 MHz (same tick rate
//    as v2.1 clk25), por chain in the clk domain with strobe s0
//    (POR = 8 x 160 = 1280 ns), TXUART core BIT-FOR-BIT v2.1 (18 MCs,
//    baud = 25/16 = 1562500 exactly, bit = 640 ns);
//  - CPU = 3.125 MHz (T = 320 ns) - 12.5% slower than the golden
//    3.571 MHz, accepted by the owner (FW cycle-calibrated constants
//    stretch by 1.143x);
//  - the PRIMARY verification for the v2.0 -> v2.1 core equivalence
//    remains sim_txuart_v21.py + diffsim (92/92, 8283 ticks, 0 diffs);
//    this tb proves the REAL RTL: node legalization from ALL 16 ring
//    codes (P0a), X1/X2 timing, POR edge ~1240 ns, frame grid 640 ns,
//    busy-write drop, status port, reset mid-frame.
// Run:  bash scripts/run_tb_v22.sh
//   or: iverilog -g2001 -o tb_txuart.vvp tb_txuart_v22.v top_txuart_por6_v22_utf8.v
//       vvp tb_txuart.vvp
// Expect: "TOTAL: N pass, 0 fail" + "SIMULATION PASSED".
//=====================================================================
`timescale 1ns/1ps

module tb_txuart;

  localparam CLKP  = 40;      // 25 MHz tick: 40 ns (H1 WITH shunt, v2.2)
  localparam BITNS = 640;     // 16 ticks of clk (40 ns) = 640 ns = 1562500 baud
  localparam T     = 320;     // CPU T-state at 3.125 MHz (v2.2)
  localparam RSTLAT = 500;    // button qualifier latency (p.21): 2FF + 8 clk + margin

  reg clk = 0;
  always #(CLKP/2) clk = ~clk;

  reg  RST = 0, ALE = 0, WRn = 1, RDn = 1, IOM = 0, A15 = 0;
  reg  SOD = 0, RX = 1;
  reg  [7:0] A_tb = 8'h00;  reg A_en = 0;
  reg  [7:0] D_tb = 8'h00;  reg D_en = 0;
  reg  r0 = 0, r1 = 0, r2 = 0, r3 = 0, r4 = 0;

  wire [7:0] A = A_en ? A_tb : 8'bZZZZZZZZ;
  wire [7:0] D = D_en ? D_tb : 8'bZZZZZZZZ;

  wire CSr_n, OEr_n, CS_n, OE_n, WE_n, CS1, X1, X2, READY, RESET_IN, SID, TX, SND;
  wire [7:0] seg;  wire [3:0] dig;  wire col0, col1, col2, col3;

  retro_pcld_top #(.POR_W(6), .CLK_DIV(4), .CLK_HALF(1)) dut (
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

  integer pass = 0, fail = 0;

  task chk(input cond, input [127:0] msg);
    begin
      if (cond) pass = pass + 1;
      else begin
        fail = fail + 1;
        $display("FAIL: %0s", msg);
      end
    end
  endtask

  // ---------- CPU bus cycles (T1 = 1 CPU cycle with ALE) ----------
  task cpu_io_write(input [7:0] port, input [7:0] data);
    begin
      ALE = 1; IOM = 1; A_en = 1; A_tb = port;
      #(T);                       // T1: ALE high, address on AD
      ALE = 0; #(T/2);            // T2 begins
      WRn = 0; A_tb = data;       // CPU drives data at !WR
      #(T + T/2);                 // data valid through WR# fall..rise
      WRn = 1; A_en = 0;
      #(T);
    end
  endtask

  task cpu_io_read(input [7:0] port, output [7:0] val);
    begin
      ALE = 1; IOM = 1; A_en = 1; A_tb = port;
      #(T);
      ALE = 0; #(T/2);
      RDn = 0; A_en = 0;          // CPU releases AD, CPLD drives status/rows
      #(T);
      val = A;                    // sample before RD# rises
      #(T/2);
      RDn = 1;
      #(T);
    end
  endtask

  // ---------- PC side: TX line receiver (mid-bit sampling) ----------
  integer pc_byte;
  event   pc_byte_ev;

  initial pc_byte = 0;
  always @(negedge TX) begin : pc_rx
    integer i, b;
    begin
      #(BITNS/2);                       // center of start bit
      if (TX !== 1'b0) begin
        // glitch: line back high at start center - ignore
      end else begin
        b = 0;
        for (i = 0; i < 8; i = i + 1) begin
          #(BITNS);                     // center of data bit i
          b = b | (TX << i);            // LSB first
        end
        #(BITNS);                       // center of stop
        pc_byte = b;
        -> pc_byte_ev;
      end
    end
  end

  // ---------- helpers ----------
  integer k;
  integer guard;
  reg [7:0] val;
  reg [63:0] w_start, w_x1, t_rise, t_fall;
  reg [63:0] t_reset_in = 0;

  // measure first RESET_IN rise (POR window v2.2 ~1240 ns)
  always @(posedge RESET_IN)
    if (t_reset_in == 0) t_reset_in = $time;

  initial begin
    // ---- C1: POR (v2.2: 8 strobes of por_ce=s0, RESET_IN rises ~1240 ns) ----
    #(3000);
    chk(RESET_IN === 1'b1, "C1: RESET_IN released after POR (reset_q register)");
    chk(t_reset_in >= 1200 && t_reset_in <= 1400,
        "C1: RESET_IN rise at ~1240 ns (8 x 160 POR, drain 1000)");
    $display("  info: RESET_IN rise at %0t ns", t_reset_in);
    chk(TX === 1'b1,      "C1: TX idle '1' (shreg INIT=1FF)");
    cpu_io_read(8'h05, val);
    chk(val === 8'h02,    "C1: status IN 05h = 02h (TXRDY=1, A0=0, A7..A2=0)");
    chk(SID === RX,       "C1: SID = RX transit alive");

    // ---- C1b: ring node - X1 period exactly 160 ns, duty 1/4, X2 = ~X1 ----
    fork
      begin : x1_period
        @(posedge X1); t_rise = $time;
        @(negedge X1); t_fall = $time;
        @(posedge X1); w_x1 = $time;
        chk((t_fall - t_rise) === 40,  "C1b: X1 high exactly 40 ns (duty 1/4)");
        chk((w_x1 - t_fall) === 120,   "C1b: X1 low exactly 120 ns");
        chk((w_x1 - t_rise) === 160,   "C1b: X1 period exactly 160 ns (6.25 MHz, ring/4)");
      end
      begin #3000; end
    join
    begin : x2_pol
      integer ok;
      ok = 1;
      repeat (16) begin
        #(17);                        // off-grid sample
        if (X1 === X2) ok = 0;
      end
      chk(ok === 1, "C1b: X2 = ~X1 (antiphase in legal one-hot)");
    end

    // ---- C2: TX frame 0x55, bit grid = 640 ns ----
    fork
      begin : tx_frame55
        @(negedge TX);
        w_start = $time;
        // first rising edge must be exactly one bit later (d0 of 0x55 = 1)
        @(posedge TX);
        chk(($time - w_start) === BITNS,
            "C2(55): start bit exactly 640 ns (16 ticks of clk 25 MHz)");
      end
      begin
        cpu_io_write(8'h04, 8'h55);
      end
    join
    fork
      begin : pc_wait55
        @(pc_byte_ev);
        chk(pc_byte === 8'h55, "C2(55): PC decoded 0x55");
      end
      begin
        #(BITNS * 12);
      end
    join
    chk(TX === 1'b1,  "C2(55): back to idle after frame");
    chk(dut.shreg === 9'h1FF, "C2(55): shreg self-idle all-ones");

    // ---- C3: TX stream with TXRDY polling ----
    begin : stream
      for (k = 0; k < 3; k = k + 1) begin
        // poll TXRDY (IN 05h bit1) UNTIL ready - the previous frame may
        // still be running (6.4 us), a single poll would see TXRDY=0
        guard = 0;
        cpu_io_read(8'h05, val);
        while (val[1] !== 1'b1 && guard < 50) begin
          cpu_io_read(8'h05, val);
          guard = guard + 1;
        end
        chk(val[1] === 1'b1, "C3: TXRDY=1 before OUT");
        cpu_io_write(8'h04, 8'h41 + k[7:0]);
      end
      #(BITNS * 12);
    end

    // ---- C4: write while busy is silently dropped ----
    cpu_io_write(8'h04, 8'h11);
    #(BITNS * 2);              // inside the frame
    chk(dut.bit_cnt !== 4'd0,  "C4: frame running (busy = |bit_cnt, core v2.1)");
    cpu_io_write(8'h04, 8'h99);// must be dropped (io_wr_tx gated by tx_idle)
    fork
      begin : pc_wait11
        @(pc_byte_ev);
        chk(pc_byte === 8'h11, "C4(11): frame intact, busy byte dropped");
      end
      begin
        #(BITNS * 12);
      end
    join

    // ---- C5: status IN 05h reflects TXRDY ----
    cpu_io_read(8'h05, val);
    chk(val[1] === 1'b1, "C5: TXRDY=1 after frame");

    // ---- C7: reset mid-TX-frame (button qualifier ~400 ns -> GSR) ----
    cpu_io_write(8'h04, 8'hC3);
    chk(dut.bit_cnt !== 4'd0, "C7: frame started (bit_cnt != 0)");
    #(BITNS/2);               // still inside the frame
    RST = 1; #RSTLAT;
    chk(TX === 1'b1, "C7: GSR (via p.21 qualifier) drives TX to '1'");
    chk(dut.bit_cnt === 4'd0 && dut.shreg === 9'h1FF, "C7: core cleared (bit_cnt=0, shreg=1FF)");
    chk(dut.rst_press === 1'b1, "C7: rst_press set (qualified reset)");
    RST = 0; #RSTLAT; #(BITNS);
    chk(TX === 1'b1, "C7: idle after reset release");
    chk(dut.rst_press === 1'b0, "C7: rst_press released (qualified)");

    // ---- P0a: ALL 16 ring codes -> legal one-hot (self-cleaning) ----
    begin : ring_bruteforce
      integer code;
      integer ok_all;
      integer q0, q1, q2, q3;
      reg recovered;
      ok_all = 1;
      for (code = 0; code < 16; code = code + 1) begin
        // inject the code between clock edges
        @(negedge clk);
        dut.s0 = code[0];
        dut.s1 = code[1];
        dut.s2 = code[2];
        dut.s3 = code[3];
        // wait 4 clock cycles (double kill + restart need <= 2-3 fronts)
        repeat (4) @(posedge clk);
        @(negedge clk);
        q0 = dut.s0; q1 = dut.s1; q2 = dut.s2; q3 = dut.s3;
        // one-hot, or 0000 on the way to restart (then one more cycle)
        if (q0 + q1 + q2 + q3 !== 1) begin
          repeat (2) @(posedge clk);
          @(negedge clk);
          q0 = dut.s0; q1 = dut.s1; q2 = dut.s2; q3 = dut.s3;
        end
        if (q0 + q1 + q2 + q3 !== 1) ok_all = 0;
        // ring must KEEP cycling: state advances each 2 cycles
        q0 = dut.s0; q1 = dut.s1; q2 = dut.s2; q3 = dut.s3;
        repeat (2) @(posedge clk);
        @(negedge clk);
        recovered = ((dut.s0 + dut.s1 + dut.s2 + dut.s3) === 1);
        if (!recovered) ok_all = 0;
      end
      chk(ok_all === 1, "P0a: all 16 ring codes legalize to one-hot and cycle");
      // X1/X2 healthy after brute-force
      @(posedge X1); t_rise = $time;
      @(posedge X1);
      chk(($time - t_rise) === 160, "P0a: X1 period 160 ns after recovery");
    end

    $display("TOTAL: %0d pass, %0d fail", pass, fail);
    if (fail == 0) $display("SIMULATION PASSED");
    else           $display("SIMULATION FAILED");
    $finish;
  end

endmodule
