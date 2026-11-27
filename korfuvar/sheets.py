"""Havi autó- és sofőrlétszám beolvasása az "Éves fajlagos fuvarozási mutatók" Google-táblázatból.

Hozzáférés (a transporeon-inno apphoz hasonlóan):
- Streamlit secrets `google_service_account` (szolgáltatásfiók JSON mezői) -> Sheets API, csak olvasás;
- ennek hiányában a nyilvános gviz CSV-export (csak ha a táblázat link-megosztással olvasható).
A táblázat azonosítója a secrets `flotta_sheet_url` kulcsában van (a repó publikus).
"""
from __future__ import annotations

import csv
import io
import re

import pandas as pd
import requests

SOROK = {  # táblázat "Megnevezés" -> belső oszlopnév
    "Nemz. gjmű db.sz.": "nemz_gjmu",
    "Belf. gjmű db.sz.": "belf_gjmu",
    "Nemzetközi gkv": "nemz_gkv",
    "Belföldes gkv": "belf_gkv",
    "Átl. ledolgozott nap": "atl_ledolg_nap",
    "KM/ledolgozott nap": "km_per_ledolg_nap",
    "Szabadság": "szabadsag_nap",
    "Táppénz": "tappenz_nap",
    "Havi nemz. km": "havi_nemz_km",
    "Átlagos nemz. futás/gkv": "nemz_futas_per_gkv",
    "Fajl. árbevétel €/km": "fajl_arbevetel_eur_km",
}


def sheet_id(url_or_id: str) -> str:
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", url_or_id or "")
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", url_or_id or ""):
        return url_or_id
    raise ValueError("Érvénytelen Google-táblázat hivatkozás.")


def _szam(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).replace("\xa0", "").replace(" ", "").replace("%", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def fetch_values(url_or_id: str, munkalap: str, credentials=None) -> list[list]:
    sid = sheet_id(url_or_id)
    if credentials:
        from google.auth.transport.requests import Request
        from google.oauth2.service_account import Credentials
        auth = Credentials.from_service_account_info(
            dict(credentials), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        auth.refresh(Request())
        r = requests.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/'{munkalap}'!A1:AD60",
                         params={"valueRenderOption": "UNFORMATTED_VALUE"},
                         headers={"Authorization": f"Bearer {auth.token}"}, timeout=30)
        r.raise_for_status()
        return r.json().get("values", [])
    r = requests.get(f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tq",
                     params={"tqx": "out:csv", "sheet": munkalap}, timeout=30)
    r.raise_for_status()
    if "<html" in r.text[:1000].lower() or "accounts.google.com" in r.url:
        raise PermissionError("A Google-táblázat bejelentkezést kér (nincs nyilvános olvasási jog).")
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))


def parse_ev(values: list[list], ev: int) -> pd.DataFrame:
    """Egy éves munkalap -> havi sorok (honap, nemz_gjmu, nemz_gkv, …)."""
    if not values:
        raise ValueError(f"A(z) {ev} munkalap üres.")
    fejlec = [str(c).strip() for c in values[0]]
    honap_oszlop = {i: int(c) for i, c in enumerate(fejlec) if re.fullmatch(r"\d{1,2}", c) and 1 <= int(c) <= 12}
    if not honap_oszlop:
        raise ValueError(f"A(z) {ev} munkalapon nem találom a hónap-oszlopokat (01–12).")
    adat: dict[int, dict] = {h: {"honap": f"{ev}-{h:02d}"} for h in honap_oszlop.values()}
    talalt = set()
    for sor in values[1:]:
        if not sor:
            continue
        nev = SOROK.get(str(sor[0]).strip())
        if not nev:
            continue
        talalt.add(nev)
        for i, h in honap_oszlop.items():
            adat[h][nev] = _szam(sor[i]) if i < len(sor) else None
    if "nemz_gkv" not in talalt or "nemz_gjmu" not in talalt:
        raise ValueError(f"A(z) {ev} munkalapon nincs 'Nemz. gjmű db.sz.' vagy 'Nemzetközi gkv' sor.")
    df = pd.DataFrame(list(adat.values()))
    return df[df["nemz_gkv"].notna()].reset_index(drop=True)


def load_flotta_google(url_or_id: str, evek: list[int], credentials=None) -> pd.DataFrame:
    return pd.concat([parse_ev(fetch_values(url_or_id, str(ev), credentials), ev) for ev in sorted(set(evek))],
                     ignore_index=True)
