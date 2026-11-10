#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Хирургия uart_speed.ps1 (v1.2/v1.3) -> /tmp/test_uart_speed.ps1: COM-порт
заменён синтетическим фидером из файла. Код Close-Phase/Get-TimeAtPos/
цикла чтения остаётся 1-в-1 оригиналом."""
import sys

src_path, dst_path, simfile = sys.argv[1], sys.argv[2], sys.argv[3]
txt = open(src_path, encoding="utf-8-sig").read()

# (0) проверки порта -> мимо (SIM: реальных COM нет)
old_noport = """if ($Port -eq '') {
    Write-Host 'Укажите -Port COMx (список: .\\uart_speed.ps1 -ListPorts)' -ForegroundColor Yellow
    exit 1
}"""
assert old_noport in txt, "блок 'укажите порт' не найден"
txt = txt.replace(old_noport, "if ($false) { }")

old_val = """if ($names -notcontains $Port) {
    Write-Host ('ОШИБКА: порт ' + $Port + ' не найден. Доступны: ' + ($names -join ', ')) -ForegroundColor Red
    exit 1
}"""
assert old_val in txt, "блок проверки порта не найден"
txt = txt.replace(old_val, "if ($false) { }")

# (1) блок порта -> симулятор
a1 = "$sp = New-Object System.IO.Ports.SerialPort"
a2 = "Write-Host ('Читаю ' + $Port + '... (остановка: Ctrl+C)')"
i, j = txt.index(a1), txt.index(a2)
sim_block = (
    "$sp = $null\n"
    "$simData = [IO.File]::ReadAllBytes('" + simfile + "')\n"
    "$simPos = 0\n"
    "Write-Host ('SIM-режим: ' + $simData.Length + ' байт эталона, зациклено')\n"
)
txt = txt[:i] + sim_block + txt[j:]

# (2) чтение порта -> чтение из симулятора
old_read = """        $n = 0
        try {
            $n = $sp.BaseStream.Read($buf, 0, $buf.Length)
        }
        catch [TimeoutException] {
            continue
        }
        catch {
            # USB-мост выдернули / порт умер
            Write-Host ('ОШИБКА ЧТЕНИЯ: ' + $_.Exception.Message) -ForegroundColor Red
            $exitCode = 2
            break
        }
        if ($n -le 0) { continue }
"""
new_read = """        $n = [Math]::Min($buf.Length, $simData.Length - $simPos)
        if ($n -gt 2048) { $n = 200 + (Get-Random -Minimum 1 -Maximum 1800) }
        if ($n -le 0) { $simPos = 0; Start-Sleep -Milliseconds 1; continue }
        [Array]::Copy($simData, $simPos, $buf, 0, $n)
        $simPos += $n
        Start-Sleep -Milliseconds 1
"""
assert old_read in txt, "блок чтения не найден"
txt = txt.replace(old_read, new_read)

# (3) закрытие порта в finally -> пустышка
old_close = """    if ($sp.IsOpen) { $sp.Close() }
    $sp.Dispose()
"""
assert old_close in txt, "блок закрытия не найден"
txt = txt.replace(old_close, "    # SIM: порт закрыт\n")

open(dst_path, "w", encoding="utf-8-sig").write(txt)
print(f"OK: {dst_path} (симулятор: {simfile})")
