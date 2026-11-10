#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РЕКОНСТРУКЦИЯ ТРЁХ ПРОГОНОВ ВЛАДЕЛЬЦА (11-10, COM13 1М, TX_BOTH=1):
исполняем СТАРЫЙ txstress_v10.hex, собранный АССЕМБЛЕРОМ С БАГОМ size_of
(ANI/ADI/ACI/CPI считались 1-байтовыми) - тот самый hex, что прошит в ПЗУ.

Ожидаемая картина (симуляция докажет или опровергнет):
  - баннер "TXSTRESS v1.0" НЕ появляется: LXI H,M_BAN грузит M_BAN-14,
    PBAN печатает байты КОДА до ближайшего 00h (2-3 мусорных байта);
  - после FLOOD прыжки JNZ SPIN / JZ FDONE ведут в чужой код - ЦП уходит
    в дикий цикл с непрерывным OUT'ом ПОСТОЯННОЙ скорости;
  - темп дикого потока должен совпасть с наблюдаемыми ~59.6 КБ/с.
Аудит: посекундный профиль (по 1М T), +1-пробеги, гистограмма байтов.
"""
import sys, importlib.util
from collections import Counter

spec = importlib.util.spec_from_file_location(
    'm', '/home/z/my-project/scripts/sim_txstress_v11.py')
m = importlib.util.module_from_spec(spec)
sys.modules['m'] = m
spec.loader.exec_module(m)

BASE = '/home/z/my-project/CPLD-plus-8085/beta/txuart/rom/txstress'
T_NS = 320e-9

def main():
    print("== Реконструкция: txstress_v10.hex (корруптированный ассемблером) ==")
    mem = m.load_hex(f'{BASE}/txstress_v10.hex')
    cpu = m.CPU(mem, 'noop')
    WINDOW = 30_000_000          # ~9.4 реальных секунд (>= 5 циклов v1.0)
    s = cpu.run(WINDOW)
    n = len(s)
    print(f"  окно {WINDOW / 1e6:.1f}M T = {WINDOW * T_NS:.2f} c, записей {cpu.writes}, принято {n} Б")
    print(f"  средний темп: {n / (WINDOW * T_NS):,.0f} Б/с")

    # посекундный профиль (1 с = 3.125M T): байты, попадающие в секунду,
    # восстанавливаем по временам ПРИЁМА - у потока нет времён, поэтому
    # считаем профиль по временам ЗАПИСЕЙ ядра, отфильтрованных по приёму:
    # прием = подмножество записей; воспроизводим времена приема из wtimes
    # невозможно без сопоставления - вместо этого дампим профиль по ПРИНЯТЫМ
    # байтам равномерно внутри их записи... точный вариант: пере-запуск с
    # логом (t_приёма, байт).
    cpu2 = m.CPU(mem, 'noop')
    acc_t = []
    orig_out = cpu2.out
    def probe(port, val):
        had = len(cpu2.stream)
        orig_out(port, val)
        if len(cpu2.stream) > had:
            acc_t.append((cpu2.t, val))
    cpu2.out = probe
    cpu2.run(WINDOW)
    # посекундные вёдра (как в uart_speed.ps1: секунда от старта чтения)
    buckets = {}
    for t, v in acc_t:
        sec = int(t * T_NS)
        buckets[sec] = buckets.get(sec, 0) + 1
    secs = sorted(buckets)
    rates = [buckets[x] for x in secs]
    print(f"  секунд с данными: {len(secs)} из {secs[-1] + 1 if secs else 0}")
    print(f"  посекундно: мин {min(rates):,} / макс {max(rates):,} Б/с")
    mid = rates[len(rates) // 4: 3 * len(rates) // 4]
    mid.sort()
    print(f"  медиана активных секунд: {mid[len(mid) // 2]:,} Б/с (у владельца ~59 600)")

    # структура потока
    ban = s.count(b"TXSTRESS v1.0")
    print(f"  вхождений 'TXSTRESS v1.0': {ban} (у владельца: 0)")
    u = s.count(b'U')
    print(f"  байтов 55h 'U': {u} ({100.0 * u / n:.1f}%)")
    hist = Counter(s)
    top = hist.most_common(6)
    print("  топ-6 байтов: " + ', '.join(f'{b:02X}h x{c}' for b, c in top))
    # +1 пробеги
    mx = cur = 0
    brk = 0
    for i in range(1, n):
        if s[i] == ((s[i - 1] + 1) & 0xFF):
            cur += 1
            if cur > mx: mx = cur
        else:
            brk += 1; cur = 0
    print(f"  +1: разрывов {brk} ({100.0 * brk / max(1, n):.1f}%), макс-пробег {mx}")
    print(f"  первые 48 байт: {s[:48].hex(' ')}")
    print(f"  ASCII: {s[:48].decode('latin-1').encode('ascii', 'xdecode') if False else ''.join(chr(c) if 32 <= c < 127 else '.' for c in s[:48])!r}")
    # дамп первых 512 КБ принятого потока - АУТЕНТИЧНЫЙ фидер для самотеста
    # uart_speed v1.2 (диагностика "дикого цикла печати" 1-в-1 с v1.0)
    open('/tmp/txs10_repro.bin', 'wb').write(s[:512_000])
    print(f"  дамп: /tmp/txs10_repro.bin {min(n, 512_000)} Б")

    # сравнение с прогонами владельца
    print("== СРАВНЕНИЕ С ПРОГОНАМИ ВЛАДЕЛЬЦА ==")
    print("  прогон 1 : 60.2 c, 614 871 Б -> 10 212 Б/с, 11 активных секунд (мин 37 453 / макс 62 080)")
    print("  прогоны A/B: 60.0 c, ~3.55 MB -> 59 624 / 58 936 Б/с, 61 сек, мин 31/1, макс 61 280/59 616")
    print("  баннер 'TXSTRESS v1.0' НЕ НАЙДЕН ни в одном прогоне")
    sys.exit(0)

if __name__ == '__main__':
    main()
