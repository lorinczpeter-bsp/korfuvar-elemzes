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
_REGIO = re.compile(r"^\s*([A-Za-z]{2})[\s\-]*(?:[A-Za-z]{1,2}-)?(\d{2})")


def regio(cim) -> str | None:
    """'FR 56500 Naizin …' -> 'FR56'; 'AT-4550 …' -> 'AT45'."""
    if not isinstance(cim, str):
        return None
    m = _REGIO.match(cim)
    return (m.group(1).upper() + m.group(2)) if m else None


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
            cel_letszam: dict[str, float] | None = None) -> Adat:
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

    df["Státusz"] = df.apply(statusz, axis=1)
    df["Pénzügyi körben"] = df["Státusz"].isin(["Teljes kör", "Részleges / hibás"])

    # Régiópár: kifelé lerakó régió → befelé felrakó régió
    ki = df["Kifelé záró cím"].map(regio).fillna(df["Nemzetközi (semleges) kezdő cím"].map(regio))
    be = df["Befelé kezdő cím"].map(regio).fillna(df["Nemzetközi (semleges) záró cím"].map(regio))
    df["Kifelé régió"], df["Befelé régió"] = ki, be
    df["Viszonylat"] = ki.fillna("–") + " → " + be.fillna("–")

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
def osszesit(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    g = df.groupby(by, dropna=False)
    out = g.agg(**{
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
    return out.reset_index()


def besorol(df: pd.DataFrame, alap: str = "Eredmény", min_kor: int = 3) -> pd.DataFrame:
    """Visszatérő viszonylatok besorolása a negatív körök aránya szerint.

    alap: 'Eredmény' | 'Fedezet' | 'Eredmény (szcenárió)'
    """
    agg = osszesit(df, ["Viszonylat"])
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
