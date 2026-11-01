#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_decl_order.py — статическая проверка Verilog: объявление раньше
использования.

Зачем: однопроходные компиляторы Verilog (фронт-енд XST — «HDLCompilers»,
а также iverilog) требуют, чтобы идентификатор был объявлен ДО первого
использования в исходном тексте; нарушение — ERROR:HDLCompilers:28
"'x' has not been declared" — всплывает у владельца только внутри медленного
ISE. Скрипт ловит весь этот класс за секунды ДО запуска ISE. Написан после
провала компиляции txclient v6 (17 ошибок: объявления сериализатора стояли
ниже мест использования — al_shift/br_shift читались в шинном движке,
bit_cnt/tx_byte в in_cap/in_frame).

Проверяемые правила:
  1) использование имени раньше строки объявления — ошибка (как у
     однопроходного компилятора);
  2) имя, которого нет ни в одной живой области видимости, — ошибка;
     исключение — левая часть assign: необъявлённое имя создаёт implicit
     net (легально), регистрируем его как объявление уровня модуля;
  3) повторное объявление в ОДНОЙ области — ошибка (двойники с одним именем
     в разных ветках generate — легальны, это разные области).
Области: module / begin..end (в т.ч. именованные ветки generate begin : имя)
/ function / task — стек, как у однопроходного компилятора.

Эвристики заточены на стиль RTL этого репозитория (плоские модули без
инстансов, атрибуты (* keep *), sized-литералы, `директивы). НЕ замена
iverilog: только класс «объявление/использование».

Проверено на регрессии:
  - top_txclient_v6_utf8.v ДО правки — ровно 15 нарушений (у XST 17: 'tx_byte'
    на строке 1469 встречается дважды и посчитано за два), набор совпадает
    с HDLCompilers:28 бит-в-бит;
  - top_txclient_v6_utf8.v ПОСЛЕ правки и v3.9.2 — 0 нарушений;
  - top_txclient_v5_utf8.v — 14 «нарушений»: в v5 тот же порядок «mux выше
    объявлений», который XST ПРОПУСТИЛ (v5 скомпилировался и дошёл до
    плейсмента — в его .rpt нет ни одной HDLCompilers). Проверка сознательно
    строже XST: объявление должно опережать использование ВЕЗДЕ — тогда
    исходник проходит любой компилятор (в т.ч. iverilog, которым владелец
    гоняет tb; strict-режим избавляет от догадок, чей фронт-енд что допускает).

Использование:
  python3 check_decl_order.py file.v [file2.v ...]
Код возврата: 0 — чисто; 1 — есть нарушения; 2 — файл не читается.
"""
import re
import sys

KEYWORDS = set("""always and assign automatic begin buf bufif0 bufif1 case
casex casez cell cmos config deassign default defparam design disable edge
else end endcase endconfig endfunction endgenerate endmodule endprimitive
endspecify endtable endtask event for force forever fork function generate
genvar highz0 highz1 if ifnone incdir include initial inout input instance
integer join large liblist library localparam macromodule medium module
nand negedge nmos nor noshowcancelled not notif0 notif1 or output parameter
pmos posedge primitive pull0 pull1 pulldown pullup pulsestyle_onevent
pulsestyle_ondetect rcmos real realtime reg release repeat rnmos rpmos rtran
rtranif0 rtranif1 scalared showcancelled signed small specify specparam
strong0 strong1 supply0 supply1 table task time tran tranif0 tranif1 tri
tri0 tri1 triand trior trireg unsigned use uwire vectored wait wand weak0
weak1 while wire wor xnor xor""".split())

NUM_RE = re.compile(r"\d*'[sS]?[bBoOdDhH][0-9a-fA-FxXzZ_?]+")
INT_RE = re.compile(r"\b\d+\b")
ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
STR_RE = re.compile(r'"(?:[^"\\]|\\.)*"')
ATTR_RE = re.compile(r"\(\*.*?\*\)", re.S)
BLOCK_RE = re.compile(r"/\*.*?\*/", re.S)
RANGE_RE = re.compile(r"\[[^\]]*\]")

DECL_KWS = ("input|output|inout|wire|reg|integer|genvar|real|time|event|"
            "localparam|parameter")
DECL_RE = re.compile(r"^\s*(%s)\b(.*)$" % DECL_KWS)
PARAM_ANY_RE = re.compile(r"\bparameter\s*(?:\[[^\]]*\])?\s*(\w+)")
MODULE_RE = re.compile(r"\bmodule\s+(\w+)")
ASSIGN_RE = re.compile(r"^\s*assign\b(.*)$")
LABEL_RE = re.compile(r"\bbegin\s*:\s*(\w+)|\bend\s*:\s*(\w+)")
CONT_NAME_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_$]*)\s*=")
SCOPE_PUSH = {"begin", "function", "task"}
SCOPE_POP = {"end", "endfunction", "endtask"}


def read_text(path):
    """Файлы репозитория — UTF-8 (двойники * _utf8.v) или CP1251."""
    for enc in ("utf-8", "cp1251"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"{path}: не удалось прочитать ни как UTF-8, ни как CP1251")


def strip_noise(text):
    """Убрать всё, что не является кодом: атрибуты, комментарии, строки,
    sized-литералы и целые числа. Разбивка на строки СОХРАНЯЕТСЯ."""
    text = ATTR_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), text)
    text = BLOCK_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), text)
    out = []
    for ln in text.split("\n"):
        ln = STR_RE.sub('""', ln)
        ln = re.sub(r"//[^\n]*", "", ln)
        ln = NUM_RE.sub(" ", ln)
        ln = INT_RE.sub(" ", ln)
        out.append(ln)
    return out


def split_top_commas(s):
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p for p in parts if p.strip()]


def decl_names_from_tail(tail):
    """Имена из хвоста объявления: до '=' верхнего уровня, без диапазонов
    [..] и ключевых слов.  'wire ALE,' -> ALE; 'adv_q = , ld_q = ' ->
    adv_q, ld_q; '[1:0] TXB_IDLE = , TXB_HI = ' -> TXB_IDLE, TXB_HI."""
    names = []
    for part in split_top_commas(tail):
        left = part.split("=", 1)[0]
        left = RANGE_RE.sub(" ", left)
        names.extend(t for t in ID_RE.findall(left) if t not in KEYWORDS)
    return names


def collect_module_names(lines):
    mods = set()
    for raw in lines:
        m = MODULE_RE.search(raw)
        if m:
            mods.add(m.group(1))
    return mods


def check_file(path, all_modules, errors):
    lines = strip_noise(read_text(path))
    mods_here = collect_module_names(lines)
    scopes = [{}]           # scopes[0] — область модуля; далее begin/func/task
    seen_any = set()        # все имена, встреченные объявленными где-либо
    pending_decl = False    # объявление не закрыто ';' — строка-продолжение

    def register(nm):
        if nm in scopes[-1]:
            errors.append(
                f"{path}:{lineno}: ПОВТОРНОЕ объявление '{nm}' "
                f"(впервые — строка {scopes[-1][nm]})")
        else:
            scopes[-1][nm] = lineno
            seen_any.add(nm)

    for lineno, raw in enumerate(lines, 1):
        s = raw.strip()
        if not s or s.startswith("`"):        # директивы компилятора — мимо
            continue
        # --- стек областей: begin/end/function/task (слева направо) ---
        for tok in ID_RE.findall(raw):
            if tok == "module":
                scopes, seen_any = [{}], set()
            elif tok in SCOPE_PUSH:
                scopes.append({})
            elif tok in SCOPE_POP and len(scopes) > 1:
                scopes.pop()
        # --- объявления (в т.ч. multi-line: localparam A = 1,
        #              B = 2;  — продолжение до ';' не начинается с ключевого
        #              слова и иначе выглядело бы «использованием») ---
        in_decl = pending_decl
        m = DECL_RE.match(raw)
        if m:
            in_decl = True
        if in_decl:
            if m:
                tail = m.group(2)
                for nm in decl_names_from_tail(tail):
                    register(nm)
            else:
                # Строка-продолжение объявления. НОВЫЕ имена — только в форме
                # "ИМЯ =" в начале строки (очередной элемент списка
                # объявлений). Продолжение ВЫРАЖЕНИЯ (wire x = a ? b :
                # продолжается строкой "(bit_cnt == 1) ? AH8 :") имён НЕ
                # добавляет — иначе '==' внутри выражения порождал бы ложные
                # "объявления" из правой части.
                tail = raw
                cm = CONT_NAME_RE.match(raw)
                if cm:
                    register(cm.group(1))
            pending_decl = ";" not in tail
        else:
            pending_decl = False
        for pm in PARAM_ANY_RE.finditer(raw):        # #(parameter X = ...)
            if pm.group(1) not in scopes[-1]:
                scopes[-1][pm.group(1)] = lineno
                seen_any.add(pm.group(1))
        mm = MODULE_RE.search(raw)
        if mm and mm.group(1) not in scopes[-1]:
            scopes[-1][mm.group(1)] = lineno
            seen_any.add(mm.group(1))
        # --- использование ---
        # LHS assign: implicit net — «объявление» уровня модуля, если имени
        # ещё нет нигде (por_ce-прецедент невозможен: он объявлен явно;
        # правило — на всякий случай, Verilog так и делает).
        exempt = set()
        am = ASSIGN_RE.match(raw)
        if am:
            lhs = am.group(1).split("=", 1)[0]
            for t in ID_RE.findall(lhs):
                if t in KEYWORDS:
                    continue
                exempt.add(t)
                if t not in seen_any:
                    scopes[0][t] = lineno
                    seen_any.add(t)
        skip_pos = set()
        for lm in LABEL_RE.finditer(raw):            # begin : метка
            skip_pos.add(lm.start(1) if lm.group(1) else lm.start(2))
        reported = set()
        for tm in ID_RE.finditer(raw):
            tok, st = tm.group(), tm.start()
            if tok in KEYWORDS or tok in mods_here or tok in all_modules:
                continue
            if st in skip_pos:
                continue
            prev = raw[st - 1] if st else ""
            nxt = raw[tm.end()] if tm.end() < len(raw) else ""
            if prev in ".$`" or nxt == ".":          # '.имя', 'имя.', $task, `macro
                continue
            if tok in exempt:
                continue
            found = None
            for sc in reversed(scopes):
                if tok in sc:
                    found = sc[tok]
                    break
            if found is None:
                key = (lineno, tok)
                if key not in reported:
                    reported.add(key)
                    errors.append(
                        f"{path}:{lineno}: '{tok}' has not been declared "
                        f"(HDLCompilers:28)")
            elif found > lineno:
                key = (lineno, tok)
                if key not in reported:
                    reported.add(key)
                    errors.append(
                        f"{path}:{lineno}: '{tok}' использовано ДО объявления "
                        f"(объявлено на строке {found}) — HDLCompilers:28")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    all_modules = set()
    for p in argv[1:]:
        all_modules |= collect_module_names(strip_noise(read_text(p)))
    errors = []
    for p in argv[1:]:
        check_file(p, all_modules, errors)
    if errors:
        print(f"НАРУШЕНИЙ: {len(errors)}")
        for e in errors:
            print("  " + e)
        return 1
    print("OK: объявления опережают использование, неявных имён нет "
          f"({len(argv) - 1} файл(ов))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
