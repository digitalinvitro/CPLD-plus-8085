; ======================================================================
;  GFXSTREAM v2.2 — ДЕМО: 160x100 1bpp, РЕАЛЬНЫЙ период 46.875 мс = 3 ТИКА
;  ПК (КАЛИБРОВКА по живому логу владельца 11-12: 2606 кадров/120.5 с,
;  10 обёрток SEQ: реальный период платы 46.348 мс = -1.124% от номинала
;  146 484T — сим считал такты по таблице 8085, реальный силикон быстрее;
;  пад-петля DCX/MOV/ORA/JNZ = 24T и на 8080A и на 8085 — нейтральна,
;  поэтому коррекция делается ДОБАВКОЙ ПАДА: +1644T = W_V2 2194->2262
;  (+1632T) + 3 NOP (+12T); РЕАЛЬНЫЙ период = 146 484T = 46.875 мс,
;  в СИМЕ период = 148 128T = 47.401 мс (сим-время ≠ реальному — задоку-
;  ментировано в sim_gfxstream_v2.py). TXSTRESS не тронут (69 770 Б/с
;  подтверждён при номинале — такт платы номинален, расхождение в СМЕСИ
;  инструкций; точный корень — отдельный эксперимент, не блокер).
;  Плата: retro PC (8085 + XC95108, TX-ядро v2.3, 1 000 000 бод 8N1)
;  CPU: 8085 @ 3.125 МГц, T = 320 нс; кадр 8N1 = 31.25T = 10 мкс.
;  База: gfxstream v1 (приёмка шага 3 закрыта 11-11-6, вьюер v1.4
;  заморожен md5 e3ab74ca). ФОРМАТ ПРОВОДА = v1 БЕЗ ИЗМЕНЕНИЙ:
;   A5 5A [TYPE] [N_LO] [N_HI] [SEQ] [payload], конверт = 2 006 Б;
;   TYPE 01: N=07D0h (2 000 Б = 100 строк x 20 Б, MSB = левый px);
;   TYPE 02: N=00CAh (202) = маска 13 Б + 9 x [номер строки][20 Б],
;   хвост конверта добит FFh (UART-idle, парсер ПК пропускает).
;   -> вьюер v1.4 работает БЕЗ ПРАВОК (N=202 сохранён во всех сценах).
;
;  ТРИ СЦЕНЫ (цикл 910 кадров = 36.4 с):
;   S0 БЫСТРЫЙ ШАР   250 кадров: шар 8 px x 7 строк, шаг dc=+-2 клетки
;                    (16 px/кадр), dr=+-2 строки; отскок flip-recompute
;                    от 0/19 (col) и 0/92 (row). Дельта = ровно 9 строк
;                    [min(r',r)..min+8] (7-row шар при шаге 2 -> те же
;                    9 строк, что в v1!) -> N=202 соблюдён. Кейфрейм
;                    TYPE 01 на входе в сцену и каждый 100-й кадр сцены.
;   S1 ДИТЕР-ВОЛНА   240 кадров: полные кадры; байт строки =
;                    DIT[(row + NEG16[t&15]) & 15] — 16-ступенчатый
;                    дизеринг-«занавес», волна плотности ползёт вниз
;                    1 строка/кадр. Демонстрация серой шкалы из 1bpp
;                    и полного темпа 50 150 Б/с (50% канала).
;   S2 БЕГУЩАЯ СТРОКА 420 кадров: вход = полный кадр (сетка + полоса
;                    текста), далее дельты строк 45..53 (9 строк!);
;                    битмап 48 символов x 8 строк в ОЗУ, сдвиг влево
;                    1 px/кадр (RLC-цепочка), окно 20 байт x 8 строк.
;
;  ГЕНЕРАЦИЯ: FB НЕ ИСПОЛЬЗУЕТСЯ — каждый кадр строится аналитически
;  и льётся в UART прямо из регистров (fusion генерация+посылка).
;  Такт посылки: OUT(10)+NOP(4)+NOP(4)+DCR(4)+JNZ(10) = 32T/байт
;  (>= 31.25T — ноль отбросов TX, режим доказан TXSTRESS на 100%),
;  либо LDAX-вариант 37T/байт. Период кадра = 125 000T: работа путей
;  выравнивается падами P_* (по одному на путь, калибровка по симу),
;  единый ожидатель W_V2. КАДРЫ СМЕНЫ СЦЕНЫ (3 шт. за цикл 910) несут
;  доп. работу смены состояния (+~250T) и копию битмапа строки
;  (+16.9kT на входе в S2) — задокументированное исключение, дисплеем
;  поглощается (гейт вьюера), в симе проверяются отдельно.
;
;  ОЗУ (8000h-FFFFh, 32 КБ): STATE 9800h..981Ch, MSKBF 9900h..990Ch
;  (маска дельты шара), MWORK A000h..A17Fh (битмап строки, 8x48),
;  MMASR A200h..A27Fh (мастер-копия). SP = FFF8h. Итого ~1.4 КБ (4.3%).
;
;  Порты: OUT 04h — данные TX.
;  Сборка: python3 asm8085.py gfxstream_v2.asm gfxstream_v2 > gfxstream_v2.lst
;  Проверка: scripts/sim_gfxstream_v2.py (исполнение hex + модель сцен
;  + побайтовая сверка + период 125 000T по путям + мин-гэп >= 32T).
; ======================================================================

TXPORT  EQU 004h

; ---- состояние (9800h..) ----
S_SEQ   EQU 9800h       ; SEQ кадров mod 256
S_DPH   EQU 9801h       ; счётчик кадров до кейфрейма (100)
S_C     EQU 9802h       ; шар: col 0..19 (чётные)
S_R     EQU 9803h       ; шар: row 0..92 (чётные)
S_DC    EQU 9804h       ; шаг col: 02h / FEh
S_DR    EQU 9805h       ; шаг row: 02h / FEh
S_PR    EQU 9806h       ; предыдущая row (для RMIN)
S_R6    EQU 9807h       ; S_R + 6 (нижняя строка шара)
S_RM    EQU 9808h       ; RMIN текущей дельты
S_SCENE EQU 9809h       ; сцена: 0 шар / 1 дитер / 2 строка
S_SW    EQU 980Ah       ; 1 = кадр входа в сцену (принудительный полный)
S_TL    EQU 980Bh       ; T счётчик кадров сцены (16 бит, lo)
S_TH    EQU 980Ch
S_LL    EQU 980Dh       ; предел сцены (16 бит)
S_LH    EQU 980Eh
S_DCNT  EQU 980Fh       ; счётчик строк дельты (9)
S_NEG   EQU 9810h       ; NEG16[t&15] текущего кадра дитера (alias S_K, init-скретч)
S_K     EQU 9810h       ; счётчик сборки битмапа (init)
S_HDRF  EQU 9811h       ; заголовок TYPE 01: A5 5A 01 D0 07 [SEQ]
S_HDRD  EQU 9817h       ; заголовок TYPE 02: A5 5A 02 CA 00 [SEQ]
MSKBF   EQU 9900h       ; маска дельты шара, 13 Б
MWORK   EQU A000h       ; битмап бегущей строки 8 x 48
MMASR   EQU A200h       ; мастер-копия битмапа

; ---- калибровка периода (по симу 11-11-7: работы путей BF 93.1k, BD 72.1k,
; DI 71.4k, MF 89.4k, MD 80.5k + W-часть 31.2k -> пады = (125000 - работа - 31236)/24)
W_V2    EQU 2262        ; единый ожидатель, 24T/итерация; КАЛИБРОВКА 11-12:
                        ; 2194->2262 (+1632T) + 3 NOP в хвосте WTAIL (+12T)
                        ; = +1644T -> РЕАЛЬНЫЙ период 46.875 мс = 3 тика
                        ; (в СИМЕ период = 148 128T = 47.401 мс)
P_H     EQU 46          ; пад головы: выравнивает головы BF/DI/MF под голову BD (маска)
P_BF    EQU 1           ; пад: шар, полный кадр
P_BD    EQU 1052        ; пад: шар, дельта
P_DI    EQU 760         ; пад: дитер-волна
P_MF    EQU 183         ; пад: строка, полный (вход)
P_MD    EQU 496         ; пад: строка, дельта

L_BALL  EQU 0FAh        ; длина сцены шара = 250
L_DIT   EQU 0F0h        ; длина сцены дитера = 240
L_MARL  EQU 0A4h        ; длина сцены строки = 420 = 01A4h (lo)
L_MARH  EQU 001h        ; (hi)
MSGN    EQU 030h        ; символов в строке = 48

        ORG 0000h
; ---------------------- сброс ----------------------
        DI
        LXI SP,FFF8h
        LXI D,0000h        ; пауза ~503 мс: POR CPLD (прецедент v1)
PORLP:  DCX D
        MOV A,D
        ORA E
        JNZ PORLP

; ---------------------- баннер ----------------------
        LXI H,M_BAN
PBAN:   MOV A,M
        ORA A
        JZ PBAND
        OUT TXPORT
        INX H
        JMP PBAN
PBAND:

; ---------------------- init ----------------------
; заголовки кадров
        LXI H,S_HDRF
        MVI A,0A5h
        MOV M,A
        INX H
        MVI A,05Ah
        MOV M,A
        INX H
        MVI A,001h
        MOV M,A
        INX H
        MVI A,0D0h
        MOV M,A
        INX H
        MVI A,007h
        MOV M,A
        INX H
        XRA A
        MOV M,A
        LXI H,S_HDRD
        MVI A,0A5h
        MOV M,A
        INX H
        MVI A,05Ah
        MOV M,A
        INX H
        MVI A,002h
        MOV M,A
        INX H
        MVI A,0CAh
        MOV M,A
        INX H
        XRA A
        MOV M,A
        INX H
        XRA A
        MOV M,A
; состояние: SEQ=FFh (первый INR -> 00h), шар (0,0) шаг +2/+2, сцена 0
        LXI H,S_SEQ
        MVI A,0FFh
        MOV M,A
        INX H              ; S_DPH
        XRA A
        MOV M,A
        INX H              ; S_C
        MOV M,A
        INX H              ; S_R
        MOV M,A
        INX H              ; S_DC
        MVI A,002h
        MOV M,A
        INX H              ; S_DR
        MOV M,A
        XRA A
        STA S_PR
        STA S_RM
        STA S_SCENE        ; сцена 0 = шар
        STA S_TL
        STA S_TH
        STA S_LH
        MVI A,001h         ; первый кадр = полный (вход в сцену)
        STA S_SW
        MVI A,L_BALL       ; предел сцены 0 = 250
        STA S_LL
; мастер-битмап строки: MMASR[r*48+k] = FONT[MSG[k]*8+r]
        XRA A
        STA S_K
MKLP:   LDA S_K
        MOV L,A
        MVI H,000h
        LXI D,MSG
        DAD D              ; HL = MSG + k
        MOV A,M            ; A = индекс глифа
        MOV L,A
        MVI H,000h
        DAD H
        DAD H
        DAD H              ; HL = idx*8
        LXI D,FONT
        DAD D              ; HL = FONT + idx*8
        XCHG               ; DE = глиф (цел до конца итерации)
        LDA S_K
        MOV C,A            ; C = k
        MVI B,000h
        LXI H,MMASR
        DAD B              ; HL = MMASR + k (DE не тронут)
        LXI B,0030h        ; BC = шаг строки 48
        LDAX D
        MOV M,A
        INX D
        DAD B
        LDAX D
        MOV M,A
        INX D
        DAD B
        LDAX D
        MOV M,A
        INX D
        DAD B
        LDAX D
        MOV M,A
        INX D
        DAD B
        LDAX D
        MOV M,A
        INX D
        DAD B
        LDAX D
        MOV M,A
        INX D
        DAD B
        LDAX D
        MOV M,A
        INX D
        DAD B
        LDAX D
        MOV M,A
        INX D
        DAD B
        LDA S_K
        INR A
        STA S_K
        CPI MSGN
        JNZ MKLP

; ===================== кадровый цикл =====================
FRAME:
; ---- 1. SEQ++ и в заголовки ----
        LXI H,S_SEQ
        INR M
        LDA S_SEQ
        STA S_HDRF+0005h
        STA S_HDRD+0005h

; ---- 2. смена сцены: T++; если T == предел -> switch ----
        LXI H,S_TL
        INR M
        JNZ TCHK
        INX H
        INR M
TCHK:   LDA S_LL
        MOV B,A
        LDA S_TL
        CMP B
        JNZ TNO
        LDA S_LH
        MOV B,A
        LDA S_TH
        CMP B
        JZ DOSW
TNO:
; ---- 3. диспетчер по сцене ----
        LDA S_SCENE
        ORA A
        JZ SC_BALL
        CPI 001h
        JZ SC_DIT
        JMP SC_MARQ

; ----- смена сцены: SCENE=(SCENE+1) mod 3, T=0, SW=1, пределы -----
DOSW:   LDA S_SCENE
        CPI 002h
        JZ DSWW
        INR A
        JMP DSWR
DSWW:   XRA A
DSWR:   STA S_SCENE
        MOV C,A            ; C = новая сцена
        XRA A
        STA S_TL
        STA S_TH
        MVI A,001h
        STA S_SW
        MOV A,C
        ORA A
        JZ DSWL0
        CPI 001h
        JZ DSWL1
        MVI A,L_MARL       ; сцена 2 (строка): 420
        STA S_LL
        MVI A,L_MARH
        STA S_LH
        ; копия мастера -> рабочую (384 Б)
        LXI B,0180h
        LXI H,MMASR
        LXI D,MWORK
DSWCP:  MOV A,M
        STAX D
        INX H
        INX D
        DCX B
        MOV A,B
        ORA C
        JNZ DSWCP
        JMP TNO2
DSWL0:  MVI A,L_BALL
        STA S_LL
        XRA A
        STA S_LH
        JMP TNO2
DSWL1:  MVI A,L_DIT
        STA S_LL
        XRA A
        STA S_LH
TNO2:
; ---- диспетчер (повтор после смены) ----
        LDA S_SCENE
        ORA A
        JZ SC_BALL
        CPI 001h
        JZ SC_DIT
        JMP SC_MARQ

; ======================================================================
;  СЦЕНА 0: БЫСТРЫЙ ШАР
; ======================================================================
SC_BALL:
; ---- модель шара: шаг +-2, отскок flip-recompute ----
        LDA S_DC
        MOV B,A            ; B = dc
        LDA S_C
        MOV C,A            ; C = c
        MOV A,C
        ADD B              ; A = c + dc
        CPI 014h           ; 20: CY=1 -> в диапазоне 0..19
        JC B_COK
        MOV A,B            ; dc = -dc
        CMA
        ADI 001h
        MOV B,A
        MOV A,C
        ADD B              ; пересчёт
B_COK:  MOV D,A            ; D = c'
        MOV A,B
        STA S_DC
        MOV A,D
        STA S_C
; строка
        LDA S_DR
        MOV B,A            ; B = dr
        LDA S_R
        MOV C,A            ; C = r
        MOV A,C
        ADD B
        CPI 05Dh           ; 93: CY=1 -> в диапазоне 0..92
        JC B_ROK
        MOV A,B
        CMA
        ADI 001h
        MOV B,A
        MOV A,C
        ADD B
B_ROK:  MOV D,A            ; D = r'
        MOV A,B
        STA S_DR
        MOV A,C
        STA S_PR           ; предыдущая строка
        MOV A,D
        STA S_R            ; новая строка
        ADI 007h
        STA S_R6           ; r' + 7 (эксклюзивная граница 7 строк шара)
; ---- полный или дельта: вход в сцену / DPH=100 -> полный ----
        LDA S_SW
        ORA A
        JZ B_NOSW
        XRA A
        STA S_SW
        JMP B_FULL
B_NOSW: LXI H,S_DPH
        INR M
        MOV A,M
        CPI 064h
        JC B_DELTA
        XRA A
        STA S_DPH
; ----- TYPE 01: полный кадр: 100 строк (сетка + шар) -----
B_FULL:
; пад головы (у головы BD строится маска ~1.1kT — выравниваем)
        LXI B,P_H
BHP:    DCX B
        MOV A,B
        ORA C
        JNZ BHP
        LXI D,S_HDRF
        MVI C,006h
BHD:    LDAX D
        OUT TXPORT
        INX D
        DCR C
        JNZ BHD
        XRA A
        MOV E,A            ; E = номер строки 0..99
BRL:    MOV A,E
        MOV C,A            ; C = rr
; тест шара, ПОСТОЯННАЯ цена: A = rr - r - 1 (mod 256); шар <=> FFh или 0..5
        LDA S_R
        CMA
        MOV B,A            ; B = ~r
        MOV A,C
        ADD B
        CPI 006h
        JC BBAL
        CPI 0FFh
        JZ BBAL
        MVI L,000h
        JMP BBK
BBAL:   MVI L,001h
BBK:
; байт сетки P
        MOV A,C
        ANI 007h
        JZ BPFF
        MOV A,C
        CPI 063h
        JZ BPFF
        MVI B,080h
        JMP BPOK
BPFF:   MVI B,0FFh
BPOK:
; часть 1: c байтов P
        LDA S_C
        MOV D,A
        ORA A
        JZ BSK1
        MOV A,B
BP1:    OUT TXPORT
        NOP
        NOP
        DCR D
        JNZ BP1
BSK1:
; байт шара
        MOV A,L
        ORA A
        JZ BSKB
        MVI A,0FFh
        OUT TXPORT
        NOP
        NOP
        NOP
BSKB:
; часть 2: (19-c) байтов P; на строках с шаром минус 1 (байт шара уже выдан)
        LDA S_C
        CMA
        ADI 001h
        ADI 013h      ; A = 19 - c
        MOV D,A
        MOV A,L
        ORA A
        JZ BSK2C
        DCR D         ; шар съел один байт части 2
BSK2C:  MOV A,D
        ORA A
        JZ BSK2
        MOV A,B
BP2:    OUT TXPORT
        NOP
        NOP
        DCR D
        JNZ BP2
BSK2:
; крайний байт (P | 01h); 3 NOP = гэп от последнего OUT части 2 >= 32T
        NOP
        NOP
        NOP
        MOV A,B
        ORI 001h
        OUT TXPORT
        NOP
        NOP
; следующая строка
        INR E
        MOV A,E
        CPI 064h
        JNZ BRL
; пад пути
        LXI B,P_BF
BPAD:   DCX B
        MOV A,B
        ORA C
        JNZ BPAD
        JMP WTAIL

; ----- TYPE 02: дельта 9 строк -----
B_DELTA:
; маска 13 Б в MSKBF: обнулить
        LXI H,MSKBF
        MVI B,00Dh
        XRA A
BZM:    MOV M,A
        INX H
        DCR B
        JNZ BZM
; RMIN = min(S_PR, S_R)
        LDA S_PR
        MOV B,A
        LDA S_R
        CMP B
        JNC BRM1
        JMP BRM2
BRM1:   MOV A,B
BRM2:   MOV C,A            ; C = RMIN
        STA S_RM
; байт маски: HL = MSKBF + (RMIN>>3)
        MOV A,C
        RRC
        RRC
        RRC
        ANI 01Fh
        MOV E,A
        MVI D,000h
        LXI H,MSKBF
        DAD D
; начальный бит = TBL[RMIN&7]
        MOV A,C
        ANI 007h
        MOV E,A
        MVI D,000h
        LXI H,TBL
        DAD D
        MOV B,M            ; B = бит (C = RMIN не тронут)
; указатель маски заново (HL испорчен выборкой TBL)
        MOV A,C
        RRC
        RRC
        RRC
        ANI 01Fh
        MOV E,A
        MVI D,000h
        LXI H,MSKBF
        DAD D
        MOV D,B            ; D = бит
; отметить 9 строк
        MVI B,009h
BWL:    MOV A,M
        ORA D
        MOV M,A
        MOV A,D
        RLC
        MOV D,A
        JNC BWNB
        MVI D,001h
        INX H
BWNB:   DCR B
        JNZ BWL
; заголовок дельты
        LXI D,S_HDRD
        MVI C,006h
BDH:    LDAX D
        OUT TXPORT
        INX D
        DCR C
        JNZ BDH
; маска 13 Б
        LXI D,MSKBF
        MVI C,00Dh
BDM:    LDAX D
        OUT TXPORT
        INX D
        DCR C
        JNZ BDM
; 9 строк: [номер][20 Б]
        LDA S_RM
        MOV E,A
        MVI A,009h
        STA S_DCNT
BDRL:   MOV A,E
        MOV C,A            ; C = rr
; тест шара, постоянная цена (как в B_FULL)
        LDA S_R
        CMA
        MOV B,A
        MOV A,C
        ADD B
        CPI 006h
        JC BDBAL
        CPI 0FFh
        JZ BDBAL
        MVI L,000h
        JMP BDBK
BDBAL:  MVI L,001h
BDBK:
; P для rr
        MOV A,C
        ANI 007h
        JZ BDPF
        MOV A,C
        CPI 063h
        JZ BDPF
        MVI B,080h
        JMP BDPO
BDPF:   MVI B,0FFh
BDPO:
; номер строки
        MOV A,E
        OUT TXPORT
        INR E
; часть 1
        LDA S_C
        MOV D,A
        ORA A
        JZ BDSK1
        MOV A,B
BDP1:   OUT TXPORT
        NOP
        NOP
        DCR D
        JNZ BDP1
BDSK1:
; байт шара
        MOV A,L
        ORA A
        JZ BDSKB
        MVI A,0FFh
        OUT TXPORT
        NOP
        NOP
        NOP
BDSKB:
; часть 2: (19-c) байтов P; на строках с шаром минус 1
        LDA S_C
        CMA
        ADI 001h
        ADI 013h      ; A = 19 - c
        MOV D,A
        MOV A,L
        ORA A
        JZ BDSK2C
        DCR D         ; шар съел один байт части 2
BDSK2C: MOV A,D
        ORA A
        JZ BDSK2
        MOV A,B
BDP2:   OUT TXPORT
        NOP
        NOP
        DCR D
        JNZ BDP2
BDSK2:
; крайний; 3 NOP = гэп от части 2 >= 32T
        NOP
        NOP
        NOP
        MOV A,B
        ORI 001h
        OUT TXPORT
        NOP
        NOP
        NOP
; следующая строка дельты
        LDA S_DCNT
        DCR A
        STA S_DCNT
        JNZ BDRL
; FF-добивка 1798 = 7*255 + 13
        MVI A,0FFh
        MVI B,007h
BPD7:   MVI D,0FFh
BPDI:   OUT TXPORT
        NOP
        NOP
        DCR D
        JNZ BPDI
        DCR B
        NOP
        JNZ BPD7
        MVI D,00Dh
BPDT:   OUT TXPORT
        NOP
        NOP
        DCR D
        JNZ BPDT
; пад пути
        LXI B,P_BD
BDPD:   DCX B
        MOV A,B
        ORA C
        JNZ BDPD
        JMP WTAIL

; ======================================================================
;  СЦЕНА 1: ДИТЕР-ВОЛНА (полные кадры)
; ======================================================================
SC_DIT:
; пад головы (как B_FULL)
        LXI B,P_H
DIHP:   DCX B
        MOV A,B
        ORA C
        JNZ DIHP
; заголовок
        LXI D,S_HDRF
        MVI C,006h
DIH:    LDAX D
        OUT TXPORT
        INX D
        DCR C
        JNZ DIH
; NEG16[t & 15] -> S_NEG (через DAD: адрес таблицы не кратен странице)
        LDA S_TL
        ANI 00Fh
        MOV C,A
        MVI B,000h
        LXI H,NEG16
        DAD B
        MOV A,M
        STA S_NEG
; 100 строк: байт = DIT[(rr + NEG) & 15]
        XRA A
        MOV E,A
DRL:    MOV A,E
        MOV C,A         ; C = rr
        LDA S_NEG       ; A = NEG (rr спасён в C)
        ADD C
        ANI 00Fh
        MOV C,A         ; C = idx
        MVI B,000h
        LXI H,DIT
        DAD B
        MOV A,M
        MVI D,014h
DLA:    OUT TXPORT
        NOP
        NOP
        DCR D
        JNZ DLA
        INR E
        MOV A,E
        CPI 064h
        JNZ DRL
; пад пути
        LXI B,P_DI
DIPD:   DCX B
        MOV A,B
        ORA C
        JNZ DIPD
        JMP WTAIL

; ======================================================================
;  СЦЕНА 2: БЕГУЩАЯ СТРОКА
; ======================================================================
SC_MARQ:
        LDA S_SW
        ORA A
        JZ M_DELTA
        XRA A
        STA S_SW
        JMP M_FULL

; ----- вход: полный кадр (сетка + полоса текста) -----
M_FULL:
; пад головы (как B_FULL)
        LXI B,P_H
MFHP:   DCX B
        MOV A,B
        ORA C
        JNZ MFHP
        LXI D,S_HDRF
        MVI C,006h
MFH:    LDAX D
        OUT TXPORT
        INX D
        DCR C
        JNZ MFH
; строки 0..45: сетка
        XRA A
        MOV E,A
MGL1:   MOV A,E
        MOV C,A
        MOV A,C
        ANI 007h
        JZ MPF1
        MOV A,C
        CPI 063h
        JZ MPF1
        MVI B,080h
        JMP MPO1
MPF1:   MVI B,0FFh
MPO1:   MOV A,B
        MVI D,013h
MPL1:   OUT TXPORT
        NOP
        NOP
        DCR D
        JNZ MPL1
        NOP
        NOP
        NOP
        MOV A,B
        ORI 001h
        OUT TXPORT
        NOP
        NOP
        INR E
        MOV A,E
        CPI 02Eh
        JNZ MGL1
; строки 46..53: полоса (строка i битмапа = MWORK + 48*i). Указатель в HL
; (пара DE занята E-счётчиком: INX D менял бы E!). Продвижение на 28 = INX H x28.
        LXI H,MWORK
        MVI E,008h
MBL:    MVI C,014h
MBLA:   MOV A,M
        OUT TXPORT
        INX H
        DCR C
        JNZ MBLA
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        DCR E
        JNZ MBL
; строки 54..99: сетка
        MVI E,036h
MGL2:   MOV A,E
        MOV C,A
        MOV A,C
        ANI 007h
        JZ MPF2
        MOV A,C
        CPI 063h
        JZ MPF2
        MVI B,080h
        JMP MPO2
MPF2:   MVI B,0FFh
MPO2:   MOV A,B
        MVI D,013h
MPL2:   OUT TXPORT
        NOP
        NOP
        DCR D
        JNZ MPL2
        NOP
        NOP
        NOP
        MOV A,B
        ORI 001h
        OUT TXPORT
        NOP
        NOP
        INR E
        MOV A,E
        CPI 064h
        JNZ MGL2
; пад пути
        LXI B,P_MF
MFPD:   DCX B
        MOV A,B
        ORA C
        JNZ MFPD
        JMP WTAIL

; ----- дельта: сдвиг битмапа + строки 45..53 -----
M_DELTA:
; сдвиг влево 1 px: 8 строк x 48 Б (RAR-цепочка по убыванию адресов,
; CY = бит0 соседа справа; RLC нельзя — это РОТАТ, не потребляет CY)
        LXI H,MWORK+002Fh
        ORA A
        MVI C,030h
MSL1:   MOV A,M
        RAR
        MOV M,A
        DCX H
        DCR C
        JNZ MSL1
        LXI H,MWORK+005Fh
        ORA A
        MVI C,030h
MSL2:   MOV A,M
        RAR
        MOV M,A
        DCX H
        DCR C
        JNZ MSL2
        LXI H,MWORK+008Fh
        ORA A
        MVI C,030h
MSL3:   MOV A,M
        RAR
        MOV M,A
        DCX H
        DCR C
        JNZ MSL3
        LXI H,MWORK+00BFh
        ORA A
        MVI C,030h
MSL4:   MOV A,M
        RAR
        MOV M,A
        DCX H
        DCR C
        JNZ MSL4
        LXI H,MWORK+00EFh
        ORA A
        MVI C,030h
MSL5:   MOV A,M
        RAR
        MOV M,A
        DCX H
        DCR C
        JNZ MSL5
        LXI H,MWORK+011Fh
        ORA A
        MVI C,030h
MSL6:   MOV A,M
        RAR
        MOV M,A
        DCX H
        DCR C
        JNZ MSL6
        LXI H,MWORK+014Fh
        ORA A
        MVI C,030h
MSL7:   MOV A,M
        RAR
        MOV M,A
        DCX H
        DCR C
        JNZ MSL7
        LXI H,MWORK+017Fh
        ORA A
        MVI C,030h
MSL8:   MOV A,M
        RAR
        MOV M,A
        DCX H
        DCR C
        JNZ MSL8
; заголовок дельты
        LXI D,S_HDRD
        MVI C,006h
MDH:    LDAX D
        OUT TXPORT
        INX D
        DCR C
        JNZ MDH
; фиксированная маска 13 Б (строки 45..53)
        LXI D,MMASK
        MVI C,00Dh
MDM:    LDAX D
        OUT TXPORT
        INX D
        DCR C
        JNZ MDM
; строка 45 (сетка, P=80h); 2 NOP = гэп от маски, 3 NOP = от номера строки
        NOP
        NOP
        MVI A,02Dh
        OUT TXPORT
        NOP
        NOP
        NOP
        MVI B,080h
        MVI D,013h
        MOV A,B
MD45:   OUT TXPORT
        NOP
        NOP
        DCR D
        JNZ MD45
        NOP
        NOP
        NOP
        MOV A,B
        ORI 001h
        OUT TXPORT
        NOP
        NOP
; строки 46..53: полоса (строка i = MWORK + 48*i) + номера строк.
; Указатель в HL (E = номер строки: INX D менял бы его!)
        MVI E,02Eh
        LXI H,MWORK
MDBL:   MOV A,E          ; номер строки 46+i
        OUT TXPORT
        NOP
        NOP
        NOP
        NOP
        INR E
        MVI C,014h
MDBA:   MOV A,M
        OUT TXPORT
        INX H
        DCR C
        JNZ MDBA
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        INX H
        MOV A,E
        CPI 036h
        JNZ MDBL
; FF-добивка 1798
        MVI A,0FFh
        MVI B,007h
MPD7:   MVI D,0FFh
MPDI:   OUT TXPORT
        NOP
        NOP
        DCR D
        JNZ MPDI
        DCR B
        NOP
        JNZ MPD7
        MVI D,00Dh
MPDT:   OUT TXPORT
        NOP
        NOP
        DCR D
        JNZ MPDT
; пад пути
        LXI B,P_MD
MDPD:   DCX B
        MOV A,B
        ORA C
        JNZ MDPD
        JMP WTAIL

; ---- единый ожидатель до ровно 125 000T ----
WTAIL:  LXI B,W_V2
WLP:    DCX B
        MOV A,B
        ORA C
        JNZ WLP
        ORI 000h
        ORI 000h
        NOP
        NOP
        NOP
        NOP
        NOP
        NOP
        JMP FRAME

; ---------------------- таблицы и строки ----------------------
TBL:    DB 001h,002h,004h,008h,010h,020h,040h,080h
; дитер: 16 ступелей плотности (MSB = левый px)
DIT:    DB 000h,080h,0C0h,0E0h,0F0h,0F8h,0FCh,0FEh
        DB 0FFh,07Fh,03Fh,01Fh,00Fh,007h,003h,001h
; NEG16[k] = (16-k) & 15
NEG16:  DB 000h,00Fh,00Eh,00Dh,00Ch,00Bh,00Ah,009h
        DB 008h,007h,006h,005h,004h,003h,002h,001h
; фиксированная маска дельты строки: строки 45..53
MMASK:  DB 000h,000h,000h,000h,000h,0E0h,03Fh,000h
        DB 000h,000h,000h,000h,000h
; шрифт 8x8, MSB = левый px (23 глифа x 8 Б)
; 0 пробел, 1 '-', 2 '0', 3 '1', 4 '2', 5 '3', 6 '5', 7 '6',
; 8 'A', 9 'B', 10 'D', 11 'E', 12 'F', 13 'G', 14 'L', 15 'M',
; 16 'O', 17 'P', 18 'R', 19 'S', 20 'T', 21 'V', 22 'X'
FONT:   DB 000h,000h,000h,000h,000h,000h,000h,000h   ; пробел
        DB 000h,000h,000h,07Eh,07Eh,000h,000h,000h   ; -
        DB 03Ch,066h,06Eh,076h,066h,066h,03Ch,000h   ; 0
        DB 018h,038h,018h,018h,018h,018h,07Eh,000h   ; 1
        DB 03Ch,066h,006h,00Ch,030h,060h,07Eh,000h   ; 2
        DB 03Ch,066h,006h,01Ch,006h,066h,03Ch,000h   ; 3
        DB 07Eh,060h,07Ch,006h,006h,066h,03Ch,000h   ; 5
        DB 01Ch,030h,060h,07Ch,066h,066h,03Ch,000h   ; 6
        DB 018h,03Ch,066h,066h,07Eh,066h,066h,000h   ; A
        DB 07Ch,066h,066h,07Ch,066h,066h,07Ch,000h   ; B
        DB 07Ch,066h,066h,066h,066h,066h,07Ch,000h   ; D
        DB 07Eh,060h,060h,07Ch,060h,060h,07Eh,000h   ; E
        DB 07Eh,060h,060h,07Ch,060h,060h,060h,000h   ; F
        DB 03Ch,066h,060h,06Eh,066h,066h,03Ch,000h   ; G
        DB 060h,060h,060h,060h,060h,060h,07Eh,000h   ; L
        DB 066h,07Eh,07Eh,066h,066h,066h,066h,000h   ; M
        DB 03Ch,066h,066h,066h,066h,066h,03Ch,000h   ; O
        DB 07Ch,066h,066h,07Ch,060h,060h,060h,000h   ; P
        DB 07Ch,066h,066h,07Ch,06Ch,066h,066h,000h   ; R
        DB 03Ch,066h,060h,03Ch,006h,066h,03Ch,000h   ; S
        DB 07Eh,018h,018h,018h,018h,018h,018h,000h   ; T
        DB 066h,066h,066h,066h,066h,03Ch,018h,000h   ; V
        DB 066h,066h,03Ch,018h,03Ch,066h,066h,000h   ; X
; сообщение (индексы глифов): "GFXSTREAM V2 - 160X100 - 25FPS - FAST BALL DEMO "
MSG:    DB 00Dh,00Ch,016h,013h,014h,012h,00Bh,008h   ; "GFXSTREA"
        DB 00Fh,000h                                  ; "M "
        DB 015h,004h,000h                             ; "V2 "
        DB 001h,000h                                  ; "- "
        DB 003h,007h,002h,016h,003h,002h,002h,000h    ; "160X100 "
        DB 001h,000h                                  ; "- "
        DB 004h,006h,00Ch,011h,013h,000h              ; "25FPS "
        DB 001h,000h                                  ; "- "
        DB 00Ch,008h,013h,014h,000h                   ; "FAST "
        DB 009h,008h,00Eh,00Eh,000h                   ; "BALL "
        DB 00Ah,00Bh,00Fh,010h,000h                   ; "DEMO "
M_BAN:  DB 00Dh,00Ah
        DB "GFXSTREAM v2.2"
        DB 00Dh,00Ah,000h
        END
