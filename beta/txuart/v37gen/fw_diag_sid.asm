; =====================================================================
; beta/txuart/v37gen -- fw_diag_sid: ДИАГНОСТИКА RX-ПУТИ (SID) для платы
; retro_pcld (CPLD v37G01, XC95108). Одно назначение: показать, доходят
; ли ФРОНТЫ сигнала от терминала до пина CPU.SID.
;
;   ЧТО ДЕЛАЕТ: безостановочный опрос RIM (A7 = SID). Каждый ПАДАЮЩИЙ
;   фронт (1->0, как старт-бит UART) инкрементирует счётчик FALLC,
;   каждый ВОСХОДЯЩИЙ (0->1, как стоп-бит) - RISEC. Дисплей (динамическая
;   развёртка самим ЦП, без прерываний, ~70 Гц):
;       DIG3 DIG2  DIG1 DIG0   (слева направо)
;       [ FALLC  ] [ RISEC  ]  - два 8-битных счётчика, hex, wrap 00-FF.
;
;   КАК ЧИТАТЬ (терминал 4800 8N1, на плате светодиод = просто RESET):
;     FALL=00 RISE=00 при вводе текста        -> на SID НИЧЕГО не приходит:
;         линия CH340G.TXD -> P38 -> P73(CPU.SID) мертва. Проверить
;         провод/пин P38, наличие jed с транзитом SID<=RX в ПЛИС.
;     FALL=01 RISE=00 (застряло)              -> P38/SDI удерживается в 0
;         (провод на землю, CH340G не подключён/не в режиме).
;     FALL и RISE РАСТУТ ВМЕСТЕ при вводе     -> линия ЖИВА (каждый байт =
;         1 падение + 1 подъём). Если счётчики идут - проблема НЕ в
;         железе: проверять скорость (4800) и формат.
;     Хаотичное дёрганье обоих счётчиков без ввода -> вход висит в
;         воздухе (наводки): тот же вывод - провод до P38 отсутствует.
;
;   ВЫХОД - RESET (SW20). После диагностики прошить обратно
;   fw_monitor_ACdE_tm_xstream_v2_0_3.hex (offset 0000h).
;
; ПОРТЫ (v37G01): 00h = сегменты D6-D0 (D0=a..D6=g, 1=горит), 01h =
; разряды D3-D0 (1=горит), D4 = SND. RAM: PREV=FFE8h, FALLC=FFE9h,
; RISEC=FFEAh. Прерывания НЕ используются (IE=0 после сброса; RIM
; работает всегда). CPU 3,125 МГц.
; Сборка: python3 ../../../tools/asm85.py fw_diag_sid.asm -o
;         fw_diag_sid.hex -l fw_diag_sid.lst   (кодировка CP1251)
; =====================================================================

SEGP    EQU 00h             ; сегменты
DIGP    EQU 01h             ; разряды + SND

PREV    EQU 0FFE8h          ; предыдущий уровень SID (00h/80h)
FALLC   EQU 0FFE9h          ; счётчик падающих фронтов (wrap 8 бит)
RISEC   EQU 0FFEAh          ; счётчик восходящих фронтов (wrap 8 бит)

        ORG 0000h
        JMP START

        ORG 0008h
        RET                 ; RST 1 - заглушки (IE=0, сюда не попадаем)
        ORG 0010h
        RET
        ORG 0018h
        RET
        ORG 0020h
        RET
        ORG 0024h
        RET                 ; TRAP
        ORG 0028h
        RET
        ORG 0030h
        RET
        ORG 0038h
        RET
        ORG 003Ch
        RET                 ; RST 7.5 - джиффи-вектор, в diag не нужен

; ---------------------------------------------------------------------
        ORG 0040h
START:  LXI SP,0FFE7h       ; стек в ОЗУ (1-2 уровня CALL)
        XRA A
        OUT SEGP            ; сегменты blank
        OUT DIGP            ; разряды off
        STA FALLC           ; счётчики = 0
        STA RISEC
        RIM                 ; текущий уровень SID -> PREV
        ANI 80h             ; (без фантомного фронта на старте)
        STA PREV

; ---- главный цикл: 4 слота развёртки, в каждом - непрерывный опрос SID
MAIN:   LDA FALLC           ; старшая тетрада FALLC -> DIG3 (левый)
        CALL GNIBH
        MVI B,08h
        CALL SLOT
        LDA FALLC           ; младшая тетрада FALLC -> DIG2
        CALL GNIBL
        MVI B,04h
        CALL SLOT
        LDA RISEC           ; старшая тетрада RISEC -> DIG1
        CALL GNIBH
        MVI B,02h
        CALL SLOT
        LDA RISEC           ; младшая тетрада RISEC -> DIG0 (правый)
        CALL GNIBL
        MVI B,01h
        CALL SLOT
        JMP MAIN

; ---------------------------------------------------------------------
; GNIBH/GNIBL: A (байт счётчика) -> A = глиф старшей/младшей тетрады.
GNIBH:  RRC
        RRC
        RRC
        RRC
GNIBL:  ANI 0Fh
        MOV E,A
        MVI D,00h
        LXI H,GTBL
        DAD D
        MOV A,M
        RET

; ---------------------------------------------------------------------
; SLOT: показать глиф (A) на разряде (B) ~3 мс, всю паузу опрашивая SID
; и считая фронты. Портит A/C/D, B сохраняет.
SLOT:   OUT SEGP            ; глиф на сегменты
        MOV A,B
        OUT DIGP            ; один разряд горит
        MVI D,0C8h          ; ~200 итераций x ~15-18 мкс ~ 3 мс
SLOT1:  RIM                 ; A7 = SID
        ANI 80h
        MOV C,A             ; C = текущий уровень (00h/80h)
        LDA PREV
        CMP C               ; уровень не менялся?
        JZ  SLOT2
        MOV A,C
        STA PREV            ; запомнить новый уровень
        ORA A               ; S = текущий уровень
        JM  SLOTUP          ; 0->1 = восходящий фронт
        LDA FALLC           ; 1->0 = падающий (старт-бит-подобный)
        INR A
        STA FALLC
        JMP SLOT2
SLOTUP: LDA RISEC
        INR A
        STA RISEC
SLOT2:  DCR D
        JNZ SLOT1
        RET

; ---- глифы 7-сегм (как в мониторе v2.0.3: D0=a..D6=g, 1=горит) ----
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
