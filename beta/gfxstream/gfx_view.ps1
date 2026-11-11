# ======================================================================
#  gfx_view.ps1 v1.0 — PC-вьюер GFXSTREAM v1 (COM 1М 8N1, 160x100 1bpp)
#  Пара к прошивке rom/gfxstream/gfxstream_v1.hex (SPEC beta/gfxstream/SPEC.md)
#
#  ЧТО ДЕЛАЕТ:
#   - GUI-окно WinForms: кадр 160x100 в масштабе x3 (480x300, пиксели
#     чёткие — NearestNeighbor), статус: FPS, SEQ, кадры, пропуски SEQ,
#     ресинки, Б/с;
#   - ресинк по магии A5 5A (прецедент лендмарков TXSTRESS): мусор и
#     FFh-добивка дельты пропускаются сами;
#   - TYPE 01 (полный 2000 Б) и TYPE 02 (дельта-строки 202 Б) — рендер;
#     TYPE 03/04 — пропускаются (зарезервированы SPEC);
#   - FPS-метр по декодированным кадрам за скользящую 1 с.
#
#  РЕЖИМЫ:
#   .\gfx_view.ps1 -Port COM13              # окно
#   .\gfx_view.ps1 -Port COM13 -Scale 4     # крупнее
#   .\gfx_view.ps1 -SelfTest                # самотест без железа (exit 0/1)
#
#  САМОТЕСТ (pwsh 7/Windows PowerShell 5.1): синтетический поток = точная
#  модель прошивки (баннер + 130 кадров: полные 0..74, дельты, ресурсинк
#  на 99-м), подаётся чанками по 4096: счётчики 1-в-1, позиция шара в FB,
#  мусор между кадрами -> ресинк, удалённый кадр -> пропуск SEQ.
# ======================================================================
param(
    [string]$Port = 'COM13',
    [int]$Baud = 1000000,
    [int]$Scale = 3,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
# --- сборки: SerialPort не грузится по умолчанию в pwsh 7 (урок v1.1 uart_speed) ---
if ($PSVersionTable.PSVersion.Major -ge 6) { Add-Type -AssemblyName System.IO.Ports }

# ======================= парсер потока =======================
# Состояние парсера (скриптовые переменные, чтобы и GUI, и самотест
# звали один и тот же Invoke-GfxChunk).
$script:GfxAcc       = New-Object System.Collections.Generic.List[byte]
$script:GfxFb        = New-Object 'byte[]' 2000     # 100 строк x 20 Б
$script:GfxDirty     = @{}                          # номер строки -> 1 (изменённые)
$script:GfxFrames    = 0
$script:GfxGaps      = 0
$script:GfxResync    = 0
$script:GfxResyncB   = 0
$script:GfxLastSeq   = -1
$script:GfxLastType  = 0
$script:GfxFillLeft  = 0   # ожидаемая FFh-добивка дельты (тихий пропуск)
$script:GfxBps       = 0
$script:GfxBpsAcc    = 0
$script:GfxBpsT0     = $null

# --- предрасчёт: байт -> 8 пикселей (int 0..1), MSB = левый пиксель ---
$script:GfxBytePix = New-Object 'object[]' 256
for ($v = 0; $v -lt 256; $v++) {
    $row = New-Object 'int[]' 8
    for ($b = 0; $b -lt 8; $b++) {
        $row[$b] = if (($v -band (1 -shl (7 - $b))) -ne 0) { 1 } else { 0 }
    }
    $script:GfxBytePix[$v] = $row
}

function Reset-GfxParser {
    $script:GfxAcc.Clear()
    $script:GfxFrames = 0; $script:GfxGaps = 0
    $script:GfxResync = 0; $script:GfxResyncB = 0
    $script:GfxLastSeq = -1; $script:GfxLastType = 0
    $script:GfxFillLeft = 0
}

# Применить один кадр (заголовок уже проверен) к FB.
function Invoke-GfxFrame {
    param([byte[]]$Payload, [byte]$Type, [byte]$Seq)
    if ($Type -eq 1) {
        for ($i = 0; $i -lt 2000; $i++) { $script:GfxFb[$i] = $Payload[$i] }
        for ($r = 0; $r -lt 100; $r++) { $script:GfxDirty[$r] = 1 }
    }
    elseif ($Type -eq 2) {
        # блоки идут по возрастанию номеров: [номер строки 1 Б][20 Б]
        $idx = 13
        while ($idx -lt $Payload.Length - 20) {
            $r = $Payload[$idx]
            if ($r -ge 100) { break }
            for ($j = 0; $j -lt 20; $j++) {
                $script:GfxFb[$r * 20 + $j] = $Payload[$idx + 1 + $j]
            }
            $script:GfxDirty[$r] = 1
            $idx += 21
        }
    }
}

# Скормить парсеру очередную пачку байтов из порта.
function Invoke-GfxChunk {
    param([byte[]]$Chunk)
    if ($Chunk.Length -eq 0) { return }
    if ($null -eq $script:GfxBpsT0) { $script:GfxBpsT0 = [DateTime]::UtcNow }
    $script:GfxBpsAcc += $Chunk.Length
    $now = [DateTime]::UtcNow
    if (($now - $script:GfxBpsT0).TotalMilliseconds -ge 1000) {
        $script:GfxBps = [int](1000.0 * $script:GfxBpsAcc / ($now - $script:GfxBpsT0).TotalMilliseconds)
        $script:GfxBpsAcc = 0; $script:GfxBpsT0 = $now
    }
    $script:GfxAcc.AddRange($Chunk)
    while ($true) {
        if ($script:GfxAcc.Count -eq 0) { break }
        # FFh-добивка дельты (конверт 2006 Б): тихий пропуск ожидаемых 1798 Б.
        # Первый не-FF байт = сбой добивки -> обычный скан (честный мусор).
        # Пропуск байтов вне кадров (баннер, мусор) идёт в GfxResyncB.
        if ($script:GfxFillLeft -gt 0) {
            if ($script:GfxAcc[0] -eq 0xFF) {
                $script:GfxAcc.RemoveAt(0)
                $script:GfxFillLeft--
                continue
            }
            $script:GfxFillLeft = 0
        }
        if ($script:GfxAcc.Count -lt 6) { break }
        # ресинк: ищем A5 5A, мусор до него отбрасываем
        if ($script:GfxAcc[0] -ne 0xA5 -or $script:GfxAcc[1] -ne 0x5A) {
            $script:GfxAcc.RemoveAt(0)
            $script:GfxResyncB++
            continue
        }
        $type = $script:GfxAcc[2]
        # УРОК PS: -shl/-bor НЕ расширяют тип: [byte]7 -shl 8 = 0 (mod 256)!
        # Поэтому перед bitwise-операциями явно приводим к Int32.
        $n = [int]$script:GfxAcc[3] -bor ([int]$script:GfxAcc[4] -shl 8)
        $seq = [int]$script:GfxAcc[5]
        $wantN = 0
        if ($type -eq 1) { $wantN = 2000 }
        elseif ($type -eq 2) { $wantN = 202 }
        if ($type -notin 1,2 -or $n -ne $wantN) {
            # не похоже на кадр — сдвиг на 1 байт (псевдомагия в данных)
            $script:GfxAcc.RemoveAt(0)
            $script:GfxResyncB++
            continue
        }
        if ($script:GfxAcc.Count -lt 6 + $n) { break }   # кадр ещё не доехал
        $payload = New-Object 'byte[]' $n
        for ($i = 0; $i -lt $n; $i++) { $payload[$i] = $script:GfxAcc[6 + $i] }
        $script:GfxAcc.RemoveRange(0, 6 + $n)
        # после дельты ожидаем 1798 Б FFh-добивки (тихий пропуск в сканере)
        if ($type -eq 2) { $script:GfxFillLeft = 2006 - 6 - $n }
        # SEQ: первый кадр после ресинка - без штрафа
        if ($script:GfxLastSeq -ge 0 -and $seq -ne (($script:GfxLastSeq + 1) -band 0xFF)) {
            $script:GfxGaps++
        }
        $script:GfxLastSeq = $seq
        Invoke-GfxFrame -Payload $payload -Type $type -Seq $seq
        $script:GfxFrames++
        $script:GfxLastType = $type
        $script:GfxResync++   # счётчик успешных ресинков-кадров подряд
    }
}

# ======================= самотест =======================
# Модель прошивки: баннер + кадры; возвращает поток байтов.
function New-GfxModelStream {
    param([int]$Frames, [switch]$NoBanner)
    $out = New-Object System.Collections.Generic.List[byte]
    if (-not $NoBanner) {
        foreach ($c in [System.Text.Encoding]::ASCII.GetBytes("`r`nGFXSTREAM v1`r`n")) { $out.Add($c) }
    }
    $fb = New-Object 'byte[]' 2000
    for ($r = 0; $r -lt 100; $r++) {
        for ($j = 0; $j -lt 20; $j++) {
            $v = if (($r % 8 -eq 0) -or ($r -eq 99)) { 0xFF } else { if ($j -eq 19) { 0x81 } else { 0x80 } }
            $fb[$r * 20 + $j] = $v
        }
    }
    $c = 0; $r = 0; $dc = 1; $dr = 1; $dph = 0
    for ($k = 0; $k -lt $Frames; $k++) {
        $nc = ($c + $dc) -band 0xFF; $nr = ($r + $dr) -band 0xFF
        if ($nc -eq 0 -or $nc -eq 19) { $dc = -$dc }
        if ($nr -eq 0 -or $nr -eq 92) { $dr = -$dr }
        # стереть старый шар аналитической сеткой (включая бит правой рамки!)
        for ($i = 0; $i -lt 8; $i++) {
            $rr = $r + $i
            $v = if (($rr % 8 -eq 0) -or ($rr -eq 99)) { 0xFF } else { if ($c -eq 19) { 0x81 } else { 0x80 } }
            $fb[$rr * 20 + $c] = $v
        }
        # нарисовать новый
        for ($i = 0; $i -lt 8; $i++) { $fb[($nr + $i) * 20 + $nc] = 0xFF }
        $dph++; $wrap = ($dph -eq 100); if ($wrap) { $dph = 0 }
        $full = ($k -lt 75) -or $wrap
        $out.Add(0xA5); $out.Add(0x5A)
        if ($full) {
            $out.Add(0x01); $out.Add(0xD0); $out.Add(0x07); $out.Add($k -band 0xFF)
            foreach ($b in $fb) { $out.Add($b) }
        } else {
            $out.Add(0x02); $out.Add(0xCA); $out.Add(0x00); $out.Add($k -band 0xFF)
            $mask = New-Object 'byte[]' 13
            # дельта vs показанный кадр: строки [min(pos(k), pos(k+1)) .. max+7]
            # ($r на входе итерации = pos(k) = стёртый старый шар)
            $rmin = [Math]::Min($r, $nr); $rmax = [Math]::Max($r, $nr)
            for ($rr = $rmin; $rr -lt $rmax + 8; $rr++) { $mask[[int][Math]::Floor($rr / 8)] = $mask[[int][Math]::Floor($rr / 8)] -bor (1 -shl ($rr -band 7)) }
            foreach ($b in $mask) { $out.Add($b) }
            for ($rr = $rmin; $rr -lt $rmax + 8; $rr++) {
                $out.Add($rr)
                for ($j = 0; $j -lt 20; $j++) { $out.Add($fb[$rr * 20 + $j]) }
            }
            for ($i = 0; $i -lt (2006 - 6 - 202); $i++) { $out.Add(0xFF) }
        }
        $c = $nc; $r = $nr
    }
    return ,$out.ToArray()
}

function Invoke-GfxSelfTest {
    $ok = $true
    function Req([bool]$cond, [string]$msg) {
        if ($cond) { Write-Host "  OK   $msg" } else { Write-Host "  FAIL $msg"; $script:stOk = $false }
    }
    $script:stOk = $true
    Write-Host "== Самотест gfx_view v1 (модель прошивки, 130 кадров) =="

    # --- тест A: чистый поток 130 кадров ---
    Reset-GfxParser
    $s = New-GfxModelStream -Frames 130
    for ($off = 0; $off -lt $s.Length; $off += 4096) {
        $len = [Math]::Min(4096, $s.Length - $off)
        $chunk = New-Object 'byte[]' $len
        [Array]::Copy($s, $off, $chunk, 0, $len)
        Invoke-GfxChunk -Chunk $chunk
    }
    Req ($script:GfxFrames -eq 130) "кадров декодировано 130 (факт $($script:GfxFrames))"
    Req ($script:GfxGaps -eq 0) "пропусков SEQ 0"
    Req ($script:GfxLastSeq -eq 129) "последний SEQ 129 (факт $($script:GfxLastSeq))"
    Req ($script:GfxResyncB -eq 16) "вне кадров пропущено ровно 16 Б баннера (факт $($script:GfxResyncB))"

    # --- тест B: полный образ FB после 130 кадров = сетка + шар на позиции 130-го шага ---
    $c = 0; $r = 0; $dc = 1; $dr = 1
    for ($k = 0; $k -lt 130; $k++) {
        $c = ($c + $dc) -band 0xFF; $r = ($r + $dr) -band 0xFF
        if ($c -eq 0 -or $c -eq 19) { $dc = -$dc }
        if ($r -eq 0 -or $r -eq 92) { $dr = -$dr }
    }
    $bad = 0
    for ($rr = 0; $rr -lt 100; $rr++) {
        for ($j = 0; $j -lt 20; $j++) {
            $want = if (($rr % 8 -eq 0) -or ($rr -eq 99)) { 0xFF } else { if ($j -eq 19) { 0x81 } else { 0x80 } }
            $isBall = (($rr -ge $r) -and ($rr -lt $r + 8) -and ($j -eq $c))
            if ($isBall) { $want = 0xFF }
            if ($script:GfxFb[$rr * 20 + $j] -ne $want) { $bad++ }
        }
    }
    Req ($bad -eq 0) "FB 1-в-1 модели (сетка + шар на (${c},${r})): расхождений $bad"

    # --- тест C: дельта отмечает РОВНО 9 строк и пишет их содержимое ---
    Reset-GfxParser
    $s2 = New-GfxModelStream -Frames 76
    # подать баннер + кадры 0..74 (полные) одним куском
    $n74 = 16 + 75 * 2006
    $ch74 = New-Object 'byte[]' $n74
    [Array]::Copy($s2, 0, $ch74, 0, $n74)
    Invoke-GfxChunk -Chunk $ch74
    Req ($script:GfxFrames -eq 75) "75 полных кадров (факт $($script:GfxFrames))"
    $script:GfxDirty.Clear()
    # кадр 75 — первая дельта: строки [min(r74,r75) .. max(r74,r75)+7]
    $ch75 = New-Object 'byte[]' 2006
    [Array]::Copy($s2, $n74, $ch75, 0, 2006)
    Invoke-GfxChunk -Chunk $ch75
    $rows = @($script:GfxDirty.Keys | Sort-Object)
    # траектория: r_i = позиция шара после i шагов от (0,0)
    $rp = 0; $dr3 = 1; $rlist = @()
    for ($k = 0; $k -lt 80; $k++) { $rlist += $rp; $rp = ($rp + $dr3) -band 0xFF; if ($rp -eq 0 -or $rp -eq 92) { $dr3 = -$dr3 } }
    $r74 = $rlist[75]; $r75 = $rlist[76]
    $rmin = [Math]::Min($r74, $r75); $rmax = [Math]::Max($r74, $r75)
    $wantRows = @(); for ($rr = $rmin; $rr -lt $rmax + 8; $rr++) { $wantRows += $rr }
    $diff = Compare-Object -ReferenceObject $wantRows -DifferenceObject $rows
    Req ($null -eq $diff) "дельта-строки 1-в-1 модели [$($rmin)..$($rmax+7)] (факт $($rows -join ','))"
    Req ($rows.Count -eq 9) "дельта изменила ровно 9 строк (факт $($rows.Count))"

    # --- тест D: мусор между кадрами -> ресинк, счётчики целы ---
    Reset-GfxParser
    $s3 = New-GfxModelStream -Frames 4
    $mid = [Math]::Floor($s3.Length / 2)
    $junk = [byte[]](0xDE, 0xAD, 0xBE, 0xEF, 0x12)
    $s3j = New-Object 'byte[]' ($s3.Length + $junk.Length)
    [Array]::Copy($s3, 0, $s3j, 0, $mid)
    [Array]::Copy($junk, 0, $s3j, $mid, $junk.Length)
    [Array]::Copy($s3, $mid, $s3j, $mid + $junk.Length, $s3.Length - $mid)
    for ($off = 0; $off -lt $s3j.Length; $off += 4096) {
        $len = [Math]::Min(4096, $s3j.Length - $off)
        $ch = New-Object 'byte[]' $len
        [Array]::Copy($s3j, $off, $ch, 0, $len)
        Invoke-GfxChunk -Chunk $ch
    }
    Req ($script:GfxFrames -eq 4) "4 кадра после мусора (факт $($script:GfxFrames))"
    Req ($script:GfxResyncB -eq 21) "мусор 5 Б + баннер 16 Б отброшены (факт $($script:GfxResyncB))"

    # --- тест E: удалённый кадр -> пропуск SEQ ---
    Reset-GfxParser
    $s4 = New-GfxModelStream -Frames 3
    $s4g = New-Object 'byte[]' ($s4.Length - 2006)
    [Array]::Copy($s4, 0, $s4g, 0, 2006)                    # кадр 0
    [Array]::Copy($s4, 2 * 2006, $s4g, 2006, $s4.Length - 2 * 2006)  # кадр 2 (кадр 1 выброшен)
    for ($off = 0; $off -lt $s4g.Length; $off += 4096) {
        $len = [Math]::Min(4096, $s4g.Length - $off)
        $ch = New-Object 'byte[]' $len
        [Array]::Copy($s4g, $off, $ch, 0, $len)
        Invoke-GfxChunk -Chunk $ch
    }
    Req ($script:GfxGaps -eq 1) "пропуск SEQ найден: 1 (факт $($script:GfxGaps))"
    Req ($script:GfxFrames -eq 2) "2 кадра декодировано (факт $($script:GfxFrames))"

    Write-Host "== САМОТЕСТ ПРОЙДЕН =="
    return $script:stOk
}

# ======================= главный путь =======================
if ($SelfTest) {
    $res = Invoke-GfxSelfTest
    if ($res) { exit 0 } else { exit 1 }
}

# --- GUI-сборки (только для окна; на Linux pwsh их нет — самотест выше) ---
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# --- порт ---
if (-not [System.IO.Ports.SerialPort]::GetPortNames() -contains $Port) {
    Write-Host "Порт $Port не найден. Доступны: $([System.IO.Ports.SerialPort]::GetPortNames() -join ', ')"
    exit 2
}
$sp = New-Object System.IO.Ports.SerialPort
$sp.PortName = $Port
$sp.BaudRate = $Baud
$sp.Parity = 'None'; $sp.DataBits = 8; $sp.StopBits = 'One'
$sp.ReadBufferSize = 131072
$sp.ReadTimeout = 50
try { $sp.Open() } catch {
    if ($_.Exception -is [System.UnauthorizedAccessException]) {
        Write-Host "Порт $Port занят — закройте PuTTY/терминал и повторите."
    } else { Write-Host "Не удалось открыть ${Port}: $($_.Exception.Message)" }
    exit 2
}
Write-Host "COM открыт: $Port $Baud 8N1. Окно gfx_view запускается... (закрыть окно = выход)"

# --- рендер-примитивы ---
$pixS = New-Object 'int[]' (160 * 100)
$bmpS = New-Object System.Drawing.Bitmap 160, 100
$rectS = New-Object System.Drawing.Rectangle 0, 0, 160, 100
$bmpB = New-Object System.Drawing.Bitmap (160 * $Scale), (100 * $Scale)
$colDark = [System.Drawing.Color]::FromArgb(16, 16, 16).ToArgb()
$colLite = [System.Drawing.Color]::FromArgb(230, 230, 230).ToArgb()

function Update-GfxBitmap {
    for ($r = 0; $r -lt 100; $r++) {
        if (-not $script:GfxDirty.ContainsKey($r)) { continue }
        $base = $r * 20; $pixBase = $r * 160
        for ($j = 0; $j -lt 20; $j++) {
            $row = $script:GfxBytePix[$script:GfxFb[$base + $j]]
            $p = $pixBase + $j * 8
            for ($k = 0; $k -lt 8; $k++) { $pixS[$p + $k] = if ($row[$k] -eq 1) { $colLite } else { $colDark } }
        }
    }
    $script:GfxDirty.Clear()
    $bd = $bmpS.LockBits($rectS, [System.Drawing.Imaging.ImageLockMode]::WriteOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    [System.Runtime.InteropServices.Marshal]::Copy($pixS, 0, $bd.Scan0, $pixS.Length)
    $bmpS.UnlockBits($bd)
    $g = [System.Drawing.Graphics]::FromImage($bmpB)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
    $g.Clear([System.Drawing.Color]::FromArgb(16, 16, 16))
    $g.DrawImage($bmpS, 0, 0, (160 * $Scale), (100 * $Scale))
    $g.Dispose()
}

# --- окно ---
$form = New-Object System.Windows.Forms.Form
$form.Text = "GFXSTREAM v1 - $Port $Baud 8N1 (160x100 x$Scale)"
$form.ClientSize = New-Object System.Drawing.Size ((160 * $Scale) + 24, (100 * $Scale) + 70)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedSingle'
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(24, 24, 28)

$pbox = New-Object System.Windows.Forms.PictureBox
$pbox.Location = New-Object System.Drawing.Point 12, 12
$pbox.Size = New-Object System.Drawing.Size ((160 * $Scale), (100 * $Scale))
$pbox.BorderStyle = 'FixedSingle'
$form.Controls.Add($pbox)

$lbl = New-Object System.Windows.Forms.Label
$lbl.Location = New-Object System.Drawing.Point 12, ((100 * $Scale) + 22)
$lbl.Size = New-Object System.Drawing.Size ((160 * $Scale) + 4, 34)
$lbl.ForeColor = [System.Drawing.Color]::FromArgb(200, 210, 200)
$lbl.Font = New-Object System.Drawing.Font 'Consolas', 9
$lbl.Text = 'инициализация...'
$form.Controls.Add($lbl)

$script:statT0 = [DateTime]::UtcNow
$script:fpsShown = 0.0
$script:framesShown = 0
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 15
$timer.Add_Tick({
    try {
        $avail = $sp.BytesToRead
        if ($avail -gt 0) {
            $chunk = New-Object 'byte[]' $avail
            try { $n = $sp.BaseStream.Read($chunk, 0, $avail) } catch { $n = 0 }
            if ($n -gt 0) {
                if ($n -lt $chunk.Length) { $chunk = $chunk[0..($n - 1)] }
                Invoke-GfxChunk -Chunk $chunk
            }
        }
        if ($script:GfxDirty.Count -gt 0) { Update-GfxBitmap; $pbox.Image = $bmpB }
        $now = [DateTime]::UtcNow
        if (($now - $script:statT0).TotalMilliseconds -ge 250) {
            $dt = ($now - $script:statT0).TotalSeconds
            $script:fpsShown = [Math]::Round(($script:GfxFrames - $script:framesShown) / $dt, 1)
            $script:framesShown = $script:GfxFrames
            $script:statT0 = $now
            $lbl.Text = "FPS {0,5:N1}  SEQ {1,3}  кадры {2}  пропуски SEQ {3}  ресинк {4} Б  {5} Б/с" -f `
                $script:fpsShown, $script:GfxLastSeq, $script:GfxFrames, $script:GfxGaps, $script:GfxResyncB, $script:GfxBps
        }
    } catch { $lbl.Text = "ошибка: $($_.Exception.Message)" }
})
$form.Add_Shown({ $timer.Start() })
$form.Add_FormClosed({ $timer.Stop(); $sp.Close() })
[void]$form.ShowDialog()
