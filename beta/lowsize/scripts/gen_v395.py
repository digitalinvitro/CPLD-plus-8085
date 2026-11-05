#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_v395.py (lowsize, 2026-11-05): top_suart_por6_v394.v -> top_suart_por6_v395.v.

Мера 11-5: ИСПРАВЛЕНИЕ ДЕФЕКТА СТАРТА v3.9.3/v3.9.4 (жалоба владельца:
нестабильный запуск по питанию/кнопке, v3.9.2 стабилен).
Дельта RTL - 2 слова: асинхронный сброс логики по cpu_rst = RST|por_run
вместо RST (источник GSR расширен, структура п.18 сохранена).
Экономика/верификация - п.20 шапки.

CP1251-эталон + UTF8-двойник, round-trip проверка, контроль дельты.
Запуск: python3 scripts/gen_v395.py (из beta/lowsize или откуда угодно).
"""
import difflib, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.normpath(os.path.join(HERE, ".."))
F394 = os.path.join(SRC, "top_suart_por6_v394.v")
F395 = os.path.join(SRC, "top_suart_por6_v395.v")
F395U= os.path.join(SRC, "top_suart_por6_v395_utf8.v")

def rd_cp(p):  return open(p, "rb").read().decode("cp1251")
def wr_cp(p, t):
    raw = t.encode("cp1251")
    assert raw.decode("cp1251") == t, "round-trip CP1251 FAIL"
    open(p, "wb").write(raw)

# --- якоря (UTF8 в скрипте; сравнение в CP1251-тексте) -----------------
OLD_TITLE = "// top_suart.v v3.9.4 - retro_pcld_top + SOFT-UART ТРАНЗИТЫ + CPU 3,57 МГц (X1/X2 = 7,14 МГц, счётчик mod-7, п.17; CS_n от FSM, п.16; СБРОС ЛОГИКИ -> СЕТЬ GSR, п.18; POR 8->4 со стробом x1_n - М1 txclient, п.19)"
NEW_TITLE = "// top_suart.v v3.9.5 - retro_pcld_top + SOFT-UART ТРАНЗИТЫ + CPU 3,57 МГц (X1/X2 = 7,14 МГц, счётчик mod-7, п.17; CS_n от FSM, п.16; СБРОС ЛОГИКИ -> СЕТЬ GSR, п.18, В Т.Ч. ВЕСЬ POR - источник GSR = cpu_rst = RST|por_run, п.20; POR 8->4 со стробом x1_n - М1 txclient, п.19)"

TODO_OLD = "// Что делать владельцу (TODO 78, ред. v3.9.4):"
TODO_NEW = "// Что делать владельцу (TODO 78, ред. v3.9.5):"

P20 = """//  20) v3.9.5 (линия lowsize, 2026-11-05; ИСПРАВЛЕНИЕ ДЕФЕКТА СТАРТА
//      v3.9.3/v3.9.4 - жалоба владельца 11-5: «после включения питания
//      плата запускается очень нестабильно, по кнопке сброса не
//      стартует, помогает только передёргивание питания; на плате
//      товарища не запускается вовсе; v3.9.2 запускается стабильно»):
//      GSR-ИСТОЧНИК РАСШИРЕН: RST -> cpu_rst = RST | por_run.
//      ЧТО БЫЛО (п.18, v3.9.3): асинхронный сброс логики ПО КНОПКЕ
//      ТОЛЬКО - в окне POR (~1 мкс) FSM и флаги ЖИВЫ, а шина CPU в
//      сбросе «floated» (ВМ85А 3-стирует управления/адрес/данные,
//      линейки дрейфуют вместе с растром VCC) - FSM бродит по
//      T1H/T2 под плавающими ALE/RDn/WRn/IOM/A15, пачкает
//      rd_seen/wr_seen/addr_latch/bus_reg/seg_q/dig_q/kbcol_q/snd_q
//      и встречает CPU на выходе из сброса ГРЯЗНОЙ (класс-эффекты:
//      rd_drive=1 -> контеншн CPLD против '573 на A-сетях, мусорные
//      декоды портов, глубоко испачканные шинные регистры). v3.9.2
//      был невосприимчив: cpu_rst держал ВСЮ логику в IDLE/нулях
//      КАЖДЫЙ такт POR. ДЕЛЬТА - 2 СЛОВА: always @(posedge clk or
//      posedge cpu_rst) / if (cpu_rst) - условие v3.9.2, СТРУКТУРА
//      v3.9.3 (сброс асинхронный и уходит в СЕТЬ GSR, теперь от узла
//      cpu_rst, а не от ноги RST напрямую). СВОЙСТВА: (1) в окне POR
//      логика чистится асинхронно с t=0 (GSR=1 от INIT por_run=1) -
//      чистый выход в IDLE ГАРАНТИРОВАН; (2) кнопка RESET - прежняя
//      (cpu_rst=1 при RST=1, мгновенный взвод/снятие сохранены);
//      (3) POR-цепь por_sh/por_run, делитель cnt/x1_n и sod_q - как
//      были ВНЕ GSR (por_run в GSR нельзя - сбрасывал бы сам себя);
//      (4) гейт !por_run в S_T2 (п.18) ОСТАЁТСЯ вторым рубежом
//      (бесплатно); (5) tx_pass/tx_q (async SR по cpu_rst) - без
//      правок. ВЕРИФИКАЦИЯ: (1) fuzz-тест окна POR (scripts/
//      tb_por_fuzz.v + run_tb_por_fuzz.sh, Icarus 12.0; модель
//      «плавающей» шины - случайные переключения ALE/RDn/WRn/IOM/
//      A15/A/D, 100 сидов): ГРЯЗЬ В МОМЕНТ СНЯТИЯ por_run -
//      v3.9.2 0/100 (структурная гарантия держит), v3.9.4 100/100
//      (ДЕФЕКТ ВОСПРОИЗВЕДЁН), v3.9.5 0/100 (фикс восстанавливает
//      гарантию); rd_drive-контеншн в окне POR: v3.9.4 86 тактов на
//      100 сидов, v3.9.2/v3.9.5 0; WE_n=0 в POR: 0 у всех (гейт
//      !por_run держит); «грязь на старте CPU» (+200 нс хвост):
//      v3.9.2 84/100 - хвост ОБЩИЙ для обеих линий (после POR
//      cpu_rst снят и в v3.9.2), в поле v3.9.2 стабилен - хвост
//      вымывается первым реальным циклом CPU, а вот ВХОДИТЬ в него
//      грязной и глубоко (порты/шины от всего POR) - смерть старта:
//      этим и отличается v3.9.4; (2) дифсим v3.9.4 vs v3.9.5
//      (scripts/tb_v395_diff.v + run_tb_v395.sh): 0 расхождений на
//      норм-пути (окно POR закрыто, RST-окна строго); (3) POR-цепь
//      бит-в-бит v3.9.4 (4 строба x1_n, RESET_IN ~1020-1040 нс >=
//      840 нс). ЭКОНОМИКА: источник GSR = узел cpu_rst вместо ноги
//      RST: ожидание +1 ПТ (OR) в ФБ гейта RESET_IN (RST и por_run
//      уже импортированы туда), вх.ФБ +0..2; ЕСЛИ фиттер НЕ сведёт
//      узел на GSR (fallback - PT-сбросы на каждом flopa) -
//      функционально то же, дороже по ПТ/вх (анатомия v3.9.2: ~12
//      вх.ФБ на импорты RST/por_run) - .rpt НА РАЗБОР в обоих
//      случаях, НЕ прошивать без аудита.
//
"""

CK3C = """//  3c) v3.9.5 (GSR-источник = cpu_rst, п.20): в .rpt СЕТЬ GSR
//     ИСПОЛЬЗУЕТСЯ ("Global set/reset net(s) used", "GSR : 1"); в
//     Node Listing узел cpu_rst (или $-хелпер с RST|por_run) с
//     признаком GSR; D-функции логики БЕЗ литералов сброса (NOT RST /
//     NOT por_run нет); por-цепь por_sh<3:0>/por_run ВНЕ GSR (Init=SET
//     сохранён!), cnt/x1_n/sod_q вне GSR; tx_pass/tx_q - async SR по
//     cpu_rst; RESET_IN = (por_run) OR (RST) сохранён; ЕСЛИ GSR НЕ
//     применился (PT-сбросы) - функционально корректно, но дорого:
//     rpt НА РАЗБОР, не прошивать без сверки ресурсов;
"""

RTL_A_OLD = "  always @(posedge clk or posedge RST) begin // v3.9.3: асинхронный сброс логики по RST -> СЕТЬ GSR (п.18)"
RTL_A_NEW = "  always @(posedge clk or posedge cpu_rst) begin // v3.9.5: сброс логики по cpu_rst = RST|por_run -> сеть GSR (п.20; структура п.18, расширен ИСТОЧНИК - закрывает дефект старта)"
RTL_B_OLD = "    if (RST) begin"
RTL_B_NEW = "    if (cpu_rst) begin"

def rep1(t, old, new, tag):
    n = t.count(old)
    assert n == 1, f"якорь [{tag}] найден {n} раз (ожидался 1)"
    return t.replace(old, new)

def strip_comments(t):
    out = []
    for ln in t.splitlines():
        s = re.sub(r"//.*$", "", ln).rstrip()
        if s.strip():
            out.append(s)
    return out

def main():
    t = rd_cp(F394)
    # 1) заголовок
    t = rep1(t, OLD_TITLE, NEW_TITLE, "титул")
    # 2) п.20 перед TODO
    t = rep1(t, TODO_OLD, P20 + TODO_NEW, "п.20/TODO")
    # 3) чек-лист 3c после 3b (перед "4) ПАСС")
    CK4 = "//  4) ПАСС -> .jed"
    assert t.count(CK4) == 1, "якорь 4) ПАСС"
    t = t.replace(CK4, CK3C + CK4)
    # 4) RTL-дельта
    t = rep1(t, RTL_A_OLD, RTL_A_NEW, "always-заголовок")
    t = rep1(t, RTL_B_OLD, RTL_B_NEW, "if (RST)")

    wr_cp(F395, t)
    # UTF8-двойник
    with open(F395U, "w", encoding="utf-8") as f:
        f.write(t)

    # 5) контроль дельты RTL (без комментариев): ожидаются РОВНО 2 строки
    a = strip_comments(rd_cp(F394).replace("retro_pcld_top", "M"))
    b = strip_comments(t.replace("retro_pcld_top", "M"))
    d = [l for l in difflib.unified_diff(a, b, "v394", "v395", lineterm="", n=1)
         if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    print(f"RTL-дельта v3.9.4 -> v3.9.5 (без комментариев): {len(d)} строк")
    print("\n".join(d))
    # Ожидание: ровно 2 пары строк (+/-): always-заголовок и if (RST)->if (cpu_rst)
    assert d.count("+    if (cpu_rst) begin") == 1 and d.count("-    if (RST) begin") == 1, "нет строки if (cpu_rst) в дельте"
    assert any(l.startswith("-  always @(posedge clk or posedge RST)") for l in d), "нет always-строки в дельте"
    print("OK: top_suart_por6_v395.v (CP1251) + _utf8 записаны, round-trip OK")

if __name__ == "__main__":
    main()
