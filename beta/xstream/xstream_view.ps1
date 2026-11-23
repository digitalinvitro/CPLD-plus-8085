#!/usr/bin/env pwsh
# ======================================================================
# XSTREAM_VIEW.PS1 v1.3.1 -- клиент XSTREAM: приём потока 80x25 из платы
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
#
# v1.2.1 (третий железный отчёт владельца 11-13):
#   4. FormatError «Индекс ... меньше размера списка аргументов» в
#      Write-Log при -Log: "-f <список>" стоял прямо в скобках
#      метод-вызова - PowerShell делит аргументы метода по запятым
#      верхнего уровня, "-f" получал 1 аргумент при 7 подстановках
#      {0}..{6}. Формат собирается в переменную, затем WriteLine($line).
#   5. SelfTest: счётчик 5/5 -> 6/6 (кейс 2b добавили в v1.2, счётчик
#      не обновили); OK payload больше не печатается после FAIL.
#
# v1.2.2 (четвёртый железный отчёт владельца 11-13: живой сеанс 118 с,
# 2412 кадров, лог xlog.csv):
#   6. ФАНТОМНАЯ 8-Я КОЛОНКА В CSV (урок 12): шапка объявляет 7 колонок,
#      а строки несут 8 полей - {3:F1} в Write-Log форматируется оператором
#      -f, который берёт КУЛЬТУРУ ПОТОКА: на ru-RU Windows F1 даёт "17,1"
#      (десятичная ЗАПЯТАЯ), и в запятой-CSV поле расщепляется на "17" и
#      "1". Все 2516 строк живого лога имеют 8 полей, 5-е всегда одна цифра
#      0-9. Лечение: dt и штамп времени форматируются ЯВНО через
#      InvariantCulture и собираются конкатенацией (никакого -f вовсе).
#   7. РЕСТАРТ ПОТОКА ПЛАТЫ - НЕ ГЭП: в живом логе 110 из 113 "гэпов" дал
#      один эпизод (пауза 462 мс, SEQ 145 -> 0) - плата перезапустила поток
#      (счётчик SEQ обнулился), кадры при этом не терялись. Правило: dt >
#      250 мс (~5 периодов) И скачок SEQ -> счётчик Restarts + строка "R"
#      в CSV, SeqGaps не растёт. Оставшиеся 3 гэпа живого лога - честные
#      пропуски по 1 кадру (dt 86-99 мс - плата промедлила один период).
#   8. Косметика: в статусе "ресинк {N} Б" -> "ресинков {N}" (Resyncs -
#      счётчик, не байты); статус и «Итог» показывают рестарты; SelfTest
#      6/6 -> 7/7 (кейс 3b: пауза 1 с + скачок SEQ = рестарт, не гэп).
#
# v1.3.0 (загрузка Intel HEX без выхода из клиента; пара fw v2.0.6):
#   9. КНОПКА/ХОТКЕЙ "Загрузить HEX (L)": выбор .hex -> валидация ВСЕХ
#      записей ДО переключения порта (контрольные суммы, счётчик длины) ->
#      диалог "нажмите B на плате" -> порт ЗАКРЫВАЕТСЯ и открывается
#      заново 4800 8N2 (верифицированные настройки отчёта об отладке
#      загрузчика; пейсинг 2 мс/символ + 10 мс/строка, параметры
#      -LoadCharDelayMs/-LoadLineDelayMs) -> построчная передача с
#      прогрессом в строке статуса и DoEvents (окно живое) -> пауза 0,8 с
#      -> порт обратно 1000000 8N1 -> таймер приёма возобновляется,
#      ресинк по A5 5A. Плата показывает прогресс сама (v2.0.6: счётчик
#      записей на индикаторе), при ошибке - EEEE + SOS до Enter.
#   10. Test-HexRecord: чистая функция валидации записи Intel HEX
#      (контрольная сумма mod 256, соответствие счётчика длины) -
#      покрыта SelfTest-кейсом 8 (валидная/битая/EOF/мусор), 7/7 -> 8/8.
#
# v1.3.1 (первый железный запуск v1.3.0: при кнопке окно "Ошибка
#   передачи: Значение PortName не может быть пустым"):
#   11. УРОК 13 (в продолжение урока 3 про скоуп): имена переменных PS
#      НЕЧУВСТВИТЕЛЬНЫ К РЕГИСТРУ. Локальная "$port = $null" в
#      Invoke-HexLoad - это ТО ЖЕ ИМЯ, что параметр скрипта "$Port":
#      присваивание затирало его в локальном скоупе функции, .ctor
#      SerialPort получал PortName=$null (у Open-Port такого локала
#      нет - поэтому основной поток экрана работал). Локал переименован
#      в $portLoad; параметр читается как $Port.
# ======================================================================
param(
    [string]$Port = "",
    [int]$Baud = 1000000,
    [string]$Log = "",
    [switch]$SelfTest,
    [double]$FontSize = 13,
    [int]$LoadCharDelayMs = 2,     # v1.3: пауза между СИМВОЛАМИ при загрузке hex
    [int]$LoadLineDelayMs = 10     # v1.3: пауза между СТРОКАМИ hex (верифицировано отчётом)
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
        # v1.2.1 / урок 11: "-f <список>" НЕЛЬЗЯ ставить прямо в скобках
        # метод-вызова: PowerShell делит аргументы метода по запятым
        # верхнего уровня, поэтому WriteLine("fmt" -f a,b,c) парсится как
        # WriteLine(("fmt" -f a), b, c) - "-f" получает 1 аргумент при 7
        # подстановках -> FormatException «Индекс ... меньше размера
        # списка аргументов» (всплывало только с -Log: без лога Write-Log
        # не вызывался). Форматируем в переменную, затем WriteLine($line).
        # v1.2.2 / урок 12: -f и ToString() берут КУЛЬТУРУ ПОТОКА: на ru-RU
        # Windows {3:F1} даёт "17,1" (десятичная запятая), и в запятой-CSV
        # поле расщепляется на "17" и "1" - в живом логе владельца 11-13
        # все 2516 строк имели фантомную 8-ю колонку при шапке в 7.
        # Поэтому dt и штамп времени - ЯВНО через InvariantCulture, строка
        # собирается конкатенацией: ни -f, ни культурных сюрпризов.
        $inv = [System.Globalization.CultureInfo]::InvariantCulture
        $ts = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fff", $inv)
        $line = $ts + "," + $kind + "," + $seq + "," + $dt.ToString("F1", $inv) + "," + $total + "," + $rs + "," + $gaps
        $script:LogSw.WriteLine($line)
    }
}

# ---------------------------------------------------------------- Intel HEX
# Test-HexRecord (v1.3): валидация ОДНОЙ записи Intel HEX.
# ":nnaaaatt[dd...]cc" - сумма ВСЕХ байт записи (nn+aa+aa+tt+dd..+cc)
# mod 256 == 0; длина = nn + 5. Возвращает hashtable:
#   Ok ($true/$false), Data (байт данных, 0 для EOF/пустой),
#   Empty (пустая строка - пропускаем), Err (текст причины).
# Чистая функция - покрыта SelfTest-кейсом 8.
function Test-HexRecord([string]$line) {
    $t = $line.Trim()
    if ($t -eq "") { return @{ Ok = $true; Data = 0; Empty = $true; Err = "" } }
    if (-not $t.StartsWith(":")) { return @{ Ok = $false; Data = 0; Empty = $false; Err = "нет ':'" } }
    $hex = $t.Substring(1)
    if (($hex.Length -lt 10) -or (($hex.Length % 2) -ne 0)) {
        return @{ Ok = $false; Data = 0; Empty = $false; Err = "длина поля" }
    }
    $bytes = [byte[]]::new([int]($hex.Length / 2))
    for ($i = 0; $i -lt $bytes.Length; $i++) {
        $b = 0
        $s2 = $hex.Substring(2 * $i, 2)
        if (-not [int]::TryParse($s2, [System.Globalization.NumberStyles]::HexNumber,
                                 [System.Globalization.CultureInfo]::InvariantCulture, [ref]$b)) {
            return @{ Ok = $false; Data = 0; Empty = $false; Err = "не hex '$s2'" }
        }
        $bytes[$i] = [byte]$b
    }
    $s = 0
    foreach ($b in $bytes) { $s = ($s + $b) -band 0xFF }
    if ($s -ne 0) { return @{ Ok = $false; Data = 0; Empty = $false; Err = "сумма {0:X2}h" -f $s } }
    $cnt = $bytes[0]
    if ($bytes.Length -ne ($cnt + 5)) {
        return @{ Ok = $false; Data = 0; Empty = $false; Err = "cnt=$cnt, полей $($bytes.Length - 5)" }
    }
    return @{ Ok = $true; Data = $cnt; Empty = $false; Err = "" }
}

# ---------------------------------------------------------------- парсер
# Состояние: 0=ищем A5, 1=ждём 5A+SEQ, 2=набираем payload.
# Зеркало парсера проверено симом (parse_frames в sim_xstream_v1.py).
function New-Parser {
    $p = [hashtable]::Synchronized(@{
        State = 0; Buf = [System.Collections.Generic.List[byte]]::new()
        Screen = [byte[]]::new($Screen); Seq = -1
        Frames = 0; Resyncs = 0; SeqGaps = 0; Restarts = 0; LastSeq = -1
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
                    if ($d -ne 1) {
                        # v1.2.2: пауза > 250 мс (~5 периодов) + скачок SEQ -
                        # плата ПЕРЕЗАПУСТИЛА поток (счётчик обнулился; живой
                        # лог 11-13: пауза 462 мс, SEQ 145 -> 0 = 110 ложных
                        # "гэпов"). Это рестарт, а не потеря кадров.
                        if ($p.DtMs -gt 250.0) { $p.Restarts++ }
                        else { $p.SeqGaps += ($d - 1 + 256) -band 0xFF }
                    }
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
    $bad = $false
    for ($k = 0; $k -lt $Screen; $k++) {
        if ($p.Screen[$k] -ne $ref[$k]) { Write-Host ("  FAIL: payload байт {0}: {1:X2} != {2:X2}" -f $k, $p.Screen[$k], $ref[$k]); $fail++; $bad = $true; break }
    }
    if (-not $bad) { Write-Host "  OK: побайтовая сверка payload кадра 129 (сшивка кусочков чтения)" }

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

    # 3b) рестарт потока: пауза > 250 мс + скачок SEQ = рестарт, НЕ гэп
    #     (живой лог владельца 11-13: пауза 462 мс, SEQ 145 -> 0 давал
    #     +110 ложных "гэпов" - плата просто перезапустила счётчик)
    $p = New-Parser
    $script:FrameReady = $false
    $frame[2] = 5;  Add-Bytes $p $frame $FrameLen
    $p.LastFrameTicks = [DateTime]::Now.Ticks - 10000000    # 1 с назад -> dt ~ 1000 мс
    $frame[2] = 200; Add-Bytes $p $frame $FrameLen
    if ($p.SeqGaps -ne 0 -or $p.Restarts -ne 1) { Write-Host "  FAIL: рестарт потока (gaps=$($p.SeqGaps), рестартов=$($p.Restarts))"; $fail++ }
    else { Write-Host "  OK: пауза 1 с + скачок SEQ 5 -> 200 -> рестарт=1, гэпов 0" }

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

    # 5) Test-HexRecord (v1.3): валидатор записей Intel HEX для загрузчика
    # строим валидную запись данных: cnt=4, addr=8000, typ=00, dd=C3 C8 07 00
    $payload = @(0x04, 0x80, 0x00, 0x00, 0xC3, 0xC8, 0x07, 0x00)
    $cc = (0x100 - (($payload | ForEach-Object { $_ } | Measure-Object -Sum).Sum % 256)) % 256
    $rec = ":" + (($payload + $cc | ForEach-Object { "{0:X2}" -f $_ }) -join "")
    $r = Test-HexRecord $rec
    if (-not $r.Ok -or $r.Data -ne 4) { Write-Host "  FAIL: валидатор '$rec' -> Ok=$($r.Ok) Data=$($r.Data) Err=$($r.Err)"; $fail++ }
    else { Write-Host "  OK: валидатор: '$rec' -> Ok, данных 4 Б" }
    # битая сумма: последняя цифра cc+1
    $bad = $rec.Substring(0, $rec.Length - 2) + ("{0:X2}" -f (($cc + 1) -band 0xFF))
    $r = Test-HexRecord $bad
    if ($r.Ok) { Write-Host "  FAIL: битая сумма не поймана: '$bad'"; $fail++ }
    else { Write-Host "  OK: валидатор: битая контрольная сумма поймана ($($r.Err))" }
    $r = Test-HexRecord ":00000001FF"                       # штатный EOF
    if (-not $r.Ok -or $r.Data -ne 0) { Write-Host "  FAIL: EOF-запись не валидна"; $fail++ }
    else { Write-Host "  OK: валидатор: ':00000001FF' (EOF) -> Ok, данных 0" }
    $r = Test-HexRecord "не hex вообще"
    if ($r.Ok) { Write-Host "  FAIL: мусор принят за запись"; $fail++ }
    else { Write-Host "  OK: валидатор: мусор отклонён ($($r.Err))" }

    if ($fail -eq 0) { Write-Host "SELFTEST: 8/8 ПРОЙДЕНЫ" }
    else { Write-Host "SELFTEST: ПРОВАЛОВ $fail"; exit 1 }
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
$script:LastRestarts = 0               # v1.2.2: сколько рестартов уже отражено в CSV (строки "R")
$script:LoadBusy = $false              # v1.3: активна ли передача hex (защита от реэнтранта)

$form = [System.Windows.Forms.Form]::new()
$form.Text = "XSTREAM v1.3.1 - 80x25 ($Port @ $Baud 8N1) | HEX LOAD (L)"
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
# v1.3: кнопка загрузки hex (Dock=Top добавляется ПОСЛЕ status: док-разметка
# идёт в обратном порядке коллекции Controls - status/Bottom, кнопка/Top,
# panel/Fill достаётся остаток; BringToFront панели ниже сохраняет это)
$btnLoad = [System.Windows.Forms.Button]::new()
$btnLoad.Text = "Загрузить HEX на плату (L)"
$btnLoad.Dock = "Top"
$btnLoad.Height = 32
$btnLoad.Font = [System.Drawing.Font]::new("Consolas", 10)
$btnLoad.FlatStyle = "Flat"
$btnLoad.BackColor = [System.Drawing.Color]::FromArgb(24, 34, 24)
$btnLoad.ForeColor = [System.Drawing.Color]::FromArgb(190, 255, 190)
$form.Controls.Add($btnLoad)
# хоткей L: KeyPreview - форма получает нажатия раньше контролов
$form.KeyPreview = $true
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

# ------------------------------------------------------- загрузка Intel HEX
# Invoke-HexLoad (v1.3): выбор файла -> валидация -> порт 4800 8N2 ->
# передача с пейсингом -> порт обратно 1000000 8N1. Работает на UI-потоке:
# таймер приёма остановлен, окно живёт через DoEvents. Плата: B (LOADM)
# до отправки; прогресс - счётчик записей на индикаторе (fw v2.0.6),
# ошибка - EEEE + SOS до Enter на плате.
function Invoke-HexLoad {
    if ($script:LoadBusy) { return }               # защита от повторного пуска
    if ($null -eq $script:PortObj) { return }
    $dlg = [System.Windows.Forms.OpenFileDialog]::new()
    $dlg.Filter = "Intel HEX (*.hex)|*.hex|Все файлы|*.*"
    $dlg.Title = "Файл для LOADM (4800 8N2 -> SID платы)"
    if ($dlg.ShowDialog() -ne "OK") { return }

    # --- валидация ДО переключения порта: битый файл железо не трогает ---
    $lines = [System.IO.File]::ReadAllLines($dlg.FileName)
    $recs = [System.Collections.Generic.List[string]]::new()
    $dataBytes = 0
    foreach ($ln in $lines) {
        $r = Test-HexRecord $ln
        if (-not $r.Ok) {
            [void][System.Windows.Forms.MessageBox]::Show(
                "Файл не является корректным Intel HEX:`n" + $dlg.FileName + "`n`nЗапись: " + $ln + "`nОшибка: " + $r.Err,
                "HEX-валидация", 0, 48)
            return
        }
        if (-not $r.Empty) { $recs.Add($ln.Trim()); $dataBytes += $r.Data }
    }
    if ($recs.Count -eq 0) {
        [void][System.Windows.Forms.MessageBox]::Show("В файле нет записей Intel HEX.", "HEX-валидация", 0, 48)
        return
    }

    $res = [System.Windows.Forms.MessageBox]::Show(
        "Файл: " + [System.IO.Path]::GetFileName($dlg.FileName) + "`nЗаписей: " + $recs.Count + ", байт данных: " + $dataBytes + "`n`n1. Нажмите B на плате (LOADM) - индикатор покажет 'L'.`n2. Затем OK здесь - пойдёт передача 4800 8N2.`n`nИндикатор платы = счётчик принятых записей; успех - возврат в меню,`nошибка - EEEE + звук SOS до нажатия Enter на плате.",
        "Загрузка HEX", 1, 64)
    if ($res -ne "OK") { return }

    $script:LoadBusy = $true
    $script:timer.Stop()
    $btnLoad.Enabled = $false
    $portLoad = $null
    try {
        $script:PortObj.Close()
        # ВАЖНО (урок 13, v1.3.1): локал называется $portLoad, НЕ $port -
        # имена PS НЕЧУВСТВИТЕЛЬНЫ К РЕГИСТРУ, "$port" = параметр скрипта
        # "$Port", и "$port = $null" затирал имя порта: .ctor получал
        # PortName=$null ("Значение PortName не может быть пустым").
        $portLoad = [System.IO.Ports.SerialPort]::new($Port, 4800, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::Two)
        $portLoad.WriteTimeout = 5000
        $portLoad.Open()
        $portLoad.DiscardInBuffer()
        $portLoad.DiscardOutBuffer()

        $k = 0
        foreach ($rec in $recs) {
            $k++
            foreach ($ch in $rec.ToCharArray()) {
                $portLoad.Write([string]$ch)
                if ($LoadCharDelayMs -gt 0) { Start-Sleep -Milliseconds $LoadCharDelayMs }
            }
            if ($LoadLineDelayMs -gt 0) { Start-Sleep -Milliseconds $LoadLineDelayMs }
            $status.Text = "LOAD: запись $k/$($recs.Count) ($dataBytes байт данных) - индикатор платы = счётчик записей"
            [void][System.Windows.Forms.Application]::DoEvents()
        }
        Start-Sleep -Milliseconds 800     # плате: EOF -> тик -> меню -> поток 1M
        $status.Text = "LOAD: отправлено записей $k, байт данных $dataBytes. Успех = меню на плате; EEEE+SOS = нажмите Enter на плате"
    } catch {
        [void][System.Windows.Forms.MessageBox]::Show("Ошибка передачи: " + $_.Exception.Message, "HEX-загрузка", 0, 48)
        $status.Text = "LOAD: ошибка передачи - " + $_.Exception.Message
    } finally {
        try { if ($null -ne $portLoad -and $portLoad.IsOpen) { $portLoad.Close() } } catch { }
        try {
            $script:PortObj = [System.IO.Ports.SerialPort]::new($Port, $Baud, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
            $script:PortObj.ReadBufferSize = 262144
            $script:PortObj.ReadTimeout = 500
            $script:PortObj.Open()
            $script:PortObj.DiscardInBuffer()
        } catch {
            $status.Text = "ПОРТ $Port не открыт повторно: " + $_.Exception.Message
        }
        $btnLoad.Enabled = $true
        $script:LoadBusy = $false
        $script:timer.Start()
    }
}

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
        # v1.2.2: рестарт потока платы - отдельная строка "R" в CSV
        if ($script:Parser.Restarts -gt $script:LastRestarts) {
            $script:LastRestarts = $script:Parser.Restarts
            $p = $script:Parser
            Write-Log -Kind "R" -Seq $p.LastSeq -Dt $p.DtMs -Total $p.BytesTotal -Rs $p.Resyncs -Gaps $p.SeqGaps
        }
        $now = [DateTime]::Now.Ticks
        if (($now - $script:LastRateTicks) -ge 10000000) {
            $script:RxRate = $script:Parser.BytesTotal
            $script:LastRateTicks = $now
            $p = $script:Parser
            $el = [int](($now - $script:StartTicks) / 10000000)
            $period = 0.0
            if ($script:FpsEma -gt 0) { $period = 1000.0 / $script:FpsEma }
            # v1.2.2: + рестарты (рестарт потока не гэп), "ресинк N Б" -> "ресинков N"
            $status.Text = ("FPS {0:F1} | период {1:F1} мс | кадров {2} | SEQ-гэпы {3} | рестарт {4} | ресинков {5} | принято {6:F1} КБ | {7} с" -f `
                $script:FpsEma, $period, $p.Frames, $p.SeqGaps, $p.Restarts, $p.Resyncs, ($p.BytesTotal / 1024.0), $el)
            Write-Log -Kind "S" -Seq $p.LastSeq -Dt 0 -Total $p.BytesTotal -Rs $p.Resyncs -Gaps $p.SeqGaps
        }
    } catch { }
})
$timer.Start()

# v1.3: запуск загрузки - кнопкой или клавишей L (KeyPreview на форме)
$btnLoad.Add_Click({ Invoke-HexLoad })
$form.Add_KeyDown({
    if ($_.KeyCode -eq "L") { Invoke-HexLoad }
})

$form.Add_FormClosed({
    try {
        $timer.Stop()
        if ($null -ne $script:PortObj) { $script:PortObj.Close() }
        $p = $script:Parser
        Write-Log -Kind "FIN" -Seq $p.LastSeq -Dt 0 -Total $p.BytesTotal -Rs $p.Resyncs -Gaps $p.SeqGaps
        if ($null -ne $script:LogSw) { $script:LogSw.Flush(); $script:LogSw.Close() }
        Write-Host ("Итог: кадров {0}, FPS {1:F2}, SEQ-гэпов {2}, рестартов {3}, ресинков {4}, байт {5}" -f `
            $p.Frames, $script:FpsEma, $p.SeqGaps, $p.Restarts, $p.Resyncs, $p.BytesTotal)
    } catch { }
})

[void]$form.ShowDialog()
