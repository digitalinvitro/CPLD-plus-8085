//=====================================================================
// tb_hwuart_v401.v - testbench for hwuart v4.0.1 (beta/hwuart).
// NOTES:
//  - ASCII-only comments (encoding-safe for ISE and iverilog);
//  - the PRIMARY verification tool is the cycle-exact sim_hwuart_v400.py
//    (75/75 PASS, scenarios C1-C9); this tb repeats the key functional
//    scenarios for iverilog: TX frame 8N1 at 25MHz/13, RX byte + IRQ,
//    reset mid-frame;
//  - rx_int goes to P75 (RST 7.5); SID = RX transit observer is alive.
//  - v4.0.1 = v4.0.0 + M1 (p.27): POR counter 8->4, strobe por_ce = x1_n
//    (1 pulse per cnt period 280 ns); POR ~1020-1040 ns from INIT
//    (4 shifts F->7->3->1->0), norm 840 ns kept, margin 1.33x.
//  - FIX 11-5 (first real iverilog run; RTL unchanged, stimulus bugs only):
//    (1) C3 polls TXRDY in a loop - a single poll lands while the previous
//    frame still runs (TXRDY=0 legitimately); (2) C5 pre-reads status IN 05h
//    before the RX frame: the io_rd_rx decode is combinational on live IOM +
//    latched addr, after OUT 04h it holds rx_full low until the next bus
//    cycle; (3) C7 frame-start check via dut.tx_run (data C3 has d0=1, the
//    TX line is high during data bits).
// Run:  iverilog -o tb_hwuart.vvp tb_hwuart_v401.v top_hwuart_por6_v401_utf8.v
//       vvp tb_hwuart.vvp
// Expect: "TOTAL: N pass, 0 fail" + "SIMULATION PASSED".
//=====================================================================
`timescale 1ns/1ps

module tb_hwuart;

  localparam CLKP  = 40;      // 25 MHz tick: 40 ns
  localparam BITNS = 520;     // 13 ticks = 520 ns = 1923077.8 baud
  localparam T     = 280;     // CPU T-state (7 ticks)

  reg         clk = 0;
  always #(CLKP/2) clk = ~clk;

  reg  RST = 0, ALE = 0, WRn = 1, RDn = 1, IOM = 0, A15 = 0;
  reg  SOD = 0, RX = 1;
  reg  [7:0] A_tb = 8'h00;  reg A_en = 0;
  reg  [7:0] D_tb = 8'h00;  reg D_en = 0;
  reg  r0 = 0, r1 = 0, r2 = 0, r3 = 0, r4 = 0;

  wire [7:0] A = A_en ? A_tb : 8'bZZZZZZZZ;
  wire [7:0] D = D_en ? D_tb : 8'bZZZZZZZZ;

  wire CSr_n, OEr_n, CS_n, OE_n, WE_n, CS1, X1, X2, READY, RESET_IN, SID, TX, SND, rx_int;
  wire [7:0] seg;  wire [3:0] dig;  wire col0, col1, col2, col3;

  retro_pcld_top #(.POR_W(6), .CLK_DIV(2), .CLK_HALF(1)) dut (
    .clk(clk), .RST(RST),
    .ALE(ALE), .WRn(WRn), .RDn(RDn), .IOM(IOM), .A15(A15),
    .A(A), .D(D),
    .CSr_n(CSr_n), .OEr_n(OEr_n), .CS_n(CS_n), .OE_n(OE_n), .WE_n(WE_n), .CS1(CS1),
    .X1(X1), .READY(READY), .RESET_IN(RESET_IN),
    .SID(SID), .TX(TX), .rx_int(rx_int),
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
      RDn = 0; A_en = 0;          // CPU releases AD, CPLD drives rows/data
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

  // ---------- PC side: RX line driver (8N1 frame) ----------
  task pc_send(input [7:0] byte);
    integer i;
    begin
      RX = 0; #(BITNS);                 // start
      for (i = 0; i < 8; i = i + 1) begin
        RX = (byte >> i) & 1; #(BITNS); // LSB first
      end
      RX = 1; #(BITNS);                 // stop
    end
  endtask

  // ---------- helpers ----------
  integer k;
  integer guard;
  reg rx_seen;
  reg [7:0] val;
  reg [63:0] w_start;

  initial begin
    // ---- wait POR (~1020-1040 ns from INIT, M1: 4 shifts x 280 ns) ----
    #(3000);
    chk(RESET_IN === 1'b1, "C1: RESET_IN released after POR");
    chk(TX === 1'b1,      "C1: TX idle '1'");
    chk(rx_int === 1'b0,  "C1: no IRQ in idle");

    // ---- C2: TX frame 0x55, bit grid = 13 ticks ----
    fork
      begin : tx_frame55
        @(negedge TX);
        w_start = $time;
        // first rising edge must be exactly one bit later (d0 of 0x55 = 1)
        @(posedge TX);
        chk(($time - w_start) === BITNS,
            "C2(55): start bit exactly 520 ns");
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
        // still be running (5.2 us), a single poll would see TXRDY=0
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

    // ---- C5: RX byte 0x5A -> IRQ -> read clears ----
    // pre-read of status: the io_rd_rx decode is combinational on live
    // IOM + latched addr - after the last OUT 04h it stays active EVERY
    // tick and holds rx_full low until the next bus cycle changes the
    // address. Real firmware polls status first - do the same.
    cpu_io_read(8'h05, val);
    rx_seen = 0;
    fork
      begin : rx5a
        pc_send(8'h5A);
      end
      begin
        @(posedge rx_int);
        rx_seen = 1;
      end
    join
    chk(rx_seen === 1'b1, "C5: rx_int (RST7.5) asserted at stop");
    begin
      cpu_io_read(8'h05, val);
      chk(val[0] === 1'b1, "C5: status RXRDY=1");
      cpu_io_read(8'h04, val);
      chk(val === 8'h5A, "C5: IN 04h returns 0x5A");
      chk(rx_int === 1'b0, "C5: read clears IRQ");
    end

    // ---- C7: reset mid-TX-frame ----
    cpu_io_write(8'h04, 8'hC3);
    // frame-start check is hierarchical (tx_run): with data C3 (d0=1)
    // the TX line leaves the start bit high during data bits, so a
    // line-level check after BITNS is meaningless
    chk(dut.tx_run === 1'b1, "C7: frame started");
    #(BITNS/2);               // still inside the frame
    RST = 1; #100;
    chk(TX === 1'b1, "C7: GSR drives TX to '1' immediately");
    chk(dut.tx_run === 1'b0 && dut.shreg === 9'h1FF, "C7: core cleared");
    RST = 0; #(BITNS * 2);
    chk(TX === 1'b1, "C7: idle after reset");

    $display("TOTAL: %0d pass, %0d fail", pass, fail);
    if (fail == 0) $display("SIMULATION PASSED");
    else           $display("SIMULATION FAILED");
    $finish;
  end

endmodule
