#!/usr/bin/env python3
# fit_diff_v399.py - sravnenie fitter-otchetov XC95108: v3.9.8-clear
# (POR = por_sh 8 bit so strobom r0) vs v3.9.9-clear (VARIANT A: schet
# frontov CLKOUT). Parset Mapped Resource Summary, razbivku po FB,
# prisutstvie por_*/clkout_*/rst_cnt v netliste; delty schitaet kodom.
# Istochniki: upload/retro_pcld_top (398_clear).rpt, (399_clear).rpt
import re, sys

R398 = "/home/z/my-project/upload/retro_pcld_top (398_clear).rpt"
R399 = "/home/z/my-project/upload/retro_pcld_top (399_clear).rpt"

def parse(path):
    t = open(path, encoding="cp1251", errors="replace").read()
    d = {"name": path}
    # Mapped Resource Summary: 5 chisel Used/Tot (MC, PT, FB-inps, Reg, Pins)
    m = re.search(r"Macrocells.*?\n.*?\n\s*([\d]+)\s*/\s*([\d]+).*?\( ?(\d+)%\)\s+([\d]+)\s*/\s*([\d]+).*?\( ?(\d+)%\)\s+([\d]+)\s*/\s*([\d]+).*?\( ?(\d+)%\)\s+([\d]+)\s*/\s*([\d]+).*?\( ?(\d+)%\)\s+([\d]+)\s*/\s*([\d]+).*?\( ?(\d+)%\)", t, re.S)
    (d["mc"], d["mc_tot"], _, d["pt"], d["pt_tot"], _, d["inp"], d["inp_tot"],
     _, d["reg"], d["reg_tot"], _, d["pin"], d["pin_tot"], _) = m.groups()
    for k in ("mc", "pt", "inp", "reg", "pin"):
        d[k] = int(d[k]); d[k + "_tot"] = int(d[k + "_tot"])
    # razbivka po FB
    d["fb"] = {}
    for fb, mc, mct, inp, inpt, sig, pt, ptt in re.findall(r"(FB\d)\s+(\d+)/(\d+)\*?\s+(\d+)/(\d+)\*?\s+(\d+)\s+(\d+)/(\d+)", t):
        d["fb"][fb] = dict(mc=int(mc), mc_tot=int(mct), inp=int(inp), inp_tot=int(inpt),
                           sig=int(sig), pt=int(pt), pt_tot=int(ptt), exhausted=("*" in t))
    # ischerpannye FB: po MC (18/18*) i po vkhodam (36/36*)
    d["fb_exh"] = re.findall(r"(FB\d)\s+\d+/\d+\*\s+\d+/\d+\s", t)
    d["fb_inp_exh"] = re.findall(r"(FB\d)\s+\d+/\d+\s+\d+/\d+\*", t)
    # globalnye resursy
    d["gck"] = re.findall(r"Signal '(\w+)' mapped onto global clock net (\w+)", t)
    d["gsr_used"] = "Global set/reset net(s) unused" not in t
    d["mchp"] = int(re.search(r"There are (\d+) macrocells in high performance", t).group(1))
    # netlist sbrosa
    for pat, key in (("por_sh", "por_sh"), ("por_run", "por_run"), ("por_ce", "por_ce"),
                     ("clkout_meta", "clkout_meta"), ("clkout_sync", "clkout_sync"),
                     ("clkout_d", "clkout_d"), ("rst_cnt<", "rst_cnt")):
        d[key] = len(re.findall(pat, t))
    # PT sbrosovogo ostrova (iz FB-tablic: signal -> Total Pt)
    d["island_pt"] = {}
    for sig, pt, loc in re.findall(r"^(por_\S+|clkout_\w+|rst_cnt<\d>|RESET_IN)\s+(\d+)\s+\d+\s+\d+\s+\d+\s+(FB\d_\d+)", t, re.M):
        d["island_pt"][sig] = (int(pt), loc)
    return d

a, b = parse(R398), parse(R399)

def row(fmt, *args): print(fmt.format(*args))

print("=" * 74)
print("SRVNENIE FITTER-OTCHETOV: 398_clear (POR por_sh) vs 399_clear (VARIANT A)")
print("=" * 74)
print(f"{'Metrika':24s}{'398_clear':>14s}{'399_clear':>14s}{'delta':>10s}")
print("-" * 74)
for key, title in (("mc", "Macrocells"), ("pt", "Product Terms"), ("inp", "FB Inputs"),
                   ("reg", "Registers"), ("pin", "Pins (IO)")):
    row("{:24s}{:>7s}/{:<6s}{:>7s}/{:<6s}{:>+10d}", title,
        f"{a[key]}", f"{a[key+'_tot']}", f"{b[key]}", f"{b[key+'_tot']}", b[key] - a[key])
row("{:24s}{:>14d}{:>14d}{:>+10d}", "MC high-perf (MCHP)", a["mchp"], b["mchp"], b["mchp"] - a["mchp"])
row("{:24s}{:>14s}{:>14s}{:>10s}", "GCK (takt)", "; ".join(f"{s}->{n}" for s, n in a["gck"]), "; ".join(f"{s}->{n}" for s, n in b["gck"]), "-")
row("{:24s}{:>14s}{:>14s}{:>10s}", "Set/reset net (GSR)", "unused" if not a["gsr_used"] else "USED", "unused" if not b["gsr_used"] else "USED", "-")
row("{:24s}{:>14s}{:>14s}{:>10s}", "Ischerpano FB", ",".join(a["fb_exh"]) or "-", ",".join(b["fb_exh"]) or "-", f"{len(b['fb_exh'])-len(a['fb_exh']):+d}")
row("{:24s}{:>14s}{:>14s}{:>10s}", "Ischerpano FB po Vh", ",".join(a["fb_inp_exh"]) or "-", ",".join(b["fb_inp_exh"]) or "-", f"{len(b['fb_inp_exh'])-len(a['fb_inp_exh']):+d}")
row("{:24s}{:>14d}{:>14d}{:>+10d}", "Svobodnye MC", a["mc_tot"] - a["mc"], b["mc_tot"] - b["mc"], (b["mc_tot"] - b["mc"]) - (a["mc_tot"] - a["mc"]))
print()
print("Razbivka po FB (MC / PT / FB-vhody):")
print(f"{'FB':6s}{'398':>16s}{'399':>16s}{'delta':>18s}")
print("-" * 60)
for fb in sorted(set(a["fb"]) | set(b["fb"])):
    fa, fbk = a["fb"][fb], b["fb"][fb]
    star_a = "*" if fb in a["fb_exh"] else ""
    star_b = "*" if fb in b["fb_exh"] else ""
    ia = "*" if fb in a["fb_inp_exh"] else ""
    ib = "*" if fb in b["fb_inp_exh"] else ""
    row("{:6s}{:>7d}/{:<3d}{:<5s}{:>7d}/{:<3d}{:<5s}{:+3d} MC {:+3d} PT {:+3d} vh",
        fb, fa["mc"], fa["pt"], star_a + ia, fbk["mc"], fbk["pt"], star_b + ib,
        fbk["mc"] - fa["mc"], fbk["pt"] - fa["pt"], fbk["inp"] - fa["inp"])
print()
print("Sbrosostrov v netliste:")
print(f"  398: por_sh={a['por_sh']} por_run={a['por_run']} por_ce={a['por_ce']} (por_ce - alias r0, flatten)")
a_cnt = sum(pt for sig, (pt, loc) in a["island_pt"].items() if sig.startswith(("por_sh", "por_run")))
for sig, (pt, loc) in sorted(a["island_pt"].items()):
    print(f"  398: {sig:12s} {pt} PT @ {loc}")
print(f"  398: por-cep = {a_cnt} PT (9 MC: por_sh 8 + por_run 1)")
print(f"  399: por_sh={b['por_sh']} por_run={b['por_run']} por_ce={b['por_ce']} (vse 0)")
for sig, (pt, loc) in sorted(b["island_pt"].items()):
    print(f"  399: {sig:12s} {pt} PT @ {loc}")
tot_cnt = sum(pt for sig, (pt, loc) in b["island_pt"].items() if sig.startswith(("clkout", "rst_cnt")))
print(f"  399: novaya polka (clkout_* + rst_cnt) = {tot_cnt} PT; reset_q (RESET_IN) = {b['island_pt'].get('RESET_IN', ('?','?'))[0]} PT (v 398: {a['island_pt'].get('RESET_IN', ('?','?'))[0]} PT)")
print()
print("VYVOD: registr -3 (progn -3 tochno: -9 por-cep +6 clkout/rst_cnt); MC -2",
      "(-3 reg +1 komb. MC pogloshchen perekidkoy); PT +1 (schet frontov 10 PT",
      "dorozhe sdviga 2 PT/bit - kompensirovano udaleniem por-cep); FB-vhody +2",
      "(schetchik rastashchen po FB4/FB6); iz 2 ischerpannykh FB (FB4, FB6)",
      "svobodny 0 ostalos tolko FB3 (36/36* vkhody, A-transformer) - bylo i v 398.")
