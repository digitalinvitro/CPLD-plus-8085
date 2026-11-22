; fw_test_rx_ok -- самотест приёма, УНИВЕРСАЛЬНЫЙ (v2.0.4/v2.0.5/v2.0.5G+)
; ORG 8000, длина 231 байт, сумма образа == 0 mod 256
; БЕЗ CALL В ROM: задержка ~1 мс инлайн (MVI D,208 + 208x DCR/JNZ = 3127T).
; RAM-ссылки: SNDST=0FFE8h, DIGIMG0..3=0FFF5h-FFF8h, экран B000h,
; вход E=RUN: SP=FFE6h, [FFE6h]=MONRET, EI, B/C/D/E=0, длительности в E
; История: v1 CALL DLMS 0359h -- на v2.0.5G DLMS=035Dh, CALL 0359h
;          попадал на OUT SEGP/POP B/RET -> бип молча пропадал.
; Сборка: scripts/make_rxok_test.py

8000:            ; START:
8000: 21 00 80    LXI H 32768
8003: 0e e7       MVI C LEN
8005: af          XRA A
8006:            ; CKL:
8006: 86          ADD M
8007: 23          INX H
8008: 0d          DCR C
8009: c2 06 80    JNZ CKL
800C: f5          PUSH PSW
800D: 21 00 b0    LXI H 45056
8010: 11 96 80    LXI D MSG
8013: 0e 50       MVI C 80
8015:            ; WR1:
8015: 1a          LDAX D
8016: 77          MOV M A
8017: 23          INX H
8018: 13          INX D
8019: 0d          DCR C
801A: c2 15 80    JNZ WR1
801D: f1          POP PSW
801E: b7          ORA A
801F: ca 38 80    JZ GOOK
8022: 3e 2d       MVI A 45
8024: 32 00 b0    STA 45056
8027: 3e 79       MVI A 121
8029: 32 f5 ff    STA 65525
802C: 32 f6 ff    STA 65526
802F: 32 f7 ff    STA 65527
8032: 32 f8 ff    STA 65528
8035: c3 4c 80    JMP TONE
8038:            ; GOOK:
8038: 3e 71       MVI A 113
803A: 32 f8 ff    STA 65528
803D: 3e 77       MVI A 119
803F: 32 f7 ff    STA 65527
8042: 3e 39       MVI A 57
8044: 32 f6 ff    STA 65526
8047: 3e 79       MVI A 121
8049: 32 f5 ff    STA 65525
804C:            ; TONE:
804C: 26 03       MVI H 3
804E:            ; BP:
804E: 1e c8       MVI E 200
8050: cd 68 80    CALL BTONE
8053: 1e 96       MVI E 150
8055: cd 8b 80    CALL BGAP
8058: 25          DCR H
8059: c2 4e 80    JNZ BP
805C: 26 05       MVI H 5
805E:            ; H2:
805E: 1e c8       MVI E 200
8060: cd 8b 80    CALL BGAP
8063: 25          DCR H
8064: c2 5e 80    JNZ H2
8067: c9          RET 
8068:            ; BTONE:
8068: 3a e8 ff    LDA 65512
806B: f6 02       ORI 2
806D: 32 e8 ff    STA 65512
8070:            ; BT1:
8070: 3a e8 ff    LDA 65512
8073: ee 01       XRI 1
8075: 32 e8 ff    STA 65512
8078: 16 d0       MVI D 208
807A:            ; BT2:
807A: 15          DCR D
807B: c2 7a 80    JNZ BT2
807E: 1d          DCR E
807F: c2 70 80    JNZ BT1
8082: 3a e8 ff    LDA 65512
8085: e6 fd       ANI 253
8087: 32 e8 ff    STA 65512
808A: c9          RET 
808B:            ; BGAP:
808B: 16 d0       MVI D 208
808D:            ; BG1:
808D: 15          DCR D
808E: c2 8d 80    JNZ BG1
8091: 1d          DCR E
8092: c2 8b 80    JNZ BGAP
8095: c9          RET 
8096:            ; MSG:
8096: 2b 20 52 58 20 4f 4b 20 76 32 2e 30 2e 35 47 20 52 4c 43 2d 46 49 58 20 4c 4f 41 44 4d 2d 3e 38 30 30 30 20 45 3d 52 55 4e 20 42 45 45 50 2b 46 41 43 45 2b 43 52 43 20 4f 4b 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 DB b'+ RX OK v2.0.5G RLC-FIX LOADM->8000 E=RUN BEEP+FACE+CRC OK                      '
80E6:            ; CHK:
80E6: 1E          DB CHK = 1Eh (сумма образа = 0)
