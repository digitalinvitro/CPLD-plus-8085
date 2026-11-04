#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Конвертер UTF8 -> CP1251 для линий beta/* (Verilog/UCF для ISE).
Создаёт CP1251-эталон + проверяет round-trip байт-в-байт.
Запуск: python3 scripts/make_twins.py (из любой папки; пути от папки скрипта).
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
HWUART = os.path.normpath(os.path.join(HERE, ".."))

JOBS = [
    ("top_hwuart_por6_v400_utf8.v", "top_hwuart_por6_v400.v"),
    ("top_hwuart_utf8.ucf",         "top_hwuart.ucf"),
]

def roundtrip_ok(text: str) -> bool:
    try:
        raw = text.encode("cp1251")
    except UnicodeEncodeError as e:
        print(f"  !! символ вне CP1251: {e}")
        return False
    return raw.decode("cp1251") == text

def main():
    ok = True
    for src, dst in JOBS:
        sp, dp = os.path.join(HWUART, src), os.path.join(HWUART, dst)
        with open(sp, "r", encoding="utf-8") as f:
            text = f.read()
        if not roundtrip_ok(text):
            ok = False
            continue
        raw = text.encode("cp1251")
        with open(dp, "wb") as f:
            f.write(raw)
        # round-trip: прочитать CP1251, сконвертировать в UTF8, сравнить с исходником
        back = raw.decode("cp1251")
        rt = (back == text)
        print(f"{src} ({len(text.encode('utf-8'))} б UTF8) -> {dst} ({len(raw)} б CP1251); round-trip: {'OK' if rt else 'FAIL'}")
        ok = ok and rt
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
