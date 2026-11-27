"""Körfuvar-elemzés · Bábolna Sped (A2 design: navy felső sáv, teljes szélesség)."""
from __future__ import annotations

import base64
import io
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from korfuvar import data as kd

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
    min_kor = c2.number_input("Visszatérő viszonylat: legalább ennyi kör", 2, 20, 3)
    alap = c2.radio("Besorolás alapja", ["Eredmény", "Fedezet", "Eredmény (szcenárió)"], horizontal=True,
                    help="Eredmény = bevétel − teljes költség. Fedezet = bevétel − futással arányos költség.")
    flotta_fajl = c1.file_uploader("Havi létszám (flotta_ÉÉÉÉ.csv, pontosvesszős)", type="csv",
                                   help="Oszlopok: honap;nemz_gjmu;nemz_gkv;atl_ledolg_nap;km_per_ledolg_nap;"
                                        "szabadsag_nap;tappenz_nap. Ha nincs, a config/ mappából olvas, "
                                        "vagy a Szcenárió fülön kézzel is kitölthető.")
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
flotta = st.session_state.get("flotta")
if flotta is None:
    flotta = kd.load_flotta()
adat = kd.prepare(raw, besorolas, flotta, st.session_state.get("cel"))
korok = adat.korok
honapok = sorted(korok["Hónap"].dropna().unique())

f1, f2 = st.columns([3, 1])
valasztott = f1.multiselect("Hónapok", honapok, default=honapok)
orszagok = sorted(korok["Célország"].dropna().unique())
orszag = f2.multiselect("Célország", orszagok, placeholder="Mind")

p = korok[korok["Pénzügyi körben"] & korok["Hónap"].isin(valasztott)]
if orszag:
    p = p[p["Célország"].isin(orszag)]
if p.empty:
    st.warning("A szűrésnek nincs értékelhető köre.")
    st.stop()

ossz = kd.osszesit(p.assign(_=1), ["_"]).iloc[0]
k = st.columns(4)
kpi(k[0], "Eredmény / km (tény)", fmt(ossz["Eredmény / km"]), dark=True,
    pill=f"{fmt(ossz['Eredmény'], EUR)} összesen")
kpi(k[1], "Eredmény / km teljes sofőrállománnyal", fmt(ossz["Eredmény (szcenárió) / km"]),
    f"különbség: {fmt(ossz['Eredmény (szcenárió) / km'] - ossz['Eredmény / km'])} · "
    f"{fmt(ossz['Eredmény (szcenárió)'] - ossz['Eredmény'], EUR)}")
kpi(k[2], "Bevétel / km", fmt(ossz["Bevétel / km"]),
    f"futással arányos ktg {fmt(ossz['Futással arányos ktg / km'])} · fix {fmt(ossz['Fix ktg / km'])}")
kpi(k[3], "Értékelt körök", f"{int(ossz['Körök'])}",
    f"{fmt(ossz['Km'], '{:,.0f} km')} · {len(korok) - len(korok[korok['Pénzügyi körben']])} kör kizárva (Adatminőség fül)")
st.write("")

t_att, t_visz, t_szc, t_kor, t_adat = st.tabs(
    ["Áttekintés", "Viszonylatok", "Szcenárió: teljes sofőrállomány", "Körök", "Adatminőség"])

# --------------------------------------------------------------------------- Áttekintés
with t_att:
    h = kd.osszesit(p, ["Hónap"])
    c1, c2 = st.columns([3, 2])
    fig = go.Figure()
    fig.add_bar(x=h["Hónap"], y=h["Futással arányos ktg / km"], name="Futással arányos ktg", marker_color="#7E93C9")
    fig.add_bar(x=h["Hónap"], y=h["Fix ktg / km"], name="Fix ktg (tény)", marker_color=NAVY)
    fig.add_scatter(x=h["Hónap"], y=h["Bevétel / km"], name="Bevétel", mode="lines+markers+text",
                    line=dict(color="#B54708", width=3), text=[fmt(v, "{:.3f}") for v in h["Bevétel / km"]],
                    textposition="top center", textfont=dict(color="#B54708"))
    fig.add_scatter(x=h["Hónap"], y=h["Futással arányos ktg / km"] + h["Fix ktg (szcenárió) / km"],
                    name="Összköltség teljes sofőrállománnyal", mode="markers",
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

    tabla = h[["Hónap", "Körök", "Km", "Bevétel / km", "Futással arányos ktg / km", "Fix ktg / km",
               "Fedezet / km", "Eredmény / km", "Fix ktg (szcenárió) / km", "Eredmény (szcenárió) / km",
               "Eredmény", "Eredmény (szcenárió)"]]
    st.dataframe(tabla, hide_index=True, width="stretch", column_config={
        **{c: st.column_config.NumberColumn(format="%.3f") for c in tabla.columns if c.endswith("/ km")},
        "Km": st.column_config.NumberColumn(format="%.0f"),
        "Eredmény": st.column_config.NumberColumn(format="%.0f €"),
        "Eredmény (szcenárió)": st.column_config.NumberColumn(format="%.0f €")})

# --------------------------------------------------------------------------- Viszonylatok
with t_visz:
    b = kd.besorol(p, alap=alap, min_kor=int(min_kor))
    st.markdown(f'<div class="note"><strong>{len(b)} visszatérő viszonylat</strong> (régiópár: kifelé lerakó → '
                f'befelé felrakó, legalább {int(min_kor)} kör). Besorolás alapja: <strong>{alap}</strong>, '
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
            "Bevétel / km", "Futással arányos ktg / km", "Fix ktg / km", "Fedezet / km", "Eredmény / km",
            "Eredmény (szcenárió) / km", "Eredmény", "Javaslat"]
    st.dataframe(bt[cols], hide_index=True, width="stretch", height=460, column_config={
        **{c: st.column_config.NumberColumn(format="%.3f") for c in cols if c.endswith("/ km")},
        "Negatív körök %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
        "Fedezet negatív %": st.column_config.NumberColumn(format="%.0f%%"),
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
        st.session_state["flotta"] = szerk.drop(columns=["cel_sofor"]).reset_index(drop=True)
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

# --------------------------------------------------------------------------- Körök
with t_kor:
    cols = ["Kör ID", "Hónap", "Viszonylat", "Reláció", "Célország", "Megbízók", "Vontatmány", "Státusz",
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
        kd.besorol(p, alap=alap, min_kor=int(min_kor)).to_excel(xw, sheet_name="Viszonylatok", index=False)
        kd.osszesit(p, ["Hónap"]).to_excel(xw, sheet_name="Havi összesítő", index=False)
        kt.to_excel(xw, sheet_name="Körök", index=False)
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
    st.markdown("#### Kizárt körök")
    kiz = korok[~korok["Pénzügyi körben"]][["Kör ID", "Hónap", "Státusz", "Reláció", "Megbízók", "Magyarázat"]]
    st.dataframe(kiz, hide_index=True, width="stretch", height=320)
