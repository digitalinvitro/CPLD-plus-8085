#requires -Version 5
<#
uart_speed.ps1 v1.2 - измеритель ФАКТИЧЕСКОЙ скорости приёма UART (Windows, PowerShell 5.1+)
Пара к прошивке TXSTRESS v1.1 (beta/txuart/rom/txstress, 8085 + XC95108).
Совместима и с v1.0 hex: баннер "TXSTRESS v1.0" и "TXSTRESS v1.1" принимаются оба.

v1.2 - ДИАГНОСТИЧЕСКИЙ РЕЛИЗ (по итогам трёх прогонов 11-10, COM13 1М):
  КОРЕНЬ НАЙДЕН И ИСПРАВЛЕН на стороне прошивки: ассемблер asm8085.py считал
  ANI/ADI/ACI/CPI однобайтовыми (размер 1, эмиссия 2) - все метки после первого
  ANI уезжали на +13..14 байт, hex v1.0 исполнялся КОРРУПТИРОВАННЫМ: баннер
  печатался как 3 байта КОДА, после FLOOD ЦП уходил в дикий цикл, печатая байт
  53h ('S') непрерывно ~58.2К Б/с - реконструкция симуляцией 1-в-1 совпала с
  прогонами владельца (58 936/59 624 Б/с, 0 баннеров). Прошивка v1.1 собрана
  исправленным ассемблером и просимулирована по hex. ЧТО ДОБАВЛЕНО ЗДЕСЬ:
  - баннер ищется ВЕСЬ поток (и v1.0, и v1.1) по regex, лендмарки принимаются
    и без токена (v1.0), и с токеном "B=xxxx TXSTRESS" (v1.1);
  - СЫРАЯ ДИАГНОСТИКА при отсутствии баннера: +1-разрывы/пробеги, доля 'U',
    hexdump первых байт, оценка периода байта и ТАБЛИЦА КАНДИДАТОВ
    "если это FLOOD/SPRINT/BURST, то фактический T = ... нс";
  - счёт ПУСТЫХ секунд (прогон 1 владельца: 11 активных из 60 - сразу видно);
  - -Probe: быстрый диагноз (3 с + hexdump) без полного замера;
  - -SaveRaw <файл>: весь сырой поток в файл для разбора;
  - лендмарк-токен в IDLE: если баннера нет, но в потоке есть "B=... TXSTRESS",
    значит TXSTRESS исполняется (идёт FLOOD) - печатается сразу;
  - хвост до ПЕРВОГО баннера больше не считается порчей ("хвост между фазами").

Что меряет:
  - поток байт/с посекундно, средняя/макс/пустые секунды, % от линии (baud/10);
  - в -Mode txstress - фазы прошивки по маркерам:
      FLOOD : 65536 байт инкрементного паттерна (+1 mod 256), лендмарки
              "B=xxxx TXSTRESS" каждые 8 КБ (7 шт за фазу);
      SPRINT: 16384 записей 'U' вслепую - на 1 000 000 бод ядро принимает
              каждый 2-й = 8192 'U' (если 05h окажется алиасом того же ядра -
              больше 'U', это НЕ порча: приходят и 05h-записи);
      BURST : честный ПЕРЕГРУЗ (запись каждые 14.875T) - принимается ~2816
              'U' за фазу (сетка 14T внутри прохода + 28T на стыке проходов);
      цикл  : banner->banner ~1.09 с - средняя скорость линии на длинном окне.

Замер скорости - главный критерий: FLOOD обязан идти ровно темпом CPU
(74 405 Б/с при TX_BOTH=1, ~73 950 с учётом лендмарков), SPRINT/BURST показывают
поведение ядра на границе и за границей линии. Целостность паттерна = отсутствие
бит-ошибок на линии.

Примеры:
  .\uart_speed.ps1 -ListPorts
  .\uart_speed.ps1 -Port COM13                       # txstress, 1 000 000, 60 c
  .\uart_speed.ps1 -Port COM13 -Baud 1562500         # ядро v2.2 (25/16)
  .\uart_speed.ps1 -Port COM13 -Mode monitor -Seconds 30 -Csv speed.csv
  .\uart_speed.ps1 -Port COM13 -TxBoth 0             # если прошит _p04.hex
  .\uart_speed.ps1 -Port COM13 -Probe                # 3 c + hexdump: что вообще идёт
  .\uart_speed.ps1 -Port COM13 -SaveRaw raw.bin      # сырой поток в файл

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
    [int]$HexDump = 256,          # сколько первых байт потока показать в ИТОГ (0 = выкл)
    [string]$SaveRaw = '',        # файл для сырого потока (диагностика; до 64 МБ)
    [switch]$Probe,               # быстрый диагноз: 3 с + hexdump 512 и всё
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
if ($Probe) {
    if ($Seconds -eq 60) { $Seconds = 3 }
    if ($HexDump -lt 512) { $HexDump = 512 }
}

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
if ($Probe) { Write-Host 'Режим -Probe: короткий диагноз (содержимое потока важнее скоростей)' }
Write-Host 'ОЖИДАНИЯ (TXSTRESS v1.1):'
Write-Host ('  FLOOD  (' + ('{0:F0}' -f $floodT) + 'T/Б)  : ' + (Format-N $floodAcc) + ' Б/с (~73 950 с лендмарками), паттерн +1 ЦЕЛ, лендмарков "B=xxxx TXSTRESS" 7 за цикл')
Write-Host ('  SPRINT (' + ('{0:F0}' -f $sprintT) + 'T/Б) : приём ' + (Format-N $sprintAcc) + ' Б/с -> U=' + (Format-N $sprintUExp) + ' за фазу (записано 16384; алиас 05h даст больше U - это НЕ порча)')
Write-Host ('  BURST  (' + ('{0:F3}' -f $burstT) + 'T/Б): приём ~' + (Format-N $burstAcc) + ' Б/с -> U~2816 за фазу (записано 8192) - ПЕРЕГРУЗ')
Write-Host '  цикл баннер->баннер ~1.09 с; после сброса пауза ~0.5 с; перед баннером ~20 мс тишины'
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
$script:rLm = 0; $script:rLmBad = 0; $script:rLmTok = 0
$script:rSprU = 0; $script:rSprNon = 0; $script:rSprDt = 0.0
$script:rBurU = 0; $script:rBurNon = 0; $script:rBurDt = 0.0
$script:cycBytes = 0; $script:cycDt = 0.0

# сырая диагностика (IDLE): +1-разрывы/пробеги/U + гистограмма; hexdump; SaveRaw
$script:rawAcc = New-Object 'int[]' 7                 # 0=разрывы 1=макс.пробег 2=сумма 3=число 4='U' 5=prev 6=тек.пробег
$script:rawHist = New-Object 'int[]' 256              # гистограмма байтов (топ-байт для диагноза)
$script:rawTotal = 0
$script:rawCsOk = $false
$script:hexBuf = New-Object 'System.Collections.Generic.List[byte]'
$script:rawChunks = New-Object 'System.Collections.Generic.List[byte[]]'
$script:rawBytes = 0
$script:rawCap = 64MB
$script:rawCapped = $false
$script:idleLmCount = 0
$script:idleLmNoted = $false

# маркеры: баннер - по regex (v1.0 и v1.1+), фазы - литеральные строки
$script:rxBan = [regex]'\r\nTXSTRESS v1\.\d\r\n'
$script:rxLm = [regex]'B=[0-9A-F]{4}( TXSTRESS)?\r\n'
$script:markers = @{
    FLOOD  = 'FLOOD OK' + $script:CRLF
    SPRINT = 'SPRINT OK' + $script:CRLF
    BURST  = 'BURST OK' + $script:CRLF
}
$script:nextState = @{ IDLE = 'FLOOD'; FLOOD = 'SPRINT'; SPRINT = 'BURST'; BURST = 'IDLE' }
$script:expectedLm = @('0020', '0040', '0060', '0080', '00A0', '00C0', '00E0')  # 7 шт за цикл (v1.1)
$script:tailLen = 18                                  # >= самый длинный маркер - 1

# сырой сканер +1: Add-Type один раз (нативно, миллионы байт/с); при отказе -
# fallback на первые 64 КБ в PowerShell (медленно, но достаточно для диагноза)
if (-not ('RawScan.Uart' -as [type])) {
    try {
        Add-Type -TypeDefinition @"
namespace RawScan {
  public static class Uart {
    // acc: [0]=+1 разрывы, [1]=макс.пробег, [2]=сумма пробегов, [3]=число
    // пробегов, [4]=байтов 55h 'U', [5]=последний байт (-1 нет), [6]=тек.пробег
    // hist[256] - гистограмма байтов (накопительная между вызовами)
    public static void Scan(byte[] b, int n, int[] acc, int[] hist) {
      int prev = acc[5]; int cur = acc[6];
      for (int i = 0; i < n; i++) {
        int v = b[i];
        if (prev >= 0) {
          if (v == ((prev + 1) & 0xFF)) { cur++; if (cur > acc[1]) acc[1] = cur; }
          else { if (cur > 0) { acc[2] += cur; acc[3]++; } acc[0]++; cur = 0; }
        } else { cur = 0; }
        if (v == 0x55) acc[4]++;
        hist[v]++;
        prev = v;
      }
      acc[5] = prev; acc[6] = cur;
    }
  }
}
"@ -ErrorAction Stop
        $script:rawCsOk = $true
    }
    catch {
        $script:rawCsOk = $false
        Write-Host '  (Add-Type недоступен - сырая диагностика по первым 64 КБ)' -ForegroundColor DarkGray
    }
}

function Invoke-RawScan([byte[]]$buf, [int]$n) {
    if ($script:rawCsOk) {
        [RawScan.Uart]::Scan($buf, $n, $script:rawAcc, $script:rawHist)
    }
    elseif ($script:rawTotal -lt 65536) {
        $take = [Math]::Min($n, 65536 - $script:rawTotal)
        $prev = $script:rawAcc[5]; $cur = $script:rawAcc[6]
        for ($i = 0; $i -lt $take; $i++) {
            $v = [int]$buf[$i]
            if ($prev -ge 0) {
                if ($v -eq (($prev + 1) -band 0xFF)) { $cur++; if ($cur -gt $script:rawAcc[1]) { $script:rawAcc[1] = $cur } }
                else { if ($cur -gt 0) { $script:rawAcc[2] += $cur; $script:rawAcc[3]++ }; $script:rawAcc[0]++; $cur = 0 }
            }
            else { $cur = 0 }
            if ($v -eq 0x55) { $script:rawAcc[4]++ }
            $script:rawHist[$v]++
            $prev = $v
        }
        $script:rawAcc[5] = $prev; $script:rawAcc[6] = $cur
    }
    $script:rawTotal += $n
}

function Invoke-HexKeep([byte[]]$buf, [int]$n) {
    if ($script:HexDump -le 0) { return }
    $need = $script:HexDump - $script:hexBuf.Count
    if ($need -le 0) { return }
    if ($n -lt $need) { $need = $n }
    for ($i = 0; $i -lt $need; $i++) { $script:hexBuf.Add($buf[$i]) }
}

function Invoke-RawKeep([byte[]]$buf, [int]$n) {
    if ($script:SaveRaw -eq '') { return }
    if ($script:rawBytes -ge $script:rawCap) { $script:rawCapped = $true; return }
    $take = [Math]::Min($n, $script:rawCap - $script:rawBytes)
    $b2 = New-Object byte[] $take
    [Array]::Copy($buf, $b2, $take)
    $script:rawChunks.Add($b2)
    $script:rawBytes += $take
}

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
        if ($script:cycleStartPos -ge 0) {
            # хвост между BURST OK и баннером - обязан быть пустым (v1.2: до
            # ПЕРВОГО баннера окно не считается порчей - это частичный цикл)
            $script:rTail += ($winEnd - $winStart)
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
        $lms = $script:rxLm.Matches($win)
        $data = $script:rxLm.Replace($win, '')
        $lmVals = @()
        foreach ($mm in $lms) {
            $lmVals += $mm.Value.Substring(2, 4)
            if ($mm.Value.EndsWith(' TXSTRESS' + $script:CRLF)) { $script:rLmTok++ }
        }
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
            Write-Host ('  FLOOD : ' + (Format-N $data.Length) + ' Б, паттерн +1 ЦЕЛ, B= ' + $lmVals.Count + '/7 (токенов ' + $script:rLmTok + '), ' + (Format-N $rate) + ' Б/с') -ForegroundColor Green
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
# ВАЖНО (урок v1.1): переменная объекта НЕ может называться $port - параметр
# $Port типизирован [string], PS игнорирует регистр: объект молча превратился
# бы в строку. Объект живёт в $sp.
if ($PSVersionTable.PSVersion.Major -ge 6) {
    Add-Type -AssemblyName System.IO.Ports -ErrorAction SilentlyContinue   # pwsh 7+: сборка не всегда загружена
}
try {
    $names = [System.IO.Ports.SerialPort]::GetPortNames()
}
catch {
    Write-Host ('ОШИБКА: System.IO.Ports недоступен в этой среде: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Запустите в Windows PowerShell 5.1 (powershell.exe).' -ForegroundColor Yellow
    exit 1
}
if ($names -notcontains $Port) {
    Write-Host ('ОШИБКА: порт ' + $Port + ' не найден. Доступны: ' + ($names -join ', ')) -ForegroundColor Red
    exit 1
}

$sp = New-Object System.IO.Ports.SerialPort
$sp.PortName = $Port
$sp.BaudRate = $Baud
$sp.DataBits = $DataBits
$sp.Parity = $Parity            # строка -> enum, PS конвертирует сам
$sp.StopBits = $StopBits
$sp.ReadBufferSize = 131072
$sp.ReadTimeout = 250
$sp.DtrEnable = $true
$sp.RtsEnable = $true
try {
    $sp.Open()
}
catch {
    Write-Host ('ОШИБКА: не удалось открыть ' + $Port + ': ' + $_.Exception.Message) -ForegroundColor Red
    if ($_.Exception -is [System.UnauthorizedAccessException] -or $_.Exception -is [System.IO.IOException]) {
        Write-Host 'Порт занят другим процессом - закройте терминал/PuTTY и повторите.' -ForegroundColor Yellow
    }
    $names = [System.IO.Ports.SerialPort]::GetPortNames() -join ', '
    Write-Host ('Доступны: ' + $names + '  (список: .\uart_speed.ps1 -ListPorts)') -ForegroundColor Yellow
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

        $tms = $sw.Elapsed.TotalMilliseconds
        $script:totalBytes += $n

        # посекундные вёдра
        $sec = [int][math]::Floor($tms / 1000.0)
        if ($script:buckets.ContainsKey($sec)) { $script:buckets[$sec] += $n }
        else { $script:buckets[$sec] = $n }

        # чанк: время + позиция (до добавления символов)
        [void]$script:cTimes.Add($tms)
        [void]$script:cStarts.Add($script:globalPos)

        # сырые диагностики - по ВСЕМ байтам потока (до всяких фаз)
        Invoke-HexKeep $buf $n
        Invoke-RawKeep $buf $n

        if ($Mode -eq 'txstress') {
            # сырой +1-сканер - только пока синхронизация не найдена (IDLE):
            # это и есть зона "неизвестного потока" для диагноза
            if ($script:state -eq 'IDLE') { Invoke-RawScan $buf $n }

            # хвост (18 симв.) НЕ был просканирован - теперь ищем с его начала
            $s = $script:tail + $script:Latin.GetString($buf, 0, $n)
            $sBase = $script:globalPos - $script:tail.Length
            [void]$script:sb.Append($s.Substring($script:tail.Length))
            $script:globalPos = $script:sb.Length

            $searchFrom = 0
            while ($true) {
                if ($script:state -eq 'IDLE') {
                    $bm = $script:rxBan.Match($s, $searchFrom)
                    if (-not $bm.Success) { break }
                    $idx = $bm.Index; $mkLen = $bm.Length
                }
                else {
                    $marker = $script:markers[$script:state]
                    $idx = $s.IndexOf($marker, $searchFrom)
                    if ($idx -lt 0) { break }
                    $mkLen = $marker.Length
                }
                Close-Phase ($sBase + $idx) $mkLen
                $searchFrom = $idx + $mkLen
            }
            # лендмарк-токен без баннера: доказательство, что исполняется TXSTRESS
            if ($script:state -eq 'IDLE') {
                $lm = $script:rxLm.Match($s)
                if ($lm.Success) {
                    $script:idleLmCount++
                    if (-not $script:idleLmNoted) {
                        $script:idleLmNoted = $true
                        Write-Host ('  !! Баннера нет, но найден лендмарк "' + $lm.Value.TrimEnd() + '" - это TXSTRESS, идёт FLOOD; баннер должен появляться каждые ~1.1 c') -ForegroundColor Yellow
                    }
                }
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
        Write-Host ('  FLOOD : ср. ' + (Format-N $avgFl) + ' Б/с (ожидание ' + (Format-N $floodAcc) + '), разрывов +1: ' + $script:rBreaks + ', лендмарков B=: ' + $script:rLm + ' (плохих ' + $script:rLmBad + '), токенов TXSTRESS: ' + $script:rLmTok)
        Write-Host ('  SPRINT: ср. ' + (Format-N $avgSp) + ' Б/с, U=' + (Format-N $script:rSprU) + ' (ожидание ' + (Format-N ($sprintUExp * $script:cycleCount)) + '), ЧУЖИХ ' + (Format-N $script:rSprNon))
        Write-Host ('  BURST : ср. ' + (Format-N $avgBu) + ' Б/с, U=' + (Format-N $script:rBurU) + ' (ожидание ~' + (Format-N (2816 * $script:cycleCount)) + '), ЧУЖИХ ' + (Format-N $script:rBurNon))
        if ($script:rTail -gt 0) {
            Write-Host ('  Хвосты между циклами (BURST OK -> баннер): ' + $script:rTail + ' Б (ожидание 0)')
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
    elseif ($Mode -eq 'txstress' -and $script:cycleCount -eq 0) {
        # ---- СЫРАЯ ДИАГНОСТИКА: баннер не найден ни разу ----
        $msg = 'СИНХРОНИЗАЦИЯ: баннер TXSTRESS не найден за всё окно'
        if ($script:idleLmCount -gt 0) {
            $msg += ' (но лендмарков-токенов ' + $script:idleLmCount + ' - TXSTRESS исполняется, ждите баннер)'
        }
        else {
            $msg += ' и лендмарков-токенов нет - в ПЗУ, вероятно, НЕ TXSTRESS'
        }
        Write-Host ('  ' + $msg) -ForegroundColor Yellow
        if ($script:rawTotal -gt 0) {
            $acc = $script:rawAcc
            $br = $acc[0]; $mx = $acc[1]; $rc = $acc[3]; $rs = $acc[2]; $uc = $acc[4]
            $topVal = -1; $topCnt = 0
            for ($i2 = 0; $i2 -lt 256; $i2++) {
                if ($script:rawHist[$i2] -gt $topCnt) { $topCnt = $script:rawHist[$i2]; $topVal = $i2 }
            }
            $avgRun = 0.0; if ($rc -gt 0) { $avgRun = ($rs + $acc[6]) / ($rc + 1) }
            $pct = 100.0 * $br / [Math]::Max(1, $script:rawTotal)
            $topAsc = '.'
            if ($topVal -ge 32 -and $topVal -lt 127) { $topAsc = [char]$topVal }
            Write-Host ('  СЫРОЙ ПОТОК (' + (Format-N $script:rawTotal) + ' Б): +1-разрывов ' + (Format-N $br) + ' (' + ('{0:F1}' -f $pct) + '%), макс-пробег ' + (Format-N ($mx + 1)) + ', ср. пробег ' + ('{0:F0}' -f ($avgRun + 1)) + ', байт 55h(U): ' + (Format-N $uc) + ' (' + ('{0:F1}' -f (100.0 * $uc / [Math]::Max(1, $script:rawTotal))) + '%), топ-байт ' + ('{0:X2}h' -f $topVal) + ' (' + $topAsc + ') x ' + (Format-N $topCnt) + ' (' + ('{0:F1}' -f (100.0 * $topCnt / $script:rawTotal)) + '%)')
            if ($mx -ge 200 -and $pct -lt 2) {
                Write-Host '  ПОХОЖЕ: непрерывный инкрементный (+1) поток - FLOOD-подобный, БЕЗ маркеров' -ForegroundColor Yellow
            }
            elseif ($topCnt -gt 0.9 * $script:rawTotal) {
                Write-Host ('  ПОХОЖЕ: монотонный поток одного байта ' + ('{0:X2}h' -f $topVal) + ' - дикий цикл печати (точно как v1.0 с битым ассемблером!)') -ForegroundColor Red
            }
            elseif ($uc -gt 0.9 * $script:rawTotal) {
                Write-Host "  ПОХОЖЕ: поток почти целиком 'U' (55h) - фаза SPRINT/BURST" -ForegroundColor Yellow
            }
            else {
                Write-Host '  СТРУКТУРА: не опознана - смотрите hexdump' -ForegroundColor Yellow
            }
        }
        # угадывание режима по медиане активных секунд
        $rates2 = @($script:buckets.Keys | ForEach-Object { $script:buckets[$_] } | Where-Object { $_ -gt 0 } | Sort-Object)
        if ($rates2.Count -gt 0) {
            $med = $rates2[[int][Math]::Floor(($rates2.Count - 1) / 2)]
            $usPerByte = 1000000.0 / $med
            Write-Host ('  ТЕМП: медиана активных секунд ' + (Format-N $med) + ' Б/с = ' + ('{0:F2}' -f $usPerByte) + ' мкс/байт = ' + ('{0:F1}' -f ($usPerByte * 3.125)) + 'T@320нс')
            Write-Host ('    если это FLOOD (42T/Б): фактический T = ' + ('{0:F0}' -f ($usPerByte / 42.0 * 1000)) + ' нс (норма 320)')
            Write-Host ('    если это FLOOD p04 (32T/Б): T = ' + ('{0:F0}' -f ($usPerByte / 32.0 * 1000)) + ' нс')
            Write-Host ('    если это SPRINT-приём (62T/принятый): T = ' + ('{0:F0}' -f ($usPerByte / 62.0 * 1000)) + ' нс')
            Write-Host ('    если это BURST-приём (~43.3T/принятый): T = ' + ('{0:F0}' -f ($usPerByte / 43.3 * 1000)) + ' нс')
            Write-Host '    T=320нс у какого-то кандидата = опознанная фаза; не совпало нигде = в ПЗУ чужая программа.'
        }
        if ($exitCode -eq 0) { $exitCode = 1 }
    }

    # ---- hexdump первых байт потока ----
    if ($script:HexDump -gt 0 -and $script:hexBuf.Count -gt 0) {
        Write-Host ('  HEXDUMP первых ' + $script:hexBuf.Count + ' байт потока:')
        $tot = $script:hexBuf.Count
        for ($off = 0; $off -lt $tot; $off += 16) {
            $end = [Math]::Min($off + 16, $tot)
            $hex = ''; $asc = ''
            for ($i = $off; $i -lt $end; $i++) {
                $b = $script:hexBuf[$i]
                $hex += ('{0:X2} ' -f $b)
                if ($b -ge 32 -and $b -lt 127) { $asc += [char]$b } else { $asc += '.' }
            }
            Write-Host ('    {0:X4}  {1} {2}' -f $off, $hex.PadRight(48), $asc)
        }
    }

    # ---- сырой дамп в файл ----
    if ($script:SaveRaw -ne '' -and $script:rawChunks.Count -gt 0) {
        $all = New-Object byte[] $script:rawBytes
        $o = 0
        foreach ($c2 in $script:rawChunks) { [Array]::Copy($c2, 0, $all, $o, $c2.Length); $o += $c2.Length }
        [IO.File]::WriteAllBytes($SaveRaw, $all)
        $note = ''
        if ($script:rawCapped) { $note = ', ОБРЕЗАН по 64 МБ' }
        Write-Host ('  RAW-дамп: ' + $SaveRaw + ' (' + (Format-N $script:rawBytes) + ' Б' + $note + ')')
    }

    # посекундная таблица
    $secs = @($script:buckets.Keys | Sort-Object)
    if ($secs.Count -gt 0) {
        $rates = @(); foreach ($s2 in $secs) { $rates += $script:buckets[$s2] }
        $maxR = ($rates | Measure-Object -Maximum).Maximum
        $minR = ($rates | Measure-Object -Minimum).Minimum
        $totalSecs = [int][math]::Floor($elapsed)
        $silent = 0
        for ($t2 = 0; $t2 -lt $totalSecs; $t2++) {
            if (-not $script:buckets.ContainsKey($t2) -or $script:buckets[$t2] -eq 0) { $silent++ }
        }
        $silNote = ''
        if ($silent -gt 0) { $silNote = ' - ПУСТЫХ: ' + $silent + ' из ' + $totalSecs + ' (поток прерывался!)' }
        Write-Host ('  Посекундно: мин ' + (Format-N $minR) + ' / макс ' + (Format-N $maxR) + ' Б/с, секунд: ' + $secs.Count + $silNote)
        if ($Mode -eq 'monitor' -or $silent -gt 0) {
            foreach ($s2 in $secs) {
                Write-Host ('    t=' + ('{0,3}' -f $s2) + ' c: ' + (Format-N $script:buckets[$s2]) + ' Б/с')
            }
        }
    }

    if ($Csv -ne '') {
        $lines = @('sec;bytes;bps')
        foreach ($s2 in $secs) {
            $lines += ('' + $s2 + ';' + $script:buckets[$s2] + ';' + $script:buckets[$s2])
        }
        [IO.File]::WriteAllLines($Csv, $lines)
        Write-Host ('  CSV: ' + $Csv)
    }

    if ($sp.IsOpen) { $sp.Close() }
    $sp.Dispose()
}

exit $exitCode
