#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор эталонных потоков для самотеста uart_speed.ps1 v1.2.

Структура цикла - строго по txstress_v11.asm (проверена симуляцией по hex,
sim_txstress_v11.py: баннер 4/4, 7 лендмарков B=xxxx TXSTRESS, SPRINT 8192,
BURST 2816 'U' по реальной сетке 14T/28T):
  banner CRLF+"TXSTRESS v1.1"+CRLF
  FLOOD: 256 блоков по 256 байт инкремента C, лендмарк после блоков
         32..224: "B=%04X TXSTRESS\r\n" (ровно 7), затем "FLOOD OK\r\n"
  SPRINT: принятые 8192 'U'
  "SPRINT OK\r\n"
  BURST: принятые 2816 'U'
  "BURST OK\r\n"
Выдаёт:
  /tmp/txs_ok.bin      - чистый v1.1, ncyc циклов
  /tmp/txs_bad.bin     - 4 порчи (потеря байта FLOOD, бит SPRINT, бит BURST,
                         битое ЗНАЧЕНИЕ лендмарка)
  /tmp/txs_ok_v10.bin  - то же с баннером/лендмарками v1.0 (обратная совместимость)
  /tmp/txs_raw.bin     - БЕЗ баннера: непрерывный +1 (FLOOD-подобный поток,
                         как гипотеза для прогонов A/B владельца)
"""
import sys

BANNER = b"\r\nTXSTRESS v1.1\r\n"
BANNER10 = b"\r\nTXSTRESS v1.0\r\n"


def cycle(banner=BANNER, token=b" TXSTRESS\r\n"):
    out = bytearray()
    out += banner
    c = 0
    for blk in range(256):
        for _ in range(256):
            out.append(c)
            c = (c + 1) & 0xFF
        nb = blk + 1
        if nb % 32 == 0 and nb < 256:
            out += b"B=" + (b"%04X" % nb) + token
    out += b"FLOOD OK\r\n"
    out += b"U" * 8192
    out += b"SPRINT OK\r\n"
    out += b"U" * 2816
    out += b"BURST OK\r\n"
    return bytes(out)


def main():
    ncyc = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    one = cycle()
    data = one * ncyc
    open("/tmp/txs_ok.bin", "wb").write(data)

    # v1.0-совместимость: баннер v1.0, лендмарки без токена
    one10 = cycle(banner=BANNER10, token=b"\r\n")
    open("/tmp/txs_ok_v10.bin", "wb").write(one10 * 10)

    # порченый v1.1: 4 инъекции; каждая следующая ищется В САМОМ bad
    # (первая - удаление байта - сдвигает все офсеты)
    bad = bytearray(data)
    # (1) потерян байт FLOOD данных в цикле 1 (после первого лендмарка)
    lm1 = bad.index(b"B=0020 TXSTRESS\r\n") + len(b"B=0020 TXSTRESS\r\n")
    off = lm1 + 100
    assert bad[off] != 0x0D and bad[off] != 0x42, hex(bad[off])
    del bad[off]
    # (2) бит-ошибка в SPRINT цикла 2 ('U'->'V'): SPRINT-регион лежит МЕЖДУ
    # "FLOOD OK" и "SPRINT OK", поэтому 2-е вхождение "FLOOD OK" + 500
    p2 = -1
    for _ in range(2):
        p2 = bad.index(b"FLOOD OK\r\n", p2 + 1)
    off = p2 + 500
    assert bad[off] == 0x55, hex(bad[off])
    bad[off] = 0x56
    # (3) бит-ошибка в BURST цикла 3: 3-е вхождение "BURST OK", минус 100
    p3 = -1
    for _ in range(3):
        p3 = bad.index(b"BURST OK\r\n", p3 + 1)
    off = p3 - 100
    assert bad[off] == 0x55, hex(bad[off])
    bad[off] = 0x00
    # (4) битое ЗНАЧЕНИЕ лендмарка в цикле 4 (4-е вхождение B=0040: '0'->'X')
    p4 = -1
    for _ in range(4):
        p4 = bad.index(b"B=0040 TXSTRESS\r\n", p4 + 1)
    assert bad[p4 + 2:p4 + 6] == b"0040"
    bad[p4 + 3] = 0x78  # '0'->'X'
    open("/tmp/txs_bad.bin", "wb").write(bytes(bad))

    # безбаннерный непрерывный +1 (гипотеза для прогонов A/B: FLOOD-подобный
    # поток без маркеров) - ~1.5 МБ
    raw = bytearray((one * 12)[:1_500_000])
    # стираем ВСЕ маркеры: баннеры/лендмарки/OK-строки заменяем продолжением
    # паттерна: проще собрать чистый +1 без маркеров
    raw = bytearray()
    v = 0x5A
    while len(raw) < 1_500_000:
        raw.append(v)
        v = (v + 1) & 0xFF
    open("/tmp/txs_raw.bin", "wb").write(bytes(raw))

    print(f"OK: /tmp/txs_ok.bin {len(data)} B ({ncyc} циклов, {len(one)} Б/цикл)")
    print(f"OK: /tmp/txs_bad.bin {len(bad)} B (4 порчи: FLOOD-потеря, SPRINT-бит, BURST-бит, лендмарк)")
    print(f"OK: /tmp/txs_ok_v10.bin {len(one10) * 10} B (10 циклов v1.0: баннер v1.0, лендмарки без токена)")
    print(f"OK: /tmp/txs_raw.bin {len(raw)} B (безбаннерный непрерывный +1)")


if __name__ == "__main__":
    main()
