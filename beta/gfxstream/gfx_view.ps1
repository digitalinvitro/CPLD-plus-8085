# ======================================================================
#  gfx_view.ps1 v1.5 — PC-вьюер GFXSTREAM (COM 1М 8N1, 160x100 1bpp)
#  Пара к прошивке rom/gfxstream/gfxstream_v22.hex (SPEC beta/gfxstream/SPEC.md)
#
#  ЧТО ДЕЛАЕТ:
#   - GUI-окно WinForms: кадр 160x100 в масштабе x3 (480x300, пиксели
#     чёткие — NearestNeighbor), статус (2 строки): FPS, SEQ, кадры;
#     инт ср/макс мс между декодами, пропуски SEQ, ресинки, буф макс, Б/с;
#   - ресинк по магии A5 5A (прецедент лендмарков TXSTRESS): мусор и
#     FFh-добивка дельты пропускаются сами;
#   - TYPE 01 (полный 2000 Б) и TYPE 02 (дельта-строки 202 Б) — рендер;
#     TYPE 03/04 — пропускаются (зарезервированы SPEC);
#   - FPS-метр по декодированным кадрам за скользящую 1 с.
#
#  v1.1 — ФИКС 5.1 №2 (рантайм, доклад владельца): строка 374 падала
#  «op_Addition» на [System.Object[]]: New-Object Size с арифметикой и
#  запятой в ОДНИХ скобках — запятая в PS связывает крепче '+', «(a)+24,
#  (b)+70» = «(a) + @(24,(b))» = int + массив. Оба места (ClientSize,
#  lbl.Size) переведены на [System.Drawing.Size]::new(): в вызове метода
#  запятая = разделитель аргументов.
#
#  v1.2 — ФИКС 5.1 №3 (рывки, доклад владельца): первые 3 с (75 полных
#  кадров TYPE 01, добивки нет) шар шёл ровно, на дельтах TYPE 02 дёргался:
#  FFh-добивка (1798 Б на кадр) пропускалась RemoveAt(0) ПО ОДНОМУ байту
#  (~45 000 вызовов/с) — GUI-поток на 5.1 голодал, декод шёл пачками.
#  Фикс: серия FFh срезается ОДНИМ RemoveRange (семантика прежняя);
#  поточечные копии payload/FB заменены на .NET-батчи; в самотест добавлен
#  INFO-замер времени декода.
#
#  v1.3 — ФИКС-4 (каденс отрисовки, доклад владельца «всё так же»): после
#  v1.2 рывки на дельтах остались (граница ~кадр 75-80 та же). Провод целый:
#  по цифрам владельца (кадры 1504, SEQ 171, пропуски SEQ 1) после сброса
#  потерянных кадров НЕТ — единственный «пропуск» это сам сброс (SEQ прыгнул
#  на 0), дальше поток непрерывен. Остался каденс ПАНЕЛИ: WM_TIMER таймера
#  WinForms ~15,6 мс, кадр 40 мс завершается на 2-м или 3-м тике — попере-
#  менные интервалы декода/рисования 31/47 мс; на дельтах декод и перерисовка
#  дешёвые (v1.2) и ничто больше не выравнивает такт (на полных кадрах до-
#  рогая перерисовка 100 строк случайно работала метрономом — потому начало
#  было «плавным»). Фикс: рисовать не чаще раза в 36 мс (Stopwatch-гейт),
#  всегда самый свежий FB (просроченные отбрасываются — по SPEC); гейт +
#  сетка таймера дают равномерные ~40-47 мс (~21-25 FPS) вместо дёрганья
#  31/47. Плюс инструментация в статусе: инт ср/макс мс между декодами
#  (Stopwatch, монотонный), буф макс (BytesToRead); -Log <файл> пишет CSV
#  по кадру (utc,seq,type,dt_ms,buf) — по логу видно, ровный ли эфир.
#
#  v1.4 — ФИКС-5 (дорогая краска полного кадра, доклад владельца с логом
#  gfx_log.csv, 419 кадров): самотест 12/12; ПОТОК ЦЕЛ (2 разрыва SEQ =
#  два сброса владельца, dt 866/952 мс); ВСЕ фазы дают ср. 25,1-25,4 FPS —
#  плата/провод подтверждены ЖЕЛЕЗОМ. Но в полных фазах (TYPE 01 после
#  сброса) декод шёл ПАЧКАМИ: 5 и 9 пар с dt 0-5 мс (2 кадра за один тик)
#  с паузами 60-82 мс, при том что в дельтах пары единичны. Единственная
#  разница фаз на ПК — краска: полный кадр = 100 строк = 16 000 интерпре-
#  тируемых итераций (~30-70 мс на 5.1) ВНУТРИ обработчика тика, т.е. В
#  ПОТОКЕ ЧТЕНИЯ ПОРТА: на время краски порт копится, следующий тик вычиты-
#  вает 2 кадра разом — «быстрый шар» после сброса (прыжки по 2 клетки).
#  Фикс: краска = LUT байт -> 32 Б BGRA + [Array]::Copy на каждый байт FB
#  (2000 memcpy на полный кадр вместо 16 000 итераций, ~10-20x дешевле),
#  один LockBits + Marshal.Copy на кадр. После фикса все фазы декодируются
#  ровно (31/47 мс), гейт красит равномерно ~40-47 мс — «быстрый режим»
#  после сброса исчезает: шар идёт ЧЕСТНЫЕ равномерные 25 FPS везде.
#  (Реальное ускорение шара — только правкой прошивки: шаг 2 клетки/кадр;
#  канал загружен на 50%, запас есть.)
#
#  v1.5 — ДИАГНОСТИКА + ФИКС СКОЛЬЗЯЩЕЙ ФАЗЫ (доклад владельца «мячик не
#  плавно и скачет» на v2.1, лог gfx_log.csv: 2606 кадров / 120,5 с).
#  Форензика лога: провод ЦЕЛ (0 разрывов SEQ, потерь нет), НО реальный
#  период платы 46,348 мс вместо 46,875 (-1,124%) — фаза кадра СКОЛЬЗИТ
#  по сетке WM_TIMER 15,6 мс: dt размазан 31/47/62 мс, гейт 36 мс режет
#  краску структурно (модель: 3,37% кадров = шар прыгает на 2 шага раз в
#  ~1,4 с) плюс стартовый бэклог 10461 Б (5 кадров прокрасились teleport-ом).
#  УРОК 14: краска не должна жить на сетке WM_TIMER — при скользящей фазе
#  провода гейт рано или поздно отрезает кадр всегда; каденс краски =
#  каденс ПРОВОДА. Фиксы:
#   1) таймер 15 -> 2 мс + timeBeginPeriod(1) (winmm): тик реально ~2 мс;
#      гейт 36 мс УДАЛЁН — краска СРАЗУ в тике декода: интервал краски =
#      интервал провода ± 2 мс, ни одна позиция не теряется (кроме 2+
#      кадров в одном тике — считаются как «пропуск»);
#   2) бэклог > 3000 Б (старт окна, батчинг CH340) сбрасывается целиком
#      (DiscardInBuffer + ресинк парсера, событие «флеш» в CSV) — вместо
#      прокрутки устаревших кадров скачком экран ждёт свежий кадр;
#   3) CSV v1.5: колонка kind: D=декод (seq,type,dt_ms,buf), P=краска
#      (seq=покрашенный, type=0, dt_ms=интервал краски, buf=пропуски этой
#      краски), F=флеш (buf=сброшено Б). Старые логи совместимы — анализатор
#      различает по шапке;
#   4) статус: краска ср/макс мс, пропуски, флеш; сводка при закрытии окна.
#   (Калибровка периода платы до ровных 46,875 мс = 3 тика — в ROM v2.2:
#   W_V2 2194->2262 +3 NOP = +1644T; вьюеру это не требуется — он более
#   не зависит от совпадения фаз.)
#
#  РЕЖИМЫ:
#   .\gfx_view.ps1 -Port COM13              # окно
#   .\gfx_view.ps1 -Port COM13 -Scale 4     # крупнее
#   .\gfx_view.ps1 -Port COM13 -Log gfx_log.csv   # + CSV-лог по кадрам
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
    [string]$Log = '',
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
# --- v1.3: инструментация каденса + CSV-лог ---
$script:GfxSw        = $null   # Stopwatch межкадровых интервалов (монотонный)
$script:GfxIvPrev    = 0.0     # отметка прошлого декода по Stopwatch
$script:GfxIvSum     = 0.0     # сумма интервалов в окне статистики (250 мс)
$script:GfxIvMax     = 0.0     # макс интервал в окне
$script:GfxIvN       = 0       # декодов в окне
$script:GfxBufLast   = -1      # BytesToRead на тике последнего декода
$script:GfxBufMax    = 0       # макс буфер за окно
$script:GfxLogPath   = ''
$script:GfxLogLines  = $null   # List[string]: буфер CSV, слив каждые 250 мс
# --- v1.5: краска без гейта + пропуски + флеш бэклога ---
$script:GfxPaintSw    = $null   # Stopwatch интервала краски (создаётся в GUI-ветке)
$script:GfxPaintSum   = 0.0     # окно 250 мс: сумма интервалов краски
$script:GfxPaintN     = 0       # окно 250 мс: красок
$script:GfxPaintMax   = 0.0     # окно 250 мс: макс интервал краски
$script:GfxPaintTotal = 0       # красок за сеанс
$script:GfxSincePaint = 0       # кадров декодировано с последней краски
$script:GfxSkipN      = 0       # позиций, не попавших на экран (>1 декода на краску)
$script:GfxFlushN     = 0       # сбросов бэклога > 3000 Б

# --- предрасчёт: байт -> 32 Б BGRA (8 пикселей x 4 Б, MSB = левый пиксель).
# v1.4: краска кадра = 2000 memcpy по 32 Б ([Array]::Copy) вместо 16 000
# интерпретируемых итераций — полная перерисовка ~10-20x дешевле и не
# блокирует чтение порта (причина парного декода в полных фазах, см. шапку).
$script:GfxByteBgra = New-Object 'object[]' 256
for ($v = 0; $v -lt 256; $v++) {
    $a = New-Object 'byte[]' 32
    for ($b = 0; $b -lt 8; $b++) {
        $off = $b * 4
        if (($v -band (1 -shl (7 - $b))) -ne 0) {
            $a[$off] = 230; $a[$off + 1] = 230; $a[$off + 2] = 230   # BGRA: светлая
        } else {
            $a[$off] = 16; $a[$off + 1] = 16; $a[$off + 2] = 16      # BGRA: тёмная
        }
        $a[$off + 3] = 255                                            # альфа
    }
    $script:GfxByteBgra[$v] = $a
}
$script:GfxPixBuf = New-Object 'byte[]' (160 * 100 * 4)   # буфер кадра 64 000 Б

function Reset-GfxParser {
    $script:GfxAcc.Clear()
    $script:GfxFrames = 0; $script:GfxGaps = 0
    $script:GfxResync = 0; $script:GfxResyncB = 0
    $script:GfxLastSeq = -1; $script:GfxLastType = 0
    $script:GfxFillLeft = 0
    $script:GfxIvSum = 0.0; $script:GfxIvMax = 0.0; $script:GfxIvN = 0
    $script:GfxBufMax = 0
}

# Применить один кадр (заголовок уже проверен) к FB.
function Invoke-GfxFrame {
    param([byte[]]$Payload, [byte]$Type, [byte]$Seq)
    if ($Type -eq 1) {
        [Array]::Copy($Payload, $script:GfxFb, 2000)   # УРОК 7: батч вместо поточечного цикла
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
    if ($null -eq $script:GfxBpsT0) {
        $script:GfxBpsT0 = [DateTime]::UtcNow
        $script:GfxSw = [System.Diagnostics.Stopwatch]::StartNew()
        $script:GfxIvPrev = 0.0
    }
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
            # УРОК 7 (рывки у владельца, v1.2): добивку срезать СЕРИЕЙ одним
            # RemoveRange — RemoveAt(0) по байту давал ~45 000 вызовов/с на
            # дельтах, PS 5.1 не тянул (декод пачками = мяч дёргается; TYPE 01
            # без добивки потому и шёл ровно). Семантика 1-в-1: серию FFh в
            # пределах ожидаемой добивки пропускаем (не дальше), первый не-FF —
            # сбой добивки -> FillLeft=0, обычный скан (честный мусор).
            if ($script:GfxAcc[0] -eq 0xFF) {
                $skip = [Math]::Min($script:GfxAcc.Count, $script:GfxFillLeft)
                $i = 1
                while ($i -lt $skip -and $script:GfxAcc[$i] -eq 0xFF) { $i++ }
                $script:GfxAcc.RemoveRange(0, $i)
                $script:GfxFillLeft -= $i
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
        # УРОК 7: пакетная копия одним .NET-вызовом вместо n итераций PS
        $script:GfxAcc.CopyTo(6, $payload, 0, $n)
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
        # v1.3: каденс — интервал между декодами (Stopwatch, монотонный) в
        # окно статистики + строка CSV-лога (если лог включён; в самотесте
        # GfxLogLines = null и BufLast = -1 — ветки не мешают)
        $ivNow = $script:GfxSw.Elapsed.TotalMilliseconds
        $ivDt = $ivNow - $script:GfxIvPrev
        $script:GfxIvPrev = $ivNow
        $script:GfxIvSum += $ivDt; $script:GfxIvN++
        if ($ivDt -gt $script:GfxIvMax) { $script:GfxIvMax = $ivDt }
        if ($null -ne $script:GfxLogLines) {
            $script:GfxLogLines.Add(("{0},D,{1},{2},{3},{4}" -f `
                [DateTime]::Now.ToString('HH:mm:ss.fff'), $seq, $type, `
                [int][Math]::Round($ivDt), $script:GfxBufLast))
        }
        $script:GfxSincePaint++   # v1.5: кадр ждёт краски (пропуск = >1 на краску)
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
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    for ($off = 0; $off -lt $s.Length; $off += 4096) {
        $len = [Math]::Min(4096, $s.Length - $off)
        $chunk = New-Object 'byte[]' $len
        [Array]::Copy($s, $off, $chunk, 0, $len)
        Invoke-GfxChunk -Chunk $chunk
    }
    $sw.Stop()
    # INFO (не Req): чтобы поспевать за живым эфиром (2006 Б x 25 = 50 150 Б/с),
    # декод этого потока (130 конвертов x 2006 Б) должен уложиться в бюджет ниже.
    $budgetMs = [int]($s.Length / 50150.0 * 1000)
    Write-Host ("  INFO декод {0} Б за {1} мс (бюджет {2} мс = темп живого 25 FPS)" -f $s.Length, $sw.ElapsedMilliseconds, $budgetMs)
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

# --- v1.5: разрешение системного таймера ~1 мс — тик 2 мс реально ~2 мс
# (без этого WM_TIMER живёт на сетке ~15,6 мс и краска квантуется 31/47/62)
Add-Type -Namespace GfxNative -Name WinMM -MemberDefinition '[DllImport("winmm.dll")] public static extern uint timeBeginPeriod(uint ms); [DllImport("winmm.dll")] public static extern uint timeEndPeriod(uint ms);' | Out-Null
[void][GfxNative.WinMM]::timeBeginPeriod(1)

# --- v1.5: инструментация краски (гейта 36 мс больше НЕТ) ---
$script:GfxPaintSw = [System.Diagnostics.Stopwatch]::StartNew()
$script:GfxBufLast = -1
$script:GfxBufMax  = 0
$script:GfxLogPath = $Log
if ($Log -ne '') {
    try {
        [System.IO.File]::WriteAllText($Log, "utc,kind,seq,type,dt_ms,buf`r`n", [System.Text.Encoding]::UTF8)
        $script:GfxLogLines = New-Object System.Collections.Generic.List[string]
        Write-Host "Лог кадров: $Log"
    } catch {
        Write-Host "Лог недоступен ($Log): $($_.Exception.Message) — работаю без лога"
        $script:GfxLogLines = $null
    }
}

# --- рендер-примитивы ---
$bmpS = New-Object System.Drawing.Bitmap 160, 100
$rectS = New-Object System.Drawing.Rectangle 0, 0, 160, 100
$bmpB = New-Object System.Drawing.Bitmap (160 * $Scale), (100 * $Scale)

function Update-GfxBitmap {
    # v1.4: только ГРЯЗНЫЕ строки перекрашиваются в GfxPixBuf одним memcpy
    # на байт FB (32 Б BGRA из LUT); LockBits + Marshal.Copy + масштаб — как
    # раньше. На дельте это 9 копий, на полном кадре 2000 (было 16 000
    # интерпретируемых итераций — блокировало чтение порта, см. шапку v1.4).
    for ($r = 0; $r -lt 100; $r++) {
        if (-not $script:GfxDirty.ContainsKey($r)) { continue }
        $base = $r * 20; $dst = $r * 640   # 160 px x 4 Б = 640 Б/строку
        for ($j = 0; $j -lt 20; $j++) {
            [Array]::Copy($script:GfxByteBgra[$script:GfxFb[$base + $j]], 0, $script:GfxPixBuf, $dst, 32)
            $dst += 32
        }
    }
    $script:GfxDirty.Clear()
    $bd = $bmpS.LockBits($rectS, [System.Drawing.Imaging.ImageLockMode]::WriteOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    [System.Runtime.InteropServices.Marshal]::Copy($script:GfxPixBuf, 0, $bd.Scan0, $script:GfxPixBuf.Length)
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
$form.Text = "GFXSTREAM v2.2 - $Port $Baud 8N1 (160x100 x$Scale)"
# УРОК PS 5.1: запятая крепче '+' — «Size ((a)+24, (b)+70)» группируется как
# «(a) + @(24,(b))» → op_Addition на Object[] (доклад владельца 11-11).
# ::new() — вызов метода: запятая там = разделитель аргументов, '+' безопасен.
$form.ClientSize = [System.Drawing.Size]::new((160 * $Scale) + 24, (100 * $Scale) + 70)
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
$lbl.Size = [System.Drawing.Size]::new((160 * $Scale) + 4, 34)   # тот же фикс, что и ClientSize
$lbl.ForeColor = [System.Drawing.Color]::FromArgb(200, 210, 200)
$lbl.Font = New-Object System.Drawing.Font 'Consolas', 9
$lbl.Text = 'инициализация...'
$form.Controls.Add($lbl)

$script:statT0 = [DateTime]::UtcNow
$script:fpsShown = 0.0
$script:framesShown = 0
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 2
$timer.Add_Tick({
    try {
        $avail = $sp.BytesToRead
        $script:GfxBufLast = $avail
        # v1.5: бэклог > 3000 Б = вьюер отстал больше чем на конверт с запасом
        # (старт окна, батчинг CH340): сброс — устаревшие кадры всё равно
        # прокрасились бы скачком; экран просто ждёт свежий кадр.
        if ($avail -gt 3000) {
            if ($null -ne $script:GfxLogLines) {
                $script:GfxLogLines.Add(("{0},F,-1,-1,0,{1}" -f `
                    [DateTime]::Now.ToString('HH:mm:ss.fff'), $avail))
            }
            try { $sp.DiscardInBuffer() } catch { }
            $script:GfxAcc.Clear()
            $script:GfxFillLeft = 0
            $script:GfxLastSeq = -1
            $script:GfxFlushN++
            return
        }
        if ($avail -gt $script:GfxBufMax) { $script:GfxBufMax = $avail }
        if ($avail -gt 0) {
            $chunk = New-Object 'byte[]' $avail
            try { $n = $sp.BaseStream.Read($chunk, 0, $avail) } catch { $n = 0 }
            if ($n -gt 0) {
                if ($n -lt $chunk.Length) { $chunk = $chunk[0..($n - 1)] }
                Invoke-GfxChunk -Chunk $chunk
            }
        }
        # v1.5: краска БЕЗ гейта (УРОК 14: гейт на сетке WM_TIMER при сколь-
        # зящей фазе провода режет кадры структурно — 3,37% по логу 11-12);
        # краска дёшева с v1.4 — рисуем каждый тик с грязным FB: каденс
        # краски = каденс провода ± 2 мс.
        if ($script:GfxDirty.Count -gt 0) {
            $pd = $script:GfxPaintSw.Elapsed.TotalMilliseconds
            $script:GfxPaintSw.Restart()
            if ($script:GfxPaintTotal -gt 0) {
                $script:GfxPaintSum += $pd; $script:GfxPaintN++
                if ($pd -gt $script:GfxPaintMax) { $script:GfxPaintMax = $pd }
            }
            $skipped = 0
            if ($script:GfxSincePaint -gt 1) {
                $skipped = $script:GfxSincePaint - 1
                $script:GfxSkipN += $skipped
            }
            Update-GfxBitmap; $pbox.Image = $bmpB
            $script:GfxPaintTotal++
            if ($null -ne $script:GfxLogLines) {
                $script:GfxLogLines.Add(("{0},P,{1},0,{2},{3}" -f `
                    [DateTime]::Now.ToString('HH:mm:ss.fff'), $script:GfxLastSeq, `
                    [int][Math]::Round($pd), $skipped))
            }
            $script:GfxSincePaint = 0
        }
        $now = [DateTime]::UtcNow
        if (($now - $script:statT0).TotalMilliseconds -ge 250) {
            $dt = ($now - $script:statT0).TotalSeconds
            $script:fpsShown = [Math]::Round(($script:GfxFrames - $script:framesShown) / $dt, 1)
            $script:framesShown = $script:GfxFrames
            $script:statT0 = $now
            $pdAvg = 0.0; $pdMax = 0.0
            if ($script:GfxPaintN -gt 0) {
                $pdAvg = [Math]::Round($script:GfxPaintSum / $script:GfxPaintN, 0)
                $pdMax = [Math]::Round($script:GfxPaintMax, 0)
            }
            $lbl.Text = "FPS {0,5:N1}  SEQ {1,3}  кадры {2}  краски {3}`nкраска {4}/{5} мс  пропуск {6}  флеш {7}  разрыв {8}  буф {9} Б  {10} Б/с" -f `
                $script:fpsShown, $script:GfxLastSeq, $script:GfxFrames, $script:GfxPaintTotal, `
                $pdAvg, $pdMax, $script:GfxSkipN, $script:GfxFlushN, $script:GfxGaps, $script:GfxBufMax, $script:GfxBps
            # v1.3: слив CSV-лога (файл открыт/закрыт на каждый слив — краш-
            # безопасно: в файле всегда хвост ≤250 мс) + сброс окна
            if ($null -ne $script:GfxLogLines -and $script:GfxLogLines.Count -gt 0) {
                try { [System.IO.File]::AppendAllLines($script:GfxLogPath, $script:GfxLogLines) } catch { }
                $script:GfxLogLines.Clear()
            }
            $script:GfxIvSum = 0.0; $script:GfxIvMax = 0.0; $script:GfxIvN = 0
            $script:GfxBufMax = 0
            $script:GfxPaintSum = 0.0; $script:GfxPaintN = 0; $script:GfxPaintMax = 0.0
        }
    } catch { $lbl.Text = "ошибка: $($_.Exception.Message)" }
})
$form.Add_Shown({ $timer.Start() })
$form.Add_FormClosed({
    $timer.Stop(); $sp.Close()
    if ($null -ne $script:GfxLogLines -and $script:GfxLogLines.Count -gt 0) {
        try { [System.IO.File]::AppendAllLines($script:GfxLogPath, $script:GfxLogLines) } catch { }
    }
    [void][GfxNative.WinMM]::timeEndPeriod(1)
    Write-Host ("СВОДКА v1.5: кадров {0}, красок {1}, пропусков {2}, флешей {3}, разрывов SEQ {4}, ресинк {5} Б" -f `
        $script:GfxFrames, $script:GfxPaintTotal, $script:GfxSkipN, $script:GfxFlushN, $script:GfxGaps, $script:GfxResyncB)
})
[void]$form.ShowDialog()
