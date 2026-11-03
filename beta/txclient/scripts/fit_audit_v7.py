#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fit_audit_v7.py — аудит фит-отчёта txclient v7 (первый фит v7, 11-3-2026 6:46PM,
Placement Failed). Использование:

    python3 fit_audit_v7.py [путь-к-rpt]

По умолчанию берёт архив beta/txclient/retro_pcld_top (v7-fit1-1103-646PM-FAILED).rpt.
Скрипт CWD-независим (пути от папки скрипта, os.path.join(HERE, ...)).

Что выдаёт:
  1. Сводка ресурсов (МЦ/ПТ/вх.ФБ/рег/ноги) и таблица ФБ.
  2. Анатомия триггеров по сбросу: CLR=RST (GSR-домен, сброс в 0),
     PRE=RST (GSR-домен, сброс в 1 — все 9 бит shreg!), без сброса
     (вне домена: por_sh/por_run/cnt/x1_n).
  3. Литералы RST / por_run / cpu_rst в ТЕРМАХ секции Mapped Logic
     (порт-мэпы FDCPE/FTCPE/LDCP исключаются, считаются построчно —
     методика fit_literals.py линии lowsize).
  4. Членство RST/por_run/clk в списках «Signals Used by Logic» каждого ФБ
     (GSR-подпись: RST только в ФБ гейта RESET_IN, SR-ПТ нигде не начислены).
  5. Строки глобальных сетей (в проваленных фита cpldfit печатает
     «Global ... unused» — артефакт, сравнение с успешными rpt).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "..", "retro_pcld_top (v7-fit1-1103-646PM-FAILED).rpt")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    with open(path, "rb") as f:
        txt = f.read().decode("cp1251", errors="replace")

    print("=" * 78)
    print("ОТЧЁТ:", os.path.basename(path))
    m = re.search(r"Design Name: (\S+)\s+Date: (.+)", txt)
    if m:
        print("Дизайн:", m.group(1), "| дата:", m.group(2).strip())
    m = re.search(r"Fitting Status: (.+)", txt)
    print("Статус :", m.group(1).strip() if m else "?")
    m = re.search(r"Device Used: (.+)", txt)
    print("Кристалл:", m.group(1).strip() if m else "?")

    # --- сводка ресурсов ---------------------------------------------------
    m = re.search(
        r"Macrocells\s+Product Terms\s+Function Block\s+Registers\s+Pins\s+"
        r"Used/Tot\s+Used/Tot\s+Inps Used/Tot\s+Used/Tot\s+Used/Tot\s+"
        r"(\d+)/(\d+).+?(\d+)\s*/(\d+).+?(\d+)/(\d+).+?(\d+)\s*/(\d+).+?(\d+)\s*/(\d+)",
        txt, re.S)
    if m:
        g = m.groups()
        print("\nСВОДКА: МЦ %s/%s | ПТ %s/%s | вх.ФБ %s/%s | рег %s/%s | ноги %s/%s"
              % (g[0], g[1], g[2], g[3], g[4], g[5], g[6], g[7], g[8], g[9]))

    # --- таблица ФБ ---------------------------------------------------------
    print("\nПО ФБ (МЦ | вх.ФБ | ПТ):")
    for mm in re.finditer(
            r"^(FB\d)\s+(\d+)/(\d+)\*?\s+(\d+)/(\d+)\*?\s+(\d+)\s+(\d+)/(\d+)\s+(\d+)/(\d+)",
            txt, re.M):
        fb, mc, mct, inp, inpt, sig, pt, ptt = mm.group(1, 2, 3, 4, 5, 6, 7, 8)
        print("  %s: МЦ %s/%s%s | вх.ФБ %s/%s%s | ПТ %s/%s" % (
            fb, mc, mct, "*" if "/18*" in mm.group(0).split()[1] else "",
            inp, inpt, "*" if "/36*" in mm.group(0).split()[2] else "", pt, ptt))

    # --- секция Mapped Logic (ТОЛЬКО уравнения, методика fit_literals.py) ----
    beg = txt.find("********** Mapped Logic **********")
    end = txt.find("Register Legend:", beg)
    eq = txt[beg:end] if beg != -1 and end != -1 else ""
    pm_lines = [ln for ln in eq.splitlines() if "port map" in ln]

    clr_rst, pre_rst, no_rst, other = [], [], [], []
    for ln in pm_lines:
        mm = re.match(r"\s*(\w+):\s*(FDCPE|FTCPE|LDCP)\s+port\s+map\s*\((.*)\);", ln)
        if not mm:
            other.append(ln.strip())
            continue
        inst, kind, args = mm.groups()
        # разрез по запятым верхнего уровня (внутри D(4)_BUFR есть скобки)
        parts, depth, cur = [], 0, ""
        for ch in args:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append(cur.strip())
                cur = ""
            else:
                cur += ch
        parts.append(cur.strip())
        while len(parts) < 5:
            parts.append("?")
        q, d, c, clr, pre = parts[:5]
        if clr == "RST" and pre != "RST":
            clr_rst.append(inst)
        elif pre == "RST" and clr != "RST":
            pre_rst.append(inst)
        elif clr in ("'0'", "'1'") and pre in ("'0'", "'1'"):
            no_rst.append(inst)
        else:
            other.append("%s: CLR=%s PRE=%s" % (inst, clr, pre))

    print("\nАНАТОМИЯ ТРИГГЕРОВ (порт-мэпы): всего", len(pm_lines))
    print("  CLR=RST (GSR, сброс в 0):", len(clr_rst))
    print("  PRE=RST (GSR, сброс в 1):", len(pre_rst), "->", ", ".join(pre_rst))
    print("  без сброса (вне домена) :", len(no_rst))
    if other:
        print("  ПРОЧИЕ (разобрать!):", len(other))
        for o in other:
            print("   ", o)

    # --- литералы сброса в термах (без порт-мэпов) ---------------------------
    body = "\n".join(ln for ln in eq.splitlines() if "port map" not in ln)
    for sig in ("RST", "por_run", "cpu_rst"):
        n = len(re.findall(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % sig, body))
        print("  литералов %-8s в термах: %d" % (sig, n))
    print("  (порт-мэпов с RST: %d, с por_run: %d)" % (
        sum(1 for ln in pm_lines if re.search(r",RST,", ln)),
        sum(1 for ln in pm_lines if re.search(r",por_run,", ln))))

    # --- членство RST/por_run/clk в сигнальных списках ФБ ---------------------
    print("\nСигналы RST/por_run/clk в списках 'Signals Used by Logic' ФБ:")
    for mm in re.finditer(
            r"Signals Used by Logic in Function Block(.*?)(?:Signal\s+1\s+|\Z)",
            txt, re.S):
        block = mm.group(1)
        fbm = re.finditer(r"(\d+):\s*([A-Za-z0-9_$/<>()\.]+)", block)
        names = {mm2.group(2) for mm2 in fbm}
        hits = [s for s in ("RST", "por_run", "clk") if s in names]
        if hits:
            # определить, какой ФБ: ближайший перед блоком заголовок FBnn
            head = txt[:mm.start()]
            fb = re.findall(r"\*\s+(FB\d)\s+\*", head) or re.findall(r"\bFB\d\b", head)
            print("  %s: %s" % (fb[-1] if fb else "?", ", ".join(hits)))

    # --- глобальные сети -----------------------------------------------------
    print("\nГлобальные сети (строки отчёта):")
    for ln in txt.splitlines():
        if ("mapped onto global" in ln or "Global clock net" in ln
                or "Global set/reset net" in ln or "Global output enable" in ln):
            print("  ", ln.strip())

    # --- не размещено --------------------------------------------------------
    m = re.search(r"Summary of UnMapped Logic.*?\*\* (\d+) Buried Nodes \*\*(.*?)\*\*\*\*", txt, re.S)
    if m:
        print("\nНЕ РАЗМЕЩЕНО (%s закопанных узлов):" % m.group(1))
        for ln in m.group(2).splitlines():
            mm = re.match(r"^(\S+)\s+(\d+)\s+(\d+)\s*$", ln.strip())
            if mm:
                print("   %-36s %s ПТ / %s вх." % (mm.group(1), mm.group(2), mm.group(3)))

    # --- где стоят литералы RST/por_run в термах -----------------------------
    print("\nТермы с RST/por_run (Mapped Logic, без порт-мэпов):")
    for i, ln in enumerate(eq.splitlines()):
        if "port map" in ln:
            continue
        if re.search(r"(?<![A-Za-z0-9_])(RST|por_run)(?![A-Za-z0-9_])", ln):
            print("   ", " ".join(ln.split()))


if __name__ == "__main__":
    main()
