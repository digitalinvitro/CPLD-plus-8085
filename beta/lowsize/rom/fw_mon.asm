; =====================================================================
; beta/lowsize/rom -- fw_mon: МОНИТОР дисплея и клавиатуры (меню ACDE)
;
; Плата: retro_PCLD_board V2, CPLD = beta/lowsize v3.9.1/v3.9.2
; (транзиты kbcol/kbrow/seg/dig/SND идентичны v3.2...v3.9.x).
; Прошивается в flash A29040B с offset 0 (это и есть fw_mon: тест-прошивки
; fw_test_disp/fw_text_kbd после приёмки 10-30 больше не нужны).
;
; Сборка (asm85.py, исходник CP1251):
;   python3 asm85.py fw_mon.asm -o fw_mon.hex -l fw_mon.lst
;   быстрый вариант для стендовой симуляции:
;   python3 asm85.py fw_mon.asm -o fw_mon_fast.hex -D FAST=1
;
; МАТРИЦА (PORTS_MAP.md §10): 4 колонки - ВЫХОДЫ порт 02h (D0..D3, 1 =
; заведена; после сброса 0000), 5 рядов - ВХОДЫ порт 03h (D0..D4,
; подтяжки 10к на GND, покой = 0, нажатие = 1). Клавиша (row,col) =
; SW_{row*4+col+1}. КАРТА КЛАВИШ (в скобках - что показывал тест
; клавиатуры fw_text_kbd, "строка__колонка"):
;
;            col0        col1        col2        col3
;   row0     A (0__0)    B (0__1)    C (0__2)    D (0__3)
;   row1     7 (1__0)    8 (1__1)    9 (1__2)    E (1__3)
;   row2     4 (2__0)    5 (2__1)    6 (2__2)    F (2__3)
;   row3     1 (3__0)    2 (3__1)    3 (3__2)    Enter (3__3)
;   row4     0 (4__0)    F1 (4__1)   F2 (4__2)   (нет: SW20 = RESET)
;
; РЕЖИМЫ (по ТЗ владельца, клк10-69/70): меню "ACDE" - 4 буквы на 4
; разрядах, каждая буква = своя функция (C созвучно с Code, клавиша
; C = 0__2 есть на матрице; "P" не потребовался вовсе):
;   F1 (4__1)  - системное меню "ACDE" (работает из ЛЮБОГО режима);
;   A (0__0)   - из меню: ввод адреса, 4 знака; цифры 0-F вдвигаются
;                справа (как на калькуляторе: 8 -> "___8", 80 -> "__80"),
;                лишние (5-й и дальше) выталкивают старшие;
;   Enter      - завершает ввод адреса (при 0 знаков - игнор);
;   C (0__2)   - из меню: ВВОД КОДА (Code). Байт в КОДАХ 8085 - 2 тетрады
;                в ПРАВЫХ разрядах, слева пусто ("__C3"); Enter - записать
;                байт в [ADDR], ADDR++, поле гасится; Enter при пустом
;                поле - игнор; F1 - конец ввода, возврат в меню;
;   D (0__3)   - из меню: ПРОСМОТР КОДА с введённого адреса: в правых
;                разрядах байт [ADDR] ("__C3"), слева пусто; Enter -
;                ADDR++ и показать следующий байт; F1 - возврат в меню;
;                режим только чтение (тетрады игнорируются);
;   E (1__3)   - из меню: запуск программы с введённого адреса (по
;                умолчанию 8000h); дисплей гасится, DI, регистры 0,
;                SP = FFE8h, в стеке - адрес возврата в монитор;
;   ВЫХОД из пользовательской программы: RET (C9) - вернёт в меню "ACDE"
;   (ждёт отпускания клавиш + дебаунс 30 мс); аварийный выход - RESET.
;   В меню остальные клавиши (0-9,B,F,F2,Enter) игнорируются; в режимах
;   адреса/кода A,C,D,E - обычные тетрады (кроме Enter/F1).
;
; ПАМЯТЬ (MEMORY_MAP.md): ROM 0000h-7FFFh (запись невозможна - железо
; отбрасывает), RAM 8000h-FFFFh. Служебные монитора: FFE8h-FFF8h
; (переменные, см. ниже), стек с FFE7h вниз. ПОЛЬЗОВАТЕЛЬСКАЯ ОБЛАСТЬ:
; 8000h-FFE7h. Пример: A -> 8000 -> Enter -> C -> C3 Enter 0E Enter ->
; F1 -> D: "__C3" (байт в 8000), Enter -> "__0E" (8001), F1 -> E - пуск.
; (RAM 8000=C3 8001=0E = JMP 000Eh... для пробы введите C9 - RET).
;
; ДИСПЛЕЙ: динамическая регенерация 4 разрядов, порядок ГАШЕНИЕ ->
; РАЗРЯД -> ГЛИФ (клк10-67, послесвечения нет - проверено на плате
; 10-30). Слот = один проход скана матрицы (~290 мкс: 4 колонки по
; ~180 T + REFRESH ~300 T) -> полный цикл дисплея ~1,16 мс (~860 Гц),
; скважность 1/4. Короткий ТИК ~31 мс (~500 Гц) на нажатую клавишу;
; бит SND (D4) едет в записи DIGP внутри REFRESH - дисплей при тике
; НЕ гаснет.
;
; ТАЙМИНГ (CPU 3,571 МГц, T = 280 нс):
;   SETTLE ~25 мкс (89 T); единица BUNIT/QUNIT ~1,05 мс (K_MS=144);
;   тик клавиши = TICK_MS единиц (полный 30 ~ 31 мс, FAST 4);
;   дебаунс отпускания = SET_MS единиц (полный 30 ~ 31 мс, FAST 2);
;   задержка реакции на нажатие < 1,2 мс (скан непрерывный).
; Ожидаемый тон тика по замеру на симуляции: ~500 Гц (полупериод ~1 мс).
; =====================================================================

; ---- константы (переопределяются через -D) ----
FAST    EQU 0               ; 1 = укороченные паузы (для симуляции)
IF FAST
TICK_MS EQU 4               ; тик клавиши, единиц ~1 мс (быстро)
SET_MS  EQU 2               ; дебаунс после отпускания
ELSE
TICK_MS EQU 30              ; 30 x ~1,05 мс = ~31 мс тик
SET_MS  EQU 30              ; 30 x ~1,05 мс = ~31 мс дебаунс
ENDIF

K_MS    EQU 144             ; внутренний счётчик единицы ~1 мс

; ---- порты CPLD (декод по A2-A0, зеркала mod 8) ----
SEGP    EQU 00h             ; сегменты: D0=a..D6=g, D7=dp; 1 = горит
DIGP    EQU 01h             ; D3-D0 разряды, D4 = SND
KBCOLP  EQU 02h             ; D3-D0 колонки (1 = заведена)
KBROWP  EQU 03h             ; D4-D0 ряды (1 = нажата в активной колонке)

; ---- коды клавиш (после KEYTBL) ----
; 00h..0Fh = тетрады 0..F; далее:
K_ENT   EQU 10h             ; Enter  (row3/col3, SW16)
K_F1    EQU 11h             ; F1     (row4/col1, SW18) - меню
K_F2    EQU 12h             ; F2     (row4/col2, SW19) - резерв
K_NONE  EQU 0FFh            ; пустая позиция матрицы

; ---- состояния ----
ST_MENU EQU 00h             ; меню "ACDE"
ST_ADDR EQU 01h             ; ввод адреса
ST_PROG EQU 02h             ; ввод кода (Code)
ST_VIEW EQU 03h             ; просмотр кода

; ---- ОЗУ (служебные монитора, FFE8h-FFF8h; стек с FFE7h вниз) ----
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

; ---- КАРТА КЛАВИШ: KEYTBL[row*4+col] ----
KEYTBL: DB 0Ah,0Bh,0Ch,0Dh  ; row0: A  B  C  D
        DB 07h,08h,09h,0Eh  ; row1: 7  8  9  E
        DB 04h,05h,06h,0Fh  ; row2: 4  5  6  F
        DB 01h,02h,03h,10h  ; row3: 1  2  3  Enter
        DB 00h,11h,12h,0FFh ; row4: 0  F1 F2 (нет)

; ---------------------------------------------------------------------
; SETTLE: пауза ~25 мкс (установка рядов после заведения колонки)
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
; REFRESH: один слот регенерации. ГАШЕНИЕ -> РАЗРЯД -> ГЛИФ
; (клк10-67, без послесвечения). DIGIMG[DPIDX] на разряд DPIDX.
; Бит D4 (SND) уносится записью DIGP - дисплей при тоне не гаснет.
; Портит A/B/C/H/L (D/E - бит колонки и индекс скана - НЕ трогает).
; ---------------------------------------------------------------------
REFRESH: LDA DPIDX
        MOV C,A             ; C = индекс 0..3
        MVI B,0
        LXI H,BITTBL
        DAD B
        MOV B,M             ; B = бит разряда (01,02,04,08)
        LXI H,DIGIMG        ; HL = DIGIMG + DPIDX (цикл вместо ADD)
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
; тон ~500 Гц). Дисплей живёт (SND едет в записи DIGP внутри REFRESH).
; Счётчик - В DE: REFRESH портит HL, но гарантирует D/E.
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
; REDRAW: пересобрать DIGIMG[0..3] по состоянию.
;   меню : DIG3='A'(77) DIG2='C'(39) DIG1='d'(5E) DIG0='E'(79) = "ACDE"
;   адрес: 4 тетрады вдвигаются СПРАВА (новая - в AF0/DIG0, старые
;          уходят влево), показаны последние ADCNT, пустые старшие
;          гаснут; 5-я тетрада вытесняет старшую
;   код  : DIG3/DIG2 пусто, DIG1 = BF1 (при BDCNT>=2), DIG0 = BF0
;          (при BDCNT>=1) - вид "__C3"
;   просм.: DIG3/DIG2 пусто, DIG1/DIG0 = байт [ADDR] - вид "__C3"
; ---------------------------------------------------------------------
REDRAW: LDA STATE           ; пересборка глифов по состоянию
        ORA A
        JZ RDM
        CPI 01h
        JZ RDA
        CPI 03h
        JZ RDV
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
        STA DIGIMG3         ; (заполняем от DIG0 к DIG3 - ранний выход
        STA DIGIMG2         ; по счётчику тетрад)
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
MAIN2:  XRA A
        OUT SEGP            ; дисплей погашен (после сброса горело "8.")
        OUT DIGP            ; разряды off, SND off
        OUT KBCOLP          ; колонки off (безопасный INIT)
        STA SNDST
        STA ADCNT
        STA BDCNT
        STA DPIDX
        STA STATE           ; ST_MENU
        CALL REDRAW         ; "APE_"

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
        JMP NKEY
WDN:    LXI D,SET_MS        ; счётчик В DE (QUNIT->REFRESH портит HL)
ST1:    CALL QUNIT
        DCX D
        MOV A,D
        ORA E
        JNZ ST1
        JMP SCAN

; ---------------------------------------------------------------------
; DISPATCH: обработка кода клавиши (A). F1 - глобально в меню.
; Смены состояния подтверждаются тиком; K_IGN - молча.
; ---------------------------------------------------------------------
DISPATCH: MOV C,A           ; C = КОД КЛАВИШИ (LDA STATE затирает A!)
        CPI K_F1
        JZ K_F1E
        LDA STATE
        ORA A
        JZ DSM
        CPI 01h
        JZ DSA
        CPI 02h
        JZ DSP
        ; ================= ST_VIEW =================
DSV:    MOV A,C             ; вернули код клавиши
        CPI K_ENT
        JZ VENT
        RET                 ; тетрады/F2 - игнор (режим только чтение)
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
        RET                 ; F2 и пр. - игнор
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
        STA BDCNT           ; поле гасится - ждём следующий байт
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
        ; ждём отпускания всех клавиш + дебаунс (иначе поймали бы
        ; ещё прижатую клавишу immediately после возврата)
MNR1:   CALL SCANALL
        ANI 1Fh
        JZ MNR2
        CALL REFRESH
        JMP MNR1
MNR2:   LXI D,SET_MS        ; счётчик В DE (QUNIT->REFRESH портит HL)
MNR3:   CALL QUNIT
        DCX D
        MOV A,D
        ORA E
        JNZ MNR3
        JMP MAIN2           ; реинициализация, ADDR сохранён

        END
