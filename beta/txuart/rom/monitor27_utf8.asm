; =====================================================================
; beta/txuart/rom -- monitor27: монитор для платы v2.7 (beta/txuart)
;
; База: fw_mon v5 (beta/lowsize/rom, клавиатурный монитор "ACDE").
; Отличия от v5 (платформа v2.7, CPLD top_txuart_por6_v27):
;   1. ВЕКТОРА 0008h-003Fh = глушилки EI;RET. На v2.7 CPLD выдаёт на
;      ногу TRAP (P74) квадрат 128 мкс (64/64) = 7,8125 кГц (tick_q).
;      TRAP немаскируем: DI не помогает. Без обработчика первый же фронт
;      уводит CPU на 0024h, где у v5 лежала таблица GTBL -> "8.8.8.8.".
;      EI в глушилке ОБЯЗАТЕЛЕН: после приёма TRAP новые TRAP блокируются
;      до EI (п.36 даташита; без EI тик-система глохнет после 1-го тика).
;      Пользовательские программы защищены автоматически: глушилки в ROM.
;   2. Таблицы перенесены с 0003h на 0044h (освобождена векторная зона).
;   3. Тайминг под 2,5 МГц (T = 400 нс; lowsize был 3,571 МГц):
;      K_MS = 104 (~1,0 мс/единица; итерация DCX/MOV/ORA/JNZ = 24T).
;   4. NEW: приём по SID 4800 8N1 (RIM, транзит RX->SID в CPLD) -
;      Intel HEX загрузчик (клавиша B в меню). Код RXD = мануал
;      (programming manual, фрагменты 5/7): PAUSE 6 мкс/итер, полбита
;      N=15, бит N=30 - числа железо-проверены эхо-прошивками.
;   5. NEW: передача через CPLD OUT 04h @ 1 000 000 8N1 (сериализатор
;      v2.7; TXRDY = IN 05h бит A1, остальные биты 0). Баннер при
;      старте. ВНИМАНИЕ: мост CH340G = ОДНА скорость на оба направления;
;      терминал 4800 -> загрузка HEX работает, баннер = короткий мусор
;      (~8 байт); терминал 1M -> баннер читается, вставка HEX не ловится
;      (приём программный, 2,5 МГц CPU не успевает за 1 мкс/бит).
;   6. NEW: RAM-тест 8000h-FFE7h (клавиша F в меню), 4 паттерна.
;   7. SOD (SIM) НЕ используется: на v2.7 транзит SOD->TX выпилен
;      (TX = только сериализатор CPLD); RIM - только для приёма SID.
;
; СБОРКА (asm85.py, кодировка CP1251):
;   python3 asm85.py monitor27.asm -o monitor27.hex -l monitor27.lst
;   (asm85.py лежит в beta/lowsize/rom; из этого каталога:
;    python3 ../../lowsize/rom/asm85.py monitor27.asm -o monitor27.hex -l monitor27.lst)
; Прошивка: flash A29040B, offset 0000h (ROM-окно 0000h-7FFFh).
;
; КЛАВИАТУРА (как v5): тетрады 0-F + Enter + F1(меню) + F2(показ адреса);
; ДОБАВЛЕНО в меню: B (0Bh) = загрузчик Intel HEX через SID 4800,
; F (0Fh) = RAM-тест. Дисплей в режимах B/F - статический (скан остановлен,
; все 4 разряда = один глиф: LLLL / 0000 / FFFF / 5555 / AAAA / EEEE).
; Выход из залипшего режима - RESET (SW20), как в v5.
;
; ОЗУ: переменные FFE8h-FFFFh, стек с FFE7h вниз (SP0 = FFE8h).
; Новые переменные загрузчика: FFFAh-FFFFh; адрес записи - в ADDRH/L
; (на дисплее после загрузки - последний адрес записи).
; =====================================================================

; ---- порты CPLD (декод по A2-A0, зеркала mod 8) ----
SEGP    EQU 00h             ; сегменты: D0=a..D6=g, D7=dp; 1 = горит
DIGP    EQU 01h             ; D3-D0 разряды, D4 = SND
KBCOLP  EQU 02h             ; D3-D0 колонки (1 = заведена)
KBROWP  EQU 03h             ; D4-D0 ряды (1 = нажата в активной колонке)
TXP     EQU 04h             ; OUT: TXDATA -> сериализатор CPLD (1M 8N1)
STP     EQU 05h             ; IN: статус, бит A1 = TXRDY (1 = готов)

; ---- константы тайминга (CPU 2,5 МГц, T = 400 нс) ----
K_MS    EQU 104             ; единица ~1,0 мс (104 x 24T x 400 нс)
TICK_MS EQU 15              ; тик клавиши ~15 мс (v5: 30 @3,57 МГц)
SET_MS  EQU 15              ; дебаунс отпускания ~15 мс (v5: 30)
RXHB    EQU 15              ; полбита 4800 (PAUSE-итераций, ~103 мкс)
RXFB    EQU 30              ; бит приёма 4800 (PAUSE-итераций, ~211 мкс)

; ---- коды клавиш ----
K_ENT   EQU 10h             ; Enter  (row3/col3, SW16)
K_F1    EQU 11h             ; F1     (row4/col1, SW18) - меню
K_F2    EQU 12h             ; F2     (row4/col2, SW19) - показ адреса
K_NONE  EQU 0FFh            ; пустая позиция матрицы

; ---- состояния ----
ST_MENU EQU 00h             ; меню "ACDE" (B = загрузчик, F = RAM-тест)
ST_ADDR EQU 01h             ; ввод адреса
ST_PROG EQU 02h             ; ввод кода (Code)
ST_VIEW EQU 03h             ; просмотр кода
ST_SHOW EQU 04h             ; показ адреса операций (F2)

; ---- ОЗУ монитора ----
SP0     EQU 0FFE8h          ; SP монитора
SNDST   EQU 0FFE8h          ; состояние тона 0/1
STATE   EQU 0FFE9h          ; 0=меню, 1=адрес, 2=код, 3=просмотр, 4=показ
ADDRH   EQU 0FFEAh          ; текущий адрес (старший); в загрузчике = адрес записи
ADDRL   EQU 0FFEBh          ; текущий адрес (младший)
ADCNT   EQU 0FFECh          ; тетрады адреса (0..4); в загрузчике = счётчик байт данных
AF3     EQU 0FFEDh          ; тетрады адреса
AF2     EQU 0FFEEh
AF1     EQU 0FFEFh
AF0     EQU 0FFF0h
BDCNT   EQU 0FFF1h          ; введено тетрад байта (0..2)
BF1     EQU 0FFF2h
BF0     EQU 0FFF3h
DPIDX   EQU 0FFF4h          ; фаза регенерации 0..3
DIGIMG  EQU 0FFF5h          ; глифы разрядов DIG0..DIG3
DIGIMG0 EQU 0FFF5h
DIGIMG1 EQU 0FFF6h
DIGIMG2 EQU 0FFF7h
DIGIMG3 EQU 0FFF8h
PREVST  EQU 0FFF9h          ; прежний режим для F2
; --- новые: парсер Intel HEX (загрузчик B) ---
LST     EQU 0FFFAh          ; состояние: 0=ждём ':' 1=count 2=addr 3=type 4=data 5=chk
LNIB    EQU 0FFFBh          ; осталось тетрад в текущем байте поля (1..2)
LBPC    EQU 0FFFCh          ; осталось байт в текущем поле
LACC    EQU 0FFFDh          ; накопитель тетрад текущего байта
LSUM    EQU 0FFFEh          ; сумма байт записи (mod 256) для контроля
LTY     EQU 0FFFFh          ; тип последней записи (00 = данные, 01 = конец)

; =====================================================================
        ORG 0000h
        JMP START

; ---- векторная зона: глушилки EI;RET -------------------------------
; RST 1..7, TRAP (0024h), RST 5.5/6.5/7.5. EI обязателен в каждой:
; снимает блокировку TRAP после приёма. Маскируемые (5.5/6.5/7.5/INTR)
; железно=0 (PGND), EI для них безопасен. Формат: F3 C9.
        ORG 0008h           ; RST 1
        EI
        RET
        ORG 0010h           ; RST 2
        EI
        RET
        ORG 0018h           ; RST 3
        EI
        RET
        ORG 0020h           ; RST 4
        EI
        RET
        ORG 0024h           ; TRAP - ГЛАВНАЯ глушилка (тик CPLD 7,8125 кГц)
        EI
        RET
        ORG 0028h           ; RST 5
        EI
        RET
        ORG 002Ch           ; RST 5.5
        EI
        RET
        ORG 0030h           ; RST 6
        EI
        RET
        ORG 0034h           ; RST 6.5
        EI
        RET
        ORG 0038h           ; RST 7
        EI
        RET
        ORG 003Ch           ; RST 7.5
        EI
        RET

; =====================================================================
; Таблицы (ORG 0044h - векторная зона выше освобождена)
; =====================================================================
        ORG 0044h
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

; ---- баннер TX @1M (на терминале 4800 = короткая мусорная строка) ----
TXBAN:  DB 4Dh,4Fh,4Eh,32h,37h,0Dh,0Ah,00h   ; "MON27\r\n"

; ---- паттерны RAM-теста: значение + глиф для статического дисплея ----
RAMPAT: DB 00h,3Fh          ; 00h -> "0000"
        DB 0FFh,71h         ; FFh -> "FFFF"
        DB 55h,6Dh          ; 55h -> "5555"
        DB 0AAh,77h         ; AAh -> "AAAA"

; =====================================================================
; Системные процедуры (перенос из fw_mon v5, константы под 2,5 МГц)
; =====================================================================
        ORG 0100h

; ---------------------------------------------------------------------
; SETTLE: пауза ~36 мкс (LXI+3 итерации 24T @400 нс; установка рядов
; после заведения колонки). Портит A/B/C.
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
; REFRESH: один слот регенерации. ГАШЕНИЕ -> РАЗРЯД -> ГЛИФ (как v5,
; без послесвечения). DIGIMG[DPIDX] на разряд DPIDX. Бит D4 (SND)
; уносится записью DIGP - дисплей при тоне не гаснет.
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
; BUNIT: единица ~1,03 мс (104 итерации 24T) + тоггл SNDST + регенерация
; QUNIT: единица ~1,03 мс без звука, дисплей живёт
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
; тон ~500 Гц). Счётчик - В DE: REFRESH портит HL, но гарантирует D/E.
; ---------------------------------------------------------------------
TICKON: LXI D,TICK_MS       ; тик клавиши (единицы ~1,03 мс)
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
; REDRAW: пересобрать DIGIMG[0..3] по состоянию (как v5).
;   меню : "ACDE"; адрес: тетрады вдвигаются справа; код "__C3";
;   просмотр: [ADDR] в правых разрядах; показ(F2): ADDR на 4 разрядах.
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
        ANI 0Fh
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
        CPI 01h
        JC RDRE             ; 0 тетрад - всё пусто
        LDA AF0
        CALL GLOOK
        STA DIGIMG0
        LDA ADCNT
        CPI 02h
        JC RDRE
        LDA AF1
        CALL GLOOK
        STA DIGIMG1
        LDA ADCNT
        CPI 03h
        JC RDRE
        LDA AF2
        CALL GLOOK
        STA DIGIMG2
        LDA ADCNT
        CPI 04h
        JC RDRE
        LDA AF3
        CALL GLOOK
        STA DIGIMG3
RDRE:   RET

; =====================================================================
; UART-канал v2.7: передача OUT 04h @1M (TXRDY = IN 05h бит A1),
; приём RIM/SID @4800 (мануал, фрагменты 5/7)
; =====================================================================

; ---------------------------------------------------------------------
; TXBYTE: A = байт -> сериализатор CPLD (1 000 000 8N1). Ожидает TXRDY
; (запись при busy аппаратно отбрасывается). Портит A.
; ---------------------------------------------------------------------
TXBYTE: PUSH PSW
TXB1:   IN STP
        ANI 02h             ; бит A1 = TXRDY (tx_idle = ~|bit_cnt)
        JZ TXB1
        POP PSW
        OUT TXP
        RET

; ---------------------------------------------------------------------
; TXSTR: HL = строка с нулевым завершителем -> TX. Портит A/HL.
; ---------------------------------------------------------------------
TXSTR:  MOV A,M
        ORA A
        RZ
        CALL TXBYTE
        INX H
        JMP TXSTR

; ---------------------------------------------------------------------
; PAUSE: пауза D итераций по 6 мкс (DCR+JNZ = 15T @2,5 МГц).
; ---------------------------------------------------------------------
PAUSE:  DCR D
        JNZ PAUSE
        RET

; ---------------------------------------------------------------------
; RXD: приём байта SID 4800 8N1 (мануал, фрагмент 7 + стоп-бит).
; Выход: C = байт, CY = 0 ОК / CY = 1 обрыв кадра (стоп-бит = 0).
; Портит A/B/C/D. Цикл строгий - прерываний не звать (TRAP-глушилка
; добавляет 5,6 мкс джиттера раз в 127 мкс - при 208 мкс/бит не опасно).
; ---------------------------------------------------------------------
RXD:    MVI B,08h
RXW:    RIM                 ; A7 = SID
        ORA A
        JM RXW              ; '1' (покой) - ждать старт-бит
        MVI D,RXHB          ; полбита - в середину старт-бита
        CALL PAUSE
        RIM                 ; подтвердить старт-бит
        ORA A
        JM RXW              ; '1' - ложный старт, ждать заново
        MVI C,00h
        MVI D,RXFB          ; бит - в середину D0
        CALL PAUSE
RXL:    RIM                 ; A7 = SID - центр очередного бита
        ANI 80h
        RAR                 ; бит -> CY
        MOV A,C
        RAR                 ; вставить сверху (LSB-first)
        MOV C,A
        MVI D,RXFB
        CALL PAUSE
        DCR B
        JNZ RXL
        ; после последней итерации RXL (выборка d7 + бит задержки)
        ; линия = середина стоп-бита
        RIM
        ANI 80h             ; CY = 0 (ANI сбрасывает перенос)
        JZ RXBAD            ; стоп-бит = 0 - обрыв кадра
        ORA A               ; CY = 0
        RET                 ; C = байт, CY = 0
RXBAD:  STC
        RET                 ; CY = 1

; ---------------------------------------------------------------------
; NIB: A = ASCII-символ -> CY = 1 и A = тетрада 0-F ('0'-'9','A'-'F',
; 'a'-'f'), иначе CY = 0. Портит A.
; ---------------------------------------------------------------------
NIB:    SUI 30h             ; '0'..'9' -> 0..9
        JC NIBX             ; < '0'
        CPI 0Ah
        JC NIBOK            ; цифра 0..9
        SUI 07h             ; 'A'..'F' -> 10..15
        CPI 10h
        JNC NIB2            ; > 'F' - попробовать строчные a..f
        JMP NIBOK
NIB2:   SUI 20h             ; ('a'-'0')-07h-20h = 10..15
        CPI 10h
        JNC NIBX
        JMP NIBOK
NIBOK:  STC
        RET
NIBX:   ORA A               ; CY = 0
        RET

; ---------------------------------------------------------------------
; LSTAT: A = глиф -> статический дисплей (все 4 разряда, скан стоит).
; Для режимов загрузчика/RAM-теста, где главный цикл не крутится.
; ---------------------------------------------------------------------
LSTAT:  PUSH B
        MOV B,A
        XRA A
        OUT SEGP            ; гашение на время переключения
        MVI A,0Fh
        OUT DIGP            ; все 4 разряда, SND = 0
        MOV A,B
        OUT SEGP            ; глиф на все разряды
        POP B
        RET

; ---------------------------------------------------------------------
; DLMS: пауза ~1,03 мс (K_MS итераций 24T). Портит A/B/C.
; ---------------------------------------------------------------------
DLMS:   LXI B,K_MS
DLS1:   DCX B
        MOV A,B
        ORA C
        JNZ DLS1
        RET

; ---------------------------------------------------------------------
; LDSUM: LSUM += B (mod 256). Портит A.
; ---------------------------------------------------------------------
LDSUM:  PUSH PSW
        LDA LSUM
        ADD B
        STA LSUM
        POP PSW
        RET

; ---------------------------------------------------------------------
; LDBEEP: длинный сигнал ~0,3 с (тон ~500 Гц, дисплей не трогает -
; только бит D4 в DIGP). Портит A/D.
; ---------------------------------------------------------------------
LDBEEP: MVI D,150
LDB1:   MVI A,1Fh           ; SND = 1, разряды on
        OUT DIGP
        CALL DLMS
        MVI A,0Fh           ; SND = 0
        OUT DIGP
        CALL DLMS
        DCR D
        JNZ LDB1
        RET

; =====================================================================
; LOADM: Intel HEX загрузчик (клавиша B). Приём SID 4800 8N1.
; Формат записи: :nnaaaatt[dd...]cc, cc = (-сумма байт) mod 256.
; Статический дисплей LLLL; адрес каждой записи живёт в ADDRH/L.
; Запись только в ОЗУ (A15=1): попадание в ROM-окно = ошибка EEEE.
; Выход: EOF-запись (type 01) -> тик и меню; ошибка -> EEEE + сигнал.
; Выход из зависшего приёма - RESET (SW20).
; ---------------------------------------------------------------------
LOADM:  XRA A
        STA LST             ; ждем ':'
        MVI A,38h           ; 'L'
        CALL LSTAT
LDLP:   CALL RXD            ; C = байт, CY = ошибка кадра
        JC LDERR
        MOV A,C
        CPI ':'
        JZ LDNEW            ; начало записи
        CALL NIB            ; тетрада?
        JNC LDLP            ; прочее (\r\n и т.п.) - пропустить
        MOV E,A             ; E = тетрада
        LDA LACC
        RLC
        RLC
        RLC
        RLC                 ; накопитель << 4
        ORA E
        STA LACC
        LDA LNIB
        DCR A
        STA LNIB
        JNZ LDLP            ; байт поля ещё не собран
        ; --- байт поля собран - применить по состоянию ---
        LDA LACC
        MOV B,A             ; B = байт
        XRA A
        STA LACC            ; накопитель очищен к следующему байту
        LDA LST
        ORA A
        JZ LDLP             ; байт вне записи - игнор
        DCR A
        JZ LDCNT            ; 1 = count
        DCR A
        JZ LDADR            ; 2 = addr
        DCR A
        JZ LDTYP            ; 3 = type
        DCR A
        JZ LDDAT            ; 4 = data
        JMP LDCHK           ; 5 = checksum
LDCNT:  MOV A,B
        STA ADCNT           ; сколько байт данных в записи
        CALL LDSUM
        MVI A,02h           ; поле addr: 4 тетрады = 2 байта
        STA LST
        STA LBPC
        STA LNIB
        JMP LDLP
LDADR:  MOV A,B
        STA LTY             ; временно: тип ещё не читался
        LDA LBPC
        CPI 02h
        JNZ LDAD1
        LDA LTY
        STA ADDRH           ; старший байт адреса (big-endian)
        MVI A,01h
        STA LBPC
        CALL LDSUM
        JMP LDLP
LDAD1:  LDA LTY
        STA ADDRL           ; младший байт адреса
        CALL LDSUM
        MVI A,03h
        STA LST             ; type
        MVI A,01h
        STA LBPC
        MVI A,02h
        STA LNIB
        JMP LDLP
LDTYP:  MOV A,B
        STA LTY
        CALL LDSUM
        LDA LTY
        CPI 01h
        JZ LDTYP1
        LDA ADCNT           ; type 00: данные
        STA LBPC
        MVI A,04h
        STA LST
        MVI A,02h
        STA LNIB
        JMP LDLP
LDTYP1: XRA A               ; type 01 (EOF): данных нет
        STA LBPC
        MVI A,05h
        STA LST
        MVI A,02h
        STA LNIB
        JMP LDLP
LDDAT:  LDA ADDRH
        ANI 80h             ; запись разрешена только в ОЗУ
        JZ LDERR            ; ROM-окно - ошибка
        LDA ADDRH
        MOV H,A
        LDA ADDRL
        MOV L,A
        MOV M,B             ; [ADDR] = байт (writeback CPLD)
        INX H
        MOV A,H
        STA ADDRH
        MOV A,L
        STA ADDRL
        CALL LDSUM
        LDA LBPC
        DCR A
        STA LBPC
        JNZ LDDAT2
        MVI A,05h           ; данные кончились - ждать checksum
        STA LST
        MVI A,02h
        STA LNIB
        JMP LDLP
LDDAT2: MVI A,02h
        STA LNIB
        JMP LDLP
LDCHK:  LDA LSUM            ; контрольная сумма записи
        ADD B               ; сумма всех байт + cc = 0 mod 256?
        JNZ LDERR
        LDA LTY
        CPI 01h
        JZ LDDONE           ; EOF - конец загрузки
        XRA A
        STA LST             ; ждем ':' следующей записи
        JMP LDLP
LDNEW:  MVI A,01h           ; ':' - новая запись
        STA LST
        MVI A,02h
        STA LNIB
        XRA A
        STA LSUM
        JMP LDLP
LDDONE: CALL TICKON         ; подтверждение успешной загрузки
        RET
LDERR:  MVI A,79h           ; 'E' -> дисплей EEEE
        CALL LSTAT
        CALL LDBEEP         ; длинный сигнал
        RET                 ; в меню (ADDRH/L = адрес сбоя, D = просмотр)

; =====================================================================
; RAMT: RAM-тест 8000h-FFE7h (клавиша F). 4 паттерна 00/FF/55/AA:
; заполнение + контроль побайтно. Статический дисплей = глиф паттерна
; ("0000"/"FFFF"/"5555"/"AAAA"). Сбой: ADDRH/L = адрес сбоя, EEEE +
; длинный сигнал. Успех: короткий тик. Стек не трогается: запись до
; FFE7h, SP = FFE8h, pushes TRAP-глушилки (FFDE/FFDF) вне диапазона
; контроля не портят паттерн (pop восстанавливает, ранняя запись
; перекрывается заполнением позже).
; Портит всё.
; ---------------------------------------------------------------------
RAMT:   LXI H,RAMPAT        ; HL = текущая пара (value+glyph)
        MVI C,04h           ; 4 паттерна
RMT0:   MOV A,M             ; A = значение паттерна
        MOV E,A
        PUSH H              ; указатель пары - на стек (HL уйдёт под заполнение)
        INX H
        MOV A,M             ; глиф паттерна
        CALL LSTAT          ; статический дисплей ("0000" и т.д.)
        MOV A,E
        LXI H,8000h
RMF:    MOV M,A             ; заполнение
        INX H
        MOV A,H
        CPI 0FEh            ; до FFE7h включительно
        JNZ RMF
        MOV A,L
        CPI 0E8h
        JNZ RMF
        LXI H,8000h
RMV:    MOV A,M             ; контроль
        CMP E
        JNZ RMBAD
        INX H
        MOV A,H
        CPI 0FEh
        JNZ RMV
        MOV A,L
        CPI 0E8h
        JNZ RMV
        POP H               ; HL = пара паттерна
        INX H
        INX H               ; следующая пара
        DCR C
        JNZ RMT0
        CALL TICKON         ; ОК
        RET
RMBAD:  SHLD ADDRL          ; ADDRH/L = адрес сбоя (HL из RMV, до POP!)
        POP H               ; снять указатель пары (баланс стека)
        MVI A,79h           ; 'E' -> EEEE
        CALL LSTAT
        CALL LDBEEP
        RET                 ; в меню; D = просмотр байта по адресу сбоя

; =====================================================================
; MAIN: как v5 (константы под 2,5 МГц) + баннер TX @1M
; =====================================================================
START:  DI
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
        STA PREVST
        CALL REDRAW         ; "ACdE"
        LXI H,TXBAN         ; баннер: терминал 1M читает, 4800 = мусор
        CALL TXSTR

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
; DISPATCH: обработка кода клавиши (A). F1 - глобально в меню,
; F2 - глобально показать адрес (повторное F2 - назад).
; NEW в меню: B = загрузчик Intel HEX (SID 4800), F = RAM-тест.
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
DSV:    MOV A,C
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
DSP:    MOV A,C
        CPI K_ENT
        JZ PENT
        CPI 10h
        JC PDIG             ; 00h..0Fh - тетрада байта
        RET
PDIG:   MOV A,C
        MOV B,A
        LDA BF0
        STA BF1             ; сдвиг: BF1 = BF0
        MOV A,B
        STA BF0
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
DSA:    MOV A,C
        CPI K_ENT
        JZ AENT
        CPI 10h
        JC ADIG             ; 00h..0Fh - тетрада адреса
        RET
ADIG:   MOV A,C
        MOV B,A
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
        CPI 0Bh             ; 'B' - загрузчик Intel HEX (NEW)
        JZ KLD
        CPI 0Fh             ; 'F' - RAM-тест (NEW)
        JZ KRAM
        RET                 ; остальные - игнор
KLD:    CALL LOADM
        JMP K_F1E           ; реинициализация меню
KRAM:   CALL RAMT
        JMP K_F1E
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
        ; ждём отпускания всех клавиш + дебаунс
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
