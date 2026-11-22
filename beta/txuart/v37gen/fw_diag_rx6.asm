; =====================================================================
; beta/txuart/v37gen -- fw_diag_rx5: ИЗМЕРИТЕЛЬ ФАКТИЧЕСКОЙ СКОРОСТИ RX.
; Плата retro_pcld (CPLD v37G01), CPU 8085 @3,125 МГц.
;
;   ИСТОРИЯ: rx4 показал на '5'/':'/'A'/'0' = 009E и на 'U' = 009F:
;   байт 00h (ВСЕ 8 выборок низко) и стоп низкий -> после пойманного
;   фронта линия низкая >= 2 мс. Честный 4800-'5' дал бы 359F.
;   RTL v37G01: assign SID = RX - чистый транзит CH340G.TXD, без
;   вентилей/растяжителей -> всё, что видит rx5, идёт с линии CH340.
;   Вывод: линия НЕ несёт 4800-кадры набираемых символов (в эпоху
;   diag_ph несла: W=0F был честный 1-битный низ). Кто виноват -
;   скорость терминала, CH340 или уровни - покажет ИЗМЕРЕНИЕ ШИРИНЫ.
;
;   ДИСПЛЕЙ: DIG3-2 = ширина ПЕРВОГО низа после фронта (W, ед. ~12 мкс)
;   или принятый байт; DIG1-0 = код режима:
;       9F/9E - ДЕКОД 4800: W был 06..13h (1-битный низ ~4800), байт
;               декодирован от исходного фронта (d0 на 1.5 бита);
;               байт на DIG3-2. 9F = стоп высокий, 9E = низкий.
;       24    - W=14h..37h (~170-410 мкс): 1 бит на 2400 ИЛИ ~2 бита 4800
;       12    - W=38h..6Fh (~420-830 мкс): 1 бит на 1200 ИЛИ ~2 бита 2400
;       06    - W=70h..DEh (~0.84-1.65 мс): 1 бит на 600 ИЛИ ~9 бит 4800
;       03    - W=DFh..FEh (~1.7-3.0 мс): 1 бит на 300
;       EE    - W>=FF (низ >= ~3 мс): 300 бод и медленнее, ИЛИ разрыв
;       FF    - глитч (низ < 6 ед. < ~70 мкс) или вход по фронту ВВЕРХ
;   КАЛИБРОВКА декода: точна при W=0Fh..11h (честный 4800, d0 на
;   1.49-1.55 бита); при иных W декод приблизителен.
;
;   ПРОЦЕДУРА: терминал "4800 8N1" (проверить настройку!), набрать '5'
;   несколько раз, затем ':' несколько раз, записать ВСЕ показания.
;   Таблица выводов - в сообщении к этой прошивке.
;
;   ПОРТЫ: 00h сегменты (D0=a..D6=g), 01h разряды D3-D0 + D4 SND.
;   RAM: PREV=FFE8, D1B=FFE9, D2B=FFEA. SP=FFE7. Прерываний нет.
;   Выход - RESET.
; =====================================================================

SEGP    EQU 00h
DIGP    EQU 01h

PREV    EQU 0FFE8h          ; предыдущий уровень SID (00h/80h)
D1B     EQU 0FFE9h          ; DIG3-2: ширина W или байт
D2B     EQU 0FFEAh          ; DIG1-0: код (9F/9E/24/12/06/03/EE/FF)

        ORG 0000h
        JMP START

        ORG 0008h
        RET
        ORG 0010h
        RET
        ORG 0018h
        RET
        ORG 0020h
        RET
        ORG 0024h
        RET
        ORG 0028h
        RET
        ORG 0030h
        RET
        ORG 0038h
        RET
        ORG 003Ch
        RET

; ---------------------------------------------------------------------
        ORG 0040h
START:  LXI SP,0FFE7h
        XRA A
        OUT SEGP
        OUT DIGP
        STA D1B             ; 0000 - измерений не было
        STA D2B
        RIM
        ANI 80h
        STA PREV            ; без фантомного фронта

; ---- развёртка 4 разрядов, в паузах - опрос SID ----
MAIN:   LDA D1B
        MOV B,A
        CALL GNIBH
        MVI B,08h           ; DIG3 = D1B старшая
        CALL SLOT
        JC  MEAS
        LDA D1B
        MOV B,A
        CALL GNIBL
        MVI B,04h           ; DIG2 = D1B младшая
        CALL SLOT
        JC  MEAS
        LDA D2B
        MOV B,A
        CALL GNIBH
        MVI B,02h           ; DIG1 = D2B старшая
        CALL SLOT
        JC  MEAS
        LDA D2B
        MOV B,A
        CALL GNIBL
        MVI B,01h           ; DIG0 = D2B младшая
        CALL SLOT
        JC  MEAS
        JMP MAIN

; ---------------------------------------------------------------------
; SLOT: глиф (A) на разряд (B) ~3 мс, всю паузу опрос SID (итерация
; ~38T, PREV кэшируется в E). Любая смена уровня -> CY=1, ранний выход.
SLOT:   OUT SEGP
        MOV A,B
        OUT DIGP
        MVI D,0C8h
        LDA PREV
        MOV E,A
SLOT1:  RIM
        ANI 80h
        MOV C,A
        MOV A,E
        CMP C
        JZ  SLOT2
        MOV A,C
        STA PREV
        MOV E,A
        JC  SLOT2           ; рост (0->1) - тоже выход
        STC                 ; падение (1->0) - старт-кандидат
        RET
SLOT2:  DCR D
        JNZ SLOT1
        XRA A
        RET

; ---------------------------------------------------------------------
; MEAS: измерить ширину низа (WLP, ед. ~12 мкс), классифицировать,
; при 1-битном ~4800-низе - декодировать байт от исходного фронта.
MEAS:   MVI A,80h
        STA PREV            ; низ должен кончиться
        MVI C,00h
WLP:    RIM
        ORA A
        JM  WEND            ; высокий - низ кончился
        INR C
        JZ  WOVF            ; >= ~3 мс - переполнение
        JMP WLP
WEND:   MOV A,C
        CPI 06h
        JC  GLIT            ; 0..5 - глитч или фронт вверх
        CPI 14h
        JC  DEC480          ; 06..13h - 1-битный низ ~4800: декод
        CPI 38h
        MVI B,24h
        JC  STW             ; 14h..37h
        CPI 70h
        MVI B,12h
        JC  STW             ; 38h..6Fh
        CPI 0DFh
        MVI B,06h
        JC  STW             ; 70h..DEh
        MVI B,03h           ; DFh..FEh
STW:    MOV A,C
        STA D1B             ; DIG3-2 = сырая ширина W
        MOV A,B
        STA D2B             ; DIG1-0 = код скорости
        JMP MEND
GLIT:   MOV A,C
        STA D1B
        MVI A,0FFh
        STA D2B
        JMP MEND
WOVF:   MVI A,0EEh
        STA D1B
        STA D2B
        JMP MEND

; ---------------------------------------------------------------------
; DEC480: W=06..13h, линия уже высокая (низ кончился). Точка входа =
; ~110T + W*37..38T от фронта (для W=0Fh..11h это ~1.03-1.08 бита).
; Цель: d0 на 1.5 бита = 977T. DLAY(16)=264T -> d0 на 966-1003T =
; 1.49-1.54 бита. Дальше цикл выборок = RXD монитора v2.0.4 (DLAY(38)).
DEC480: MVI D,10h
        CALL DLAY
        MVI B,08h
        MVI C,00h
RXL5:   RIM
        ANI 80h
        RLC                 ; ФИКС rx6: было RAR (CY<-A0=0, бит SID
                            ; терялся, C=00h всегда). RLC: CY<-A7=SID
        MOV A,C
        RAR                 ; биты в C, LSB-first
        MOV C,A
        MVI D,26h
        CALL DLAY
        DCR B
        JNZ RXL5
        RIM                 ; центр стоп-бита
        ANI 80h
        MVI A,9Eh
        JZ  STB
        MVI A,9Fh
STB:    STA D2B
        MOV A,C
        STA D1B             ; DIG3-2 = принятый байт
MEND:   RIM                 ; PREV = фактический уровень
        ANI 80h
        STA PREV
        JMP MAIN

; ---------------------------------------------------------------------
; DLAY: (34 + 14*n)T по модели автора, фактически 15n+24T c CALL/RET
; = 4,8n+7,7 мкс. Вход D = n (>=1).
DLAY:   DCR D
        JNZ DLAY
        RET

; GNIBH/GNIBL: байт в B -> A = глиф тетрады. Сохраняет B/C.
GNIBH:  MOV A,B
        RRC
        RRC
        RRC
        RRC
        ANI 0Fh
        JMP GNIBC
GNIBL:  MOV A,B
        ANI 0Fh
GNIBC:  MOV E,A
        MVI D,00h
        LXI H,GTBL
        DAD D
        MOV A,M
        RET

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
