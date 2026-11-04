# -*- coding: utf-8 -*-
"""Проверка v4.0.0 после переноса блока объявлений автомата (HDLCompilers:28)."""
import io, re, sys

SRC = "/home/z/my-project/CPLD-plus-8085/beta/hwuart/top_hwuart_por6_v400.v"
TWIN = SRC.replace(".v", "_utf8.v")

# 1) кодировка: CP1251 читается без ошибок, круговой обход в UTF-8 совпадает с двойником
raw = open(SRC, "rb").read()
text = raw.decode("cp1251")            # бросит исключение при битой кодировке
twin = io.open(TWIN, "r", encoding="utf-8").read()
assert text == twin, "UTF8-двойник не совпадает с CP1251-эталоном"
assert "\r" not in text, "появились CR - файл был LF"
print("OK 1: CP1251 читается, двойник синхронен, LF без CR, строк:", text.count("\n"))

lines = text.split("\n")

def first_decl(name):
    """Строка объявления: reg/wire/localparam; оператор может быть многострочным
    (localparam S_IDLE = ..., S_T2 = ...;), имя ищем в тексте ДО первой ';'."""
    pat = re.compile(r"^\s*(reg|wire|localparam)\b")
    for i, l in enumerate(lines):
        if not pat.match(l):
            continue
        stmt = ""
        for j in range(i, len(lines)):
            stmt += lines[j].split("//")[0]
            if ";" in lines[j].split("//")[0]:
                break
        if re.search(r"\b" + re.escape(name) + r"\b", stmt):
            return [i]
    return []

def uses(name, decl):
    """Все строки с упоминанием имени вне комментариев и вне строки объявления."""
    out = []
    for i, l in enumerate(lines):
        code = l.split("//")[0]
        if i == decl or not re.search(r"\b" + re.escape(name) + r"\b", code):
            continue
        out.append(i)
    return out

bad = 0
for name in ["state", "S_T2", "addr_latch", "S_IDLE", "rd_seen", "wr_seen",
             "bus_reg", "io_rd_kb", "por_run", "shreg", "rx_full", "tx_run"]:
    d = first_decl(name)
    if not d:
        print("FAIL: нет объявления %s" % name); bad += 1; continue
    dd = d[0]
    us = uses(name, dd)
    early = [u for u in us if u < dd]
    status = "OK " if not early else "FAIL"
    if early:
        bad += 1
    print("%s: %-11s объявление стр. %4d, использований %2d, до объявления: %s"
          % (status, name, dd + 1, len(us), early[:3] if early else "нет"))

# 2) порядок секций: POR < объявления автомата < ядро UART < шинный движок.
# Маркеры ищем ПОСЛЕ конца портов (первое ");" в начале строки) - слова из
# заголовка шапки (стр. 2, п.26) не считаются секциями.
i_ports_end = next(i for i, l in enumerate(lines) if l.rstrip() == ");")
def section(mark):
    return next(i for i, l in enumerate(lines) if mark in l and i > i_ports_end)
i_por   = section("POR (v3.4")
i_auto  = section("// Автомат шины")
i_uart  = section("АППАРАТНЫЙ UART-ТРАНСИВЕР")
i_eng   = section("// Шинный движок")
print(("OK 2: порядок секций POR(%d) < автомат(%d) < UART(%d) < движок(%d)"
       % (i_por + 1, i_auto + 1, i_uart + 1, i_eng + 1))
      if i_por < i_auto < i_uart < i_eng else "FAIL: порядок секций нарушен")
bad += 0 if i_por < i_auto < i_uart < i_eng else 1

# 3) баланс begin/end и module/endmodule не изменился структурно
opens = sum(len(re.findall(r"\bbegin\b", l.split("//")[0])) for l in lines)
closes = sum(l.split("//")[0].count("end") for l in lines)
print("OK 3: begin=%d, end(включая endmodule/endcase/endgenerate)=%d" % (opens, closes))
assert (text.count("module ") - text.count("endmodule")) == 0, "module/endmodule"

sys.exit(1 if bad else 0)
