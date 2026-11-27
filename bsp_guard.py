"""Közös Google-belépés és jogosultság-ellenőrzés a Bábolna Sped Streamlit appokhoz.

Ugyanez a fájl kerül a portálba és minden app repójába. Használat egy appban,
közvetlenül a ``st.set_page_config`` / arculat után:

    from bsp_guard import require_access
    user = require_access('korfuvar')   # a kulcs az "appok" fül "kulcs" oszlopából

Ha a látogató nincs belépve, vagy nincs joga az apphoz, a függvény a belépő /
elutasító képernyőt mutatja, és megállítja az app futását (``st.stop``).
Ha a jogosultságtábla nem olvasható, az app NEM nyílik meg (zárt alapállapot).

Szükséges Secrets (Streamlit Cloud → Settings → Secrets), minta: .streamlit/secrets.toml.example
  [auth]                      Google OAuth (redirect_uri appokként más!)
  [portal]                    sheet_id, admin_emails, portal_url
  [gcp_service_account]       a táblázat olvasásához (a régi google_service_account név is jó)
"""
from __future__ import annotations

import html
from urllib.parse import urlparse

import streamlit as st

APPS_SHEET = 'appok'
PERMS_SHEET = 'jogosultsag'
APP_COLUMNS = ['kulcs', 'nev', 'leiras', 'url', 'sorrend', 'aktiv']
PERM_COLUMNS = ['email', 'app']
SERVICE_ACCOUNT_KEYS = ('gcp_service_account', 'google_service_account')
CACHE_SECONDS = 120  # ennyi idő alatt ér el minden apphoz egy jogosultság-módosítás

NAVY, YELLOW, MUTED, BORDER = '#2A3756', '#F2E47D', '#5B6475', '#E3E6EC'


class GuardError(RuntimeError):
    """Beállítási hiba, amit a felhasználónak érthetően kell megmutatni."""


def norm(value) -> str:
    return str(value or '').strip().lower()


def is_active(value) -> bool:
    return norm(value) not in {'nem', 'false', '0', 'no', 'n'}


def portal_settings() -> dict:
    try:
        return dict(st.secrets.get('portal', {}))
    except FileNotFoundError:
        return {}


def admin_emails() -> set[str]:
    return {norm(e) for e in portal_settings().get('admin_emails', []) if norm(e)}


def service_account_info() -> dict:
    for key in SERVICE_ACCOUNT_KEYS:
        if key in st.secrets:
            return dict(st.secrets[key])
    raise GuardError('A Secretsből hiányzik a [gcp_service_account] szakasz.')


@st.cache_resource(show_spinner=False)
def spreadsheet():
    import gspread

    sheet_id = portal_settings().get('sheet_id', '').strip()
    if not sheet_id:
        raise GuardError('A Secrets [portal] szakaszából hiányzik a sheet_id.')
    info = service_account_info()
    try:
        return gspread.service_account_from_dict(info).open_by_key(sheet_id)
    except (gspread.SpreadsheetNotFound, PermissionError) as exc:
        raise GuardError('A jogosultságtáblázat nem nyitható meg. Oszd meg szerkesztőként ezzel a címmel: '
                         f'{info.get("client_email", "(szolgáltatásfiók)")}') from exc
    except gspread.exceptions.APIError as exc:
        raise GuardError(f'Google Sheets hiba: {exc}') from exc


def read_table(name: str, columns: list[str]) -> list[dict]:
    import gspread

    try:
        rows = spreadsheet().worksheet(name).get_all_values()
    except gspread.WorksheetNotFound:
        return []
    if not rows:
        return []
    header = [norm(h) for h in rows[0]]
    out = []
    for row in rows[1:]:
        if not any(str(c).strip() for c in row):
            continue
        rec = {}
        for col in columns:
            i = header.index(col) if col in header else -1
            rec[col] = str(row[i]).strip() if 0 <= i < len(row) else ''
        out.append(rec)
    return out


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def load_permissions() -> tuple[list[dict], list[dict]]:
    apps = read_table(APPS_SHEET, APP_COLUMNS)
    for a in apps:
        a['kulcs'] = norm(a['kulcs'])
    perms = [{'email': norm(p['email']), 'app': norm(p['app'])} for p in read_table(PERMS_SHEET, PERM_COLUMNS)]
    return [a for a in apps if a['kulcs']], [p for p in perms if p['email'] and p['app']]


def allowed_app_keys(email: str) -> set[str]:
    email = norm(email)
    apps, perms = load_permissions()
    active = {a['kulcs'] for a in apps if is_active(a['aktiv'])}
    if email in admin_emails():
        return active
    return {p['app'] for p in perms if p['email'] == email} & active


AUTH_KEYS = ('redirect_uri', 'cookie_secret', 'client_id', 'client_secret', 'server_metadata_url')


def auth_problem() -> str | None:
    """Érthető magyar hibaüzenet, ha a Google-belépés nincs jól beállítva a Secretsben; különben None."""
    try:
        auth = st.secrets.get('auth')
    except FileNotFoundError:
        return ('A Secrets mező üres vagy nincs elmentve. Settings → Secrets: másold be a mintát, '
                'mentsd, majd indítsd újra az appot (Reboot).')
    except Exception as exc:  # pl. TOML formai hiba a Secrets mezőben
        return f'A Secrets mező nem olvasható (formai hiba?): {exc}'
    if not auth:
        return ('A Secretsből hiányzik az [auth] szakasz, vagy a Secrets nincs elmentve. '
                'Settings → Secrets: másold be az [auth] blokkot, mentsd, majd indítsd újra az appot (Reboot).')
    missing = [k for k in AUTH_KEYS if not str(auth.get(k, '')).strip()]
    if missing:
        return 'Az [auth] szakaszból hiányzik: ' + ', '.join(missing) + '.'
    redirect = str(auth['redirect_uri']).strip().rstrip('/')
    if not redirect.endswith('/oauth2callback'):
        return 'Az [auth] redirect_uri értéke az app címe + /oauth2callback legyen.'
    try:
        here = urlparse(str(getattr(st.context, 'url', '') or ''))
    except Exception:
        here = None
    if here and here.scheme == 'https' and urlparse(redirect).netloc != here.netloc:
        return (f'A redirect_uri ({redirect}) nem ennek az appnak a címe. '
                f'Helyesen: https://{here.netloc}/oauth2callback – és ugyanezt vedd fel a Google OAuth kliensben is.')
    return None


def is_logged_in() -> bool:
    try:
        return bool(st.user.get('is_logged_in', False))
    except Exception:
        return False


def current_email() -> str:
    return norm(st.user.get('email')) if is_logged_in() else ''


def setup_error_screen(problem: str):
    with _centered():
        _card('Beállítási hiba', html.escape(problem), 'deny')


def order_key(app: dict):
    s = str(app.get('sorrend', '')).strip()
    return (int(s) if s.lstrip('-').isdigit() else 999, str(app.get('nev', '')).lower())


MENU_CSS = f'''<style>
details.bsp-apps{{position:relative;display:inline-block}}
details.bsp-apps>summary{{list-style:none;cursor:pointer;background:rgba(255,255,255,.08);padding:9px 14px;
  border-radius:10px;color:#fff;font-size:14px;user-select:none}}
details.bsp-apps>summary::-webkit-details-marker{{display:none}}
details.bsp-apps>summary:hover,details.bsp-apps[open]>summary{{background:rgba(255,255,255,.18)}}
details.bsp-apps .bsp-menu{{position:absolute;left:0;top:calc(100% + 8px);z-index:1000;min-width:280px;background:#fff;
  border:1px solid {BORDER};border-radius:12px;box-shadow:0 12px 32px rgba(42,55,86,.18);padding:6px}}
details.bsp-apps .bsp-menu a{{display:block;padding:9px 12px;border-radius:8px;color:{NAVY}!important;
  text-decoration:none!important;font-size:14px}}
details.bsp-apps .bsp-menu a:hover{{background:#F4F5F8}}
details.bsp-apps .bsp-menu a.cur{{background:{YELLOW};font-weight:600}}
details.bsp-apps .bsp-menu .home{{font-weight:600}}
details.bsp-apps .bsp-menu hr{{margin:6px 4px;border:0;border-top:1px solid {BORDER}}}
details.bsp-apps .bsp-menu .empty{{padding:9px 12px;color:{MUTED};font-size:13px}}
</style>'''


def apps_menu_html(current_key: str | None = None) -> str:
    """A felső sáv „Alkalmazások” eleme: lenyíló menü a portállal és a felhasználó engedélyezett appjaival.

    Az app arculatában a régi ``<span class="apps">Alkalmazások</span>`` helyére kerül.
    """
    current_key = norm(current_key)
    portal = str(portal_settings().get('portal_url', '')).strip()
    apps = []
    email = current_email()
    if email:
        try:
            all_apps, _ = load_permissions()
            allowed = allowed_app_keys(email)
            apps = sorted([a for a in all_apps if a['kulcs'] in allowed], key=order_key)
        except Exception:
            apps = []
    esc = lambda v: html.escape(str(v or ''), quote=True)
    items = ''.join(f'<a href="{esc(a["url"])}" target="_top" class="{"cur" if a["kulcs"] == current_key else ""}">'
                    f'{esc(a["nev"] or a["kulcs"])}</a>' for a in apps)
    if not items and email:
        items = '<div class="empty">Nincs engedélyezett alkalmazás.</div>'
    home = (f'<a class="home{" cur" if current_key == "portal" else ""}" href="{esc(portal)}" target="_top">'
            '⌂ Portál – összes alkalmazás</a><hr>') if portal else ''
    return (MENU_CSS + '<details class="bsp-apps"><summary>Alkalmazások ▾</summary>'
            f'<div class="bsp-menu">{home}{items}</div></details>')


@st.cache_data(show_spinner=False)
def _logo64() -> str:
    """A repó assets/logo_ui.png fájlja base64-ben (ha nincs, üres)."""
    import base64
    from pathlib import Path

    for base in (Path(__file__).parent, Path.cwd()):
        f = base / 'assets' / 'logo_ui.png'
        if f.exists():
            data = f.read_bytes()
            try:  # a logó körüli üres margó levágása, hogy a látható rész szélessége pontosan illeszthető legyen
                import io

                from PIL import Image, ImageOps

                im = Image.open(io.BytesIO(data)).convert('RGBA')
                flat = Image.new('RGBA', im.size, (255, 255, 255, 255))
                flat.alpha_composite(im)
                box = ImageOps.invert(flat.convert('L')).point(lambda v: 255 if v > 12 else 0).getbbox()
                if box:
                    buf = io.BytesIO()
                    im.crop(box).save(buf, format='PNG')
                    data = buf.getvalue()
            except Exception:
                pass
            return base64.b64encode(data).decode()
    return ''


def _card(title: str, text: str, tone: str = 'info'):
    accent = YELLOW if tone == 'info' else '#E9A3A3'
    logo = _logo64()
    # A logó pontosan olyan széles, mint a cím (width:0 + min-width:100% a cím szélességéhez igazít).
    logo_html = (f'<img src="data:image/png;base64,{logo}" alt="Bábolna Sped" '
                 'style="display:block;width:0;min-width:100%;height:auto;margin:0 0 20px">') if logo else ''
    st.markdown(f'''<div style="margin:48px 0 14px;background:#fff;border:1px solid {BORDER};border-radius:16px;
        overflow:hidden;text-align:center;box-shadow:0 6px 24px rgba(42,55,86,.06)">
        <div style="height:6px;background:{accent}"></div>
        <div style="padding:32px 32px 28px">
        <div style="display:inline-flex;flex-direction:column;max-width:100%;margin:0 0 10px">{logo_html}
        <div style="color:{NAVY};font-family:Montserrat,sans-serif;font-weight:700;
             font-size:26px;line-height:1.25">{title}</div></div>
        <div style="margin:0;color:{MUTED};font-size:15px;line-height:1.55">{text}</div></div></div>''',
                unsafe_allow_html=True)


def _centered():
    return st.columns([1, 1.3, 1])[1]


GOOGLE_G = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA0OCA0OCI+PHBhdGggZmlsbD0iI0VBNDMzNSIgZD0iTTI0IDkuNWMzLjU0IDAgNi43MSAxLjIyIDkuMjEgMy42bDYuODUtNi44NUMzNS45IDIuMzggMzAuNDcgMCAyNCAwIDE0LjYyIDAgNi41MSA1LjM4IDIuNTYgMTMuMjJsNy45OCA2LjE5QzEyLjQzIDEzLjcyIDE3Ljc0IDkuNSAyNCA5LjV6Ii8+PHBhdGggZmlsbD0iIzQyODVGNCIgZD0iTTQ2Ljk4IDI0LjU1YzAtMS41Ny0uMTUtMy4wOS0uMzgtNC41NUgyNHY5LjAyaDEyLjk0Yy0uNTggMi45Ni0yLjI2IDUuNDgtNC43OCA3LjE4bDcuNzMgNmM0LjUxLTQuMTggNy4wOS0xMC4zNiA3LjA5LTE3LjY1eiIvPjxwYXRoIGZpbGw9IiNGQkJDMDUiIGQ9Ik0xMC41MyAyOC41OWMtLjQ4LTEuNDUtLjc2LTIuOTktLjc2LTQuNTlzLjI3LTMuMTQuNzYtNC41OWwtNy45OC02LjE5Qy45MiAxNi40NiAwIDIwLjEyIDAgMjRjMCAzLjg4LjkyIDcuNTQgMi41NiAxMC43OGw3Ljk3LTYuMTl6Ii8+PHBhdGggZmlsbD0iIzM0QTg1MyIgZD0iTTI0IDQ4YzYuNDggMCAxMS45My0yLjEzIDE1Ljg5LTUuODFsLTcuNzMtNmMtMi4xNSAxLjQ1LTQuOTIgMi4zLTguMTYgMi4zLTYuMjYgMC0xMS41Ny00LjIyLTEzLjQ3LTkuOTFsLTcuOTggNi4xOUM2LjUxIDQyLjYyIDE0LjYyIDQ4IDI0IDQ4eiIvPjwvc3ZnPg=='

LOGIN_BUTTON_CSS = f'''<style>
.st-key-bsp_login button p{{display:inline-flex;align-items:center;gap:12px;font-weight:600}}
.st-key-bsp_login button p::before{{content:"";width:26px;height:26px;flex:none;border-radius:6px;
  background:#fff url({GOOGLE_G}) center/18px 18px no-repeat}}
</style>'''


def login_screen(title='Belépés szükséges',
                 text='Ez az alkalmazás csak engedélyezett Google-fiókkal használható.'):
    with _centered():
        _card(title, text)
        st.markdown(LOGIN_BUTTON_CSS, unsafe_allow_html=True)
        if st.button('Belépés Google-fiókkal', type='primary', width='stretch', key='bsp_login'):
            st.login()


def logout_button(label='Kilépés', key='bsp_logout', wide=False):
    if st.button(label, key=key, width='stretch' if wide else 'content'):
        st.logout()


def require_access(app_key: str) -> dict:
    """Csak belépett és jogosult felhasználónak engedi tovább az appot."""
    app_key = norm(app_key)
    problem = auth_problem()
    if problem:
        setup_error_screen(problem)
        st.stop()
    if not is_logged_in():
        login_screen()
        st.stop()
    email = current_email()
    if not email or st.user.get('email_verified') is False:
        with _centered():
            _card('Ellenőrizetlen fiók', 'Ezzel a Google-fiókkal nem lehet belépni.', 'deny')
            logout_button(key='bsp_logout_unverified', wide=True)
        st.stop()
    try:
        ok = app_key in allowed_app_keys(email)
    except Exception as exc:  # zárt alapállapot: hiba esetén nincs belépés
        st.error(f'A jogosultság most nem ellenőrizhető, ezért az alkalmazás nem nyílik meg. ({exc})')
        st.stop()
    if not ok:
        portal = portal_settings().get('portal_url', '')
        link = f' <a href="{portal}" target="_top">Vissza a portálra</a>' if portal else ''
        with _centered():
            _card('Nincs hozzáférésed',
                  f'A(z) <b>{html.escape(email)}</b> fiók ehhez az alkalmazáshoz nem kapott jogot. '
                  f'Kérj hozzáférést az adminisztrátortól.{link}', 'deny')
            logout_button('Kilépés / másik fiók', key='bsp_logout_denied', wide=True)
        st.stop()
    return {'email': email, 'name': st.user.get('name') or email, 'admin': email in admin_emails()}
