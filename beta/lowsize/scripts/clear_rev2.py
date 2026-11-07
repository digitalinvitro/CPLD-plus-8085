#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clear_rev2.py (2026-11-07) - v3.9.8-clear РЕД.2: удаление мёртвого кода.

Директива владельца (11-7, после фита ред.1): «ты плохо почистил 398_clear,
например там остались неиспользуемые сигналы» (WARNING:Xst:1780: x2_q, x2_p,
x1_q, x1_p, x1_n, t0_q, cnt) «...кроме того в комментариях осталась
информация о тех блоках которые уже не реализуются в этой версии дизайна,
прибери тщательно».

Что делает РЕЖИМ apply:
  1. Читает beta/lowsize/top_suart_por6_v398_clear.v (CP1251, ред.1).
  2. ТЕЛО: вычеркивает legacy-ветки делителя g_div2/g_div4/g_div_even/
     g_div_odd и их регистры cnt/x1_q/t0_q/x1_p/x1_n/x2_q/x2_p +
     localparam MEV/NMOD/NHALF; переписывает комментарии секции узла.
  3. ШАПКА: переписывает абзац v3.9.8-clear (ред.2), п.17, п.23, TODO 3,
     чек-лист g)/h) - описания legacy-механики заменены на факт
     «вычеркнуто из RTL».
  4. Пишет clear (CP1251) + _utf8-двойник, хвост нормализуется до ровно
     одного \\n после endmodule.
  5. ВЕРИФИКАЦИЯ: тело clear == тело v398 минус манифест (правки только
     документированные); удалённые идентификаторы отсутствуют в коде без
     комментариев; ровно одна ветка generate (g_div2p5); CP1251
     round-trip; старые формулировки шапки удалены, новые присутствуют.

Режим verify (без аргументов) - только пункт 5, файлы не пишет.

Запуск: python3 scripts/clear_rev2.py [apply]   (из beta/lowsize/)
"""

import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))   # beta/lowsize/scripts
BASE = os.path.dirname(SCRIPT_DIR)                        # beta/lowsize
SRC_CLEAR      = os.path.join(BASE, "top_suart_por6_v398_clear.v")
SRC_CLEAR_UTF8 = os.path.join(BASE, "top_suart_por6_v398_clear_utf8.v")
SRC_BASE       = os.path.join(BASE, "top_suart_por6_v398.v")

REMOVED_IDS = ["cnt", "x1_q", "x1_p", "x1_n", "x2_q", "x2_p", "t0_q",
               "MEV", "NMOD", "NHALF"]

# ------------------------------------------------------------------ правки
# Каждая правка: (имя, старый_блок, новый_блок). old должен встретиться
# РОВНО ОДИН раз; новый записывается на его место. Порядок = порядок строк
# файла (проверяется).
EDITS = []

def E(name, old, new):
    EDITS.append((name, old, new))

# --- ШАПКА -----------------------------------------------------------

E("шапка: абзац v3.9.8-clear -> ред.2",
"""// v3.9.8-clear (2026-11-07): КОД БИТ-В-БИТ top_suart_por6_v398.v -
// отличается ТОЛЬКО шапкой. Вся история версий v1->v3.9.8 (п.1-п.25:
// даты, фиты, нестарты, переговоры, прогнозы по версиям) перенесена
// ДОСЛОВНО в beta/DEVLOG.md. Здесь - только действующие решения и
// правила приёмки фита. Нумерация п.хх СОХРАНЕНА из v3.9.8, чтобы все
// ссылки «п.XX шапки» в теле файла остались валидными; номера с
// пометкой (истор.) описывают заменённые конструкции - их полный текст
// в beta/DEVLOG.md.""",
"""// v3.9.8-clear ред.2 (2026-11-07): КОД top_suart_por6_v398.v МИНИМУС
// МЁРТВЫЙ legacy-КОД. Вычеркнуты: ветки делителя g_div2/g_div4/
// g_div_even/g_div_odd, их регистры cnt/x1_q/t0_q/x1_p/x1_n/x2_q/x2_p
// и localparam MEV/NMOD/NHALF. В нетлист v3.9.8 они НЕ попадали вовсе
// (XST триммил их - WARNING:Xst:1780), поэтому нетлист/ресурсы/
// тайминги ожидаются 1-в-1 с v3.9.8; Xst:1780 в логе синтеза БОЛЬШЕ
// НЕТ. Откат legacy-веток - исходник top_suart_por6_v398.v. Вся
// история версий v1->v3.9.8 (п.1-п.25: даты, фиты, нестарты,
// переговоры, прогнозы по версиям) перенесена ДОСЛОВНО в
// beta/DEVLOG.md. Здесь - только действующие решения и правила
// приёмки фита. Нумерация п.хх СОХРАНЕНА из v3.9.8, чтобы все ссылки
// «п.XX шапки» в теле файла остались валидными; номера с пометкой
// (истор.) описывают заменённые конструкции - их полный текст в
// beta/DEVLOG.md.""")

E("шапка: п.17 - legacy-ветки удалены",
"""//  п.17 (истор.) линия счётчика mod-7 (v3.9.2-3.9.6) заменена кольцом
//       (возврат п.22) - полный текст в DEVLOG; legacy-ветки делителя
//       оставлены в коде ДЛЯ ОТКАТА (при (2,1) элайзятся, в них clk25 =
//       прямой clk) - их предупреждения XST «не используется» штатны,
//       отсутствие в нетлисте проверяет чек-лист h).""",
"""//  п.17 (истор.) линия счётчика mod-7 (v3.9.2-3.9.6) заменена кольцом
//       (возврат п.22) - полный текст в DEVLOG. v3.9.8-clear: legacy-
//       ветки делителя и их регистры (cnt/x1_q/t0_q/x1_p/x1_n/x2_q/
//       x2_p) УДАЛЕНЫ из RTL - единственная ветка узла g_div2p5;
//       откат - исходник top_suart_por6_v398.v. Отсутствие в нетлисте
//       проверяет чек-лист h), Xst:1780 более не выдаются.""")

E("шапка: п.23 - без оговорки про декларацию x1_n",
"""//       x1_n и negedge-домен УДАЛЕНЫ - вторую кромку даёт сам clk 50
//       (декларация x1_n в RTL - ТОЛЬКО для legacy g_div_odd: XST
//       компилирует ВСЕ ветки generate; в нетлисте (2,1) её БЫТЬ НЕ
//       ДОЛЖНО). X1 = r0: фронт строго каждые 140 нс = 7,143 МГц, duty
//       1/7 (high 20 / low 120 нс); внутренний /2 ВМ85А тактируется""",
"""//       x1_n и negedge-домен УДАЛЕНЫ - вторую кромку даёт сам clk 50
//       (v3.9.8-clear: x1_n вычеркнут и из RTL). X1 = r0: фронт строго
//       каждые 140 нс = 7,143 МГц, duty 1/7 (high 20 / low 120 нс);
//       внутренний /2 ВМ85А тактируется""")

E("шапка: TODO 3 - x1_n в RTL нет",
"""//     такт ЛОГИКИ 25 МГц; x1_n В НЕТЛИСТЕ НЕТ; X1 = r0 (1 ПТ; регистр""",
"""//     такт ЛОГИКИ 25 МГц; x1_n в RTL НЕТ (v3.9.8-clear); X1 = r0 (1 ПТ; регистр""")

E("шапка: TODO 3 - список удалённых сигналов",
"""//     исходник v3.9.2-3.9.6!); cnt/x1_p/x2_p/t0_q/x1_q/x2_q/x1_n/
//     wb_ram_q в нетлисте ОТСУТСТВУЮТ (legacy-ветки элайзятся, защёлка
//     удалена п.16); por_sh - РОВНО 8 триггеров (FTCPE, clk 50 МГц,""",
"""//     исходник v3.9.2-3.9.6!); wb_ram_q в нетлисте ОТСУТСТВУЕТ (защёлка
//     удалена п.16); cnt/x1_p/x2_p/t0_q/x1_q/x2_q/x1_n в v3.9.8-clear
//     ВЫЧЕРКНУТЫ ИЗ RTL - WARNING:Xst:1780 в логе синтеза БЫТЬ НЕ
//     ДОЛЖНО; por_sh - РОВНО 8 триггеров (FTCPE, clk 50 МГц,""")

E("шапка: чек-лист g - ожидание ресурсов после рефита",
"""//  g) MC < 108; v3.9.8: прогноз ~92-94/108, факт 94; Maximum Frequency:""",
"""//  g) MC < 108; v3.9.8: прогноз ~92-94/108, факт 94; v3.9.8-clear:
//     ресурсы ОЖИДАЮТСЯ 1-в-1 с v3.9.8 (вычеркнут только мёртвый код,
//     который XST и так триммил) - после рефита сверить .rpt с
//     эталоном v3.9.8; Maximum Frequency:""")

E("шапка: чек-лист h - список удалённых сигналов",
"""//       cnt/x1_p/x2_p/t0_q/x1_q/x2_q/x1_n/wb_ram_q В НЕТЛИСТЕ БЫТЬ НЕ
//              ДОЛЖНО (legacy-ветки элайзятся, защёлка - п.16);""",
"""//       wb_ram_q В НЕТЛИСТЕ БЫТЬ НЕ ДОЛЖНО (защёлка удалена п.16);
//       cnt/x1_p/x2_p/t0_q/x1_q/x2_q/x1_n в v3.9.8-clear ВЫЧЕРКНУТЫ
//              ИЗ RTL - в Equations их быть не может вовсе;""")

# --- ТЕЛО ------------------------------------------------------------

E("тело: параметр CLK_DIV",
"""                        parameter CLK_DIV = 2,  // v3.9.2: (2,1) = двоичный счётчик mod-7 -> X1 7,143 МГц (CPU 3,571, в ТУ, п.17); 4 -> 6,25 (v3.4); 2+HALF=0 -> 12,5 ВНЕ ТУ; 5 = XOR-пара legacy (п.9)""",
"""                        parameter CLK_DIV = 2,  // v3.9.8-clear: ОБЯЗАН быть 2 - единственная ветка узла g_div2p5 (кольцо r0..r6, п.22/23); legacy-ветки делителя УДАЛЕНЫ (откат - top_suart_por6_v398.v)""")

E("тело: параметр CLK_HALF",
"""                        parameter CLK_HALF = 1) ( // v3.6: 1 = ветка g_div2p5 (учитывается ТОЛЬКО при CLK_DIV=2; v3.9.2: счётчик mod-7, п.17); 0 = старые целочисленные ветки; v3.7: параметр TXM_W УДАЛЕН вместе с TX-маской (п.13)""",
"""                        parameter CLK_HALF = 1) ( // v3.9.8-clear: ОБЯЗАН быть 1 (условие ветки g_div2p5); v3.7: параметр TXM_W УДАЛЕН вместе с TX-маской (п.13)""")

E("тело: комментарий секции узла",
"""  // фазовая лотерея). Legacy-ветки (div2/div4/чёт/нечёт) сохранены
  // для отката - при (2,1) элайзятся, в них clk25 = прямой clk.
  // ВНИМАНИЕ: старый HDLCompiler (ISE) НЕ принимает localparam и
  // reg-инициализаторы ВНУТРИ generate-блока -> выносим на scope модуля.""",
"""  // фазовая лотерея).
  // v3.9.8-clear: legacy-ветки делителя (div2/div4/чёт/нечёт) и их
  // регистры cnt/x1_q/t0_q/x1_p/x1_n/x2_q/x2_p УДАЛЕНЫ - единственная
  // ветка узла g_div2p5 (параметры ОБЯЗАНЫ быть (2,1)); откат -
  // исходник top_suart_por6_v398.v.
  // ВНИМАНИЕ: старый HDLCompiler (ISE) НЕ принимает reg-инициализаторы
  // ВНУТРИ generate-блока -> reg объявляем на scope модуля.""")

E("тело: удаление cnt + комментария",
"""  reg [2:0] cnt = 3'd0;   // ТОЛЬКО legacy-ветки (N>=6, нечётные - элайзятся;
                          // целевая g_div2p5 с v3.9.7 - КОЛЬЦО r0..r6, п.22).
                          // Сужение [3:0]->[2:0] по рецепту v3.10: старшие
                          // биты - балласт МЦ; 3 бит хватает всем legacy
                          // N<=14 (MEV<=7)
  wire por_ce;""",
"""  wire por_ce;""")

E("тело: удаление localparam + x1_q/t0_q/x1_p",
"""  // Константы делителя (на уровне модуля, не в generate!) - нужны
  // только fallback-ветке (чётные N>=6) и нечётной ветке
  localparam [3:0] MEV   = CLK_DIV / 2 - 1;   // для чётного N
  localparam [3:0] NMOD  = CLK_DIV - 1;       // для нечётного N
  localparam [3:0] NHALF = (CLK_DIV + 1) / 2; // =3 при /5 (НЕ 2!)

  // Триггеры делителя (reg) тоже на уровне модуля (инициализаторы
  // в generate тоже проблемные для этого XST). Неиспользуемые ветки XST вырезает.
  reg  x1_q = 1'b1;  // чётные 2/4 (откат): INIT=1, X1 стартует с '1'
  reg  t0_q = 1'b0;  // каскад полу-такта для CLK_DIV=4 (t0_q = clk/2)
  reg  x1_p = 1'b1;  // нечётная legacy-ветка (при (2,1) элайзится)
  // v3.9.8: clk25 - /2-триггер для ЛОГИКИ (rst/TX/FSM/порты): XC95108-15""",
"""  // v3.9.8: clk25 - /2-триггер для ЛОГИКИ (rst/TX/FSM/порты): XC95108-15""")

E("тело: wire clk25 без legacy-оговорки",
"""  wire clk25;           // такт логики (в legacy-ветках - прямой clk)""",
"""  wire clk25;           // такт логики""")

E("тело: удаление x1_n/x2_q/x2_p",
"""  // v3.9.8 (фикс fit-ошибки HDLCompilers:28): x1_n в ЦЕЛЕВОЙ g_div2p5
  // УДАЛЁН (п.23), НО декларация обязательна: XST компилирует ВСЕ ветки
  // generate, а legacy g_div_odd (XOR-пара v3) на неё ссылается (x1_n <=
  // ~x1_n, X1 = x1_p ^ x1_n, X2 = x2_p ^ x1_n). В нетлисте целевой
  // конфигурации (2,1) x1_n БЫТЬ НЕ ДОЛЖНО (ветка элайзится).
  reg  x1_n = 1'b0;  // ТОЛЬКО legacy g_div_odd (элайзится; в целевой ветке не используется)
  reg  x2_q = 1'b0;  // v3.5: противофаза X2, чётные ветки (INIT=0 при x1_q=1)
  reg  x2_p = 1'b0;  // v3.5: двойник x1_p с инверсным INIT (нечётная legacy-ветка)
  // v3.9.8 (ЦЕЛЕВАЯ g_div2p5, п.23 шапки; кольцо п.22 БЕЗ ИЗМЕНЕНИЙ):""",
"""  // v3.9.8 (ЦЕЛЕВАЯ g_div2p5, п.23 шапки; кольцо п.22 БЕЗ ИЗМЕНЕНИЙ):""")

E("тело: комментарий X2 без legacy-веток",
"""  // v3.5: X2 - РЕГИСТР противофазы (п.10 шапки, clk10-41): каждая ветка
  // generate даёт СВОЙ драйвер X2 (в целевой ветке v3.9.8 - комбина-
  // ционный OR колец r1..r6 = ~r0 в легальном one-hot; регистров на
  // пине НЕТ). Прецедент v3.4: комб. ~X1 фиттер поднимал в регистр
  // В ФАЗЕ - поэтому X2 построен БЕЗ одиночной инверсии регистра:
  // 6-ПТ OR нечувствителен к классу п.10. keep на порте X2 удерживает
  // сеть отдельной (страховка).""",
"""  // X2 - КОМБИНАЦИОННЫЙ 6-ПТ OR r1..r6 = ~r0 в легальном one-hot,
  // регистров на пине НЕТ (п.10 шапки): комб. ~X1 фиттер поднимал в
  // регистр В ФАЗЕ (прецедент v3.4, clk10-41) - 6-ПТ OR к этому классу
  // нечувствителен (same-D слияние невозможно по построению). keep на
  // порте X2 удерживает сеть отдельной (страховка).""")

E("тело: заголовок целевой ветки - единственная",
"""      // v3.9.8 ЦЕЛЕВАЯ ветка (п.23 шапки, схема владельца 11-6bis-2):""",
"""      // v3.9.8 ЦЕЛЕВАЯ (и после v3.9.8-clear ЕДИНСТВЕННАЯ) ветка
      // (п.23 шапки, схема владельца 11-6bis-2):""")

# --- старые формулировки, которых НЕ должно остаться (verify) --------
FORBIDDEN_HEADER = [
    "КОД БИТ-В-БИТ",
    "оставлены в коде ДЛЯ ОТКАТА",
    "декларация x1_n в RTL - ТОЛЬКО",
    "legacy-ветки элайзятся",
    "x1_n В НЕТЛИСТЕ НЕТ",
    "(в legacy-ветках - прямой clk)",
    "Триггеры делителя (reg)",
    "Константы делителя (на уровне модуля",
]
REQUIRED_HEADER = [
    "v3.9.8-clear ред.2",
    "МЁРТВЫЙ legacy-КОД",
    "ВЫЧЕРКНУТЫ ИЗ RTL",
    "Xst:1780",
    "исходник top_suart_por6_v398.v",
    "ОБЯЗАН быть 2",
    "ОБЯЗАН быть 1",
    "и после v3.9.8-clear ЕДИНСТВЕННАЯ",
    "ресурсы ОЖИДАЮТСЯ 1-в-1 с v3.9.8",
]

# ---------------------------------------------------------------- функции
def load(path):
    with open(path, "rb") as f:
        return f.read().decode("cp1251")

def apply_edits(text, tag, edits=None):
    for name, old, new in (edits if edits is not None else EDITS):
        n = text.count(old)
        if n != 1:
            sys.exit(f"[{tag}] правка «{name}»: ожидалось 1 вхождение, найдено {n}")
        text = text.replace(old, new)
    return text

def body_edits():
    """Правки, относящиеся к телу (их old-блоки лежат в теле базы)."""
    base_body_text = "\n".join(body_of(load(SRC_BASE))[0])
    return [(n, o, w) for (n, o, w) in EDITS if o in base_body_text]

def cut_legacy_branches(text, tag):
    """Вычеркивает ветки g_div2/g_div4/g_div_even/g_div_odd: от строки
    'end else if (CLK_DIV == 2) begin : g_div2' до 'endgenerate' (не включая)."""
    lines = text.split("\n")
    starts = [i for i, l in enumerate(lines)
              if l == "    end else if (CLK_DIV == 2) begin : g_div2"]
    genend = [i for i, l in enumerate(lines) if l == "  endgenerate"]
    if len(starts) != 1 or len(genend) != 1 or genend[0] <= starts[0]:
        sys.exit(f"[{tag}] якоря legacy-веток неуникальны/сломаны: "
                 f"starts={starts}, endgenerate={genend}")
    # строка '    end else if (CLK_DIV == 2) begin : g_div2' содержит
    # закрывающий end ЦЕЛЕВОЙ ветки g_div2p5 - заменяем её на '    end',
    # остальное (до endgenerate) вычеркиваем
    lines[starts[0]:genend[0]] = ["    end"]
    return "\n".join(lines)

def body_of(text):
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l.startswith("module retro_pcld_top"):
            return lines[i:], i
    sys.exit("module не найден")

def strip_comment(l):
    p = l.find("//")
    return l if p < 0 else l[:p]

def verify():
    print("=== ВЕРИФИКАЦИЯ v3.9.8-clear ред.2 ===")
    ok = True

    # 1) CP1251 round-trip + _utf8-двойник + хвост
    clear = load(SRC_CLEAR)
    if clear.encode("cp1251").decode("cp1251") != clear:
        print("ПРОВАЛ: CP1251 round-trip"); ok = False
    else:
        print("OK: CP1251 round-trip")
    with open(SRC_CLEAR, "rb") as f:
        raw = f.read()
    if not raw.endswith(b"endmodule") or raw.endswith(b"endmodule\n"):
        print("ПРОВАЛ: хвост не как у базы v398 (endmodule без завершающего \\n)"); ok = False
    else:
        print("OK: хвост - как у базы v398: endmodule без завершающего \\n")
    with open(SRC_CLEAR_UTF8, "rb") as f:
        utf8 = f.read().decode("utf-8") if os.path.exists(SRC_CLEAR_UTF8) else None
    if utf8 == clear:
        print("OK: _utf8-двойник байт-в-байт (по тексту)")
    else:
        print("ПРОВАЛ: _utf8-двойник расходится"); ok = False

    # 2) тело == тело базы минус манифест (все правки тела - документированы)
    base = load(SRC_BASE)
    base_body, _ = body_of(base)
    exp_edits = body_edits()
    expected_body = cut_legacy_branches(
        apply_edits("\n".join(base_body), "base->expected", exp_edits),
        "base->expected").split("\n")
    clear_body, _ = body_of(clear)
    if clear_body == expected_body:
        print("OK: тело clear == тело v398 + ТОЛЬКО документированные правки "
              f"({len(exp_edits)} блоков)")
    else:
        import difflib
        print("ПРОВАЛ: тело расходится с ожидаемым:")
        for d in list(difflib.unified_diff(expected_body, clear_body,
                                           "expected", "clear", lineterm="", n=1))[:40]:
            print("   " + d)
        ok = False

    # 3) удалённые идентификаторы отсутствуют в коде без комментариев
    hits = []
    pat = re.compile(r"\b(" + "|".join(REMOVED_IDS) + r")\b")
    for i, l in enumerate(clear.split("\n")):
        for m in pat.finditer(strip_comment(l)):
            hits.append((i + 1, m.group(0)))
    if hits:
        print("ПРОВАЛ: удалённые идентификаторы в КОДЕ (не в комментариях):")
        for ln, s in hits[:20]:
            print(f"   строка {ln}: {s}")
        ok = False
    else:
        print("OK: в коде без комментариев нет cnt/x1_q/x1_p/x1_n/x2_q/x2_p/"
              "t0_q/MEV/NMOD/NHALF")

    # 4) ровно одна ветка generate - g_div2p5, и она ЗАКРЫТА end'ом
    branches = re.findall(r"begin\s*:\s*(\w+)", clear)
    if branches == ["g_div2p5"] and "    end\n  endgenerate" in clear:
        print("OK: единственная ветка generate - g_div2p5, закрыта end")
    elif branches != ["g_div2p5"]:
        print(f"ПРОВАЛ: ветки generate: {branches}"); ok = False
    else:
        print("ПРОВАЛ: перед endgenerate нет закрывающего end"); ok = False

    # 5) старые формулировки удалены, новые присутствуют (весь файл)
    bad = [s for s in FORBIDDEN_HEADER if s in clear]
    miss = [s for s in REQUIRED_HEADER if s not in clear]
    if bad:
        print(f"ПРОВАЛ: остались старые формулировки: {bad}"); ok = False
    if miss:
        print(f"ПРОВАЛ: нет новых формулировок: {miss}"); ok = False
    if not bad and not miss:
        print("OK: legacy-формулировки вычищены, ред.2 на месте")
        print(f"OK: упоминаний Xst:1780: {clear.count('Xst:1780')}")

    # 6) число строк
    n = clear.count("\n")
    print(f"OK: итоговый размер: {n} строк (ред.1: 870, ред.2 без мёртвого кода)")
    print("ИТОГ:", "PASS" if ok else "FAIL")
    return ok

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        clear = load(SRC_CLEAR)
        clear = apply_edits(clear, "clear")
        clear = cut_legacy_branches(clear, "clear")
        # нормализация хвоста: как у базы v398 - endmodule без завершающего \n
        clear = clear.rstrip("\n")
        with open(SRC_CLEAR, "wb") as f:
            f.write(clear.encode("cp1251"))
        with open(SRC_CLEAR_UTF8, "wb") as f:
            f.write(clear.encode("utf-8"))
        print("apply: файлы записаны (CP1251 + _utf8)\n")
    sys.exit(0 if verify() else 1)

if __name__ == "__main__":
    main()
