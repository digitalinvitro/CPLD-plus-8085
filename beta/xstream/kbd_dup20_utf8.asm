; =====================================================================
; beta/xstream -- kbd_dup20: ДЕМО "КЛАВИША ПЛАТЫ -> 20 КОПИЙ СИМВОЛА
; В ОКНЕ ПК" (вопрос владельца 11-14; ввод по директиве C монитора ACdE)
;
; СЦЕНАРИЙ:
;   E -> программа крутит скан матрицы 4x5 (порты 02h/03h, как в
;   мониторе) и ЖДЁТ цифровую клавишу 0..F. Пока ждёт - поддерживает
;   регенерацию индикатора (CALL REFRESH) и SW-тик XSTREAM (CALL XSCHK,
;   A=1): окно ПК ПРОДОЛЖАЕТ обновляться, хотя монитор уже не крутится
;   ("8085 выдаёт экран и работает по своим делам" - прямо из E).
;   Поймав клавишу: row*4+col -> KEYTBL (ROM fw) -> код 00..0F ->
;   XHEX (ROM fw) -> ASCII '0'..'F' -> символ пишется 20 раз в строку
;   24 экрана (B780h..B793h), затем RET (C9) -> монитор. Ближайший кадр
;   XSTREAM (~50 мс) показывает 20 копий внизу окна ПК. Повторный пуск
;   (A 8000 Enter, E) с новой клавишей ПЕРЕзаписывает те же 20 ячеек.
;   Enter/F1/F2/пустая позиция (код >= 10h) - выход БЕЗ записи.
;
;   Ввод с клавиатуры ПК в v2.3 невозможен: CPLD TX-only (RX-ядра нет),
;   клиент xstream_view.ps1 только читает COM. Поэтому "клавиатура" -
;   матрица платы; "экран" - окно ПК (B000h..B7CFh).
;
; ROM-точки fw_mon ACdE + XSTREAM v1 (SW, md5 4175b2e80af125f562c969cfcedd7157):
;   SETTLE 0040h - пауза ~25 мкс; KEYTBL 0017h - таблица клавиш;
;   REFRESH 0067h - слот регенерации; XSCHK 0486h - SW-тик кадра;
;   XHEX 0569h - тетрада 0..15 -> ASCII '0'..'F'. Все - обычные
;   подпрограммы ROM, из пользовательской программы вызывать можно.
;
; ПАМЯТЬ: 8000h..8054h (85 Б), стек монитора, XBUF B000h..B7CFh.
; СБОРКА: python3 scripts/asm85.py kbd_dup20.asm -o kbd_dup20.hex -l kbd_dup20.lst
; СИМ:    scripts/sim_kbd_dup20.py (нажатие '7'/'F'/Enter, сверка буфера и кадров)
; =====================================================================

        ORG 8000h

; ---- ROM fw_mon ACdE + XSTREAM v1 (SW) ----
KBCOLP  EQU 02h             ; колонки матрицы (D3-D0, 1 = заведена)
KBROWP  EQU 03h             ; ряды матрицы (D4-D0, 1 = нажата)
SETTLE  EQU 0040h           ; ROM fw: пауза ~25 мкс
KEYTBL  EQU 0017h           ; ROM fw: таблица клавиш KEYTBL[row*4+col]
REFRESH EQU 0067h           ; ROM fw: слот регенерации 7-сегм. индикатора
XSCHK   EQU 0486h           ; ROM fw: SW-тик XSTREAM (A = добавка слотов)
XHEX    EQU 0569h           ; ROM fw: тетрада 0..15 -> ASCII '0'..'F'
XROW24  EQU 0B780h          ; строка 24 экрана: B000h + 24*80

; ---- программа ----
START:  MVI  D,01h          ; D = бит колонки 01h..08h
        MVI  E,00h          ; E = номер колонки 0..3
SCAN:   MOV  A,D
        OUT  KBCOLP         ; завели колонку
        CALL SETTLE         ; успокоение матрицы (~25 мкс, ROM)
        IN   KBROWP         ; ряды
        ANI  1Fh
        JNZ  FOUND          ; есть нажатие в этой колонке
        MOV  A,D
        RLC
        MOV  D,A
        INR  E
        CPI  10h            ; 4 колонки отсканированы?
        JNZ  SCAN
        CALL REFRESH        ; нажатий нет: слот индикатора (ROM)
        MVI  A,01h
        CALL XSCHK          ; SW-тик: кадр в UART идёт и в ожидании (ROM)
        JMP  START
; ---- нажатие поймано: A = биты рядов, E = колонка ----
FOUND:  PUSH PSW
        XRA  A
        OUT  KBCOLP         ; колонки off - фиксируем нажатие (как HIT в fw)
        POP  PSW
        MVI  C,00h          ; C = номер ряда (индекс младшего единичного бита)
RL:     RRC
        JC   GOT
        INR  C
        JMP  RL
GOT:    MOV  A,C
        RLC
        RLC                 ; A = row*4
        ADD  E              ; A = row*4 + col
        MOV  C,A
        MVI  B,00h
        LXI  H,KEYTBL       ; HL = KEYTBL + index (ROM fw)
        DAD  B
        MOV  A,M            ; A = код клавиши 00..0F (цифры), 10..12/FF
        CPI  10h
        JNC  EXIT           ; Enter/F1/F2/пусто - выход БЕЗ записи
        CALL XHEX           ; A = ASCII '0'..'F' (ROM fw)
        MOV  C,A            ; C = символ
        LXI  H,XROW24       ; HL = B780h: строка 24, колонка 0
        MVI  B,14h          ; 20 копий (14h = 20)
PUT:    MOV  M,C
        INX  H
        DCR  B
        JNZ  PUT
EXIT:   RET                 ; C9 -> монитор; кадр с новиной уйдёт через ~50 мс

        END
