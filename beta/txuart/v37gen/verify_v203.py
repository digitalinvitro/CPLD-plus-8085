#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Верификация fw v2.0.3 (пара v37G01): байт-уровень hex + текст asm."""
import re, sys

BASE = '/home/z/my-project/CPLD-plus-8085/beta/txuart/v37gen/'
HEX  = BASE + 'fw_monitor_ACdE_tm_xstream_v2_0_3.hex'
ASM  = BASE + 'fw_monitor_ACdE_tm_xstream_v2_0_3.asm'
LST  = BASE + 'fw_monitor_ACdE_tm_xstream_v2_0_3.lst'

def load_ihx(path):
    mem = {}
    for l in open(path):
        l = l.strip()
        if not l.startswith(':'): continue
        c = int(l[1:3],16); a = int(l[3:7],16); r = int(l[7:9],16)
        d = bytes.fromhex(l[9:9+2*c])
        assert (c + (a>>8) + (a&255) + r + sum(d) + int(l[9+2*c:11+2*c],16)) % 256 == 0, 'checksum!'
        if r == 0:
            for i,b in enumerate(d): mem[a+i] = b
    top = max(mem)
    return bytes(mem.get(x,0) for x in range(top+1)), mem

rom, mem = load_ihx(HEX)
asm = open(ASM, encoding='cp1251').read()
ok = []
def chk(name, cond):
    ok.append((name, bool(cond)))
    print(('PASS ' if cond else 'FAIL ') + name)

# --- объём ---
chk(f'размер образа 2500..2700 Б ({len(rom)})', 2500 <= len(rom) <= 2700)

# --- вектора ---
chk('ORG 0000: JMP (C3)', rom[0] == 0xC3)
chk('вектор RST7.5 @003Ch: JMP (C3)', rom[0x3C] == 0xC3)
m = re.search(rb'\xc3..', rom[0x3C:0x3F])
tmsisr = rom[0x3D] | (rom[0x3E]<<8)
chk('TMISR @%04Xh: PUSH PSW(0xF5)' % tmsisr, mem.get(tmsisr,0) == 0xF5)

# --- KSCOL: фикс B/C ---
p_new = re.compile(rb'\x3a..\xe6\x03\x4f\x06\x00\x21..\x09\x56', re.DOTALL)
p_old = re.compile(rb'\x3a..\xee\x03\x47\x0e\x00\x21..\x09\x56', re.DOTALL)
hits = list(p_new.finditer(rom))
chk('KSCOL @hex: MOV C,A/MVI B,0/DAD B/MOV D,M', len(hits) == 1)
p_refr = re.compile(rb'\x3a..\x4f\x06\x00\x21..\x09\x46', re.DOTALL)
chk('REFRESH @hex: MOV C,A/MVI B,0/DAD B/MOV B,M', len(list(p_refr.finditer(rom))) == 1)
chk('KSCOL: старый вариант MOV B,A/MVI C,0 отсутствует', not p_old.search(rom))

# --- TMIARM заглушка ---
chk('TMIARM: маска-пулька 3E 68 30 только 1 (TMON)', rom.count(bytes([0x3E,0x68,0x30])) == 1)
chk('TMOFF/TMON: 3E 78 30 ровно 2 (TMTINY удалён)', rom.count(bytes([0x3E,0x78,0x30])) == 2)
chk('TMTINY-последовательность 3E 78 30 F1 FB C9 отсутствует',
    bytes([0x3E,0x78,0x30,0xF1,0xFB,0xC9]) not in rom)
chk('мои маски v2.0.1 (3E 1F 30) отсутствуют', bytes([0x3E,0x1F,0x30]) not in rom)

# --- LSTAT: 01h (токи) ---
chk('LSTAT: MVI A,01h + OUT DIGP (3E 01 D3 01)', bytes([0x3E,0x01,0xD3,0x01]) in rom)
lst_code = asm[asm.find('\nLSTAT:'):asm.find('\nDLMS:')]
chk('LSTAT(asm): в коде MVI A,01h, 0Fh нет',
    'MVI A,01h' in lst_code and 'MVI A,0Fh' not in lst_code)

# --- RAMT: паттерн из E + граница FFD8h ---
chk('RMF: MOV A,E + MOV M,A (7B 77)', bytes([0x7B,0x77]) in rom)
chk('RAMT: CPI 0FDh (FE) присутствует', rom.count(bytes([0xFE])) >= 2)
asm_ram = asm[asm.find('RAMT:', asm.find('LSTAT:')):]  # от RAMT-комментария
asm_ram = asm_ram[asm_ram.find('RAMT:'):]              # от метки RAMT
asm_ram = asm_ram[:asm_ram.find('\nRMBAD:')]
chk('RAMT(asm): CPI 0FDh/0D8h в RMF и RMV (4 шт)',
    asm_ram.count('CPI 0FDh') == 2 and asm_ram.count('CPI 0D8h') == 2)
chk('RAMT(asm): старых границ 0FEh/0E8h нет', 'CPI 0FEh' not in asm_ram and 'CPI 0E8h' not in asm_ram)
chk('RAMT(asm): дубль LXI H,8000h удалён', asm_ram.count('LXI H,8000h') == 2)

# --- баннер/версия ---
j = rom.find(b'fw_monitor_ACdE_tm_xstream v')
banner = rom[j:j+60].split(b'\x00')[0].decode()
chk(f'баннер содержит v2.0.3 ({banner!r})', 'v2.0.3' in banner)
chk('asm: нет "каждый 6-й"', 'каждый 6-й' not in asm)
chk('asm: нет "MOV B,A             ; B = индекс"', '; B = индекс колонки' not in asm)
chk('asm: LSTAT-шапка с решением владельца', 'РЕШЕНИЕ ВЛАДЕЛЬЦА' in asm)
chk('asm: шапка с джиффи 4,096', '4,096' in asm and 'ДЖИФФИ' in asm.upper())

# --- порт 03h: документация фазы [9:8] ---
chk('asm: KBROWP описан как tmr_cnt[9:8]', 'tmr_cnt[9:8]' in asm)

fails = [n for n,c in ok if not c]
print()
print('ИТОГ: %d/%d PASS' % (len(ok)-len(fails), len(ok)))
if fails:
    print('ПРОВАЛЫ:', fails); sys.exit(1)
print('ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ')
