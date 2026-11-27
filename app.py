"""Körfuvar-elemzés · Bábolna Sped (A2 design: navy felső sáv, teljes szélesség)."""
from __future__ import annotations

import base64
import io
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from korfuvar import data as kd
from korfuvar import sheets

ROOT = Path(__file__).parent
NAVY, YELLOW, BG, BORDER, MUTED = "#2A3756", "#F2E47D", "#F4F5F8", "#E3E6EC", "#5B6475"
# negatív = narancs, pozitív = kék (világosságban is eltérnek)
KAT_SZIN = {
    "Mindig negatív": "#B54708",
    "Többnyire negatív": "#F5A35C",
    "Vegyes": "#B8BEC9",
    "Többnyire pozitív": "#7E93C9",
    "Mindig pozitív": NAVY,
}
EUR = "{:,.0f} €"
EURKM = "{:,.3f} €/km"

st.set_page_config(page_title="Körfuvar-elemzés | Bábolna Sped",
                   page_icon=str(ROOT / "assets" / "logo_ui.png"), layout="wide",
                   initial_sidebar_state="collapsed")


# --------------------------------------------------------------------------- arculat
@st.cache_data(show_spinner=False)
def asset64(name: str) -> str:
    return base64.b64encode((ROOT / "assets" / name).read_bytes()).decode()


def brand():
    fonts = "".join(
        f"@font-face{{font-family:{fam};src:url(data:font/ttf;base64,{asset64(fn)})}}"
        for fam, fn in [("Fira", "FiraSans-Regular.ttf"), ("Montserrat", "Montserrat.ttf")])
    st.markdown("<style>" + fonts + f"""
    html,body,.stApp{{font-family:Fira,sans-serif;color:#1F2937}}
    .stApp{{background:{BG}}}
    header[data-testid="stHeader"]{{display:none}}
    [data-testid="stSidebar"],[data-testid="collapsedControl"]{{display:none}}
    .block-container{{padding-top:0;max-width:1360px}}
    h1,h2,h3,h4{{font-family:Montserrat,sans-serif!important;color:{NAVY}}}
    .topbar{{background:{NAVY};color:#fff;margin:0 calc(50% - 50vw) 24px;padding:0 calc(50vw - 50% + 1rem)}}
    .topbar-in{{min-height:64px;display:flex;flex-wrap:wrap;align-items:center;gap:12px 20px}}
    .topbar img{{height:40px;background:#fff;border-radius:8px;padding:2px}}
    .crumb{{display:flex;align-items:center;gap:10px;font-size:14px}}
    .crumb .apps{{background:rgba(255,255,255,.08);padding:9px 14px;border-radius:10px}}
    .crumb .sep{{color:#7D88A3}} .crumb .cur{{color:{YELLOW};font-weight:600}}
    .pagehead h1{{margin:0;font-size:28px;letter-spacing:-.01em}}
    .pagehead p{{margin:4px 0 0;color:{MUTED};font-size:14px}}
    .kpi{{background:#fff;border:1px solid {BORDER};border-radius:14px;padding:18px 20px;height:100%;
          display:flex;flex-direction:column;gap:8px}}
    .kpi.dark{{background:{NAVY};border-color:{NAVY};color:#fff}}
    .kpi .l{{font-size:13px;color:{MUTED}}} .kpi.dark .l{{color:#C9D0DF}}
    .kpi .v{{font-family:Montserrat,sans-serif;font-weight:700;font-size:30px;color:{NAVY};
             font-variant-numeric:tabular-nums;letter-spacing:-.02em}}
    .kpi.dark .v{{color:#fff}}
    .kpi .s{{font-size:12px;color:{MUTED}}} .kpi.dark .s{{color:#C9D0DF}}
    .pill{{align-self:flex-start;font-size:12px;font-weight:600;color:{NAVY};background:{YELLOW};
           padding:3px 10px;border-radius:999px}}
    .note{{background:#FBF7D9;border:1px solid #E9DC7A;border-radius:12px;padding:12px 16px;
           font-size:14px;color:{NAVY};margin:6px 0 14px}}
    .card{{background:#fff;border:1px solid {BORDER};border-radius:14px;padding:16px 18px}}
    [data-testid="stTabs"] button[role="tab"]{{font-size:15px;height:44px}}
    [data-testid="stTabs"] [aria-selected="true"]{{color:{NAVY};font-weight:600}}
    [data-testid="stTabs"] [data-baseweb="tab-highlight"]{{background:{NAVY}}}
    div.stDownloadButton>button,div.stButton>button[kind="primary"]{{background:{YELLOW};color:{NAVY};
        border:0;border-radius:10px;font-weight:600;min-height:44px}}
    [data-testid="stExpander"],[data-testid="stFileUploader"]{{background:#fff;border-radius:12px}}
    </style>""", unsafe_allow_html=True)
    st.markdown(f"""<div class="topbar"><div class="topbar-in">
      <img src="data:image/png;base64,{asset64('logo_ui.png')}" alt="Bábolna Sped">
      <div class="crumb"><span class="apps">Alkalmazások</span><span class="sep">/</span>
      <span class="cur">Körfuvar-elemzés</span></div></div></div>""", unsafe_allow_html=True)


def kpi(col, label, value, sub="", dark=False, pill=None):
    col.markdown(
        f'<div class="kpi{" dark" if dark else ""}"><span class="l">{label}</span>'
        f'<span class="v">{value}</span>'
        + (f'<span class="pill">{pill}</span>' if pill else "")
        + (f'<span class="s">{sub}</span>' if sub else "") + "</div>", unsafe_allow_html=True)


def fmt(x, f=EURKM):
    return "–" if pd.isna(x) else f.format(x).replace(",", " ").replace(".", ",")


def style_fig(fig, h=380):
    fig.update_layout(height=h, margin=dict(l=8, r=8, t=36, b=8), paper_bgcolor="#fff",
                      plot_bgcolor="#fff", font=dict(family="Fira, sans-serif", color="#1F2937"),
                      legend=dict(orientation="h", y=-0.18, title=None), separators=", ")
    fig.update_xaxes(showgrid=False, linecolor=BORDER)
    fig.update_yaxes(gridcolor="#EDEFF3", zerolinecolor="#9CA3AF")
    return fig


# --------------------------------------------------------------------------- adatok
def secret(kulcs, alap=None):
    try:
        return st.secrets.get(kulcs, alap)
    except Exception:  # nincs secrets.toml
        return alap


@st.cache_data(ttl=600, show_spinner="Létszámadatok lekérése a Google-táblázatból…")
def flotta_google(url: str, evek: tuple[int, ...], creds: tuple | None) -> pd.DataFrame:
    return sheets.load_flotta_google(url, list(evek), dict(creds) if creds else None)


@st.cache_data(show_spinner="Körfuvarok betöltése…")
def betolt(files: tuple[tuple[str, bytes], ...]) -> pd.DataFrame:
    frames = [kd.read_korfuvar_file(b, nev) for nev, b in files]
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["Kör ID", "Fuvarszámok"])


def forrasfajlok(feltoltott) -> tuple[tuple[str, bytes], ...]:
    if feltoltott:
        return tuple((f.name, f.getvalue()) for f in feltoltott)
    helyi = sorted((ROOT / "data").glob("korfuvarok_*.xlsx"))
    return tuple((p.name, p.read_bytes()) for p in helyi)


brand()
st.markdown('<div class="pagehead"><h1>Körfuvar-elemzés</h1>'
            '<p>Visszatérő viszonylatok eredménye EUR/km-ben, tényleges és teljes sofőrállományú szcenárióval</p></div>',
            unsafe_allow_html=True)
st.write("")

with st.expander("Forrásfájlok és beállítások", expanded=False):
    c1, c2 = st.columns([3, 2])
    feltoltott = c1.file_uploader("Körfuvar-fájlok (korfuvarok_ÉÉÉÉ_HH.xlsx)", type="xlsx",
                                  accept_multiple_files=True,
                                  help="Ha nem töltesz fel semmit, a data/ mappában lévő fájlokat használja.")
    szint = c2.selectbox("Viszonylat = ", list(kd.VISZONYLAT_SZINTEK), index=0,
                         help="Export célállomás: a kifelé lerakó telephely, bármilyen import jön is vissza.")
    min_kor = c2.number_input("Visszatérő viszonylat: legalább ennyi kör", 2, 20, 3)
    alap = c2.radio("Besorolás alapja", ["Eredmény", "Fedezet", "Eredmény (szcenárió)"], horizontal=True,
                    help="Eredmény = bevétel − teljes költség. Fedezet = bevétel − futással arányos költség.")
    egyszeri = c2.checkbox("Egyszeri, kiugró karbantartás kiszűrése", value=True,
                           help="Ha egy kör karbantartási költsége a medián €/km több mint 3-szorosa és legalább "
                                "300 €-val több annál, a többletet (pl. nagyjavítás) nem terheljük a körre. "
                                "A kiszűrt tételek az Adatminőség fülön láthatók.")
    sheet_url = c1.text_input("Létszám: „Éves fajlagos fuvarozási mutatók” Google-táblázat hivatkozása",
                              value=secret("flotta_sheet_url", ""),
                              help="Streamlit Cloudon a secrets „flotta_sheet_url” kulcsában tárold, így nem kell beírni.")
    if c1.button("Létszám frissítése a Google-táblázatból"):
        flotta_google.clear()
        st.session_state.pop("flotta", None)
    flotta_fajl = c1.file_uploader("Tartalék: havi létszám CSV (ha a Google-táblázat nem érhető el)", type="csv",
                                   help="Formátum: config/flotta_minta.csv. A Szcenárió fülön kézzel is kitölthető.")
    st.caption("Költségbesorolás (fix / futással arányos): config/koltseg_besorolas.csv. "
               "A havi létszám és a cél-sofőrszám a Szcenárió fülön is állítható.")

files = forrasfajlok(feltoltott)
if not files:
    st.info("Tölts fel legalább egy körfuvar-fájlt, vagy másold őket a data/ mappába.")
    st.stop()

raw = betolt(files)
besorolas = kd.load_besorolas()
if flotta_fajl is not None and st.session_state.get("flotta_nev") != flotta_fajl.name:
    st.session_state["flotta"] = kd.load_flotta(flotta_fajl.getvalue())
    st.session_state["flotta_nev"] = flotta_fajl.name
    st.session_state["flotta_forras"] = f"feltöltött fájl ({flotta_fajl.name})"

# Minden új oldalbetöltéskor (új munkamenet) friss létszám a Google-táblázatból
if "flotta_munkamenet" not in st.session_state:
    st.session_state["flotta_munkamenet"] = True
    flotta_google.clear()
    if not st.session_state.get("flotta_nev"):
        st.session_state.pop("flotta", None)

flotta_hiba = None
flotta = st.session_state.get("flotta")
if flotta is None:
    evek = tuple(sorted({int(h[:4]) for h in raw["Hónap"].dropna().astype(str) if h[:4].isdigit()}))
    if sheet_url:
        try:
            creds = secret("gcp_service_account") or secret("google_service_account")
            flotta = flotta_google(sheet_url, evek, tuple(dict(creds).items()) if creds else None)
            st.session_state["flotta_forras"] = (
                f"Google-táblázat ({', '.join(map(str, evek))}), lekérve: {pd.Timestamp.now(tz='Europe/Budapest'):%Y.%m.%d. %H:%M}")
        except Exception as e:  # noqa: BLE001 – bármilyen hiba esetén jelzünk és tartalékra váltunk
            flotta_hiba = f"{type(e).__name__}: {e}"[:300]
    if flotta is None:
        flotta = kd.load_flotta()
        st.session_state["flotta_forras"] = ("config/ mappa" if len(flotta) else "nincs létszámadat")
    st.session_state["flotta"] = flotta
if flotta_hiba:
    st.warning(f"**A létszám Google-táblázata most nem érhető el**, ezért "
               f"{'a config/ mappában lévő fájlt használom' if len(flotta) else 'nincs létszámadat (a szcenárió nem módosít)'}. "
               f"Ok: {flotta_hiba}")
elif not sheet_url and not st.session_state.get("flotta_nev") and not len(flotta):
    st.info("Nincs megadva a létszám Google-táblázata (secrets: flotta_sheet_url), és nincs feltöltött létszámfájl.")
adat = kd.prepare(raw, besorolas, flotta, st.session_state.get("cel"), egyszeri_szures=egyszeri)
korok = kd.set_viszonylat(adat.korok, szint)
honapok = sorted(korok["Hónap"].dropna().unique())

f1, f2, f3 = st.columns([3, 1, 1])
valasztott = f1.multiselect("Hónapok", honapok, default=honapok)
orszagok = sorted(korok["Célország"].dropna().unique())
orszag = f2.multiselect("Célország", orszagok, placeholder="Mind")
elvart_pct = f3.number_input("Elvárt eredmény (% árbevétel)", 0.0, 30.0, 0.0, 0.5, format="%.1f",
                             help="0 = nullszaldó. Pl. 5 esetén azt a díjat számolja, amellyel az eredmény "
                                  "az árbevétel 5%-a lett volna.")
elvart = elvart_pct / 100

p = korok[korok["Pénzügyi körben"] & korok["Hónap"].isin(valasztott)]
if orszag:
    p = p[p["Célország"].isin(orszag)]
if p.empty:
    st.warning("A szűrésnek nincs értékelhető köre.")
    st.stop()

ossz = kd.osszesit(p.assign(_=1), ["_"]).iloc[0]
k = st.columns(4)
kpi(k[0], "Eredmény / km (tény)", fmt(ossz["Eredmény / km"]), dark=True,
    pill=f"{fmt(ossz['Eredmény'], EUR)} összesen",
    sub=(f"egyszeri karbantartás nélkül (kiszűrve: {fmt(p['Egyszeri karbantartás (kiszűrve)'].sum(), EUR)})"
         if p["Egyszeri karbantartás (kiszűrve)"].sum() > 0 else ""))
kpi(k[1], "Eredmény / km teljes sofőrállománnyal", fmt(ossz["Eredmény (szcenárió) / km"]),
    f"különbség: {fmt(ossz['Eredmény (szcenárió) / km'] - ossz['Eredmény / km'])} · "
    f"{fmt(ossz['Eredmény (szcenárió)'] - ossz['Eredmény'], EUR)}")
kpi(k[2], "Bevétel / km", fmt(ossz["Bevétel / km"]),
    f"futással arányos ktg {fmt(ossz['Futással arányos ktg / km'])} · fix {fmt(ossz['Fix ktg / km'])}")
kpi(k[3], "Értékelt körök", f"{int(ossz['Körök'])}",
    f"{fmt(ossz['Km'], '{:,.0f} km')} · {len(korok) - len(korok[korok['Pénzügyi körben']])} kör kizárva (Adatminőség fül)")
st.write("")

t_att, t_rossz, t_visz, t_part, t_vall, t_szc, t_lsz, t_kor, t_adat = st.tabs(
    ["Áttekintés", "Legrosszabb körök", "Viszonylatok", "Partnerek", "Vállalkozói összevetés",
     "Szcenárió: teljes sofőrállomány", "Létszám", "Körök", "Adatminőség"])

# --------------------------------------------------------------------------- Áttekintés
with t_att:
    h = kd.osszesit(p, ["Hónap"], elvart)
    c1, c2 = st.columns([3, 2])
    fig = go.Figure()
    fig.add_bar(x=h["Hónap"], y=h["Futással arányos ktg / km"], name="Futással arányos ktg", marker_color="#7E93C9")
    fig.add_bar(x=h["Hónap"], y=h["Fix ktg / km"], name="Fix ktg (tény)", marker_color=NAVY)
    fig.add_scatter(x=h["Hónap"], y=h["Bevétel / km"], name="Bevétel", mode="lines+markers+text",
                    line=dict(color="#B54708", width=3), text=[fmt(v, "{:.3f}") for v in h["Bevétel / km"]],
                    textposition="top center", textfont=dict(color="#B54708"))
    fig.add_scatter(x=h["Hónap"], y=h["Futással arányos ktg / km"] + h["Fix ktg (szcenárió) / km"],
                    name="Nullszaldós díj teljes sofőrállománnyal", mode="markers",
                    marker=dict(symbol="line-ew", size=70, line=dict(width=4, color="#C9A400")))
    fig.update_layout(barmode="stack", title="Havi fajlagos bevétel és költség (EUR/km)",
                      yaxis_range=[0, max(h["Bevétel / km"].max(), (h["Futással arányos ktg / km"] + h["Fix ktg / km"]).max()) * 1.15])
    fig.update_xaxes(type="category")
    c1.plotly_chart(style_fig(fig, 420), width="stretch")

    g = [c for c in p.columns if c.startswith("ktg · ")]
    s = (p[g].sum() / p["Km"].sum()).rename(lambda c: c.replace("ktg · ", "")).sort_values()
    fig2 = px.bar(s, orientation="h", title="Költségszerkezet (EUR/km, kiválasztott időszak)",
                  color_discrete_sequence=[NAVY], text=[fmt(v, "{:.3f}") for v in s])
    fig2.update_traces(textposition="outside", cliponaxis=False)
    fig2.update_layout(showlegend=False, yaxis_title=None, xaxis_title=None)
    c2.plotly_chart(style_fig(fig2, 420), width="stretch")

    st.markdown(f"#### Díjszint és szükséges díj havonta (elvárt eredmény: {elvart_pct:.1f}%)".replace(".", ","))
    st.caption("Nullszaldós díj = teljes költség / km. Szükséges díj = nullszaldós díj / (1 − elvárt eredmény %): "
               "ennyi fajlagos díj kellett volna az elvárt árbevétel-arányos eredményhez. Ha a tényleges díj "
               "magasabb volt, nincs hiány.")
    nsz = h[["Hónap", "Bevétel / km", "Árbevétel-arányos eredmény %", "Nullszaldós díj / km",
             "Szükséges díj / km", "Hiányzó díj / km", "Szükséges díjemelés %",
             "Szükséges díj / km (szcenárió)", "Hiányzó díj / km (szcenárió)"]].copy()
    st.dataframe(nsz, hide_index=True, width="stretch", column_config={
        "Bevétel / km": st.column_config.NumberColumn("Tényleges díj €/km", format="%.3f"),
        "Nullszaldós díj / km": st.column_config.NumberColumn("Nullszaldós díj €/km", format="%.3f"),
        "Hiányzó díj / km": st.column_config.NumberColumn("Hiányzó €/km", format="%.3f"),
        "Szükséges díjemelés %": st.column_config.NumberColumn("Szükséges emelés", format="%.1f%%"),
        "Árbevétel-arányos eredmény %": st.column_config.NumberColumn("Tény eredmény %", format="%.1f%%"),
        "Szükséges díj / km": st.column_config.NumberColumn("Szükséges díj €/km", format="%.3f"),
        "Szükséges díj / km (szcenárió)": st.column_config.NumberColumn(
            "Szükséges díj €/km teljes sofőrállománnyal", format="%.3f"),
        "Hiányzó díj / km (szcenárió)": st.column_config.NumberColumn(
            "Hiányzó €/km teljes sofőrállománnyal", format="%.3f")})
    st.markdown("#### Havi részletek")
    tabla = h[["Hónap", "Körök", "Km", "Bevétel / km", "Futással arányos ktg / km", "Fix ktg / km",
               "Fedezet / km", "Eredmény / km", "Fix ktg (szcenárió) / km", "Eredmény (szcenárió) / km",
               "Eredmény", "Eredmény (szcenárió)"]]
    st.dataframe(tabla, hide_index=True, width="stretch", column_config={
        **{c: st.column_config.NumberColumn(format="%.3f") for c in tabla.columns if c.endswith("/ km")},
        "Km": st.column_config.NumberColumn(format="%.0f"),
        "Eredmény": st.column_config.NumberColumn(format="%.0f €"),
        "Eredmény (szcenárió)": st.column_config.NumberColumn(format="%.0f €")})

# --------------------------------------------------------------------------- Legrosszabb körök
with t_rossz:
    o = kd.okok(p, min_kor=int(min_kor))
    r1, r2 = st.columns([1, 2])
    n_db = r1.number_input("Hány kör", 5, 50, 10)
    rang = r2.radio("Rangsor", ["Eredmény (EUR)", "Eredmény / km", "Eltérés a viszonylat átlagától (EUR)"],
                    horizontal=True)
    rcol = {"Eredmény (EUR)": "Eredmény", "Eredmény / km": "Eredmény / km",
            "Eltérés a viszonylat átlagától (EUR)": "Eltérés (EUR)"}[rang]
    top = o.nsmallest(int(n_db), rcol)
    st.markdown('<div class="note">Minden kört a <strong>saját viszonylata többi körének</strong> km-súlyozott '
                'átlagához hasonlít (ha kevés az azonos viszonylatú kör, az összes kör átlagához). '
                'A hatás oszlopok megmutatják, hány euróval rontotta (−) vagy javította (+) az eredményt az adott '
                'tétel az átlaghoz képest. Összegük = eltérés az átlagtól.</div>', unsafe_allow_html=True)
    hat_cols = [c for c in o.columns if c.startswith("Hatás: ")]
    cols = ["Kör ID", "Hónap", "Viszonylat", "Eredmény", "Eltérés (EUR)", "Fő okok", "Eredmény / km",
            "bm Eredmény / km", "Bevétel / km", "bm Bevétel / km", "Km", "Napok", "Km / nap", "Rakott km %",
            "Reláció", "Megbízók", "Egyszeri karbantartás (kiszűrve)"] + hat_cols + ["Összehasonlítás"]
    with st.expander("Oszlopok jelentése"):
        st.markdown("""
| Oszlop | Jelentés |
|---|---|
| **Eredmény** | A kör eredménye: bevétel − futással arányos költség − fix költség (EUR). Az egyszeri, kiugró karbantartás nélkül, ha a szűrés be van kapcsolva. |
| **Eltérés az átlagtól** | Mennyivel rosszabb (−) vagy jobb (+) a kör, mint egy átlagos kör ugyanezen a viszonylaton, ugyanennyi km-re vetítve (EUR). |
| **Fő okok** | A legnagyobb negatív tételek euróban, plusz jelzések: hosszú kör (≥30%-kal több nap), lassú (≥20%-kal kevesebb km/nap), sok üres km (rakott arány ≥5 százalékponttal kisebb), rövid kör (<60% km). |
| **Eredmény / km**, **(átlag)** | A kör, illetve a viszonylat többi körének eredménye EUR/km-ben. |
| **Díj / km**, **(átlag)** | A kör fuvardíja (bevétele) EUR/km-ben, és ugyanez a viszonylat többi körére. |
| **Km**, **Napok**, **Km / nap** | Menetlevél szerinti km, napok száma és napi átlagos futás. |
| **Rakott km %** | A megtett km rakottan futott aránya; minél kisebb, annál több az üres futás. |
| **Reláció**, **Megbízók** | A kör országsorrendje és a megbízók. |
| **Egyszeri karbantartás (kiszűrve)** | A körből kivett kiugró karbantartási többlet (EUR); nem rontja az eredményt. |
| **Hatás · Díj** | (Díj/km − átlagos díj/km) × km. Negatív: alacsonyabb díjon ment, mint az átlag. |
| **Hatás · Üzemanyag, Útdíj, Sofőrbér, Karbantartás, Egyéb futás** | (Átlagos költség/km − a kör költsége/km) × km. Negatív: ez a tétel drágább volt az átlagnál. |
| **Hatás · Fix költség** | Ugyanez a fix költségre. Negatív általában azt jelenti, hogy az autó abban a hónapban keveset futott, így a havi fix költsége kevés km-re oszlott. |
| **Összehasonlítás** | Mihez hasonlítunk: a viszonylat többi köréhez, vagy ha abból kevés van, az összes kör átlagához. |
""")
    st.dataframe(top[cols], hide_index=True, width="stretch", height=420, column_config={
        "Km": st.column_config.NumberColumn(format="%.0f"),
        "Napok": st.column_config.NumberColumn(format="%.0f"),
        "Km / nap": st.column_config.NumberColumn(format="%.0f"),
        "Rakott km %": st.column_config.NumberColumn(format="%.0f%%", help="Rakott km a menetlevél km arányában"),
        "Bevétel / km": st.column_config.NumberColumn("Díj / km", format="%.3f", help="A kör fuvardíja EUR/km"),
        "bm Bevétel / km": st.column_config.NumberColumn("Díj / km (átlag)", format="%.3f",
                                                         help="A viszonylat többi körének díja EUR/km"),
        "Eredmény / km": st.column_config.NumberColumn(format="%.3f"),
        "bm Eredmény / km": st.column_config.NumberColumn("Eredmény / km (átlag)", format="%.3f"),
        "Eredmény": st.column_config.NumberColumn(format="%.0f €", help="Bevétel − futással arányos − fix költség"),
        "Eltérés (EUR)": st.column_config.NumberColumn("Eltérés az átlagtól", format="%.0f €",
                                                       help="A kör eredménye − átlagos kör eredménye ugyanennyi km-re"),
        "Fő okok": st.column_config.TextColumn(width="large"),
        "Egyszeri karbantartás (kiszűrve)": st.column_config.NumberColumn(format="%.0f €"),
        **{c: st.column_config.NumberColumn(c.replace("Hatás: ", "Hatás · "), format="%.0f €",
                                            help="Negatív: ennyivel rontotta az eredményt az átlaghoz képest")
           for c in hat_cols}})

    kor_id = st.selectbox("Kör részletei", top["Kör ID"], index=None, placeholder="Válassz kört…",
                          format_func=lambda i: f"{i} · {top.set_index('Kör ID').at[i, 'Viszonylat']} · "
                                                f"{fmt(top.set_index('Kör ID').at[i, 'Eredmény'], EUR)}")
    if kor_id is not None:
        r = o.set_index("Kör ID").loc[kor_id]
        st.markdown(f"**{r['Viszonylat']}** · {r['Reláció']} · {r['Megbízók']} · {r['Vontatmány']} · "
                    f"{pd.to_datetime(r['Kör kezdete dátum']):%Y.%m.%d.} – {pd.to_datetime(r['Kör vége dátum']):%Y.%m.%d.} "
                    f"· összehasonlítás: {r['Összehasonlítás']}")
        d1, d2 = st.columns([2, 3])
        sorok = [("Km", r["Km"], r["bm Km"], "{:,.0f}"), ("Időtartam (nap)", r["Napok"], r["bm Napok"], "{:,.1f}"),
                 ("Km / nap", r["Km / nap"], r["bm Km / nap"], "{:,.0f}"),
                 ("Rakott km %", r["Rakott km %"], r["bm Rakott km %"], "{:,.1f}"),
                 ("Fogyasztás l/100km", r["Tankolás l/100km"], r["bm Tankolás l/100km"], "{:,.1f}"),
                 ("Díj €/km", r["Bevétel / km"], r["bm Bevétel / km"], "{:,.3f}")]
        for c, nev in kd.OK_KTG:
            sorok.append((f"{nev} €/km", r[c] / r["Km"], r[f"bm {c} / km"], "{:,.3f}"))
        sorok.append(("Eredmény €/km", r["Eredmény / km"], r["bm Eredmény / km"], "{:,.3f}"))
        d1.dataframe(pd.DataFrame([{"Mutató": m, "Ez a kör": fmt(a, f), "Átlag": fmt(b_, f),
                                    "Eltérés": fmt(a - b_, f) if pd.notna(a) and pd.notna(b_) else "–"}
                                   for m, a, b_, f in sorok]), hide_index=True, width="stretch", height=460)
        wf = go.Figure(go.Waterfall(
            x=["Átlagos eredmény"] + [c.replace("Hatás: ", "") for c in hat_cols] + ["Ez a kör"],
            measure=["absolute"] + ["relative"] * len(hat_cols) + ["total"],
            y=[r["bm Eredmény / km"] * r["Km"]] + [r[c] for c in hat_cols] + [0],
            text=[fmt(v, EUR) for v in [r["bm Eredmény / km"] * r["Km"]] + [r[c] for c in hat_cols] + [r["Eredmény"]]],
            increasing=dict(marker_color="#7E93C9"), decreasing=dict(marker_color="#B54708"),
            totals=dict(marker_color=NAVY), connector=dict(line=dict(color="#C9D0DF"))))
        wf.update_layout(title="Mitől lett ennyi az eredmény? (EUR, átlagos kör ugyanennyi km-re vetítve)",
                         showlegend=False)
        d2.plotly_chart(style_fig(wf, 460), width="stretch")

# --------------------------------------------------------------------------- Viszonylatok
with t_visz:
    vb, vtr, vip = st.tabs(["Besorolás", "Trend havonta", "Import-párosítás"])
    with vb:
        b = kd.besorol(p, alap=alap, min_kor=int(min_kor), elvart=elvart)
        st.markdown(f'<div class="note"><strong>{len(b)} visszatérő viszonylat</strong> ({szint.lower()}, '
                    f'legalább {int(min_kor)} kör). Besorolás alapja: <strong>{alap}</strong>, '
                    f'a negatív körök aránya szerint.</div>', unsafe_allow_html=True)
        kc = st.columns(5)
        for i, kat in enumerate(kd.KATEGORIAK):
            bb = b[b["Kategória"] == kat]
            kpi(kc[i], kat, f"{len(bb)}", f"{int(bb['Körök'].sum())} kör · {fmt(bb['Eredmény'].sum(), EUR)}")
        st.write("")

        fig = px.scatter(b, x="Fedezet / km", y="Eredmény / km", size="Körök", color="Kategória",
                         color_discrete_map=KAT_SZIN, category_orders={"Kategória": kd.KATEGORIAK},
                         hover_name="Viszonylat", size_max=36,
                         hover_data={"Körök": True, "Negatív körök %": ":.0f", "Bevétel / km": ":.3f",
                                     "Eredmény (szcenárió) / km": ":.3f", "Javaslat": True},
                         title="Viszonylatok: fedezet és teljes eredmény (EUR/km)")
        fig.add_vline(x=0, line_dash="dot", line_color="#9CA3AF")
        fig.add_hline(y=0, line_dash="dot", line_color="#9CA3AF")
        st.plotly_chart(style_fig(fig, 460), width="stretch")
        st.caption("Bal oldalt (negatív fedezet) a futással arányos költséget sem hozza be: vállalkozónak adható. "
                   "Jobb alsó negyed: fedezetet termel, de a fix költséget nem fedezi; eladásakor a fix költség nálunk marad.")

        kat_szuro = st.multiselect("Kategória", kd.KATEGORIAK, default=kd.KATEGORIAK)
        bt = b[b["Kategória"].isin(kat_szuro)]
        cols = ["Viszonylat", "Kategória", "Körök", "Hónapok", "Negatív körök %", "Fedezet negatív %",
                "Nap / kör", "Km / nap", "Üres km %",
                "Bevétel / km", "Árbevétel-arányos eredmény %", "Nullszaldós díj / km", "Szükséges díj / km",
                "Hiányzó díj / km", "Szükséges díjemelés %", "Szükséges díj / km (szcenárió)", "Futással arányos ktg / km", "Fix ktg / km", "Fedezet / km",
                "Eredmény / km", "Eredmény (szcenárió) / km", "Eredmény", "Javaslat"]
        st.dataframe(bt[cols], hide_index=True, width="stretch", height=460, column_config={
            **{c: st.column_config.NumberColumn(format="%.3f") for c in cols if c.endswith("/ km")},
            "Negatív körök %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
            "Fedezet negatív %": st.column_config.NumberColumn(format="%.0f%%"),
            "Nap / kör": st.column_config.NumberColumn(format="%.1f", help="Menetlevél szerinti napok átlagosan"),
            "Km / nap": st.column_config.NumberColumn(format="%.0f", help="Alacsony érték: sok állás / várakozás"),
            "Üres km %": st.column_config.NumberColumn(format="%.1f%%", help="Üresen futott km aránya (km-súlyozott)"),
            "Bevétel / km": st.column_config.NumberColumn("Díj / km", format="%.3f"),
            "Szükséges díjemelés %": st.column_config.NumberColumn(format="%.1f%%"),
            "Árbevétel-arányos eredmény %": st.column_config.NumberColumn("Eredmény %", format="%.1f%%"),
            "Eredmény": st.column_config.NumberColumn(format="%.0f €")})

        vis = st.selectbox("Viszonylat körei", b["Viszonylat"], index=None, placeholder="Válassz viszonylatot…")
        if vis:
            kk = p[p["Viszonylat"] == vis]
            st.dataframe(kk[["Kör ID", "Hónap", "Reláció", "Megbízók", "Vontatmány", "Kör kezdete dátum",
                             "Kör vége dátum", "Km", "Bevétel / km", "Fedezet / km", "Eredmény / km",
                             "Eredmény (szcenárió) / km", "Eredmény"]],
                         hide_index=True, width="stretch", column_config={
                             **{c: st.column_config.NumberColumn(format="%.3f") for c in kk.columns if c.endswith("/ km")},
                             "Km": st.column_config.NumberColumn(format="%.0f"),
                             "Eredmény": st.column_config.NumberColumn(format="%.0f €"),
                             "Kör kezdete dátum": st.column_config.DateColumn(format="YYYY.MM.DD"),
                             "Kör vége dátum": st.column_config.DateColumn(format="YYYY.MM.DD")})


    with vtr:
        tr = kd.trend(p)
        gyak = p["Viszonylat"].value_counts()
        gyak = gyak[~gyak.index.astype(str).str.startswith("–")]
        alap_v = list(gyak[gyak >= int(min_kor)].index[:6])
        tv = st.multiselect("Viszonylatok", list(gyak.index), default=alap_v, key="trend_v")
        mut = st.radio("Mutató", ["Eredmény / km", "Bevétel / km", "Fedezet / km", "Eredmény (szcenárió) / km"],
                       horizontal=True, key="trend_m")
        tt = tr[tr["Viszonylat"].isin(tv)]
        if len(tt):
            fig = px.line(tt, x="Hónap", y=mut, color="Viszonylat", markers=True, hover_data={"Körök": True},
                          title=f"{mut} havonta (EUR/km)")
            fig.add_hline(y=0, line_dash="dot", line_color="#9CA3AF")
            fig.update_xaxes(type="category")
            st.plotly_chart(style_fig(fig, 440), width="stretch")
            piv = tt.pivot_table(index="Viszonylat", columns="Hónap", values=mut).round(3)
            piv["Körök"] = tt.groupby("Viszonylat")["Körök"].sum()
            st.dataframe(piv, width="stretch")
        st.caption("Egy hónapban kevés kör esetén egyetlen kör is nagyot mozdíthat az értéken; a Körök oszlop mutatja a mintát.")
    with vip:
        st.markdown('<div class="note">Egy exportcélhoz (kifelé lerakó) melyik visszfuvar (befelé felrakó telephely) '
                    'hozza a legjobb kört. A kör teljes eredménye számít, a ki- és visszaút együtt.</div>',
                    unsafe_allow_html=True)
        ipd = kd.import_parositas(p, elvart)
        celok = [v for v in gyak.index if v in set(ipd["Viszonylat"])]
        cel = st.selectbox("Exportcél", celok, key="ip_cel")
        it = ipd[ipd["Viszonylat"] == cel].sort_values("Eredmény / km", ascending=False)
        icol = ["Import felrakó", "Körök", "Km", "Bevétel / km", "Fedezet / km", "Eredmény / km", "Nap / kör",
                "Km / nap", "Üres km %", "Eredmény"]
        st.dataframe(it[icol], hide_index=True, width="stretch", column_config={
            **{c: st.column_config.NumberColumn(format="%.3f") for c in icol if c.endswith("/ km")},
            "Bevétel / km": st.column_config.NumberColumn("Díj / km", format="%.3f"),
            "Km": st.column_config.NumberColumn(format="%.0f"),
            "Nap / kör": st.column_config.NumberColumn(format="%.1f"),
            "Km / nap": st.column_config.NumberColumn(format="%.0f"),
            "Üres km %": st.column_config.NumberColumn(format="%.1f%%"),
            "Eredmény": st.column_config.NumberColumn(format="%.0f €")})
        if len(it):
            fig = px.bar(it.head(15), x="Eredmény / km", y="Import felrakó", orientation="h",
                         color=np.where(it.head(15)["Eredmény / km"] >= 0, "pozitív", "negatív"),
                         color_discrete_map={"pozitív": NAVY, "negatív": "#B54708"},
                         text=[fmt(v, "{:.3f}") for v in it.head(15)["Eredmény / km"]],
                         title=f"{cel}: eredmény / km visszfuvaronként")
            fig.update_layout(showlegend=False, yaxis=dict(autorange="reversed", title=None))
            st.plotly_chart(style_fig(fig, max(300, 34 * min(len(it), 15) + 120)), width="stretch")

# --------------------------------------------------------------------------- Partnerek
with t_part:
    st.markdown('<div class="note">Megrendelőnként azok a körök, amelyekben a partner szerepel. Mivel egy körben '
                'több megrendelő is lehet (export és import), egy kör több partnernél is megjelenik, így az '
                'összegek nem adhatók össze. A kör szintű bevétel nem bontható partnerekre.</div>',
                unsafe_allow_html=True)
    pa = kd.partnerek(p, elvart)
    min_p = st.number_input("Legalább ennyi kör", 1, 50, 3, key="part_min")
    pa = pa[pa["Körök"] >= min_p].sort_values("Eredmény / km")
    pcol = ["Partner", "Körök", "Hónapok", "Km", "Negatív körök %", "Bevétel / km", "Fedezet / km",
            "Eredmény / km", "Szükséges díj / km", "Hiányzó díj / km", "Nap / kör", "Km / nap", "Üres km %",
            "Eredmény"]
    st.dataframe(pa[pcol], hide_index=True, width="stretch", height=520, column_config={
        **{c: st.column_config.NumberColumn(format="%.3f") for c in pcol if c.endswith("/ km")},
        "Bevétel / km": st.column_config.NumberColumn("Díj / km", format="%.3f"),
        "Negatív körök %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
        "Km": st.column_config.NumberColumn(format="%.0f"),
        "Nap / kör": st.column_config.NumberColumn(format="%.1f"),
        "Km / nap": st.column_config.NumberColumn(format="%.0f"),
        "Üres km %": st.column_config.NumberColumn(format="%.1f%%"),
        "Eredmény": st.column_config.NumberColumn("Eredmény (érintett körök)", format="%.0f €")})

# --------------------------------------------------------------------------- Vállalkozói összevetés
with t_vall:
    v1, v2 = st.columns([1, 2])
    ar = v1.number_input("Alvállalkozói díj (EUR/km)", 0.50, 3.00, 1.10, 0.01, format="%.2f")
    fix_marad = v2.radio("Ha kiadjuk, az autó…", ["áll, a fix költség nálunk marad",
                                                 "máshol hasznosítható (a fix költség nem ezt terheli)"],
                         horizontal=False) .startswith("áll")
    st.markdown('<div class="note">Kiadva a kör eredménye: <strong>díj − alvállalkozói díj</strong>. Saját futásnál '
                + ("a <strong>fedezet</strong> (díj − futással arányos költség), mert a fix költség mindenképp felmerül. "
                   "Kiadni akkor éri meg, ha az alvállalkozói díj a futással arányos költség/km alatt van."
                   if fix_marad else
                   "a <strong>teljes eredmény</strong>, mert az autó máshol termel. Kiadni akkor éri meg, ha az "
                   "alvállalkozói díj a teljes költség/km (nullszaldós díj) alatt van.")
                + '</div>', unsafe_allow_html=True)
    bv = kd.vallalkozoi(kd.besorol(p, alap=alap, min_kor=int(min_kor), elvart=elvart), ar, fix_marad)
    vk = st.columns(3)
    jo = bv[bv["Döntés"] == "Kiadni megéri"]
    kpi(vk[0], "Kiadni megéri", f"{len(jo)} viszonylat", f"{int(jo['Körök'].sum())} kör", dark=True)
    kpi(vk[1], "Becsült előny, ha ezeket kiadjuk", fmt(jo["Kiadás előnye (EUR)"].sum(), EUR), "a vizsgált időszakban")
    kpi(vk[2], "Saját autóval jobb", f"{len(bv) - len(jo)} viszonylat")
    st.write("")
    vcol = ["Viszonylat", "Döntés", "Kategória", "Körök", "Bevétel / km", "Futással arányos ktg / km",
            "Fix ktg / km", "Saját futás / km", "Kiadva eredmény / km", "Kiadás előnye / km", "Kiadás előnye (EUR)",
            "Max. alvállalkozói díj / km"]
    st.dataframe(bv[vcol], hide_index=True, width="stretch", height=520, column_config={
        **{c: st.column_config.NumberColumn(format="%.3f") for c in vcol if c.endswith("/ km")},
        "Bevétel / km": st.column_config.NumberColumn("Díj / km", format="%.3f"),
        "Saját futás / km": st.column_config.NumberColumn(format="%.3f",
                                                          help="Fedezet/km vagy eredmény/km a választástól függően"),
        "Max. alvállalkozói díj / km": st.column_config.NumberColumn(
            format="%.3f", help="Ennél olcsóbb alvállalkozói díjnál éri meg kiadni"),
        "Kiadás előnye (EUR)": st.column_config.NumberColumn(format="%.0f €")})

# --------------------------------------------------------------------------- Szcenárió
with t_szc:
    st.markdown('<div class="note">A fix költségek (amortizáció, biztosítás, általános) a forrásban járművenként és '
                'havonta a <strong>megtett km arányában</strong> oszlanak a körökre. Ha minden autóra lett volna sofőr, '
                'ugyanaz a havi fix költség több km-re oszlott volna. A szcenárió ezért a fix költséget '
                '<strong>tény sofőrszám / cél sofőrszám</strong> arányban csökkenti; a futással arányos költség és a '
                'bevétel/km változatlan.</div>', unsafe_allow_html=True)
    fl = pd.DataFrame({"honap": honapok}).merge(flotta, on="honap", how="left")
    fl["nemz_gjmu"] = fl["nemz_gjmu"].fillna(70)
    if fl["nemz_gkv"].isna().any():
        st.warning("Néhány hónapnál hiányzik a tényleges sofőrszám, ott a szcenárió nem módosít. "
                   "Töltsd fel a létszámfájlt, vagy írd be a táblázatba, majd számold újra.")
    fl["cel_sofor"] = fl["honap"].map(lambda m: (st.session_state.get("cel") or {}).get(m)) \
        .fillna(fl["nemz_gjmu"])
    szerk = st.data_editor(
        fl[["honap", "nemz_gjmu", "nemz_gkv", "cel_sofor", "atl_ledolg_nap", "km_per_ledolg_nap",
            "szabadsag_nap", "tappenz_nap"]],
        hide_index=True, width="stretch", disabled=["honap"],
        column_config={"honap": "Hónap", "nemz_gjmu": "Nemz. autó (db)", "nemz_gkv": "Nemz. sofőr (tény)",
                       "cel_sofor": st.column_config.NumberColumn("Cél sofőrszám", help="Alapból = autók száma"),
                       "atl_ledolg_nap": "Átl. ledolg. nap", "km_per_ledolg_nap": "Km / ledolg. nap",
                       "szabadsag_nap": "Szabadság (nap)", "tappenz_nap": "Táppénz (nap)"})
    if st.button("Szcenárió újraszámítása", type="primary"):
        st.session_state["cel"] = dict(zip(szerk["honap"], szerk["cel_sofor"]))
        modositott = szerk.drop(columns=["cel_sofor"]).set_index("honap")
        st.session_state["flotta"] = modositott.combine_first(flotta.set_index("honap")).reset_index()
        st.session_state["flotta_forras"] = st.session_state.get("flotta_forras", "") + " · kézzel módosítva"
        st.rerun()

    h = kd.osszesit(p, ["Hónap"])
    hh = h.melt(id_vars="Hónap", value_vars=["Eredmény / km", "Eredmény (szcenárió) / km"],
                var_name="Változat", value_name="EUR/km")
    hh["Változat"] = hh["Változat"].map({"Eredmény / km": "Tény", "Eredmény (szcenárió) / km": "Teljes sofőrállomány"})
    fig = px.bar(hh, x="Hónap", y="EUR/km", color="Változat", barmode="group",
                 color_discrete_map={"Tény": NAVY, "Teljes sofőrállomány": YELLOW},
                 text=[fmt(v, "{:.3f}") for v in hh["EUR/km"]], title="Eredmény / km: tény és teljes sofőrállomány")
    fig.update_xaxes(type="category")
    st.plotly_chart(style_fig(fig, 380), width="stretch")
    st.caption("Korlát: a teljesen álló autók fix költsége nem szerepel a körfuvar-fájlokban, így a tényleges "
               "fix költségteher ennél nagyobb lehet. Ehhez járművenkénti havi fix költség kell.")

# --------------------------------------------------------------------------- Létszám
with t_lsz:
    st.caption(f"Forrás: {st.session_state.get('flotta_forras', '–')}")
    if not len(flotta) or "nemz_gkv" not in flotta:
        st.info("Nincs létszámadat.")
    else:
        fl = flotta.sort_values("honap").copy()
        fl["Hiányzó sofőr"] = (fl["nemz_gjmu"] - fl["nemz_gkv"]).clip(lower=0)
        fl["Lefedettség %"] = fl["nemz_gkv"] / fl["nemz_gjmu"] * 100
        u = fl.iloc[-1]
        lk = st.columns(4)
        kpi(lk[0], f"Nemzetközi sofőr · {u['honap']}", fmt(u["nemz_gkv"], "{:,.1f}"),
            f"{fmt(u['nemz_gjmu'], '{:,.0f}')} autóra", dark=True)
        kpi(lk[1], "Hiányzó sofőr", fmt(u["Hiányzó sofőr"], "{:,.1f}"), f"lefedettség {fmt(u['Lefedettség %'], '{:,.1f}')}%")
        kpi(lk[2], "Átlag hiány az időszakban", fmt(fl["Hiányzó sofőr"].mean(), "{:,.1f}"),
            f"{fl['honap'].iloc[0]} – {fl['honap'].iloc[-1]}")
        if "km_per_ledolg_nap" in fl:
            kpi(lk[3], "Km / ledolgozott nap", fmt(u.get("km_per_ledolg_nap"), "{:,.0f}"), "utolsó hónap")
        st.write("")
        l1, l2 = st.columns(2)
        fig = go.Figure()
        fig.add_bar(x=fl["honap"], y=fl["Hiányzó sofőr"], name="Hiányzó sofőr", marker_color="#F5A35C",
                    text=[fmt(v, "{:.1f}") for v in fl["Hiányzó sofőr"]], textposition="outside")
        fig.add_scatter(x=fl["honap"], y=fl["nemz_gjmu"], name="Nemzetközi autó", mode="lines",
                        line=dict(color="#9CA3AF", dash="dash", width=2))
        fig.add_scatter(x=fl["honap"], y=fl["nemz_gkv"], name="Nemzetközi sofőr", mode="lines+markers",
                        line=dict(color=NAVY, width=3))
        fig.update_layout(title="Autók és sofőrök havonta",
                          yaxis=dict(title="fő / db", rangemode="tozero"))
        fig.update_xaxes(type="category")
        l1.plotly_chart(style_fig(fig, 380), width="stretch")
        if {"szabadsag_nap", "tappenz_nap"} <= set(fl.columns):
            fig2 = go.Figure()
            fig2.add_bar(x=fl["honap"], y=fl["szabadsag_nap"], name="Szabadság (nap)", marker_color="#7E93C9")
            fig2.add_bar(x=fl["honap"], y=fl["tappenz_nap"], name="Táppénz (nap)", marker_color="#B54708")
            fig2.update_layout(barmode="stack", title="Távollét havonta (nap)")
            fig2.update_xaxes(type="category")
            l2.plotly_chart(style_fig(fig2, 380), width="stretch")
        st.dataframe(fl, hide_index=True, width="stretch", column_config={
            "honap": "Hónap", "nemz_gjmu": "Nemz. autó", "belf_gjmu": "Belf. autó", "nemz_gkv": "Nemz. sofőr",
            "belf_gkv": "Belf. sofőr", "atl_ledolg_nap": "Átl. ledolg. nap", "km_per_ledolg_nap": "Km / ledolg. nap",
            "szabadsag_nap": "Szabadság", "tappenz_nap": "Táppénz", "havi_nemz_km": "Havi nemz. km",
            "nemz_futas_per_gkv": "Nemz. km / sofőr", "fajl_arbevetel_eur_km": "Árbevétel €/km (könyvelés)",
            "Lefedettség %": st.column_config.NumberColumn(format="%.1f%%"),
            "Hiányzó sofőr": st.column_config.NumberColumn(format="%.1f")})

# --------------------------------------------------------------------------- Körök
with t_kor:
    cols = ["Kör ID", "Hónap", "Viszonylat", "Régiópár", "Reláció", "Célország", "Megbízók", "Vontatmány", "Státusz",
            "Km", "Rakott km %", "Bevétel", "Futással arányos ktg", "Fix ktg", "Fedezet", "Eredmény",
            "Bevétel / km", "Fedezet / km", "Eredmény / km", "Eredmény (szcenárió) / km"]
    keres = st.text_input("Keresés (viszonylat, megbízó, rendszám)", placeholder="pl. DE65, HARTMANN, AEBY409")
    kt = p[cols]
    if keres:
        m = kt[["Viszonylat", "Reláció", "Megbízók", "Vontatmány"]].astype(str) \
            .apply(lambda s: s.str.contains(keres, case=False, regex=False)).any(axis=1)
        kt = kt[m]
    st.dataframe(kt, hide_index=True, width="stretch", height=560, column_config={
        **{c: st.column_config.NumberColumn(format="%.3f") for c in cols if c.endswith("/ km")},
        **{c: st.column_config.NumberColumn(format="%.0f €") for c in
           ["Bevétel", "Futással arányos ktg", "Fix ktg", "Fedezet", "Eredmény"]},
        "Km": st.column_config.NumberColumn(format="%.0f"),
        "Rakott km %": st.column_config.NumberColumn(format="%.1f%%")})

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        kd.besorol(p, alap=alap, min_kor=int(min_kor), elvart=elvart).to_excel(xw, sheet_name="Viszonylatok", index=False)
        kd.osszesit(p, ["Hónap"], elvart).to_excel(xw, sheet_name="Havi összesítő", index=False)
        kt.to_excel(xw, sheet_name="Körök", index=False)
        oo = kd.okok(p, min_kor=int(min_kor)).nsmallest(50, "Eredmény")
        oo[["Kör ID", "Hónap", "Viszonylat", "Reláció", "Megbízók", "Km", "Napok", "Eredmény", "Eredmény / km",
            "bm Eredmény / km", "Eltérés (EUR)", "Fő okok"] + [c for c in oo.columns if c.startswith("Hatás: ")]] \
            .to_excel(xw, sheet_name="Legrosszabb körök", index=False)
    st.download_button("Excel letöltése", buf.getvalue(), "korfuvar_elemzes.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# --------------------------------------------------------------------------- Adatminőség
with t_adat:
    c1, c2 = st.columns(2)
    st_tab = korok.groupby(["Hónap", "Státusz"]).size().unstack(fill_value=0)
    c1.markdown("#### Körök státusz szerint")
    c1.dataframe(st_tab, width="stretch")
    c1.caption("Pénzügyi kimutatásban: Teljes kör + Részleges / hibás. Kizárva: hiányos költségadat "
               "(hiányzó előző havi költségfájl), időszak határán csonkolt (a következő hónapban záruló) "
               "és futásadat nélküli körök.")
    c2.markdown("#### Költségoszlopok besorolása")
    c2.dataframe(besorolas, hide_index=True, width="stretch", height=360)
    if adat.besorolatlan:
        c2.warning("Besorolás nélküli költségoszlop (fixként számolva): " + ", ".join(adat.besorolatlan))
    st.markdown("#### Kiszűrt egyszeri karbantartás")
    ek = korok[korok["Egyszeri karbantartás (kiszűrve)"] > 0][
        ["Kör ID", "Hónap", "Viszonylat", "Vontatmány", "Km", "Egyszeri karbantartás (kiszűrve)", "ktg · Karbantartás"]]
    if len(ek):
        st.dataframe(ek, hide_index=True, width="stretch", column_config={
            "Km": st.column_config.NumberColumn(format="%.0f"),
            "Egyszeri karbantartás (kiszűrve)": st.column_config.NumberColumn(format="%.0f €"),
            "ktg · Karbantartás": st.column_config.NumberColumn("Bent hagyott karbantartás", format="%.0f €")})
    else:
        st.caption("Nincs kiszűrt tétel (vagy a szűrés ki van kapcsolva).")
    st.markdown("#### Kizárt körök")
    kiz = korok[~korok["Pénzügyi körben"]][["Kör ID", "Hónap", "Státusz", "Reláció", "Megbízók", "Magyarázat"]]
    st.dataframe(kiz, hide_index=True, width="stretch", height=320)
