"""Körfuvar-adatok betöltése és mutatószámítás.

Bemenet: a "Bábolna Körfuvar Generálás" script havi xlsx kimenetei (körfuvarok lap).
Minden összeg EUR. A fix költségek a forrásban jármű-havonta km-arányosan vannak
a körökre osztva, ezért a teljes sofőrállomány szcenárió havi szorzóval skálázható.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"

BEVETEL = "Összes díj részarány (EUR)"
TELJES = "Teljes költség"
EREDMENY = "Járati eredmény"
ELSO_KTG = "Adminisztráció amortizáció"

KATEGORIAK = ["Mindig negatív", "Többnyire negatív", "Vegyes", "Többnyire pozitív", "Mindig pozitív"]


# --------------------------------------------------------------------------- konfiguráció
def load_besorolas(path: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(path or CONFIG / "koltseg_besorolas.csv", sep=";")


FLOTTA_OSZLOPOK = ["honap", "nemz_gjmu", "nemz_gkv", "atl_ledolg_nap", "km_per_ledolg_nap",
                   "szabadsag_nap", "tappenz_nap"]


def load_flotta(src=None) -> pd.DataFrame:
    """Havi autó- és sofőrlétszám. src: elérési út / feltöltött fájl; None = config/flotta_*.csv.

    A fájl nincs a (publikus) repóban; ha hiányzik, üres táblát ad, és a szcenárió szorzója 1.
    """
    if src is None:
        talalt = sorted(p for p in CONFIG.glob("flotta_*.csv") if "minta" not in p.name)
        if not talalt:
            return pd.DataFrame(columns=FLOTTA_OSZLOPOK)
        src = talalt[-1]
    if isinstance(src, (bytes, bytearray)):
        src = io.BytesIO(src)
    df = pd.read_csv(src, sep=";")
    df["honap"] = df["honap"].astype(str)
    for c in FLOTTA_OSZLOPOK[1:]:
        if c in df:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce")
    return df


# --------------------------------------------------------------------------- segédek
_CIM = re.compile(r"^\s*([A-Za-z]{1,2})[\s\-]*(?:[A-Za-z]{1,2}-)?(\d{4,5})\s*(?:[A-Z]{2}\s)?\s*(.*)$")
_ORSZAG_ALIAS = {"D": "DE", "F": "FR", "I": "IT", "A": "AT", "B": "BE", "L": "LU", "H": "HU"}
_ELOTAG = {"san", "santa", "santo", "st", "ste", "sankt", "saint", "sainte", "bad", "le", "la", "les", "l'",
           "den", "de", "het", "s", "mont", "port", "villa", "castel", "porto", "monte", "val", "bois", "neu"}
_KOTOSZO = {"am", "an", "bei", "der", "im", "in", "de", "di", "la", "le", "les", "en", "sur", "sous",
            "del", "della", "d'", "aan", "den", "op", "sul"}


def _cim_reszek(cim):
    if not isinstance(cim, str):
        return None
    m = _CIM.match(cim)
    if not m:
        return None
    orszag = m.group(1).upper()
    orszag = _ORSZAG_ALIAS.get(orszag, orszag)
    szavak = re.split(r"[\s,]+", m.group(3).strip())
    varos = []
    for i, w in enumerate(szavak):
        if not w:
            continue
        elozo = varos[-1] if varos else ""
        if (i == 0 or w.lower() in _KOTOSZO or elozo.lower() in _KOTOSZO
                or (i == 1 and elozo.lower().rstrip(".") in _ELOTAG) or w[:1].islower() and "'" in w):
            varos.append(w)
        else:
            break
    return orszag, m.group(2), " ".join(varos)


def regio(cim) -> str | None:
    """'FR 56500 Naizin …' -> 'FR56'; 'AT-4550 …' -> 'AT45'."""
    r = _cim_reszek(cim)
    return f"{r[0]}{r[1][:2]}" if r else None


def telephely(cim) -> str | None:
    """'DE 65203 Wiesbaden Kasteler Straße' -> 'DE 65203 Wiesbaden'."""
    r = _cim_reszek(cim)
    return f"{r[0]} {r[1]} {r[2]}".strip() if r else None


VISZONYLAT_SZINTEK = {
    "Export célállomás (település)": "Export cél",
    "Export cél régió (irsz. 2 jegy)": "Export cél régió",
    "Export célország": "Célország",
    "Régiópár (ki → be)": "Régiópár",
}


def honap_fajlnevbol(nev: str) -> str | None:
    m = re.search(r"(20\d{2})_(\d{1,2})", nev)
    return f"{m.group(1)}-{int(m.group(2)):02d}" if m else None


def statusz(row) -> str:
    magy = str(row.get("Magyarázat") or "")
    if pd.isna(row.get(TELJES)):
        return "Hiányos költségadat"
    if not (row.get("Km") or 0) > 0:
        return "Nincs futásadat"
    if "Időszak után" in magy or "Időszak előtt" in magy:
        return "Időszak határán csonkolt"
    if magy.startswith("Részleges") or "Hibás" in magy:
        return "Részleges / hibás"
    return "Teljes kör"


# --------------------------------------------------------------------------- betöltés
def read_korfuvar_file(src, nev: str | None = None) -> pd.DataFrame:
    """src: elérési út vagy feltöltött fájl (bytes / file-like)."""
    nev = nev or getattr(src, "name", None) or str(src)
    if isinstance(src, (bytes, bytearray)):
        src = io.BytesIO(src)
    df = pd.read_excel(src, sheet_name="körfuvarok")
    df = df[pd.to_numeric(df["Kör ID"], errors="coerce").notna()].copy()  # ÖSSZESEN sor ki
    df["Kör ID"] = df["Kör ID"].astype(int)
    df["Hónap"] = honap_fajlnevbol(Path(nev).name) or df["Kör kezdete hónap"].astype(str)
    df["Forrásfájl"] = Path(nev).name
    return df


@dataclass
class Adat:
    korok: pd.DataFrame          # minden kör, számolt mezőkkel
    koltseg_oszlopok: list[str]
    besorolatlan: list[str]      # költségoszlopok, amelyek nincsenek a besorolásban


def prepare(raw: pd.DataFrame, besorolas: pd.DataFrame, flotta: pd.DataFrame,
            cel_letszam: dict[str, float] | None = None, egyszeri_szures: bool = True,
            egyszeri_szorzo: float = 3.0, egyszeri_min_eur: float = 300.0) -> Adat:
    df = raw.copy()
    start, stop = df.columns.get_loc(ELSO_KTG), df.columns.get_loc(TELJES)
    ktg_cols = list(df.columns[start:stop])
    df[ktg_cols] = df[ktg_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    for c in ["Km", BEVETEL, TELJES, EREDMENY, "Menetlevél ∑ nap", "Rakott km %"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    tip = dict(zip(besorolas["oszlop"], besorolas["tipus"]))
    csop = dict(zip(besorolas["oszlop"], besorolas["csoport"]))
    besorolatlan = [c for c in ktg_cols if c not in tip]
    futas_cols = [c for c in ktg_cols if tip.get(c) == "futás"]
    fix_cols = [c for c in ktg_cols if tip.get(c) == "fix" or c in besorolatlan]

    df["Futással arányos ktg"] = df[futas_cols].sum(axis=1)
    df["Fix ktg"] = df[fix_cols].sum(axis=1)
    for g in sorted(set(csop.values()) - {"Részösszeg (nem számít bele)"}):
        cols = [c for c in ktg_cols if csop.get(c) == g]
        df[f"ktg · {g}"] = df[cols].sum(axis=1)

    # Egyszeri, kiugró karbantartás (pl. nagyjavítás) kiszűrése: ha a kör karbantartása a
    # medián €/km többszöröse és legalább egyszeri_min_eur-val több, a többletet kivesszük a körből.
    df["Egyszeri karbantartás (kiszűrve)"] = 0.0
    if egyszeri_szures and "ktg · Karbantartás" in df:
        km = pd.to_numeric(df["Km"], errors="coerce")
        arany = df["ktg · Karbantartás"] / km.where(km > 0)
        med = arany.median()
        tobblet = df["ktg · Karbantartás"] - med * km
        kiugro = (arany > egyszeri_szorzo * med) & (tobblet > egyszeri_min_eur)
        df.loc[kiugro, "Egyszeri karbantartás (kiszűrve)"] = tobblet[kiugro]
        df["ktg · Karbantartás"] -= df["Egyszeri karbantartás (kiszűrve)"]
        df["Futással arányos ktg"] -= df["Egyszeri karbantartás (kiszűrve)"]

    df["Státusz"] = df.apply(statusz, axis=1)
    df["Pénzügyi körben"] = df["Státusz"].isin(["Teljes kör", "Részleges / hibás"])

    # Régiópár: kifelé lerakó régió → befelé felrakó régió
    ki = df["Kifelé záró cím"].map(regio).fillna(df["Nemzetközi (semleges) kezdő cím"].map(regio))
    be = df["Befelé kezdő cím"].map(regio).fillna(df["Nemzetközi (semleges) záró cím"].map(regio))
    df["Kifelé régió"], df["Befelé régió"] = ki, be
    df["Régiópár"] = ki.fillna("–") + " → " + be.fillna("–")
    # Export célállomás: a kifelé (export) lerakó telephely, a visszfuvartól függetlenül
    df["Export cél"] = df["Kifelé záró cím"].map(telephely) \
        .fillna(df["Nemzetközi (semleges) kezdő cím"].map(telephely)).fillna("– (nincs export)")
    df["Export cél régió"] = ki.fillna("– (nincs export)")
    df["Viszonylat"] = df["Export cél"]

    # Eredmények
    df["Fedezet"] = df[BEVETEL] - df["Futással arányos ktg"]
    df["Eredmény"] = df[BEVETEL] - df["Futással arányos ktg"] - df["Fix ktg"]

    # Teljes sofőrállomány szcenárió: a jármű-havi fix költség km-arányosan oszlik,
    # teljes létszámnál ugyanaz a fix költség (cél/tény) arányban több km-re jutna.
    fl = flotta.set_index("honap")
    cel = cel_letszam or {}
    tény = df["Hónap"].map(fl["nemz_gkv"])
    célsz = df["Hónap"].map(lambda h: cel.get(h, fl["nemz_gjmu"].get(h, np.nan)))
    df["Sofőr (tény)"] = tény
    df["Sofőr (cél)"] = célsz
    df["Fix szorzó"] = (tény / célsz).clip(upper=1.0).fillna(1.0)
    df["Fix ktg (szcenárió)"] = df["Fix ktg"] * df["Fix szorzó"]
    df["Eredmény (szcenárió)"] = df["Fedezet"] - df["Fix ktg (szcenárió)"]

    km = df["Km"].where(df["Km"] > 0)
    for c in [BEVETEL, "Futással arányos ktg", "Fix ktg", "Fix ktg (szcenárió)",
              "Fedezet", "Eredmény", "Eredmény (szcenárió)"]:
        df[f"{c} / km"] = df[c] / km
    df.rename(columns={f"{BEVETEL} / km": "Bevétel / km"}, inplace=True)
    df["Bevétel"] = df[BEVETEL]
    return Adat(df, ktg_cols, besorolatlan)


def load(paths_or_files, besorolas=None, flotta=None, cel_letszam=None) -> Adat:
    raw = pd.concat([read_korfuvar_file(p) for p in paths_or_files], ignore_index=True)
    raw = raw.drop_duplicates(subset=["Kör ID", "Fuvarszámok"])
    return prepare(raw, besorolas if besorolas is not None else load_besorolas(),
                   flotta if flotta is not None else load_flotta(), cel_letszam)


# --------------------------------------------------------------------------- aggregálás
def osszesit(df: pd.DataFrame, by: list[str], elvart: float = 0.0) -> pd.DataFrame:
    """elvart: elvárt árbevétel-arányos eredmény (0,05 = 5%)."""
    df = df.assign(_napok=pd.to_numeric(df.get("Menetlevél ∑ nap"), errors="coerce"),
                   _rakott_km=df["Km"] * pd.to_numeric(df.get("Rakott km %"), errors="coerce") / 100,
                   _km_rakottal=df["Km"].where(pd.to_numeric(df.get("Rakott km %"), errors="coerce").notna()))
    g = df.groupby(by, dropna=False)
    out = g.agg(**{
        "Napok": ("_napok", "sum"),
        "_rakott_km": ("_rakott_km", "sum"),
        "_km_rakottal": ("_km_rakottal", "sum"),
        "Körök": ("Kör ID", "size"),
        "Hónapok": ("Hónap", "nunique"),
        "Km": ("Km", "sum"),
        "Bevétel": ("Bevétel", "sum"),
        "Futással arányos ktg": ("Futással arányos ktg", "sum"),
        "Fix ktg": ("Fix ktg", "sum"),
        "Fedezet": ("Fedezet", "sum"),
        "Eredmény": ("Eredmény", "sum"),
        "Eredmény (szcenárió)": ("Eredmény (szcenárió)", "sum"),
        "Fix ktg (szcenárió)": ("Fix ktg (szcenárió)", "sum"),
    })
    for c in ["Bevétel", "Futással arányos ktg", "Fix ktg", "Fix ktg (szcenárió)",
              "Fedezet", "Eredmény", "Eredmény (szcenárió)"]:
        out[f"{c} / km"] = out[c] / out["Km"].where(out["Km"] > 0)
    out["Nap / kör"] = out["Napok"] / out["Körök"]
    out["Km / nap"] = out["Km"] / out["Napok"].where(out["Napok"] > 0)
    out["Üres km %"] = (1 - out["_rakott_km"] / out["_km_rakottal"].where(out["_km_rakottal"] > 0)) * 100
    out = out.drop(columns=["_rakott_km", "_km_rakottal"])
    # Nullszaldós díj: az a fajlagos díj, amelynél az eredmény 0 (= teljes költség / km)
    out["Nullszaldós díj / km"] = out["Futással arányos ktg / km"] + out["Fix ktg / km"]
    out["Nullszaldós díj / km (szcenárió)"] = out["Futással arányos ktg / km"] + out["Fix ktg (szcenárió) / km"]
    # Szükséges díj az elvárt árbevétel-arányos eredményhez: díj × (1 − elvárt) = költség/km
    out["Szükséges díj / km"] = out["Nullszaldós díj / km"] / (1 - elvart)
    out["Szükséges díj / km (szcenárió)"] = out["Nullszaldós díj / km (szcenárió)"] / (1 - elvart)
    out["Hiányzó díj / km"] = (out["Szükséges díj / km"] - out["Bevétel / km"]).clip(lower=0)
    out["Hiányzó díj / km (szcenárió)"] = (out["Szükséges díj / km (szcenárió)"] - out["Bevétel / km"]).clip(lower=0)
    out["Szükséges díjemelés %"] = out["Hiányzó díj / km"] / out["Bevétel / km"] * 100
    out["Árbevétel-arányos eredmény %"] = out["Eredmény"] / out["Bevétel"] * 100
    return out.reset_index()


def besorol(df: pd.DataFrame, alap: str = "Eredmény", min_kor: int = 3, elvart: float = 0.0) -> pd.DataFrame:
    """Visszatérő viszonylatok besorolása a negatív körök aránya szerint.

    alap: 'Eredmény' | 'Fedezet' | 'Eredmény (szcenárió)'
    """
    df = df[~df["Viszonylat"].astype(str).str.startswith("–")]
    agg = osszesit(df, ["Viszonylat"], elvart)
    neg = df.assign(_neg=df[alap] < 0).groupby("Viszonylat")["_neg"].mean()
    agg["Negatív körök %"] = agg["Viszonylat"].map(neg) * 100
    fedezet_neg = df.assign(_n=df["Fedezet"] < 0).groupby("Viszonylat")["_n"].mean()
    agg["Fedezet negatív %"] = agg["Viszonylat"].map(fedezet_neg) * 100
    agg = agg[agg["Körök"] >= min_kor].copy()

    # 100% neg / ≥2/3 / (1/3, 2/3) / ≤1/3 / 0%
    def kat(p):
        if p >= 100: return KATEGORIAK[0]
        if p <= 0: return KATEGORIAK[4]
        if p >= 200 / 3: return KATEGORIAK[1]
        if p <= 100 / 3: return KATEGORIAK[3]
        return KATEGORIAK[2]

    agg["Kategória"] = pd.Categorical(agg["Negatív körök %"].map(kat), KATEGORIAK, ordered=True)

    def javaslat(r):
        if r["Kategória"] in KATEGORIAK[:2]:
            if r["Fedezet"] < 0:
                return "Vállalkozónak adni (a futással arányos költséget sem fedezi)"
            return "Tartani / árazni (fedezetet termel, a fix költséget nem fedezi)"
        if r["Kategória"] in KATEGORIAK[3:]:
            return "Megtartani, erősíteni"
        return "Figyelni"

    agg["Javaslat"] = agg.apply(javaslat, axis=1)
    return agg.sort_values(["Kategória", "Eredmény / km"]).reset_index(drop=True)


def set_viszonylat(df: pd.DataFrame, szint: str) -> pd.DataFrame:
    df = df.copy()
    df["Viszonylat"] = df[VISZONYLAT_SZINTEK.get(szint, "Export cél")].fillna("–")
    return df


# --------------------------------------------------------------------------- eltérés-okok
OK_MUTATOK = [  # (oszlop, név, egység, "magas rossz?")
    ("Km", "Km", "km", None),
    ("Napok", "Időtartam", "nap", True),
    ("Km / nap", "Km / nap", "km", False),
    ("Rakott km %", "Rakott km", "%", False),
    ("Tankolás l/100km", "Fogyasztás", "l/100km", True),
]
OK_KTG = [  # (oszlop, név)
    ("ktg · Üzemanyag", "Üzemanyag"),
    ("ktg · Útdíj", "Útdíj"),
    ("ktg · Sofőrbér és napidíj", "Sofőrbér, napidíj"),
    ("ktg · Karbantartás", "Karbantartás"),
    ("ktg · Egyéb futás", "Egyéb futás"),
    ("Fix ktg", "Fix költség"),
]


def _kiegeszit(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Napok"] = pd.to_numeric(df["Menetlevél ∑ nap"], errors="coerce").where(lambda x: x > 0)
    df["Km / nap"] = df["Km"] / df["Napok"]
    df["Tankolás l/100km"] = pd.to_numeric(df.get("Menetlevél tankolás / 100 km"), errors="coerce")
    df["Eredmény / nap"] = df["Eredmény"] / df["Napok"]
    return df


def benchmark(df: pd.DataFrame, min_kor: int = 3) -> pd.DataFrame:
    """Minden körhöz összehasonlítási alap: a viszonylat többi körének km-súlyozott átlaga
    (ha legalább min_kor-1 másik kör van), különben a kiválasztott összes kör átlaga."""
    df = _kiegeszit(df)
    sum_cols = ["Km", "Bevétel", "Napok"] + [c for c, _ in OK_KTG]
    tot = df[sum_cols].sum()
    grp = df.groupby("Viszonylat")[sum_cols].transform("sum")
    n = df.groupby("Viszonylat")["Kör ID"].transform("size")
    sajat = (n - 1) >= max(min_kor - 1, 1)
    # a kör saját magát kihagyja a viszonylat-átlagból
    alap = (grp - df[sum_cols]).where(sajat, other=pd.DataFrame([tot] * len(df), index=df.index))
    out = pd.DataFrame(index=df.index)
    out["Összehasonlítás"] = np.where(sajat, "viszonylat (" + (n - 1).astype(str) + " másik kör)",
                                      "összes kör (kevés azonos viszonylatú)")
    km = alap["Km"]
    out["bm Bevétel / km"] = alap["Bevétel"] / km
    for c, _ in OK_KTG:
        out[f"bm {c} / km"] = alap[c] / km
    out["bm Napok"] = np.where(sajat, alap["Napok"] / (n - 1).where(n > 1), tot["Napok"] / len(df))
    out["bm Km"] = np.where(sajat, km / (n - 1).where(n > 1), tot["Km"] / len(df))
    out["bm Km / nap"] = alap["Km"] / alap["Napok"]
    for c in ["Rakott km %", "Tankolás l/100km"]:
        w = df["Km"]
        if sajat.any():
            g_num = (df[c] * w).groupby(df["Viszonylat"]).transform("sum") - df[c].fillna(0) * w
            g_den = w.where(df[c].notna(), 0).groupby(df["Viszonylat"]).transform("sum") - w.where(df[c].notna(), 0)
            v = g_num / g_den
        else:
            v = pd.Series(np.nan, index=df.index)
        osszes = (df[c] * w).sum() / w.where(df[c].notna(), 0).sum()
        out[f"bm {c}"] = v.where(sajat, osszes)
    return pd.concat([df, out], axis=1)


def okok(df: pd.DataFrame, min_kor: int = 3) -> pd.DataFrame:
    """Körönként az eredmény eltérésének felbontása (EUR) a benchmarkhoz képest."""
    b = benchmark(df, min_kor)
    b["Hatás: Díj"] = (b["Bevétel"] / b["Km"] - b["bm Bevétel / km"]) * b["Km"]
    for c, nev in OK_KTG:
        b[f"Hatás: {nev}"] = -(b[c] / b["Km"] - b[f"bm {c} / km"]) * b["Km"]
    b["bm Eredmény / km"] = b["bm Bevétel / km"] - sum(b[f"bm {c} / km"] for c, _ in OK_KTG)
    b["Eltérés (EUR)"] = (b["Eredmény / km"] - b["bm Eredmény / km"]) * b["Km"]

    def szoveg(r):
        hat = {"Díj": r["Hatás: Díj"], **{n: r[f"Hatás: {n}"] for _, n in OK_KTG}}
        rossz = sorted([(v, k) for k, v in hat.items() if v < -20], key=lambda x: x[0])[:3]
        t = []
        for v, k in rossz:
            if k == "Díj":
                t.append(f"alacsony díj {r['Bevétel / km']:.2f} vs {r['bm Bevétel / km']:.2f} €/km ({v:,.0f} €)")
            elif k == "Fix költség":
                t.append(f"magas fix ktg/km {r['Fix ktg / km']:.2f} vs {r['bm Fix ktg / km']:.2f} – "
                         f"az autó keveset futott a hónapban ({v:,.0f} €)")
            else:
                col = [c for c, n in OK_KTG if n == k][0]
                t.append(f"magas {k.lower()} {r[col] / r['Km']:.2f} vs {r[f'bm {col} / km']:.2f} €/km ({v:,.0f} €)")
        if pd.notna(r["Napok"]) and pd.notna(r["bm Napok"]) and r["Napok"] >= r["bm Napok"] * 1.3 and r["Napok"] - r["bm Napok"] >= 1:
            t.append(f"hosszú kör: {r['Napok']:.0f} vs {r['bm Napok']:.1f} nap")
        if pd.notna(r["Km / nap"]) and pd.notna(r["bm Km / nap"]) and r["Km / nap"] < r["bm Km / nap"] * 0.8:
            t.append(f"lassú: {r['Km / nap']:.0f} vs {r['bm Km / nap']:.0f} km/nap")
        if pd.notna(r["Rakott km %"]) and pd.notna(r["bm Rakott km %"]) and r["Rakott km %"] < r["bm Rakott km %"] - 5:
            t.append(f"sok üres km: rakott {r['Rakott km %']:.0f}% vs {r['bm Rakott km %']:.0f}%")
        if r["Km"] < 0.6 * r["bm Km"]:
            t.append(f"rövid kör: {r['Km']:,.0f} vs {r['bm Km']:,.0f} km")
        return "; ".join(t).replace(",", " ").replace(".", ",") if t else "nincs kiugró eltérés"

    b["Fő okok"] = b.apply(szoveg, axis=1)
    return b


# --------------------------------------------------------------------------- további nézetek
def import_parositas(df: pd.DataFrame, elvart: float = 0.0) -> pd.DataFrame:
    """Exportcélonként: melyik import-felrakó (visszfuvar) hozza a legjobb kört."""
    d = df.assign(**{"Import felrakó": df["Befelé kezdő cím"].map(telephely)
                     .fillna(df["Nemzetközi (semleges) záró cím"].map(telephely)).fillna("– (nincs import)")})
    return osszesit(d, ["Viszonylat", "Import felrakó"], elvart)


def partnerek(df: pd.DataFrame, elvart: float = 0.0) -> pd.DataFrame:
    """Megrendelőnként: azok a körök, amelyekben a partner szerepel (egy kör több partnernél is számít)."""
    d = df.assign(Partner=df["Megbízók"].fillna("–").astype(str).str.split(r"\s*\|\s*")).explode("Partner")
    d["Partner"] = d["Partner"].str.strip()
    out = osszesit(d, ["Partner"], elvart)
    neg = d.assign(_n=d["Eredmény"] < 0).groupby("Partner")["_n"].mean() * 100
    out["Negatív körök %"] = out["Partner"].map(neg)
    return out


def trend(df: pd.DataFrame) -> pd.DataFrame:
    return osszesit(df, ["Viszonylat", "Hónap"])


def vallalkozoi(b: pd.DataFrame, ar_km: float, fix_marad: bool = True) -> pd.DataFrame:
    """Kiadás alvállalkozónak vs. saját futás viszonylatonként.

    Kiadva: bevétel − alvállalkozói díj. Saját futás: fix_marad esetén a fedezet (a fix költség
    mindenképp nálunk marad, az autó áll), különben a teljes eredmény (az autó máshol hasznosítható).
    """
    o = b.copy()
    o["Alvállalkozói díj / km"] = ar_km
    o["Kiadva eredmény / km"] = o["Bevétel / km"] - ar_km
    o["Saját futás / km"] = o["Fedezet / km"] if fix_marad else o["Eredmény / km"]
    o["Kiadás előnye / km"] = o["Kiadva eredmény / km"] - o["Saját futás / km"]
    o["Kiadás előnye (EUR)"] = o["Kiadás előnye / km"] * o["Km"]
    o["Max. alvállalkozói díj / km"] = o["Futással arányos ktg / km"] if fix_marad else o["Nullszaldós díj / km"]
    o["Döntés"] = np.where(o["Kiadás előnye / km"] > 0, "Kiadni megéri", "Saját autóval jobb")
    return o.sort_values("Kiadás előnye / km", ascending=False)
