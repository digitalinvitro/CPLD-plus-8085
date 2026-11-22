; =====================================================================
; beta/txuart/v37gen -- fw_diag_ph: ДИАГНОСТИКА RX v3 = НАБЛЮДАТЕЛЬ ФАЗ.
; Плата retro_pcld (CPLD v37G01), CPU 8085 @3,125 МГц.
;
;   ИСТОРИЯ: v1 (счёт фронтов) доказал - на SID приходят ЧИСТЫЕ кадры
;   (+3/+3 на символ). v2 (автобод+декод) показал: ширина старт-бита
;   ЧЕСТНАЯ 4800 (W=10h/0Fh), но байтовое поле НИКОГДА не обновляется.
;   Цикл-точная симуляция v2 говорит: декод ОБЯЗАН завершиться (стором
;   мусора или 'EE') - на железо это не доходит. ГДЕ рвётся - неясно.
;   v3 показывает это прямо на дисплее.
;
;   ДИСПЛЕЙ: DIG3-2 = W (ширина старт-бита, как v2), DIG1-0 = ФАЗА
;   последней попытки декода:
;       00 - попытка началась, но ни один масштаб задержки не подтвердил
;            старт-бит (все 4 подтверд reading HIGH - ложные старты)
;       01..04 - подтверждение ПРОШЛО на масштабе N (см. ниже)
;       9F     - выборки завершены, стоп-бит = 1 (успех - байт бы записан)
;       9E     - выборки завершены, стоп-бит = 0 (обрыв кадра, 'EE' в v2)
;   МАСШТАБЫ (idx 1..4): полубит-задержка = C>>idx, где C = полный бит
;   (4800 -> C=44 ед. DLAY): idx1 = DLAY(22) ~110 мкс (номинал),
;   idx2 = DLAY(11), idx3 = DLAY(5), idx4 = DLAY(2). Последовательность
;   22->11->5->2: первый масштаб, при котором контрольная выборка после
;   падения читает НИЗ, фиксируется в фазе. ЕСЛИ DLAY на железе работает
;   в 2 раза медленнее модели - idx1 промахнётся мимо бита, idx2
;   подтвердит -> фаза 02 укажет двукратный замедление. И т.д.
;   Выборки после подтверждения идут с полным битом = 2*(C>>idx) - тем
;   же масштабом. Поэтому 91..94 = цикл выборок ДОШЁЛ до конца.
;
;   КАК ТЕСТИРОВАТЬ: терминал 4800 8N1, набирать '5' или 'U' (0x35/0x55
;   - одиночные нулевые биты: D0=1, изолированные D1=0/D3=0 - чистый
;   тест). Писать в ответ ЧТО показала фаза.
;   Фильтр глитчей: ширина < 6 ед. (~70 мкс) игнорируется целиком и НЕ
;   портит MINW (в v2 короткий низ навсегда занижал минимум - "0600").
;
;   ПОРТЫ: 00h сегменты (D0=a..D6=g), 01h разряды D3-D0 + D4 SND.
;   RAM: PREV=FFE8, MINW=FFE9, WGLH=FFEA, WGLL=FFEB, PH=FFECh.
;   SP=FFE7. Прерываний нет. Выход - RESET, потом вернуть монитор.
; =====================================================================

SEGP    EQU 00h
DIGP    EQU 01h

PREV    EQU 0FFE8h          ; предыдущий уровень SID (00h/80h)
MINW    EQU 0FFE9h          ; ширина старт-бита (ед. ~11,8 мкс), FF = не мерили
WGLH    EQU 0FFEAh          ; глиф старшей тетрады W
WGLL    EQU 0FFEBh          ; глиф младшей тетрады W
PH      EQU 0FFECh          ; фаза последней попытки декода

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
        STA WGLH            ; W-глифы blank
        STA WGLL
        STA PH              ; фаза 00
        MVI A,0FFh
        STA MINW            ; ширина не измерена
        RIM
        ANI 80h
        STA PREV            ; без фантомного фронта

; ---- развёртка 4 разрядов, в паузах - опрос SID ----
MAIN:   LDA WGLH
        MVI B,08h           ; DIG3 = W старшая
        CALL SLOT
        JC  MEAS
        LDA WGLL
        MVI B,04h           ; DIG2 = W младшая
        CALL SLOT
        JC  MEAS
        LDA PH
        MOV B,A
        CALL GNIBH
        MVI B,02h           ; DIG1 = фаза старшая
        CALL SLOT
        JC  MEAS
        LDA PH
        MOV B,A
        CALL GNIBL
        MVI B,01h           ; DIG0 = фаза младшая
        CALL SLOT
        JC  MEAS
        JMP MAIN

; ---------------------------------------------------------------------
; SLOT: глиф (A) на разряд (B) ~3 мс, всю паузу опрос SID (итерация
; 39T, PREV кэшируется в E). Падающий фронт -> CY=1, ранний выход.
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
        JC  SLOT2
        STC
        RET
SLOT2:  DCR D
        JNZ SLOT1
        XRA A
        RET

; ---------------------------------------------------------------------
; MEAS: ширина низа, фильтр глитчей, минимум, классификация, попытка.
MEAS:   MVI C,00h
WLP:    RIM
        ORA A
        JM  WDONE
        INR C
        JZ  WOVF
        JMP WLP
WDONE:  MVI A,80h
        STA PREV
        MOV A,C             ; A = W
        CPI 06h             ; < 6 ед. (~70 мкс) - глитч, НЕ трогать MINW
        JC  MEASX
        LDA MINW
        CMP C               ; MINW < W? - кадр шире минимума, фаза сомнительна
        JC  MEASX
        MOV A,C
        STA MINW
        MOV B,A
        CALL GNIBH
        STA WGLH
        CALL GNIBL
        STA WGLL
        MOV A,B             ; классификация W
        CPI 0Eh             ; [6..13] - 9600
        JC  SP9600
        CPI 1Ch             ; [14..27] - 4800
        JC  SP4800
        CPI 38h             ; [28..55] - 2400
        JC  SP2400
        CPI 6Fh             ; [56..110] - 1200
        JC  SP1200
        JMP MEASX
SP9600: MVI C,15h
        JMP RXD3
SP4800: MVI C,2Ch
        JMP RXD3
SP2400: MVI C,5Ah
        JMP RXD3
SP1200: MVI C,0B7h
; ---------------------------------------------------------------------
; RXD3: попытка декода с ПЕРЕБОРОМ МАСШТАБА полубита.
; C = полный бит (ед. DLAY). idx = 1..4: полубит = C>>idx.
RXD3:   XRA A
        STA PH              ; фаза 00 на время попытки
        MVI H,00h           ; idx-1
IDLE3:  RIM                 ; дождаться idle-high
        ORA A
        JP  IDLE3
        MVI B,08h
RXW3:   RIM                 ; ждать падение (старт-бит или фронт внутри кадра)
        ORA A
        JM  RXW3
CONFSEQ:
        MOV A,C
        MOV E,A             ; E = база (полный бит)
        INR H               ; H = idx (1..4)
        MOV A,H
        MOV B,A             ; B = счётчик сдвигов
SHFLP:  MOV A,E
        RRC
        ANI 7Fh             ; RRC нечётных тянет A0 в A7 - маскировать
        MOV E,A
        DCR B
        JNZ SHFLP           ; E = полубит масштаба idx
        MOV A,E
        MOV D,A
        CALL DLAY
        RIM                 ; контрольная выборка: старт ещё низкий?
        ORA A
        JM  NXTDL           ; HIGH - ложный старт на этом масштабе
        MOV A,H
        STA PH              ; PH = idx - подтверждено на масштабе idx
        MOV A,E
        ADD A               ; полный бит = 2 x полубит
        MOV E,A
        MVI B,08h
        MOV A,E
        MOV D,A
        CALL DLAY           ; центр D0
RXL3:   RIM
        ANI 80h
        RAR
        MOV A,L
        RAR                 ; биты в L (не используется дальше - честный цикл)
        MOV L,A
        MOV A,E
        MOV D,A
        CALL DLAY
        DCR B
        JNZ RXL3
        RIM                 ; центр стоп-бита
        ANI 80h
        JZ  PHBAD
        MVI A,9Fh           ; выборки + стоп=1: полный успех
        STA PH
        JMP MEASX
PHBAD:  MVI A,9Eh           ; выборки + стоп=0: обрыв кадра
        STA PH
        JMP MEASX
NXTDL:  MOV A,H
        CPI 04h
        JZ  CONF0           ; все 4 масштаба дали HIGH
        JMP CONFSEQ
CONF0:  XRA A
        STA PH
        JMP MEASX
MEASX:  JMP MAIN

WOVF:   MVI A,80h
        STA PREV
        JMP MEASX

; ---------------------------------------------------------------------
; DLAY: (34 + 14*n)T = 10,9 + 4,48n мкс. Вход D = n (>=1).
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
