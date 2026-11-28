#!/bin/bash
# Прогон сравнительных симуляций old-vs-new UART (v39G08 v2).
# Требуется iverilog (в песочнице: /tmp/my-project/tools/iverilog/root/usr/bin,
# см. симлинк usr/x86_64-linux-gnu -> lib/x86_64-linux-gnu).
set -e
IV=${IV:-/tmp/my-project/tools/iverilog/root/usr/bin}
OLD=/tmp/uart_sim/g08_old_modules.v        # TXUART_OLD/RXUART_OLD (из аплоада v1)
NEW=/home/z/my-project/beta/txuart/v39gen/top_txuart_por6_v39G08_utf8.v
OUT=/tmp/uart_sim

# извлечь старые модули из аплоада владельца (CP1251), переименовав
iconv -f CP1251 -t UTF-8 /home/z/my-project/upload/top_txuart_por6_v39G08.v | tr -d '\r' > $OUT/g08_orig_utf8.v
{ sed -n '/^module TXUART_CLKOUT_RALL/,/^endmodule/p' $OUT/g08_orig_utf8.v | sed 's/module TXUART_CLKOUT_RALL/module TXUART_OLD/';
  echo; sed -n '/^module RXUART_2M/,/^endmodule/p' $OUT/g08_orig_utf8.v | sed 's/module RXUART_2M/module RXUART_OLD/'; } > $OLD

$IV/iverilog -g2001 -o $OUT/tx.vvp $OLD $NEW /home/z/my-project/scripts/tb_txuart_compact.v
$IV/vvp $OUT/tx.vvp | tee /home/z/my-project/download/v39G08_uart_compact/tx_sim.log | grep -E "RESULT|PASS|ОШИБКА"
$IV/iverilog -g2001 -o $OUT/rx.vvp $OLD $NEW /home/z/my-project/scripts/tb_rxuart_compact.v
$IV/vvp $OUT/rx.vvp | tee /home/z/my-project/download/v39G08_uart_compact/rx_sim.log | grep -E "RESULT|PASS|ОШИБКА"
