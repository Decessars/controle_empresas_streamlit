# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import threading
import time
from html import escape
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder, GridUpdateMode, JsCode

    AGGRID_AVAILABLE = True
except Exception:
    AgGrid = None
    DataReturnMode = None
    GridOptionsBuilder = None
    GridUpdateMode = None
    JsCode = None
    AGGRID_AVAILABLE = False

# Keep AgGrid enabled here so status can be color-coded per cell.
FORCE_NATIVE_GRID = False


APP_DIR = Path(__file__).resolve().parent
DATA_WEB_DIR = APP_DIR / "data_web"
EMPRESAS_CSV = DATA_WEB_DIR / "empresas_web.csv"
DEMANDAS_CSV = DATA_WEB_DIR / "demandas_web.csv"
USUARIOS_CSV = DATA_WEB_DIR / "usuarios_web.csv"
MARCACOES_CSV = DATA_WEB_DIR / "marcacoes_web.csv"
MARCACOES_SYNC_LOG = DATA_WEB_DIR / "sync_marcacoes.log"
METADATA_JSON = DATA_WEB_DIR / "metadata_web.json"
LOGO_PATH = APP_DIR / "logo.png"
SHEETS_MAX_TITLE_LEN = 100
EMPRESAS_SHEET = "empresas_web"
DEMANDAS_SHEET = "demandas_web"
MARCACOES_SHEET = "marcacoes_web"
CACHE_TTL_SECONDS = 300
SHEETS_SYNC_INTERVAL_SECONDS = 3
MARCACOES_FILE_LOCK = threading.Lock()
MARCACOES_SYNC_LOCK = threading.Lock()
MARCACOES_THREAD_LOCK = threading.Lock()
MARCACOES_SYNC_THREAD: threading.Thread | None = None

EMPRESAS_COLUMNS = [
    "empresa_id", "cnpj", "apelido", "razao_social", "nome_fantasia",
    "regime", "cidade", "uf", "contador_responsavel", "ativo", "atualizado_em",
]
DEMANDAS_COLUMNS = [
    "demanda_id",
    "empresa_id",
    "empresa",
    "cnpj",
    "competencia",
    "tipo_codigo",
    "tipo_demanda",
    "descricao",
    "status",
    "responsavel_operacional",
    "estagiario_responsavel",
    "data_limite",
    "observacao",
    "concluida_em",
    "concluida_por",
    "percentual_grupo",
    "bloqueada",
    "motivo_bloqueio",
    "tempo_min",
    "tempo_max",
    "tempo_medio",
    "estrelas",
    "peso",
    "atualizado_em",
]
MARCACOES_COLUMNS = [
    "marcacao_id",
    "demanda_id",
    "username",
    "acao",
    "status_novo",
    "observacao",
    "justificativa",
    "data_hora",
    "sincronizado",
]

PASSWORD_HASHES = {
    "DMLIMA": {
        "nome": "DMLIMA",
        "perfil": "admin",
        "sha256": "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92",
    },
    "EDIVAN": {
        "nome": "EDIVAN",
        "perfil": "estagiario",
        "sha256": "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92",
    },
    "RAYANA": {
        "nome": "RAYANA",
        "perfil": "estagiario",
        "sha256": "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92",
    },
    "VITOR": {
        "nome": "VITOR",
        "perfil": "estagiario",
        "sha256": "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92",
    }
}


st.set_page_config(page_title="Controle de Empresas", page_icon="logo.png", layout="wide")


def inject_professional_ui_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #eef3f9;
            --panel: rgba(255, 255, 255, 0.86);
            --ink: #0f172a;
            --muted: #64748b;
            --primary: #2f6fed;
            --primary-strong: #1e40af;
            --primary-soft: rgba(47, 111, 237, 0.12);
            --table-bg: #0f172a;
            --table-alt: #111827;
            --table-line: #243044;
            --table-head: #1d4ed8;
            --card-border: rgba(148, 163, 184, 0.24);
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(47, 111, 237, 0.10), transparent 34%),
                radial-gradient(circle at right top, rgba(15, 23, 42, 0.05), transparent 26%),
                var(--bg);
            color: var(--ink);
        }
        div[data-testid="stDecoration"],
        header[data-testid="stHeader"],
        div[data-testid="stToolbar"],
        #MainMenu,
        footer {
            display: none !important;
        }
        .stApp [data-testid="stCustomComponentV1"],
        .stApp [data-testid="stCustomComponentV1"] iframe,
        .stApp [data-testid="stElementContainer"],
        .stApp .element-container,
        .stApp .stale,
        .stApp [class*="stale"] {
            opacity: 1 !important;
            filter: none !important;
        }
        .stApp {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }
        .block-container {
            padding-top: 0.85rem;
            padding-bottom: 1rem;
            max-width: 1360px;
        }
        section.main > div { padding-top: 0; }
        h1, h2, h3 {
            letter-spacing: 0;
            margin-bottom: 0.35rem;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(241, 245, 249, 0.96));
            border-right: 1px solid rgba(148, 163, 184, 0.22);
        }
        [data-testid="stSidebar"] div.stButton > button {
            width: 100%;
        }
        div.stButton > button {
            width: auto;
            min-height: 38px;
            padding: 0.38rem 0.9rem;
            border-radius: 10px;
            font-weight: 700;
            border: 1px solid rgba(148, 163, 184, 0.40);
            background: #ffffff;
            color: var(--ink);
            box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
            transition: transform 120ms ease, box-shadow 120ms ease, border-color 120ms ease, background 120ms ease;
        }
        div.stButton > button:hover {
            transform: translateY(-1px);
            border-color: var(--primary);
            box-shadow: 0 12px 24px rgba(47, 111, 237, 0.14);
        }
        div.stButton > button[kind="primary"] {
            background: linear-gradient(135deg, var(--primary), var(--primary-strong));
            border-color: var(--primary);
            color: #fff;
        }
        .compact-button button,
        .action-bar div.stButton > button {
            min-height: 36px;
            font-size: 0.92rem;
        }
        .app-shell {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            padding: 0.65rem 0.9rem;
            margin: 0 0 12px 0;
            border-radius: 14px;
            background: var(--panel);
            border: 1px solid var(--card-border);
            box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
        }
        .topbar-brand {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .topbar-brand-name {
            font-size: 1.02rem;
            font-weight: 900;
            color: var(--ink);
            line-height: 1.05;
        }
        .topbar-brand-subtitle {
            color: var(--muted);
            font-size: 0.8rem;
            line-height: 1.15;
            margin-top: 2px;
        }
        .main-card,
        .module-card,
        .metric-card,
        .action-bar {
            background: var(--panel);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
        }
        .main-card {
            padding: 1rem 1.1rem;
        }
        .module-card {
            padding: 1rem;
            min-height: 168px;
        }
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
        }
        .dashboard-panel {
            position: relative;
            overflow: hidden;
            min-height: 240px;
            padding: 1.05rem 1.1rem 1rem;
            border-radius: 22px;
            border: 1px solid rgba(148, 163, 184, 0.22);
            background: linear-gradient(145deg, rgba(255, 255, 255, 0.92), rgba(255, 255, 255, 0.76));
            box-shadow: 0 18px 36px rgba(15, 23, 42, 0.06);
        }
        .dashboard-panel::after {
            content: "";
            position: absolute;
            right: -60px;
            bottom: -72px;
            width: 190px;
            height: 190px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(255, 255, 255, 0.75) 0%, rgba(255, 255, 255, 0) 70%);
            pointer-events: none;
        }
        .dashboard-panel--demandas {
            background:
                radial-gradient(circle at top left, rgba(47, 111, 237, 0.20), transparent 28%),
                linear-gradient(145deg, rgba(255, 255, 255, 0.92), rgba(235, 243, 255, 0.92));
        }
        .dashboard-panel--empresas {
            background:
                radial-gradient(circle at top left, rgba(16, 185, 129, 0.18), transparent 28%),
                linear-gradient(145deg, rgba(255, 255, 255, 0.92), rgba(236, 253, 245, 0.92));
        }
        .dashboard-panel__top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 0.55rem;
        }
        .dashboard-panel__icon {
            font-size: 1.55rem;
            line-height: 1;
        }
        .dashboard-panel__kicker {
            display: inline-flex;
            align-items: center;
            padding: 0.32rem 0.6rem;
            border-radius: 999px;
            font-size: 0.74rem;
            font-weight: 800;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: var(--ink);
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid rgba(148, 163, 184, 0.22);
        }
        .dashboard-panel__title {
            font-size: 1.18rem;
            font-weight: 900;
            color: var(--ink);
            margin-bottom: 0.24rem;
        }
        .dashboard-panel__desc {
            color: var(--muted);
            font-size: 0.93rem;
            line-height: 1.35;
            max-width: 42ch;
        }
        .dashboard-panel__stats {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
            margin-top: 0.9rem;
        }
        .dashboard-panel__stat {
            padding: 0.7rem 0.78rem;
            border-radius: 16px;
            background: rgba(255, 255, 255, 0.84);
            border: 1px solid rgba(148, 163, 184, 0.20);
            box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
        }
        .dashboard-panel__stat span {
            display: block;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--muted);
        }
        .dashboard-panel__stat strong {
            display: block;
            margin-top: 0.18rem;
            font-size: 1.25rem;
            font-weight: 900;
            color: var(--ink);
            line-height: 1;
        }
        .dashboard-panel__footer {
            margin-top: 0.95rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
        }
        .dashboard-panel__hint {
            color: var(--muted);
            font-size: 0.84rem;
        }
        .metric-card {
            padding: 0.9rem 1rem;
            min-height: 92px;
        }
        .metric-card .value {
            display: block;
            margin-top: 0.3rem;
            font-size: 1.55rem;
            font-weight: 900;
            letter-spacing: -0.03em;
            line-height: 1;
            color: var(--ink);
        }
        .metric-card .label {
            font-size: 0.79rem;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }
        .metric-card .hint {
            font-size: 0.82rem;
            color: var(--muted);
            margin-top: 0.22rem;
        }
        .module-card .icon {
            font-size: 1.35rem;
            margin-bottom: 0.35rem;
        }
        .module-card .title {
            font-size: 1.02rem;
            font-weight: 900;
            color: var(--ink);
            margin-bottom: 0.25rem;
        }
        .module-card .desc {
            color: var(--muted);
            font-size: 0.88rem;
            line-height: 1.35;
            min-height: 2.6em;
        }
        .section-title {
            font-size: 1rem;
            font-weight: 900;
            color: var(--ink);
            margin-bottom: 0.25rem;
        }
        .muted-text {
            color: var(--muted);
            font-size: 0.88rem;
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.36rem 0.62rem;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.24);
            background: rgba(255, 255, 255, 0.8);
            color: var(--ink);
            font-size: 0.8rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .status-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.28rem 0.7rem;
            border-radius: 999px;
            border: 1px solid transparent;
            font-size: 0.82rem;
            font-weight: 800;
            line-height: 1.1;
            white-space: nowrap;
        }
        .status-pill--pendente {
            background: rgba(251, 191, 36, 0.18);
            color: #92400e;
            border-color: rgba(245, 158, 11, 0.45);
        }
        .status-pill--em-andamento {
            background: rgba(59, 130, 246, 0.16);
            color: #1d4ed8;
            border-color: rgba(96, 165, 250, 0.45);
        }
        .status-pill--concluida {
            background: rgba(34, 197, 94, 0.16);
            color: #166534;
            border-color: rgba(74, 222, 128, 0.45);
        }
        .status-pill--bloqueada {
            background: rgba(248, 113, 113, 0.16);
            color: #b91c1c;
            border-color: rgba(248, 113, 113, 0.45);
        }
        .status-pill--default {
            background: rgba(148, 163, 184, 0.18);
            color: #334155;
            border-color: rgba(148, 163, 184, 0.45);
        }
        .action-bar {
            margin-top: 0.9rem;
            padding: 0.95rem;
        }
        .home-intro {
            display: grid;
            gap: 0.18rem;
        }
        .home-hero {
            display: grid;
            gap: 0.25rem;
            margin-bottom: 0.8rem;
        }
        .home-hero h1 {
            font-size: 1.55rem;
            margin: 0;
            line-height: 1.1;
        }
        .home-hero p {
            margin: 0;
            color: var(--muted);
        }
        .compact-grid {
            gap: 10px;
        }
        .dmls-table {
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
            background: var(--table-bg);
            color: #f8fafc;
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 12px;
            overflow: hidden;
            font-size: 0.79rem;
            line-height: 1.25;
        }
        .dmls-table th,
        .dmls-table td {
            border-bottom: 1px solid var(--table-line);
            padding: 0.42rem 0.55rem;
            vertical-align: top;
            white-space: normal;
            overflow-wrap: anywhere;
        }
        .dmls-table th {
            background: var(--table-head);
            color: #fff;
            font-weight: 900;
        }
        .dmls-table tbody tr:nth-child(even) { background: var(--table-alt); }
        .dmls-table tbody tr:hover { background: #1f2937; }
        .metric-row {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            margin: 0.6rem 0 1rem;
        }
        @media (max-width: 900px) {
            .metric-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .topbar { flex-direction: column; align-items: stretch; }
            .topbar-brand { justify-content: center; }
            .dmls-table { font-size: 0.70rem; }
            .dmls-table th, .dmls-table td { padding: 0.34rem; }
            .module-card { min-height: 0; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_user(value: str) -> str:
    text = str(value or "").strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.upper()


def extract_responsavel_from_observacao(value: str) -> str:
    text = str(value or "")
    marker = "[Responsável:"
    if marker not in text:
        marker = "[Responsavel:"
    if marker not in text:
        return ""
    start = text.find(marker) + len(marker)
    end = text.find("]", start)
    if end == -1:
        return ""
    return normalize_user(text[start:end])


def check_login(username: str, password: str) -> bool:
    user = PASSWORD_HASHES.get(normalize_user(username))
    if not user:
        return False
    return hmac.compare_digest(sha256_text(password), user["sha256"])


def current_user() -> str:
    return normalize_user(st.session_state.get("usuario", ""))


def current_profile() -> str:
    user = PASSWORD_HASHES.get(current_user(), {})
    return str(user.get("perfil") or "estagiario")


def current_profile_label() -> str:
    return {
        "admin": "Administrador Geral",
        "contador": "Contador",
        "estagiario": "Estagiário",
    }.get(current_profile(), "Usuário")


def is_admin() -> bool:
    return current_profile() in {"admin", "contador"}


ALLOWED_PAGES = {"Home", "Empresas", "Demandas"}
PAGE_ALIASES = {
    "HOME": "Home",
    "EMPRESAS": "Empresas",
    "DEMANDAS": "Demandas",
    "HOME ": "Home",
    "EMPRESAS ": "Empresas",
    "DEMANDAS ": "Demandas",
    "AUTOMACAO": "Home",
    "BACKUP": "Home",
    "FATURAMENTO": "Home",
    "PAINEL": "Home",
    "RELATORIOS": "Home",
    "USUARIOS": "Home",
    "MODULOS": "Home",
}


def normalize_page(page: str) -> str:
    value = str(page or "").strip()
    if not value:
        return "Home"
    if value in ALLOWED_PAGES:
        return value
    normalized = normalize_user(value)
    return PAGE_ALIASES.get(normalized, "Home")


def navigate_to(page: str, label: str | None = None, push_history: bool = True) -> None:
    target = normalize_page(page)
    current = normalize_page(st.session_state.get("page", "Home"))
    if push_history and current != target:
        history = st.session_state.setdefault("nav_history", [])
        if not history or history[-1] != current:
            history.append(current)
        st.session_state["nav_history"] = history[-20:]
    st.session_state["page"] = target
    st.session_state["page_label"] = label or target
    st.query_params["page"] = target
    st.rerun()


def go_back() -> None:
    history = st.session_state.get("nav_history", [])
    if history:
        previous = normalize_page(history.pop())
        st.session_state["nav_history"] = history
        navigate_to(previous, previous, push_history=False)
    else:
        navigate_to("Home", "Home", push_history=False)


def resolve_start_page() -> str:
    query_page = st.query_params.get("page", "")
    if isinstance(query_page, list):
        query_page = query_page[0] if query_page else ""
    page = normalize_page(query_page or st.session_state.get("page", "Home"))
    st.session_state["page"] = page
    st.session_state["page_label"] = {
        "Home": "Home",
        "Empresas": "Empresas",
        "Demandas": "📋 Demandas",
    }.get(page, page)
    if str(query_page or "") != page:
        st.query_params["page"] = page
    return page


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    empresas = load_empresas_web()
    demandas = load_demandas_web()
    usuarios = pd.read_csv(USUARIOS_CSV, dtype=str).fillna("") if USUARIOS_CSV.exists() else pd.DataFrame()
    metadata = load_metadata_web()
    return empresas, demandas, usuarios, metadata


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_metadata_web() -> dict:
    metadata = {}
    if METADATA_JSON.exists():
        try:
            metadata = json.loads(METADATA_JSON.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}
    return metadata


def usar_google_sheets() -> bool:
    try:
        configuracao = st.secrets.get("google_sheets", {})
        credenciais = st.secrets.get("google_service_account", {})
    except Exception:
        return False
    return bool(str(configuracao.get("spreadsheet_id", "")).strip() and credenciais)


def obter_config_google_sheets() -> dict[str, object]:
    try:
        configuracao = dict(st.secrets.get("google_sheets", {}))
        credenciais = dict(st.secrets.get("google_service_account", {}))
    except Exception as erro:
        raise RuntimeError("Configuracao do Google Sheets indisponivel em st.secrets.") from erro

    spreadsheet_id = str(configuracao.get("spreadsheet_id", "")).strip()
    if not spreadsheet_id:
        raise RuntimeError("Defina google_sheets.spreadsheet_id em st.secrets.")
    if not credenciais:
        raise RuntimeError("Defina google_service_account em st.secrets.")

    return {
        "spreadsheet_id": spreadsheet_id,
        "service_account": credenciais,
        "sheet_prefix": str(configuracao.get("sheet_prefix", "")).strip(),
    }


def nome_aba_google(nome: str) -> str:
    if not usar_google_sheets():
        return nome[:SHEETS_MAX_TITLE_LEN]
    prefixo = str(obter_config_google_sheets().get("sheet_prefix", "")).strip()
    return f"{prefixo}{nome}"[:SHEETS_MAX_TITLE_LEN]


@st.cache_resource(show_spinner=False)
def cliente_google_sheets() -> object:
    if not usar_google_sheets():
        raise RuntimeError("Google Sheets nao configurado.")

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as erro:
        raise RuntimeError("Instale gspread e google-auth para usar Google Sheets.") from erro

    configuracao = obter_config_google_sheets()
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credenciais = Credentials.from_service_account_info(configuracao["service_account"], scopes=scopes)
    return gspread.authorize(credenciais)


@st.cache_resource(show_spinner=False)
def planilha_google() -> object:
    cliente = cliente_google_sheets()
    configuracao = obter_config_google_sheets()
    return cliente.open_by_key(str(configuracao["spreadsheet_id"]))


def obter_worksheet_google(nome: str, columns: list[str], criar: bool = True):
    planilha = planilha_google()
    titulo = nome_aba_google(nome)
    try:
        aba = planilha.worksheet(titulo)
    except Exception:
        if not criar:
            return None
        aba = planilha.add_worksheet(title=titulo, rows=200, cols=max(2, len(columns)))
        aba.update([columns], value_input_option="RAW")
        return aba

    valores = aba.get_all_values()
    if criar and not valores:
        aba.update([columns], value_input_option="RAW")
    return aba


def dataframe_para_linhas_google(df: pd.DataFrame, columns: list[str]) -> list[list[object]]:
    frame = df.copy().fillna("")
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[columns].copy()

    linhas: list[list[object]] = [columns]
    for _, row in frame.iterrows():
        valores = []
        for column in columns:
            value = row.get(column, "")
            if pd.isna(value):
                value = ""
            elif isinstance(value, (pd.Timestamp, datetime)):
                value = value.strftime("%Y-%m-%d %H:%M:%S")
            valores.append(value)
        linhas.append(valores)
    return linhas


def linhas_google_para_dataframe(linhas: list[list[object]], columns: list[str]) -> pd.DataFrame:
    if not linhas:
        return pd.DataFrame(columns=columns)

    cabecalho = [str(value).strip() for value in linhas[0]]
    registros: list[dict[str, object]] = []
    for linha in linhas[1:]:
        if not any(str(value).strip() for value in linha):
            continue
        registro = {}
        for index, column in enumerate(cabecalho):
            if column:
                registro[column] = linha[index] if index < len(linha) else ""
        registros.append(registro)
    return pd.DataFrame(registros, columns=cabecalho or columns).fillna("")


def ler_dataframe_google(nome: str, columns: list[str], csv_fallback: Path | None = None) -> pd.DataFrame:
    if not usar_google_sheets():
        raise RuntimeError("Google Sheets nao configurado.")

    aba = obter_worksheet_google(nome, columns, criar=True)
    valores = aba.get_all_values()
    if len(valores) <= 1 and csv_fallback is not None and csv_fallback.exists():
        local_df = pd.read_csv(csv_fallback, dtype=str).fillna("")
        salvar_dataframe_google(nome, local_df, columns)
        return local_df
    return linhas_google_para_dataframe(valores, columns)


def salvar_dataframe_google(nome: str, df: pd.DataFrame, columns: list[str]) -> None:
    aba = obter_worksheet_google(nome, columns, criar=True)
    aba.clear()
    aba.update(dataframe_para_linhas_google(df, columns), value_input_option="RAW")


def append_linha_google(nome: str, row: dict[str, object], columns: list[str]) -> None:
    aba = obter_worksheet_google(nome, columns, criar=True)
    valores = []
    for column in columns:
        value = row.get(column, "")
        if pd.isna(value):
            value = ""
        valores.append(value)
    aba.append_row(valores, value_input_option="RAW")


def _normalize_marcacoes_df(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy().fillna("")
    for column in MARCACOES_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[MARCACOES_COLUMNS].copy()


def _read_marcacoes_local() -> pd.DataFrame:
    if not MARCACOES_CSV.exists():
        return pd.DataFrame(columns=MARCACOES_COLUMNS)
    try:
        return _normalize_marcacoes_df(pd.read_csv(MARCACOES_CSV, dtype=str).fillna(""))
    except Exception:
        return pd.DataFrame(columns=MARCACOES_COLUMNS)


def _write_marcacoes_local(df: pd.DataFrame) -> None:
    MARCACOES_CSV.parent.mkdir(parents=True, exist_ok=True)
    _normalize_marcacoes_df(df).to_csv(MARCACOES_CSV, index=False, encoding="utf-8-sig")


def _append_marcacao_local(row: dict[str, object]) -> None:
    MARCACOES_CSV.parent.mkdir(parents=True, exist_ok=True)
    exists = MARCACOES_CSV.exists()
    with MARCACOES_FILE_LOCK:
        with MARCACOES_CSV.open("a", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=MARCACOES_COLUMNS)
            if not exists:
                writer.writeheader()
            writer.writerow({column: row.get(column, "") for column in MARCACOES_COLUMNS})


def _cliente_google_sheets_from_config(configuracao: dict[str, object]) -> object:
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credenciais = Credentials.from_service_account_info(configuracao["service_account"], scopes=scopes)
    return gspread.authorize(credenciais)


def _worksheet_google_from_config(configuracao: dict[str, object], nome: str, columns: list[str]):
    cliente = _cliente_google_sheets_from_config(configuracao)
    planilha = cliente.open_by_key(str(configuracao["spreadsheet_id"]))
    titulo = f"{str(configuracao.get('sheet_prefix', '')).strip()}{nome}"[:SHEETS_MAX_TITLE_LEN]
    try:
        aba = planilha.worksheet(titulo)
    except Exception:
        aba = planilha.add_worksheet(title=titulo, rows=200, cols=max(2, len(columns)))
        aba.update([columns], value_input_option="RAW")
    if not aba.get_all_values():
        aba.update([columns], value_input_option="RAW")
    return aba


def sync_marcacoes_google_once(configuracao: dict[str, object] | None = None) -> int:
    if not MARCACOES_SYNC_LOCK.acquire(blocking=False):
        return 0
    try:
        if configuracao is None:
            if not usar_google_sheets():
                return 0
            configuracao = obter_config_google_sheets()

        with MARCACOES_FILE_LOCK:
            local_df = _read_marcacoes_local()
            if local_df.empty:
                return 0
            pending_mask = local_df["sincronizado"].astype(str).str.strip().ne("1")
            pending_df = local_df.loc[pending_mask].copy()

        if pending_df.empty:
            return 0

        rows_to_append: list[list[object]] = []
        for _, row in pending_df.iterrows():
            values = []
            for column in MARCACOES_COLUMNS:
                value = row.get(column, "")
                if column == "sincronizado":
                    value = "1"
                values.append("" if pd.isna(value) else value)
            rows_to_append.append(values)

        aba = _worksheet_google_from_config(configuracao, MARCACOES_SHEET, MARCACOES_COLUMNS)
        aba.append_rows(rows_to_append, value_input_option="RAW")

        synced_ids = set(pending_df["marcacao_id"].astype(str))
        with MARCACOES_FILE_LOCK:
            refreshed = _read_marcacoes_local()
            mask = refreshed["marcacao_id"].astype(str).isin(synced_ids)
            refreshed.loc[mask, "sincronizado"] = "1"
            _write_marcacoes_local(refreshed)
        return len(rows_to_append)
    finally:
        MARCACOES_SYNC_LOCK.release()


def _log_marcacoes_sync_error(erro: Exception) -> None:
    try:
        DATA_WEB_DIR.mkdir(parents=True, exist_ok=True)
        with MARCACOES_SYNC_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {type(erro).__name__}: {erro}\n")
    except Exception:
        pass


def _marcacoes_sync_worker(configuracao: dict[str, object]) -> None:
    while True:
        try:
            sync_marcacoes_google_once(configuracao)
        except Exception as erro:
            _log_marcacoes_sync_error(erro)
        time.sleep(SHEETS_SYNC_INTERVAL_SECONDS)


def start_marcacoes_background_sync() -> bool:
    global MARCACOES_SYNC_THREAD
    if not usar_google_sheets():
        return False
    try:
        configuracao = obter_config_google_sheets()
    except Exception:
        return False
    with MARCACOES_THREAD_LOCK:
        if MARCACOES_SYNC_THREAD is not None and MARCACOES_SYNC_THREAD.is_alive():
            return True
        MARCACOES_SYNC_THREAD = threading.Thread(
            target=_marcacoes_sync_worker,
            args=(configuracao,),
            daemon=True,
            name="marcacoes_google_sync",
        )
        MARCACOES_SYNC_THREAD.start()
    return True


def fonte_persistencia_label() -> str:
    return "data_web + Google Sheets" if usar_google_sheets() else "data_web"


def _normalize_empresa_text(value: object) -> str:
    text = str(value or "").strip()
    return text


def _normalize_ativo(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"1", "1.0", "true", "sim", "ativo", "yes", "y"}:
        return "1"
    if text in {"0", "0.0", "false", "nao", "não", "inativo", "no", "n"}:
        return "0"
    return "1" if text == "" else text


def normalize_empresas_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=EMPRESAS_COLUMNS)

    frame = df.copy().fillna("")
    aliases = {
        "id": "empresa_id",
        "empresa id": "empresa_id",
        "cnpj": "cnpj",
        "documento": "cnpj",
        "apelido": "apelido",
        "cliente": "apelido",
        "razao social": "razao_social",
        "razao": "razao_social",
        "nome fantasia": "nome_fantasia",
        "fantasia": "nome_fantasia",
        "regime": "regime",
        "cidade": "cidade",
        "uf": "uf",
        "estado": "uf",
        "contador responsavel": "contador_responsavel",
        "contador": "contador_responsavel",
        "responsavel": "contador_responsavel",
        "ativo": "ativo",
        "status": "ativo",
        "atualizado em": "atualizado_em",
    }

    normalized_columns: dict[str, str] = {}
    for column in frame.columns:
        key = normalize_user(column).lower().replace("_", " ").strip()
        normalized_columns[column] = aliases.get(key, column)

    frame = frame.rename(columns=normalized_columns)
    for column in EMPRESAS_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""

    frame["empresa_id"] = frame["empresa_id"].map(_normalize_empresa_text)
    frame["cnpj"] = frame["cnpj"].map(_normalize_empresa_text)
    frame["apelido"] = frame["apelido"].map(_normalize_empresa_text)
    frame["razao_social"] = frame["razao_social"].map(_normalize_empresa_text)
    frame["nome_fantasia"] = frame["nome_fantasia"].map(_normalize_empresa_text)
    frame["regime"] = frame["regime"].map(_normalize_empresa_text)
    frame["cidade"] = frame["cidade"].map(_normalize_empresa_text)
    frame["uf"] = frame["uf"].map(_normalize_empresa_text).str.upper()
    frame["contador_responsavel"] = frame["contador_responsavel"].map(_normalize_empresa_text)
    frame["ativo"] = frame["ativo"].map(_normalize_ativo)
    frame["atualizado_em"] = frame["atualizado_em"].map(_normalize_empresa_text)

    return frame[EMPRESAS_COLUMNS].copy()


def load_empresas_web() -> pd.DataFrame:
    if not EMPRESAS_CSV.exists():
        if usar_google_sheets():
            try:
                return normalize_empresas_df(ler_dataframe_google(EMPRESAS_SHEET, EMPRESAS_COLUMNS, EMPRESAS_CSV))
            except Exception:
                pass
        return normalize_empresas_df(pd.DataFrame())
    try:
        df = pd.read_csv(EMPRESAS_CSV, dtype=str).fillna("")
    except Exception:
        return normalize_empresas_df(pd.DataFrame())
    return normalize_empresas_df(df)


def save_empresas_web(df: pd.DataFrame) -> None:
    normalized = normalize_empresas_df(df)
    EMPRESAS_CSV.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(EMPRESAS_CSV, index=False, encoding="utf-8-sig")
    if usar_google_sheets():
        try:
            salvar_dataframe_google(EMPRESAS_SHEET, normalized, EMPRESAS_COLUMNS)
        except Exception:
            pass
    load_data.clear()
    load_empresas_web.clear()


def _normalize_demanda_value(value: object) -> str:
    return str(value or "").strip()


def _normalize_demanda_flag(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"1", "1.0", "true", "sim", "s", "yes", "y"}:
        return "1"
    if text in {"0", "0.0", "false", "nao", "não", "n", "no"}:
        return "0"
    return "1" if text == "" else text


def _parse_competencia_ym(value: object) -> tuple[int, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        ano_txt, mes_txt = text.split("-", 1)
        ano = int(ano_txt)
        mes = int(mes_txt)
    except Exception:
        return None
    if ano < 2000 or ano > 2100 or mes < 1 or mes > 12:
        return None
    return ano, mes


def _nth_business_day(year: int, month: int, target: int) -> datetime | None:
    if target <= 0:
        return None
    cursor = datetime(year, month, 1)
    counted = 0
    while cursor.month == month:
        if cursor.weekday() < 5:
            counted += 1
            if counted == target:
                return cursor
        cursor += timedelta(days=1)
    return None


def _next_business_day(value: datetime) -> datetime:
    cursor = value
    while cursor.weekday() >= 5:
        cursor += timedelta(days=1)
    return cursor


def _format_date_display(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    raw = text[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except Exception:
            continue
    return text


def _demand_deadline(tipo_codigo: object, competencia: object) -> str:
    comp = _parse_competencia_ym(competencia)
    if not comp:
        return ""
    ano, mes = comp
    tipo = str(tipo_codigo or "").strip().upper()

    def business_day(n: int) -> str:
        value = _nth_business_day(ano, mes, n)
        return value.strftime("%Y-%m-%d") if value else ""

    def calendar_day(day: int) -> str:
        try:
            value = datetime(ano, mes, day)
        except Exception:
            return ""
        return value.strftime("%Y-%m-%d")

    if tipo in {"EXEC_FOLHA", "ENV_CONTRACHEQUES"}:
        return business_day(1)
    if tipo == "GUIA_INSS":
        return business_day(2)
    if tipo in {"GUIA_FGTS", "GUIA_FGTS_PARC"}:
        return business_day(3)
    if tipo == "PEDIR_INFOS":
        return business_day(4)
    if tipo == "APUR_ISS":
        return calendar_day(5)
    if tipo == "APUR_SIMPLES":
        return business_day(5)
    if tipo == "GUIA_MEI":
        return business_day(6)
    if tipo == "ENV_PARC_SIMPLES":
        return calendar_day(10)
    if tipo == "GUIA_PREF":
        return business_day(7)
    if tipo == "REL_DEBITOS":
        try:
            value = datetime(ano, mes, 11)
        except Exception:
            return ""
        if value.weekday() < 5:
            return value.strftime("%Y-%m-%d")
        return _next_business_day(value).strftime("%Y-%m-%d")
    if tipo == "CONS_ICMS_ST":
        return business_day(4)
    if tipo == "PUXAR_NF_SAIDA":
        return business_day(5)
    if tipo == "COBRAR_HONORARIOS":
        return calendar_day(25)
    if tipo in {"PARC_MENSAL", "PARC_IMPOSTOS"}:
        return business_day(7)
    return ""


def normalize_demandas_web(df: pd.DataFrame, empresas: pd.DataFrame | None = None) -> pd.DataFrame:
    columns = DEMANDAS_COLUMNS
    if df.empty:
        return pd.DataFrame(columns=columns)

    frame = df.copy().fillna("")
    aliases = {
        "demanda id": "demanda_id",
        "empresa id": "empresa_id",
        "tipo codigo": "tipo_codigo",
        "tipo demanda": "tipo_demanda",
        "data limite": "data_limite",
        "concluida em": "concluida_em",
        "concluida por": "concluida_por",
        "percentual grupo": "percentual_grupo",
        "motivo bloqueio": "motivo_bloqueio",
        "tempo min": "tempo_min",
        "tempo max": "tempo_max",
        "tempo medio": "tempo_medio",
        "atualizado em": "atualizado_em",
    }
    renamed: dict[str, str] = {}
    for column in frame.columns:
        key = normalize_user(column).lower().replace("_", " ").strip()
        renamed[column] = aliases.get(key, column)
    frame = frame.rename(columns=renamed)

    for column in columns:
        if column not in frame.columns:
            frame[column] = ""

    if empresas is not None and not empresas.empty:
        emp = normalize_empresas_df(empresas)
        if "empresa" not in frame.columns or frame["empresa"].astype(str).str.strip().eq("").all():
            if "empresa_id" in frame.columns and "empresa_id" in emp.columns:
                keep_cols = [c for c in ["empresa_id", "apelido", "razao_social", "cnpj"] if c in emp.columns]
                merged = frame.merge(emp[keep_cols].drop_duplicates("empresa_id"), on="empresa_id", how="left", suffixes=("", "_emp"))
                if "apelido" in merged.columns:
                    merged["empresa"] = merged["empresa"].where(merged["empresa"].astype(str).str.strip().ne(""), merged["apelido"].fillna(""))
                if "razao_social" in merged.columns:
                    merged["empresa"] = merged["empresa"].where(merged["empresa"].astype(str).str.strip().ne(""), merged["razao_social"].fillna(""))
                if "cnpj_emp" in merged.columns:
                    merged["cnpj"] = merged["cnpj"].where(merged["cnpj"].astype(str).str.strip().ne(""), merged["cnpj_emp"].fillna(""))
                frame = merged

    for column in columns:
        frame[column] = frame[column].map(_normalize_demanda_value)
    frame["status"] = frame["status"].replace("", "pendente").str.lower()
    frame["bloqueada"] = frame["bloqueada"].map(_normalize_demanda_flag)
    frame["empresa"] = frame["empresa"].where(frame["empresa"].astype(str).str.strip().ne(""), frame["descricao"].fillna(""))
    frame["descricao"] = frame["descricao"].where(frame["descricao"].astype(str).str.strip().ne(""), frame["tipo_demanda"].fillna(""))
    frame["tipo_demanda"] = frame["tipo_demanda"].where(frame["tipo_demanda"].astype(str).str.strip().ne(""), frame["descricao"].fillna(""))

    for column in ["concluida_em", "concluida_por", "data_limite", "atualizado_em", "tempo_min", "tempo_max", "tempo_medio", "estrelas", "peso", "percentual_grupo"]:
        if column in frame.columns:
            frame[column] = frame[column].map(_normalize_demanda_value)

    estrelas_numeric = pd.to_numeric(frame["estrelas"], errors="coerce")
    percentual_numeric = pd.to_numeric(frame["percentual_grupo"], errors="coerce")
    if estrelas_numeric.notna().any():
        stars = estrelas_numeric.fillna(0).round().astype(int).clip(0, 5)
    else:
        stars = (percentual_numeric.fillna(0) / 20).round().astype(int).clip(0, 5)
    frame["estrelas"] = stars.astype(str)
    frame["estrelas_visual"] = frame["estrelas"].map(lambda value: "?" * int(value) if str(value).isdigit() and int(value) > 0 else "—")

    def _tempo_display(row: pd.Series) -> str:
        tempo_medio = str(row.get("tempo_medio", "")).strip()
        tempo_min = str(row.get("tempo_min", "")).strip()
        tempo_max = str(row.get("tempo_max", "")).strip()
        if tempo_medio:
            return f"{tempo_medio} min"
        if tempo_min and tempo_max and tempo_min != tempo_max:
            return f"{tempo_min}–{tempo_max} min"
        if tempo_min:
            return f"{tempo_min} min"
        if tempo_max:
            return f"{tempo_max} min"
        return "—"

    frame["tempo_display"] = frame.apply(_tempo_display, axis=1)
    frame["responsavel_display"] = frame["responsavel_operacional"].where(
        frame["responsavel_operacional"].astype(str).str.strip().ne(""),
        frame["estagiario_responsavel"],
    )
    frame["status"] = frame["status"].replace({"concluido": "concluida", "finalizado": "concluida"})
    frame["status"] = frame["status"].replace("", "pendente")
    frame["status_visual"] = frame["status"].map(
        {
            "pendente": "⚪ Pendente",
            "em_andamento": "▶️ Em andamento",
            "concluida": "✅ Concluída",
            "bloqueada": "🔒 Bloqueada",
        }
    ).fillna(frame["status"].astype(str))
    frame["status_label"] = frame["status"].map(
        {
            "pendente": "Pendente",
            "em_andamento": "Em andamento",
            "concluida": "Concluída",
            "bloqueada": "Bloqueada",
        }
    ).fillna(frame["status"].astype(str))
    frame["bloqueio_display"] = frame["motivo_bloqueio"].astype(str).map(lambda value: f"🔒 {value}" if value.strip() else "")
    if "data_limite" in frame.columns:
        fallback = frame.apply(lambda row: _demand_deadline(row.get("tipo_codigo", ""), row.get("competencia", "")), axis=1)
        frame["data_limite"] = frame["data_limite"].where(frame["data_limite"].astype(str).str.strip().ne(""), fallback)
    return frame[[
        "demanda_id",
        "empresa_id",
        "empresa",
        "cnpj",
        "competencia",
        "tipo_codigo",
        "tipo_demanda",
        "descricao",
        "status",
        "responsavel_operacional",
        "estagiario_responsavel",
        "responsavel_display",
        "data_limite",
        "observacao",
        "concluida_em",
        "concluida_por",
        "percentual_grupo",
        "bloqueada",
        "motivo_bloqueio",
        "status_label",
        "tempo_min",
        "tempo_max",
        "tempo_medio",
        "tempo_display",
        "estrelas",
        "estrelas_visual",
        "peso",
        "atualizado_em",
        "status_visual",
        "bloqueio_display",
    ]].copy()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_demandas_web() -> pd.DataFrame:
    if DEMANDAS_CSV.exists():
        try:
            df = pd.read_csv(DEMANDAS_CSV, dtype=str).fillna("")
            empresas = load_empresas_web()
            return normalize_demandas_web(df, empresas)
        except Exception:
            return normalize_demandas_web(pd.DataFrame())
    if usar_google_sheets():
        try:
            df = ler_dataframe_google(DEMANDAS_SHEET, DEMANDAS_COLUMNS, DEMANDAS_CSV)
            empresas = load_empresas_web()
            return normalize_demandas_web(df, empresas)
        except Exception:
            pass
    return normalize_demandas_web(pd.DataFrame())


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_marcacoes_web() -> pd.DataFrame:
    columns = MARCACOES_COLUMNS
    if MARCACOES_CSV.exists():
        return _read_marcacoes_local()
    if usar_google_sheets():
        try:
            df = _normalize_marcacoes_df(ler_dataframe_google(MARCACOES_SHEET, columns, MARCACOES_CSV))
            _write_marcacoes_local(df)
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=columns)


def append_marcacao_web(
    demanda_id: str,
    username: str,
    acao: str,
    status_novo: str,
    observacao: str | None = None,
    justificativa: str | None = None,
) -> None:
    row = {
        "marcacao_id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "demanda_id": str(demanda_id),
        "username": normalize_user(username),
        "acao": str(acao),
        "status_novo": str(status_novo),
        "observacao": str(observacao or ""),
        "justificativa": str(justificativa or ""),
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sincronizado": "0",
    }
    _append_marcacao_local(row)
    if usar_google_sheets():
        start_marcacoes_background_sync()
    load_data.clear()
    load_marcacoes_web.clear()


def append_marcacao(demanda_id: str, status: str, observacao: str) -> None:
    append_marcacao_web(demanda_id, current_user(), "status", status, observacao=observacao)


def can_mark_demanda(row: pd.Series, username: str, role: str) -> bool:
    role_key = normalize_user(role).lower()
    user_key = normalize_user(username)
    if role_key in {"admin", "contador"}:
        return True
    responsavel = normalize_user(row.get("responsavel_operacional", ""))
    estagiario = normalize_user(row.get("estagiario_responsavel", ""))
    return user_key in {responsavel, estagiario}


def apply_marcacoes_to_view(df_demandas: pd.DataFrame, df_marcacoes: pd.DataFrame) -> pd.DataFrame:
    frame = normalize_demandas_web(df_demandas)
    if frame.empty or df_marcacoes.empty:
        return frame

    marks = df_marcacoes.copy().fillna("")
    marks["data_ordem"] = pd.to_datetime(marks.get("data_hora", ""), errors="coerce")
    marks["marcacao_ordem"] = marks.get("marcacao_id", "").astype(str)
    marks = marks.sort_values(["data_ordem", "marcacao_ordem"], kind="mergesort")

    for demanda_id, group in marks.groupby("demanda_id", dropna=False):
        demanda_id = str(demanda_id)
        mask = frame["demanda_id"].astype(str).eq(demanda_id)
        if not mask.any():
            continue
        row_idx = frame.index[mask][0]
        row = frame.loc[row_idx].copy()
        for _, mark in group.iterrows():
            acao = normalize_user(mark.get("acao", "")).lower()
            status_novo = str(mark.get("status_novo", "")).strip().lower()
            observacao = str(mark.get("observacao", "")).strip()
            justificativa = str(mark.get("justificativa", "")).strip()
            data_hora = str(mark.get("data_hora", "")).strip()
            if acao in {"concluir", "concluir_selecionadas", "marcar_concluida"} or status_novo == "concluida":
                if row.get("bloqueada", "0") != "1":
                    row["status"] = "concluida"
                    row["concluida_em"] = data_hora or row.get("concluida_em", "")
                    row["concluida_por"] = str(mark.get("username", "")).strip() or row.get("concluida_por", "")
            elif acao in {"em_andamento", "marcar_em_andamento"} or status_novo == "em_andamento":
                if row.get("bloqueada", "0") != "1":
                    row["status"] = "em_andamento"
                    row["concluida_em"] = ""
                    row["concluida_por"] = ""
            elif acao in {"desmarcar", "reabrir"} or status_novo == "pendente":
                if row.get("bloqueada", "0") != "1":
                    row["status"] = "pendente"
                    row["concluida_em"] = ""
                    row["concluida_por"] = ""
            elif acao in {"observacao", "salvar_observacao"}:
                if observacao:
                    row["observacao"] = observacao
            if justificativa:
                row["observacao"] = f"{row.get('observacao', '').strip()} | Justificativa: {justificativa}".strip(" |")
            if observacao and acao not in {"observacao", "salvar_observacao"}:
                row["observacao"] = observacao
            row["atualizado_em"] = data_hora or row.get("atualizado_em", "")
        for column in frame.columns:
            frame.at[row_idx, column] = row.get(column, frame.at[row_idx, column])

    frame["status"] = frame["status"].replace("", "pendente")
    frame["status_visual"] = frame["status"].map(
        {
            "pendente": "⚪ Pendente",
            "em_andamento": "▶️ Em andamento",
            "concluida": "✅ Concluída",
            "bloqueada": "🔒 Bloqueada",
        }
    ).fillna(frame["status"].astype(str))
    frame["status_label"] = frame["status"].map(
        {
            "pendente": "Pendente",
            "em_andamento": "Em andamento",
            "concluida": "Concluída",
            "bloqueada": "Bloqueada",
        }
    ).fillna(frame["status"].astype(str))
    frame["bloqueio_display"] = frame["motivo_bloqueio"].astype(str).map(lambda value: f"🔒 {value}" if value.strip() else "")
    frame["responsavel_display"] = frame["responsavel_operacional"].where(
        frame["responsavel_operacional"].astype(str).str.strip().ne(""),
        frame["estagiario_responsavel"],
    )
    frame["estrelas_visual"] = frame["estrelas"].map(lambda value: "?" * int(value) if str(value).isdigit() and int(value) > 0 else "—")
    return frame


def normalize_demandas(demandas: pd.DataFrame, empresas: pd.DataFrame) -> pd.DataFrame:
    df = demandas.copy()
    for col in [
        "demanda_id", "empresa_id", "empresa", "cnpj", "competencia", "tipo_demanda",
        "status", "responsavel_operacional", "estagiario_responsavel", "observacao",
        "concluida_em", "concluida_por", "bloqueada", "motivo_bloqueio",
    ]:
        if col not in df.columns:
            df[col] = ""

    if (df["empresa"].eq("").all() or df["cnpj"].eq("").all()) and not empresas.empty:
        emp = empresas.copy()
        if "empresa_id" not in emp.columns and "id" in emp.columns:
            emp["empresa_id"] = emp["id"]
        keep = [c for c in ["empresa_id", "apelido", "razao_social", "cnpj"] if c in emp.columns]
        df = df.merge(emp[keep].drop_duplicates("empresa_id"), on="empresa_id", how="left", suffixes=("", "_emp"))
        if "apelido" in df.columns:
            df["empresa"] = df["empresa"].where(df["empresa"].astype(str).str.strip().ne(""), df["apelido"].fillna(""))
        if "razao_social" in df.columns:
            df["empresa"] = df["empresa"].where(df["empresa"].astype(str).str.strip().ne(""), df["razao_social"].fillna(""))
        if "cnpj_emp" in df.columns:
            df["cnpj"] = df["cnpj"].where(df["cnpj"].astype(str).str.strip().ne(""), df["cnpj_emp"].fillna(""))

    df["empresa"] = df["empresa"].fillna("").astype(str)
    df["cnpj"] = df["cnpj"].fillna("").astype(str)
    df["status"] = df["status"].fillna("pendente").astype(str).replace("", "pendente")
    parsed_resp = df["observacao"].fillna("").astype(str).map(extract_responsavel_from_observacao)
    for col in ["responsavel_operacional", "estagiario_responsavel"]:
        df[col] = df[col].fillna("").astype(str)
        df[col] = df[col].where(df[col].str.strip().ne(""), parsed_resp)
    return df


def login_screen() -> None:
    st.markdown("<div style='height:8vh'></div>", unsafe_allow_html=True)
    left, center, right = st.columns([1, 1.25, 1])
    with center:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=82)
        st.title("Controle de Empresas")
        st.caption("Acesso restrito ao painel operacional.")
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar", type="primary")
        if submitted:
            if check_login(username, password):
                st.session_state["usuario"] = normalize_user(username)
                st.session_state["nav_history"] = []
                st.session_state["page"] = "Home"
                st.session_state["page_label"] = "Home"
                st.query_params["page"] = "Home"
                st.rerun()
            else:
                st.error("Usuario ou senha invalidos.")


def sidebar(metadata: dict) -> str:
    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=54)
        st.markdown(f"**{escape(current_user())}**")
        st.caption(current_profile_label())
        st.divider()
        st.markdown("**Navegacao**")
        if st.button("Home", use_container_width=True):
            navigate_to("Home", "Home")
        if st.button("Empresas", use_container_width=True):
            navigate_to("Empresas", "Empresas")
        if st.button("📋 Demandas", use_container_width=True):
            navigate_to("Demandas", "📋 Demandas")
        competencia = str(metadata.get("competencia_atual") or "2026-05")
        st.caption(f"Competencia: {competencia}")
        st.caption(f"Atualizado: {metadata.get('data_ultima_atualizacao', '')}")
    return str(metadata.get("competencia_atual") or "2026-05")


def header(title: str, subtitle: str = "") -> None:
    st.markdown(
        f"""
        <div class="main-card">
            <div class="section-title">{escape(title)}</div>
            <div class="muted-text">{escape(subtitle)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_topbar(competencia: str) -> None:
    page_label = st.session_state.get("page_label", "Home")
    c1, c2, c3, c4, c5 = st.columns([2.1, 1.0, 1.0, 0.55, 0.45], vertical_alignment="center")
    with c1:
        st.markdown(
            f"""
            <div class="topbar-brand">
                <div>
                    <div class="topbar-brand-name">DMLS Controle</div>
                    <div class="topbar-brand-subtitle">{escape(str(page_label))} • Competência {escape(str(competencia))}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(f"<span class='status-badge'>Usuário: {escape(current_user())}</span>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"<span class='status-badge'>Perfil: {escape(current_profile_label())}</span>", unsafe_allow_html=True)
    with c4:
        if st.button("Home", key="topbar_home", use_container_width=True):
            navigate_to("Home", "Home")
    with c5:
        if st.button("Sair", key="topbar_logout", use_container_width=True):
            st.session_state.clear()
            st.rerun()


def render_home() -> None:
    empresas, _, _, metadata = load_data()
    df_demandas = build_demandas_view(load_demandas_web(), current_user(), current_profile(), empresas)
    total = len(df_demandas)
    pendentes = int(df_demandas["status"].astype(str).eq("pendente").sum()) if total else 0
    concluidas = int(df_demandas["status"].astype(str).eq("concluida").sum()) if total else 0
    progresso = round((concluidas / total) * 100, 0) if total else 0
    competencia = str(metadata.get("competencia_atual") or "2026-05")

    st.markdown(
        f"""
        <div class="home-hero">
            <h1>Olá, {escape(current_user())}</h1>
            <p>Competência atual: {escape(competencia)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="label">Total de demandas</div>
                <span class="value">{total}</span>
                <div class="hint">Base carregada em {escape(fonte_persistencia_label())}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="label">Pendentes</div>
                <span class="value">{pendentes}</span>
                <div class="hint">Demandas ainda abertas</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="label">Concluídas</div>
                <span class="value">{concluidas}</span>
                <div class="hint">Demandas finalizadas</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="label">Progresso geral</div>
                <span class="value">{progresso:.0f}%</span>
                <div class="hint">Conclusão simples da competência</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    empresas_total = int(len(empresas)) if empresas is not None else 0
    if empresas is not None and not empresas.empty:
        if "ativo" in empresas.columns:
            empresas_ativas = int(empresas["ativo"].astype(str).eq("1").sum())
        elif "is_ativo" in empresas.columns:
            empresas_ativas = int(empresas["is_ativo"].astype(str).eq("1").sum())
        else:
            empresas_ativas = empresas_total
        empresas_inativas = max(empresas_total - empresas_ativas, 0)
        regimes_distintos = int(empresas["regime"].astype(str).replace("", pd.NA).dropna().nunique())
    else:
        empresas_ativas = 0
        empresas_inativas = 0
        regimes_distintos = 0

    st.markdown('<div class="section-title" style="margin-top:0.35rem;">Dashboards principais</div>', unsafe_allow_html=True)
    st.markdown('<div class="muted-text" style="margin-bottom:0.55rem;">Dois painéis diretos para entrar no fluxo operacional.</div>', unsafe_allow_html=True)
    d1, d2 = st.columns(2, gap="large")
    with d1:
        st.markdown(
            f"""
            <div class="dashboard-panel dashboard-panel--demandas">
                <div class="dashboard-panel__top">
                    <div class="dashboard-panel__icon">📋</div>
                    <div class="dashboard-panel__kicker">Operação diária</div>
                </div>
                <div class="dashboard-panel__title">Controle de Demandas</div>
                <div class="dashboard-panel__desc">Veja pendências, concluídas e a distribuição da competência em um painel mais direto.</div>
                <div class="dashboard-panel__stats">
                    <div class="dashboard-panel__stat"><span>Total</span><strong>{total}</strong></div>
                    <div class="dashboard-panel__stat"><span>Pendentes</span><strong>{pendentes}</strong></div>
                    <div class="dashboard-panel__stat"><span>Concluídas</span><strong>{concluidas}</strong></div>
                    <div class="dashboard-panel__stat"><span>Progresso</span><strong>{progresso:.0f}%</strong></div>
                </div>
                <div class="dashboard-panel__footer">
                    <div class="dashboard-panel__hint">Acesso rápido ao painel de trabalho.</div>
                    <div class="status-badge">Fluxo operacional</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("📋 Abrir Demandas", key="home_demandas", type="primary", use_container_width=True):
            navigate_to("Demandas", "📋 Demandas")
    with d2:
        st.markdown(
            f"""
            <div class="dashboard-panel dashboard-panel--empresas">
                <div class="dashboard-panel__top">
                    <div class="dashboard-panel__icon">🏢</div>
                    <div class="dashboard-panel__kicker">Base operacional</div>
                </div>
                <div class="dashboard-panel__title">Controle de Empresas</div>
                <div class="dashboard-panel__desc">Consulte clientes, ativos e filtros cadastrais em uma visão mais limpa e objetiva.</div>
                <div class="dashboard-panel__stats">
                    <div class="dashboard-panel__stat"><span>Total</span><strong>{empresas_total}</strong></div>
                    <div class="dashboard-panel__stat"><span>Ativas</span><strong>{empresas_ativas}</strong></div>
                    <div class="dashboard-panel__stat"><span>Inativas</span><strong>{empresas_inativas}</strong></div>
                    <div class="dashboard-panel__stat"><span>Regimes</span><strong>{regimes_distintos}</strong></div>
                </div>
                <div class="dashboard-panel__footer">
                    <div class="dashboard-panel__hint">Acesso rápido à base de clientes.</div>
                    <div class="status-badge">Consulta cadastral</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("🏢 Abrir Empresas", key="home_empresas", use_container_width=True):
            navigate_to("Empresas", "Empresas")


def sort_controls(df: pd.DataFrame, columns: list[str], key_prefix: str) -> pd.DataFrame:
    if df.empty:
        return df
    c1, c2 = st.columns([1.4, 0.8])
    sort_col = c1.selectbox("Classificar por", columns, key=f"{key_prefix}_sort_col")
    sort_dir = c2.selectbox("Ordem", ["A-Z", "Z-A"], key=f"{key_prefix}_sort_dir")
    ascending = sort_dir != "Z-A"
    sort_series = df[sort_col].fillna("").astype(str).map(
        lambda value: unicodedata.normalize("NFKD", value).casefold()
    )
    return (
        df.assign(_sort_key=sort_series)
        .sort_values("_sort_key", ascending=ascending, kind="mergesort")
        .drop(columns=["_sort_key"])
        .reset_index(drop=True)
    )


def render_table(df: pd.DataFrame, widths: dict[str, str]) -> None:
    colgroup = "<colgroup>" + "".join(
        f"<col style='width:{widths.get(str(col), 'auto')}'>" for col in df.columns
    ) + "</colgroup>"
    html = df.fillna("").to_html(index=False, escape=True, classes="dmls-table")
    html = html.replace("<table ", f"<table ", 1).replace(">\n  <thead>", f">\n  {colgroup}\n  <thead>", 1)
    st.markdown(html, unsafe_allow_html=True)


def _empresa_status_label(value: str) -> str:
    return "Ativa" if str(value).strip() in {"1", "1.0", "true", "True", "sim", "SIM"} else "Inativa"


def _company_blob(df: pd.DataFrame) -> pd.Series:
    return (
        df["cnpj"].astype(str) + " "
        + df["apelido"].astype(str) + " "
        + df["razao_social"].astype(str) + " "
        + df["nome_fantasia"].astype(str) + " "
        + df["cidade"].astype(str)
    ).str.upper()


def _empresa_detail_html(row: pd.Series) -> str:
    return f"""
    <div class="main-card">
        <div class="section-title">Detalhe rápido</div>
        <div class="muted-text" style="margin-bottom:0.4rem;">Visão resumida da empresa selecionada.</div>
        <div class="status-badge">CNPJ: {escape(str(row.get("cnpj", "")))}</div>
        <div style="height:8px"></div>
        <div><strong>Razão Social:</strong> {escape(str(row.get("razao_social", "")))}</div>
        <div><strong>Nome Fantasia:</strong> {escape(str(row.get("nome_fantasia", "")))}</div>
        <div><strong>Apelido:</strong> {escape(str(row.get("apelido", "")))}</div>
        <div><strong>Regime:</strong> {escape(str(row.get("regime", "")))}</div>
        <div><strong>Cidade/UF:</strong> {escape(str(row.get("cidade", "")))} / {escape(str(row.get("uf", "")))}</div>
        <div><strong>Contador responsável:</strong> {escape(str(row.get("contador_responsavel", "")))}</div>
        <div><strong>Status:</strong> {_empresa_status_label(str(row.get("ativo", "")))}</div>
    </div>
    """


def _selected_empresa_frame(empresas: pd.DataFrame, selected_id: str) -> pd.DataFrame:
    if empresas.empty or not selected_id:
        return empresas.iloc[0:0].copy()
    if "empresa_id" in empresas.columns:
        return empresas.loc[empresas["empresa_id"].astype(str).eq(str(selected_id))].copy()
    return empresas.loc[empresas["cnpj"].astype(str).eq(str(selected_id))].copy()


def render_empresas(empresas: pd.DataFrame) -> None:
    header("Controle de Empresas", "Consulta rápida dos clientes exportados pelo sistema principal.")

    empresas_df = load_empresas_web()
    if empresas_df.empty:
        st.info("Nenhuma empresa encontrada em data_web/empresas_web.csv.")
        return

    base_df = empresas_df.copy()
    df = base_df.copy()

    total_empresas = len(df)
    ativas = int(df["ativo"].astype(str).eq("1").sum())
    inativas = int(df["ativo"].astype(str).eq("0").sum())
    regimes = int(df["regime"].astype(str).replace("", pd.NA).dropna().nunique()) if total_empresas else 0

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"<div class='metric-card'><div class='label'>Total de empresas</div><span class='value'>{total_empresas}</span><div class='hint'>Base operacional carregada</div></div>", unsafe_allow_html=True)
    with m2:
        st.markdown(f"<div class='metric-card'><div class='label'>Ativas</div><span class='value'>{ativas}</span><div class='hint'>Clientes em operação</div></div>", unsafe_allow_html=True)
    with m3:
        st.markdown(f"<div class='metric-card'><div class='label'>Inativas</div><span class='value'>{inativas}</span><div class='hint'>Clientes suspensos</div></div>", unsafe_allow_html=True)
    with m4:
        st.markdown(f"<div class='metric-card'><div class='label'>Regimes</div><span class='value'>{regimes}</span><div class='hint'>Tipos distintos</div></div>", unsafe_allow_html=True)

    c1, c2, c3, c4, c5, c6 = st.columns([2.4, 1.2, 1.2, 1.0, 0.7, 0.9], vertical_alignment="bottom")
    busca = c1.text_input("Busca geral", placeholder="CNPJ, apelido, razão social, fantasia, cidade", key="empresas_busca")
    regimes_options = ["Todos"] + sorted([v for v in df["regime"].astype(str).unique().tolist() if v.strip()])
    regime = c2.selectbox("Regime", regimes_options, key="empresas_regime")
    responsaveis_options = ["Todos"] + sorted([v for v in df["contador_responsavel"].astype(str).unique().tolist() if v.strip()])
    responsavel = c3.selectbox("Contador responsável", responsaveis_options, key="empresas_responsavel")
    status = c4.selectbox("Ativo/Inativo", ["Todos", "Ativas", "Inativas"], key="empresas_status")
    sort_col = c5.selectbox("Ordenar por", ["apelido", "razao_social", "cnpj", "regime", "cidade", "uf", "contador_responsavel", "ativo"], key="empresas_sort_col")
    sort_dir = c6.selectbox("Ordem", ["A-Z", "Z-A"], key="empresas_sort_dir")

    action_left, action_right = st.columns([0.9, 2.2], vertical_alignment="center")
    if action_left.button("🔄 Recarregar", use_container_width=True):
        st.rerun()
    st.caption("Exportação CSV disponível para perfis administrativos.")

    df = df.copy()
    if busca:
        q = busca.strip().upper()
        df = df[_company_blob(df).str.contains(q, regex=False)]
    if regime != "Todos":
        df = df[df["regime"].astype(str).eq(regime)]
    if responsavel != "Todos":
        df = df[df["contador_responsavel"].astype(str).eq(responsavel)]
    if status == "Ativas":
        df = df[df["ativo"].astype(str).eq("1")]
    elif status == "Inativas":
        df = df[df["ativo"].astype(str).eq("0")]

    ascending = sort_dir != "Z-A"
    df = df.sort_values(by=sort_col, kind="mergesort", ascending=ascending)

    view = df.rename(
        columns={
            "apelido": "Apelido",
            "razao_social": "Razão Social",
            "cnpj": "CNPJ",
            "regime": "Regime",
            "cidade": "Cidade",
            "uf": "UF",
            "contador_responsavel": "Contador",
            "ativo": "Ativo",
        }
    )[["Apelido", "Razão Social", "CNPJ", "Regime", "Cidade", "UF", "Contador", "Ativo"]]
    view_display = view.copy()
    view_display["Ativo"] = view_display["Ativo"].map(_empresa_status_label)
    view_display = view_display.reset_index(drop=True)

    export_bytes = df.to_csv(index=False).encode("utf-8-sig")
    action_right.download_button(
        "📤 Exportar visão filtrada",
        data=export_bytes,
        file_name="empresas_visao_filtrada.csv",
        mime="text/csv",
        use_container_width=True,
        disabled=current_profile() == "estagiario",
    )

    st.markdown('<div style="margin-top:0.55rem;"></div>', unsafe_allow_html=True)
    st.dataframe(
        view_display,
        hide_index=True,
        use_container_width=True,
        height=420,
        column_config={
            "Apelido": st.column_config.TextColumn("Apelido", width="medium"),
            "Razão Social": st.column_config.TextColumn("Razão Social", width="large"),
            "CNPJ": st.column_config.TextColumn("CNPJ", width="medium"),
            "Regime": st.column_config.TextColumn("Regime", width="medium"),
            "Cidade": st.column_config.TextColumn("Cidade", width="medium"),
            "UF": st.column_config.TextColumn("UF", width="small"),
            "Contador": st.column_config.TextColumn("Contador", width="medium"),
            "Ativo": st.column_config.TextColumn("Ativo", width="small"),
        },
    )

    st.markdown('<div class="main-card" style="margin-top:0.75rem;">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Detalhe rápido</div>', unsafe_allow_html=True)
    if view.empty:
        st.info("Nenhuma empresa encontrada com os filtros atuais.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    detail_options = df["empresa_id"].astype(str).tolist() if "empresa_id" in df.columns else df["cnpj"].astype(str).tolist()
    detail_labels = {
        str(option): f"{str(apelido)} • {str(cnpj)}"
        for option, apelido, cnpj in zip(detail_options, df["apelido"].astype(str).tolist(), df["cnpj"].astype(str).tolist())
    }
    selected_detail = st.selectbox(
        "Ver detalhes",
        detail_options,
        format_func=lambda value: detail_labels.get(str(value), str(value)),
        key="empresas_detail_select",
    )
    selected_row = _selected_empresa_frame(df, str(selected_detail))
    if not selected_row.empty:
        row = selected_row.iloc[0]
        st.markdown(_empresa_detail_html(row), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if current_profile() != "estagiario":
        with st.expander("Edição simples da empresa selecionada", expanded=False):
            if selected_row.empty:
                st.info("Selecione uma empresa para editar.")
            else:
                row = selected_row.iloc[0]
                with st.form("empresa_edicao_simples"):
                    apelido = st.text_input("Apelido", value=str(row.get("apelido", "")))
                    cidade = st.text_input("Cidade", value=str(row.get("cidade", "")))
                    uf = st.text_input("UF", value=str(row.get("uf", "")), max_chars=2)
                    contador_responsavel = st.text_input("Contador responsável", value=str(row.get("contador_responsavel", "")))
                    ativo_value = st.selectbox("Ativo", ["1", "0"], index=0 if str(row.get("ativo", "1")) == "1" else 1)
                    save_simple = st.form_submit_button("💾 Salvar ajustes", type="primary")
                if save_simple:
                    updated = base_df.copy()
                    key_col = "empresa_id" if "empresa_id" in updated.columns else "cnpj"
                    target_key = str(row.get(key_col, ""))
                    mask = updated[key_col].astype(str).eq(target_key)
                    updated.loc[mask, "apelido"] = apelido.strip()
                    updated.loc[mask, "cidade"] = cidade.strip()
                    updated.loc[mask, "uf"] = uf.strip().upper()
                    updated.loc[mask, "contador_responsavel"] = contador_responsavel.strip()
                    updated.loc[mask, "ativo"] = ativo_value
                    updated.loc[mask, "atualizado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_empresas_web(updated)
                    st.success("Empresa atualizada com sucesso.")
                    st.rerun()


def can_mark(row: pd.Series) -> bool:
    if is_admin():
        return True
    user = current_user()
    return user in {
        normalize_user(row.get("responsavel_operacional", "")),
        normalize_user(row.get("estagiario_responsavel", "")),
    }


def append_marcacao(demanda_id: str, status: str, observacao: str) -> None:
    append_marcacao_web(demanda_id, current_user(), "status", status, observacao=observacao)


def metric_row(total: int, pendentes: int, concluidas: int) -> None:
    pct = round((concluidas / total) * 100, 0) if total else 0
    st.markdown(
        f"""
        <div class="metric-row">
            <div class="metric-card"><span>Total</span><strong>{total}</strong></div>
            <div class="metric-card"><span>Pendentes</span><strong>{pendentes}</strong></div>
            <div class="metric-card"><span>Concluidas</span><strong>{concluidas}</strong></div>
            <div class="metric-card"><span>% concluido</span><strong>{pct:.0f}%</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_demandas_metrics(total: int, pendentes: int, concluidas: int, minhas: int) -> None:
    geral_pct = round((concluidas / total) * 100, 0) if total else 0
    meu_pct = round((minhas / total) * 100, 0) if total else 0
    top_row = st.columns(3)
    bottom_row = st.columns(3)
    cards = [
        ("Total", total, "Demandas visíveis na competência"),
        ("Pendentes", pendentes, "Ainda abertas para trabalho"),
        ("Concluídas", concluidas, "Finalizadas no painel"),
        ("Minhas", minhas, "Sob sua responsabilidade"),
        ("Meu percentual", f"{meu_pct:.0f}%", "Minha participação sobre o total"),
        ("Percentual geral", f"{geral_pct:.0f}%", "Conclusão simples da tela"),
    ]
    for idx, (label, value, hint) in enumerate(cards):
        container = top_row[idx] if idx < 3 else bottom_row[idx - 3]
        with container:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="label">{escape(str(label))}</div>
                    <span class="value">{escape(str(value))}</span>
                    <div class="hint">{escape(str(hint))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _demanda_status_value(value: str) -> str:
    text = normalize_user(value).lower()
    if text in {"concluida", "concluido", "finalizado"}:
        return "concluida"
    if text in {"em_andamento", "andamento", "andando"}:
        return "em_andamento"
    if text in {"bloqueada", "bloqueado"}:
        return "bloqueada"
    return "pendente"


def build_demandas_view(df: pd.DataFrame, username: str, role: str, empresas: pd.DataFrame | None = None) -> pd.DataFrame:
    frame = apply_marcacoes_to_view(normalize_demandas_web(df, empresas), load_marcacoes_web())
    if frame.empty:
        return frame

    user_key = normalize_user(username)
    role_key = normalize_user(role).lower()
    frame["status"] = frame["status"].map(_demanda_status_value)
    frame.loc[frame["bloqueada"].astype(str).eq("1"), "status"] = "bloqueada"
    frame["status_visual"] = frame["status"].map(
        {
            "pendente": "⚪ Pendente",
            "em_andamento": "▶️ Em andamento",
            "concluida": "✅ Concluída",
            "bloqueada": "🔒 Bloqueada",
        }
    ).fillna(frame["status"].astype(str))
    frame["minha_demanda"] = (
        frame["responsavel_operacional"].astype(str).map(normalize_user).eq(user_key)
        | frame["estagiario_responsavel"].astype(str).map(normalize_user).eq(user_key)
    )
    frame["editavel"] = frame.apply(lambda row: can_mark_demanda(row, username, role) and str(row.get("bloqueada", "0")) != "1", axis=1)
    frame["selecionavel"] = True
    frame["responsavel_display"] = frame["responsavel_display"].where(
        frame["responsavel_display"].astype(str).str.strip().ne(""),
        frame["responsavel_operacional"],
    )
    frame["dificuldade"] = frame["estrelas_visual"]
    frame["demanda_display"] = frame["descricao"].where(frame["descricao"].astype(str).str.strip().ne(""), frame["tipo_demanda"])
    frame["bloqueio_display"] = frame["bloqueio_display"].where(frame["bloqueio_display"].astype(str).str.strip().ne(""), "")
    frame["status_visual"] = frame["status_visual"].where(frame["status_visual"].astype(str).str.strip().ne(""), frame["status"].astype(str))
    if role_key in {"admin", "contador"}:
        frame["editavel"] = frame["bloqueada"].astype(str).ne("1")
    return frame


def _demandas_allowed_subset(df: pd.DataFrame, selected_ids: list[str], username: str, role: str) -> tuple[pd.DataFrame, int, int]:
    if not selected_ids:
        return df.iloc[0:0].copy(), 0, 0
    subset = df[df["demanda_id"].astype(str).isin([str(value) for value in selected_ids])].copy()
    blocked = int(subset["bloqueada"].astype(str).eq("1").sum()) if not subset.empty else 0
    allowed_mask = subset.apply(lambda row: can_mark_demanda(row, username, role) and str(row.get("bloqueada", "0")) != "1", axis=1)
    denied = int((~allowed_mask).sum()) if not subset.empty else 0
    return subset.loc[allowed_mask].copy(), denied, blocked


def _demandas_apply_batch(
    df: pd.DataFrame,
    selected_ids: list[str],
    username: str,
    role: str,
    action: str,
    observacao: str = "",
    justificativa: str = "",
) -> tuple[int, int, int]:
    targets, denied, blocked = _demandas_allowed_subset(df, selected_ids, username, role)
    if targets.empty:
        return 0, denied, blocked

    action = action.lower().strip()
    for _, row in targets.iterrows():
        demanda_id = str(row.get("demanda_id", ""))
        if action == "concluir":
            append_marcacao_web(demanda_id, username, "concluir", "concluida", observacao=observacao or str(row.get("observacao", "")))
        elif action == "em_andamento":
            append_marcacao_web(demanda_id, username, "em_andamento", "em_andamento", observacao=observacao or str(row.get("observacao", "")))
        elif action == "desmarcar":
            append_marcacao_web(demanda_id, username, "desmarcar", "pendente", observacao=observacao or str(row.get("observacao", "")), justificativa=justificativa)
        elif action == "observacao":
            append_marcacao_web(demanda_id, username, "observacao", str(row.get("status", "pendente")), observacao=observacao)
    load_marcacoes_web.clear()
    return int(len(targets)), denied, blocked


def _render_demandas_grid_aggrid(df: pd.DataFrame) -> list[str]:
    status_options = ["Pendente", "Em andamento", "Concluída"]
    status_to_internal = {
        "Pendente": "pendente",
        "Em andamento": "em_andamento",
        "Concluída": "concluida",
    }
    internal_to_status = {value: key for key, value in status_to_internal.items()}
    visible_order = [
        "Empresa",
        "Demanda",
        "Responsável",
        "Status",
        "Tempo",
        "Dificuldade",
        "Observação",
        "Concluída em",
        "Concluída por",
        "Bloqueio",
    ]
    hidden_order = [
        "demanda_id",
        "status",
        "data_limite",
        "minha_demanda",
        "editavel",
        "bloqueada",
        "responsavel_operacional",
        "estagiario_responsavel",
    ]
    grid_df = df[visible_order + hidden_order].copy()
    if "data_limite" in grid_df.columns:
        grid_df.insert(4, "Data limite", grid_df["data_limite"].map(_format_date_display))
    if not grid_df.empty and "Demanda" in grid_df.columns:
        demanda_ordem = pd.to_numeric(
            grid_df["Demanda"].astype(str).str.extract(r"^\s*(\d+)")[0],
            errors="coerce",
        ).fillna(999999).astype(int)
        grid_df = (
            grid_df.assign(_demanda_ordem=demanda_ordem, _demanda_texto=grid_df["Demanda"].astype(str))
            .sort_values(["_demanda_ordem", "_demanda_texto", "Empresa"], kind="mergesort")
            .drop(columns=["_demanda_ordem", "_demanda_texto"])
        )
    if FORCE_NATIVE_GRID or not AGGRID_AVAILABLE:
        fallback_columns = [col for col in grid_df.columns if col not in hidden_order and col != "data_limite"]
        fallback = grid_df[fallback_columns].copy()
        fallback.insert(0, "Selecionar", False)
        edited = st.data_editor(
            fallback,
            hide_index=True,
            use_container_width=True,
            height=760,
            column_config={
                "Selecionar": st.column_config.CheckboxColumn("Selecionar"),
                "Status": st.column_config.SelectboxColumn("Status", options=status_options, required=True),
            },
            disabled=[col for col in fallback.columns if col not in {"Selecionar", "Status"}],
            key="demandas_fallback_editor",
        )
        status_baseline = st.session_state.setdefault("demandas_status_baseline", {})
        changes_applied = 0
        for row_index, row in edited.iterrows():
            if row_index not in grid_df.index:
                continue
            source_row = grid_df.loc[row_index]
            demanda_id = str(source_row.get("demanda_id", "")).strip()
            if not demanda_id:
                continue
            current_status_label = str(row.get("Status", "")).strip()
            if current_status_label not in status_to_internal:
                continue
            current_status_internal = status_to_internal[current_status_label]
            original_status_internal = str(source_row.get("status", "")).strip().lower()
            baseline_status = str(status_baseline.get(demanda_id, original_status_internal)).strip().lower()
            if current_status_internal == baseline_status:
                continue
            if str(source_row.get("bloqueada", "0")) == "1":
                continue
            editavel_value = str(source_row.get("editavel", "")).strip().lower()
            if editavel_value not in {"true", "1", "yes"}:
                continue
            append_marcacao_web(
                demanda_id,
                current_user(),
                "status",
                current_status_internal,
                observacao=str(row.get("Observacao", row.get("Observação", ""))),
            )
            status_baseline[demanda_id] = current_status_internal
            changes_applied += 1
        if changes_applied:
            st.session_state["demandas_status_baseline"] = status_baseline
            st.toast("Status salvo em segundo plano")
        selected_index = edited.index[edited["Selecionar"].astype(bool)]
        selected_ids = grid_df.loc[selected_index, "demanda_id"].astype(str).tolist()
        return selected_ids

    builder = GridOptionsBuilder.from_dataframe(grid_df)
    builder.configure_default_column(sortable=False, filter=True, resizable=True, floatingFilter=True, editable=False)
    builder.configure_selection("multiple", use_checkbox=True, header_checkbox=True)
    builder.configure_pagination(paginationAutoPageSize=False, paginationPageSize=100)
    builder.configure_grid_options(
        rowHeight=36,
        domLayout="normal",
        suppressRowClickSelection=True,
        tooltipShowDelay=0,
        singleClickEdit=True,
        stopEditingWhenCellsLoseFocus=True,
    )
    for column in ["demanda_id", "status", "data_limite", "minha_demanda", "editavel", "bloqueada", "responsavel_operacional", "estagiario_responsavel"]:
        builder.configure_column(column, hide=True)
    builder.configure_column("Empresa", minWidth=180)
    builder.configure_column("Demanda", minWidth=220, sortable=True, sort="asc")
    builder.configure_column("Responsável", minWidth=120)
    if JsCode is not None:
        status_editable = JsCode(
            """
            function(params) {
                if (!params.data) return false;
                var editable = params.data.editavel === true || String(params.data.editavel).toLowerCase() === 'true';
                var blocked = String(params.data.bloqueada) === '1';
                return editable && !blocked;
            }
            """
        )
        status_cell_style = JsCode(
            """
            function(params) {
                var value = String(params.value || '').trim();
                if (!value) {
                    return {
                        backgroundColor: 'rgba(148, 163, 184, 0.18)',
                        color: '#334155',
                        border: '1px solid rgba(148, 163, 184, 0.45)',
                        fontWeight: '800',
                        textAlign: 'center'
                    };
                }
                var normalized = value.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
                if (normalized === 'pendente') {
                    return {
                        backgroundColor: 'rgba(251, 191, 36, 0.18)',
                        color: '#92400e',
                        border: '1px solid rgba(245, 158, 11, 0.45)',
                        fontWeight: '800',
                        textAlign: 'center'
                    };
                }
                if (normalized === 'em andamento') {
                    return {
                        backgroundColor: 'rgba(59, 130, 246, 0.16)',
                        color: '#1d4ed8',
                        border: '1px solid rgba(96, 165, 250, 0.45)',
                        fontWeight: '800',
                        textAlign: 'center'
                    };
                }
                if (normalized === 'concluida') {
                    return {
                        backgroundColor: 'rgba(34, 197, 94, 0.16)',
                        color: '#166534',
                        border: '1px solid rgba(74, 222, 128, 0.45)',
                        fontWeight: '800',
                        textAlign: 'center'
                    };
                }
                if (normalized === 'bloqueada') {
                    return {
                        backgroundColor: 'rgba(248, 113, 113, 0.16)',
                        color: '#b91c1c',
                        border: '1px solid rgba(248, 113, 113, 0.45)',
                        fontWeight: '800',
                        textAlign: 'center'
                    };
                }
                return {
                    backgroundColor: 'rgba(148, 163, 184, 0.18)',
                    color: '#334155',
                    border: '1px solid rgba(148, 163, 184, 0.45)',
                    fontWeight: '800',
                    textAlign: 'center'
                };
            }
            """
        )
        builder.configure_column(
            "Status",
            minWidth=170,
            editable=status_editable,
            cellEditor="agSelectCellEditor",
            cellEditorParams={"values": status_options},
            cellStyle=status_cell_style,
        )
    else:
        builder.configure_column(
            "Status",
            minWidth=170,
            editable=True,
            cellEditor="agSelectCellEditor",
            cellEditorParams={"values": status_options},
            cellStyle=status_cell_style,
        )
    builder.configure_column("Data limite", minWidth=120)
    builder.configure_column("Tempo", minWidth=95)
    builder.configure_column("Dificuldade", minWidth=90)
    builder.configure_column("Observação", minWidth=220)
    builder.configure_column("Concluída em", minWidth=145)
    builder.configure_column("Concluída por", minWidth=130)
    builder.configure_column("Bloqueio", minWidth=180)
    if JsCode is not None:
        row_style = JsCode(
            """
            function(params) {
                if (params.data && String(params.data.bloqueada) === '1') {
                    return {backgroundColor: '#fff1f2', color: '#7f1d1d'};
                }
                if (params.data && (params.data.minha_demanda === true || String(params.data.minha_demanda).toLowerCase() === 'true')) {
                    return {backgroundColor: '#eff6ff'};
                }
                return {};
            }
            """
        )
        builder.configure_grid_options(getRowStyle=row_style)
    grid_options = builder.build()
    response = AgGrid(
        grid_df,
        gridOptions=grid_options,
        height=860,
        update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED,
        data_return_mode=DataReturnMode.AS_INPUT,
        allow_unsafe_jscode=True,
        fit_columns_on_grid_load=True,
        enable_enterprise_modules=False,
        theme="streamlit",
        key="demandas_aggrid",
    )
    edited_data = response.get("data", None)
    if isinstance(edited_data, pd.DataFrame) and not edited_data.empty:
        changes_applied = 0
        status_baseline = st.session_state.setdefault("demandas_status_baseline", {})
        for _, row in edited_data.iterrows():
            demanda_id = str(row.get("demanda_id", "")).strip()
            if not demanda_id:
                continue
            original_status_internal = str(row.get("status", "")).strip().lower()
            current_status_label = str(row.get("Status", "")).strip()
            if not current_status_label:
                continue
            if current_status_label not in status_to_internal:
                continue
            current_status_internal = status_to_internal[current_status_label]
            baseline_status = str(status_baseline.get(demanda_id, original_status_internal)).strip().lower()
            if current_status_internal == baseline_status:
                continue
            if str(row.get("bloqueada", "0")) == "1":
                continue
            editavel_value = str(row.get("editavel", "")).strip().lower()
            if editavel_value not in {"true", "1", "yes"}:
                continue
            append_marcacao_web(
                demanda_id,
                current_user(),
                "status",
                current_status_internal,
                observacao=str(row.get("observacao", "")),
            )
            status_baseline[demanda_id] = current_status_internal
            changes_applied += 1
        if changes_applied:
            st.session_state["demandas_status_baseline"] = status_baseline
            load_marcacoes_web.clear()
            st.toast("✅ Status atualizado com sucesso")
    selected_rows = response.get("selected_rows", [])
    if isinstance(selected_rows, pd.DataFrame):
        if selected_rows.empty or "demanda_id" not in selected_rows.columns:
            return []
        return selected_rows["demanda_id"].astype(str).tolist()
    if not selected_rows:
        return []
    return [str(row.get("demanda_id", "")) for row in selected_rows if row.get("demanda_id", "")]


def _render_selected_demand_panel(df: pd.DataFrame, selected_ids: list[str]) -> None:
    if not selected_ids:
        st.markdown(
            """
            <div class="main-card">
                <div class="section-title">Detalhes da demanda selecionada</div>
                <div class="muted-text">Selecione uma ou mais demandas na tabela para ver os detalhes aqui.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return
    selected = df[df["demanda_id"].astype(str).isin([str(value) for value in selected_ids])].copy()
    if selected.empty:
        return
    row = selected.iloc[0]
    st.markdown(
        f"""
        <div class="main-card">
            <div class="section-title">Detalhes da demanda selecionada</div>
            <div class="muted-text" style="margin-bottom:0.4rem;">{escape(str(len(selected_ids)))} demanda(s) selecionada(s). Mostrando a primeira seleção.</div>
            <div><strong>Empresa:</strong> {escape(str(row.get("Empresa", row.get("empresa", ""))))}</div>
            <div><strong>Tipo:</strong> {escape(str(row.get("Demanda", row.get("tipo_demanda", ""))))}</div>
            <div><strong>Responsável:</strong> {escape(str(row.get("Responsável", row.get("responsavel_display", ""))))}</div>
            <div><strong>Status:</strong> {escape(str(row.get("Status", row.get("status_visual", ""))))}</div>
            <div><strong>Data limite:</strong> {escape(_format_date_display(row.get("Data limite", row.get("data_limite", ""))))}</div>
            <div><strong>Tempo:</strong> {escape(str(row.get("Tempo", row.get("tempo_display", ""))))}</div>
            <div><strong>Estrelas:</strong> {escape(str(row.get("Dificuldade", row.get("estrelas_visual", ""))))}</div>
            <div><strong>Observação:</strong> {escape(str(row.get("Observação", row.get("observacao", ""))))}</div>
            <div><strong>Bloqueio:</strong> {escape(str(row.get("Bloqueio", row.get("bloqueio_display", ""))))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_demandas(empresas: pd.DataFrame, demandas: pd.DataFrame, competencia_padrao: str) -> None:
    header("📋 Controle de Demandas", "Visualize, filtre e marque as demandas operacionais da competência.")

    username = current_user()
    role = current_profile()
    base_demandas = demandas if not demandas.empty else load_demandas_web()
    view = build_demandas_view(base_demandas, username, role, empresas)
    if view.empty:
        st.info("Nenhuma demanda encontrada.")
        return

    if "demandas_only_mine" not in st.session_state:
        st.session_state["demandas_only_mine"] = False
    if "demandas_status_filter" not in st.session_state:
        st.session_state["demandas_status_filter"] = "Todos"

    competencias_options = sorted([v for v in view["competencia"].astype(str).dropna().unique().tolist() if v.strip()])
    competence_default = str(competencia_padrao or (competencias_options[0] if competencias_options else ""))
    status_options = ["Todos", "pendente", "em_andamento", "concluida", "bloqueada"]
    responsavel_options = ["Todos"] + sorted([v for v in pd.concat([view["responsavel_operacional"], view["estagiario_responsavel"]]).astype(str).unique().tolist() if v.strip()])
    empresa_options = ["Todas"] + sorted([v for v in view["empresa"].astype(str).unique().tolist() if v.strip()])
    tipo_options = ["Todos"] + sorted([v for v in view["tipo_demanda"].astype(str).unique().tolist() if v.strip()])

    filter_cols = st.columns([1.0, 1.02, 1.08, 1.08, 1.35, 0.75, 0.72, 0.85], vertical_alignment="bottom")
    competencia = filter_cols[0].selectbox(
        "Competência",
        competencias_options or [competence_default],
        index=(competencias_options.index(competence_default) if competence_default in competencias_options else 0),
        key="demandas_competencia",
    )
    status = filter_cols[1].selectbox(
        "Status",
        status_options,
        index=status_options.index(st.session_state.get("demandas_status_filter", "Todos")) if st.session_state.get("demandas_status_filter", "Todos") in status_options else 0,
        key="demandas_status",
    )
    st.session_state["demandas_status_filter"] = status
    responsavel = filter_cols[2].selectbox("Responsável / Estagiário", responsavel_options, key="demandas_responsavel")
    empresa = filter_cols[3].selectbox("Empresa", empresa_options, key="demandas_empresa")
    tipo = filter_cols[4].selectbox("Tipo de demanda", tipo_options, key="demandas_tipo")

    if filter_cols[5].button("🎯 Só minhas", use_container_width=True, type="primary" if st.session_state.get("demandas_only_mine") else "secondary"):
        st.session_state["demandas_only_mine"] = True
        st.rerun()
    if filter_cols[6].button("👥 Todas", use_container_width=True, type="primary" if not st.session_state.get("demandas_only_mine") else "secondary"):
        st.session_state["demandas_only_mine"] = False
        st.rerun()
    if filter_cols[7].button("🔄 Recarregar", use_container_width=True):
        load_demandas_web.clear()
        load_marcacoes_web.clear()
        st.rerun()

    filtro_mask = view["competencia"].astype(str).eq(str(competencia))
    if status != "Todos":
        filtro_mask &= view["status"].astype(str).eq(status)
    if responsavel != "Todos":
        filtro_mask &= (
            view["responsavel_operacional"].astype(str).eq(responsavel)
            | view["estagiario_responsavel"].astype(str).eq(responsavel)
        )
    if empresa != "Todas":
        filtro_mask &= view["empresa"].astype(str).eq(empresa)
    if tipo != "Todos":
        filtro_mask &= view["tipo_demanda"].astype(str).eq(tipo)
    if st.session_state.get("demandas_only_mine"):
        filtro_mask &= view["minha_demanda"]

    filtered = view.loc[filtro_mask].copy()
    if filtered.empty:
        st.info("Nenhuma demanda encontrada com os filtros atuais.")
        return

    total = len(filtered)
    pendentes = int(filtered["status"].astype(str).eq("pendente").sum())
    concluidas = int(filtered["status"].astype(str).eq("concluida").sum())
    minhas = int(filtered["minha_demanda"].astype(bool).sum())
    render_demandas_metrics(total, pendentes, concluidas, minhas)

    st.markdown('<div class="action-bar">', unsafe_allow_html=True)
    selected_ids = _render_demandas_grid_aggrid(
        filtered.rename(
            columns={
                "empresa": "Empresa",
                "demanda_display": "Demanda",
                "responsavel_display": "Responsável",
                "status_label": "Status",
                "tempo_display": "Tempo",
                "estrelas_visual": "Dificuldade",
                "observacao": "Observação",
                "concluida_em": "Concluída em",
                "concluida_por": "Concluída por",
                "bloqueio_display": "Bloqueio",
            }
        )
    )
    st.markdown("</div>", unsafe_allow_html=True)
    st.session_state["demandas_selected_ids"] = selected_ids

    selected_df = filtered[filtered["demanda_id"].astype(str).isin([str(value) for value in selected_ids])].copy()
    selected_count = len(selected_df)

    quick_action_left, quick_action_right = st.columns([1.15, 4.85], vertical_alignment="center")
    if quick_action_left.button("✅ Concluir selecionadas", use_container_width=True, type="primary", disabled=not selected_ids):
        applied, denied, blocked = _demandas_apply_batch(filtered, selected_ids, username, role, "concluir", observacao="")
        if applied:
            st.toast("✅ Demandas concluídas com sucesso")
        if denied:
            st.warning("Algumas demandas não foram alteradas porque pertencem a outro responsável.")
        if blocked:
            st.warning("Algumas demandas estão bloqueadas.")
        if applied:
            st.rerun()
    quick_action_right.markdown(
        f"<div class='muted-text' style='padding-top:0.45rem;'>Selecionadas: <strong>{selected_count}</strong>. As demais ações ficam no bloco recolhido abaixo.</div>",
        unsafe_allow_html=True,
    )

    with st.expander(f"Ações nas selecionadas ({selected_count})", expanded=False):
        action_left, action_center, action_right = st.columns([1.0, 1.0, 2.4], vertical_alignment="center")
        justification = action_center.text_input(
            "Justificativa para desmarcar",
            key="demandas_justificativa",
            placeholder="Explique por que está desmarcando.",
        )
        observation_text = action_right.text_area(
            "Observação para selecionadas",
            key="demandas_observacao_text",
            height=72,
            placeholder="Escreva uma observação curta para aplicar nas demandas selecionadas.",
        )
        if action_center.button("↩️ Desmarcar selecionadas", use_container_width=True):
            if not selected_ids:
                st.warning("Selecione ao menos uma demanda na tabela.")
            elif not justification.strip():
                st.error("Explique por que está desmarcando.")
            else:
                applied, denied, blocked = _demandas_apply_batch(
                    filtered,
                    selected_ids,
                    username,
                    role,
                    "desmarcar",
                    observacao=observation_text,
                    justificativa=justification,
                )
                if applied:
                    st.toast("↩️ Demandas desmarcadas com sucesso")
                if denied:
                    st.warning("Algumas demandas não foram alteradas porque pertencem a outro responsável.")
                if blocked:
                    st.warning("Algumas demandas estão bloqueadas.")
                if applied:
                    st.session_state["demandas_justificativa"] = ""
                    st.rerun()
        if action_right.button("▶️ Marcar em andamento", use_container_width=True):
            if not selected_ids:
                st.warning("Selecione ao menos uma demanda na tabela.")
            else:
                applied, denied, blocked = _demandas_apply_batch(
                    filtered,
                    selected_ids,
                    username,
                    role,
                    "em_andamento",
                    observacao=observation_text,
                )
                if applied:
                    st.toast("▶️ Demandas marcadas como em andamento")
                if denied:
                    st.warning("Algumas demandas não foram alteradas porque pertencem a outro responsável.")
                if blocked:
                    st.warning("Algumas demandas estão bloqueadas.")
                if applied:
                    st.rerun()
        if action_right.button("Salvar observacoes", use_container_width=True):
            if not selected_ids:
                st.warning("Selecione ao menos uma demanda na tabela.")
            elif not observation_text.strip():
                st.error("Informe uma observação para aplicar.")
            else:
                applied, denied, blocked = _demandas_apply_batch(
                    filtered,
                    selected_ids,
                    username,
                    role,
                    "observacao",
                    observacao=observation_text,
                )
                if applied:
                    st.toast("Observacoes aplicadas com sucesso")
                if denied:
                    st.warning("Algumas demandas não foram alteradas porque pertencem a outro responsável.")
                if blocked:
                    st.warning("Algumas demandas estão bloqueadas.")
                if applied:
                    st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    _render_selected_demand_panel(filtered, selected_ids)


ACTIVE_PAGES = {
    "Home": {"label": "Home", "renderer": render_home},
    "Empresas": {"label": "Empresas", "renderer": render_empresas},
    "Demandas": {"label": "📋 Demandas", "renderer": render_demandas},
}


def main() -> None:
    inject_professional_ui_css()
    if not st.session_state.get("usuario"):
        login_screen()
        return

    start_marcacoes_background_sync()
    metadata = load_metadata_web()
    competencia = sidebar(metadata)
    page = resolve_start_page()
    render_topbar(competencia)
    renderer = ACTIVE_PAGES[page]["renderer"]
    if page == "Home":
        renderer()
    elif page == "Empresas":
        empresas = load_empresas_web()
        renderer(empresas)
    elif page == "Demandas":
        empresas = load_empresas_web()
        demandas = load_demandas_web()
        renderer(empresas, demandas, competencia)


if __name__ == "__main__":
    main()

