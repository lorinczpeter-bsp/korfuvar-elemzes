"""Havi autó- és sofőrlétszám beolvasása az "Éves fajlagos fuvarozási mutatók" Google-táblázatból.

Hozzáférés (a transporeon-inno apphoz hasonlóan):
- Streamlit secrets `gcp_service_account` (mint a jutalék-appban) -> Drive API xlsx-export, csak olvasás;
- ennek hiányában a nyilvános xlsx-export (csak ha a táblázat link-megosztással olvasható).
A táblázat azonosítója a secrets `flotta_sheet_url` kulcsában van (a repó publikus).
"""
from __future__ import annotations

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


def fetch_xlsx(url_or_id: str, credentials=None) -> bytes:
    """A teljes táblázat xlsx-ként.

    credentials megadva: Google Drive API export szolgáltatásfiókkal (a táblázatot meg kell osztani
    olvasásra a szolgáltatásfiók client_email címével; elég a Drive API, külön Sheets API nem kell).
    credentials nélkül: nyilvános export-link (csak „bárki, akinek megvan a link” megosztásnál működik).
    """
    sid = sheet_id(url_or_id)
    if credentials:
        from google.auth.transport.requests import Request
        from google.oauth2.service_account import Credentials
        auth = Credentials.from_service_account_info(
            dict(credentials), scopes=["https://www.googleapis.com/auth/drive.readonly"])
        auth.refresh(Request())
        r = requests.get(f"https://www.googleapis.com/drive/v3/files/{sid}/export",
                         params={"mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 "supportsAllDrives": "true"},
                         headers={"Authorization": f"Bearer {auth.token}"}, timeout=60)
        if r.status_code in (403, 404):
            raise PermissionError(f"A szolgáltatásfiók nem látja a táblázatot (HTTP {r.status_code}). "
                                  "Oszd meg vele olvasásra a client_email címén.")
        r.raise_for_status()
        return r.content
    r = requests.get(f"https://docs.google.com/spreadsheets/d/{sid}/export", params={"format": "xlsx"}, timeout=60)
    r.raise_for_status()
    if r.content[:2] != b"PK":
        raise PermissionError("A Google-táblázat bejelentkezést kér (nincs nyilvános olvasási jog, "
                              "és nincs beállítva szolgáltatásfiók).")
    return r.content


def fetch_values(url_or_id: str, munkalap: str, credentials=None, xlsx: bytes | None = None) -> list[list]:
    import openpyxl
    xlsx = xlsx or fetch_xlsx(url_or_id, credentials)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx), read_only=True, data_only=True)
    if munkalap not in wb.sheetnames:
        raise ValueError(f"Nincs „{munkalap}” munkalap a táblázatban.")
    return [list(r) for r in wb[munkalap].iter_rows(max_row=80, values_only=True)]


def parse_ev(values: list[list], ev: int) -> pd.DataFrame:
    """Egy éves munkalap -> havi sorok (honap, nemz_gjmu, nemz_gkv, …)."""
    if not values:
        raise ValueError(f"A(z) {ev} munkalap üres.")
    def _ho(c):
        if isinstance(c, (int, float)) and float(c).is_integer() and 1 <= int(c) <= 12:
            return int(c)
        t = str(c).strip() if c is not None else ""
        return int(t) if re.fullmatch(r"\d{1,2}", t) and 1 <= int(t) <= 12 else None
    honap_oszlop = {i: _ho(c) for i, c in enumerate(values[0]) if _ho(c)}
    if not honap_oszlop:
        raise ValueError(f"A(z) {ev} munkalapon nem találom a hónap-oszlopokat (01–12).")
    adat: dict[int, dict] = {h: {"honap": f"{ev}-{h:02d}"} for h in honap_oszlop.values()}
    talalt = set()
    for sor in values[1:]:
        if not sor:
            continue
        nev = SOROK.get(str(sor[0]).strip()) if sor[0] is not None else None
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
    xlsx = fetch_xlsx(url_or_id, credentials)
    return pd.concat([parse_ev(fetch_values(url_or_id, str(ev), xlsx=xlsx), ev) for ev in sorted(set(evek))],
                     ignore_index=True)
