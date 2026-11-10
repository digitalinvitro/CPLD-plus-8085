; ======================================================================
;  GFXSTREAM v1 — графический поток по UART 1М: 160x100 1bpp, 25 FPS
;  Плата: retro PC (8085 + XC95108, TX-ядро v2.3, 1 000 000 бод 8N1)
;  CPU: 8085 @ 3.125 МГц, T = 320 нс; кадр 8N1 = 31.25T = 10 мкс.
;  Спецификация: beta/gfxstream/SPEC.md (выборы владельца 11-10-4).
;
;  ЧТО ДЕЛАЕТ:
;   POR-пауза ~503 мс -> баннер "\r\nGFXSTREAM v1\r\n" -> init ->
;   кадры каждые РОВНО 125 000T = 40 мс (25.000 FPS, детерминировано):
;   кадры 0..74      TYPE 01 — полные 160x100 (payload 2 000 Б);
;   кадры 75..       TYPE 02 — дельта-строки (маска 13 Б + 9 строк x 21 Б),
;                      каждый 100-й кадр — TYPE 01 полный (ресинк);
;   конверт кадра на проводе ВСЕГДА 2 006 Б: хвост дельты добит FFh
;   (UART-idle, парсер ПК пропускает) -> период кадра одинаков в обоих
;   режимах и калибруется до 125 000T точно.
;
;  ТЕСТ-ПАТТЕРН: сетка 8x8 (вертикали каждый 8-й px, горизонтали каждый
;  8-я строка, рамка по краям) + шар 8x8 (сплошной белый блок),
;  движется по диагонали с отскоком: col 0..19, row 0..92.
;  Одинарный кадровый буфер: патч (стереть старый шар аналитической
;  сеткой, нарисовать новый) ЗАВЕРШАЕТСЯ до посылки — разрывов нет.
;
;  ПОСЫЛКА (ключевая механика, доказана симом):
;   единый цикл из ОЗУ MOV A,M(7)+OUT 04h(10)+INX H(6)+DCX B(6)+
;   MOV A,B(4)+ORA C(4)+JNZ(10) = 47T/байт РАВНОМЕРНО на всём кадре,
;   включая границы заголовок/строки — 47 > 31.25 -> TX успевает,
;   НОЛЬ отбросов (у развёртки x2 из SPEC межписьмо 24T < 31.25T —
;   отбросы, потому отказано; см. DEVLOG 11-10-6).
;   Темп посылки 66 489 Б/с = 66.5% линии; кадр 2 006 Б за 30.2 мс.
;
;  ФОРМАТ КАДРА (SPEC п.3): A5 5A [TYPE] [N_LO] [N_HI] [SEQ] [payload]
;   TYPE 01: N=07D0h (2 000), payload = 100 строк x 20 Б, MSB=левый px,
;            1 = светлая точка.
;   TYPE 02: N=00CAh (202) = маска 13 Б (бит k байта m = строка 8m+k,
;            LSB = верхняя строка группы) + 9 x [номер строки][20 Б];
;            дельта vs показанный кадр: строки [min(r_prev,r_new) ..
;            max(r_prev,r_new)+7] — ровно 9 строк (шаг по r всегда ±1).
;   SEQ = номер кадра mod 256, без пропусков.
;
;  ОЗУ (8000h-FFFFh, 32 КБ):
;   FB    8000h..87D5h — кадровый буфер 2 006 Б (заголовок 6 + 2 000);
;   SCRAP 9000h..97E5h — сборка дельты 2 006 Б (хвост заранее FFh);
;   STATE 9800h..980Ah — SEQ/DPH/FCNT/шар; SP = FFF8h.
;   Итого 4 027 Б из 32 КБ (12.3%) — как в SPEC (п.4).
;
;  ПЕЙСИНГ БЕЗ АППАРАТНОГО ТАЙМЕРА: в ядре v2.3 таймера нет (карта
;  портов 00h-05h), поэтому период 40 мс — калиброванный программный
;  цикл ожидания W_FULL/W_DEL (EQU, подбор по симу до 125 000T точно).
;  Отклонение от SPEC п.4 («таймером платы») задокументировано.
;
;  Порты: OUT 04h — данные TX (TX_BOTH=0, как в p04; алиас 05h не нужен).
;  Сборка: python3 asm8085.py gfxstream_v1.asm <имя>
;  Проверка: scripts/sim_gfxstream_v1.py (интерпретатор hex + модель TX
;  + побайтовая сверка паттерна/масок/периода).
; ======================================================================

TXPORT  EQU 004h

FB      EQU 8000h       ; кадровый буфер: +0..5 заголовок, +6..2005 payload
SCRAP   EQU 9000h       ; сборка дельты (тот же конверт 2 006 Б)
S_SEQ   EQU 9800h
S_DPH   EQU 9801h       ; счётчик до 100-кадрового ресурсинка
S_FCNT  EQU 9802h       ; счётчик кадров 16 бит (lo 9802, hi 9803)
S_FC1   EQU 9803h       ; старший байт FCNT
S_C     EQU 9804h       ; шар: текущий col (0..19)
S_R     EQU 9805h       ; шар: текущая row (0..92)
S_DC    EQU 9806h       ; шаг col: 01h / FFh
S_DR    EQU 9807h       ; шаг row: 01h / FFh
S_PC    EQU 9808h       ; предыдущий col (стираемый)
S_PR    EQU 9809h       ; предыдущая row (стираемая)
S_MODE  EQU 980Ah       ; режим последнего кадра: 0 = TYPE 01, 1 = TYPE 02

W_FRAME EQU 930         ; единая калибровка периода кадра (см. сим)
PADF    EQU 261         ; выравнивание работы полного пути под дельту

        ORG 0000h
; ---------------------- сброс ----------------------
        DI
        LXI SP,FFF8h
        LXI D,0000h        ; пауза ~503 мс: POR CPLD, запас открыть
PORLP:  DCX D              ; вьюер до баннера (прецедент TXSTRESS)
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
; FB payload: сетка. Строка r: FFh если (r&7)==0 или r==99, иначе
; 80h; в байте 19 дополнительно бит 01h (правый край px 159).
        LXI H,FB+0006h
        MVI E,000h         ; номер строки 0..99
IRLP:   MOV A,E
        ANI 007h
        JZ IGRID
        MOV A,E
        CPI 063h
        JZ IGRID
        MVI C,080h
        JMP IROK
IGRID:  MVI C,0FFh
IROK:   MVI D,013h         ; 19 обычных байт строки
IJLP:   MOV A,C
        MOV M,A
        INX H
        DCR D
        JNZ IJLP
        MOV A,C            ; байт 19: правый край
        ORI 001h
        MOV M,A
        INX H
        INR E
        MOV A,E
        CPI 064h
        JNZ IRLP

; FB заголовок: A5 5A 01 D0 07 (SEQ пишется каждый кадр)
        LXI H,FB
        MVI A,0A5h
        MOV M,A
        INX H
        MVI A,05Ah
        MOV M,A
        INX H
        MVI A,001h
        MOV M,A
        INX H
        MVI A,0D0h         ; N_LO: 2 000 = 07D0h
        MOV M,A
        INX H
        MVI A,007h         ; N_HI
        MOV M,A

; SCRAP: 2 006 Б FFh (конверт дельты; хвост = UART-idle для парсера)
        LXI H,SCRAP
        MVI A,0FFh
        LXI B,07D6h
IFILL:  MVI A,0FFh         ; A портится тестом счётчика — перезагрузка
        MOV M,A
        INX H
        DCX B
        MOV A,B
        ORA C
        JNZ IFILL
; SCRAP заголовок: A5 5A 02 CA 00 (N = 13+9x21 = 202 = CAh)
        LXI H,SCRAP
        MVI A,0A5h
        MOV M,A
        INX H
        MVI A,05Ah
        MOV M,A
        INX H
        MVI A,002h
        MOV M,A
        INX H
        MVI A,0CAh         ; N_LO
        MOV M,A
        INX H
        MVI A,000h         ; N_HI
        MOV M,A

; состояние: шар в (0,0), шаг +1/+1, SEQ=FFh (первый INR -> 00h)
        XRA A
        STA S_C
        STA S_R
        STA S_PC
        STA S_PR
        STA S_DPH
        STA S_FCNT         ; lo
        STA S_FC1          ; hi
        STA S_MODE
        MVI A,001h
        STA S_DC
        STA S_DR
        MVI A,0FFh
        STA S_SEQ

; ===================== кадровый цикл =====================
FRAME:
; ---- 1. шаг шара: c'=c+dc (отскок 0/19), r'=r+dr (отскок 0/92) ----
        LDA S_DC
        MOV B,A            ; B = dc
        LDA S_C
        MOV C,A            ; C = старый col
        MOV A,C
        ADD B              ; A = c', флаги по c'
        JZ CFL0
        CPI 013h
        JZ CFL19
        JMP COK1
CFL0:   MVI B,001h
        JMP COK1
CFL19:  MVI B,0FFh
COK1:   MOV E,A            ; E = c' (A не тронут ветками)
        MOV A,B            ; новый dc
        STA S_DC
        MOV A,C            ; старый col -> S_PC
        STA S_PC
        MOV A,E            ; новый col -> S_C
        STA S_C
;
        LDA S_DR
        MOV B,A            ; B = dr
        LDA S_R
        MOV C,A            ; C = старый row
        MOV A,C
        ADD B              ; A = r', флаги по r'
        JZ RFL0
        CPI 05Ch
        JZ RFL92
        JMP ROK1
RFL0:   MVI B,001h
        JMP ROK1
RFL92:  MVI B,0FFh
ROK1:   MOV E,A            ; E = r' (A не тронут ветками)
        MOV A,B            ; новый dr
        STA S_DR
        MOV A,C            ; старый row -> S_PR
        STA S_PR
        MOV A,E            ; новый row -> S_R
        STA S_R

; ---- 2. стереть старый шар (8 байт аналитической сеткой) ----
        LDA S_PC
        CPI 013h           ; флаг "col==19" -> в сетке 81h
        MVI C,000h
        JZ EFLG
        JMP EFLG0
EFLG:   MVI C,001h
EFLG0:  LDA S_PR
        MOV L,A            ; HL = 20*r_old
        MVI H,000h
        DAD H
        DAD H
        MOV D,H
        MOV E,L
        DAD H
        DAD H
        DAD D              ; HL = 20*r_old
        LXI D,FB+0006h
        DAD D              ; + база FB+6
        LDA S_PC
        MOV E,A
        MVI D,000h
        DAD D              ; + c_old
        LXI D,0014h        ; DE = шаг строки 20 (в цикле НЕ трогается!)
        MVI B,000h         ; i = 0..7
ERL:    LDA S_PR
        ADD B              ; A = номер строки r_old + i
        ANI 007h
        JZ EGR
        LDA S_PR           ; ANI испортил A — перезагрузка (E занят шагом!)
        ADD B
        CPI 063h
        JZ EGR
        MOV A,C
        ORA A
        JZ E80
        MVI A,081h
        JMP EST
EGR:    MVI A,0FFh
        JMP EST
E80:    MVI A,080h
EST:    MOV M,A
        DAD D
        INR B
        MOV A,B
        CPI 008h
        JNZ ERL

; ---- 3. нарисовать новый шар (8 байт FFh) ----
        LDA S_R
        MOV L,A            ; HL = 20*r_new
        MVI H,000h
        DAD H
        DAD H
        MOV D,H
        MOV E,L
        DAD H
        DAD H
        DAD D
        LXI D,FB+0006h
        DAD D              ; + база FB+6
        LDA S_C
        MOV E,A
        MVI D,000h
        DAD D              ; + c_new
        LXI D,0014h
        MVI A,0FFh
        MVI B,008h
DRL:    MOV M,A
        DAD D
        DCR B
        JNZ DRL

; ---- 4. счётчики: SEQ++, FCNT++, DPH++ (100 -> ресурсинк) ----
        LXI H,S_SEQ
        INR M
        LXI H,S_FCNT
        INR M
        JNZ FOK
        INX H
        INR M
FOK:    LDA S_DPH
        INR A
        MVI C,000h         ; C = признак ресурсинка
        CPI 064h
        JC DOK
        XRA A              ; DPH достиг 100 -> 0, кадр = полный
        STA S_DPH
        MVI C,001h
        JMP DMOD
DOK:    STA S_DPH
DMOD:   MOV A,C
        ORA A
        JNZ FULLM
        LDA S_FC1          ; FCNT (hi): 0 -> ещё первый этап
        ORA A
        JNZ DELTAM
        LDA S_FCNT         ; hi=0: полный, пока lo <= 75
        CPI 04Ch
        JC FULLM
DELTAM: MVI A,001h
        STA S_MODE
        JMP MOK
FULLM:  XRA A
        STA S_MODE
MOK:

; ---- 5. ветка режима ----
        LDA S_MODE
        ORA A
        JNZ DELTAP

; ----- TYPE 01: полный кадр из FB -----
        LXI B,PADF         ; выравнивание работы полного пути под дельту:
PADFL:  DCX B              ; период кадра = посылка + ожидание + РАБОТА
        MOV A,B            ; СЛЕДУЮЩЕГО кадра — она должна быть одинакова
        ORA C              ; в обоих режимах, иначе полные кадры перед
        JNZ PADFL          ; дельтами растягиваются на +2 мс (см. DEVLOG)
        NOP                ; PAD-FULL точная доводка (калибровка по симу)
        NOP
        LXI H,FB+0005h
        LDA S_SEQ
        MOV M,A            ; SEQ в заголовок
        LXI H,FB
        LXI B,07D6h        ; 2 006 Б
        JMP SENDLP

; ----- TYPE 02: дельта в SCRAP -----
DELTAP:
; маска: обнулить 13 Б
        LXI H,SCRAP+0006h
        MVI B,00Dh
        MVI A,000h
ZML:    MOV M,A
        INX H
        DCR B
        JNZ ZML
; RMIN = min(S_PR, S_R)
        LDA S_PR
        MOV B,A
        LDA S_R
        CMP B
        JNC RMP
        JMP RMR
RMP:    MOV A,B
RMR:    MOV C,A            ; C = RMIN
; начальный байт маски: HL = SCRAP+6 + (RMIN>>3)
        MOV A,C
        RRC
        RRC
        RRC
        ANI 01Fh
        MOV E,A
        MVI D,000h
        LXI H,SCRAP+0006h
        DAD D              ; HL -> байт маски
; начальный бит = 1 << (RMIN & 7) — по таблице (постоянное время, без
; сдвигового цикла: иначе дрожание периода дельты до ±380T). Бит спасаем
; в B: следующие блоки пользуются D и HL.
        MOV A,C
        ANI 007h
        MOV E,A
        MVI D,000h
        LXI H,TBL
        DAD D
        MOV B,M          ; B = бит
; начальный байт маски: HL = SCRAP+6 + (RMIN>>3)
        MOV A,C
        RRC
        RRC
        RRC
        ANI 01Fh
        MOV E,A
        MVI D,000h
        LXI H,SCRAP+0006h
        DAD D            ; HL -> байт маски
        MOV D,B          ; D = бит
SBPD:   MVI B,009h         ; 9 строк
WLK:    MOV A,M
        ORA D
        MOV M,A
        MOV A,D
        RLC
        MOV D,A
        JNC WNB
        MVI D,001h
        INX H
WNB:    DCR B
        JNZ WLK
; копия строк: HL = FB+6+RMIN*20, DE = SCRAP+19, C = номер строки
        MOV A,C
        MOV L,A
        MVI H,000h
        DAD H
        DAD H
        MOV D,H
        MOV E,L
        DAD H
        DAD H
        DAD D              ; HL = 20*RMIN
        LXI D,FB+0006h
        DAD D              ; + база FB+6
        LXI D,SCRAP+0013h  ; DE = SCRAP+19
        MVI B,009h
CRL:    MOV A,C
        STAX D             ; номер строки
        INX D
        INR C
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        MOV A,M
        STAX D            ; [DE] = A (в SCRAP, НЕ MOV M,A!)
        INX H
        INX D
        DCR B
        JNZ CRL
; SEQ в заголовок дельты
        LXI H,SCRAP+0005h
        LDA S_SEQ
        MOV M,A
        LXI H,SCRAP
        LXI B,07D6h        ; конверт тоже 2 006 Б (хвост FFh)
        JMP SENDLP

; ---- 6. посылка: 47T/байт равномерно ----
SENDLP: MOV A,M
        OUT TXPORT
        INX H
        DCX B
        MOV A,B
        ORA C
        JNZ SENDLP

; ---- 7. ожидание до ровно 125 000T (единое W — работа путей выровнена) ----
        LXI B,W_FRAME
WLP:    DCX B
        MOV A,B
        ORA C
        JNZ WLP
        ORI 000h           ; PAD-W (калибровка по симу): 7+7+4+4+4 = 22T
        ORI 000h
        NOP
        NOP
        NOP
        JMP FRAME

; ---------------------- таблицы и строки ----------------------
TBL:    DB 001h,002h,004h,008h,010h,020h,040h,080h
M_BAN:  DB 00Dh,00Ah
        DB "GFXSTREAM v1"
        DB 00Dh,00Ah,000h
        END
