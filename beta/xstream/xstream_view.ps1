#!/usr/bin/env pwsh
# ======================================================================
# XSTREAM_VIEW.PS1 v1.2 -- клиент XSTREAM: приём потока 80x25 из платы
# (fw xstream_v1) в GUI-окно PowerShell.
#
# ПРОВОД: 1 000 000 8N1; кадр = A5 5A [SEQ] + 2000 Б (80x25, row-major).
# Ресинк по магии A5 5A (мусор/флеш порта пропускается), SEQ mod 256,
# пропуски считаются. Темп задаёт ПЛАТА (тик/прерывание), клиент -
# пассивный приёмник-рендерер (никакого WM_TIMER-пейсинга).
#
# Запуск:
#   .\xstream_view.ps1 -Port COM13
#   .\xstream_view.ps1 -Port COM13 -Baud 1000000 -Log xs_log.csv
#   .\xstream_view.ps1 -SelfTest
#
# Совместимость: Windows PowerShell 5.1 (BOM обязателен; без ??, без
# арифметики в New-Object - только ::new(); DoubleBuffered - только через
# рефлексию (защищённое свойство); уроки gfx_view v1.1-v1.5 + свои 11-12).
#
# v1.2 (по железным отчётам владельца 11-13):
#   1. SelfTest #2 FAIL (frames=1, rs=0): мусор $garb создавался, но
#      НЕ подавался в парсер - в v1.1 пропущен Add-Bytes; теперь подаётся
#      + кейс 2b "мусор, кончающийся A5, перед шапкой" (A5-набег не
#      сдвигает кадр: в state 1 держим ТОЛЬКО последний A5);
#   2. GUI-пад на 5.1 при старте окна: [Brush]::new([SolidBrush](...)) -
#      Brush абстрактный, конструктора с 1 аргументом нет ->
#      SolidBrush::new(цвет);
#   3. ГЛАВНОЕ (всплыло бы следующим): Register-ObjectEvent -Action не
#      видит $script: переменные - Action живёт в скопе PSEventJob-модуля,
#      там $script:RxQueue = $null, Enqueue падал в пустой catch{} -
#      0 кадров при живом потоке. Чтение порта перенесено в GUI-таймер
#      (опрос BytesToRead/Read на UI-потоке; буфер драйвера 256 КБ
#      держит ~2.6 с потока - паузы таймера байтов не теряют).
# ======================================================================
param(
    [string]$Port = "",
    [int]$Baud = 1000000,
    [string]$Log = "",
    [switch]$SelfTest,
    [double]$FontSize = 13
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$Cols = 80
$Rows = 25
$Screen = $Cols * $Rows          # 2000
$FrameLen = 3 + $Screen          # A5 5A SEQ + payload
$Magic1 = 0xA5; $Magic2 = 0x5A
$Enc1251 = [System.Text.Encoding]::GetEncoding(1251)

# ---------------------------------------------------------------- CSV-лог
$script:LogSw = $null
if ($Log -ne "") {
    $script:LogSw = [System.IO.StreamWriter]::new($Log, $false, $Enc1251)
    $script:LogSw.WriteLine("utc,kind,seq,dt_ms,bytes_total,resyncs,seq_gaps")
}

function Write-Log([string]$kind, [int]$seq, [double]$dt, [int]$total, [int]$rs, [int]$gaps) {
    if ($null -ne $script:LogSw) {
        $script:LogSw.WriteLine("{0:yyyy-MM-ddTHH:mm:ss.fff},{1},{2},{3:F1},{4},{5},{6}" -f `
            [DateTime]::UtcNow, $kind, $seq, $dt, $total, $rs, $gaps)
    }
}

# ---------------------------------------------------------------- парсер
# Состояние: 0=ищем A5, 1=ждём 5A+SEQ, 2=набираем payload.
# Зеркало парсера проверено симом (parse_frames в sim_xstream_v1.py).
function New-Parser {
    $p = [hashtable]::Synchronized(@{
        State = 0; Buf = [System.Collections.Generic.List[byte]]::new()
        Screen = [byte[]]::new($Screen); Seq = -1
        Frames = 0; Resyncs = 0; SeqGaps = 0; LastSeq = -1
        LastFrameTicks = [DateTime]::Now.Ticks; DtMs = 0.0
        BytesTotal = 0; Dropped = 0
    })
    return $p
}

function Add-Bytes([hashtable]$p, [byte[]]$data, [int]$n) {
    $i = 0
    while ($i -lt $n) {
        $b = $data[$i]; $i++
        $p.BytesTotal++
        if ($p.State -eq 0) {
            if ($b -eq $Magic1) { $p.State = 1; $p.Buf.Clear(); $p.Buf.Add($b) }
            else { $p.Dropped++ }   # мусор вне кадра
        }
        elseif ($p.State -eq 1) {
            $p.Buf.Add($b)
            if ($b -eq $Magic2) { $p.State = 2 }      # A5 5A пойманы
            elseif ($b -eq $Magic1) { $p.Buf.Clear(); $p.Buf.Add($b) }  # A5 A5... - держим ТОЛЬКО последний A5 (набег A5 из мусора перед шапкой иначе сдвинул бы кадр, v1.2)
            else {
                $p.Resyncs++; $p.State = 0            # A5 x - мусор, ресинк
            }
        }
        else {
            $p.Buf.Add($b)
            if ($p.Buf.Count -eq $FrameLen) {
                $seq = $p.Buf[2]
                $now = [DateTime]::Now.Ticks
                $p.DtMs = ($now - $p.LastFrameTicks) / 10000.0
                $p.LastFrameTicks = $now
                if ($p.LastSeq -ge 0) {
                    $d = ($seq - $p.LastSeq) -band 0xFF
                    if ($d -ne 1) { $p.SeqGaps += ($d - 1 + 256) -band 0xFF }
                }
                $p.LastSeq = $seq
                [Array]::Copy($p.Buf.ToArray(), 3, $p.Screen, 0, $Screen)
                $p.Frames++
                $p.State = 0
                $script:FrameReady = $true
            }
        }
    }
}

# ---------------------------------------------------------------- SelfTest
function Invoke-SelfTest {
    Write-Host "XSTREAM_VIEW SelfTest: синтетический поток + мусор + пропуски SEQ"
    $rnd = [System.Random]::new(2026)
    $fail = 0

    # 1) 130 кадров с живым SEQ и меняющимся содержимым
    $p = New-Parser
    $script:FrameReady = $false
    for ($f = 0; $f -lt 130; $f++) {
        $frame = [byte[]]::new($FrameLen)
        $frame[0] = $Magic1; $frame[1] = $Magic2; $frame[2] = $f -band 0xFF
        for ($k = 0; $k -lt $Screen; $k++) {
            $frame[3 + $k] = [byte]((($k + $f) * 7 + ($k -band 0x0F)) -band 0xFF)
        }
        # подача по кусочкам (проверка склейки через границы чтения)
        $chunk = 64 + $rnd.Next(900)
        for ($off = 0; $off -lt $FrameLen; $off += $chunk) {
            $len = [Math]::Min($chunk, $FrameLen - $off)
            $piece = [byte[]]::new($len)
            [Array]::Copy($frame, $off, $piece, 0, $len)
            Add-Bytes $p $piece $len
        }
    }
    if ($p.Frames -ne 130) { Write-Host "  FAIL: кадров $($p.Frames) != 130"; $fail++ }
    else { Write-Host "  OK: 130 кадров декодировано, SEQ без пропусков ($($p.SeqGaps) гэпов)" }
    $ref = [byte[]]::new($Screen)
    $frame = [byte[]]::new($FrameLen)
    $frame[0] = $Magic1; $frame[1] = $Magic2; $frame[2] = 129
    for ($k = 0; $k -lt $Screen; $k++) { $frame[3 + $k] = [byte]((($k + 129) * 7 + ($k -band 0x0F)) -band 0xFF) }
    [Array]::Copy($frame, 3, $ref, 0, $Screen)
    for ($k = 0; $k -lt $Screen; $k++) {
        if ($p.Screen[$k] -ne $ref[$k]) { Write-Host ("  FAIL: payload байт {0}: {1:X2} != {2:X2}" -f $k, $p.Screen[$k], $ref[$k]); $fail++; break }
    }
    Write-Host "  OK: побайтовая сверка payload кадра 129 (сшивка кусочков чтения)"

    # 2) мусор до кадра -> ресинк без потери кадра (ДЕТЕРМИНИРОВАННО:
    #    одиночный A5 + байт не-5A -> Resyncs>=1; рандом зависел от сида
    #    и мог не дать ни одного A5 - FAIL на железе владельца 11-12;
    #    v1.2: в v1.1 мусор ещё и НЕ подавался (Add-Bytes потерян) ->
    #    frames=1, rs=0 - FAIL в отчёте 11-13)
    $p = New-Parser
    $script:FrameReady = $false
    $garb = [byte[]]::new(137)
    $garb[0] = $Magic1; $garb[1] = 0x11              # A5 + НЕ 5A -> ресинк
    for ($k = 2; $k -lt 137; $k++) { $garb[$k] = 0x33 }
    Add-Bytes $p $garb $garb.Length                  # v1.2: мусор РЕАЛЬНО подаётся
    $frame[2] = 7
    Add-Bytes $p $frame $FrameLen
    if ($p.Frames -ne 1 -or $p.Resyncs -lt 1) { Write-Host "  FAIL: ресинк мусора (frames=$($p.Frames), rs=$($p.Resyncs))"; $fail++ }
    else { Write-Host "  OK: мусор 137 Б (A5 + не-5A) -> ресинк=1, кадр принят без потерь" }

    # 2b) мусор, кончающийся A5, перед шапкой: A5-набег НЕ должен сдвинуть
    #     кадр. v1.1 копил A5-ы в Buf (A5 A5 5A -> SEQ=5A, экран со сдвигом
    #     на 1 Б и потеря байта хвоста); v1.2 держит только последний A5.
    $p = New-Parser
    $script:FrameReady = $false
    $tail = [byte[]]::new(9)
    for ($k = 0; $k -lt 8; $k++) { $tail[$k] = 0x33 }
    $tail[8] = $Magic1                               # мусор ...33 33 A5
    $frame[2] = 7
    Add-Bytes $p $tail 9
    Add-Bytes $p $frame $FrameLen
    # payload кадра #129 из теста 1: scr0 = ((0+129)*7+0)&FF = 87h; SEQ = 7
    # (а не 5A/90 и scr0=07, как было бы при сдвиге)
    if ($p.Frames -ne 1 -or $p.LastSeq -ne 7 -or $p.Screen[0] -ne 0x87) {
        Write-Host ("  FAIL: A5-набег (frames={0}, seq={1}, scr0={2:X2} != 87)" -f $p.Frames, $p.LastSeq, $p.Screen[0]); $fail++
    } else { Write-Host "  OK: мусор ...A5 перед шапкой -> кадр выровнен (SEQ=7, scr0=87)" }

    # 3) пропуск SEQ (плата сбросилась: ...5 -> 200)
    $p = New-Parser
    $script:FrameReady = $false
    $frame[2] = 5;  Add-Bytes $p $frame $FrameLen
    $frame[2] = 200; Add-Bytes $p $frame $FrameLen
    if ($p.SeqGaps -lt 1) { Write-Host "  FAIL: гэп SEQ не замечен"; $fail++ }
    else { Write-Host "  OK: пропуск SEQ (5 -> 200) засчитан ($($p.SeqGaps))" }

    # 4) декод CP1251: байты CP1251 -> кириллица
    $p = New-Parser
    $script:FrameReady = $false
    $frame[2] = 0
    $word = $Enc1251.GetBytes("ПРИВЕТ")
    for ($k = 0; $k -lt $word.Length; $k++) { $frame[3 + $k] = $word[$k] }
    Add-Bytes $p $frame $FrameLen
    $line = $Enc1251.GetString($p.Screen, 0, $word.Length)
    if ($line -ne "ПРИВЕТ") { Write-Host "  FAIL: CP1251-декод ('$line')"; $fail++ }
    else { Write-Host "  OK: CP1251-декод payload -> 'ПРИВЕТ'" }

    if ($fail -eq 0) { Write-Host "SELfTEST: 5/5 ПРОЙДЕНЫ" }
    else { Write-Host "SELfTEST: ПРОВАЛОВ $fail"; exit 1 }
}

if ($SelfTest) { Invoke-SelfTest; exit 0 }

# ---------------------------------------------------------------- GUI
if ($Port -eq "") { Write-Host "Укажите -Port COMxx (или -SelfTest)"; exit 1 }

$script:Parser = New-Parser
$script:FrameReady = $false
$script:PortObj = $null
$script:StartTicks = [DateTime]::Now.Ticks
$script:FpsEma = 0.0
$script:RxAccum = 0
$script:RxRate = 0.0
$script:LastRateTicks = $script:StartTicks
$script:RxBuf = [byte[]]::new(16384)   # переиспользуемый буфер опроса порта

$form = [System.Windows.Forms.Form]::new()
$form.Text = "XSTREAM v1 - 80x25 ($Port @ $Baud 8N1)"
$form.StartPosition = "Manual"
$form.BackColor = [System.Drawing.Color]::FromArgb(12, 12, 16)
$panel = [System.Windows.Forms.Panel]::new()
$panel.Dock = "Fill"
$form.Controls.Add($panel)

$status = [System.Windows.Forms.Label]::new()
$status.Dock = "Bottom"
$status.Height = 28
$status.BackColor = [System.Drawing.Color]::FromArgb(12, 12, 16)
$status.ForeColor = [System.Drawing.Color]::FromArgb(140, 220, 140)
$status.Font = [System.Drawing.Font]::new("Consolas", 10)
$form.Controls.Add($status)
# double-buffering панели через рефлексию (свойство защищённое):
$flags = [System.Reflection.BindingFlags]"Instance,NonPublic"
$null = $panel.GetType().GetProperty("DoubleBuffered", $flags).SetValue($panel, $true, $null)
$panel.BringToFront()

$font = [System.Drawing.Font]::new("Consolas", [double]$FontSize)
$green = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(190, 255, 190))
$dim   = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(90, 130, 90))

$panel.Add_Paint({
    param($sender, $e)
    $scr = $script:Parser.Screen
    for ($r = 0; $r -lt $Rows; $r++) {
        $line = $Enc1251.GetString($scr, $r * $Cols, $Cols)
        $brush = $dim
        if ($line.TrimEnd().Length -gt 0) { $brush = $green }
        $e.Graphics.DrawString($line, $font, $brush, 8, 6 + $r * [int]($font.Height))
    }
})

function Open-Port {
    $script:PortObj = [System.IO.Ports.SerialPort]::new($Port, $Baud, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
    $script:PortObj.ReadBufferSize = 262144
    $script:PortObj.ReadTimeout = 500
    $script:PortObj.Open()
    $script:PortObj.DiscardInBuffer()
    # v1.2: обработчик Register-ObjectEvent DataReceived УДАЛЁН - он живёт в
    # скопе PSEventJob-модуля и НЕ видит $script:RxQueue (там $null,
    # Enqueue падал в пустой catch{} -> 0 кадров при живом потоке).
    # Чтение - опросом в GUI-таймере (см. Add_Tick).
}

Open-Port
Write-Log -Kind "OPEN" -Seq -1 -Dt 0 -Total 0 -Rs 0 -Gaps 0

$timer = [System.Windows.Forms.Timer]::new()
$timer.Interval = 30
$null = $timer.Add_Tick({
    try {
        # v1.2: опрос порта на UI-потоке. BytesToRead -> Read ровно столько,
        # сколько уже в буфере драйвера - чтение неблокирующее. Буфер
        # драйвера 256 КБ >= 2.6 с потока: паузы таймера байтов не теряют.
        $n = $script:PortObj.BytesToRead
        if ($n -gt 0) {
            if ($n -gt $script:RxBuf.Length) { $n = $script:RxBuf.Length }
            $n = $script:PortObj.Read($script:RxBuf, 0, $n)
            if ($n -gt 0) { Add-Bytes $script:Parser $script:RxBuf $n }
        }

        if ($script:FrameReady) {
            $script:FrameReady = $false
            $panel.Invalidate()
            $p = $script:Parser
            $ema = if ($p.DtMs -gt 0) { 1000.0 / $p.DtMs } else { 0 }
            if ($script:FpsEma -eq 0) { $script:FpsEma = $ema } else { $script:FpsEma = 0.8 * $script:FpsEma + 0.2 * $ema }
            Write-Log "D" $p.LastSeq $p.DtMs $p.BytesTotal $p.Resyncs $p.SeqGaps
        }
        $now = [DateTime]::Now.Ticks
        if (($now - $script:LastRateTicks) -ge 10000000) {
            $script:RxRate = $script:Parser.BytesTotal
            $script:LastRateTicks = $now
            $p = $script:Parser
            $el = [int](($now - $script:StartTicks) / 10000000)
            $period = 0.0
            if ($script:FpsEma -gt 0) { $period = 1000.0 / $script:FpsEma }
            $status.Text = ("FPS {0:F1} | период {1:F1} мс | кадров {2} | SEQ-гэпы {3} | ресинк {4} Б | принято {5:F1} КБ | {6} с" -f `
                $script:FpsEma, $period, $p.Frames, $p.SeqGaps, $p.Resyncs, ($p.BytesTotal / 1024.0), $el)
            Write-Log -Kind "S" -Seq $p.LastSeq -Dt 0 -Total $p.BytesTotal -Rs $p.Resyncs -Gaps $p.SeqGaps
        }
    } catch { }
})
$timer.Start()

$form.Add_FormClosed({
    try {
        $timer.Stop()
        if ($null -ne $script:PortObj) { $script:PortObj.Close() }
        $p = $script:Parser
        Write-Log -Kind "FIN" -Seq $p.LastSeq -Dt 0 -Total $p.BytesTotal -Rs $p.Resyncs -Gaps $p.SeqGaps
        if ($null -ne $script:LogSw) { $script:LogSw.Flush(); $script:LogSw.Close() }
        Write-Host ("Итог: кадров {0}, FPS {1:F2}, SEQ-гэпов {2}, ресинков {3}, байт {4}" -f `
            $p.Frames, $script:FpsEma, $p.SeqGaps, $p.Resyncs, $p.BytesTotal)
    } catch { }
})

[void]$form.ShowDialog()
