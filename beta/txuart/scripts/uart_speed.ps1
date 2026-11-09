#requires -Version 5
<#
uart_speed.ps1 - измеритель ФАКТИЧЕСКОЙ скорости приёма UART (Windows, PowerShell 5.1+)
Пара к прошивке TXSTRESS v1.0 (beta/txuart/rom/txstress, 8085 + XC95108).

Без TXSTRESS тоже работает: -Mode monitor меряет чистый поток с любой прошивки.

Что меряет:
  - поток байт/с посекундно, средняя/макс, % от линии (baud/10);
  - в -Mode txstress - фазы прошивки по маркерам:
      FLOOD : 65536 байт инкрементного паттерна (+1 mod 256), лендмарки B=xxxx;
      SPRINT: 16384 байта 0x55 ('U') - на 1 000 000 бод ядро принимает каждый
              2-й байт (кадр 31.25T, темп записи 31T), на 1 562 500 - все;
      BURST : честный ПЕРЕГРУЗ (запись каждые 14.875T) - кадры целы, часть
              отброшена ядром; мусор здесь возможен и не страшен;
      цикл  : banner->banner - средняя скорость линии на длинном окне.

Замер скорости - главный критерий: FLOOD обязан идти ровно темпом CPU
(74 405 Б/с при TX_BOTH=1), SPRINT/BURST показывают поведение ядра на границе
и за границей линии. Целостность паттерна = отсутствие бит-ошибок на линии.

Примеры:
  .\uart_speed.ps1 -ListPorts
  .\uart_speed.ps1 -Port COM3                        # txstress, 1 000 000, 60 c
  .\uart_speed.ps1 -Port COM3 -Baud 1562500          # ядро v2.2 (25/16)
  .\uart_speed.ps1 -Port COM3 -Mode monitor -Seconds 30 -Csv speed.csv
  .\uart_speed.ps1 -Port COM3 -TxBoth 0              # если прошит _p04.hex

ВНИМАНИЕ: закройте PuTTY/терминал - COM-порт не должен быть занят.
Точность: счётчики байтов точные; скорости фаз - интерполяция по чанкам
приёма (единицы процентов); средняя по циклам/окну - самая точная.
#>
param(
    [string]$Port = '',
    [int]$Baud = 1000000,
    [int]$DataBits = 8,
    [ValidateSet('None', 'Odd', 'Even')][string]$Parity = 'None',
    [ValidateSet('One', 'Two')][string]$StopBits = 'One',
    [ValidateSet('txstress', 'monitor')][string]$Mode = 'txstress',
    [int]$Seconds = 60,
    [int]$TxBoth = 1,
    [switch]$ListPorts,
    [string]$Csv = ''
)

# ---------------------------------------------------------------- служебные
$script:Latin = [Text.Encoding]::GetEncoding(28591)   # Latin-1: байт <-> символ 1:1
$script:CRLF = "`r`n"
$script:Tns = 320e-9                                  # такт 8085 @ 3.125 МГц

function Format-N([double]$v) { return ('{0:N0}' -f $v) }

if ($ListPorts) {
    Write-Host 'Доступные COM-порты:'
    $names = [System.IO.Ports.SerialPort]::GetPortNames()
    if ($names.Count -eq 0) { Write-Host '  (нет)' }
    foreach ($n in ($names | Sort-Object)) { Write-Host ('  ' + $n) }
    exit 0
}
if ($Port -eq '') {
    Write-Host 'Укажите -Port COMx (список: .\uart_speed.ps1 -ListPorts)' -ForegroundColor Yellow
    exit 1
}
if ($TxBoth -ne 0) { $TxBoth = 1 }

# ------------------------------------------------- ожидания по темпам ядра
# Кадр 8N1 = 10 бит. Ядро: запись при busy тихо отбрасывается, приём =
# 1 байт на k записей, k = ceil(кадр/темп записи).
$frameT = 10.0 / ($Baud * $script:Tns)                # кадр в тактах ядра
$floodT = 42.0; $sprintT = 31.0
if ($TxBoth -eq 0) { $floodT = 32.0; $sprintT = 21.0 }
$burstT = 14.875

function Get-Accept([double]$paceT) {
    if ($paceT -ge $frameT) { return 1.0 / ($paceT * $script:Tns) }
    $k = [math]::Ceiling($frameT / $paceT)
    return 1.0 / ($k * $paceT * $script:Tns)
}
function Get-UExpected([int]$written, [double]$paceT) {
    if ($paceT -ge $frameT) { return $written }
    $k = [math]::Ceiling($frameT / $paceT)
    return [math]::Floor($written / $k)
}

$lineRate = $Baud / 10.0
$floodAcc = Get-Accept $floodT
$sprintAcc = Get-Accept $sprintT
$burstAcc = Get-Accept $burstT
$sprintUExp = Get-UExpected 16384 $sprintT
$burstUExp = Get-UExpected 8192 $burstT

Write-Host ('Порт ' + $Port + '  ' + (Format-N $Baud) + ' 8N1 (' + $Parity + '/' + $StopBits + ')  линия: ' + (Format-N $lineRate) + ' Б/с')
Write-Host ('Окно ' + $Seconds + ' c, режим ' + $Mode + ', TX_BOTH=' + $TxBoth + ' (T=320 нс, кадр ' + ('{0:F2}' -f $frameT) + 'T)')
Write-Host 'ОЖИДАНИЯ (TXSTRESS v1.0):'
Write-Host ('  FLOOD  (' + ('{0:F0}' -f $floodT) + 'T/Б)  : ' + (Format-N $floodAcc) + ' Б/с, паттерн +1 ЦЕЛ, лендмарков B= 7 за цикл')
Write-Host ('  SPRINT (' + ('{0:F0}' -f $sprintT) + 'T/Б) : приём ' + (Format-N $sprintAcc) + ' Б/с -> U=' + (Format-N $sprintUExp) + ' за фазу (записано 16384)')
Write-Host ('  BURST  (' + ('{0:F3}' -f $burstT) + 'T/Б): приём ~' + (Format-N $burstAcc) + ' Б/с -> U~' + (Format-N $burstUExp) + ' за фазу (записано 8192) - ПЕРЕГРУЗ')
Write-Host ''

# ---------------------------------------------------------------- состояние
$script:sb = New-Object Text.StringBuilder            # весь поток (Latin-1)
$script:cTimes = New-Object 'System.Collections.Generic.List[double]'   # время чанка, мс
$script:cStarts = New-Object 'System.Collections.Generic.List[int]'     # глоб. позиция чанка
$script:globalPos = 0
$script:tail = ''
$script:seekK = 0
$script:buckets = @{}                                 # секунда -> байты
$script:totalBytes = 0

# машина фаз txstress
$script:state = 'IDLE'
$script:phaseStartPos = 0
$script:cycleStartPos = -1
$script:cycleCount = 0
$script:floodPrev = -1
# накопители ЗА ВЕСЬ ПРОГОН (не сбрасываются по циклам)
$script:rTail = 0
$script:rFlData = 0; $script:rFlDt = 0.0; $script:rBreaks = 0
$script:rLm = 0; $script:rLmBad = 0
$script:rSprU = 0; $script:rSprNon = 0; $script:rSprDt = 0.0
$script:rBurU = 0; $script:rBurNon = 0; $script:rBurDt = 0.0
$script:cycBytes = 0; $script:cycDt = 0.0

$script:markers = @{
    IDLE   = $script:CRLF + 'TXSTRESS v1.0' + $script:CRLF
    FLOOD  = 'FLOOD OK' + $script:CRLF
    SPRINT = 'SPRINT OK' + $script:CRLF
    BURST  = 'BURST OK' + $script:CRLF
}
$script:nextState = @{ IDLE = 'FLOOD'; FLOOD = 'SPRINT'; SPRINT = 'BURST'; BURST = 'IDLE' }
$script:expectedLm = @('0020', '0040', '0060', '0080', '00A0', '00C0', '00E0')  # D&1F==0: 7 шт (D=0x01 при 256-м блоке - выход)
$script:tailLen = 18                                  # >= самый длинный маркер - 1

# время (мс Stopwatch) для глобальной позиции потока: интерполяция по чанкам
function Get-TimeAtPos([double]$pos) {
    $cnt = $script:cStarts.Count
    if ($cnt -eq 0) { return 0.0 }
    $k = $script:seekK
    if ($k -ge $cnt) { $k = $cnt - 1 }
    while ($k -gt 0 -and $script:cStarts[$k] -gt $pos) { $k-- }
    while ($k -lt ($cnt - 1) -and $script:cStarts[$k + 1] -le $pos) { $k++ }
    $script:seekK = $k
    $t0 = $script:cTimes[$k]; $p0 = $script:cStarts[$k]
    if ($k -eq ($cnt - 1)) {
        # последний чанк: темп по последним ~10 чанкам
        $j = $k - 10; if ($j -lt 0) { $j = 0 }
        $spanT = $t0 - $script:cTimes[$j]
        $spanB = $p0 - $script:cStarts[$j]
        if ($spanB -gt 0 -and $spanT -gt 0) {
            return $t0 + ($pos - $p0) * ($spanT / $spanB)
        }
        return $t0
    }
    $p1 = $script:cStarts[$k + 1]
    $frac = ($pos - $p0) / [math]::Max(1, ($p1 - $p0))
    return $t0 + $frac * ($script:cTimes[$k + 1] - $t0)
}

# закрытие фазы: окно [phaseStartPos, mkPos), маркер начинается в mkPos
function Close-Phase([int]$mkPos, [int]$mkLen) {
    $winStart = $script:phaseStartPos
    $winEnd = $mkPos
    if ($winEnd -lt $winStart) { $winEnd = $winStart }
    $t0 = Get-TimeAtPos $winStart
    $t1 = Get-TimeAtPos $winEnd
    $dt = $t1 - $t0
    $st = $script:state

    if ($st -eq 'IDLE') {
        # хвост между BURST OK и баннером - обязан быть пустым
        $script:rTail += ($winEnd - $winStart)
        if ($script:cycleStartPos -ge 0) {
            $cb = $mkPos - $script:cycleStartPos
            $cd = $t1 - (Get-TimeAtPos $script:cycleStartPos)
            $script:cycleCount++
            $script:cycBytes += $cb; $script:cycDt += $cd
            $rate = 0.0; if ($cd -gt 0) { $rate = $cb / $cd }
            $pct = 0.0; if ($cd -gt 0) { $pct = 100.0 * $rate / $lineRate }
            Write-Host ('=== ЦИКЛ ' + $script:cycleCount + ': ' + (Format-N $cb) + ' Б за ' + ('{0:F0}' -f $cd) + ' мс -> ' + (Format-N $rate) + ' Б/с (' + ('{0:F1}' -f $pct) + '% линии)')
        }
        $script:cycleStartPos = $mkPos
    }
    elseif ($st -eq 'FLOOD') {
        $win = $script:sb.ToString($winStart, $winEnd - $winStart)
        $lms = [regex]::Matches($win, 'B=[0-9A-F]{4}\r\n')
        $data = [regex]::Replace($win, 'B=[0-9A-F]{4}\r\n', '')
        $lmVals = @()
        foreach ($m in $lms) { $lmVals += $m.Value.Substring(2, 4) }
        $badLm = 0
        for ($i = 0; $i -lt $lmVals.Count; $i++) {
            if ($i -ge 8 -or $lmVals[$i] -ne $script:expectedLm[$i]) { $badLm++ }
        }
        # целостность инкрементного паттерна (+1 mod 256)
        $prev = $script:floodPrev; $breaks = 0
        foreach ($ch in $data.ToCharArray()) {
            $b = [int]$ch
            if ($prev -ge 0 -and $b -ne ((($prev + 1) -band 0xFF))) { $breaks++ }
            $prev = $b
        }
        $script:floodPrev = $prev
        $script:rFlData += $data.Length
        $script:rFlDt += $dt
        $script:rBreaks += $breaks
        $script:rLm += $lmVals.Count
        $script:rLmBad += $badLm
        $rate = 0.0; if ($dt -gt 0) { $rate = $data.Length / $dt }
        if ($breaks -eq 0 -and $badLm -eq 0 -and $lmVals.Count -eq 7) {
            Write-Host ('  FLOOD : ' + (Format-N $data.Length) + ' Б, паттерн +1 ЦЕЛ, B= ' + $lmVals.Count + '/7, ' + (Format-N $rate) + ' Б/с') -ForegroundColor Green
        }
        else {
            Write-Host ('  FLOOD : ' + (Format-N $data.Length) + ' Б, РАЗРЫВОВ +1: ' + $breaks + ', B= ' + $lmVals.Count + '/7 (плохих ' + $badLm + '), ' + (Format-N $rate) + ' Б/с') -ForegroundColor Yellow
        }
    }
    elseif ($st -eq 'SPRINT' -or $st -eq 'BURST') {
        $win = $script:sb.ToString($winStart, $winEnd - $winStart)
        $len = $win.Length
        $u = [regex]::Matches($win, 'U').Count
        $nonU = $len - $u
        if ($st -eq 'SPRINT') {
            $script:rSprU += $u; $script:rSprNon += $nonU; $script:rSprDt += $dt
            $tag = 'SPRINT'
        }
        else {
            $script:rBurU += $u; $script:rBurNon += $nonU; $script:rBurDt += $dt
            $tag = 'BURST '
        }
        $rate = 0.0; if ($dt -gt 0) { $rate = $len / $dt }
        if ($nonU -eq 0) {
            Write-Host ('  ' + $tag + ': ' + (Format-N $len) + ' Б, U=' + (Format-N $u) + ', чужих 0, ' + (Format-N $rate) + ' Б/с') -ForegroundColor Green
        }
        else {
            Write-Host ('  ' + $tag + ': ' + (Format-N $len) + ' Б, U=' + (Format-N $u) + ', ЧУЖИХ ' + (Format-N $nonU) + ' (бит-ошибки), ' + (Format-N $rate) + ' Б/с') -ForegroundColor Red
        }
    }

    $script:phaseStartPos = $mkPos + $mkLen
    $script:state = $script:nextState[$st]
}

# ---------------------------------------------------------------- порт
$port = New-Object System.IO.Ports.SerialPort
$port.PortName = $Port
$port.BaudRate = $Baud
$port.DataBits = $DataBits
$port.Parity = $Parity            # строка -> enum, PS конвертирует сам
$port.StopBits = $StopBits
$port.ReadBufferSize = 131072
$port.ReadTimeout = 250
$port.DtrEnable = $true
$port.RtsEnable = $true
try {
    $port.Open()
}
catch {
    Write-Host ('ОШИБКА: не удалось открыть ' + $Port + ': ' + $_.Exception.Message) -ForegroundColor Red
    $names = [System.IO.Ports.SerialPort]::GetPortNames() -join ', '
    Write-Host ('Доступны: ' + $names + '  (терминал/PuTTY закрыт?)') -ForegroundColor Yellow
    exit 1
}
Write-Host ('Читаю ' + $Port + '... (остановка: Ctrl+C)')

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$buf = New-Object byte[] 65536
$exitCode = 0

try {
    while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
        $n = 0
        try {
            $n = $port.BaseStream.Read($buf, 0, $buf.Length)
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

        $tms = $sw.Elapsed.TotalMilliseconds
        $script:totalBytes += $n

        # посекундные вёдра
        $sec = [int][math]::Floor($tms / 1000.0)
        if ($script:buckets.ContainsKey($sec)) { $script:buckets[$sec] += $n }
        else { $script:buckets[$sec] = $n }

        # чанк: время + позиция (до добавления символов)
        [void]$script:cTimes.Add($tms)
        [void]$script:cStarts.Add($script:globalPos)

        if ($Mode -eq 'txstress') {
            # хвост (18 симв.) НЕ был просканирован - теперь ищем с его начала
            $s = $script:tail + $script:Latin.GetString($buf, 0, $n)
            $sBase = $script:globalPos - $script:tail.Length
            [void]$script:sb.Append($s.Substring($script:tail.Length))
            $script:globalPos = $script:sb.Length

            $searchFrom = 0
            while ($true) {
                $marker = $script:markers[$script:state]
                $idx = $s.IndexOf($marker, $searchFrom)
                if ($idx -lt 0) { break }
                Close-Phase ($sBase + $idx) $marker.Length
                $searchFrom = $idx + $marker.Length
            }
            if ($s.Length -gt $script:tailLen) {
                $script:tail = $s.Substring($s.Length - $script:tailLen)
            }
            else {
                $script:tail = $s
            }
        }
        else {
            $script:globalPos += $n
        }
    }
}
finally {
    $sw.Stop()
    $elapsed = $sw.Elapsed.TotalSeconds
    $avgAll = 0.0
    if ($elapsed -gt 0.001) { $avgAll = $script:totalBytes / $elapsed }
    Write-Host ''
    Write-Host '==== ИТОГ =================================================='
    Write-Host ('  Окно: ' + ('{0:F1}' -f $elapsed) + ' c, принято ' + (Format-N $script:totalBytes) + ' байт -> средняя ' + (Format-N $avgAll) + ' Б/с (' + ('{0:F1}' -f (100.0 * $avgAll / $lineRate)) + '% линии ' + (Format-N $lineRate) + ' Б/с)')

    if ($Mode -eq 'txstress' -and $script:cycleCount -gt 0) {
        $avgCyc = 0.0; if ($script:cycDt -gt 0) { $avgCyc = $script:cycBytes / $script:cycDt }
        $avgFl = 0.0; if ($script:rFlDt -gt 0) { $avgFl = $script:rFlData / $script:rFlDt }
        $avgSp = 0.0; if ($script:rSprDt -gt 0) { $avgSp = ($script:rSprU + $script:rSprNon) / $script:rSprDt }
        $avgBu = 0.0; if ($script:rBurDt -gt 0) { $avgBu = ($script:rBurU + $script:rBurNon) / $script:rBurDt }
        Write-Host ('  Циклов: ' + $script:cycleCount + '; средний цикл ' + (Format-N ($script:cycBytes / $script:cycleCount)) + ' Б за ' + ('{0:F0}' -f ($script:cycDt / $script:cycleCount)) + ' мс -> ' + (Format-N $avgCyc) + ' Б/с')
        Write-Host ('  FLOOD : ср. ' + (Format-N $avgFl) + ' Б/с (ожидание ' + (Format-N $floodAcc) + '), разрывов +1: ' + $script:rBreaks + ', лендмарков B=: ' + $script:rLm + ' (плохих ' + $script:rLmBad + ')')
        Write-Host ('  SPRINT: ср. ' + (Format-N $avgSp) + ' Б/с, U=' + (Format-N $script:rSprU) + ' (ожидание ' + (Format-N ($sprintUExp * $script:cycleCount)) + '), ЧУЖИХ ' + (Format-N $script:rSprNon))
        Write-Host ('  BURST : ср. ' + (Format-N $avgBu) + ' Б/с, U=' + (Format-N $script:rBurU) + ' (ожидание ~' + (Format-N ($burstUExp * $script:cycleCount)) + '), ЧУЖИХ ' + (Format-N $script:rBurNon))
        if ($script:rTail -gt 0) {
            Write-Host ('  Хвост между фазами (BURST OK -> banner): ' + $script:rTail + ' Б (ожидание 0)')
        }
        $bad = $script:rBreaks + $script:rSprNon + $script:rBurNon + $script:rLmBad
        if ($bad -eq 0) {
            Write-Host '  ВЕРДИКТ: бит-ошибок НЕТ, все фазы целы' -ForegroundColor Green
        }
        else {
            Write-Host ('  ВЕРДИКТ: ПОРЧЕНИЯ: ' + $bad + ' (FLOOD-разрывы + чужие байты фаз + плохие лендмарки)') -ForegroundColor Red
            $exitCode = 1
        }
    }

    # посекундная таблица
    $secs = @($script:buckets.Keys | Sort-Object)
    if ($secs.Count -gt 0) {
        $rates = @(); foreach ($s2 in $secs) { $rates += $script:buckets[$s2] }
        $maxR = ($rates | Measure-Object -Maximum).Maximum
        $minR = ($rates | Measure-Object -Minimum).Minimum
        Write-Host ('  Посекундно: мин ' + (Format-N $minR) + ' / макс ' + (Format-N $maxR) + ' Б/с, секунд: ' + $secs.Count)
        if ($Mode -eq 'monitor') {
            foreach ($s2 in $secs) {
                Write-Host ('    t=' + ('{0,3}' -f $s2) + ' c: ' + (Format-N $script:buckets[$s2]) + ' Б/с')
            }
        }
    }

    if ($Csv -ne '') {
        $inv = [System.Globalization.CultureInfo]::InvariantCulture
        $lines = @('sec;bytes;bps')
        foreach ($s2 in $secs) {
            $lines += ('' + $s2 + ';' + $script:buckets[$s2] + ';' + $script:buckets[$s2])
        }
        [IO.File]::WriteAllLines($Csv, $lines)
        Write-Host ('  CSV: ' + $Csv)
    }

    if ($port.IsOpen) { $port.Close() }
    $port.Dispose()
}

exit $exitCode
