"""Tabele za poglavlje 7, tacno po zahtevima specifikacije (7.1-7.10).

Svaka tabela odgovara jednoj stavci iz specifikacije, navedenoj u komentaru
iznad nje. Izvestaj ne generise grafike niti tabele van tog spiska; 7.11 je
diskusija i nema tabelu.

Pokretanje:  python -m analysis.report --source inprocess
Izlaz:       results/<izvor>/tables.md
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from statistics import mean, pstdev

from analysis.loader import load

OVERLAYS = ["random", "sybil_resistant", "eclipse_resistant"]
AGGS = ["mean", "median", "trimmed_mean"]
PROFILES = ["coordinated", "extreme", "random", "low_biased"]
ROUNDS = [1, 10, 11, 15, 20, 30, 40, 50]


# --- pomocne funkcije -------------------------------------------------------

def _sel(rows, **uslovi):
    return [r for r in rows if all(r.get(k) == v for k, v in uslovi.items())]


def _avg(rows, polje):
    vals = [r[polje] for r in rows if isinstance(r.get(polje), (int, float))]
    return mean(vals) if vals else None


def _f(v, dec=5):
    return "-" if v is None else f"{v:.{dec}f}"


def _e(v):
    return "-" if v is None else f"{v:.2e}"


def _conv(rows, polje="convergence_time"):
    # prosek nad pokretanjima koja su konvergirala, uz broj onih koja nisu
    t = [r[polje] for r in rows if isinstance(r.get(polje), (int, float))]
    if not t:
        return "-"
    ok = [x for x in t if x >= 0]
    if not ok:
        return "nikad"
    s = f"{mean(ok):.1f}"
    return s if len(ok) == len(t) else f"{s} ({len(t) - len(ok)}/{len(t)} nikad)"


def _vals(rows, polje):
    return sorted({r[polje] for r in rows if isinstance(r.get(polje), (int, float))})


class Out:
    def __init__(self, path):
        self.path = path
        self.lines = []

    def h(self, naslov):
        self.lines += [f"# {naslov}", ""]

    def table(self, naslov, zaglavlje, redovi, napomena=None):
        self.lines += [f"## {naslov}", "",
                       "| " + " | ".join(zaglavlje) + " |",
                       "|" + "---|" * len(zaglavlje)]
        self.lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in redovi]
        if napomena:
            self.lines += ["", napomena]
        self.lines.append("")

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines) + "\n")


def _last_round(rows):
    return max(r["round"] for r in rows)


_VICTIMS = {}


def _victims(cfg_path, n_honest, seed):
    # zrtve ciljanog Eclipse napada, istim postupkom kao u simulaciji
    key = (cfg_path, n_honest, seed)
    if key not in _VICTIMS:
        from attacks.scenario import AttackParams, Scenario
        with open(cfg_path, encoding="utf-8") as f:
            k = json.load(f).get("eclipse_targets", 0)
        if not k:
            _VICTIMS[key] = set()
        else:
            sc = Scenario(set(range(n_honest)), set(), set(),
                          AttackParams(eclipse_targets=k, experiment_seed=seed))
            _VICTIMS[key] = set(sc.targets())
    return _VICTIMS[key]


def _byz_share(r):
    # udeo Byzantine suseda: peer set umanjen za cestite i Sybil susede
    n = r["peer_count"]
    if not n:
        return 0.0
    syb = round(r["sybil_share"] * n)
    return max(0, n - r["honest_peers"] - syb) / n


def _mal_count(r):
    return int(r["peer_count"] - r["honest_peers"])


# --- 7.1 ---------------------------------------------------------------------

def t71(o, main, rounds, ablation, beta):
    o.h("7.1. Uticaj overlay strategije na agregacionu tacnost")
    betas = _vals(main, "beta")

    # razlicite vrednosti beta i agregacione funkcije; rast zlonamernog ucesca
    o.table("Tabela 7.1.1 Relativna greska po strategiji, agregaciji i beta",
            ["strategija", "agregacija"] + [f"beta={b}" for b in betas],
            [[ov, ag] + [_f(_avg(_sel(main, overlay=ov, aggregation=ag, beta=b), "final_err_rel"))
                         for b in betas]
             for ov in OVERLAYS for ag in AGGS])

    # razliciti Byzantine profili vrednosti
    if ablation:
        o.table("Tabela 7.1.2 Relativna greska po strategiji i Byzantine profilu (trimmed_mean)",
                ["strategija"] + PROFILES,
                [[ov] + [_f(_avg(_sel(ablation, overlay=ov, aggregation="trimmed_mean",
                                      byzantine_profile=p), "final_err_rel")) for p in PROFILES]
                 for ov in OVERLAYS])

    # E_rel(t) kroz vise gossip rundi
    if rounds:
        o.table(f"Tabela 7.1.3 Relativna greska kroz runde (beta={beta})",
                ["strategija", "agregacija"] + [f"r{r}" for r in ROUNDS],
                [[ov, ag] + [_f(_avg(_sel(rounds, overlay=ov, aggregation=ag, beta=beta, round=r),
                                     "err_rel")) for r in ROUNDS]
                 for ov in OVERLAYS for ag in AGGS])


# --- 7.2 ---------------------------------------------------------------------

def t72(o, main, ablation):
    o.h("7.2. Uticaj agregacione funkcije na otpornost sistema")
    if ablation:
        red = [(ov, ag) for ov in OVERLAYS for ag in AGGS]
        # otpornost na outlier-e po profilu; uticaj overlay degradacije
        o.table("Tabela 7.2.1 Relativna greska po agregaciji i Byzantine profilu",
                ["strategija", "agregacija"] + PROFILES,
                [[ov, ag] + [_f(_avg(_sel(ablation, overlay=ov, aggregation=ag, byzantine_profile=p),
                                     "final_err_rel")) for p in PROFILES] for ov, ag in red])
        # stabilnost procene
        o.table("Tabela 7.2.2 Varijansa procene po agregaciji i Byzantine profilu",
                ["strategija", "agregacija"] + PROFILES,
                [[ov, ag] + [_e(_avg(_sel(ablation, overlay=ov, aggregation=ag, byzantine_profile=p),
                                     "stability")) for p in PROFILES] for ov, ag in red])
        # brzina konvergencije
        o.table("Tabela 7.2.3 Vreme konvergencije po agregaciji i Byzantine profilu (runde)",
                ["strategija", "agregacija"] + PROFILES,
                [[ov, ag] + [_conv(_sel(ablation, overlay=ov, aggregation=ag, byzantine_profile=p))
                             for p in PROFILES] for ov, ag in red])
    # kompromis robusnost / preciznost: greska bez napada
    o.table("Tabela 7.2.4 Preciznost bez napada: relativna greska pri beta=0",
            ["strategija"] + AGGS,
            [[ov] + [_f(_avg(_sel(main, overlay=ov, aggregation=ag, beta=0.0), "final_err_rel"))
                     for ag in AGGS] for ov in OVERLAYS])


# --- 7.3 ---------------------------------------------------------------------

def t73(o, main, rounds, nodes, admission, flooding, beta):
    o.h("7.3. Analiza Sybil penetracije")
    betas = _vals(main, "beta")

    # prosecne vrednosti; razlicite beta
    o.table("Tabela 7.3.1 Sybil penetracija po strategiji i beta",
            ["strategija"] + [f"beta={b}" for b in betas],
            [[ov] + [_f(_avg(_sel(main, overlay=ov, beta=b), "final_sybil_penetration"))
                     for b in betas] for ov in OVERLAYS])

    # promene kroz vreme
    if rounds:
        o.table(f"Tabela 7.3.2 Sybil penetracija kroz runde (beta={beta})",
                ["strategija"] + [f"r{r}" for r in ROUNDS],
                [[ov] + [_f(_avg(_sel(rounds, overlay=ov, beta=beta, round=r), "sybil_penetration"))
                         for r in ROUNDS] for ov in OVERLAYS])

    # distribucija peer set kompromitovanja
    if nodes:
        last = _last_round(nodes)
        fin = _sel(nodes, beta=beta, round=last)
        red = []
        for ov in OVERLAYS:
            sel = _sel(fin, overlay=ov)
            c = Counter(round(r["sybil_share"] * r["peer_count"]) for r in sel)
            red.append([ov] + [f"{100 * c.get(k, 0) / len(sel):.1f}%" if sel else "-"
                               for k in range(8)])
        o.table(f"Tabela 7.3.3 Udeo cvorova po broju Sybil suseda (runda {last}, beta={beta})",
                ["strategija"] + [str(k) for k in range(8)], red)

    # uticaj admission politike: struktura odbijanja
    o.table(f"Tabela 7.3.4 Udeo odbijenih kandidata i struktura odbijanja (beta={beta})",
            ["strategija", "udeo odbijenih", "PoW", "starost", "skor", "bucket"],
            [[ov] + [_f(_avg(_sel(main, overlay=ov, beta=beta), k))
                     for k in ("rejected_ratio", "rej_pow", "rej_age", "rej_score", "rej_bucket")]
             for ov in OVERLAYS])

    # age-gating: pragovi starosti i ocene
    if admission:
        ages, scores = _vals(admission, "age_min"), _vals(admission, "score_threshold")
        o.table("Tabela 7.3.5 Sybil penetracija po pragu starosti i pragu ocene (sybil_resistant)",
                ["min. starost"] + [f"ocena>={s}" for s in scores],
                [[int(a)] + [_f(_avg(_sel(admission, age_min=a, score_threshold=s),
                                     "final_sybil_penetration")) for s in scores] for a in ages])

    # peer flooding; PoW
    if flooding:
        fl = _vals(flooding, "flooding")
        o.table("Tabela 7.3.6 Peer flooding: penetracija, udeo odbijenih i udeo odbijenih na PoW",
                ["strategija", "flooding", "penetracija", "udeo odbijenih", "PoW"],
                [[ov, int(v)] + [_f(_avg(_sel(flooding, overlay=ov, flooding=v), k))
                                 for k in ("final_sybil_penetration", "rejected_ratio", "rej_pow")]
                 for ov in OVERLAYS for v in fl])


# --- 7.4 ---------------------------------------------------------------------

def t74(o, ecl, ecl_rounds, ecl_nodes, ecl_cfg):
    o.h("7.4. Analiza Eclipse otpornosti")
    if not ecl:
        return
    from core.config import spec_from
    betas = _vals(ecl, "beta")
    sizes = _vals(ecl, "n_honest")

    # uslov: izolacija je moguca tek kada broj napadaca dostigne K
    red, K = [], None
    for n in sizes:
        cells = []
        for b in betas:
            sp = spec_from(n_honest=int(n), beta=float(b))
            K = sp.peer_set_size
            f, s = sp.malicious_counts()
            cells.append(f"{f + s} ({'moguca' if f + s >= K else 'nemoguca'})")
        red.append([int(n)] + cells)
    o.table("Tabela 7.4.1 Broj napadackih identiteta naspram velicine peer set-a",
            ["N"] + [f"beta={b}" for b in betas], red,
            f"K = {K}. Potpuna izolacija moguca je samo kada je broj napadaca >= K.")

    # broj eclipsed cvorova; da li bucket diverzifikacija smanjuje izolaciju
    red = []
    for ov in OVERLAYS:
        cells = []
        for b in betas:
            sel = _sel(ecl, overlay=ov, beta=b)
            izol = sum(r["final_eclipse_rate"] * r["n_honest"] for r in sel)
            uk = sum(r["n_honest"] for r in sel)
            cells.append(f"{izol:.0f}/{uk:.0f} ({_f(izol / uk if uk else None)})")
        red.append([ov] + cells)
    o.table("Tabela 7.4.2 Izolovani cvorovi na kraju (broj/ukupno i Eclipse success rate)",
            ["strategija"] + [f"beta={b}" for b in betas], red)

    if ecl_rounds:
        # koliko brzo napadac kompromituje overlay
        o.table("Tabela 7.4.3 Eclipse success rate kroz runde",
                ["strategija", "beta"] + [f"r{r}" for r in ROUNDS],
                [[ov, b] + [_f(_avg(_sel(ecl_rounds, overlay=ov, beta=b, round=r), "eclipse_rate"))
                            for r in ROUNDS] for ov in OVERLAYS for b in betas])
        # peer diversity metrike
        last = _last_round(ecl_rounds)
        o.table(f"Tabela 7.4.4 Peer diversity (entropija) na kraju (runda {last})",
                ["strategija"] + [f"beta={b}" for b in betas],
                [[ov] + [_f(_avg(_sel(ecl_rounds, overlay=ov, beta=b, round=last), "peer_diversity"))
                         for b in betas] for ov in OVERLAYS])

    if ecl_nodes:
        # peer poisoning: degradacija peer set-a zrtve
        zr = [r for r in ecl_nodes
              if r["node_id"] in _victims(ecl_cfg, int(r["n_honest"]), int(r["seed"]))]
        o.table("Tabela 7.4.5 Prosecan broj cestitih suseda zrtve kroz runde",
                ["strategija", "beta"] + [f"r{r}" for r in ROUNDS],
                [[ov, b] + [_f(_avg(_sel(zr, overlay=ov, beta=b, round=r), "honest_peers"), 2)
                            for r in ROUNDS] for ov in OVERLAYS for b in betas])
        # raspodela peer-ova po bucket-ima
        last = _last_round(ecl_nodes)
        fin = _sel(ecl_nodes, round=last)
        red = []
        for ov in OVERLAYS:
            sel = _sel(fin, overlay=ov)
            c = Counter(round(r["bucket_occupancy"] * r["peer_count"]) for r in sel)
            red.append([ov] + [f"{100 * c.get(k, 0) / len(sel):.1f}%" if sel else "-"
                               for k in range(1, 8)])
        o.table(f"Tabela 7.4.6 Udeo cvorova po najvecem broju suseda iz istog bucket-a (runda {last})",
                ["strategija"] + [str(k) for k in range(1, 8)], red)


# --- 7.5 ---------------------------------------------------------------------

def t75(o, main, delay, selective, beta):
    o.h("7.5. Analiza vremena konvergencije")
    # prosecno vreme, standardna devijacija, slucajevi bez konvergencije;
    # razlika mean / robustne funkcije; razlicite strategije
    red = []
    for ov in OVERLAYS:
        for ag in AGGS:
            t = [r["convergence_time"] for r in _sel(main, overlay=ov, aggregation=ag, beta=beta)]
            ok = [x for x in t if x >= 0]
            red.append([ov, ag, f"{mean(ok):.1f}" if ok else "-",
                        f"{pstdev(ok):.2f}" if ok else "-", f"{len(t) - len(ok)}/{len(t)}"])
    o.table(f"Tabela 7.5.1 Vreme konvergencije (beta={beta})",
            ["strategija", "agregacija", "prosek", "std", "ne konvergira"], red)

    # uticaj delay i selective forwarding napada
    for rows, kol, naslov in (
            (delay, "delay_rounds", "Tabela 7.5.2 Vreme konvergencije pod delay napadom"),
            (selective, "selective_p", "Tabela 7.5.3 Vreme konvergencije pod selective forwarding napadom")):
        if rows:
            vals = _vals(rows, kol)
            o.table(naslov, ["strategija"] + [f"{kol}={v:g}" for v in vals],
                    [[ov] + [_conv(_sel(rows, overlay=ov, **{kol: v})) for v in vals]
                     for ov in OVERLAYS])


# --- 7.6 ---------------------------------------------------------------------

def t76(o, main, rounds, churn, delay, beta):
    o.h("7.6. Stabilnost agregacione procene")
    # poredjenje stabilnosti po agregacionim funkcijama
    o.table(f"Tabela 7.6.1 Varijansa procene Var(x) u prozoru stabilnosti (beta={beta})",
            ["strategija"] + AGGS,
            [[ov] + [_e(_avg(_sel(main, overlay=ov, aggregation=ag, beta=beta), "stability"))
                     for ag in AGGS] for ov in OVERLAYS])

    # kratkorocno mala greska, dugorocno nestabilno
    if rounds:
        o.table(f"Tabela 7.6.2 Kratkorocna i dugorocna greska uz varijansu (beta={beta})",
                ["strategija", "agregacija", "greska r15", "greska r50", "Var(x)"],
                [[ov, ag,
                  _f(_avg(_sel(rounds, overlay=ov, aggregation=ag, beta=beta, round=15), "err_rel")),
                  _f(_avg(_sel(rounds, overlay=ov, aggregation=ag, beta=beta, round=50), "err_rel")),
                  _e(_avg(_sel(main, overlay=ov, aggregation=ag, beta=beta), "stability"))]
                 for ov in OVERLAYS for ag in AGGS])

    # uticaj churn i delay napada
    for rows, kol, naslov in (
            (churn, "churn_period", "Tabela 7.6.3 Varijansa procene pod churn napadom"),
            (delay, "delay_rounds", "Tabela 7.6.4 Varijansa procene pod delay napadom")):
        if rows:
            vals = _vals(rows, kol)
            o.table(naslov, ["strategija"] + [f"{kol}={v:g}" for v in vals],
                    [[ov] + [_e(_avg(_sel(rows, overlay=ov, **{kol: v}), "stability")) for v in vals]
                     for ov in OVERLAYS])


# --- 7.7 ---------------------------------------------------------------------

def t77(o, rounds, ecl_nodes, beta):
    o.h("7.7. Analiza peer diversity metrike")
    if rounds:
        last = _last_round(rounds)
        betas = _vals(rounds, "beta")
        # da li bucket diverzifikacija odrzava visoku raznovrsnost
        o.table(f"Tabela 7.7.1 Shannon entropija peer set-a po strategiji i beta (runda {last})",
                ["strategija"] + [f"beta={b}" for b in betas],
                [[ov] + [_f(_avg(_sel(rounds, overlay=ov, beta=b, round=last), "peer_diversity"))
                         for b in betas] for ov in OVERLAYS])
        # uticaj peer poisoning-a na entropiju (napad pocinje u rundi 11)
        o.table(f"Tabela 7.7.2 Shannon entropija kroz runde (beta={beta})",
                ["strategija"] + [f"r{r}" for r in ROUNDS],
                [[ov] + [_f(_avg(_sel(rounds, overlay=ov, beta=beta, round=r), "peer_diversity"))
                         for r in ROUNDS] for ov in OVERLAYS])
    # povezanost entropije sa Eclipse otpornoscu
    if ecl_nodes:
        last = _last_round(ecl_nodes)
        grupe = defaultdict(list)
        for r in _sel(ecl_nodes, round=last):
            grupe[int(r["honest_peers"])].append(r)
        o.table(f"Tabela 7.7.3 Entropija po broju cestitih suseda (runda {last})",
                ["cestitih suseda", "broj cvorova", "entropija", "izolovanih"],
                [[k, len(v), _f(_avg(v, "peer_diversity")), sum(1 for r in v if r["eclipsed"])]
                 for k, v in sorted(grupe.items())])


# --- 7.8 ---------------------------------------------------------------------

def t78(o, main, rounds, beta):
    o.h("7.8. Analiza kontrolnog i data overhead-a")
    # broj control i data poruka i njihov odnos
    red = []
    for ov in OVERLAYS:
        sel = _sel(main, overlay=ov, beta=beta)
        c, d = _avg(sel, "control_overhead"), _avg(sel, "data_overhead")
        red.append([ov, _f(c), _f(d), _f(c / d if c and d else None)])
    o.table(f"Tabela 7.8.1 Kontrolni i data overhead po cvoru i rundi (beta={beta})",
            ["strategija", "control", "data", "control/data"], red)

    # overhead po rundi
    if rounds:
        o.table(f"Tabela 7.8.2 Broj kontrolnih poruka po rundi (beta={beta})",
                ["strategija"] + [f"r{r}" for r in ROUNDS],
                [[ov] + [_f(_avg(_sel(rounds, overlay=ov, beta=beta, round=r), "control_msgs"), 1)
                         for r in ROUNDS] for ov in OVERLAYS])

    # kompromis bezbednost / stabilnost / overhead
    red = []
    for ov in OVERLAYS:
        for ag in AGGS:
            sel = _sel(main, overlay=ov, aggregation=ag, beta=beta)
            red.append([ov, ag, _f(_avg(sel, "final_err_rel")),
                        _f(_avg(sel, "final_sybil_penetration")),
                        _e(_avg(sel, "stability")), _f(_avg(sel, "control_overhead"))])
    o.table(f"Tabela 7.8.3 Kompromis bezbednosti, stabilnosti i overhead-a (beta={beta})",
            ["strategija", "agregacija", "greska", "penetracija", "Var(x)", "control"], red)


# --- 7.9 ---------------------------------------------------------------------

def t79(o, main, nodes, ecl, main_cfg, beta):
    o.h("7.9. Analiza kombinovanih napada")
    # da li odbrana jednog sloja indirektno poboljsava otpornost ostalih
    konf = [("bez zastite", "random", "mean"),
            ("samo kontrola strukture", "sybil_resistant", "mean"),
            ("samo robusna agregacija", "random", "trimmed_mean"),
            ("oba sloja", "sybil_resistant", "trimmed_mean")]
    o.table(f"Tabela 7.9.1 Doprinos slojeva odbrane (beta={beta})",
            ["konfiguracija", "greska", "Sybil penetracija", "Eclipse success rate"],
            [[naziv] + [_f(_avg(_sel(main, overlay=ov, aggregation=ag, beta=beta), k))
                        for k in ("final_err_rel", "final_sybil_penetration", "final_eclipse_rate")]
             for naziv, ov, ag in konf])

    # kako Sybil penetracija povecava verovatnocu Eclipse izolacije
    if ecl:
        o.table("Tabela 7.9.2 Sybil penetracija i Eclipse success rate",
                ["strategija", "beta", "penetracija", "Eclipse success rate"],
                [[ov, b, _f(_avg(_sel(ecl, overlay=ov, beta=b), "final_sybil_penetration")),
                  _f(_avg(_sel(ecl, overlay=ov, beta=b), "final_eclipse_rate"))]
                 for ov in OVERLAYS for b in _vals(ecl, "beta")])

    if nodes:
        last = _last_round(nodes)
        fin = _sel(nodes, beta=beta, round=last)
        # kako Eclipse povecava efektivni uticaj Byzantine vrednosti
        red = []
        for ov in OVERLAYS:
            for ag in AGGS:
                z, ost = [], []
                for r in _sel(fin, overlay=ov, aggregation=ag):
                    vz = _victims(main_cfg, int(r["n_honest"]), int(r["seed"]))
                    (z if r["node_id"] in vz else ost).append(r)
                red.append([ov, ag,
                            _f(mean(_byz_share(r) for r in z) if z else None),
                            _f(mean(_byz_share(r) for r in ost) if ost else None),
                            _f(_avg(z, "err_rel")), _f(_avg(ost, "err_rel"))])
        o.table(f"Tabela 7.9.3 Udeo Byzantine suseda i greska: zrtve Eclipse napada naspram ostalih "
                f"(beta={beta})",
                ["strategija", "agregacija", "Byzantine zrtve", "Byzantine ostali",
                 "greska zrtve", "greska ostali"], red)

        # kako degradacija peer set-a utice na robustne agregacione funkcije
        grupe = defaultdict(lambda: defaultdict(list))
        for r in fin:
            grupe[_mal_count(r)][r["aggregation"]].append(r["err_rel"])
        o.table(f"Tabela 7.9.4 Greska cvora po broju napadackih suseda (beta={beta})",
                ["napadackih suseda", "broj cvorova"] + AGGS,
                [[k, sum(len(v) for v in g.values())] +
                 [_f(mean(g[ag])) if g.get(ag) else "-" for ag in AGGS]
                 for k, g in sorted(grupe.items())])


# --- 7.10 --------------------------------------------------------------------

def t710(o, main, beta):
    o.h("7.10. Statisticka obrada rezultata")
    # srednja vrednost, std, min, max, varijabilnost preko seed-ova
    red = []
    for ov in OVERLAYS:
        for ag in AGGS:
            v = [r["final_err_rel"] for r in _sel(main, overlay=ov, aggregation=ag, beta=beta)]
            if not v:
                continue
            m, s = mean(v), pstdev(v)
            red.append([ov, ag, len(v), _f(m), _f(s), _f(min(v)), _f(max(v)),
                        _f(s / m if m else None)])
    o.table(f"Tabela 7.10.1 Relativna greska preko seed-ova (beta={beta})",
            ["strategija", "agregacija", "pokretanja", "srednja", "std", "min", "max", "CV"], red)

    # seed-ovi sa najvecim odstupanjem; osetljivost na slucajne varijacije
    red = []
    for ov in OVERLAYS:
        for ag in AGGS:
            sel = _sel(main, overlay=ov, aggregation=ag, beta=beta)
            if not sel:
                continue
            po_seed = defaultdict(list)
            for r in sel:
                po_seed[r["seed"]].append(r["final_err_rel"])
            uk = mean(r["final_err_rel"] for r in sel)
            s, v = max(((s, mean(x)) for s, x in po_seed.items()), key=lambda p: abs(p[1] - uk))
            red.append([ov, ag, int(s), _f(v), f"{100 * (v - uk) / uk:+.1f}%" if uk else "-"])
    o.table(f"Tabela 7.10.2 Seed sa najvecim odstupanjem od proseka (beta={beta})",
            ["strategija", "agregacija", "seed", "greska seed-a", "odstupanje"], red)


# --- glavni tok --------------------------------------------------------------

def t7part(o, part, part_rounds):
    # 7.4: napad particionisanjem mreze
    if not part:
        return
    grupe = _vals(part, "partition_groups")
    o.table("Tabela 7.4.7 Particionisanje: greska i vreme oporavka",
            ["strategija", "mera"] + [f"grupa={int(g)}" for g in grupe],
            [[ov, naziv] + [fun(_sel(part, overlay=ov, partition_groups=g))
                            for g in grupe]
             for ov in OVERLAYS
             for naziv, fun in (("greska", lambda r: _f(_avg(r, "final_err_rel"))),
                                ("vreme oporavka", lambda r: _conv(r, "recovery_time")))])

    if not part_rounds:
        return
    poslednja = max(r["round"] for r in part_rounds
                    if isinstance(r.get("round"), (int, float)))
    o.table("Tabela 7.4.8 Particionisanje: rasipanje procena i stabilnost",
            ["strategija", "mera"] + [f"grupa={int(g)}" for g in grupe],
            [[ov, naziv] + [fun(ov, g) for g in grupe]
             for ov in OVERLAYS
             for naziv, fun in (
                 ("raspon procena",
                  lambda ov, g: _f(_avg(_sel(part_rounds, overlay=ov,
                                             partition_groups=g, round=poslednja),
                                        "spread"), 2)),
                 ("varijansa procene",
                  lambda ov, g: _e(_avg(_sel(part, overlay=ov, partition_groups=g),
                                        "stability"))))],
            napomena="_Raspon procena je razlika najvece i najmanje procene u "
                     "poslednjoj rundi; nula znaci potpunu saglasnost cvorova._")


def main():
    ap = argparse.ArgumentParser(description="Tabele za poglavlje 7")
    ap.add_argument("--source", default="inprocess", choices=["inprocess", "docker"])
    ap.add_argument("--beta", type=float, default=0.3)
    args = ap.parse_args()

    base = os.path.join("results", args.source)

    def opt(name):
        p = os.path.join(base, name)
        return load(p) if os.path.exists(p) else []

    main_summary = opt("main_summary.csv")
    if not main_summary:
        raise SystemExit(f"nema {os.path.join(base, 'main_summary.csv')} - pokreni glavnu matricu")

    rounds, nodes = opt("main.csv"), opt("main_nodes.csv")
    ablation = opt("ablation_summary.csv")
    ecl, ecl_rounds, ecl_nodes = opt("eclipse_summary.csv"), opt("eclipse.csv"), opt("eclipse_nodes.csv")
    admission, flooding = opt("admission_summary.csv"), opt("flooding_summary.csv")
    churn, delay, selective = opt("churn_summary.csv"), opt("delay_summary.csv"), opt("selective_summary.csv")
    part, part_rounds = opt("partitioning_summary.csv"), opt("partitioning.csv")

    out = Out(os.path.join(base, "tables.md"))
    t71(out, main_summary, rounds, ablation, args.beta)
    t72(out, main_summary, ablation)
    t73(out, main_summary, rounds, nodes, admission, flooding, args.beta)
    t74(out, ecl, ecl_rounds, ecl_nodes, os.path.join("configs", "eclipse.json"))
    t7part(out, part, part_rounds)
    t75(out, main_summary, delay, selective, args.beta)
    t76(out, main_summary, rounds, churn, delay, args.beta)
    t77(out, rounds, ecl_nodes, args.beta)
    t78(out, main_summary, rounds, args.beta)
    t79(out, main_summary, nodes, ecl, os.path.join("configs", "main.json"), args.beta)
    t710(out, main_summary, args.beta)
    out.save()
    print("tabele ->", out.path)


if __name__ == "__main__":
    main()