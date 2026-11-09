; ======================================================================
;  TXSTRESS v1.0 — тест максимальной нагрузки на UART TX
;  Плата: retro PC (8085 + XC95108, ядро TX в CPLD)
;  CPU: 8085 @ 3.125 МГц, T = 320 нс (v2.2: вход 25 МГц, /4)
;  Формат 8N1. Бит v2.2 (mod-16) = 1 562 500 бод;
;  бит diag (mod-25, фит 11-9 19:26) = 1 000 000 бод.
;
;  Порты:
;    OUT 04h   — данные TX (редакция v2.2)
;    OUT 05h   — данные TX (возможный новый порт в diag-редакции)
;    IN  05h   — бит 1: флаг ядра TX (bit_cnt==0)
;  TX_BOTH=1: каждый байт пишется в ОБА порта — работает при любом
;  раскладе; "чужой" порт — no-op. После подтверждения рабочего порта
;  соберите вариант с TX_BOTH=0 (файл txstress_v10_p04.hex) — темп выше.
;
;  Фазы (бесконечный цикл):
;   FLOOD  64 КБ, инкрементный байт, 42T/байт = 13.44 мкс = 74 405 Б/с
;          (74% линии на 1М, 48% на 1.5625М) — чисто всегда.
;          Лендмарк "B=xxxx" каждые 8 КБ.
;   SPRINT 16 КБ, 'U', 31T/байт = 9.92 мкс = 100 807 Б/с
;          (на 1М — впритык к границе стоп-бита; на 1.5625М — 64%, чисто)
;   BURST   8 КБ, порт 04h ТОЛЬКО, 14.875T/байт = 4.76 мкс = 210 084 Б/с
;          — честный ПЕРЕГРУЗ на обеих скоростях: мусор в терминале —
;          НОРМА. Критерий: "BURST OK" после мусора печатается чисто
;          (ядро не клинит). Тишина в BURST = порт записи уехал на 05h.
;
;  Замер скорости: PuTTY -> Log -> All session output; между "SPRINT" и
;  "SPRINT OK" ровно 16 384 байта данных (+ строки маркеров).
;
;  Сборка: python3 asm8085.py txstress_v10.asm <имя> [TX_BOTH=0]
; ======================================================================

TXPORT1 EQU 004h
TXPORT2 EQU 005h
TX_BOTH EQU 1

        ORG 0000h
; ---------------------- сброс ----------------------
        DI
        LXI D,4000h        ; пауза ~126 мс: POR CPLD, успокоение шины
PORLP:  DCX D
        MOV A,D
        ORA E
        JNZ PORLP

; ===================== основной цикл =====================
FOREVER:
        LXI D,0000h        ; счётчик блоков FLOOD (печатается)
        MVI C,000h         ; стартовый байт паттерна
        LXI H,M_BAN
PBAN:   MOV A,M
        ORA A
        JZ PBAND
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        INX H
        JMP PBAN
PBAND:

; ---------- FLOOD: 256 блоков x 256 Б, 42T/байт ----------
FLOOD:  MVI B,000h         ; 256 байт в блоке
FIN:    MOV A,C
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        INR C
        DCR B
        JNZ FIN            ; блок = 42T x 256 = 10 752T
        INX D
        MOV A,D
        ANI 01Fh
        JNZ FLC            ; каждые 32 блока (8 КБ) — лендмарк
        LXI H,M_EQ
PB2:    MOV A,M
        ORA A
        JZ PB2D
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        INX H
        JMP PB2
PB2D:   MOV A,D            ; D, старший ниббл
        RRC
        RRC
        RRC
        RRC
        ANI 00Fh
        ADI 090h
        DAA
        ACI 040h
        DAA
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        MOV A,D            ; D, младший
        ANI 00Fh
        ADI 090h
        DAA
        ACI 040h
        DAA
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        MOV A,E            ; E, старший
        RRC
        RRC
        RRC
        RRC
        ANI 00Fh
        ADI 090h
        DAA
        ACI 040h
        DAA
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        MOV A,E            ; E, младший
        ANI 00Fh
        ADI 090h
        DAA
        ACI 040h
        DAA
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        LXI H,M_CRLF
PB3:    MOV A,M
        ORA A
        JZ PB3D
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        INX H
        JMP PB3
PB3D:
FLC:    MOV A,D
        CPI 001h           ; DE = 0100h -> FLOOD закончен (64 КБ)
        JZ FDONE
        JMP FLOOD
FDONE:  LXI H,M_FLOK
PB4:    MOV A,M
        ORA A
        JZ PB4D
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        INX H
        JMP PB4
PB4D:

; ---------- SPRINT: 64 блока x 256 Б, 'U', 31T/байт ----------
        MVI C,055h
        LXI H,0040h
SPR:    MVI B,080h         ; 128 проходов x 2 байта
SPIN:   MOV A,C
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        MOV A,C
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        DCR B
        JNZ SPIN           ; проход = 62T -> 31T/байт
        DCX H
        MOV A,H
        ORA L
        JNZ SPR
        LXI H,M_SPROK
PB6:    MOV A,M
        ORA A
        JZ PB6D
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        INX H
        JMP PB6
PB6D:

; ---------- BURST: 32 блока x 256 Б, порт 04h, 14.875T/байт (перегруз) --
        LXI H,0020h
BUR:    MVI B,010h         ; 16 проходов x 16 байт
BUIN:   MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        MOV A,C
        OUT TXPORT1
        DCR B
        JNZ BUIN           ; проход = 238T -> 14.875T/байт
        DCX H
        MOV A,H
        ORA L
        JNZ BUR
        MVI B,020h         ; пауза ~143 мкс (слить искорёженный кадр)
SDL:    DCR B
        JNZ SDL
        LXI H,M_BROK
PB8:    MOV A,M
        ORA A
        JZ PB8D
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        INX H
        JMP PB8
PB8D:
        JMP FOREVER

; ---------------------- строки ----------------------
M_BAN:  DB 00Dh,00Ah
        DB "TXSTRESS v1.0"
        DB 00Dh,00Ah,000h
M_EQ:   DB "B=",000h
M_CRLF: DB 00Dh,00Ah,000h
M_FLOK: DB "FLOOD OK",00Dh,00Ah,000h
M_SPROK: DB "SPRINT OK",00Dh,00Ah,000h
M_BROK: DB "BURST OK",00Dh,00Ah,000h
        END
