#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор эталонного потока TXSTRESS v1.0 (1М бод, TX_BOTH=1) + порченый вариант.
Структура цикла - строго по txstress_v10.asm:
  banner CRLF+"TXSTRESS v1.0"+CRLF
  FLOOD: 256 блоков по 256 байт инкремента C, после каждого лендмарк "B=HHHH\r\n"
         (DE = номер блока x256: 0020..0100), затем "FLOOD OK\r\n"
  SPRINT: 16384 записей 'U', на 1М принимается каждый 2-й -> 8192 'U'
  "SPRINT OK\r\n"
  BURST: 8192 записей, принимается каждый 3-й -> 2731 'U'
  "BURST OK\r\n"
"""
import sys

BANNER = b"\r\nTXSTRESS v1.0\r\n"

def cycle():
    out = bytearray()
    out += BANNER
    # FLOOD: лендмарк при D&0x1F==0 -> D = 0x20..0xE0, РОВНО 7 на цикл,
    # значение = счётчик блоков DE (0x0020..0x00E0); при D=0x01 - выход
    c = 0
    for blk in range(256):
        for _ in range(256):
            out.append(c)
            c = (c + 1) & 0xFF
        if (blk + 1) % 32 == 0 and (blk + 1) < 256:
            out += b"B=" + (b"%04X" % (blk + 1)) + b"\r\n"
    out += b"FLOOD OK\r\n"
    # SPRINT: принят каждый 2-й из 16384
    out += b"U" * 8192
    out += b"SPRINT OK\r\n"
    # BURST: принят каждый 3-й из 8192 -> 2731
    out += b"U" * 2731
    out += b"BURST OK\r\n"
    return bytes(out)

def main():
    ncyc = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    one = cycle()
    data = one * ncyc
    open("/tmp/txs_ok.bin", "wb").write(data)
    # порченый: 3 инъекции в разных местах
    bad = bytearray(data)
    cyc = len(one)
    # (1) потерян байт FLOOD данных в цикле 1
    off = cyc + 40000
    assert bad[off] != 0x0D and bad[off] != 0x42
    del bad[off]
    # (2) бит-ошибка в SPRINT цикла 2 ('U'->'V'); сдвиг -1 после удаления
    off = 2 * cyc + len(BANNER) + 65536 + 64 + 10 + 500 - 1
    assert bad[off] == 0x55
    bad[off] = 0x56
    # (3) бит-ошибка в BURST цикла 3; длина не менялась
    off = 3 * cyc + len(BANNER) + 65536 + 64 + 10 + 8192 + 11 + 100 - 1
    assert bad[off] == 0x55
    bad[off] = 0x00
    open("/tmp/txs_bad.bin", "wb").write(bytes(bad))
    print(f"OK: /tmp/txs_ok.bin {len(data)} B ({ncyc} циклов, {len(one)} Б/цикл)")
    print(f"OK: /tmp/txs_bad.bin {len(bad)} B (3 порчи: FLOOD-потеря, SPRINT-бит, BURST-бит)")

if __name__ == "__main__":
    main()
