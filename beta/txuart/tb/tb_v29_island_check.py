#!/usr/bin/env python3
# tb_v289_island_check.py - v2.8.9 = бесплатный блок по ревью
# v2.9 ШАГ-1+ШАГ-2 (слитый порт 06h: A[3:0]=N, A[7:4]=колонки; слитое чтение 03h: бит 7=TXRDY) + всё наследство v28.9:
# Д-5..Д-9). Шина/тактирование/пины/контракт таймера - БЕЗ ИЗМЕНЕНИЙ, поэтому
# контракты v28.8 сохраняются 1-в-1; модель таймера теперь ЦИКЛОТЧНАЯ
# (registered RST75_r, окно загрузки 16 клк = вся T2 записи), в отличие от
# tb_v288 (там rst75 считался комбинационно в том же шаге).
#
# НОВОЕ в v2.8.9:
#   О-1: seg[7] (dp) = 1'b1 = ПОГАС (было 1'b0 = ГОРЕЛ всегда - активный 0).
#   О-2/самотест «----» (правка владельца 11-16, после ответа на ревью):
#        dig_q INIT/сброс = 4'hF + seg_q INIT = 7'h40 -> при включении
#        и после RESET тире в каждом разряде до первой записи fw в порты
#        (цена О-2 - ~68 мА баз PNP - возвращена осознанно; сегменты в
#        7 раз легче «8888»; альтернатива с нулевым окном - fw).
#   О-3: гейт счёта tick_step && |tmr_cnt (было !RST75_r) - underflow 0->F
#        при OUT 06h,0 закрыт по построению; -1 вход ФБ (RST75_r ушёл из
#        входов ФБ счётчика). Регрессия: фазовый перебор СТОП на верной
#        модели + БРАК-модель (старый гейт) показывает, что тест дискриминативен.
#   О-7: (* fsm_encoding = "compact" *) на state - one-hot (109>108) закрыт.
#   Р-4: таймер в асинхронной форме ядра (posedge clk or posedge cpu_rst);
#   Шаг-7 (18-17, решение владельца): ВСЕ сбросы таймера СНЯТЫ (блоки на
#   чистом @(posedge clk), INIT-значения прежние) - ложные фронты RST7.5
#   при старте/после кнопки приняты (RESET_IN чистит защёлку 7.5 у CPU).
#   Р-6: параметры POR_W/CLK_DIV/CLK_HALF и generate-обёртка удалены.
#   Н-3: каденция честная (период = N*4 + ISR; ~24 FPS @3,125, не 41.9).
# База:
# (П-5: tmr_cnt 4 бита, N <= 15; v2.8.8: RST75_r = УРОВЕНЬ до загрузки).
# 1 clk = 40 нс (clk 25 МГц); tick_step = 1 клк каждые 100 клк (4 мкс).

import re, sys

BASE = "/home/z/my-project/CPLD-plus-8085/beta/txuart/"
RTL9 = BASE + "top_txuart_por6_v29_utf8.v"
RTL8 = BASE + "top_txuart_por6_v28_8_utf8.v"
UCF9 = BASE + "top_txuart_v29.ucf"
UCF8 = BASE + "top_txuart_v28_8.ucf"

TICK = 100          # клк между tick_step
MASK = 0x0F         # П-5: 4 бита
WR = 16             # окно tmr_wr06 (вся T2 записи IO, ~640 нс)

ok = []
def chk(name, cond, detail=""):
    ok.append((name, cond)); print(("  PASS " if cond else "  FAIL ") + name + (" " + detail if detail else ""))

# =====================================================================
# A. RTL-сверка фикс-паттернов (по САМОМУ ФАЙЛУ, не по модели)
# =====================================================================
print("== A. RTL v2.8.9: паттерны фиксов в исходнике ==")
src9 = open(RTL9, encoding="utf-8").read()
src8 = open(RTL8, encoding="utf-8").read()
# код без комментариев (строчные // и блочные /* */):
def code_of(s):
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    s = re.sub(r"//[^\n]*", " ", s)
    return s
code9 = code_of(src9)

chk("О-1: assign seg = {1'b1, ~seg_q} (dp ПОГАС)",
    "assign seg = {1'b1, ~seg_q};" in code9)
chk("О-1: старой формы {1'b0, ~seg_q} в коде НЕТ",
    "assign seg = {1'b0, ~seg_q};" not in code9)
chk("самотест «----» (правка владельца 11-16): dig_q INIT/сброс = 4'hF",
    bool(re.search(r"reg\s*\[3:0\]\s*dig_q\s*=\s*4'hF;", code9)) and
    bool(re.search(r"dig_q\s*<=\s*4'hF;", code9)) and
    not re.search(r"dig_q\s*<=\s*4'h0;", code9))
chk("самотест: seg_q INIT/сброс = 7'h40 (только сегмент g)",
    bool(re.search(r"reg\s*\[6:0\]\s*seg_q\s*=\s*7'h40;", code9)) and
    bool(re.search(r"seg_q\s*<=\s*7'h40;", code9)))
seg_out = (1 << 7) | (~0x40 & 0x7F)   # пины seg = {dp(О-1), ~seg_q}: активный 0
dig_out = ~0xF & 0xF                  # пины dig = ~dig_q: активный 0
chk("самотест «----» на пинах: горит ТОЛЬКО g (seg=BFh), все 4 разряда выбраны (dig=00h)",
    seg_out == 0xBF and dig_out == 0x00,
    f"seg=0x{seg_out:02X} (0=горит: g), dig=0x{dig_out:02X} (0=выбран: все)")
chk("Шаг-1 (v2.9): kbcol_q <= A[7:4] в блоке загрузки tmr_wr06 (слитый порт 06h; Шаг-7: первый if блока)",
    bool(re.search(r"if \(tmr_wr06\) begin\s*tmr_cnt\s*<=\s*A\[3:0\];\s*kbcol_q\s*<=\s*A\[7:4\];", code9)))
chk("Шаг-1: декод 3'b010: kbcol_q ИЗ case записи УДАЛЁН (порт 02h немаплен)",
    not re.search(r"3'b010:\s*kbcol_q", code9))
chk("Шаг-1: КОНТРАКТ ПОРТОВ помечает 02h немапленным",
    "02h в v2.9" in src9 and "Шаг-1: колонки переехали" in src9)
chk("Шаг-1: fw v1.2 обязателен (пара RTL v2.9 <-> fw v1.2 зафиксирована в шапке)",
    "Обязателен fw v1.2" in src9)
chk("Шаг-1: N заперт на 4 бита - Р-2 с этим портом невозможна (шапка)",
    "Р-2 (tmr_cnt 7 бит)" in src9 and "НЕВОЗМОЖНА навсегда" in src9)
chk("Шаг-2 (v2.9): мукс 03h = {tx_idle, 2'b00, row4..row0} - TXRDY в бит 7",
    "io_rd_kb ? {tx_idle, 2'b00, row4, row3, row2, row1, row0}" in code9)
chk("Шаг-2: io_rd_st в КОДЕ НЕТ (декод 05h удалён, чтений 2 -> 1)",
    "io_rd_st" not in code9)
chk("Шаг-2: старый мукс-вид {6'b000000, tx_idle, 1'b0} отсутствует",
    "{6'b000000, tx_idle, 1'b0}" not in code9)
chk("Шаг-2: 05h помечен немапленным (КОНТРАКТ ПОРТОВ: 00/01/02/04/05/06/07h)",
    "04/05/06/07h" in src9 and "05h в v2.9 НЕМАПЛЕН" in src9)
chk("Шаг-2: hwuart-совместимость бита A1 упразднена владельцем (шапка)",
    "УПРАЗДНЕНА" in src9 and "единственный потребитель статуса - fw_mon" in src9)
chk("Шаг-2: v1.1 опрашивает 05h - встанет намертво (предупреждение в шапке)",
    "встанет НАМЕРТВО" in src9)
# Шаг-1 ФИКС (16-16, синтез владельца: XST 528 x4 на col0..3) - статические сканеры;
# Шаг-7 (18-17): сбросы таймера СНЯТЫ по решению владельца - таймер вне сети сброса
frags = re.split(r"\balways\b", code9)
chk("Шаг-1 фикс (XST 528): kbcol_q - ОДИН always-водитель (Шаг-7: ветка сброса удалена)",
    sum(1 for f in frags if re.search(r"\bkbcol_q\s*<=", f)) == 1)
chk("Шаг-7: reset-ветка таймера (tmr_cnt <= 4'hF) в коде отсутствует",
    re.search(r"if \(cpu_rst_r\) begin\s*tmr_cnt <= 4'hF;", code9) is None
    and "tmr_cnt <= 4'hF" not in code9)
chk("Шаг-7: reset-ветка триггера 7.5 (if cpu_rst_r -> RST75_r) в коде отсутствует",
    re.search(r"if \(cpu_rst_r\)\s+RST75_r", code9) is None)
chk("Шаг-7: оба таймерных блока на чистом @(posedge clk) (2 пометки Шаг-7)",
    len(re.findall(r"always\s*@\(posedge clk\)\s*(?:begin\s*)?//\s*ШАГ-7", src9)) == 2)
chk("Шаг-7: INIT-значения сохранены (старт бит-в-бит прежний)",
    bool(re.search(r"reg\s+\[3:0\]\s+tmr_cnt\s*=\s*4'hF;", code9))
    and bool(re.search(r"reg\s+RST75_r\s*=\s*1'b0;", code9))
    and bool(re.search(r"reg\s+\[3:0\]\s+kbcol_q\s*=\s*4'h0;", code9)))
chk("Шаг-7: загрузка/стоп OUT 06h не задеты (RST75_r <= 1'b0 при tmr_wr06 жив)",
    re.search(r"if \(tmr_wr06\)\s+RST75_r <= 1'b0;", code9) is not None)
_bad = []
for _n in set(re.findall(r"\breg\s+(?:signed\s+)?(?:\[[^\]]+\]\s*)?(\w+)", code9)):
    if sum(1 for f in frags if re.search(r"\b%s\s*<=" % re.escape(_n), f)) > 1:
        _bad.append(_n)
chk("Шаг-1 фикс (XST 528): ни один reg не назначается в >1 always-блоке"
    + ("" if not _bad else " - НАРУШИТЕЛИ: " + ",".join(_bad)),
    not _bad)
_bad = []
for _line in code9.split("\n"):
    for _m in re.finditer(r"(\d+)'([hb])([0-9a-fA-FxXzZ_]+)", _line):
        _w, _b, _d = int(_m.group(1)), _m.group(2).lower(), _m.group(3).replace("_", "")
        if any(c in "xXzZ" for c in _d):
            continue
        _per = 4 if _b == "h" else 1
        if len(_d) > (_w + _per - 1) // _per:          # правило ISE 301: цифр > ceil(ширина/цифру)
            _bad.append(_m.group(0))
chk("Шаг-1 фикс (XST 301): based-констант с лишними цифрами НЕТ"
    + ("" if not _bad else " - " + ",".join(_bad[:4])),
    not _bad)
# Шаг-3 (Р-5, фит Шаг-1+2 не прошёл): единый узел записи в порт
chk("Шаг-3 (Р-5): узел io_wr = (state == S_T2) && !WRn && IOM, kept",
    bool(re.search(r'keep = "true" \*\) wire io_wr = \(state == S_T2\) && !WRn && IOM', code9)))
chk("Шаг-3 (Р-5): копий декода (state/!WRn/IOM) в коде ровно 1 - сам узел",
    code9.count("(state == S_T2) && !WRn && IOM") == 1)
chk("Шаг-3 (Р-5): io_wr_tx построен ОТ узла (старый инлайн отсутствует)",
    "wire io_wr_tx = io_wr" in code9
    and "io_wr_tx = (state == S_T2) && !WRn && IOM" not in code9)
chk("Шаг-3 (Р-5): tmr_wr06 построен ОТ узла (старый инлайн отсутствует)",
    "wire tmr_wr06 = io_wr &&" in code9
    and "tmr_wr06 = (state == S_T2) && !WRn && IOM" not in code9)
chk("Шаг-3 (Р-5): case портов под if (io_wr), гейт if (IOM) удалён",
    bool(re.search(r"if \(io_wr\) begin\s*case \(addr_latch\[2:0\]\)", code9))
    and "if (IOM) begin" not in code9)
chk("Шаг-3 (Р-5): bus_reg НЕ на узле (ловит и записи памяти)",
    bool(re.search(r"if \(state == S_T2 && !WRn\)\s*bus_reg <= A;", code9)))
# Шаг-4 -> Шаг-6 (GSR-идея владельца отклонена по первоисточникам для 5В
# XC95108: у сети GSR нет внутреннего драйвера - только пин I/O/GSR, а наш
# пин 1 = кнопка SW20; та же цель достигается РЕГИСТРОМ сброса, который
# фиттер не может растворить в PT - kept-проводку Шага-4 cpldfit растворил)
chk("Шаг-6: сброс - РЕГИСТР cpu_rst_r = rst_press | por_run (INIT=1)",
    bool(re.search(r"reg\s+cpu_rst_r\s*=\s*1'b1;", code9))
    and "cpu_rst_r <= rst_press | por_run;" in code9)
chk("Шаг-6: kept-проводки wire cpu_rst в коде НЕТ (растворялась фиттером)",
    "wire cpu_rst" not in code9)
chk("Шаг-4/6: сырая пара !por_run && !rst_press в коде отсутствует (де Морган)",
    code9.count("!por_run && !rst_press") == 0)
chk("Шаг-4/6: io_wr_tx гейтится регистром (!cpu_rst_r)",
    "&& tx_idle && !ld_tx_q && !cpu_rst_r" in code9)
chk("Шаг-4/6: FSM-гейт T2->WB1 от регистра (!cpu_rst_r)",
    "(!IOM && A15 && !cpu_rst_r)" in code9)
chk("Шаг-6: оба АСИНХРОННЫХ блока ядра сбрасываются cpu_rst_r (Шаг-7: таймер вышел из сети - осталось 2)",
    code9.count("posedge clk or posedge cpu_rst_r)") == 2
    and "posedge clk or posedge cpu_rst)" not in code9)
# Шаг-5 (Р-1, фит Шага-4: FB3 36/36 вх. при 15/18 МЦ, 892 D<2>_BUFR; по матрице
# FB3 por_sh<7> - единственный читатель X1/t0_q/FC_3, переезду некуда - 5 ФБ
# по 18/18 МЦ; Т1/Т2 бесполезны - константный пад держит МЦ (seg<7>), Т3/Т4
# фиттер уже поглотил): POR + квалификатор СЛИТЫ в por_sh, rst_qcnt удалён.
chk("Р-1: rst_qcnt в коде отсутствует (счёт в por_sh)",
    "rst_qcnt" not in code9)
chk("Р-1: por_sh бидир. сдвиг под por_ce (влево 1-цы / вправо 0-ы)",
    bool(re.search(r"if \(por_ce\)\s*\n\s*por_sh <= \(rst_sync != rst_press\) \? \{por_sh\[6:0\], 1'b1\}", code9))
    and "{1'b0, por_sh[7:1]}" in code9)
chk("Р-1: por_run - защёлка нуля (por_sh[0] & por_run)",
    "por_run <= por_sh[0] & por_run" in code9)
chk("Р-1: переворот rst_press по por_sh[6] на strobe + сброс счёта",
    "por_ce && por_sh[6] && (rst_sync != rst_press)" in code9
    and "por_sh    <= 8'h00;" in code9)

# --- поведенческая модель слитого блока Р-1 + регистра сброса Шага-6:
#     clk 40 нс, строб por_ce каждый 4-й такт; ВСЕ D-функции от СТАРОГО
#     состояния (nonblocking, как RTL); cpu_rst_r - +1 клк пайплайн ---
class R1:
    def __init__(s):
        s.por_sh, s.por_run = 0xFF, 1        # INIT (RTL: FF / SET)
        s.rst_meta = s.rst_sync = s.rst_press = 0
        s.ph = 0                             # фаза строба por_ce
        s.cpu_rst_r = 1                      # Шаг-6: регистр сброса (INIT=1)
    def step(s, rst_pin):
        meta_n, sync_n = rst_pin, s.rst_meta           # 2FF-синхронизатор
        diff = int(s.rst_sync != s.rst_press)
        ce = (s.ph == 0); s.ph = (s.ph + 1) % 4        # строб: 1 такт за 160 нс
        if ce:
            sh_n = (((s.por_sh << 1) & 0xFF) | 1) if diff else (s.por_sh >> 1)
        else:
            sh_n = s.por_sh
        pr_n, sh_clr = s.rst_press, False
        if ce and (s.por_sh & 0x40) and diff:          # por_sh[6] ДО сдвига
            pr_n, sh_clr = s.rst_sync, True            # переворот + счёт закрыт
        run_n = (s.por_sh & 1) & s.por_run             # защёлка нуля
        rst_n = s.rst_press | s.por_run                # Шаг-6: D регистра сброса
        s.rst_meta, s.rst_sync = meta_n, sync_n
        s.por_sh = 0x00 if sh_clr else sh_n
        s.rst_press, s.por_run = pr_n, run_n
        s.cpu_rst_r = rst_n

# 1) POR: защёлка por_run снимается ровно через 8 стробов + 1 такт и держится;
#    регистр сброса cpu_rst_r отстаёт от por_run ровно на 1 клк (Шаг-6)
r1 = R1()
released_at = -1
for k in range(40):
    r1.step(0)
    if r1.por_run == 0 and released_at < 0:
        released_at = k
chk("Р-1 модель: POR - por_run снят на такт %d (8-й строб=28, снятие=29), пор_sh=00" % released_at,
    released_at == 29 and r1.por_sh == 0x00 and r1.cpu_rst_r == 0)
r1b = R1()
rel_run = rel_rst = -1
for k in range(40):
    r1b.step(0)
    if r1b.por_run == 0 and rel_run < 0:
        rel_run = k
    if r1b.cpu_rst_r == 0 and rel_rst < 0:
        rel_rst = k
chk("Шаг-6 модель: cpu_rst_r отстаёт от por_run ровно на 1 клк (%d -> %d; низ RESET_IN ~1240 нс)" % (rel_run, rel_rst),
    rel_run == 29 and rel_rst == 30)
for _ in range(120):
    r1.step(0)
chk("Р-1 модель: защёлка держит por_run=0 (300 тактов покоя)",
    r1.por_run == 0 and r1.cpu_rst_r == 0)

# 2) взвод: 2 клка лага синхронизатора -> 8 ЗАСЧИТАННЫХ стробов -> переворот
r2 = R1()
for _ in range(40): r2.step(0)                       # POR прошёл
seen = []
for _ in range(36):                                  # такты 40..75, стробы 40..72
    r2.step(1)
    seen.append(r2.rst_press)
chk("Р-1 модель: 7 засчитанных стробов не взводят rst_press",
    all(v == 0 for v in seen[:32]))
chk("Р-1 модель: на 8-м засчитанном стробе rst_press=1 (cpu_rst_r активен)",
    seen[32] == 1 and r2.cpu_rst_r == 1 and r2.rst_press == 1)

# 3) короткий импульс (24 такта = 6 засчитанных стробов) не взводит
r3 = R1()
for _ in range(40): r3.step(0)
for _ in range(24): r3.step(1)
for _ in range(60): r3.step(0)
chk("Р-1 модель: импульс 960 нс (<1280) не взводит, счёт распался",
    r3.rst_press == 0 and r3.cpu_rst_r == 0 and r3.por_sh == 0x00)

# 4) дребезг (нерегулярные выбеги 1-2 тактов, период 5 клков - НЕ кратен
#    стробу, иначе когерентный 5 МГц-квадрат алиасится со стробами) не взводит
r4 = R1()
for _ in range(40): r4.step(0)
for k2 in range(80):
    r4.step(1 if (k2 % 5) < 2 else 0)
chk("Р-1 модель: дребезг (выбеги <=2 тактов, период 5 клков) не виден вовсе",
    r4.rst_press == 0 and r4.cpu_rst_r == 0)

# 5) снятие симметрично: удержание держит, отпускание - 8 засчитанных стробов
r5 = R1()
for _ in range(40): r5.step(0)
for _ in range(60): r5.step(1)                       # взвод + удержание
chk("Р-1 модель: удержание держит rst_press=1", r5.rst_press == 1)
seen5 = []
for _ in range(36):                                  # такты 100..135
    r5.step(0)
    seen5.append(r5.rst_press)
chk("Р-1 модель: 7 засчитанных стробов отпущенного держат rst_press=1",
    all(v == 1 for v in seen5[:32]))
chk("Р-1 модель: на 8-м стробе отпущенного rst_press=0 (cpu_rst_r=0)",
    seen5[32] == 0 and r5.cpu_rst_r == 0)
chk("О-3: гейт tick_step && |tmr_cnt в коде",
    "tick_step && |tmr_cnt" in code9)
chk("О-3: старый гейт tick_step && !RST75_r в КОДЕ отсутствует",
    "tick_step && !RST75_r" not in code9)
chk("О-3: RST75_r не входит в D-путь счётчика (вход ФБ освобождён)",
    not re.search(r"tmr_cnt\s*<=\s*tmr_cnt\s*-\s*4'd1;\s*end\s*assign[^\n]*RST75_r.*tmr_cnt", code9)
    and "tick_step && !RST75_r" not in code9)
chk("О-7: (* fsm_encoding = \"compact\" *) на state",
    '(* fsm_encoding = "compact" *)' in src9 and
    bool(re.search(r'fsm_encoding = "compact" \*\)\s*reg\s*\[2:0\]\s*state', src9)))
chk("О-7: директива-комментарий v3.9-era заменена",
    '// synthesis attribute fsm_encoding of state is "compact"' not in src9)
n_async8 = len(re.findall(r"always\s*@\(posedge clk or posedge cpu_rst_r?\)", code_of(src8)))
n_async9 = len(re.findall(r"always\s*@\(posedge clk or posedge cpu_rst_r?\)", code9))
chk("Р-4/Шаг-7: асинхронных блоков осталось 2 (только ядро; таймер вне сети сброса; было %d)" % n_async8,
    n_async9 == 2, f"v28_8={n_async8}, v28_9={n_async9}")
chk("Р-6: параметров POR_W/CLK_DIV/CLK_HALF в коде НЕТ",
    all(p not in code9 for p in ("POR_W", "CLK_DIV", "CLK_HALF")))
chk("Р-6: generate/endgenerate в коде НЕТ",
    "generate" not in code9 and "endgenerate" not in code9)
chk("Р-6: module retro_pcld_top БЕЗ #(...)",
    bool(re.search(r"module\s+retro_pcld_top\s*\(", code9)) and
    not re.search(r"module\s+retro_pcld_top\s*#", code9))
chk("Шаг-7: старт таймера жив как INIT (tmr_cnt=0F в декларации, RST75_r гасится OUT 06h)",
    bool(re.search(r"reg\s+\[3:0\]\s+tmr_cnt\s*=\s*4'hF;", code9)) and
    bool(re.search(r"RST75_r\s*<=\s*1'b0;", code9)))

# CP1251-двойник и UCF
try:
    twin = open(BASE + "top_txuart_por6_v29.v", "rb").read().decode("cp1251")
    chk("CP1251-двойник декодируется и совпадает с UTF-8 (iconv-эквивалент)",
        twin == src9)
except FileNotFoundError:
    chk("CP1251-двойник существует", False, "файл не найден")

try:
    u9 = open(UCF9, "rb").read(); u9.decode("utf-8")
    u8 = open(UCF8, "rb").read().decode("cp1251", errors="replace")
    nets = lambda s: sorted(re.findall(r'NET "([^"]+)"\s+LOC = "([^"]+)"', s))
    chk("UCF v29: чистый UTF-8", b"\xef\xbf\xbd" not in u9)
    chk("UCF v29: 73 NET/LOC, 1-в-1 с v28_8 (Д-12: пины не тронуты)",
        len(nets(u9.decode("utf-8"))) == 73 and nets(u9.decode("utf-8")) == nets(u8))
    u9t = u9.decode("utf-8")
    chk("Н-6: UCF обещает 1 000 000 бод (мёртвого «OUT 04h, 1 562 500» нет)",
        "1 000 000" in u9t and "OUT 04h, 1 562 500" not in u9t)
    chk("Н-8: UCF фиксирует PGND 8 шт (P73/P75 - ВЫХОДЫ, не PGND)",
        "8 шт" in u9t and "73 назначенных + 8" in u9t and "ВЫХОДЫ" in u9t)
    chk("Д-1/Д-2: предупреждения о подтяжках RST/R21..R25 записаны",
        "Д-1" in u9t and "Д-2" in u9t)
except FileNotFoundError:
    chk("UCF v29 существует", False, "файл не найден")

# =====================================================================
# B. Остров ТАЙМЕР v2.8.9 (циклоточная модель, nonblocking, окно загрузки)
# =====================================================================
print("== B. Остров ТАЙМЕР v2.8.9: контракт v28.8 сохранён + О-3 ==")

class Tmr:
    """Циклоточная модель v2.8.9: tmr_cnt/RST75_r - регистры, все RHS от
    старого состояния; окно загрузки WR клк (tmr_wr06 держится всю T2).
    gate='new' -> |tmr_cnt (v2.8.9), gate='old' -> !RST75_r (v2.8.8, БРАК)."""
    def __init__(s, gate="new"):
        s.cnt = MASK; s.rst75 = 0; s.t = 0
        s.gate = gate
        s.wr = None          # (t0, t1, val) - окно tmr_wr06
        s.edges = []
    def out06(s, n, t0, width=WR):
        s.wr = (t0, t0 + width, n & MASK)
    def step(s):
        tick = (s.t % TICK == TICK - 1)
        wr = s.wr is not None and s.wr[0] <= s.t < s.wr[1]
        if wr:
            n_cnt = s.wr[2]
            n_rst = 0
        else:
            if s.gate == "new":
                n_cnt = (s.cnt - 1) & MASK if (tick and s.cnt > 0) else s.cnt
            else:   # БРАК-модель v2.8.8: гейт по уровню (registered, отстаёт на клк)
                n_cnt = (s.cnt - 1) & MASK if (tick and not s.rst75) else s.cnt
            n_rst = (1 if s.cnt == 0 else 0) | s.rst75
        if n_rst and not s.rst75:
            s.edges.append(s.t + 1)   # уровень виден с клка s.t+1
        s.cnt, s.rst75 = n_cnt, n_rst
        s.t += 1
    def run(s, n):
        for _ in range(n): s.step()

def zero_tick(t0, n):
    """Тик, на котором cnt обнуляется: n-й tick_step ПОСЛЕ окна загрузки."""
    ticks = [t for t in range(t0 + WR, t0 + WR + 20 * TICK) if t % TICK == TICK - 1]
    return ticks[n - 1]

# 1. RESET->0F (загрузка тем же 0F на t=5): фронт на 15-м тике, уровень держится
a = Tmr(); a.out06(MASK, 5); a.run(4000)
e = a.edges[0] if a.edges else -1
nticks = (e - 1) // TICK - 5 // TICK
chk("RESET->0F: 1-й фронт на 15-м тике (~60 мкс)", nticks == 15,
    f"клк={e}, тиков после загрузки={nticks}")
chk("уровень держится после стопа (не пере-фронтирует)", len(a.edges) == 1, f"фронтов={len(a.edges)}")

# 2. N=3 -> фронт через 3 тика
b = Tmr(); b.out06(3, 10); b.run(2000)
e = b.edges[0] if b.edges else -1
chk("N=3: фронт через 3 tick_step'а (ожидался клк %d)" % (zero_tick(10, 3) + 2),
    e == zero_tick(10, 3) + 2, f"клк={e}")

# 3. N=0 СТОП: один защитный фронт, счётчик стоит в 0, уровень держится
c = Tmr(); c.out06(0, 10); c.run(5000)
chk("N=0: один защитный фронт, затем тишина",
    len(c.edges) == 1 and c.cnt == 0 and c.rst75 == 1,
    f"фронтов={len(c.edges)}, cnt={c.cnt}")

# 4. О-3 РЕГРЕССИЯ: фазовый перебор OUT 06h,0 - underflow невозможен
under_new, under_old = [], []
for ph in range(TICK):
    m = Tmr("new"); m.out06(0, ph); m.run(4000)
    if m.cnt == MASK: under_new.append(ph)          # 0->F без загрузки 15
    b_ = Tmr("old"); b_.out06(0, ph); b_.run(4000)
    if b_.cnt == MASK: under_old.append(ph)
chk("О-3 (v2.8.9): перебор 100 фаз СТОП - 0 underflow (cnt=0F без загрузки)",
    len(under_new) == 0, f"подтекает фаз: {len(under_new)}")
chk("О-3 (дискриминативность): БРАК-модель v2.8.8 ловит ровно 1 фазу из 100",
    len(under_old) == 1, f"фаза {under_old} (клк после снятия tmr_wr06 = tick_step); "
    "v28.8 маскировала защёлкой уровня, счётчик молча портился")
chk("О-3: защитный фронт СТОП присутствует во ВСЕХ фазах (контракт цел)",
    all((lambda m: (m.out06(0, ph), m.run(4000), len(m.edges) == 1 and m.rst75 == 1)[-1])
        (Tmr()) for ph in (0, 1, 42, 83, 99)))

# 5. ре-арм после СТОПа: N=5 -> второй фронт через 5 тиков
d = Tmr(); d.out06(2, 10); d.run(1500)
assert len(d.edges) == 1
d.out06(5, 1500); d.run(1500)
chk("ре-арм N=5 после стопа: второй фронт через 5 тиков (ожидался клк %d)" % (zero_tick(1500, 5) + 2),
    len(d.edges) == 2 and d.edges[1] == zero_tick(1500, 5) + 2,
    f"клк={d.edges[1] if len(d.edges) > 1 else -1}")

# 6. максимум диапазона: N=15 -> 15 тиков
f_ = Tmr(); f_.out06(15, 10); f_.run(4000)
chk("N=15 (макс): фронт через 15 тиков (ожидался клк %d)" % (zero_tick(10, 15) + 2),
    f_.edges and f_.edges[0] == zero_tick(10, 15) + 2, f"клк={f_.edges[0] if f_.edges else -1}")

# 7. A[7:4] игнорируются: OUT 06h,0xFF эквивалентен N=15
g = Tmr(); g.out06(0xFF, 10); g.run(4000)
chk("OUT 06h,0xFF -> N=15 (A[7:4] отброшены)",
    g.edges and (g.edges[0] - 1) // TICK - 10 // TICK == 15, f"клк={g.edges[0]}")

# 8. ширина уровня фронта >= 8 клк (такт CPU 320 нс)
m = Tmr(); m.out06(14, 5); m.run(3000)
e = m.edges[0] if m.edges else -1
hi = 3000 - e
chk("фронт OUT 06h,14 на 14-м тике после окна загрузки (56 мкс + фаза)",
    e == zero_tick(5, 14) + 2, f"клк={e}, ожидалось {zero_tick(5, 14) + 2}")
chk("ширина уровня >= 8 клк (>= 320 нс, такт CPU)", hi >= 8,
    f"уровень {hi} клк = {hi * 40} нс >> 320 нс")

# 9. О-3 для ре-арма: перебор фаз OUT 06h,14 - underflow невозможен
under14 = 0
for ph in range(TICK):
    m = Tmr(); m.out06(14, ph); m.run(4000)
    if m.cnt == MASK: under14 += 1
chk("О-3: перебор 100 фаз N=14 (ре-арм ISR) - 0 underflow", under14 == 0)

# 10. каденция ISR-ре-армов (тело tiny ~536 клк @3,125): фронт на
#     14-м тике после каждой загрузки
sched = [5 + k * 1925 for k in range(5)]
m = Tmr()
exp = [zero_tick(t, 14) + 2 for t in sched]
for t in range(sched[-1] + 15 * TICK + 10):
    if t in sched:
        m.out06(14, t)
    m.step()
got = m.edges[:5]
chk("ре-арм каждые 77 мкс: фронт на 14-м тике после каждой загрузки",
    got == exp, f"получено {got}, ожидалось {exp}")

# 11. уровень фронта держится ДО СЛЕДУЮЩЕЙ загрузки (v28.8 контракт):
#     загрузка МОЖЕТ сбросить уровень (затем новый фронт через N тиков),
#     но ВНЕ окон загрузок спадов быть не должно (уровень, не импульс)
m = Tmr()
rearms = (5, 1930, 3855)
fronts = 0; unexpected_drops = 0; prev_rst = 0
for t in range(6000):
    if t in rearms:
        m.out06(14, t)
    m.step()
    if m.rst75 and not prev_rst:
        fronts += 1
    if prev_rst and not m.rst75:
        near_load = any(r <= t <= r + WR + 1 for r in rearms)  # спад в клке загрузки включительно
        if not near_load:
            unexpected_drops += 1
    prev_rst = m.rst75
chk("уровень фронта держится до следующей загрузки (3 фронта; спады ТОЛЬКО "
    "в окнах загрузок - уровень, не импульс)", fronts == 3 and unexpected_drops == 0,
    f"фронтов={fronts}, внезапных спадов={unexpected_drops}")

# 12. джиттер базы (jam TX): фаза tick_step блуждает +-200 клк
import random
class TmrJ(Tmr):
    def __init__(s):
        Tmr.__init__(s)
        random.seed(1)
        phi = 0; s.ticks = set()
        for k in range(1, 500):
            phi = max(-200, min(200, phi + random.choice([-50, 0, 50])))
            s.ticks.add(100 * k + phi)
    def step(s):
        tick = 1 if s.t in s.ticks else 0
        wr = s.wr is not None and s.wr[0] <= s.t < s.wr[1]
        if wr:
            n_cnt, n_rst = s.wr[2], 0
        else:
            n_cnt = s.cnt - 1 if (tick and s.cnt > 0) else s.cnt
            n_rst = (1 if s.cnt == 0 else 0) | s.rst75
        if n_rst and not s.rst75: s.edges.append(s.t + 1)
        s.cnt, s.rst75 = n_cnt, n_rst
        s.t += 1
jj = TmrJ(); jj.out06(14, 10)
last = 0
while len(jj.edges) < 2 and jj.t < 40000:
    jj.step()
    if len(jj.edges) > last:
        last = len(jj.edges); jj.out06(14, jj.t + 5)
per = (jj.edges[1] - jj.edges[0]) * 0.04 if len(jj.edges) >= 2 else -1
chk("джиттер базы: период N=14 в пределах 56+-16 мкс (jam TX)", abs(per - 56) <= 16.4,
    f"{per:.1f} мкс")

# =====================================================================
# C. Каденция честная (Н-3): период = N*4 + ISR, каденция CPU-зависима
# =====================================================================
print("== C. Каденция monitor27 v1.2 (Н-3: с телами ISR, не идеализация) ==")
for cpu_mhz, T_ns, fps_lo, fps_hi in ((3.125, 320, 22.0, 26.0), (2.5, 400, 17.0, 21.0)):
    tiny_t = 67 * T_ns / 1000.0       # мкс - тело tiny ISR (fw: 67T)
    slot_t = 543 * T_ns / 1000.0      # мкс - тело slot ISR (fw: 543T)
    front = 14 * 4.0                  # таймерная часть фронта (N=14), фаза 52..56
    cycle = 5 * (front + tiny_t) + (front + slot_t)   # слот-цикл: 5 tiny + 1 slot
    frame = 71 * cycle / 1000.0       # мс, 71 слот на кадр (fw)
    fps = 1000.0 / frame
    chk(f"кадр @ {cpu_mhz} МГц = {frame:.1f} мс = {fps:.1f} FPS (fw-шапка честна)",
        fps_lo <= fps <= fps_hi, f"слот-цикл {cycle:.0f} мкс > 336 мкс -> каденция CPU-зависима (Н-3)")

# =====================================================================
# D. Узел ЧАСЫ v2.8.7 (в v2.8.9 не тронут - Р-6 снял только обёртку)
# =====================================================================
print("== D. Узел ЧАСЫ: делитель /4 (t0_q/x1_q/x2_q), противофаза X2 ==")

class Div:
    def __init__(s, x1=1, x2=0, t0=0):
        s.x1, s.x2, s.t0 = x1, x2, t0        # INIT конфигурации (SET/RESET/RESET)
    def step(s):
        if s.t0:                              # T у x1_q и x2_q - ОДИН провод
            s.x1 ^= 1; s.x2 ^= 1              # -> x2^x1 ИНВАРИАНТ
        s.t0 ^= 1
        return int(not s.t0 and not s.x1)     # por_ce (bool, не ~int!)

d = Div(); seq1, seq2, ce = [], [], []
for _ in range(4000):
    seq1.append(d.x1); seq2.append(d.x2)
    ce.append(int(not d.t0 and not d.x1))
    d.step()
anti = all(b != a for a, b in zip(seq1, seq2))
chk("инвариант X2 = ~X1 в КАЖДЫЙ такт (4000 клк)", anti)
per = sum(1 for i in range(1, 4000) if seq1[i] != seq1[i - 1])
chk("период X1 = 4 клк = 160 нс (6,25 МГц)", per in (1999, 2000), f"переключений {per}")
chk("duty X1 = 1/2 (80/80 нс)", seq1[:4].count(1) == 2, f"first4={seq1[:4]}")
chk("duty X2 = 1/2, фаза противоположна", seq2[:4].count(1) == 2, f"first4={seq2[:4]}")
chk("por_ce ровно 1 клк за период (1000 за 4000)", sum(ce) == 1000, f"={sum(ce)}")

bad = 0
for init in ((1, 1, 0), (0, 0, 1), (0, 1, 1), (1, 0, 1), (1, 1, 1), (0, 0, 0), (0, 1, 0)):
    d = Div(*init); s1, s2 = [], []
    for _ in range(16):
        s1.append(d.x1); s2.append(d.x2); d.step()
    if all(b != a for a, b in zip(s1, s2)): bad += 1
chk("самовыравнивание: инвариант из ЛЮБОГО живого INIT-кода (x1^x2=1)",
    bad == 3, f"7 кодов -> {bad} дают противофазу (фаза = БРАК INIT X2=SET)")

# =====================================================================
print("ВЕРДИКТ:", "PASS (%d проверок)" % sum(1 for _, c in ok if c)
      if all(c for _, c in ok) else "FAIL (%d из %d)" % (sum(1 for _, c in ok if not c), len(ok)))
sys.exit(0 if all(c for _, c in ok) else 1)
