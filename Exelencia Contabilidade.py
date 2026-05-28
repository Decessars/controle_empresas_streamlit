# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import zipfile
from datetime import date, datetime
from pathlib import Path
import tomllib

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "cnpjs.db"
DB_PATH = Path(os.getenv("CONTROLE_EMPRESAS_DB", str(DEFAULT_DB_PATH))).expanduser()
AUTH_EXPORT_PATH = APP_DIR / "usuarios_senhas.txt"
_ENGINE = None

DEMAND_TYPES = [
    ("EXEC_FOLHA", "Execução da Folha de Pagamento"),
    ("ENV_CONTRACHEQUES", "Envio de Contracheques"),
    ("GUIA_INSS", "Geração/Envio Guia INSS"),
    ("GUIA_FGTS", "Geração/Envio Guia FGTS"),
    ("GUIA_FGTS_PARC", "Parc FGTS"),
    ("PEDIR_INFOS", "Pedir Informações ao Cliente"),
    ("APUR_ISS", "Apuração ISS"),
    ("APUR_SIMPLES", "Apuração do Simples Nacional"),
    ("GUIA_MEI", "Gerar/Enviar DAS-MEI"),
    ("ENV_PARC_SIMPLES", "Enviar Parcelamento do Simples/MEI"),
    ("REL_MEI", "Relatório Mensal do MEI"),
    ("GUIA_PREF", "Guia da Prefeitura"),
    ("REL_DEBITOS", "Relatório de Débitos"),
    ("CONS_ICMS_ST", "Consulta ICMS-ST (SEFAZ)"),
    ("PUXAR_NF_SAIDA", "Puxar NF de Saída (SEFAZ)"),
    ("EMISSAO_NF", "Emissão NF"),
    ("COBRAR_HONORARIOS", "Cobrar Honorários"),
    ("PARC_MENSAL", "Parcelamento Mensal (impostos)"),
    ("PARC_IMPOSTOS", "Parcelamento de Impostos (outro)"),
    ("DEFIS", "DEFIS"),
    ("OUTRA", "Outra Demanda"),
]

DEMAND_LABELS = dict(DEMAND_TYPES)
REGIMES = ["Simples Nacional", "MEI", "Lucro Presumido", "Lucro Real", "Imune/Isenta", "Outro"]

MODULES = [
    {
        "title": "Cadastro de Clientes",
        "desc": "Tela moderna para visualizar todos os clientes e editar cadastro com agilidade.",
        "tag": "CADASTRO",
        "icon": "◎",
        "enabled": True,
        "page": "Empresas",
    },
    {
        "title": "Demandas Mensais",
        "desc": "Checklist operacional por competência com marcação rápida.",
        "tag": "NOVO",
        "icon": "◈",
        "enabled": True,
        "page": "Demandas",
    },
    {
        "title": "Automação",
        "desc": "Painel com ações fiscais rápidas e atalhos para rotinas operacionais.",
        "tag": "NOVO",
        "icon": "◌",
        "enabled": True,
        "page": "Automação",
    },
    {
        "title": "Controle de Faturamento",
        "desc": "Lançamento manual mensal do faturamento MEI com alerta de limite anual.",
        "tag": "MEI",
        "icon": "◍",
        "enabled": False,
        "page": "Faturamento MEI",
    },
    {
        "title": "Relatórios Inteligentes",
        "desc": "Slot reservado para insights e exportações avançadas.",
        "tag": "EM BREVE",
        "icon": "◌",
        "enabled": False,
        "page": "Relatórios",
    },
    {
        "title": "Painel de Controle 2026",
        "desc": "Abrir o sistema principal de empresas, demandas e operações.",
        "tag": "PRINCIPAL",
        "icon": "◉",
        "enabled": True,
        "featured": True,
        "page": "Painel",
    },
]


def apply_nexus_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --nexus-bg: #f4f7fb;
            --nexus-surface: #ffffff;
            --nexus-surface-2: #eef2ff;
            --nexus-border: #d6deea;
            --nexus-primary: #5b21b6;
            --nexus-accent: #7c3aed;
            --nexus-text: #0f172a;
            --nexus-muted: #475569;
            --nexus-danger: #dc2626;
            --nexus-ok: #059669;
            --nexus-warn: #d97706;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(124,58,237,.10), transparent 34%),
                radial-gradient(circle at top right, rgba(37,99,235,.08), transparent 30%),
                linear-gradient(180deg, #f8fbff 0%, #f4f7fb 38%, #eef3f9 100%);
            background-size: auto;
            color: var(--nexus-text);
        }
        header[data-testid="stHeader"] {
            background: rgba(244,247,251,.94) !important;
            height: 0 !important;
            backdrop-filter: blur(10px);
        }
        [data-testid="stDecoration"] {
            display: none !important;
        }
        .block-container {
            padding-top: 0.6rem;
            max-width: 1280px;
        }
        h1 {
            margin-bottom: 0.45rem !important;
        }
        h2, h3 {
            margin-bottom: 0.35rem !important;
        }
        div[data-testid="stCaptionContainer"] {
            margin-top: 0.1rem !important;
            margin-bottom: 0.15rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            margin-bottom: 0.65rem !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            padding-top: 0.45rem !important;
            padding-bottom: 0.45rem !important;
        }
        section[data-testid="stSidebar"] {
            width: 16rem !important;
            min-width: 16rem !important;
            max-width: 16rem !important;
        }
        section[data-testid="stSidebar"] {
            background:
                linear-gradient(135deg, rgba(91,33,182,.05) 0 1px, transparent 1px 18px),
                #f8fbff;
            background-size: 18px 18px, auto;
            border-right: 1px solid var(--nexus-border);
        }
        section[data-testid="stSidebar"] * {
            color: var(--nexus-text) !important;
            opacity: 1 !important;
        }
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] span {
            color: var(--nexus-text) !important;
            opacity: 1 !important;
        }
        section[data-testid="stSidebar"] small,
        section[data-testid="stSidebar"] .stCaptionContainer {
            color: var(--nexus-muted) !important;
            opacity: 1 !important;
        }
        h1, h2, h3 {
            color: var(--nexus-text) !important;
            letter-spacing: 0;
        }
        h1 {
            font-size: 2rem !important;
            line-height: 1.1 !important;
        }
        h2 {
            font-size: 1.35rem !important;
            line-height: 1.15 !important;
        }
        h3 {
            font-size: 1.1rem !important;
            line-height: 1.15 !important;
        }
        p, label, span, div {
            letter-spacing: 0;
        }
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,.92);
            border: 1px solid var(--nexus-border);
            border-radius: 12px;
            padding: 10px 14px;
            box-shadow: 0 14px 28px rgba(15,23,42,.08);
        }
        div[data-testid="stMetric"] label, div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: var(--nexus-text) !important;
        }
        div[data-testid="stDataFrame"], div[data-testid="stForm"], div[data-testid="stExpander"] {
            border-radius: 12px;
        }
        div[data-testid="stExpander"] {
            margin-bottom: 0.6rem !important;
        }
        div[data-testid="stExpander"] summary {
            padding-top: 0.35rem !important;
            padding-bottom: 0.35rem !important;
        }
        div[data-testid="stExpander"] div[role="button"] {
            min-height: 2rem !important;
        }
        .stButton > button, .stDownloadButton > button, div[data-testid="stFormSubmitButton"] button {
            background: var(--nexus-primary);
            color: white;
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 10px;
            font-weight: 700;
            box-shadow: 0 10px 24px rgba(86,0,178,.22);
        }
        .stButton > button:hover, .stDownloadButton > button:hover, div[data-testid="stFormSubmitButton"] button:hover {
            background: var(--nexus-accent);
            color: white;
            border-color: rgba(255,255,255,.20);
        }
        input, textarea, select {
            background-color: #ffffff !important;
            color: var(--nexus-text) !important;
            border-color: var(--nexus-border) !important;
            border-radius: 10px !important;
        }
        div[data-baseweb="select"] * {
            color: var(--nexus-text) !important;
        }
        div[data-testid="stDataFrame"] {
            background: #ffffff;
            color: #0f172a;
            border: 1px solid var(--nexus-border);
        }
        div[data-testid="stDataFrame"] * {
            color: #0f172a;
        }
        div[data-testid="stAlert"] {
            color: #0f172a;
        }
        div[data-testid="stAlert"] * {
            color: #0f172a !important;
        }
        div[data-testid="stFileUploader"] section {
            background: #ffffff;
            color: #0f172a;
            border-radius: 10px;
        }
        div[data-testid="stFileUploader"] section * {
            color: #0f172a !important;
        }
        div[data-testid="stSidebar"] .stButton > button,
        div[data-testid="stSidebar"] .stLinkButton > a {
            background: #5b21b6 !important;
            color: #ffffff !important;
            border: 1px solid #7c3aed !important;
            font-weight: 800 !important;
            box-shadow: 0 10px 22px rgba(86, 0, 178, .26) !important;
        }
        div[data-testid="stSidebar"] .stButton > button *,
        div[data-testid="stSidebar"] .stLinkButton > a * {
            color: #ffffff !important;
            opacity: 1 !important;
        }
        div[data-testid="stSidebar"] .stButton > button:hover,
        div[data-testid="stSidebar"] .stLinkButton > a:hover {
            background: #7c3aed !important;
        }
        section[data-testid="stSidebar"] a[href="http://localhost:8501/"] {
            background: #5b21b6 !important;
            color: #ffffff !important;
            border: 1px solid #7c3aed !important;
        }
        section[data-testid="stSidebar"] a[href="http://localhost:8501/"] * {
            color: #ffffff !important;
        }
        div[data-testid="stSidebar"] input {
            background-color: #ffffff !important;
            color: var(--nexus-text) !important;
        }
        div[data-testid="stSidebar"] .stButton > button,
        div[data-testid="stSidebar"] .stLinkButton > a {
            min-height: 2.15rem !important;
            padding: 0.25rem 0.6rem !important;
            font-size: 0.92rem !important;
        }
        .top-action-row .stButton > button {
            width: 100% !important;
            min-height: 3.1rem !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .nexus-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 12px 16px;
            margin: 12px 0 20px;
            background: rgba(255,255,255,.90);
            border: 1px solid var(--nexus-border);
            border-radius: 12px;
            box-shadow: 0 10px 24px rgba(15,23,42,.06);
        }
        .login-brand {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 18px;
            color: var(--nexus-text);
            font-size: 13px;
            font-weight: 900;
            text-transform: uppercase;
        }
        .login-mark {
            width: 30px;
            height: 30px;
            display: inline-grid;
            place-items: center;
            border-radius: 8px;
            background: #5b21b6;
            color: #fff;
            box-shadow: 0 12px 24px rgba(86,0,178,.28);
        }
        .login-title {
            font-size: 30px;
            line-height: 1.1;
            font-weight: 900;
            color: var(--nexus-text);
            margin: 0 0 8px 0;
        }
        .login-subtitle {
            color: var(--nexus-muted);
            font-size: 14px;
            margin-bottom: 22px;
        }
        .st-key-login_card {
            width: min(460px, calc(100vw - 48px));
            margin: 7vh auto 0 auto;
            background: rgba(255,255,255,.92);
            border: 1px solid rgba(124,58,237,.18);
            border-radius: 14px;
            padding: 28px 28px 24px;
            box-shadow: 0 24px 70px rgba(15,23,42,.12);
        }
        .st-key-login_card div[data-testid="stForm"] {
            border: 0;
            padding: 0;
        }
        .st-key-login_card input {
            min-height: 42px;
        }
        .st-key-login_card .stButton > button,
        .st-key-login_card div[data-testid="stFormSubmitButton"] button {
            width: 100%;
            min-height: 42px;
        }
        .nexus-brand {
            font-size: 14px;
            font-weight: 900;
            text-transform: uppercase;
        }
        .nexus-brand span {
            color: #8b5cf6;
        }
        .nexus-local-link {
            color: #5b21b6 !important;
            text-decoration: none;
            font-weight: 700;
        }
        .nexus-module-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 12px;
            margin-top: 10px;
        }
        .nexus-module {
            display: block;
            background: rgba(255,255,255,.95);
            border: 1px solid var(--nexus-border);
            border-radius: 12px;
            padding: 14px;
            min-height: 120px;
            color: inherit;
            text-decoration: none;
            transition: transform .16s ease, border-color .16s ease, background .16s ease, box-shadow .16s ease;
        }
        a.nexus-module {
            cursor: pointer;
        }
        a.nexus-module:hover {
            transform: translateY(-2px);
            background: #ffffff;
            border-color: rgba(124,58,237,.48);
            box-shadow: 0 18px 34px rgba(15,23,42,.10), 0 0 0 1px rgba(124,58,237,.08) inset;
            text-decoration: none;
        }
        .nexus-module.disabled {
            cursor: default;
            opacity: .78;
        }
        .nexus-module strong {
            display: block;
            color: var(--nexus-text);
            margin-bottom: 4px;
        }
        .nexus-module small {
            color: var(--nexus-muted);
        }
        .nexus-status {
            display: inline-block;
            margin-top: 10px;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 800;
            text-transform: uppercase;
        }
        .nexus-status.ok {
            background: rgba(5,150,105,.10);
            color: var(--nexus-ok);
            border: 1px solid rgba(5,150,105,.22);
        }
        .nexus-status.pending {
            background: rgba(217,119,6,.10);
            color: var(--nexus-warn);
            border: 1px solid rgba(217,119,6,.22);
        }
        div[class*="st-key-module_btn_"] button {
            width: 100%;
            min-height: 116px;
            justify-content: flex-start;
            align-items: flex-start;
            text-align: left;
            white-space: pre-line;
            padding: 18px 18px 14px;
            background: #ffffff !important;
            border: 1px solid var(--nexus-border) !important;
            border-top: 4px solid #6aa0ff !important;
            border-radius: 12px !important;
            color: var(--nexus-text) !important;
            box-shadow: none;
            line-height: 1.45;
        }
        div[class*="st-key-module_btn_"] button p {
            color: var(--nexus-text) !important;
            font-weight: 700;
        }
        div[class*="st-key-module_btn_"] button:hover:not(:disabled) {
            transform: translateY(-1px);
            background: #f8fbff !important;
            border-color: #8bb6ff !important;
            box-shadow: 0 18px 34px rgba(15,23,42,.08), 0 0 0 1px rgba(139,182,255,.14) inset;
        }
        div[class*="st-key-module_btn_"] button:disabled {
            background: rgba(241,245,249,.92) !important;
            border-color: rgba(148,163,184,.28) !important;
            border-top-color: rgba(148,163,184,.28) !important;
            opacity: .90;
            cursor: default;
        }
        div[class*="st-key-module_btn_"] button:disabled p {
            color: #94a3b8 !important;
        }
        div[class*="st-key-module_btn_Painel_de_Controle_2026"] button {
            border-color: #6aa0ff !important;
            border-top-color: #6aa0ff !important;
        }
        .launcher-shell {
            max-width: 1160px;
            padding: 0 0 10px;
            background: transparent;
            border: 0;
            box-shadow: none;
        }
        .launcher-kicker {
            color: var(--nexus-muted);
            font-size: 12px;
            font-weight: 800;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        .launcher-title {
            color: var(--nexus-text);
            font-size: 28px;
            line-height: 1.1;
            font-weight: 900;
            margin-bottom: 6px;
        }
        .launcher-subtitle {
            color: var(--nexus-muted);
            font-size: 14px;
            margin-bottom: 10px;
        }
        .launcher-grid-wrap {
            max-width: 1160px;
        }
        .module-card {
            min-height: 146px;
            padding: 16px 16px 14px;
            margin-bottom: 16px;
            background: #ffffff;
            border: 1px solid var(--nexus-border);
            border-top: 4px solid #6aa0ff;
            box-shadow: 0 14px 30px rgba(15,23,42,.08);
        }
        .module-card.disabled {
            background: #f8fafc;
            border-color: rgba(148,163,184,.30);
            border-top-color: rgba(148,163,184,.30);
            box-shadow: none;
        }
        .module-head {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
        }
        .module-icon {
            width: 26px;
            height: 26px;
            display: inline-grid;
            place-items: center;
            background: #dbeafe;
            color: #1d4ed8;
            font-weight: 900;
        }
        .module-title {
            color: var(--nexus-text);
            font-size: 16px;
            font-weight: 900;
            flex: 1;
        }
        .module-tag {
            color: #0f172a;
            background: #6aa0ff;
            font-family: Consolas, monospace;
            font-size: 10px;
            font-weight: 900;
            padding: 4px 10px;
            text-transform: uppercase;
        }
        .module-card.disabled .module-icon,
        .module-card.disabled .module-tag {
            background: rgba(148,163,184,.18);
            color: #334155;
        }
        .module-card.disabled .module-title,
        .module-card.disabled .module-desc {
            color: var(--nexus-muted);
        }
        .module-desc {
            min-height: 40px;
            color: var(--nexus-muted);
            font-size: 13px;
            line-height: 1.45;
        }
        div[class*="st-key-access_module_"] button {
            min-height: 0;
            padding: 0 !important;
            background: transparent !important;
            border: 0 !important;
            color: #2563eb !important;
            box-shadow: none !important;
            font-family: "Bahnschrift", "Segoe UI", sans-serif;
            font-size: 12px;
            font-weight: 900;
            text-align: left;
        }
        div[class*="st-key-access_module_"] button p {
            color: #2563eb !important;
            font-weight: 900;
        }
        div[class*="st-key-access_module_"] button:hover p {
            color: #1d4ed8 !important;
        }
        div[class*="st-key-access_module_"],
        div[class*="st-key-disabled_module_"] {
            margin-top: -54px;
            margin-left: 16px;
            margin-bottom: 28px;
            width: fit-content;
        }
        div[class*="st-key-disabled_module_"] button {
            min-height: 0;
            padding: 0 !important;
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            cursor: default;
        }
        div[class*="st-key-disabled_module_"] button p {
            color: #94a3b8 !important;
            font-weight: 900;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_topbar() -> None:
    st.markdown(
        """
        <div class="nexus-topbar">
            <div class="nexus-brand">EXCELENCIA <span>CONTABILIDADE</span></div>
            <a class="nexus-local-link" href="http://localhost:8501/" target="_blank">🖥️ Local</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def current_competencia() -> str:
    today = date.today()
    return f"{today.year}-{today.month:02d}"


def get_setting(key: str, default: str = "") -> str:
    df = query_df("SELECT value FROM settings WHERE key=?", (key,))
    if df.empty:
        return default
    value = df.iloc[0].get("value", default)
    return default if value is None else str(value)


def set_setting(key: str, value: str) -> None:
    execute(
        """
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (key, str(value)),
    )


def parse_competencia(competencia: str) -> tuple[int, int]:
    try:
        year_str, month_str = competencia.split("-", 1)
        return int(year_str), int(month_str)
    except Exception:
        today = date.today()
        return today.year, today.month


def database_url() -> str:
    try:
        secrets_database = st.secrets.get("database", {})
        url = secrets_database.get("url", "") if hasattr(secrets_database, "get") else ""
        if url:
            return str(url)
    except Exception:
        pass
    return os.getenv("DATABASE_URL", "").strip()


def using_postgres() -> bool:
    return bool(database_url())


def db_label() -> str:
    if using_postgres():
        return "PostgreSQL online"
    return str(DB_PATH)


def db_exists() -> bool:
    return True if using_postgres() else DB_PATH.exists()


def get_engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(database_url(), pool_pre_ping=True)
    return _ENGINE


def get_sqlite_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def adapt_sql(sql: str, params: tuple = ()):
    if not using_postgres():
        return sql, params

    adapted = sql.replace(" COLLATE NOCASE", "")
    values: dict[str, object] = {}
    for idx, value in enumerate(params):
        key = f"p{idx}"
        adapted = adapted.replace("?", f":{key}", 1)
        values[key] = value
    return text(adapted), values


def execute(sql: str, params: tuple = ()) -> int:
    adapted_sql, adapted_params = adapt_sql(sql, params)
    if using_postgres():
        with get_engine().begin() as conn:
            result = conn.execute(adapted_sql, adapted_params)
            return max(result.rowcount or 0, 0)
    with get_sqlite_conn() as conn:
        cur = conn.execute(adapted_sql, adapted_params)
        return max(cur.rowcount or 0, 0)


def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    adapted_sql, adapted_params = adapt_sql(sql, params)
    if using_postgres():
        with get_engine().connect() as conn:
            return pd.read_sql_query(adapted_sql, conn, params=adapted_params)
    with get_sqlite_conn() as conn:
        return pd.read_sql_query(adapted_sql, conn, params=adapted_params)


def ensure_column(table: str, column: str, coltype: str, default: str = "NULL") -> None:
    if using_postgres():
        exists = query_df(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name=?
               AND column_name=?
             LIMIT 1
            """,
            (table, column),
        )
        if exists.empty:
            pg_type = {"INTEGER": "INTEGER", "TEXT": "TEXT", "REAL": "DOUBLE PRECISION"}.get(coltype, coltype)
            execute(f"ALTER TABLE {table} ADD COLUMN {column} {pg_type} DEFAULT {default}")
        return

    with get_sqlite_conn() as conn:
        cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype} DEFAULT {default}")


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if using_postgres():
        execute(
            """
            CREATE TABLE IF NOT EXISTS empresas (
                id SERIAL PRIMARY KEY,
                cnpj TEXT NOT NULL UNIQUE,
                razao_social TEXT NOT NULL,
                nome_fantasia TEXT,
                apelido TEXT,
                regime TEXT,
                is_ativo INTEGER DEFAULT 1,
                criado_em TEXT,
                atualizado_em TEXT
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS demandas (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER NOT NULL REFERENCES empresas(id),
                competencia TEXT NOT NULL,
                tipo TEXT NOT NULL,
                feito INTEGER DEFAULT 0,
                criado_em TEXT,
                atualizado_em TEXT,
                observacao TEXT DEFAULT '',
                UNIQUE (empresa_id, competencia, tipo)
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS faturamento_mei (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
                competencia TEXT NOT NULL,
                valor DOUBLE PRECISION NOT NULL DEFAULT 0,
                valor_nota_fiscal DOUBLE PRECISION DEFAULT 0,
                valor_mov_extrato DOUBLE PRECISION DEFAULT 0,
                observacao TEXT,
                criado_em TEXT,
                atualizado_em TEXT,
                UNIQUE (empresa_id, competencia)
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS historico_empresas (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER NOT NULL REFERENCES empresas(id),
                acao TEXT NOT NULL,
                usuario TEXT NOT NULL,
                resumo TEXT,
                snapshot_anterior TEXT,
                snapshot_atual TEXT,
                criado_em TEXT
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
    else:
        with get_sqlite_conn() as conn:
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS empresas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cnpj TEXT NOT NULL UNIQUE,
                razao_social TEXT NOT NULL,
                nome_fantasia TEXT,
                apelido TEXT,
                regime TEXT,
                is_ativo INTEGER DEFAULT 1,
                criado_em TEXT,
                atualizado_em TEXT
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS demandas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                competencia TEXT NOT NULL,
                tipo TEXT NOT NULL,
                feito INTEGER DEFAULT 0,
                criado_em TEXT,
                atualizado_em TEXT,
                observacao TEXT DEFAULT '',
                UNIQUE (empresa_id, competencia, tipo),
                FOREIGN KEY (empresa_id) REFERENCES empresas(id)
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS faturamento_mei (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                competencia TEXT NOT NULL,
                valor REAL NOT NULL DEFAULT 0,
                valor_nota_fiscal REAL DEFAULT 0,
                valor_mov_extrato REAL DEFAULT 0,
                observacao TEXT,
                criado_em TEXT,
                atualizado_em TEXT,
                UNIQUE (empresa_id, competencia),
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historico_empresas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                acao TEXT NOT NULL,
                usuario TEXT NOT NULL,
                resumo TEXT,
                snapshot_anterior TEXT,
                snapshot_atual TEXT,
                criado_em TEXT,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id)
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
            )
    ensure_column("empresas", "mensalidade", "TEXT")
    ensure_column("empresas", "cidade", "TEXT")
    ensure_column("empresas", "uf", "TEXT")
    ensure_column("empresas", "inativo", "INTEGER", "0")
    ensure_column("empresas", "funcionarios", "INTEGER", "0")
    ensure_column("empresas", "prolabore", "INTEGER", "0")
    ensure_column("empresas", "prefeitura_optante", "INTEGER", "0")
    ensure_column("empresas", "fgts_parc", "INTEGER", "0")
    ensure_column("demandas", "observacao", "TEXT", "''")


def demand_options() -> list[str]:
    return [f"{code} - {label}" for code, label in DEMAND_TYPES]


def option_to_code(option: str) -> str:
    return option.split(" - ", 1)[0].strip()


def show_table(
    df: pd.DataFrame,
    *,
    key: str,
    height: int = 420,
    editable: bool = False,
    column_config: dict | None = None,
    disabled: list[str] | bool = True,
    row_height: int = 30,
) -> pd.DataFrame:
    return st.data_editor(
        df,
        key=key,
        width="stretch",
        height=height,
        row_height=row_height,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=disabled if editable else True,
        column_config=column_config,
    )


def normalize_cnpj(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) != 14:
        return str(value or "").strip()
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def load_empresas(active_only: bool = True) -> pd.DataFrame:
    active_expr = "COALESCE(is_ativo, CASE WHEN COALESCE(inativo,0)=1 THEN 0 ELSE 1 END)"
    where = f"WHERE {active_expr}=1" if active_only else ""
    return query_df(
        f"""
        SELECT id, cnpj, razao_social, COALESCE(nome_fantasia,'') AS nome_fantasia,
               COALESCE(apelido,'') AS apelido, COALESCE(regime,'') AS regime,
               COALESCE(mensalidade,'') AS mensalidade, COALESCE(cidade,'') AS cidade,
               COALESCE(uf,'') AS uf, COALESCE(inativo,0) AS inativo,
               {active_expr} AS is_ativo, atualizado_em
        FROM empresas
        {where}
        ORDER BY razao_social COLLATE NOCASE
        """
    )


def save_empresa(data: dict, empresa_id: int | None = None) -> None:
    timestamp = now_str()
    is_ativo = 0 if int(data.get("inativo", 0)) else 1
    normalized = {
        "cnpj": normalize_cnpj(data["cnpj"]),
        "razao_social": data["razao_social"].strip(),
        "nome_fantasia": data.get("nome_fantasia", "").strip(),
        "apelido": data.get("apelido", "").strip(),
        "regime": data.get("regime", "").strip(),
        "mensalidade": data.get("mensalidade", "").strip(),
        "cidade": data.get("cidade", "").strip(),
        "uf": data.get("uf", "").strip().upper(),
        "inativo": int(data.get("inativo", 0)),
        "is_ativo": is_ativo,
        "timestamp": timestamp,
    }
    if empresa_id:
        before = empresa_snapshot(empresa_row(int(empresa_id)))
        execute(
            """
            UPDATE empresas
               SET cnpj=?, razao_social=?, nome_fantasia=?, apelido=?, regime=?,
                   mensalidade=?, cidade=?, uf=?, inativo=?, is_ativo=?, atualizado_em=?
             WHERE id=?
            """,
            (
                normalized["cnpj"],
                normalized["razao_social"],
                normalized["nome_fantasia"],
                normalized["apelido"],
                normalized["regime"],
                normalized["mensalidade"],
                normalized["cidade"],
                normalized["uf"],
                normalized["inativo"],
                normalized["is_ativo"],
                timestamp,
                int(empresa_id),
            ),
        )
        after = empresa_snapshot(empresa_row(int(empresa_id)))
        if before and after and any(str(before.get(key, "")) != str(after.get(key, "")) for key in ["cnpj", "razao_social", "nome_fantasia", "apelido", "regime", "mensalidade", "cidade", "uf", "inativo", "is_ativo"]):
            before_active = int(before.get("is_ativo", 1) or 1)
            after_active = int(after.get("is_ativo", 1) or 1)
            if before_active == 1 and after_active == 0:
                action = "EXCLUSAO"
            elif before_active == 0 and after_active == 1:
                action = "REATIVACAO"
            else:
                action = "ALTERACAO"
            record_empresa_history(int(empresa_id), action, before, after)
    else:
        execute(
            """
            INSERT INTO empresas
                (cnpj, razao_social, nome_fantasia, apelido, regime, mensalidade,
                 cidade, uf, inativo, is_ativo, criado_em, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["cnpj"],
                normalized["razao_social"],
                normalized["nome_fantasia"],
                normalized["apelido"],
                normalized["regime"],
                normalized["mensalidade"],
                normalized["cidade"],
                normalized["uf"],
                normalized["inativo"],
                normalized["is_ativo"],
                timestamp,
                timestamp,
            ),
        )
        created = empresa_snapshot(empresa_row_by_cnpj(normalized["cnpj"]))
        if created:
            record_empresa_history(int(created.get("id", 0) or 0), "INCLUSAO", {}, created)


def empresa_row_by_cnpj(cnpj: str) -> dict:
    df = query_df(
        """
        SELECT id, cnpj, razao_social, COALESCE(nome_fantasia,'') AS nome_fantasia,
               COALESCE(apelido,'') AS apelido, COALESCE(regime,'') AS regime,
               COALESCE(mensalidade,'') AS mensalidade, COALESCE(cidade,'') AS cidade,
               COALESCE(uf,'') AS uf, COALESCE(inativo,0) AS inativo,
               COALESCE(is_ativo, CASE WHEN COALESCE(inativo,0)=1 THEN 0 ELSE 1 END) AS is_ativo,
               atualizado_em, criado_em
          FROM empresas
         WHERE cnpj=?
         ORDER BY id DESC
         LIMIT 1
        """,
        (cnpj,),
    )
    return df.iloc[0].to_dict() if not df.empty else {}




def load_empresa_history(empresa_id: int) -> pd.DataFrame:
    return query_df(
        """
        SELECT id, empresa_id, acao, usuario, resumo, criado_em,
               snapshot_anterior, snapshot_atual
          FROM historico_empresas
         WHERE empresa_id=?
         ORDER BY id DESC
        """,
        (int(empresa_id),),
    )
def load_demandas(competencia: str) -> pd.DataFrame:
    df = query_df(
        """
        SELECT d.id, d.empresa_id, d.competencia, d.tipo, COALESCE(d.feito,0) AS feito,
               COALESCE(d.observacao,'') AS observacao, d.atualizado_em,
               e.razao_social, e.cnpj, COALESCE(e.apelido,'') AS apelido,
               COALESCE(e.regime,'') AS regime
          FROM demandas d
          JOIN empresas e ON e.id = d.empresa_id
         WHERE d.competencia=?
         ORDER BY d.tipo, e.razao_social COLLATE NOCASE
        """,
        (competencia,),
    )
    if not df.empty:
        df["demanda"] = df["tipo"].map(lambda code: DEMAND_LABELS.get(code, code))
        df["status"] = df["feito"].map(lambda v: "Concluída" if int(v or 0) else "Pendente")
    return df


def create_demandas(competencia: str, tipo: str, empresa_ids: list[int]) -> int:
    timestamp = now_str()
    created = 0
    for empresa_id in empresa_ids:
        created += execute(
            """
            INSERT INTO demandas (empresa_id, competencia, tipo, feito, criado_em, atualizado_em)
            VALUES (?, ?, ?, 0, ?, ?)
            ON CONFLICT(empresa_id, competencia, tipo) DO NOTHING
            """,
            (int(empresa_id), competencia, tipo, timestamp, timestamp),
        )
    return created


def update_demanda_status(demanda_id: int, feito: bool, observacao: str) -> None:
    execute(
        "UPDATE demandas SET feito=?, observacao=?, atualizado_em=? WHERE id=?",
        (1 if feito else 0, observacao, now_str(), int(demanda_id)),
    )


def delete_demanda(demanda_id: int) -> None:
    execute("DELETE FROM demandas WHERE id=?", (int(demanda_id),))


def render_setup() -> None:
    st.warning("Banco de dados ainda não encontrado para este projeto web.")
    uploaded = st.file_uploader("Enviar cnpjs.db", type=["db", "sqlite", "sqlite3"])
    if uploaded:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_DB_PATH.write_bytes(uploaded.getbuffer())
        st.success("Banco recebido. Recarregue a página para abrir o sistema.")
    if st.button("Criar banco vazio"):
        init_db()
        st.rerun()


def sync_auth_passwords_txt(users: dict[str, str]) -> None:
    lines = [
        "# Arquivo gerado automaticamente pelo app.",
        "# Nao versionar nem compartilhar.",
        "[auth.users]",
    ]
    for user in sorted(users):
        lines.append(f"{user} = {json.dumps(users[user], ensure_ascii=False)}")
    if not users:
        lines.append("# Nenhum usuario configurado.")

    content = "\n".join(lines) + "\n"
    try:
        if AUTH_EXPORT_PATH.exists():
            current = AUTH_EXPORT_PATH.read_text(encoding="utf-8")
            if current == content:
                return
        AUTH_EXPORT_PATH.write_text(content, encoding="utf-8")
    except Exception:
        pass


def load_auth_users_from_file() -> dict[str, str]:
    if not AUTH_EXPORT_PATH.exists():
        return {}
    try:
        data = tomllib.loads(AUTH_EXPORT_PATH.read_text(encoding="utf-8"))
        raw_users = data.get("auth", {}).get("users", {})
        return {str(k): str(v) for k, v in dict(raw_users).items()}
    except Exception:
        return {}


def configured_users() -> dict[str, str]:
    users: dict[str, str] = load_auth_users_from_file()
    try:
        secrets_auth = st.secrets.get("auth", {})
        raw_users = secrets_auth.get("users", {}) if hasattr(secrets_auth, "get") else {}
        users.update({str(k): str(v) for k, v in dict(raw_users).items()})
    except Exception:
        pass

    env_user = os.getenv("CONTROLE_EMPRESAS_USER")
    env_password = os.getenv("CONTROLE_EMPRESAS_PASSWORD")
    if env_user and env_password:
        users[str(env_user)] = str(env_password)
    sync_auth_passwords_txt(users)
    return users


def require_login() -> bool:
    users = configured_users()
    if not users:
        with st.container(border=True, key="login_card"):
            st.markdown(
                """
                <div class="login-brand"><span class="login-mark">E</span>Excelencia Contabilidade</div>
                <div class="login-title">Controle de Empresas</div>
                <div class="login-subtitle">Acesso bloqueado. Configure usuarios em secrets ou variaveis de ambiente para liberar o acesso.</div>
                """,
                unsafe_allow_html=True,
            )
            st.warning(
                "Defina pelo menos um usuario em `.streamlit/secrets.toml` no formato `[auth.users]` "
                "ou use `CONTROLE_EMPRESAS_USER` e `CONTROLE_EMPRESAS_PASSWORD`.",
            )
        return False

    if st.session_state.get("authenticated"):
        if "page_label" not in st.session_state:
            st.session_state["page_label"] = "🏠 Módulos"
        if "page" not in st.session_state:
            st.session_state["page"] = "Módulos"
        with st.sidebar:
            user = st.session_state.get("auth_user", "")
            if user:
                st.caption(f"👤 {user}")
            if st.button("🚪 Sair", help="Sair do sistema"):
                st.session_state.pop("authenticated", None)
                st.session_state.pop("auth_user", None)
                st.rerun()
        return True

    with st.container(border=True, key="login_card"):
        st.markdown(
            """
            <div class="login-brand"><span class="login-mark">E</span>Excelencia Contabilidade</div>
            <div class="login-title">Controle de Empresas</div>
            <div class="login-subtitle">Acesso restrito ao controle operacional.</div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            user = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
    if submitted:
        if users.get(user) == password:
            st.session_state["authenticated"] = True
            st.session_state["auth_user"] = user
            st.session_state["page_label"] = "🏠 Módulos"
            st.session_state["page"] = "Módulos"
            st.query_params["page"] = "Módulos"
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos.")
    return False


def render_sidebar() -> tuple[str, str]:
    menu_map = {
        "🏠 Módulos": "Módulos",
        "📊 Painel": "Painel",
        "➕ Novo Cliente": "Novo Cliente",
        "🏢 Empresas": "Empresas",
        "✅ Demandas": "Demandas",
        "⚙️ Automação": "Automação",
        "💰 Faturamento": "Faturamento MEI",
        "🧰 Backup": "Backup",
    }
    menu_items = list(menu_map.keys())
    requested_page = st.query_params.get("page", "Módulos")
    requested_label = next((label for label, page in menu_map.items() if page == requested_page), "🏠 Módulos")
    if requested_label not in menu_items:
        requested_label = st.session_state.get("page_label", "🏠 Módulos")
    if requested_label not in menu_items:
        requested_label = "🏠 Módulos"
    page_label = st.sidebar.radio("Menu", menu_items, index=menu_items.index(requested_label))
    page = menu_map[page_label]
    st.session_state["page_label"] = page_label
    st.session_state["page"] = page
    if st.query_params.get("page") != page:
        st.query_params["page"] = page
    saved_competencia = st.session_state.get("competencia") or get_setting("ultima_competencia", current_competencia())
    current_year, current_month = parse_competencia(saved_competencia)
    years = list(range(current_year - 5, current_year + 6))
    month_options = [f"{m:02d}" for m in range(1, 13)]
    y1, y2 = st.sidebar.columns(2)
    year = y1.selectbox("Ano", years, index=years.index(current_year))
    month = y2.selectbox("Mês", month_options, index=month_options.index(f"{current_month:02d}"))
    competencia = f"{int(year)}-{month}"
    st.session_state["competencia"] = competencia
    set_setting("ultima_competencia", competencia)
    return page, competencia


def render_modulos() -> None:
    st.markdown(
        """
        <div class="launcher-shell">
            <div class="launcher-kicker">●  Portal Principal • Seleção de Módulo</div>
            <div class="launcher-title">Acesso ao SISTEMA EXCELENCIA CONTABILIDADE</div>
            <div class="launcher-subtitle">Selecione o ambiente de trabalho para iniciar sua operação.</div>
        </div>
        <div class="launcher-grid-wrap">
        """,
        unsafe_allow_html=True,
    )
    for start in range(0, len(MODULES), 2):
        cols = st.columns(2)
        for idx, item in enumerate(MODULES[start:start + 2]):
            with cols[idx]:
                enabled = bool(item.get("enabled"))
                safe_key = str(item["title"]).replace(" ", "_").replace("/", "_")
                disabled_class = "" if enabled else " disabled"
                st.markdown(
                    f"""
                    <div class="module-card{disabled_class}">
                        <div class="module-head">
                            <span class="module-icon">{item['icon']}</span>
                            <span class="module-title">{item['title']}</span>
                            <span class="module-tag">{item['tag']}</span>
                        </div>
                        <div class="module-desc">{item['desc']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if enabled:
                    if st.button("Acessar módulo  >", key=f"access_module_{safe_key}"):
                        target = str(item["page"])
                        st.session_state["page"] = target
                        st.query_params["page"] = target
                        st.rerun()
                else:
                    st.button("Disponível em breve", key=f"disabled_module_{safe_key}", disabled=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_painel(competencia: str) -> None:
    empresas = load_empresas(active_only=False)
    demandas = load_demandas(competencia)
    faturamento_mei = query_df(
        """
        SELECT f.id, f.empresa_id, e.razao_social, f.competencia, f.valor,
               COALESCE(f.valor_nota_fiscal,0) AS valor_nota_fiscal,
               COALESCE(f.valor_mov_extrato,0) AS valor_mov_extrato,
               COALESCE(f.observacao,'') AS observacao
          FROM faturamento_mei f
          JOIN empresas e ON e.id=f.empresa_id
         WHERE f.competencia=?
         ORDER BY e.razao_social COLLATE NOCASE
        """,
        (competencia,),
    )

    total_empresas = len(empresas)
    empresas_ativas = int((empresas["is_ativo"] == 1).sum()) if not empresas.empty else 0
    empresas_inativas = int((empresas["is_ativo"] == 0).sum()) if not empresas.empty else 0
    total_demandas = len(demandas)
    concluidas = int((demandas["feito"] == 1).sum()) if not demandas.empty else 0
    pendentes = int((demandas["feito"] == 0).sum()) if not demandas.empty else 0
    receita_mei = float(faturamento_mei["valor"].fillna(0).sum()) if not faturamento_mei.empty else 0.0
    faturamento_nf = float(faturamento_mei["valor_nota_fiscal"].fillna(0).sum()) if not faturamento_mei.empty else 0.0
    faturamento_extrato = float(faturamento_mei["valor_mov_extrato"].fillna(0).sum()) if not faturamento_mei.empty else 0.0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Empresas", total_empresas)
    c2.metric("Ativas", empresas_ativas)
    c3.metric("Inativas", empresas_inativas)
    c4.metric("Demandas do mês", total_demandas)
    c5.metric("Concluídas", concluidas)
    c6.metric("Pendentes", pendentes)

    st.caption(f"Competência selecionada: {competencia}")

    if demandas.empty:
        st.info("Sem demandas para esta competência. O painel continua mostrando os demais indicadores do banco.")

    resumo = pd.DataFrame()
    if not demandas.empty:
        resumo = (
            demandas.groupby(["tipo", "demanda", "status"])
            .size()
            .reset_index(name="qtd")
            .sort_values(["tipo", "status"])
        )

    left, right = st.columns([1.1, 0.9])
    with left:
        st.subheader("Resumo por demanda")
        if resumo.empty:
            st.write("Sem dados para consolidar nesta competência.")
        else:
            resumo_chart = resumo.pivot_table(index="demanda", columns="status", values="qtd", aggfunc="sum", fill_value=0)
            st.bar_chart(resumo_chart)
            show_table(
                resumo[["demanda", "status", "qtd"]],
                key=f"painel_resumo_{competencia}",
                height=260,
                editable=False,
                disabled=True,
                column_config={
                    "demanda": st.column_config.TextColumn("Demanda", width=260),
                    "status": st.column_config.TextColumn("Status", width=120),
                    "qtd": st.column_config.NumberColumn("Qtd", width=80),
                },
            )
    with right:
        st.subheader("Faturamento MEI")
        mc1, mc2 = st.columns(2)
        mc1.metric("Total", f"R$ {receita_mei:,.2f}")
        mc2.metric("NF", f"R$ {faturamento_nf:,.2f}")
        st.metric("Extrato", f"R$ {faturamento_extrato:,.2f}")
        if faturamento_mei.empty:
            st.info("Sem faturamento MEI para esta competência.")
        else:
            st.dataframe(
                faturamento_mei[["razao_social", "valor", "valor_nota_fiscal", "valor_mov_extrato", "observacao"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "razao_social": st.column_config.TextColumn("Empresa", width=220),
                    "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                    "valor_nota_fiscal": st.column_config.NumberColumn("NF", format="R$ %.2f"),
                    "valor_mov_extrato": st.column_config.NumberColumn("Extrato", format="R$ %.2f"),
                    "observacao": st.column_config.TextColumn("Observação", width=180),
                },
            )

    c_left, c_right = st.columns([1.05, 0.95])
    with c_left:
        st.subheader("Pendências")
        pendentes_df = demandas[demandas["feito"] == 0][["demanda", "razao_social", "cnpj", "regime", "observacao"]] if not demandas.empty else demandas
        if pendentes_df.empty:
            st.success("Nenhuma pendência aberta nesta competência.")
        else:
            show_table(
                pendentes_df,
                key=f"painel_pendentes_{competencia}",
                height=320,
                editable=False,
                disabled=True,
                column_config={
                    "demanda": st.column_config.TextColumn("Demanda", width=220),
                    "razao_social": st.column_config.TextColumn("Razão social", width=300),
                    "cnpj": st.column_config.TextColumn("CNPJ", width=150),
                    "regime": st.column_config.TextColumn("Regime", width=120),
                    "observacao": st.column_config.TextColumn("Observação", width=260),
                },
            )

    with c_right:
        st.subheader("Leitura rápida")
        regime_counts = empresas[empresas["is_ativo"] == 1]["regime"].replace("", "Sem regime").value_counts().reset_index()
        regime_counts.columns = ["regime", "qtd"]
        if regime_counts.empty:
            st.info("Sem empresas ativas para resumir por regime.")
        else:
            st.bar_chart(regime_counts.set_index("regime"))

        if not demandas.empty:
            top_pendentes = (
                demandas[demandas["feito"] == 0]
                .groupby(["razao_social", "cnpj"])
                .size()
                .reset_index(name="pendencias")
                .sort_values(["pendencias", "razao_social"], ascending=[False, True])
                .head(8)
            )
            st.caption("Top clientes com pendências")
            if top_pendentes.empty:
                st.write("Sem pendências por cliente.")
            else:
                show_table(
                    top_pendentes,
                    key=f"painel_top_pendencias_{competencia}",
                    height=220,
                    editable=False,
                    disabled=True,
                    column_config={
                        "razao_social": st.column_config.TextColumn("Cliente", width=260),
                        "cnpj": st.column_config.TextColumn("CNPJ", width=150),
                        "pendencias": st.column_config.NumberColumn("Pendências", width=100),
                    },
                )

    if not demandas.empty:
        st.subheader("Últimas movimentações")
        ultimas = demandas.sort_values(["atualizado_em", "id"], ascending=[False, False]).head(12)
        show_table(
            ultimas[["demanda", "razao_social", "status", "atualizado_em", "observacao"]],
            key=f"painel_ultimas_{competencia}",
            height=260,
            editable=False,
            disabled=True,
            column_config={
                "demanda": st.column_config.TextColumn("Demanda", width=220),
                "razao_social": st.column_config.TextColumn("Razão social", width=280),
                "status": st.column_config.TextColumn("Status", width=110),
                "atualizado_em": st.column_config.TextColumn("Atualizado em", width=160),
                "observacao": st.column_config.TextColumn("Observação", width=240),
            },
        )


def render_empresas() -> None:
    st.markdown("**Empresas**")

    if "empresa_selected_id" not in st.session_state:
        st.session_state["empresa_selected_id"] = 0
    if "empresas_view_mode" not in st.session_state:
        st.session_state["empresas_view_mode"] = "ativas"

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([2.3, 1.2, 0.8, 0.8])
        search = c1.text_input("Buscar", value=st.session_state.get("empresa_search", ""), label_visibility="collapsed", placeholder="Buscar")
        regime_filter = c2.selectbox("Regime", ["Todos", *REGIMES], index=0, label_visibility="collapsed")
        if c3.button("Ativas"):
            st.session_state["empresas_view_mode"] = "ativas"
            st.rerun()
        if c4.button("Exclu?das"):
            st.session_state["empresas_view_mode"] = "excluidas"
            st.rerun()

    empresas = load_empresas(active_only=False)
    st.session_state["empresa_search"] = search
    filtered = empresas.copy()
    if search:
        q = search.strip().lower()
        mask = (
            filtered["cnpj"].astype(str).str.lower().str.contains(q, na=False)
            | filtered["razao_social"].astype(str).str.lower().str.contains(q, na=False)
            | filtered["nome_fantasia"].astype(str).str.lower().str.contains(q, na=False)
            | filtered["apelido"].astype(str).str.lower().str.contains(q, na=False)
        )
        filtered = filtered[mask]
    if regime_filter != "Todos":
        filtered = filtered[filtered["regime"] == regime_filter]
    if st.session_state["empresas_view_mode"] == "excluidas":
        filtered = filtered[filtered["is_ativo"] == 0]
    else:
        filtered = filtered[filtered["is_ativo"] == 1]

    display_df = filtered[["id", "cnpj", "razao_social", "nome_fantasia", "apelido", "regime", "mensalidade", "cidade", "uf"]].copy() if not filtered.empty else filtered
    editable_mode = st.session_state["empresas_view_mode"] != "excluidas"

    if editable_mode:
        save_col, _ = st.columns([0.18, 0.82])
        save_clicked = save_col.button("?? Salvar", use_container_width=True)
    else:
        save_clicked = False

    edited_df = show_table(
        display_df,
        key="empresas_editor",
        height=620,
        editable=editable_mode,
        disabled=["id"],
        column_config={
            "id": st.column_config.NumberColumn("id", width=60),
            "cnpj": st.column_config.TextColumn("cnpj", width=130),
            "razao_social": st.column_config.TextColumn("razao_social", width=240),
            "nome_fantasia": st.column_config.TextColumn("nome_fantasia", width=140),
            "apelido": st.column_config.TextColumn("apelido", width=120),
            "regime": st.column_config.SelectboxColumn("Regime", options=REGIMES, width=120),
            "mensalidade": st.column_config.TextColumn("mensalidade", width=100),
            "cidade": st.column_config.TextColumn("cidade", width=100),
            "uf": st.column_config.TextColumn("uf", width=50),
        },
    )

    if filtered.empty:
        st.info("Nenhuma empresa encontrada.")
        return

    if editable_mode and save_clicked:
        try:
            changed = 0
            original = display_df.set_index("id")
            for _, edited_row in edited_df.iterrows():
                empresa_id = int(edited_row["id"])
                if empresa_id not in original.index:
                    continue
                orig_row = original.loc[empresa_id]
                payload = {
                    "cnpj": str(edited_row.get("cnpj", "")),
                    "razao_social": str(edited_row.get("razao_social", "")),
                    "nome_fantasia": str(edited_row.get("nome_fantasia", "")),
                    "apelido": str(edited_row.get("apelido", "")),
                    "regime": str(edited_row.get("regime", "")),
                    "mensalidade": str(edited_row.get("mensalidade", "")),
                    "cidade": str(edited_row.get("cidade", "")),
                    "uf": str(edited_row.get("uf", "")),
                }
                if any(str(payload[key]) != str(orig_row[key]) for key in payload):
                    save_empresa(payload, empresa_id)
                    changed += 1
            st.success(f"Altera??es salvas. Registros atualizados: {changed}.")
            st.rerun()
        except Exception as exc:
            st.error(f"N?o foi poss?vel salvar as altera??es. Detalhe: {exc}")
    elif not editable_mode:
        st.caption("Exibindo somente empresas exclu?das.")

def render_novo_cliente() -> None:
    st.subheader("Novo cliente")
    st.caption("Preencha os campos abaixo para criar um novo cadastro.")

    with st.container(border=True):
        with st.form("novo_cliente_form"):
            c1, c2 = st.columns(2)
            cnpj = c1.text_input("CNPJ")
            razao = c2.text_input("Razão social")
            fantasia = c1.text_input("Nome fantasia")
            apelido = c2.text_input("Apelido")
            regime = c1.selectbox("Regime", REGIMES, index=0)
            mensalidade = c2.text_input("Mensalidade")
            cidade = c1.text_input("Cidade")
            uf = c2.text_input("UF", max_chars=2)
            inativo = st.checkbox("Inativa", value=False)
            csave, ccancel = st.columns(2)
            save_new = csave.form_submit_button("💾 Salvar novo")
            cancel_new = ccancel.form_submit_button("↩️ Voltar")

        if cancel_new:
            st.session_state["page"] = "Empresas"
            st.query_params["page"] = "Empresas"
            st.rerun()

        if save_new:
            if not cnpj or not razao:
                st.error("CNPJ e razão social são obrigatórios.")
            else:
                try:
                    save_empresa(
                        {
                            "cnpj": cnpj,
                            "razao_social": razao,
                            "nome_fantasia": fantasia,
                            "apelido": apelido,
                            "regime": regime,
                            "mensalidade": mensalidade,
                            "cidade": cidade,
                            "uf": uf,
                            "inativo": inativo,
                        },
                        None,
                    )
                    st.success("Novo cliente salvo.")
                    st.session_state["page"] = "Empresas"
                    st.query_params["page"] = "Empresas"
                    st.rerun()
                except Exception as exc:
                    st.error(f"Não foi possível salvar o novo cliente. Detalhe: {exc}")


def render_demandas(competencia: str) -> None:
    st.markdown("**Demandas**")
    empresas = load_empresas(active_only=True)
    if empresas.empty:
        st.info("Cadastre empresas antes de criar demandas.")
        return

    with st.expander("Criar demandas", expanded=False):
        c1, c2 = st.columns([1, 2])
        tipo_option = c1.selectbox("Tipo", demand_options())
        tipo = option_to_code(tipo_option)
        choices = empresas["id"].tolist()
        selected = c2.multiselect(
            "Empresas",
            choices,
            format_func=lambda eid: empresas.loc[empresas["id"] == eid, "razao_social"].iloc[0],
        )
        if st.button("Criar para selecionadas"):
            total = create_demandas(competencia, tipo, selected)
            st.success(f"Processado. Novos registros criados: {total}.")
            st.rerun()

    demandas = load_demandas(competencia)
    if demandas.empty:
        st.info("Sem demandas nesta compet?ncia.")
        return

    f1, f2 = st.columns(2)
    tipo_filter = f1.selectbox("Filtrar tipo", ["Todos", *[label for _, label in DEMAND_TYPES]])
    status_filter = f2.selectbox("Filtrar status", ["Todos", "Pendentes", "Conclu?das"])
    filtered = demandas.copy()
    if tipo_filter != "Todos":
        code = next(code for code, label in DEMAND_TYPES if label == tipo_filter)
        filtered = filtered[filtered["tipo"] == code]
    if status_filter == "Pendentes":
        filtered = filtered[filtered["feito"] == 0]
    elif status_filter == "Conclu?das":
        filtered = filtered[filtered["feito"] == 1]

    show_table(
        filtered[["id", "demanda", "razao_social", "cnpj", "status", "observacao", "atualizado_em"]],
        key=f"demandas_table_{competencia}_{tipo_filter}_{status_filter}",
        height=360,
        editable=False,
        disabled=True,
        column_config={
            "id": st.column_config.NumberColumn("id", width=60),
            "demanda": st.column_config.TextColumn("Demanda", width=220),
            "razao_social": st.column_config.TextColumn("Raz?o social", width=280),
            "cnpj": st.column_config.TextColumn("CNPJ", width=150),
            "status": st.column_config.TextColumn("Status", width=120),
            "observacao": st.column_config.TextColumn("Observa??o", width=250),
            "atualizado_em": st.column_config.TextColumn("Atualizado em", width=160),
        },
    )

def render_automacao() -> None:
    st.subheader("Automação")
    st.caption("Painel com ações fiscais rápidas e atalhos para rotinas operacionais.")

    actions = [
        ("Baixar Guias do MEI", "Use a Extensão: Baixar Guias_DMLS!"),
        ("Baixar NFe (Portal do Contribuinte)", "Rotina depende das credenciais e do fluxo do Portal do Contribuinte. A versão web será ligada ao mesmo cadastro de acessos."),
        ("Extrair XML", "Use a Extensão: Extrator XML (dmls)."),
        ("Analisar XML", "Selecione os XMLs na versão web para gerar uma análise simplificada."),
        ("Emitir Certidão Negativa", "Função em preparação para integração web."),
        ("Importar Pendências", "Função em preparação para integração web."),
        ("Relatório Fiscal", "Função em preparação para integração web."),
    ]

    for start in range(0, len(actions), 2):
        cols = st.columns(2)
        for idx, (label, message) in enumerate(actions[start:start + 2]):
            with cols[idx]:
                if st.button(label, key=f"auto_{label}"):
                    st.session_state["automacao_msg"] = message

    if st.session_state.get("automacao_msg"):
        st.info(st.session_state["automacao_msg"])

    with st.expander("Analisar XML na web", expanded=False):
        files = st.file_uploader("Selecionar XMLs", type=["xml"], accept_multiple_files=True)
        if files:
            rows = []
            for file in files:
                data = file.getvalue()
                rows.append({"arquivo": file.name, "tamanho_bytes": len(data)})
            show_table(
                pd.DataFrame(rows),
                key=f"leitura_fiscal_{len(rows)}",
                height=240,
                editable=False,
                disabled=True,
                column_config={
                    "arquivo": st.column_config.TextColumn("Arquivo", width=260),
                    "tamanho_bytes": st.column_config.NumberColumn("Tamanho (bytes)", width=140),
                },
            )
            st.warning("Leitura fiscal detalhada será conectada na próxima etapa para espelhar o relatório do desktop.")


def render_faturamento(competencia: str) -> None:
    st.subheader("Faturamento MEI")
    empresas = load_empresas(active_only=True)
    mei = empresas[empresas["regime"].str.upper() == "MEI"] if not empresas.empty else empresas
    if mei.empty:
        st.info("Nenhuma empresa MEI ativa encontrada.")
        return

    rows = query_df(
        """
        SELECT f.id, f.empresa_id, e.razao_social, f.competencia, f.valor,
               COALESCE(f.valor_nota_fiscal,0) AS valor_nota_fiscal,
               COALESCE(f.valor_mov_extrato,0) AS valor_mov_extrato,
               COALESCE(f.observacao,'') AS observacao
          FROM faturamento_mei f
          JOIN empresas e ON e.id=f.empresa_id
         WHERE f.competencia=?
         ORDER BY e.razao_social COLLATE NOCASE
        """,
        (competencia,),
    )
    show_table(
        rows,
        key=f"faturamento_table_{competencia}",
        height=260,
        editable=False,
        disabled=True,
        column_config={
            "id": st.column_config.NumberColumn("id", width=60),
            "empresa_id": st.column_config.NumberColumn("empresa_id", width=90),
            "razao_social": st.column_config.TextColumn("Razão social", width=260),
            "competencia": st.column_config.TextColumn("Competência", width=110),
            "valor": st.column_config.TextColumn("Valor", width=90),
            "valor_nota_fiscal": st.column_config.TextColumn("NF", width=90),
            "valor_mov_extrato": st.column_config.TextColumn("Extrato", width=90),
            "observacao": st.column_config.TextColumn("Observação", width=220),
        },
    )

    with st.form("faturamento_form"):
        empresa_id = st.selectbox(
            "Empresa MEI",
            mei["id"].tolist(),
            format_func=lambda eid: mei.loc[mei["id"] == eid, "razao_social"].iloc[0],
        )
        c1, c2, c3 = st.columns(3)
        valor = c1.number_input("Valor bruto", min_value=0.0, step=100.0, format="%.2f")
        valor_nf = c2.number_input("Notas fiscais", min_value=0.0, step=100.0, format="%.2f")
        valor_ext = c3.number_input("Movimento extrato", min_value=0.0, step=100.0, format="%.2f")
        observacao = st.text_area("Observação")
        submitted = st.form_submit_button("Salvar faturamento")
    if submitted:
        timestamp = now_str()
        execute(
            """
            INSERT INTO faturamento_mei
                (empresa_id, competencia, valor, valor_nota_fiscal, valor_mov_extrato,
                 observacao, criado_em, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(empresa_id, competencia) DO UPDATE SET
                valor=excluded.valor,
                valor_nota_fiscal=excluded.valor_nota_fiscal,
                valor_mov_extrato=excluded.valor_mov_extrato,
                observacao=excluded.observacao,
                atualizado_em=excluded.atualizado_em
            """,
            (empresa_id, competencia, valor, valor_nf, valor_ext, observacao, timestamp, timestamp),
        )
        st.success("Faturamento salvo.")
        st.rerun()


def render_backup() -> None:
    st.subheader("Backup e dados")
    st.write("Use esta tela para baixar uma cópia dos dados ou substituir a base SQLite local.")

    if using_postgres():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for table in ["empresas", "demandas", "historico_empresas", "faturamento_mei", "settings"]:
                df = query_df(f"SELECT * FROM {table}")
                zf.writestr(f"{table}.csv", df.to_csv(index=False).encode("utf-8-sig"))
        st.download_button(
            "Baixar backup CSV",
            data=buffer.getvalue(),
            file_name=f"controle_empresas_backup_{datetime.now():%Y%m%d_%H%M%S}.zip",
            mime="application/zip",
        )
        st.info("Em modo PostgreSQL, a substituição direta por arquivo .db fica desativada.")
        return

    if DB_PATH.exists():
        st.download_button(
            "Baixar cnpjs.db",
            data=DB_PATH.read_bytes(),
            file_name=f"cnpjs_backup_{datetime.now():%Y%m%d_%H%M%S}.db",
            mime="application/octet-stream",
        )

    uploaded = st.file_uploader("Substituir banco por outro cnpjs.db", type=["db", "sqlite", "sqlite3"])
    if uploaded and st.button("Confirmar substituição"):
        backup_path = DB_PATH.with_suffix(f".bak_{datetime.now():%Y%m%d_%H%M%S}.db")
        if DB_PATH.exists():
            shutil.copy2(DB_PATH, backup_path)
        DB_PATH.write_bytes(uploaded.getbuffer())
        st.success("Banco substituído. Recarregue a página.")


def main() -> None:
    st.set_page_config(page_title="Controle de Empresas", layout="wide", initial_sidebar_state="collapsed")
    apply_nexus_theme()

    if not require_login():
        return

    render_topbar()
    st.title("Controle de Empresas")

    init_db()
    if not db_exists():
        render_setup()
        return

    page, competencia = render_sidebar()

    if page == "Módulos":
        render_modulos()
    elif page == "Painel":
        render_painel(competencia)
    elif page == "Novo Cliente":
        render_novo_cliente()
    elif page == "Empresas":
        render_empresas()
    elif page == "Demandas":
        render_demandas(competencia)
    elif page == "Automação":
        render_automacao()
    elif page == "Faturamento MEI":
        render_faturamento(competencia)
    elif page == "Backup":
        render_backup()


if __name__ == "__main__":
    main()
