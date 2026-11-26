; =====================================================================
; fw_diag_v39_6tst v1.0 (11-26): ДИАГНОСТИКА v39G02 ПО ШАГАМ ВЛАДЕЛЬЦА.
; Бенч 11-26: "8888 после сброса, тактовая/противофаза/CLKOUT есть, ALE
; появляется ненадолго и пропадает". Разбор: 8888 = СБРОСОВОЕ состояние
; конвейера (Rseg=Rdig=0 -> пины 0) => ПЛАТА АКТИВ-НИЗКАЯ (пин=0 горит),
; DPOL=1 подтверждена железом. ALE пропадает = ЦП ОСТАНОВИЛСЯ (HLT/WAIT);
; READY=1'b1 держит CPLD - заливание в WAIT исключено; HLDA/борт без
; изменений (v2.0.7 на G07 работал). Претенденты: шторм RST7.5 (8.14 кГц),
; уход исполнения в данные ('v'=76h=HLT в текстах баннера), позднее железо.
; ЭТА ПРОШИВКА БИСЕКТИРУЕТ: DI + SIM 1Fh (все маски + СБРОС защёлки 7.5)
; ПЕРВОЙ инструкцией; EI ТОЛЬКО в тесте 6; HLT нигде нет - ALE живёт во
; всех петлях. Если ALE умрёт уже на тесте 1 - прерывания НЕ при чём.
; 1. ДИСПЛЕЙ : '8' на каждом разряде по 700 мс -> скан "8888" ~2 с
; 2. ЗВУК    : 3 бипа по 100 мс (SOD/SIM, C0h/40h, MSE=0)
; 3. КЛАВИАТ.: полный скан, код клавиши (0-F) на DIG0 + тик 30 мс;
;              Enter -> шаг 4; нет клавиш 10 с -> авто-дальше
; 4. UART TX : баннер "DIAG-4 TX OK" каждые 500 мс (poll D6)
; 5. UART RX : эхо FAST-пар 0xC0|nib -> TX, счётчик mod 16 на DIG0
; 6. ТАЙМЕР  : RST7.5 (8.14 кГц) - минимальный ISR (62T), DIG0 мигает
;              '8'/пусто с периодом ~1 с (H[3]); Enter -> 'F' и DI.
; СБОРКА: python3 ../rom/asm85.py fw_diag_v39_6tst.asm -o ... -D DPOL=1
; (дефолт бенч-подтверждён; DPOL=0 - для пин=1-горит плат).
; Примитивы (пары конвейера/TX/FAST-RX) верифицированы на цикломодели
; 16.19 (sim_fw_v3_check.py ALL OK) - у диага те же последовательности.
; =====================================================================
; ---- порты v39G02 (бит-декод, ТОЛЬКО канонические) ----
DISPP   EQU 01h             ; OUT: конвейер Rdig<-Rseg<-BUS (пара OUT)
TXP     EQU 02h             ; OUT: TXDATA 1.0417М 8N1
KBCOLP  EQU 08h             ; OUT: AD[7:4] = колонки
KBROWP  EQU 01h             ; IN: D7=1, D6=tx_idle, D5=rx_ready, D4-D0=rows
RXP     EQU 00h             ; IN: RXDATA = (байт&7F)<<1, чтение снимает ready
; ---- константы ----
K_MS    EQU 130             ; DLMS ~1 мс (130 x 25T x 320 нс)
K_ENT   EQU 10h             ; код клавиши Enter
; ---- RAM диага (стек растёт вниз от FFE7) ----
TICKL   EQU 0FFE8h          ; счётчик тиков (ISR)
TICKH   EQU 0FFE9h
T1CL    EQU 0FFEBh          ; счётчик кадров скана шага 1
T1CH    EQU 0FFECh
T3CL    EQU 0FFEDh          ; счётчик таймаута шага 3
T3CH    EQU 0FFEEh
T5C     EQU 0FFEFh          ; счётчик принятых байтов шага 5
T6P     EQU 0FFF0h          ; прошлое состояние мигания

; =====================================================================
        ORG 0000h
        DI                  ; ПЕРВАЯ инструкция: прерывания запрещены
        MVI A,01Fh          ; MSE=1: маски 5.5/6.5/7.5=1 + СБРОС защёлки 7.5
        SIM
        LXI SP,0FFE8h
        CALL DISPOFF        ; гашение парой (после сброса горело 8888)
        JMP T1

; =====================================================================
; RST 7.5 (003Ch): минимальный ISR 62T - только счётчик тиков.
; =====================================================================
        ORG 003Ch
        PUSH PSW
        LDA TICKL
        INR A
        STA TICKL
        JNZ T6I
        LDA TICKH
        INR A
        STA TICKH
T6I:    POP PSW
        EI
        RET

; ---------------------------------------------------------------------
; DISPOFF: погасить дисплей парой OUT. DPOL=1 (пин=0 горит): маска 00 ->
; пины разрядов F (никто не выбран), сегмент 00 -> пины 7F (все off).
; ---------------------------------------------------------------------
DISPOFF:
IF DPOL
        XRA A
        OUT DISPP
        OUT DISPP
ELSE
        MVI A,00Fh
        OUT DISPP
        MVI A,07Fh
        OUT DISPP
ENDIF
        RET

; ---------------------------------------------------------------------
; BLK0: пусто на DIG0 парой (маска DIG0 активна, сегменты все off).
; ---------------------------------------------------------------------
BLK0:   IF DPOL
        MVI A,001h          ; маска DIG0 (пин=0 = выбран)
        OUT DISPP
        XRA A               ; глиф 00 -> пины 7F = все off
        OUT DISPP
ELSE
        MVI A,00Eh
        OUT DISPP
        MVI A,07Fh
        OUT DISPP
ENDIF
        RET

; ---------------------------------------------------------------------
; GLOOK: A = тетрада 0..F -> A = глиф (GTBL, уже с полярностью DPOL).
; ---------------------------------------------------------------------
GLOOK:  MOV C,A
        MVI B,0
        LXI H,GTBL
        DAD B
        MOV A,M
        RET

; ---------------------------------------------------------------------
; SHOW: D = индекс разряда 0..3 (DIG0 правый), A = глиф -> ПАРА OUT.
; Портит D/E (вход D одноразовый).
; ---------------------------------------------------------------------
SHOW:   PUSH B
        MOV B,A             ; B = глиф
        MOV A,D
        MOV E,A
        MVI D,0
        LXI H,BITTBL
        DAD D
        MOV A,M             ; A = маска разряда (с DPOL)
        OUT DISPP           ; (1) маска
        MOV A,B
        OUT DISPP           ; (2) глиф: пара готова
        POP B
        RET

; ---------------------------------------------------------------------
; DLMS: ~1 мс (CPU-цикл, от прерываний не зависит). DLMSN: B = мс.
; PAUS: ~200 мкс. Портят B/C.
; ---------------------------------------------------------------------
DLMS:   LXI B,K_MS
DLS1:   DCX B
        MOV A,B
        ORA C
        JNZ DLS1
        RET
DLMSN:  PUSH B
DLN1:   PUSH B
        CALL DLMS
        POP B
        DCR B
        JNZ DLN1
        POP B
        RET
PAUS:   LXI B,25
PL1:    DCX B
        MOV A,B
        ORA C
        JNZ PL1
        RET

; ---------------------------------------------------------------------
; TXBYTE: A = байт -> poll tx_idle (D6) -> OUT TXP (1.0417М 8N1).
; ---------------------------------------------------------------------
TXBYTE: PUSH B
        MOV C,A
TXB1:   IN KBROWP
        ANI 040h            ; tx_idle (D6, v39G02)
        JZ TXB1
        MOV A,C
        OUT TXP
        POP B
        RET

; ---------------------------------------------------------------------
; TXS: HL = строка (0-терминатор) -> TX. Портит A/H/L.
; ---------------------------------------------------------------------
TXS:    MOV A,M
        ORA A
        RZ
        CALL TXBYTE
        INX H
        JMP TXS

; ---------------------------------------------------------------------
; GETBF: FAST-приём байта из пары 0xC0|nib (CPLD RXUART 2.083М).
; C = ASCII-байт. Poll rx_ready (D5) -> IN RXP -> nib=(rx>>1)&0F.
; ---------------------------------------------------------------------
GETBF:  MVI B,002h
GF1:    IN KBROWP
        ANI 020h
        JZ GF1
        IN RXP
        RRC
        ANI 00Fh
        RLC
        RLC
        RLC
        RLC
        MOV C,A
GF2:    IN KBROWP
        ANI 020h
        JZ GF2
        IN RXP
        RRC
        ANI 00Fh
        ORA C
        MOV C,A
        RET

; ---------------------------------------------------------------------
; SETTLE: ~26 мкс (заведение рядов). SCAN1: полный скан 4 колонок;
; A = код клавиши (KEYTBL) или FF. Портит A/B/C/D/H/L.
; ---------------------------------------------------------------------
SETTLE: LXI B,3
STL:    DCX B
        MOV A,B
        ORA C
        JNZ STL
        RET
SCAN1:  MVI C,0
SC1:    MVI B,0
        LXI H,BITTBL
        DAD B
        MOV D,M             ; бит колонки (01,02,04,08 - с DPOL)
        MOV A,D
        RLC
        RLC
        RLC
        RLC                 ; бит колонки -> старший ниббл
        OUT KBCOLP          ; колонка заведена
        CALL SETTLE
        IN KBROWP
        ANI 01Fh            ; ряды
        MOV B,A
        XRA A
        OUT KBCOLP          ; колонка off
        MOV A,B
        ORA A
        JZ SCNC
        MVI D,0
SC2:    MOV A,B
        RRC
        MOV B,A
        JC SC3
        INR D
        JMP SC2
SC3:    MOV A,D
        RLC
        RLC
        ORA C
        MOV C,A
        MVI B,0
        LXI H,KEYTBL
        DAD B
        MOV A,M
        CPI 0FFh
        RZ
        RET
SCNC:   INR C
        MOV A,C
        CPI 4
        JZ SCX
        JMP SC1
SCX:    MVI A,0FFh
        RET

; ---------------------------------------------------------------------
; TIK: короткий бип 30 мс (SOD/SIM). Портит A/D.
; ---------------------------------------------------------------------
TIK:    MVI A,0C0h          ; SDE=1, SOD=1, MSE=0 - маски целы
        SIM
        MVI B,30
        CALL DLMSN
        MVI A,040h          ; SOD=0
        SIM
        RET

; ---------------------------------------------------------------------
; NUM3: A = номер шага 0..F -> 'F'-глиф на DIG3 (индикация шага).
; ---------------------------------------------------------------------
NUM3:   CALL GLOOK
        MVI D,3
        JMP SHOW            ; хвост: (D=3, A=глиф)

; =====================================================================
; ШАГ 1: ТЕСТ ДИСПЛЕЯ. '8' на каждом разряде по 700 мс (видно каждый),
; затем программный скан "8888" ~2 с (кадр ~900 мкс, 1.1 кГц).
; Всё статикой/сканом CPU, прерываний нет - ALE живёт.
; =====================================================================
T1:     MVI A,1
        CALL NUM3           ; '1' на DIG3
        MVI D,0
T1L:    MVI A,8
        CALL GLOOK          ; глиф '8' (все сегменты)
        CALL SHOW           ; '8' на разряде D (портит D/E!)
        MVI E,7             ; 7 x 100 мс = 700 мс
T1W:    MVI B,100
        CALL DLMSN
        DCR E
        JNZ T1W
        INR D
        MOV A,D
        CPI 4
        JZ T1B
        JMP T1L
T1B:    XRA A               ; --- скан "8888" ~2 с ---
        STA T1CL
        STA T1CH
T1S:    MVI D,0
T1C:    MVI A,8
        CALL GLOOK
        CALL SHOW
        CALL PAUS           ; ~200 мкс на разряд
        INR D
        MOV A,D
        CPI 4
        JNZ T1C
        LDA T1CL            ; счётчик кадров (16 бит)
        INR A
        STA T1CL
        JNZ T1S
        LDA T1CH
        INR A
        STA T1CH
        CPI 9               ; ~9x256 кадров x 0.9 мс = ~2.1 с
        JC T1S
        JMP T2

; =====================================================================
; ШАГ 2: ТЕСТ ЗВУКА. '2' на DIG3, 3 бипа по 100 мс (SOD/SIM).
; =====================================================================
T2:     MVI A,2
        CALL NUM3
        MVI E,6             ; 6 x 100 мс = 600 мс пауза перед бипами
T2W:    MVI B,100
        CALL DLMSN
        DCR E
        JNZ T2W
        MVI E,3
T2L:    MVI A,0C0h          ; SOD=1 (SDE=1, MSE=0)
        SIM
        MVI B,100
        CALL DLMSN
        MVI A,040h          ; SOD=0
        SIM
        MVI B,100
        CALL DLMSN
        DCR E
        JNZ T2L
        MVI E,4             ; 4 x 100 мс пауза перед шагом 3
T2X:    MVI B,100
        CALL DLMSN
        DCR E
        JNZ T2X
        JMP T3

; =====================================================================
; ШАГ 3: ТЕСТ КЛАВИАТУРЫ. '3' на DIG3; код клавиши (0-F) на DIG0 + тик;
; Enter -> шаг 4; 10 с без клавиш -> авто-дальше.
; =====================================================================
T3:     MVI A,3
        CALL NUM3
        XRA A
        STA T3CL
        STA T3CH
T3L:    CALL SCAN1
        CPI 0FFh
        JZ T3T              ; пусто - тик таймаута
        CPI 10h
        JZ T4               ; Enter - дальше
        CALL GLOOK          ; глиф кода клавиши (0..F)
        MVI D,0
        CALL SHOW           ; код на DIG0
        CALL TIK            ; подтверждение бипом
T3T:    MVI B,20            ; 20 мс тик
        CALL DLMSN
        LDA T3CL
        INR A
        STA T3CL
        JNZ T3L
        LDA T3CH
        INR A
        STA T3CH
        CPI 2               ; 512 x 20.5 мс = ~10.5 с
        JNZ T3L
        JMP T4              ; таймаут: клавиатура мертва - идём дальше

; =====================================================================
; ШАГ 4: ТЕСТ ПЕРЕДАЧИ UART. '4' на DIG3; баннер каждые 500 мс;
; терминал 1000000 8N1. Enter -> шаг 5.
; =====================================================================
S_B4:   DB 'DIAG-4 TX OK',0Dh,0Ah,00h
T4:     MVI A,4
        CALL NUM3
        LXI H,S_B4
        CALL TXS
T4L:    MVI E,5             ; 5 x 100 мс = 500 мс между баннерами
T4W:    MVI B,100
        CALL DLMSN
        DCR E
        JNZ T4W
        CALL SCAN1
        CPI 10h
        JZ T5
        LXI H,S_B4
        CALL TXS
        JMP T4L

; =====================================================================
; ШАГ 5: ТЕСТ ПРИЁМА UART. '5' на DIG3; эхо FAST-байта -> TX,
; счётчик mod 16 на DIG0. Пир: fw_load_fast.ps1 (пары 0xC0|nib).
; Enter -> шаг 6.
; =====================================================================
S_B5:   DB 'DIAG-5 RX ECHO',0Dh,0Ah,00h
T5:     MVI A,5
        CALL NUM3
        LXI H,S_B5
        CALL TXS
        XRA A
        STA T5C
T5L:    CALL GETBF          ; C = принятый ASCII-байт
        MOV A,C
        CALL TXBYTE         ; ЭХО -> терминал
        LDA T5C             ; счётчик mod 16 на DIG0
        INR A
        STA T5C
        ANI 00Fh
        CALL GLOOK
        MVI D,0
        CALL SHOW
        CALL SCAN1
        CPI 10h
        JZ T6
        JMP T5L

; =====================================================================
; ШАГ 6: ТЕСТ ИНТЕРВАЛЬНОГО ТАЙМЕРА. ЕДИНСТВЕННОЕ место с EI: RST7.5
; (tmr_cnt[6], фронт раз в 122.88 мкс) -> минимальный ISR (62T) тикает
; 16-бит счётчик; DIG0 мигает '8'/пусто с периодом ~0.5 с (H[3]:
; тоггл каждые 8 инкр H = 251 мс). Enter -> DI + 'F' на DIG3.
; =====================================================================
T6:     MVI A,6
        CALL NUM3
        XRA A
        STA TICKL
        STA TICKH
        STA T6P
        MVI A,8
        CALL GLOOK
        MVI D,0
        CALL SHOW           ; '8' на DIG0 - стартовое состояние
        MVI A,03Bh          ; MSE=1: 5.5/6.5 маскированы, 7.5 СНЯТ,
        SIM                 ;  защёлка 7.5 сброшена
        EI                  ; ЕДИНСТВЕННЫЙ EI диага
T6L:    LDA TICKH
        ANI 008h            ; H[3] - тоггл ~0.5 с
        MOV B,A
        LDA T6P
        CMP B
        JZ T6K
        MOV A,B
        STA T6P
        ORA A
        JZ T6Z              ; стал 0 - погасить DIG0
        MVI A,8
        CALL GLOOK
        MVI D,0
        CALL SHOW
        JMP T6K
T6Z:    CALL BLK0
T6K:    CALL SCAN1
        CPI 10h
        JZ T6X
        JMP T6L
T6X:    DI
        MVI A,01Fh          ; все маски + сброс защёлки
        SIM
FIN:    MVI A,0Fh
        CALL GLOOK
        MVI D,3
        CALL SHOW           ; 'F' на DIG3 - все шаги пройдены
FINL:   JMP FINL            ; idle без HLT - ALE живёт

; =====================================================================
; Таблицы (полярность DPOL: регистр v39 хранит ~AD; при DPOL=1 запись
; как есть - пин=0 горит; при DPOL=0 - инверсия 127-G / 15-M).
; =====================================================================
IF DPOL
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
ELSE
GTBL:   DB 127-3Fh
        DB 127-06h
        DB 127-5Bh
        DB 127-4Fh
        DB 127-66h
        DB 127-6Dh
        DB 127-7Dh
        DB 127-07h
        DB 127-7Fh
        DB 127-6Fh
        DB 127-77h
        DB 127-7Ch
        DB 127-39h
        DB 127-5Eh
        DB 127-79h
        DB 127-71h
ENDIF
IF DPOL
BITTBL: DB 01h,02h,04h,08h  ; маска выбранного разряда (пин=0 горит)
ELSE
BITTBL: DB 0Eh,0Dh,0Bh,07h
ENDIF
KEYTBL: DB 0Ah,0Bh,0Ch,0Dh  ; row0: A  B  C  D
        DB 07h,08h,09h,0Eh  ; row1: 7  8  9  E
        DB 04h,05h,06h,0Fh  ; row2: 4  5  6  F
        DB 01h,02h,03h,10h  ; row3: 1  2  3  Enter
        DB 00h,11h,12h,0FFh ; row4: 0  F1 F2 (нет)

        END
