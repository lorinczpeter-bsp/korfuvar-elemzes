# Körfuvar-elemzés · Bábolna Sped

Streamlit alkalmazás a „Bábolna Körfuvar Generálás” havi xlsx kimeneteinek elemzéséhez (A2 design).

## Futtatás

```
pip install -r requirements.txt
streamlit run app.py
```

A repó publikus, ezért **üzleti adat nincs benne**. Az appban a „Forrásfájlok és beállítások” résznél
töltsd fel a havi körfuvar-fájlokat (`korfuvarok_ÉÉÉÉ_HH.xlsx`) és a havi létszámfájlt (`flotta_ÉÉÉÉ.csv`,
formátum: `config/flotta_minta.csv`). Helyi futtatásnál a fájlok a `data/`, illetve a `config/` mappába is
tehetők; ezeket a `.gitignore` kizárja a repóból.

## Mit számol

- **Fedezet** = bevétel − futással arányos költség; **Eredmény** = bevétel − teljes költség. Minden EUR/km-ben is.
- **Viszonylat** = régiópár: kifelé lerakó régió → befelé felrakó régió (ország + irányítószám első 2 jegye).
- **Besorolás** (legalább N kör): Mindig negatív / Többnyire negatív (≥2/3) / Vegyes / Többnyire pozitív (≤1/3) / Mindig pozitív,
  a negatív körök aránya szerint. Alap választható: Eredmény, Fedezet vagy szcenárió.
- **Teljes sofőrállomány szcenárió**: a fix költség a forrásban jármű-havonta km-arányosan oszlik, ezért
  fix × (tény sofőr / cél sofőr). Cél alapból = nemzetközi autók száma (70).
- Kizárva: hiányos költségadat, időszak határán csonkolt, futásadat nélküli körök.

## Beállítások

- `config/koltseg_besorolas.csv`: melyik költségoszlop fix és melyik futással arányos (csoportokkal).
- `flotta_ÉÉÉÉ.csv` (nincs a repóban): havi autó- és sofőrlétszám az „Éves fajlagos fuvarozási mutatók” táblázatból.
