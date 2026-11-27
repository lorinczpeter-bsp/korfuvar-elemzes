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

## Létszám a Google-táblázatból

Az app automatikusan beolvassa a havi autó- és sofőrlétszámot az „Éves fajlagos fuvarozási mutatók”
Google-táblázat éves munkalapjaiból (pl. `2026`). Ha nem érhető el, figyelmeztet, és tartalékként a feltöltött
CSV-t vagy a Szcenárió fülön kézzel beírt értékeket használja. Beállítás a Streamlit Cloudon,
az app **Settings → Secrets** részében (a repóba soha):

```toml
flotta_sheet_url = "https://docs.google.com/spreadsheets/d/…/edit"
```

Hozzáférés, két lehetőség közül:

1. **Szolgáltatásfiókkal (javasolt, a táblázat privát marad):** ugyanaz a `[gcp_service_account]` blokk,
   amely a jutalék-app Secrets részében van (Drive API elég), és a táblázatot meg kell osztani olvasásra
   a szolgáltatásfiók `client_email` címével.
2. **Link-megosztással:** a táblázat megosztása „Bárki, akinek megvan a link – Megtekintő”. Ilyenkor
   szolgáltatásfiók nem kell, de a link birtokában bárki olvashatja.

## Mit számol

- **Fedezet** = bevétel − futással arányos költség; **Eredmény** = bevétel − teljes költség. Minden EUR/km-ben is.
- **Viszonylat** = alapból az export célállomás (kifelé lerakó telephely: ország + irányítószám + település), bármilyen import jön vissza. Választható: export cél régió, célország, régiópár.
- **Nullszaldós / szükséges díj**: teljes költség / km, illetve ez / (1 − elvárt árbevétel-arányos eredmény %), havonta és viszonylatonként.
- **Legrosszabb körök**: a kör eltérése a viszonylat többi körének átlagától, tételenként (díj, üzemanyag, útdíj, bér, karbantartás, fix), plusz időtartam, km/nap, üres km.
- **Besorolás** (legalább N kör): Mindig negatív / Többnyire negatív (≥2/3) / Vegyes / Többnyire pozitív (≤1/3) / Mindig pozitív,
  a negatív körök aránya szerint. Alap választható: Eredmény, Fedezet vagy szcenárió.
- **Teljes sofőrállomány szcenárió**: a fix költség a forrásban jármű-havonta km-arányosan oszlik, ezért
  fix × (tény sofőr / cél sofőr). Cél alapból = nemzetközi autók száma (70).
- Kizárva: hiányos költségadat, időszak határán csonkolt, futásadat nélküli körök.

## Beállítások

- `config/koltseg_besorolas.csv`: melyik költségoszlop fix és melyik futással arányos (csoportokkal).
- `flotta_ÉÉÉÉ.csv` (nincs a repóban): havi autó- és sofőrlétszám az „Éves fajlagos fuvarozási mutatók” táblázatból.
- **Viszonylatok**: besorolás (nap/kör, km/nap, üres km % is), havi trend viszonylatonként, import-párosítás
  (egy exportcélhoz melyik visszfuvar hozza a legjobb kört).
- **Partnerek**: megrendelőnként az érintett körök eredménye (egy kör több partnernél is szerepelhet).
- **Vállalkozói összevetés**: a mindig/többnyire negatív viszonylatok kiadása; max. alvállalkozói díj = átlagos díj/kör − elvárt többlet (alap 50 €/kör). A felszabaduló autót másik export váltja ki.
