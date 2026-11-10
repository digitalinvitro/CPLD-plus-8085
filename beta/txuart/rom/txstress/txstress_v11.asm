; ======================================================================
;  TXSTRESS v1.1 — тест максимальной нагрузки на UART TX
;  Плата: retro PC (8085 + XC95108, ядро TX в CPLD v2.3, 1 000 000 бод)
;  CPU: 8085 @ 3.125 МГц, T = 320 нс (вход 25 МГц, /4, шунт H1)
;  Формат 8N1. Кадр 10 мкс = 31.25T.
;
;  ЧЕНДЖЛОГ v1.1 (по итогам трёх прогонов 11-10, COM13 1М, TX_BOTH=1:
;  баннер "TXSTRESS v1.0" не пойман ни разу за 60 с, поток ~59.6 КБ/с
;  непрерывно):
;   1) ИСПРАВЛЕН БАГ ЛЕНДМАРКОВ v1.0: гейт "MOV A,D / ANI 01Fh" смотрел
;      СТАРШИЙ байт счётчика DE, который весь первый килоблок (DE=0000h..
;      00FFh) равен 00h -> лендмарк печатался КАЖДЫЙ блок (256 строк
;      "B=00xx" за FLOOD вместо 7), темп FLOOD падал до ~43.9T/Б.
;      Теперь гейт по МЛАДШЕМУ байту: (E&1F)==0 И E/=0 -> РОВНО 7
;      лендмарков B=0020..00E0 за FLOOD, 1-в-1 с ожиданиями
;      uart_speed.ps1 (expectedLm) и эталон-генератором.
;   2) Лендмарк несёт токен синхронизации: "B=xxxx TXSTRESS\r\n" — поток
;      сам называет себя каждые 8 КБ (~107 мс), даже если баннер цикла
;      не пойман: PC-сторона доказуемо видит, что исполняется TXSTRESS,
;      и где внутри FLOOD она находится.
;   3) POR-пауза 126 -> 503 мс (LXI D,0000h): запас открыть
;      терминал/скрипт до первого баннера.
;   4) Пауза ~19.7 мс тишины перед баннером каждого цикла: баннер выходит
;      из чистого idle, PC-стороне легче поймать старт цикла; хвост
;      "BURST OK -> баннер" остаётся пустым по байтам (только время).
;   Темпы фаз НЕ тронуты (FLOOD 42T, SPRINT 31T, BURST 14.875T) — все
;   ожидания темпов v1.0 действительны. Баннер: "TXSTRESS v1.1".
;
;  Порты:
;    OUT 04h   — данные TX (редакция v2.3)
;    OUT 05h   — данные TX (возможный алиас в других редакциях ядра)
;    IN  05h   — бит 1: флаг ядра TX (bit_cnt==0)
;  TX_BOTH=1: каждый байт пишется в ОБА порта — работает при любом
;  раскладе; "чужой" порт — no-op. Для темпа выше соберите вариант
;  TX_BOTH=0 (txstress_v11_p04.hex): FLOOD 32T/Б = 97 656 Б/с.
;
;  Фазы (бесконечный цикл, ~1.107 с):
;   FLOOD  64 КБ, инкрементный байт +1 mod 256, 42T/байт = 74 405 Б/с
;          (74% линии 1М) — чисто всегда. Лендмарк "B=xxxx TXSTRESS"
;          каждые 32 блока (8 КБ), ровно 7 за фазу: 0020..00E0.
;   SPRINT 16 КБ записей 'U', 31T/байт = 100 807 Б/с записи; на 1М кадр
;          31.25T > 31T -> принимается КАЖДЫЙ 2-Й = 50 403 Б/с.
;   BURST   8 КБ, порт 04h ТОЛЬКО, 14.875T/байт = 210 084 Б/с записи —
;          честный ПЕРЕГРУЗ: принимается ~каждый 3-й (~70 028 Б/с),
;          кадры целы, мусор в терминале — НОРМА. Критерий: "BURST OK"
;          после мусора печатается чисто (ядро не клинит).
;
;  Сборка: python3 asm8085.py txstress_v11.asm <имя> [TX_BOTH=0]
;  PC-сторона: scripts/uart_speed.ps1 v1.2 (фазы по маркерам, сырая
;  диагностика без баннера, hexdump первых байт, -Probe, -SaveRaw).
; ======================================================================

TXPORT1 EQU 004h
TXPORT2 EQU 005h
TX_BOTH EQU 1

        ORG 0000h
; ---------------------- сброс ----------------------
        DI
        LXI D,0000h        ; пауза ~503 мс: POR CPLD, успокоение шины,
PORLP:  DCX D              ; запас открыть терминал/скрипт до 1-го баннера
        MOV A,D
        ORA E
        JNZ PORLP

; ===================== основной цикл =====================
FOREVER:
        LXI D,0000h        ; счётчик блоков FLOOD (идёт в лендмарк "B=xxxx")
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
        MOV A,E            ; гейт лендмарка по МЛАДШЕМУ байту DE.
        ANI 01Fh           ; ФИКС v1.1: в v1.0 гейт смотрел D (старший
        JNZ FLC            ; байт) — весь первый килоблок D=00h, лендмарк
        MOV A,E            ; печатался КАЖДЫЙ блок. Теперь: кратен 32
        ORA A              ; блокам (E&1F==0) и E/=0 -> ровно 7 лендмарков
        JZ FLC             ; 0020..00E0; на выходе (DE=0100h, E=0) нет.
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
        LXI H,M_TOK2       ; токен синхронизации " TXSTRESS\r\n":
PB2T:   MOV A,M            ; каждые 8 КБ поток сам называет себя,
        ORA A              ; даже если баннер цикла не пойман
        JZ PB2TD
        OUT TXPORT1
IF TX_BOTH
        OUT TXPORT2
ENDIF
        INX H
        JMP PB2T
PB2TD:
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
PB8D:   LXI D,0A00h        ; пауза ~19.7 мс тишины: баннер нового цикла
GAPLP:  DCX D              ; выходит из чистого idle — PC-стороне легче
        MOV A,D            ; поймать старт цикла; байтов в хвосте нет
        ORA E
        JNZ GAPLP
        JMP FOREVER

; ---------------------- строки ----------------------
M_BAN:  DB 00Dh,00Ah
        DB "TXSTRESS v1.1"
        DB 00Dh,00Ah,000h
M_EQ:   DB "B=",000h
M_TOK2: DB " TXSTRESS",00Dh,00Ah,000h
M_FLOK: DB "FLOOD OK",00Dh,00Ah,000h
M_SPROK: DB "SPRINT OK",00Dh,00Ah,000h
M_BROK: DB "BURST OK",00Dh,00Ah,000h
        END
