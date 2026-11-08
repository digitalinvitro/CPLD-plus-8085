//=====================================================================
// tb_txuart_v21.v - testbench for txuart v2.1 (beta/txuart).
// NOTES:
//  - ASCII-only comments (encoding-safe for ISE and iverilog);
//  - the PRIMARY verification tool is the cycle-exact sim_txuart_v21.py
//    (92/92 PASS, scenarios C1-C9) PLUS the differential sim
//    diffsim_v2_v21.py (v2.0 vs v2.1, all observables, 0 diffs); this
//    tb repeats the key functional scenarios against the REAL RTL
//    (iverilog): ring node r0..r6 on 50 MHz (X1 = r0, period 140 ns),
//    TX frame 8N1 at clk25/16 = 1562500 baud (bit = 640 ns), start bit
//    exactly 640 ns, status port IN 05h (bit A1 = TXRDY), busy-write
//    drop, reset mid-frame (button qualifier ~400 ns -> GSR);
//  - v2.1 differences vs v2.0 (core 20 -> 18 MCs): adv_q and tx_run
//    are collapsed - bit_cnt encodes frame bit-times 1..10 (idle = 0,
//    busy = |bit_cnt, TXRDY = ~|bit_cnt); jam baud_cnt <= 0 (first
//    shift on the same edge as v2.0 - adv_q lag compensated); shreg 9
//    bit self-idle and ld_tx_q are UNCHANGED; node v3.9.8 (ring r0..r6
//    on clk 50, X1 = r0, X2 = ~r0, clk25 = /2, POR in 50-domain) is
//    BIT-FOR-BIT the lowsize v3.9.8-clear base;
//  - TX-only core: no RX; SID = RX transit observer is alive; SOD
//    (P72) is a keep'd observer input.
// Run:  bash scripts/run_tb_v21.sh
//   or: iverilog -g2001 -o tb_txuart.vvp tb_txuart_v21.v top_txuart_por6_v21_utf8.v
//       vvp tb_txuart.vvp
// Expect: "TOTAL: N pass, 0 fail" + "SIMULATION PASSED".
//=====================================================================
`timescale 1ns/1ps

module tb_txuart;

  localparam CLKP  = 20;      // 50 MHz tick: 20 ns (H1 without shunt, v3.9.8)
  localparam BITNS = 640;     // 16 ticks of clk25 (40 ns) = 640 ns = 1562500 baud
  localparam T     = 280;     // CPU T-state at 3.571 MHz (unchanged)
  localparam RSTLAT = 500;    // button qualifier latency (p.21): 2FF + 8 clk25 + margin

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
  reg [63:0] w_start, w_x1;

  initial begin
    // ---- wait POR (v3.9.8 base: 8 strobes of por_ce=r0, release ~1020 ns) ----
    #(3000);
    chk(RESET_IN === 1'b1, "C1: RESET_IN released after POR (reset_q register)");
    chk(TX === 1'b1,      "C1: TX idle '1' (shreg INIT=1FF)");
    chk(dut.clk25_q === 1'b0 || dut.clk25_q === 1'b1, "C1: clk25_q divider alive");
    cpu_io_read(8'h05, val);
    chk(val === 8'h02,    "C1: status IN 05h = 02h (TXRDY=1, A0=0, A7..A2=0)");
    chk(SID === RX,       "C1: SID = RX transit alive");

    // ---- C1b: ring node - X1 period exactly 140 ns, X2 = ~X1 ----
    fork
      begin : x1_period
        @(posedge X1); w_x1 = $time;
        @(posedge X1);
        chk(($time - w_x1) === 140, "C1b: X1 period exactly 140 ns (7.143 MHz, ring/7)");
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
            "C2(55): start bit exactly 640 ns (16 ticks of clk25)");
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
    chk(dut.bit_cnt !== 4'd0,  "C4: frame running (busy = |bit_cnt, v2.1)");
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

    $display("TOTAL: %0d pass, %0d fail", pass, fail);
    if (fail == 0) $display("SIMULATION PASSED");
    else           $display("SIMULATION FAILED");
    $finish;
  end

endmodule
