; =====================================================================
; beta/xstream -- XSTREAM v1: ПРЕРЫВАНИЯ/ТИК -> ВЕСЬ ЭКРАН В UART
; (патч монитора fw_mon "ACdE", владелец: "8085 прерывая выдает в UART
; весь экран, потом идет работать по своим делам в монитор")
;
; ИДЕЯ РЕЖИМА (ТЗ владельца, 11-12):
;   - экран = ФИКСИРОВАННЫЙ буфер ОЗУ B000h..B7CFh (80x25 = 2000 Б,
;     row-major; любой код байтов, у ПК-клиента трактуется как CP1251);
;   - по тику (прерыванию) ЦП выдаёт ВЕСЬ экран в UART аппаратным TX
;     (CPLD v2.3, 1 000 000 бод 8N1, OUT 04h) и возвращается в монитор;
;   - частота тика = из условия ЦП <= 50% на выдачу, FPS 20-25
;     (расчёт: scripts/xstream_calc.py; посылка 22.9 мс => потолок
;     21.3 FPS при 48.8% ЦП; 22 FPS уже 50.2% -> по ТЗ FPS снижается);
;   - фолбэк 10 FPS = 22.9% ЦП (константы XS_TH/TMR_N).
;
; ДВА ВАРИАНТА ТИКА (ключ TMR_HW, сборка -D TMR_HW=1):
;   TMR_HW=0 (по умолчанию, для ТЕКУЩЕГО образа CPLD txuart v2.3:
;     источника прерываний нет - RST 7.5 заземлён) - ПРОГРАММНЫЙ ТИК:
;     накопитель слотов скана XSPASS, каждые XS_TH слотов (~0.33 мс
;     слот скана монитора) CALL XSEND. Кадр ~47.4 мс = 21.1 FPS,
;     48.2% ЦП. Тик живёт в контексте монитора: во время
;     пользовательской программы (E) поток останавливается.
;   TMR_HW=1 (для будущего фит-а CPLD v24 = txuart + таймер -> RST 7.5,
;     порт 06h = N, тик 51.2 мкс): ВЕКТОР 003Ch уже прошит, ISR
;     ре-армит таймер (T = N x 51.2 мкс), делитель XS_DIVN=3 ->
;     кадр 46.9 мс = 21.3 FPS, 48.8% ЦП. ISR выбивает из монитора:
;     поток идёт и ВО ВРЕМЯ пользовательской программы (пока та не DI).
;     Смета v24: база v3.9.8-clear 94 + TX-ядро 18 - узел -7 = 103/108,
;     остров таймера ~18 МЦ (прескалер 8 + счётчик 8 + строб 1 + P75 1)
;     => 121/108 - НЕ ЛОЖИТСЯ в XC95108 (документировано в README).
;
; ФОРМАТ ПРОВОДА (2003 Б/кадр):
;   A5 5A [SEQ] + 2000 Б экрана. SEQ++ mod 256 в каждом кадре.
;   Ресинк клиента по A5 5A; хвост кадра = ровно 2000 Б, без добивки.
;
; ПОСЫЛКА (сим xstream_calc + sim_xstream_v1):
;   РАВНОМЕРНЫЙ пейсинг 35T/Б (УРОК SPRINT: пачки развёртки 23T ->
;   отбросы: TX принимает 1 Б за 31.25T, запись в busy ОТБРАСЫВАЕТСЯ;
;   мин. цикл из ОЗУ MOV+OUT+INX = 23T + 3 NOP = 35T >= 31.25T - ноль
;   отбросов; прецедент p04: равномерные 32T железно);
;   слот дисплея XDIG (~147T с CALL) каждые 200 Б: регенерация 7-сегмент-
;   ника не замирает (цикл разряда ~4.8 мс, ~207 Гц - без мерцания; тон
;   бипа идёт через SND в XDIG);
;   итого ~37.7T/Б => посылка ~24.2 мс; провод (чистый эфир) 20.03 мс.
;
; ПАМЯТЬ (MEMORY_MAP.md): ROM 0000-7FFF (вектор RST 7.5 = 003Ch прошит
;   JMP XISR, код после таблиц смещён на ORG 0040h), RAM 8000-FFFF.
;   Монитор: переменные FFE8-FFF9, стек с FFE7 вниз. XSTREAM:
;   XBUF B000-B7CF (пользовательская область), XSSEQ/XSPASS/XSDIV =
;   FFFA-FFFC (свободно выше PREVST FFF9, стек до них не доходит).
;
; ПОРТЫ: 00h сегменты, 01h разряды+SND, 02h колонки, 03h ряды (монитор);
;   04h TXDATA, 05h TXRDY (не используется), 06h - в v24 загрузка N
;   (на v2.3 записи игнорируются - безопасно в обоих образах CPLD).
;
; СОБРАКА (asm85.py из beta/lowsize/rom; регрессия: fw_mon.hex md5
;   f9ad5c6deb3bf0618018fd630b1d25aa воспроизводится байт-в-байт):
;   python3 asm85.py xstream_v1.asm -o xstream_v1.hex -l xstream_v1.lst
;   HW-вариант:  ... -D TMR_HW=1 -o xstream_v1_hw.hex
;   (исходник-канон CP1251 = xstream_v1.asm; близнец UTF-8 = xstream_v1_utf8.asm)
;
; СИМ: beta/xstream/scripts/sim_xstream_v1.py - исполнение РЕАЛЬНОГО hex,
;   период кадра, 0 отбросов, побайтовая сверка экрана, нажатие клавиши.
; =====================================================================

; ---- константы монитора (fw_mon, без изменений; переопределяются -D) ----
FAST    EQU 0               ; 1 = укороченные паузы (для симуляции)
IF FAST
TICK_MS EQU 4               ; тик клавиши, единиц ~1 мс (быстро)
SET_MS  EQU 2               ; дебаунс после отпускания
ELSE
TICK_MS EQU 30              ; 30 x ~1.2 мс = ~36 мс тик (на CPU 3.125 МГц)
SET_MS  EQU 30              ; 30 x ~1.2 мс = ~36 мс дебаунс
ENDIF

K_MS    EQU 144             ; внутренний счётчик единицы ~1 мс

; ---- порты CPLD (декод по A2-A0, зеркала mod 8) ----
SEGP    EQU 00h             ; сегменты: D0=a..D6=g, D7=dp; 1 = горит
DIGP    EQU 01h             ; D3-D0 разряды, D4 = SND
KBCOLP  EQU 02h             ; D3-D0 колонки (1 = заведена)
KBROWP  EQU 03h             ; D4-D0 ряды (1 = нажата в активной колонке)

; ---- XSTREAM v1 ----
TMR_HW  EQU 0               ; 0 = SW-тик (CPLD txuart v2.3); 1 = таймер->RST 7.5 (v24)
TXPORT  EQU 04h             ; TXDATA ядра TX v2.3 (запись при busy отбрасывается)
TMRP    EQU 06h             ; v24: загрузка N таймера (на v2.3 запись игнорируется)
XBUF    EQU 0B000h          ; ЭКРАН 80x25 = 2000 Б (B000h..B7CFh)
XSSEQ   EQU 0FFFAh          ; SEQ кадра mod 256
XSPASS  EQU 0FFFBh          ; накопитель слотов скана между кадрами (SW-тик)
XSDIV   EQU 0FFFCh          ; делитель ISR (только TMR_HW=1)
XS_TH   EQU 71              ; слотов скана между кадрами (сим-калибровка; ~49.8 мс)
XS_QINC EQU 4               ; добавка за единицу QUNIT/BUNIT (~1.2 мс = 3.7 слота)
TMR_N   EQU 250             ; v24: N тиков по 51.2 мкс = 12.80 мс
XS_DIVN EQU 2               ; v24: ISR на кадр; период = посылка + 2x12.80 = 49.7 мс
XSCNT   EQU XBUF+06E4h      ; живой счётчик SEQ в демо-экране (строка 22, кол. 4-5)

; ---- коды клавиш ----
K_ENT   EQU 10h             ; Enter  (row3/col3, SW16)
K_F1    EQU 11h             ; F1     (row4/col1, SW18) - меню
K_F2    EQU 12h             ; F2     (row4/col2, SW19) - показ адреса
K_NONE  EQU 0FFh            ; пустая позиция матрицы

; ---- состояния ----
ST_MENU EQU 00h             ; меню "ACDE"
ST_ADDR EQU 01h             ; ввод адреса
ST_PROG EQU 02h             ; ввод кода (Code)
ST_VIEW EQU 03h             ; просмотр кода
ST_SHOW EQU 04h             ; показ адреса операций (F2)

; ---- ОЗУ монитора (FFE8h-FFF9h; стек с FFE7 вниз) ----
SP0     EQU 0FFE8h          ; SP монитора
SNDST   EQU 0FFE8h          ; состояние тона 0/1
STATE   EQU 0FFE9h          ; 0=меню, 1=адрес, 2=код, 3=просмотр
ADDRH   EQU 0FFEAh          ; текущий адрес (старший)
ADDRL   EQU 0FFEBh          ; текущий адрес (младший)
ADCNT   EQU 0FFECh          ; введено тетрад адреса (0..4)
AF3     EQU 0FFEDh          ; тетрады адреса (AF3 - старшая...)
AF2     EQU 0FFEEh
AF1     EQU 0FFEFh
AF0     EQU 0FFF0h
BDCNT   EQU 0FFF1h          ; введено тетрад байта (0..2)
BF1     EQU 0FFF2h          ; старшая тетрада байта
BF0     EQU 0FFF3h          ; младшая тетрада байта
DPIDX   EQU 0FFF4h          ; фаза регенерации 0..3 (0 = DIG0)
DIGIMG  EQU 0FFF5h          ; глифы разрядов DIG0..DIG3 (4 байта)
DIGIMG0 EQU 0FFF5h          ;   правый (DIG0)
DIGIMG1 EQU 0FFF6h
DIGIMG2 EQU 0FFF7h
DIGIMG3 EQU 0FFF8h          ;   левый (DIG3)
PREVST  EQU 0FFF9h          ; прежний режим для F2

; =====================================================================
;                    СБРОС, ТАБЛИЦЫ, ВЕКТОР RST 7.5
; =====================================================================
        ORG 0000h
        JMP MAIN

; ---- глифы '0'..'F' (a,b,c,d,e,f,g = D0..D6) ----
GTBL:   DB 3Fh              ; '0'
        DB 06h              ; '1'
        DB 5Bh              ; '2'
        DB 4Fh              ; '3'
        DB 66h              ; '4'
        DB 6Dh              ; '5'
        DB 7Dh              ; '6'
        DB 07h              ; '7'
        DB 7Fh              ; '8'
        DB 6Fh              ; '9'
        DB 77h              ; 'A'
        DB 7Ch              ; 'b'
        DB 39h              ; 'C'
        DB 5Eh              ; 'd'
        DB 79h              ; 'E'
        DB 71h              ; 'F'

; ---- биты разрядов (индекс = DPIDX: 0=DIG0 правый ... 3=DIG3 левый) ----
BITTBL: DB 01h,02h,04h,08h

; ---- таблица клавиш: KEYTBL[row*4+col] ----
KEYTBL: DB 0Ah,0Bh,0Ch,0Dh  ; row0: A  B  C  D
        DB 07h,08h,09h,0Eh  ; row1: 7  8  9  E
        DB 04h,05h,06h,0Fh  ; row2: 4  5  6  F
        DB 01h,02h,03h,10h  ; row3: 1  2  3  Enter
        DB 00h,11h,12h,0FFh ; row4: 0  F1 F2 (нет)

; ---- ВЕКТОР RST 7.5 (003Ch) - XSTREAM ----
;   TMR_HW=1: обработчик кадра по таймеру CPLD (v24);
;   TMR_HW=0: на CPLD v2.3 линия заземлена - вход невозможен.
        ORG 003Ch
        JMP XISR

        ORG 0040h           ; код монитора смещён вектором (3 Б из 003Ch)

; ---------------------------------------------------------------------
; SETTLE: пауза ~25 мкс (успокоение колонки клавиатуры)
; ---------------------------------------------------------------------
SETTLE: LXI B,3
STL:    DCX B
        MOV A,B
        ORA C
        JNZ STL
        RET

; ---------------------------------------------------------------------
; SCANALL: опрос всех 4 колонок; A = ИЛИ рядов (0 = нажатий нет);
; колонки на выходе погашены. Портит A/B/C/D/E.
; ---------------------------------------------------------------------
SCANALL: XRA A
        MOV E,A             ; E = накопитель
        MVI D,01h           ; D = бит колонки
SAL1:   MOV A,D
        OUT KBCOLP
        CALL SETTLE
        IN KBROWP
        ANI 1Fh
        ORA E
        MOV E,A
        MOV A,D
        RLC
        MOV D,A
        CPI 10h
        JNZ SAL1
        XRA A
        OUT KBCOLP
        MOV A,E
        RET

; ---------------------------------------------------------------------
; REFRESH: один слот регенерации. ГАШЕНИЕ -> РАЗРЯД -> ГЛИФ.
; DIGIMG[DPIDX] на разряд DPIDX. Бит D4 (SND) уносится записью DIGP -
; дисплей при тоне не гаснет. Портит A/B/C/H/L.
; ---------------------------------------------------------------------
REFRESH: LDA DPIDX
        MOV C,A             ; C = индекс 0..3
        MVI B,0
        LXI H,BITTBL
        DAD B
        MOV B,M             ; B = бит разряда (01,02,04,08)
        LXI H,DIGIMG        ; HL = DIGIMG + DPIDX
RFIL:   MOV A,C
        ORA A
        JZ RFGD
        INR L
        DCR C
        JMP RFIL
RFGD:   MOV C,M             ; C = глиф разряда
        LDA SNDST
        ORA A
        JZ RFN
        MOV A,B
        ORI 10h
        MOV B,A             ; B |= SND
RFN:    XRA A
        OUT SEGP            ; (1) гашение: старый разряд погас
        MOV A,B
        OUT DIGP            ; (2) разряд переключён (сегменты пусты)
        MOV A,C
        OUT SEGP            ; (3) зажгли глиф нового разряда
        LDA DPIDX
        INR A
        ANI 03h
        STA DPIDX
        RET

; ---------------------------------------------------------------------
; BUNIT: единица ~1 мс + тоггл SNDST + регенерация дисплея
;         + XSTREAM SW-тик (кадр не останавливается на тоне/дебаунсе)
; QUNIT: единица ~1 мс без звука, дисплей живёт
; ---------------------------------------------------------------------
BUNIT:  LXI B,K_MS
BUL:    DCX B
        MOV A,B
        ORA C
        JNZ BUL
        LDA SNDST
        XRI 01h
        STA SNDST
        CALL REFRESH
        MVI A,XS_QINC
        CALL XSCHK          ; XSTREAM: тик кадра
        RET

QUNIT:  LXI B,K_MS
QUL:    DCX B
        MOV A,B
        ORA C
        JNZ QUL
        CALL REFRESH
        RET

; ---------------------------------------------------------------------
; TICKON: короткий тик подтверждения клавиши (TICK_MS единиц ~1 мс,
; тон ~415 Гц на CPU 3.125 МГц). Счётчик - В DE.
; ---------------------------------------------------------------------
TICKON: LXI D,TICK_MS
TK1:    CALL BUNIT
        DCX D
        MOV A,D
        ORA E
        JNZ TK1
        XRA A
        STA SNDST           ; тон гарантированно погашен
        RET

; ---------------------------------------------------------------------
; GLOOK: A = тетрада 0..F -> A = глиф (GTBL). Портит A/B/C/H/L.
; ---------------------------------------------------------------------
GLOOK:  MOV C,A
        MVI B,0
        LXI H,GTBL
        DAD B
        MOV A,M
        RET

; ---------------------------------------------------------------------
; REDRAW: пересобрать DIGIMG[0..3] по состоянию (меню/адрес/код/...)
; ---------------------------------------------------------------------
REDRAW: LDA STATE
        ORA A
        JZ RDM
        CPI 01h
        JZ RDA
        CPI 03h
        JZ RDV
        CPI 04h
        JZ RDW
        ; ---- ST_PROG ----
        XRA A
        STA DIGIMG3
        STA DIGIMG2
        STA DIGIMG1
        STA DIGIMG0
        LDA BDCNT
        CPI 02h
        JC RDPR0            ; <2 - старшая тетрада пуста
        LDA BF1
        CALL GLOOK
        STA DIGIMG1
RDPR0:  LDA BDCNT
        ORA A
        JZ RDRE             ; 0 - младшая тоже пуста
        LDA BF0
        CALL GLOOK
        STA DIGIMG0
        JMP RDRE
RDV:    LDA ADDRH           ; ---- ST_VIEW: [ADDR] в правых разрядах ----
        MOV H,A
        LDA ADDRL
        MOV L,A             ; HL = ADDR
        MOV A,M             ; A = [ADDR] (HL>=8000h - ОЗУ)
        MOV D,A             ; D = байт (GLOOK портит B)
        RRC
        RRC
        RRC
        RRC
        ANI 0Fh             ; старшая тетрада
        CALL GLOOK
        STA DIGIMG1
        MOV A,D
        ANI 0Fh             ; младшая тетрада
        CALL GLOOK
        STA DIGIMG0
        XRA A
        STA DIGIMG3
        STA DIGIMG2
        JMP RDRE
RDW:    LDA ADDRH           ; ---- ST_SHOW: ADDR на 4 разрядах ----
        MOV D,A             ; D = старший байт (GLOOK портит B)
        RRC
        RRC
        RRC
        RRC
        ANI 0Fh             ; старшая тетрада
        CALL GLOOK
        STA DIGIMG3
        MOV A,D
        ANI 0Fh
        CALL GLOOK
        STA DIGIMG2
        LDA ADDRL
        MOV D,A
        RRC
        RRC
        RRC
        RRC
        ANI 0Fh
        CALL GLOOK
        STA DIGIMG1
        MOV A,D
        ANI 0Fh
        CALL GLOOK
        STA DIGIMG0
        JMP RDRE
RDM:    MVI A,77h           ; 'A'
        STA DIGIMG3
        MVI A,39h           ; 'C'
        STA DIGIMG2
        MVI A,5Eh           ; 'd' (D)
        STA DIGIMG1
        MVI A,79h           ; 'E'
        STA DIGIMG0
        JMP RDRE
RDA:    XRA A               ; ---- ST_ADDR: последняя тетрада справа ----
        STA DIGIMG3
        STA DIGIMG2
        STA DIGIMG1
        STA DIGIMG0
        LDA ADCNT
        CPI 01h             ; 0 тетрад - всё пусто
        JC RDRE
        LDA AF0             ; DIG0 = AF0 (последний ввод)
        CALL GLOOK
        STA DIGIMG0
        LDA ADCNT
        CPI 02h
        JC RDRE
        LDA AF1             ; DIG1 = AF1
        CALL GLOOK
        STA DIGIMG1
        LDA ADCNT
        CPI 03h
        JC RDRE
        LDA AF2             ; DIG2 = AF2
        CALL GLOOK
        STA DIGIMG2
        LDA ADCNT
        CPI 04h
        JC RDRE
        LDA AF3             ; DIG3 = AF3 (старшая)
        CALL GLOOK
        STA DIGIMG3
RDRE:   RET

; ---------------------------------------------------------------------
; MAIN / MAIN2
; ---------------------------------------------------------------------
MAIN:   DI
        LXI SP,SP0
        MVI A,80h           ; адрес по умолчанию 8000h (начало ОЗУ)
        STA ADDRH
        XRA A
        STA ADDRL
        CALL XSINIT         ; XSTREAM v1: демо-экран B000h, SEQ=0 (холодный старт)
        IF TMR_HW
        EI                  ; HW: поток идёт всегда (ISR самодостаточен)
        ENDIF
MAIN2:  XRA A
        OUT SEGP            ; дисплей погашен (после сброса горел "8.")
        OUT DIGP            ; разряды off, SND off
        OUT KBCOLP          ; колонки off (безопасный INIT)
        STA SNDST
        STA ADCNT
        STA BDCNT
        STA DPIDX
        STA STATE           ; ST_MENU
        STA PREVST          ; прежний режим детерминирован (0 = меню)
        CALL REDRAW         ; "ACdE"

; ---- главный цикл: скан 4 колонок, без нажатий - слот регенерации ----
SCAN:   MVI E,0             ; E = индекс колонки 0..3
        MVI D,01h           ; D = бит колонки
SC1:    MOV A,D
        OUT KBCOLP
        CALL SETTLE
        IN KBROWP
        ANI 1Fh
        JNZ HIT
        MOV A,D
        RLC
        MOV D,A
        INR E
        CPI 10h
        JNZ SC1
        CALL REFRESH        ; нажатий нет - слот дисплея
        MVI A,1
        CALL XSCHK          ; XSTREAM: SW-тик кадра (в HW-режиме - тихий RET)
        JMP SCAN

; ---- нажатие поймано: A = ряды, E = индекс колонки ----
HIT:    PUSH PSW
        XRA A
        OUT KBCOLP          ; колонки off (фиксируем факт нажатия)
        POP PSW

        MVI D,0             ; D = номер строки
H1:     RRC
        JC H2
        INR D
        JMP H1
H2:     MOV A,D             ; D = строка, E = колонка; код = KEYTBL[row*4+col]
        RLC
        RLC                 ; A = row*4
        MOV C,A
        MOV A,E
        ORA C               ; | col
        MOV C,A
        MVI B,0
        LXI H,KEYTBL
        DAD B
        MOV A,M
        CPI 0FFh
        JZ NKEY             ; пустая позиция матрицы
        CALL DISPATCH
NKEY:   CALL SCANALL        ; ожидание отпускания + дебаунс
        ANI 1Fh
        JZ WDN
        CALL REFRESH
        MVI A,1
        CALL XSCHK          ; XSTREAM: кадр идёт и при удержании клавиши
        JMP NKEY
WDN:    LXI D,SET_MS        ; счётчик В DE (QUNIT->REFRESH портит HL)
ST1:    CALL QUNIT
        MVI A,XS_QINC
        CALL XSCHK          ; XSTREAM: кадр идёт во время дебаунса
        DCX D
        MOV A,D
        ORA E
        JNZ ST1
        JMP SCAN

; ---------------------------------------------------------------------
; DISPATCH: обработка кода клавиши (A). F1 - глобально в меню,
; F2 - глобально показать адрес операций (повторное F2 - назад).
; Смены состояния подтверждаются тиком; K_IGN - молча.
; ---------------------------------------------------------------------
DISPATCH: MOV C,A           ; C = КОД КЛАВИШИ (LDA STATE затирает A!)
        CPI K_F2
        JZ K_F2E
        CPI K_F1
        JZ K_F1E
        LDA STATE
        ORA A
        JZ DSM
        CPI 01h
        JZ DSA
        CPI 02h
        JZ DSP
        CPI 04h
        JZ DSW              ; показ адреса: прочие клавиши - игнор
        ; ================= ST_VIEW =================
DSV:    MOV A,C             ; вернули код клавиши
        CPI K_ENT
        JZ VENT
        RET                 ; тетрады - игнор (режим только чтение)
VENT:   LDA ADDRL
        MOV L,A
        LDA ADDRH
        MOV H,A
        INX H               ; ADDR++
        MOV A,H
        STA ADDRH
        MOV A,L
        STA ADDRL
        CALL TICKON
        CALL REDRAW         ; следующий байт на дисплее
        RET
        ; ================= ST_PROG =================
DSP:    MOV A,C             ; вернули код клавиши
        CPI K_ENT
        JZ PENT
        CPI 10h
        JC PDIG             ; 00h..0Fh - тетрада байта
        RET                 ; прочие - игнор
PDIG:   MOV A,C             ; A = тетрада
        MOV B,A             ; B = тетрада (C больше не нужен)
        LDA BF0
        STA BF1             ; сдвиг: BF1 = BF0
        MOV A,B
        STA BF0             ; BF0 = новая тетрада
        LDA BDCNT
        CPI 02h
        JNC PDS
        INR A
        STA BDCNT
PDS:    CALL TICKON
        CALL REDRAW
        RET
PENT:   LDA BDCNT
        ORA A
        JZ PIGN             ; пусто - игнор (без записи)
        LDA BF1
        RLC
        RLC
        RLC
        RLC
        MOV C,A
        LDA BF0
        ORA C               ; C = байт
        MOV C,A
        LDA ADDRH
        MOV H,A
        LDA ADDRL
        MOV L,A
        MOV M,C             ; [ADDR] = байт (A15=0 железо отбросит)
        INX H               ; ADDR++
        MOV A,H
        STA ADDRH
        MOV A,L
        STA ADDRL
        XRA A
        STA BDCNT           ; поле гасится - ждем следующий байт
        CALL TICKON
        CALL REDRAW
PIGN:   RET
        ; ================= ST_ADDR =================
DSA:    MOV A,C             ; вернули код клавиши
        CPI K_ENT
        JZ AENT
        CPI 10h
        JC ADIG             ; 00h..0Fh - тетрада адреса
        RET
ADIG:   MOV A,C             ; A = тетрада
        MOV B,A             ; B = тетрада
        LDA AF2
        STA AF3
        LDA AF1
        STA AF2
        LDA AF0
        STA AF1
        MOV A,B
        STA AF0
        LDA ADCNT
        CPI 04h
        JNC ADS
        INR A
        STA ADCNT
ADS:    CALL TICKON
        CALL REDRAW
        RET
AENT:   LDA ADCNT
        ORA A
        JZ AIGN             ; пусто - игнор
        LDA AF3
        RLC
        RLC
        RLC
        RLC
        MOV C,A
        LDA AF2
        ORA C
        STA ADDRH
        LDA AF1
        RLC
        RLC
        RLC
        RLC
        MOV C,A
        LDA AF0
        ORA C
        STA ADDRL
        XRA A
        STA STATE           ; в меню
        CALL TICKON
        CALL REDRAW
AIGN:   RET
        ; ================= ST_MENU =================
DSM:    MOV A,C             ; вернули код клавиши
        CPI 0Ah             ; 'A' - ввод адреса
        JZ KAD
        CPI 0Ch             ; 'C' - ввод кода (Code)
        JZ KPR
        CPI 0Dh             ; 'D' - просмотр кода
        JZ KVD
        CPI 0Eh             ; 'E' - выполнить
        JZ KGO
        RET                 ; остальные (в т.ч. B) - игнор
KAD:    MVI A,ST_ADDR
        STA STATE
        XRA A
        STA ADCNT
        CALL TICKON
        CALL REDRAW
        RET
KPR:    MVI A,ST_PROG       ; C: ввод кода (Code)
        STA STATE
        XRA A
        STA BDCNT
        CALL TICKON
        CALL REDRAW
        RET
KVD:    MVI A,ST_VIEW       ; D: просмотр кода
        STA STATE
        CALL TICKON
        CALL REDRAW
        RET
; ---- F2: показ адреса операций (глобально; повторное F2 - назад) ----
K_F2E:  LDA STATE
        CPI ST_SHOW
        JZ KF2B             ; уже показываем - вернуть прежний режим
        STA PREVST          ; запомнить, откуда пришли
        MVI A,ST_SHOW
        STA STATE
        CALL TICKON
        CALL REDRAW
        RET
KF2B:   LDA PREVST
        STA STATE
        CALL TICKON
        CALL REDRAW
        RET
DSW:    RET                 ; показ адреса: Enter/тетрады не действуют
K_F1E:  XRA A
        STA STATE           ; меню (из любого режима)
        CALL TICKON
        CALL REDRAW
        RET
        ; ================= GO: запуск =================
KGO:    XRA A
        OUT SEGP            ; сегменты 0
        OUT DIGP            ; разряды 0, SND 0
        OUT KBCOLP          ; колонки off
        DI
        LXI SP,SP0
        LXI H,MONRET
        PUSH H              ; адрес возврата в монитор
        IF TMR_HW
        EI                  ; пользовательская программа живёт вместе с потоком
        ENDIF
        LDA ADDRH
        MOV H,A
        LDA ADDRL
        MOV L,A             ; HL = адрес запуска
        XRA A
        MOV B,A
        MOV C,A
        MOV D,A
        MOV E,A             ; регистры обнулены
        PCHL                ; ушли в программу пользователя
MONRET: DI
        LXI SP,SP0
        ; ждем отпускания всех клавиш + дебаунс
MNR1:   CALL SCANALL
        ANI 1Fh
        JZ MNR2
        CALL REFRESH
        MVI A,1
        CALL XSCHK          ; XSTREAM: кадр идёт при удержании клавиши
        JMP MNR1
MNR2:   LXI D,SET_MS        ; счётчик В DE (QUNIT->REFRESH портит HL)
MNR3:   CALL QUNIT
        MVI A,XS_QINC
        CALL XSCHK          ; XSTREAM: кадр идёт во время дебаунса
        DCX D
        MOV A,D
        ORA E
        JNZ MNR3
        IF TMR_HW
        EI                  ; возврат потока после DI пользователя/монитора
        ENDIF
        JMP MAIN2           ; реинициализация, ADDR сохранен

; =====================================================================
;                     XSTREAM v1: ЭКРАН -> UART
; =====================================================================
; ---------------------------------------------------------------------
; XSINIT (из MAIN, только холодный старт): демо-экран в B000h,
; SEQ/PASS = 0. В HW-варианте: делитель, запуск таймера, маска SIM
; (M7.5 = НЕ маскировать, 6.5/5.5 маскированы), EI.
; Мониторные переменные не трогаются; B000-B7CF - пользовательская
; область: ЛЮБАЯ программа может рисовать туда свой текст/графику.
; ---------------------------------------------------------------------
XSINIT: CALL XBLANK
        LXI H,XTBL
XSI1:   MOV E,M             ; DE = адрес назначения
        INX H
        MOV D,M
        INX H               ; HL -> src_lo
        MOV A,D             ; конец таблицы (dst == 0000)?
        ORA E
        JZ XSI3
        MOV C,M             ; BC = адрес строки (источник)
        INX H
        MOV B,M
        INX H               ; HL -> следующая запись
        PUSH H              ; указатель следующей записи -> стек
        MOV H,B
        MOV L,C
        CALL XCPY           ; ASCIZ [HL] -> [DE], 0 = конец
        POP H
        JMP XSI1
XSI3:   XRA A
        STA XSSEQ
        STA XSPASS
        IF TMR_HW
        MVI A,XS_DIVN
        STA XSDIV
        MVI A,TMR_N
        OUT TMRP            ; запустить таймер: 1-й фронт через ~12 мс
        MVI A,00011000b     ; SIM: MSE=1, M7.5=0 (НЕ маскировать), 6.5/5.5 маскированы
        SIM
        EI
        ENDIF
        RET

XBLANK: LXI H,XBUF          ; 2000 пробелов
        LXI B,2000
XB1:    MVI A,20h
        MOV M,A
        INX H
        DCX B
        MOV A,B
        ORA C
        JNZ XB1
        RET

XCPY:   MOV A,M             ; ASCIZ: [HL]->[DE], 0 = конец (A/флаги)
        ORA A
        RZ
        STAX D
        INX H
        INX D
        JMP XCPY

; ---------------------------------------------------------------------
; XSCHK: SW-тик кадра. A = добавка слотов (1 = слот скана ~0.37 мс,
; XS_QINC = единица QUNIT/BUNIT ~1.2 мс). Накопитель XSPASS;
; порог XS_TH -> XSEND (~24.3 мс) и сброс. Портит A/C; D/E/B целы.
; В HW-варианте тело выключено (кадр ведёт ISR) - вызов = RET.
; ---------------------------------------------------------------------
        IF TMR_HW
XSCHK:  RET                 ; HW: кадр ведёт ISR по таймеру; SW-тик отключён
        ELSE
XSCHK:  MOV C,A
        LDA XSPASS
        ADD C
        STA XSPASS
        CPI XS_TH
        JC XSKR             ; < порога - выход
        CALL XSEND          ; КАДР -> UART (~24.3 мс)
        XRA A
        STA XSPASS          ; счётчик заново
XSKR:   RET
        ENDIF

; ---------------------------------------------------------------------
; XSEND: кадр XSTREAM в UART: A5 5A [SEQ] + 2000 Б из XBUF.
;   Сохраняет PSW/B/D/H. РАВНОМЕРНЫЙ пейсинг 35T/Б (7+10+6+3x4 >= 31.25T,
;   ноль отбросов TX, прецедент p04); каждые 80 Б - слот дисплея XDIG
;   (D/E - фаза дисплея, C свободен после inner, B - внешний 20x100).
; ---------------------------------------------------------------------
XSEND:  PUSH PSW
        PUSH B
        PUSH D
        PUSH H
        CALL XUPDCTR        ; живой счётчик SEQ в демо-экран
        MVI A,0A5h
        OUT TXPORT          ; шапка: равномерный пейсинг 33T (4 NOP)
        NOP
        NOP
        NOP
        NOP
        MVI A,05Ah
        OUT TXPORT
        NOP
        NOP
        NOP
        NOP
        LDA XSSEQ
        OUT TXPORT
        NOP
        NOP
        NOP
        NOP
        INR A
        STA XSSEQ           ; SEQ++ mod 256
        LXI H,BITTBL        ; фаза дисплея: E = бит разряда, D = ptr глифа
        LDA DPIDX
        MOV C,A
        MVI B,0
        DAD B
        MOV A,M
        MOV E,A
        MOV A,C
        ADI 0F5h            ; DIGIMG = 0FFF5h (+DPIDX 0..3)
        MOV D,A
        LXI H,XBUF          ; HL = экран
        MVI B,10            ; внешний: 10 групп по 200 Б (слот дисплея)
XSOUT:  MVI C,25            ; внутренний: 25 подгрупп по 8 Б
XSL:    MOV A,M
        OUT TXPORT          ; равномерный пейсинг: гэп OUT->OUT = 23T+пад >= 31.25T
        INX H
        NOP
        NOP
        NOP
        MOV A,M
        OUT TXPORT
        INX H
        NOP
        NOP
        NOP
        MOV A,M
        OUT TXPORT
        INX H
        NOP
        NOP
        NOP
        MOV A,M
        OUT TXPORT
        INX H
        NOP
        NOP
        NOP
        MOV A,M
        OUT TXPORT
        INX H
        NOP
        NOP
        NOP
        MOV A,M
        OUT TXPORT
        INX H
        NOP
        NOP
        NOP
        MOV A,M
        OUT TXPORT
        INX H
        NOP
        NOP
        NOP
        MOV A,M
        OUT TXPORT
        INX H
        NOP
        NOP
        NOP
        DCR C               ; подгруппа = 7x35T + 49T = 294T (36.75T/Б)
        JNZ XSL
        CALL XDIG           ; слот дисплея (регенерация не замирает)
        DCR B
        JNZ XSOUT
        POP H
        POP D
        POP B
        POP PSW
        RET

; ---------------------------------------------------------------------
; XDIG: один слот регенерации дисплея ВО ВРЕМЯ посылки.
;   D = ptr глифа (DIGIMG0..3, FFF5h..FFF8h), E = бит разряда -
;   своя фаза (DPIDX не трогает, к возврату монитор продолжит свою).
;   Тон: SNDST OR-ится в бит разряда (запись DIGP несет D4).
;   Глиф хранится в C (внутр. счётчик к этому моменту отработан);
;   A/флаги портит свободно (XSEND сохранил PSW). ~187T + CALL.
; ---------------------------------------------------------------------
XDIG:   XRA A
        OUT SEGP            ; гашение
        LDAX D              ; A = глиф текущего разряда
        MOV C,A
        LDA SNDST
        ORA A
        JZ XDG1
        MOV A,E
        ORI 10h             ; + SND
        JMP XDG2
XDG1:   MOV A,E
XDG2:   OUT DIGP            ; разряд (и тон) включён
        MOV A,C
        OUT SEGP            ; глиф горит
        INX D
        MOV A,D
        ANI 03h             ; оставить 0..3 (обёртка DIGIMG0..3)
        ORI 0F5h            ; DIGIMG = 0FFF5h
        MOV D,A
XDG3:   MOV A,E
        RLC
        ANI 0Fh             ; 08h -> 10h -> 00
        JNZ XDG4
        MVI A,01h           ; после DIG3 -> DIG0
XDG4:   MOV E,A
        RET

; ---------------------------------------------------------------------
; XUPDCTR: живой счётчик SEQ (hex, 2 цифры) в демо-экран, строка 22:
;   'SEQ:xx ...' - x на B6E4/B6E5. Доказательство живого потока.
; ---------------------------------------------------------------------
XUPDCTR: PUSH H
        LDA XSSEQ
        MOV C,A
        RRC
        RRC
        RRC
        RRC
        ANI 0Fh
        CALL XHEX
        STA XSCNT
        MOV A,C
        ANI 0Fh
        CALL XHEX
        STA XSCNT+1
        POP H
        RET

XHEX:   ADI '0'
        CPI 3Ah
        JC XHX1
        ADI 07h
XHX1:   RET

; ---------------------------------------------------------------------
; XISR - обработчик RST 7.5 (вектор 003Ch).
;   HW: делитель XS_DIVN (период = посылка 22.9 мс + (XS_DIVN-1) x
;   T = N x 51.2 мкс; TMR_N=234, XS_DIVN=3 -> 46.9 мс = 21.3 FPS,
;   48.8% ЦП); ре-арм ПОСЛЕ тела - таймер не истекает внутри ISR,
;   каденция точная. ISR выбивает из монитора/программы пользователя.
;   SW (v2.3): линия заземлена - вход невозможен; тихий выход.
; ---------------------------------------------------------------------
        IF TMR_HW
XISR:   PUSH PSW
        PUSH B
        PUSH D
        PUSH H
        LDA XSDIV
        DCR A
        STA XSDIV
        JNZ XISR1
        MVI A,XS_DIVN
        STA XSDIV
        CALL XSEND          ; КАДР -> UART
XISR1:  MVI A,TMR_N
        OUT TMRP            ; ре-арм ПОСЛЕ тела: следующий фронт через N тиков
        POP H
        POP D
        POP B
        POP PSW
        EI
        RET
        ELSE
XISR:   PUSH PSW
        EI                  ; страховка: маска не трогается, тихий выход
        RET
        ENDIF

; ---- демо-экран (ASCII; NUL-конец; <= 80 символов на строку) ----
S_T0:   DB 'XSTREAM v1.0 - 80x25 TEXT SCREEN BUFFER B000h-B7CFh -> UART 1000000 8N1',0
S_T1:   DB 'FRAME: A5 5A [SEQ] + 2000 BYTES (ROW-MAJOR 80x25 / CP1251 AT PC CLIENT)',0
S_T2:   DB 'FW: fw_mon ACdE + STREAM - TMR_HW=0 SW-TICK 20 FPS / TMR_HW=1 RST 7.5 (v24)',0
S_T3:   DB 'MONITOR: A=ADDR  C=CODE  D=VIEW  E=RUN  F1=MENU  F2=SHOW ADDR',0
S_T4:   DB 'WRITE YOUR TEXT INTO B000h..B7CFh - THIS WINDOW IS THE PC SCREEN',0
S_T5:   DB 'LOAD: SEND 24.2 MS OF 49.8 MS = 49% | LINE 40% | SEQ:__',0
XTBL:   DW XBUF, S_T0       ; строка 0
        DW XBUF+00A0h, S_T1 ; строка 2
        DW XBUF+00F0h, S_T2 ; строка 3
        DW XBUF+0280h, S_T3 ; строка 5
        DW XBUF+0320h, S_T4 ; строка 6
        DW XBUF+06E0h, S_T5 ; строка 22 (счётчик SEQ живой)
        DW 0000h, 0000h     ; конец таблицы

        END
