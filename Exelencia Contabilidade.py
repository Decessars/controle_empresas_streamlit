# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import os
import base64
import hashlib
import hmac
import secrets
import shutil
import sqlite3
import uuid
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import tomllib

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import create_engine, text

try:
    import extra_streamlit_components as esc
except Exception:  # pragma: no cover - optional dependency for cookie persistence
    esc = None


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "cnpjs.db"
DB_PATH = Path(os.getenv("CONTROLE_EMPRESAS_DB", str(DEFAULT_DB_PATH))).expanduser()
AUTH_EXPORT_PATH = APP_DIR / "usuarios_senhas.txt"
LOGO_PATH = APP_DIR / "logo.png"
AUTH_SESSION_TTL_SECONDS = 3600
AUTH_COOKIE_NAME = "ce_auth_token"
AUTH_SESSION_DEFAULT_PAGE = "Modulos"
AUTH_SESSION_DEFAULT_LABEL = "📂 Módulos"
SCHEMA_VERSION = "2026-05-30-04"
_ENGINE = None
_ENGINE_URL = None

USER_ROLES = {
    "admin_geral": "Administrador Geral",
    "contador": "Contador",
    "estagiario": "Estagiário",
    "usuario": "Usuário",
}

SPECIAL_USER_ROLES = {
    "DMLIMA": "admin_geral",
    "RAFAEL": "contador",
}

USER_MANAGEMENT_ALLOWED = {"DMLIMA", "RAFAEL"}
PASSWORD_MIN_LENGTH = 6
PBKDF2_ITERATIONS = 200_000

DEMAND_TYPES = [
    ("EXEC_FOLHA", "Execucao da Folha de Pagamento"),
    ("ENV_CONTRACHEQUES", "Envio de Contracheques"),
    ("GUIA_INSS", "Geracao/Envio Guia INSS"),
    ("GUIA_FGTS", "Geracao/Envio Guia FGTS"),
    ("GUIA_FGTS_PARC", "Parc FGTS"),
    ("PEDIR_INFOS", "Pedir Informacoes ao Cliente"),
    ("APUR_ISS", "Apuracao ISS"),
    ("APUR_SIMPLES", "Apuracao do Simples Nacional"),
    ("GUIA_MEI", "Gerar/Enviar DAS-MEI"),
    ("ENV_PARC_SIMPLES", "Enviar Parcelamento do Simples/MEI"),
    ("REL_MEI", "Relatorio Mensal do MEI"),
    ("GUIA_PREF", "Guia da Prefeitura"),
    ("REL_DEBITOS", "Relatorio de Debitos"),
    ("CONS_ICMS_ST", "Consulta ICMS-ST (SEFAZ)"),
    ("PUXAR_NF_SAIDA", "Puxar NF de Saida (SEFAZ)"),
    ("EMISSAO_NF", "Emissao NF"),
    ("COBRAR_HONORARIOS", "Cobrar Honorarios"),
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
        "icon": "C",
        "enabled": True,
        "page": "Empresas",
    },
    {
        "title": "Demandas Mensais",
        "desc": "Checklist operacional por competencia com marcacao rapida.",
        "tag": "NOVO",
        "icon": "D",
        "enabled": True,
        "page": "Demandas",
    },
    {
        "title": "Automacao",
        "desc": "Painel com acoes fiscais rapidas e atalhos para rotinas operacionais.",
        "tag": "NOVO",
        "icon": "A",
        "enabled": True,
        "page": "Automacao",
    },
    {
        "title": "Controle de Faturamento",
        "desc": "Lancamento manual mensal do faturamento MEI com alerta de limite anual.",
        "tag": "MEI",
        "icon": "F",
        "enabled": False,
        "page": "Faturamento",
    },
    {
        "title": "Relatorios Inteligentes",
        "desc": "Slot reservado para insights e exportacoes avancadas.",
        "tag": "EM BREVE",
        "icon": "R",
        "enabled": False,
        "page": "Relatorios",
    },
    {
        "title": "Painel de Controle 2026",
        "desc": "Abrir o sistema principal de empresas, demandas e operacoes.",
        "tag": "PRINCIPAL",
        "icon": "P",
        "enabled": True,
        "featured": True,
        "page": "Painel",
    },
]

NAV_MENU = {
    "📂 Módulos": "Modulos",
    "📊 Painel": "Painel",
    "👤 Novo Cliente": "Novo Cliente",
    "🏢 Empresas": "Empresas",
    "📋 Demandas": "Demandas",
    "🤖 Automação": "Automacao",
    "💰 Faturamento": "Faturamento",
    "💾 Backup": "Backup",
}

BUTTON_LABELS = {
    "ativas": "✅ Ativas",
    "excluidas": "🗑️ Excluídas",
    "importar": "📥 Importar",
    "exportar": "📤 Exportar",
    "incluir_cnpj": "➕ Incluir por CNPJ",
    "cadastro_on": "🔎 Cadastro On",
    "salvar": "💾 Salvar",
    "cancelar": "❌ Cancelar",
    "editar": "✏️ Editar",
    "excluir": "🗑️ Excluir",
    "atualizar": "🔄 Atualizar",
    "buscar": "🔎 Buscar",
    "limpar": "🧹 Limpar",
    "voltar": "⬅️ Voltar",
    "usuarios": "👥 Usuários",
    "backup": "💾 Backup",
    "demandas": "📋 Demandas",
    "faturamento": "💰 Faturamento",
    "automacao": "🤖 Automação",
}


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
            opacity: 1 !important;
            filter: none !important;
        }
        .stApp[aria-busy="true"],
        .stApp[aria-busy="true"] *,
        div[data-testid="stAppViewContainer"],
        div[data-testid="stAppViewContainer"] * {
            opacity: 1 !important;
            filter: none !important;
        }
        header[data-testid="stHeader"] {
            background-color: transparent !important;
        }
        div[data-testid="stToolbar"],
        .stDeployButton {
            display: none !important;
        }
        [data-testid="stDecoration"] {
            display: none !important;
        }
        .block-container {
            padding-top: 0.15rem;
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
            padding-top: 0.2rem !important;
            padding-bottom: 0.2rem !important;
        }
        section[data-testid="stSidebar"] .element-container {
            margin-bottom: 0.02rem !important;
        }
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
            margin-bottom: 0 !important;
        }
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        section[data-testid="stSidebar"] hr {
            margin: 0.12rem 0 !important;
        }
        section[data-testid="stSidebar"] {
            width: 16rem !important;
            min-width: 16rem !important;
            max-width: 16rem !important;
        }
        .sidebar-logo {
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 0 2px 2px 2px;
        }
        .sidebar-logo img {
            max-width: 76px !important;
            height: auto !important;
            object-fit: contain !important;
            display: block;
            margin: 0 auto 1px auto;
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
        .stButton > button[data-testid="stBaseButton-secondary"], 
        .stDownloadButton > button[data-testid="stBaseButton-secondary"] {
            background: #ffffff !important;
            color: var(--nexus-primary) !important;
            border: 1px solid var(--nexus-border) !important;
            box-shadow: 0 4px 12px rgba(15,23,42,.04) !important;
        }
        .stButton > button[data-testid="stBaseButton-secondary"]:hover, 
        .stDownloadButton > button[data-testid="stBaseButton-secondary"]:hover {
            background: rgba(91,33,182,.04) !important;
            color: var(--nexus-accent) !important;
            border-color: var(--nexus-primary) !important;
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
            min-height: 1.9rem !important;
            padding: 0.18rem 0.48rem !important;
            font-size: 0.88rem !important;
        }
        div[data-testid="stSidebar"] .stSelectbox,
        div[data-testid="stSidebar"] .stRadio {
            margin-bottom: 0.05rem !important;
        }
        div[data-testid="stSidebar"] [data-testid="stRadio"] {
            margin-top: 0.05rem !important;
            margin-bottom: 0.05rem !important;
        }
        div[data-testid="stSidebar"] [data-testid="stRadio"] label {
            margin-bottom: 0.02rem !important;
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
        .global-menu-panel {
            padding: 6px 4px 2px 4px;
        }
        .global-menu-panel .stButton > button {
            width: auto !important;
            min-width: 118px !important;
            max-width: 160px !important;
            min-height: 42px !important;
            padding: 0.35rem 0.55rem !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            justify-content: center !important;
            text-align: center !important;
            border-radius: 12px !important;
            box-sizing: border-box !important;
        }
        .global-menu-panel .stButton > button p {
            width: 100%;
            text-align: center !important;
        }
        .login-brand {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 14px;
            color: var(--nexus-text);
            font-size: 12px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .login-mark {
            width: 34px;
            height: 34px;
            display: inline-grid;
            place-items: center;
            border-radius: 10px;
            background: linear-gradient(135deg, #6d28d9 0%, #7c3aed 48%, #4f46e5 100%);
            color: #fff;
            box-shadow: 0 14px 28px rgba(91,33,182,.28);
        }
        .login-title {
            font-size: 28px;
            line-height: 1.06;
            font-weight: 900;
            color: var(--nexus-text);
            margin: 0 0 6px 0;
            letter-spacing: 0;
        }
        .login-subtitle {
            color: var(--nexus-muted);
            font-size: 13px;
            margin-bottom: 18px;
            max-width: 34ch;
        }
        .st-key-login_card,
        .st-key-login_card_secure {
            width: min(392px, calc(100vw - 32px));
            margin: 8vh auto 0 auto;
            background:
                linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(248,250,255,.98) 100%);
            border: 1px solid rgba(91,33,182,.18);
            outline: 1px solid rgba(91,33,182,.06);
            border-radius: 22px;
            padding: 20px 20px 18px;
            box-shadow:
                0 24px 60px rgba(15,23,42,.12),
                0 2px 0 rgba(255,255,255,.75) inset;
        }
        .st-key-login_card div[data-testid="stForm"],
        .st-key-login_card_secure div[data-testid="stForm"] {
            border: 0;
            padding: 0;
        }
        .st-key-login_card input,
        .st-key-login_card_secure input {
            min-height: 40px;
        }
        .st-key-login_card div[data-testid="stTextInputRootElement"],
        .st-key-login_card_secure div[data-testid="stTextInputRootElement"] {
            margin-bottom: 0.35rem;
            background: #ffffff !important;
            border: 1px solid rgba(91,33,182,.18) !important;
            border-radius: 12px !important;
            box-shadow: 0 1px 0 rgba(15,23,42,.03) inset;
            padding: 0.08rem 0.3rem !important;
        }
        .st-key-login_card div[data-testid="stTextInputRootElement"]:focus-within,
        .st-key-login_card_secure div[data-testid="stTextInputRootElement"]:focus-within {
            border-color: rgba(91,33,182,.58) !important;
            box-shadow: 0 0 0 3px rgba(91,33,182,.12) !important;
        }
        .st-key-login_card div[data-testid="stTextInputRootElement"] input,
        .st-key-login_card_secure div[data-testid="stTextInputRootElement"] input {
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            padding: 0.28rem 0.35rem !important;
            min-height: 30px !important;
        }
        .st-key-login_card label,
        .st-key-login_card_secure label {
            margin-bottom: 0.14rem !important;
            font-weight: 700 !important;
            color: var(--nexus-text) !important;
            font-size: 13px !important;
        }
        .st-key-login_card .stButton > button,
        .st-key-login_card div[data-testid="stFormSubmitButton"] button,
        .st-key-login_card_secure .stButton > button,
        .st-key-login_card_secure div[data-testid="stFormSubmitButton"] button {
            width: 100%;
            min-height: 42px;
            border-radius: 12px;
            border: 0;
            background: linear-gradient(135deg, #6d28d9 0%, #7c3aed 55%, #4f46e5 100%);
            color: #fff;
            box-shadow: 0 16px 28px rgba(91,33,182,.22);
            font-weight: 800;
            letter-spacing: 0.02em;
        }
        .st-key-login_card .stButton > button:hover,
        .st-key-login_card div[data-testid="stFormSubmitButton"] button:hover,
        .st-key-login_card_secure .stButton > button:hover,
        .st-key-login_card_secure div[data-testid="stFormSubmitButton"] button:hover {
            filter: brightness(1.03);
            transform: translateY(-1px);
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
            max-width: 920px;
        }
        .module-card {
            min-height: 132px;
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
        div[class*="st-key-module_open_"] button {
            min-height: 42px !important;
            padding: 0.4rem 0.85rem !important;
            border-radius: 10px !important;
            font-weight: 800 !important;
        }
        div[class*="st-key-module_disabled_"] button {
            min-height: 42px !important;
            padding: 0.4rem 0.85rem !important;
            border-radius: 10px !important;
            font-weight: 800 !important;
            cursor: default !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_company_logo(width: int = 86, location: str = "sidebar") -> None:
    if LOGO_PATH.exists():
        logo_bytes = LOGO_PATH.read_bytes()
        logo_b64 = base64.b64encode(logo_bytes).decode("ascii")
        st.markdown(
            f"""
            <div class="sidebar-logo">
                <img src="data:image/png;base64,{logo_b64}" alt="Excelencia Contabilidade" width="{width}" />
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="sidebar-logo"><div style="text-align:center; font-weight:800; letter-spacing:0.04em;">EXCELENCIA CONTABILIDADE</div></div>',
            unsafe_allow_html=True,
        )


def normalize_page(page: str) -> str:
    page_txt = str(page or "").strip()
    aliases = {
        "Automação": "Automacao",
        "Automacao": "Automacao",
        "Faturamento": "Faturamento MEI",
        "Faturamento MEI": "Faturamento MEI",
        "Módulos": "Modulos",
        "Modulos": "Modulos",
        "Painel de Controle 2026": "Painel",
    }
    return aliases.get(page_txt, page_txt)


def normalize_page(page: str) -> str:
    page_txt = str(page or "").strip()
    aliases = {
        "Automação": "Automacao",
        "AutomaÃ§Ã£o": "Automacao",
        "Automacao": "Automacao",
        "Faturamento": "Faturamento",
        "Faturamento MEI": "Faturamento",
        "Módulos": "Modulos",
        "MÃ³dulos": "Modulos",
        "Modulos": "Modulos",
        "Painel de Controle 2026": "Painel",
    }
    return aliases.get(page_txt, page_txt)


def render_topbar() -> None:
    if "global_menu_open" not in st.session_state:
        st.session_state["global_menu_open"] = False

    cols = st.columns([6.2, 1.0, 1.0, 1.2], vertical_alignment="center")
    cols[0].markdown(
        """
        <div class="nexus-topbar">
            <div class="nexus-brand">EXCELENCIA <span>CONTABILIDADE</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if cols[1].button("🏠 Home", key="topbar_home", use_container_width=True):
        navigate_to("Modulos", "📂 Módulos")
    if cols[2].button("⬅️ Voltar", key="topbar_back", use_container_width=True):
        go_back()
    if cols[3].button("\u2630 Menu", key="global_menu_toggle", use_container_width=True):
        st.session_state["global_menu_open"] = not st.session_state.get("global_menu_open", False)

    if st.session_state.get("global_menu_open", False):
        st.markdown('<div class="global-menu-panel">', unsafe_allow_html=True)
        with st.container(border=True):
            st.caption(f"Navegacao global - pagina atual: {st.session_state.get('page_label', '📂 Módulos')}")
            items = list(NAV_MENU.items())
            for start in range(0, len(items), 4):
                row = items[start:start + 4]
                row_cols = st.columns(len(row))
                for idx, (label, page) in enumerate(row):
                    button_type = "primary" if st.session_state.get("page") == page else "secondary"
                    with row_cols[idx]:
                        if st.button(label, key=f"global_menu_{page}", type=button_type, use_container_width=False):
                            st.session_state["global_menu_open"] = False
                            navigate_to(page, label)
        st.markdown("</div>", unsafe_allow_html=True)


def navigate_to(page: str, label: str | None = None, push_history: bool = True) -> None:
    page = normalize_page(page)
    current = str(st.session_state.get("page") or "").strip()
    if push_history and current and current != page:
        history = st.session_state.setdefault("nav_history", [])
        if not history or history[-1] != current:
            history.append(current)
        st.session_state["nav_history"] = history[-20:]
    if label is None:
        label = next((menu_label for menu_label, menu_page in NAV_MENU.items() if menu_page == page), page)
    st.session_state["page"] = page
    st.session_state["page_label"] = label
    st.session_state["menu_secure"] = label
    st.query_params["page"] = page
    st.rerun()


def set_navigation_target(page: str, label: str | None = None, push_history: bool = True) -> None:
    page = normalize_page(page)
    current = str(st.session_state.get("page") or "").strip()
    if push_history and current and current != page:
        history = st.session_state.setdefault("nav_history", [])
        if not history or history[-1] != current:
            history.append(current)
        st.session_state["nav_history"] = history[-20:]
    if label is None:
        label = next((menu_label for menu_label, menu_page in NAV_MENU.items() if menu_page == page), page)
    st.session_state["page"] = page
    st.session_state["page_label"] = label
    st.session_state["menu_secure"] = label
    st.query_params["page"] = page


def go_back() -> None:
    history = st.session_state.get("nav_history", [])
    if history:
        previous = history.pop()
        st.session_state["nav_history"] = history
        navigate_to(previous, next((menu_label for menu_label, menu_page in NAV_MENU.items() if menu_page == previous), previous), push_history=False)
    else:
        navigate_to("Modulos", "📂 Módulos", push_history=False)


def navigate_to_page(page: str, page_label: str | None = None) -> None:
    if page_label is None:
        page_label = next((label for label, value in NAV_MENU.items() if value == page), page)
    navigate_to(page, page_label)


def normalize_username(value: str) -> str:
    return str(value or "").strip().upper()


def current_username() -> str:
    return normalize_username(
        st.session_state.get("username")
        or st.session_state.get("auth_user")
        or st.session_state.get("user")
        or ""
    )


def current_user_role() -> str:
    return str(st.session_state.get("user_role") or "").strip() or "usuario"


def current_user_display_name() -> str:
    value = str(st.session_state.get("user_name") or "").strip()
    return value or current_username() or "sistema"


def user_role_label(role: str) -> str:
    return USER_ROLES.get(str(role or "").strip(), str(role or "").strip() or "Usuário")


def is_admin_geral() -> bool:
    return current_username() == "DMLIMA" or current_user_role() == "admin_geral"


def is_contador() -> bool:
    return current_username() == "RAFAEL" or current_user_role() in {"contador", "admin_geral"}


def can_manage_users() -> bool:
    return current_username() in USER_MANAGEMENT_ALLOWED or is_admin_geral()


def can_access_users_page() -> bool:
    return can_manage_users()


def can_manage_user(target_user) -> bool:
    if is_admin_geral():
        return True
    if not is_contador():
        return False
    target = target_user
    if isinstance(target_user, pd.Series):
        target = target_user.to_dict()
    if isinstance(target, dict):
        target_username = normalize_username(target.get("username"))
        target_role = str(target.get("role") or "usuario").strip() or "usuario"
        responsavel = normalize_username(target.get("responsavel"))
        criado_por = normalize_username(target.get("criado_por"))
    else:
        target_username = normalize_username(target)
        target_role = "usuario"
        responsavel = ""
        criado_por = ""
    if target_username in {"DMLIMA"}:
        return False
    if target_role in {"admin_geral", "contador"} and target_username != "RAFAEL":
        return False
    if target_username == "RAFAEL":
        return True
    return current_username() in {responsavel, criado_por}


def hash_password(password: str) -> str:
    raw_password = str(password or "")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        raw_password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, senha_hash: str) -> bool:
    raw_hash = str(senha_hash or "").strip()
    if not raw_hash or "$" not in raw_hash:
        return False
    try:
        algorithm, iterations, salt_hex, digest_hex = raw_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            str(password or "").encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def load_legacy_auth_users() -> dict[str, str]:
    users: dict[str, str] = {}
    if AUTH_EXPORT_PATH.exists():
        try:
            data = tomllib.loads(AUTH_EXPORT_PATH.read_text(encoding="utf-8"))
            raw_users = data.get("auth", {}).get("users", {})
            users.update({normalize_username(k): str(v) for k, v in dict(raw_users).items()})
        except Exception:
            pass
    try:
        secrets_auth = st.secrets.get("auth", {})
        raw_users = secrets_auth.get("users", {}) if hasattr(secrets_auth, "get") else {}
        users.update({normalize_username(k): str(v) for k, v in dict(raw_users).items()})
    except Exception:
        pass
    env_user = normalize_username(os.getenv("CONTROLE_EMPRESAS_USER"))
    env_password = os.getenv("CONTROLE_EMPRESAS_PASSWORD")
    if env_user and env_password:
        users[env_user] = str(env_password)
    return users


def configured_users() -> dict[str, str]:
    return load_legacy_auth_users()


def user_role_for(username: str, default_role: str = "usuario") -> str:
    username_norm = normalize_username(username)
    if username_norm in SPECIAL_USER_ROLES:
        return SPECIAL_USER_ROLES[username_norm]
    role = str(default_role or "usuario").strip()
    return role if role in USER_ROLES else "usuario"


def user_display_name_for(username: str, stored_name: str = "") -> str:
    name = str(stored_name or "").strip()
    return name or normalize_username(username) or "Usuário"


def get_user_row(username: str):
    username_norm = normalize_username(username)
    if not username_norm:
        return None
    df = query_df("SELECT * FROM users WHERE UPPER(username)=UPPER(?) LIMIT 1", (username_norm,))
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def get_users_df() -> pd.DataFrame:
    return query_df(
        """
        SELECT id, username, COALESCE(nome,'') AS nome, COALESCE(role,'usuario') AS role,
               COALESCE(ativo,1) AS ativo, COALESCE(responsavel,'') AS responsavel,
               COALESCE(criado_por,'') AS criado_por, COALESCE(criado_em,'') AS criado_em,
               COALESCE(atualizado_em,'') AS atualizado_em, COALESCE(ultimo_login,'') AS ultimo_login,
               COALESCE(observacao,'') AS observacao
          FROM users
         ORDER BY username COLLATE NOCASE
        """
    )


def get_visible_users_df() -> pd.DataFrame:
    df = get_users_df()
    if df.empty:
        return df
    if is_admin_geral():
        return df
    if current_username() == "RAFAEL":
        mask = (
            df["username"].astype(str).str.upper().eq("RAFAEL")
            | df["responsavel"].astype(str).str.upper().eq("RAFAEL")
            | df["criado_por"].astype(str).str.upper().eq("RAFAEL")
        )
        return df.loc[mask].copy()
    return df.iloc[0:0].copy()


def active_admin_count() -> int:
    df = query_df(
        """
        SELECT COUNT(*) AS total
          FROM users
         WHERE COALESCE(ativo,1)=1
           AND COALESCE(role,'usuario')='admin_geral'
        """
    )
    if df.empty:
        return 0
    return int(df.iloc[0]["total"] or 0)


def can_disable_user_record(target: dict) -> bool:
    username_norm = normalize_username(target.get("username"))
    role = str(target.get("role") or "usuario")
    ativo = int(target.get("ativo") or 0)
    if ativo == 0:
        return True
    if username_norm == "DMLIMA" and active_admin_count() <= 1:
        return False
    if role == "admin_geral" and active_admin_count() <= 1:
        return False
    return True


def upsert_user_record(
    *,
    username: str,
    nome: str,
    senha_hash: str,
    role: str,
    ativo: int = 1,
    criado_por: str = "",
    responsavel: str = "",
    observacao: str = "",
    criado_em: str | None = None,
    atualizado_em: str | None = None,
    ultimo_login: str | None = None,
) -> None:
    username_norm = normalize_username(username)
    role_norm = user_role_for(username_norm, role)
    responsavel_norm = normalize_username(responsavel) or username_norm
    criado_por_norm = normalize_username(criado_por)
    timestamp = now_str()
    created_at = criado_em or timestamp
    updated_at = atualizado_em or timestamp
    execute(
        """
        INSERT INTO users (username, nome, senha_hash, role, ativo, criado_por, responsavel, observacao, criado_em, atualizado_em, ultimo_login)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            nome=excluded.nome,
            senha_hash=COALESCE(NULLIF(excluded.senha_hash,''), users.senha_hash),
            role=excluded.role,
            ativo=excluded.ativo,
            criado_por=COALESCE(NULLIF(excluded.criado_por,''), users.criado_por),
            responsavel=COALESCE(NULLIF(excluded.responsavel,''), users.responsavel),
            observacao=excluded.observacao,
            criado_em=COALESCE(users.criado_em, excluded.criado_em),
            atualizado_em=excluded.atualizado_em,
            ultimo_login=COALESCE(NULLIF(excluded.ultimo_login,''), users.ultimo_login)
        """,
        (
            username_norm,
            str(nome or "").strip() or username_norm,
            str(senha_hash or "").strip(),
            role_norm,
            int(1 if ativo else 0),
            criado_por_norm,
            responsavel_norm,
            str(observacao or "").strip(),
            created_at,
            updated_at,
            str(ultimo_login or "").strip(),
        ),
    )


def ensure_user_schema() -> None:
    if using_postgres():
        execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                nome TEXT,
                senha_hash TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'usuario',
                ativo INTEGER DEFAULT 1,
                criado_em TEXT,
                atualizado_em TEXT,
                criado_por TEXT,
                responsavel TEXT,
                observacao TEXT,
                ultimo_login TEXT
            )
            """
        )
    else:
        with get_sqlite_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    nome TEXT,
                    senha_hash TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'usuario',
                    ativo INTEGER DEFAULT 1,
                    criado_em TEXT,
                    atualizado_em TEXT,
                    criado_por TEXT,
                    responsavel TEXT,
                    observacao TEXT,
                    ultimo_login TEXT
                )
                """
            )
    ensure_column("users", "nome", "TEXT")
    ensure_column("users", "senha_hash", "TEXT", "''")
    ensure_column("users", "role", "TEXT", "'usuario'")
    ensure_column("users", "ativo", "INTEGER", "1")
    ensure_column("users", "criado_em", "TEXT")
    ensure_column("users", "atualizado_em", "TEXT")
    ensure_column("users", "criado_por", "TEXT")
    ensure_column("users", "responsavel", "TEXT")
    ensure_column("users", "observacao", "TEXT")
    ensure_column("users", "ultimo_login", "TEXT")


def seed_default_users() -> None:
    legacy_users = load_legacy_auth_users()
    defaults = [
        ("DMLIMA", "admin_geral"),
        ("RAFAEL", "contador"),
    ]
    for username, role in defaults:
        existing = get_user_row(username)
        legacy_password = legacy_users.get(username, "")
        senha_hash = existing.get("senha_hash", "") if existing else ""
        if legacy_password and not senha_hash:
            senha_hash = hash_password(legacy_password)
        if existing:
            execute(
                """
                UPDATE users
                   SET nome=COALESCE(NULLIF(nome,''), ?),
                       senha_hash=COALESCE(NULLIF(?,''), senha_hash),
                       role=?,
                       ativo=1,
                       responsavel=?,
                       atualizado_em=?,
                       criado_por=COALESCE(NULLIF(criado_por,''), ?)
                 WHERE UPPER(username)=UPPER(?)
                """,
                (
                    username,
                    senha_hash,
                    role,
                    username,
                    now_str(),
                    username,
                    username,
                ),
            )
        else:
            upsert_user_record(
                username=username,
                nome=username,
                senha_hash=senha_hash,
                role=role,
                ativo=1,
                criado_por=username,
                responsavel=username,
                observacao="Usuário padrão do sistema.",
            )


def update_user_last_login(username: str) -> None:
    timestamp = now_str()
    execute(
        "UPDATE users SET ultimo_login=?, atualizado_em=? WHERE UPPER(username)=UPPER(?)",
        (timestamp, timestamp, normalize_username(username)),
    )


def set_authenticated_session(username: str, role: str, nome: str) -> None:
    username_norm = normalize_username(username)
    role_norm = user_role_for(username_norm, role)
    nome_final = user_display_name_for(username_norm, nome)
    st.session_state["authenticated"] = True
    st.session_state["is_authenticated"] = True
    st.session_state["auth_user"] = username_norm
    st.session_state["user"] = username_norm
    st.session_state["username"] = username_norm
    st.session_state["user_role"] = role_norm
    st.session_state["user_name"] = nome_final


def clear_authenticated_session_state() -> None:
    for key in [
        "authenticated",
        "is_authenticated",
        "auth_user",
        "user",
        "username",
        "user_role",
        "user_name",
        "page",
        "page_label",
        "session_id",
    ]:
        st.session_state.pop(key, None)


def _auth_cookie_manager():
    if esc is None:
        return None
    try:
        return esc.CookieManager(key="auth_cookie_mgr")
    except Exception:
        return None


def hash_auth_token(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _auth_now() -> datetime:
    return datetime.now()


def _auth_now_str() -> str:
    return _auth_now().strftime("%Y-%m-%d %H:%M:%S")


def _auth_expiry_str() -> str:
    return (_auth_now() + timedelta(seconds=AUTH_SESSION_TTL_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")


def _auth_cookie_secure_flag() -> bool:
    try:
        headers = getattr(st.context, "headers", None)
        proto = ""
        if headers is not None:
            proto = str(headers.get("X-Forwarded-Proto", "") or headers.get("x-forwarded-proto", "") or "")
        return proto.lower() == "https"
    except Exception:
        return False


def _request_header_value(*names: str) -> str:
    try:
        headers = getattr(st.context, "headers", None)
        if headers is None:
            return ""
        for name in names:
            value = headers.get(name)
            if value:
                return str(value)
    except Exception:
        pass
    return ""


def ensure_auth_sessions_table() -> None:
    if using_postgres():
        execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen TEXT,
                revoked INTEGER DEFAULT 0,
                user_agent TEXT,
                ip_hint TEXT
            )
            """
        )
    else:
        with get_sqlite_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen TEXT,
                    revoked INTEGER DEFAULT 0,
                    user_agent TEXT,
                    ip_hint TEXT
                )
                """
            )


def cleanup_expired_auth_sessions() -> None:
    ensure_auth_sessions_table()
    now_txt = _auth_now_str()
    execute(
        """
        DELETE FROM auth_sessions
         WHERE revoked=1 OR expires_at < ?
        """,
        (now_txt,),
    )


def create_auth_session(username: str) -> str:
    ensure_auth_sessions_table()
    cleanup_expired_auth_sessions()
    token = secrets.token_urlsafe(32)
    token_hash = hash_auth_token(token)
    username_norm = normalize_username(username)
    created_at = _auth_now_str()
    expires_at = _auth_expiry_str()
    user_agent = _request_header_value("User-Agent", "user-agent")
    ip_hint = _request_header_value("X-Forwarded-For", "x-forwarded-for", "X-Real-Ip", "x-real-ip")
    execute(
        """
        INSERT INTO auth_sessions (
            token_hash, username, created_at, expires_at, last_seen, revoked, user_agent, ip_hint
        )
        VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (token_hash, username_norm, created_at, expires_at, created_at, user_agent, ip_hint),
    )
    return token


def validate_auth_session(token: str) -> str | None:
    if not token:
        return None
    ensure_auth_sessions_table()
    cleanup_expired_auth_sessions()
    token_hash = hash_auth_token(token)
    df = query_df(
        """
        SELECT username, expires_at, revoked
          FROM auth_sessions
         WHERE token_hash=?
         LIMIT 1
        """,
        (token_hash,),
    )
    if df.empty:
        return None
    row = df.iloc[0]
    if int(row.get("revoked", 0) or 0) == 1:
        return None
    expires_at = str(row.get("expires_at") or "").strip()
    if not expires_at or expires_at < _auth_now_str():
        execute("UPDATE auth_sessions SET revoked=1 WHERE token_hash=?", (token_hash,))
        return None
    username = normalize_username(row.get("username", ""))
    execute(
        "UPDATE auth_sessions SET last_seen=? WHERE token_hash=?",
        (_auth_now_str(), token_hash),
    )
    return username or None


def revoke_auth_session(token: str) -> None:
    if not token:
        return
    ensure_auth_sessions_table()
    execute(
        "UPDATE auth_sessions SET revoked=1, last_seen=? WHERE token_hash=?",
        (_auth_now_str(), hash_auth_token(token)),
    )


def _get_auth_token_from_cookie() -> str:
    manager = _auth_cookie_manager()
    if manager is None:
        return ""
    try:
        value = manager.get(AUTH_COOKIE_NAME)
        return str(value or "").strip()
    except Exception:
        return ""


def _get_auth_token_from_query() -> str:
    try:
        return str(st.query_params.get("auth_token", "") or "").strip()
    except Exception:
        return ""


def _set_auth_token_cookie(token: str) -> None:
    manager = _auth_cookie_manager()
    if manager is None:
        return
    try:
        manager.set(
            AUTH_COOKIE_NAME,
            token,
            max_age=AUTH_SESSION_TTL_SECONDS,
            secure=_auth_cookie_secure_flag(),
            same_site="lax",
        )
    except Exception:
        pass


def _delete_auth_token_cookie() -> None:
    manager = _auth_cookie_manager()
    if manager is None:
        return
    try:
        manager.delete(AUTH_COOKIE_NAME)
    except Exception:
        pass


def _delete_query_param_auth_token() -> None:
    try:
        if "auth_token" in st.query_params:
            del st.query_params["auth_token"]
    except Exception:
        pass


def _set_auth_persistence(token: str) -> None:
    _set_auth_token_cookie(token)
    try:
        st.query_params["auth_token"] = token
    except Exception:
        pass


def _restore_persistent_auth_session() -> bool:
    if st.session_state.get("authenticated") or st.session_state.get("is_authenticated"):
        return False
    ensure_auth_sessions_table()
    token = _get_auth_token_from_cookie() or _get_auth_token_from_query()
    if not token:
        return False
    username = validate_auth_session(token)
    if not username:
        _delete_auth_token_cookie()
        _delete_query_param_auth_token()
        return False
    user_row = get_user_row(username)
    legacy_users = configured_users()
    if not user_row and username not in legacy_users:
        revoke_auth_session(token)
        _delete_auth_token_cookie()
        _delete_query_param_auth_token()
        clear_authenticated_session_state()
        return False
    if user_row and int(user_row.get("ativo", 1) or 0) == 0:
        revoke_auth_session(token)
        _delete_auth_token_cookie()
        _delete_query_param_auth_token()
        clear_authenticated_session_state()
        return False
    role = user_row.get("role", "usuario") if user_row else "usuario"
    nome = user_row.get("nome", username) if user_row else username
    set_authenticated_session(username, role, nome)
    update_user_last_login(username)
    requested_page = str(st.query_params.get("page", AUTH_SESSION_DEFAULT_PAGE) or AUTH_SESSION_DEFAULT_PAGE)
    valid_pages = set(NAV_MENU.values()) | {"usuarios"}
    if requested_page not in valid_pages:
        requested_page = AUTH_SESSION_DEFAULT_PAGE
    requested_label = next((label for label, page in NAV_MENU.items() if page == requested_page), AUTH_SESSION_DEFAULT_LABEL)
    st.session_state["page"] = requested_page
    st.session_state["page_label"] = requested_label
    try:
        st.query_params["page"] = requested_page
    except Exception:
        pass
    return True


def _logout_authenticated_session() -> None:
    token = _get_auth_token_from_cookie() or _get_auth_token_from_query()
    if token:
        revoke_auth_session(token)
    _delete_auth_token_cookie()
    _delete_query_param_auth_token()
    clear_authenticated_session_state()


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


def schema_is_current() -> bool:
    if not using_postgres():
        return False
    try:
        return get_setting("schema_version") == SCHEMA_VERSION
    except Exception:
        return False


def active_session_cutoff(minutes: int = 10) -> str:
    return (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def cleanup_active_sessions(minutes: int = 10) -> None:
    execute("DELETE FROM active_sessions WHERE last_seen < ?", (active_session_cutoff(minutes),))


def touch_active_session(page: str = "") -> None:
    if not st.session_state.get("authenticated") and not st.session_state.get("is_authenticated"):
        return
    session_id = str(st.session_state.get("session_id") or "").strip()
    if not session_id:
        session_id = uuid.uuid4().hex
        st.session_state["session_id"] = session_id
    usuario = current_username() or "sistema"
    timestamp = now_str()
    execute(
        """
        INSERT INTO active_sessions (session_id, usuario, page, last_seen, criado_em)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            usuario=excluded.usuario,
            page=excluded.page,
            last_seen=excluded.last_seen
        """,
        (session_id, usuario, str(page or st.session_state.get("page", "")), timestamp, timestamp),
    )
    cleanup_active_sessions()


def current_user() -> str:
    return current_username() or "sistema"


def remove_active_session() -> None:
    session_id = str(st.session_state.get("session_id") or "").strip()
    if session_id:
        execute("DELETE FROM active_sessions WHERE session_id=?", (session_id,))
    st.session_state.pop("session_id", None)


def load_active_sessions() -> pd.DataFrame:
    return query_df(
        """
        SELECT session_id, usuario, COALESCE(page,'') AS page, last_seen, criado_em
          FROM active_sessions
         ORDER BY last_seen DESC
        """
    )


def parse_competencia(competencia: str) -> tuple[int, int]:
    try:
        year_str, month_str = competencia.split("-", 1)
        return int(year_str), int(month_str)
    except Exception:
        today = date.today()
        return today.year, today.month


def get_database_url() -> str:
    try:
        url = st.secrets.get("DATABASE_URL", "")
        if url:
            return str(url)
    except Exception:
        pass
    try:
        secrets_database = st.secrets.get("database", {})
        url = secrets_database.get("url", "") if hasattr(secrets_database, "get") else ""
        if url:
            return str(url)
    except Exception:
        pass
    return os.getenv("DATABASE_URL", "").strip()


def database_url() -> str:
    return get_database_url()


def using_postgres() -> bool:
    url = get_database_url()
    return url.startswith(("postgresql://", "postgres://"))


def db_label() -> str:
    if using_postgres():
        return "PostgreSQL online"
    return str(DB_PATH)


def db_exists() -> bool:
    return True if using_postgres() else DB_PATH.exists()


def get_engine():
    global _ENGINE, _ENGINE_URL
    url = get_database_url()
    engine_url = url or f"sqlite:///{DB_PATH}"
    if _ENGINE is None or _ENGINE_URL != engine_url:
        if url:
            connect_args = {"sslmode": "require"} if url.startswith(("postgresql://", "postgres://")) else {}
            _ENGINE = create_engine(
                url,
                pool_pre_ping=True,
                pool_recycle=300,
                connect_args=connect_args,
            )
        else:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            _ENGINE = create_engine(
                f"sqlite:///{DB_PATH}",
                connect_args={"check_same_thread": False},
            )
        _ENGINE_URL = engine_url
    return _ENGINE


def test_database_connection() -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        return result.scalar() == 1


@st.cache_data(ttl=30, show_spinner=False)
def database_status_for_login(database_marker: str) -> tuple[str, str]:
    try:
        total_users = query_df("SELECT COUNT(*) AS total FROM users")
        users_count = int(total_users.iloc[0]["total"] or 0) if not total_users.empty else 0
    except Exception:
        users_count = 0
    try:
        if using_postgres() and test_database_connection():
            return "success", f"Banco: Supabase PostgreSQL conectado | Usuarios: {users_count}"
        if using_postgres():
            return "error", "Banco: Supabase PostgreSQL configurado, mas sem conexao"
        return "warning", f"Banco: SQLite local/temporario | Usuarios: {users_count} | Configure DATABASE_URL nos Secrets"
    except Exception as exc:
        return "error", f"Banco: erro de conexao ({type(exc).__name__})"


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
                abertura TEXT,
                situacao TEXT,
                porte TEXT,
                natureza_juridica TEXT,
                capital_social TEXT,
                simples_optante INTEGER DEFAULT 0,
                mei_optante INTEGER DEFAULT 0,
                is_ativo INTEGER DEFAULT 1,
                inativo INTEGER DEFAULT 0,
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
            CREATE TABLE IF NOT EXISTS empresa_demandas (
                empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
                tipo TEXT NOT NULL,
                PRIMARY KEY (empresa_id, tipo)
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
            CREATE TABLE IF NOT EXISTS historico_regime (
                id SERIAL PRIMARY KEY,
                empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
                regime_anterior TEXT,
                regime_novo TEXT NOT NULL,
                vigencia_inicio TEXT NOT NULL,
                registrado_em TEXT NOT NULL,
                origem TEXT
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS active_sessions (
                session_id TEXT PRIMARY KEY,
                usuario TEXT NOT NULL,
                page TEXT,
                last_seen TEXT,
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
        execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen TEXT,
                revoked INTEGER DEFAULT 0,
                user_agent TEXT,
                ip_hint TEXT
            )
            """
        )
        execute(
            """
            CREATE TABLE IF NOT EXISTS logs_sistema (
                id SERIAL PRIMARY KEY,
                usuario TEXT,
                acao TEXT,
                detalhe TEXT,
                criado_em TEXT
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
                abertura TEXT,
                situacao TEXT,
                porte TEXT,
                natureza_juridica TEXT,
                capital_social TEXT,
                simples_optante INTEGER DEFAULT 0,
                mei_optante INTEGER DEFAULT 0,
                is_ativo INTEGER DEFAULT 1,
                inativo INTEGER DEFAULT 0,
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
            CREATE TABLE IF NOT EXISTS empresa_demandas (
                empresa_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                PRIMARY KEY (empresa_id, tipo),
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
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
            CREATE TABLE IF NOT EXISTS historico_regime (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                regime_anterior TEXT,
                regime_novo TEXT NOT NULL,
                vigencia_inicio TEXT NOT NULL,
                registrado_em TEXT NOT NULL,
                origem TEXT,
                FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_sessions (
                session_id TEXT PRIMARY KEY,
                usuario TEXT NOT NULL,
                page TEXT,
                last_seen TEXT,
                criado_em TEXT
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
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen TEXT,
                revoked INTEGER DEFAULT 0,
                user_agent TEXT,
                ip_hint TEXT
            )
            """
            )
            conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logs_sistema (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT,
                acao TEXT,
                detalhe TEXT,
                criado_em TEXT
            )
            """
            )
    ensure_column("empresas", "mensalidade", "TEXT")
    ensure_column("empresas", "cidade", "TEXT")
    ensure_column("empresas", "uf", "TEXT")
    ensure_column("empresas", "abertura", "TEXT")
    ensure_column("empresas", "situacao", "TEXT")
    ensure_column("empresas", "porte", "TEXT")
    ensure_column("empresas", "natureza_juridica", "TEXT")
    ensure_column("empresas", "capital_social", "TEXT")
    ensure_column("empresas", "simples_optante", "INTEGER", "0")
    ensure_column("empresas", "mei_optante", "INTEGER", "0")
    ensure_column("empresas", "inativo", "INTEGER", "0")
    ensure_column("empresas", "funcionarios", "INTEGER", "0")
    ensure_column("empresas", "prolabore", "INTEGER", "0")
    ensure_column("empresas", "prefeitura_optante", "INTEGER", "0")
    ensure_column("empresas", "fgts_parc", "INTEGER", "0")
    ensure_column("empresas", "link_rapido", "TEXT")
    ensure_column("empresas", "senhas_acessos", "TEXT")
    ensure_column("empresas", "observacoes", "TEXT")
    ensure_column("demandas", "observacao", "TEXT", "''")
    ensure_column("historico_regime", "cnpj", "TEXT")
    ensure_column("historico_regime", "data_inicio", "TEXT")
    ensure_column("historico_regime", "criado_em", "TEXT")
    ensure_column("historico_regime", "usuario", "TEXT")
    ensure_column("historico_regime", "regime_anterior", "TEXT")
    ensure_column("historico_regime", "origem", "TEXT")
    ensure_user_schema()
    ensure_column("logs_sistema", "usuario", "TEXT")
    ensure_column("logs_sistema", "acao", "TEXT")
    ensure_column("logs_sistema", "detalhe", "TEXT")
    ensure_column("logs_sistema", "criado_em", "TEXT")
    ensure_database_indexes()
    seed_default_users()


def ensure_database_indexes() -> None:
    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_empresas_cnpj ON empresas (cnpj)",
        "CREATE INDEX IF NOT EXISTS idx_empresas_razao_social ON empresas (razao_social)",
        "CREATE INDEX IF NOT EXISTS idx_empresas_regime ON empresas (regime)",
        "CREATE INDEX IF NOT EXISTS idx_empresas_is_ativo ON empresas (is_ativo)",
        "CREATE INDEX IF NOT EXISTS idx_users_username ON users (username)",
        "CREATE INDEX IF NOT EXISTS idx_demandas_competencia ON demandas (competencia)",
        "CREATE INDEX IF NOT EXISTS idx_demandas_empresa_id ON demandas (empresa_id)",
        "CREATE INDEX IF NOT EXISTS idx_demandas_tipo ON demandas (tipo)",
        "CREATE INDEX IF NOT EXISTS idx_empresa_demandas_empresa_id ON empresa_demandas (empresa_id)",
        "CREATE INDEX IF NOT EXISTS idx_empresa_demandas_tipo ON empresa_demandas (tipo)",
        "CREATE INDEX IF NOT EXISTS idx_faturamento_mei_empresa_id ON faturamento_mei (empresa_id)",
        "CREATE INDEX IF NOT EXISTS idx_faturamento_mei_competencia ON faturamento_mei (competencia)",
        "CREATE INDEX IF NOT EXISTS idx_historico_regime_empresa_id ON historico_regime (empresa_id)",
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_username ON auth_sessions (username)",
        "CREATE INDEX IF NOT EXISTS idx_active_sessions_usuario ON active_sessions (usuario)",
    ]
    for statement in index_statements:
        execute(statement)


@st.cache_resource(show_spinner=False)
def ensure_database_initialized(database_marker: str) -> bool:
    if schema_is_current():
        return True
    init_db()
    if using_postgres():
        set_setting("schema_version", SCHEMA_VERSION)
    return True


def ensure_database_ready() -> None:
    ensure_database_initialized(get_database_url() or str(DB_PATH))


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
    auto_height: bool = False,
    max_height: int = 4000,
) -> pd.DataFrame:
    if auto_height:
        height = calc_empresas_table_height(len(df), row_height=row_height, max_height=max_height)
    return st.data_editor(
        df,
        key=key,
        height=height,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=disabled if editable else True,
        column_config=column_config,
    )


def calc_empresas_table_height(num_rows: int, *, row_height: int = 35, max_height: int = 4000) -> int:
    header_height = 45
    padding = 20
    min_height = 260
    calc_height = header_height + padding + (max(num_rows, 0) * row_height)
    return max(min_height, min(calc_height, max_height))


def _scroll_key(page_key: str) -> str:
    return f"scroll_{page_key}_y"


def inject_scroll_keeper(page_key: str) -> None:
    storage_key = _scroll_key(page_key)
    components.html(
        f"""
        <script>
        (function() {{
          const storageKey = {json.dumps(storage_key)};
          try {{
            const parentWindow = window.parent;
            if (!parentWindow) return;
            const doc = parentWindow.document;
            const root = doc && doc.documentElement;
            const body = doc && doc.body;
            const saveScroll = function() {{
              try {{
                const y = Math.max(
                  parentWindow.pageYOffset || 0,
                  root ? root.scrollTop : 0,
                  body ? body.scrollTop : 0
                );
                parentWindow.localStorage.setItem(storageKey, String(y));
              }} catch (err) {{}}
            }};
            if (!parentWindow.__ceScrollKeeperBound) {{
              parentWindow.__ceScrollKeeperBound = true;
              parentWindow.addEventListener('scroll', saveScroll, {{ passive: true }});
            }}
            saveScroll();
          }} catch (err) {{}}
        }})();
        </script>
        """,
        height=0,
    )


def mark_restore_scroll(page_key: str) -> None:
    st.session_state[f"restore_scroll_{page_key}"] = True


def restore_scroll_if_needed(page_key: str) -> None:
    flag_key = f"restore_scroll_{page_key}"
    if not st.session_state.pop(flag_key, False):
        return
    storage_key = _scroll_key(page_key)
    components.html(
        f"""
        <script>
        (function() {{
          const storageKey = {json.dumps(storage_key)};
          try {{
            const parentWindow = window.parent;
            if (!parentWindow) return;
            const yRaw = parentWindow.localStorage.getItem(storageKey);
            const y = Number.parseInt(yRaw || '0', 10);
            if (!Number.isFinite(y)) return;
            setTimeout(function() {{
              try {{
                parentWindow.scrollTo(0, y);
                const doc = parentWindow.document;
                if (doc && doc.documentElement) doc.documentElement.scrollTop = y;
                if (doc && doc.body) doc.body.scrollTop = y;
              }} catch (err) {{}}
            }}, 60);
          }} catch (err) {{}}
        }})();
        </script>
        """,
        height=0,
    )


def normalize_cnpj(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) != 14:
        return str(value or "").strip()
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def cnpj_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def cnpj_biz_url(cnpj_txt: str) -> str:
    cnpj = only_digits(cnpj_txt)
    return f"https://cnpj.biz/{cnpj}" if len(cnpj) == 14 else "https://cnpj.biz/"


def only_digits(value: str) -> str:
    return cnpj_digits(value)


def format_cnpj(value: str) -> str:
    return normalize_cnpj(value)


def cnpj_valido(value: str) -> bool:
    return len(cnpj_digits(value)) == 14


def _normalize_brl_text_for_db(value: str) -> str:
    return format_brl_currency(value)


def split_cidade_uf(value: str) -> tuple[str, str]:
    txt = str(value or "").strip()
    if not txt:
        return "", ""
    if " - " in txt:
        city, uf = txt.rsplit(" - ", 1)
        return city.strip(), uf.strip().upper()
    if "/" in txt:
        city, uf = txt.rsplit("/", 1)
        uf = uf.strip().upper()
        if len(uf) == 2:
            return city.strip(), uf
    return txt, ""


def _first_filled(*values) -> str:
    for value in values:
        if value is None:
            continue
        txt = str(value).strip()
        if txt and txt.lower() not in {"none", "null", "nan"}:
            return txt
    return ""


def _date_br_to_iso(txt: str) -> str:
    value = str(txt or "").strip()
    if not value:
        return ""
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value
    parts = value.split("/")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        dd, mm, yyyy = parts
        if len(yyyy) == 4:
            return f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"
    return value


def _fmt_natureza_juridica(nat_id, nat_desc) -> str:
    desc = str(nat_desc or "").strip()
    raw_id = "".join(ch for ch in str(nat_id or "") if ch.isdigit())
    if raw_id:
        if len(raw_id) >= 4:
            raw_id = f"{raw_id[:-1]}-{raw_id[-1]}"
        if desc:
            return f"{raw_id} - {desc}"
        return raw_id
    return desc


def _guess_apelido(razao: str, fantasia: str) -> str:
    base = _first_filled(fantasia, razao)
    base = str(base or "").strip()
    while base and base[0].isdigit():
        base = base[1:].lstrip(" -./")
    return base.upper()[:28]


def _regime_option(value: str) -> str:
    txt = str(value or "").strip()
    if txt in REGIMES:
        return txt
    if txt.upper().startswith("MEI"):
        return "MEI"
    if txt.upper().startswith("SIMPLES"):
        return "Simples Nacional"
    if txt.upper().startswith("LUCRO PRESUMIDO"):
        return "Lucro Presumido"
    if txt.upper().startswith("LUCRO REAL"):
        return "Lucro Real"
    return REGIMES[0]


def _http_get_text(url: str, timeout: int = 20, accept_json: bool = False) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "application/json, text/plain, */*" if accept_json else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _extract_simples_flags_from_cnpjws(payload: dict) -> tuple[int, int]:
    simples = payload.get("simples") or {}
    estabelecimento = payload.get("estabelecimento") or {}
    regimes = estabelecimento.get("regimes_tributarios") or []
    text_blob = " ".join(
        str(item.get("regime_tributario") or item.get("forma_de_tributacao") or "")
        for item in regimes
        if isinstance(item, dict)
    ).upper()

    def truthy(v) -> bool:
        if isinstance(v, bool):
            return v
        return str(v or "").strip().lower() in {"1", "true", "t", "s", "sim", "y", "yes"}

    simples_optante = 0
    mei_optante = 0
    if isinstance(simples, dict):
        simples_optante = 1 if truthy(simples.get("simples") or simples.get("simples_nacional") or simples.get("optante")) else 0
        mei_optante = 1 if truthy(simples.get("mei") or simples.get("simei") or simples.get("simei")) else 0
    if not simples_optante and "SIMPLES" in text_blob:
        simples_optante = 1
    if not mei_optante and ("MEI" in text_blob or "SIMEI" in text_blob):
        mei_optante = 1
    return simples_optante, mei_optante


def _fetch_receitaws_json(cnpj: str) -> dict:
    url = f"https://www.receitaws.com.br/v1/cnpj/{cnpj}"
    text = _http_get_text(url, timeout=20, accept_json=True)
    payload = json.loads(text)
    if isinstance(payload, dict):
        return payload
    raise ValueError("Retorno invalido da ReceitaWS.")


def fetch_empresa_cadastro_on(cnpj_txt: str) -> dict:
    cnpj = only_digits(cnpj_txt)
    if not cnpj_valido(cnpj):
        raise ValueError("Informe um CNPJ v?lido com 14 d?gitos.")

    url_biz = cnpj_biz_url(cnpj)
    try:
        _http_get_text(url_biz, timeout=20, accept_json=False)
    except Exception:
        pass

    info = {
        "source": "cnpj.biz",
        "url": url_biz,
        "cnpj": cnpj,
        "razao_social": "",
        "nome_fantasia": "",
        "apelido": "",
        "regime": "Lucro Presumido",
        "abertura": "",
        "natureza_juridica": "",
        "situacao": "",
        "capital_social": "",
        "cidade": "",
        "uf": "",
        "porte": "",
        "simples_optante": 0,
        "mei_optante": 0,
    }

    cnpjws_payload: dict = {}
    cnpjws_error = None
    try:
        cnpjws_text = _http_get_text(f"https://publica.cnpj.ws/cnpj/{cnpj}", timeout=20, accept_json=True)
        cnpjws_payload = json.loads(cnpjws_text)
        if not isinstance(cnpjws_payload, dict):
            raise ValueError("JSON invalido da cnpj.ws.")
    except Exception as exc:
        cnpjws_error = exc
        cnpjws_payload = {}

    if cnpjws_payload:
        estabelecimento = cnpjws_payload.get("estabelecimento") or {}
        cidade = estabelecimento.get("cidade") or {}
        estado = estabelecimento.get("estado") or {}
        natureza = cnpjws_payload.get("natureza_juridica") or {}
        porte = cnpjws_payload.get("porte") or {}
        simples_optante, mei_optante = _extract_simples_flags_from_cnpjws(cnpjws_payload)

        info["razao_social"] = _first_filled(cnpjws_payload.get("razao_social"), estabelecimento.get("razao_social"))
        info["nome_fantasia"] = _first_filled(estabelecimento.get("nome_fantasia"))
        info["cidade"] = _first_filled(cidade.get("nome"), estabelecimento.get("municipio"), estabelecimento.get("nome_cidade_exterior"))
        info["uf"] = _first_filled(estado.get("sigla"), estabelecimento.get("uf")).upper()
        info["abertura"] = _date_br_to_iso(_first_filled(estabelecimento.get("data_inicio_atividade")))
        info["situacao"] = _first_filled(estabelecimento.get("situacao_cadastral"))
        info["capital_social"] = _first_filled(cnpjws_payload.get("capital_social"))
        info["porte"] = _first_filled(porte.get("descricao"))
        info["natureza_juridica"] = _fmt_natureza_juridica(natureza.get("id"), natureza.get("descricao"))
        info["simples_optante"] = simples_optante
        info["mei_optante"] = mei_optante
        info["regime"] = "MEI" if mei_optante else ("Simples Nacional (ME/EPP)" if simples_optante else "Lucro Presumido")
        info["apelido"] = _guess_apelido(info["razao_social"], info["nome_fantasia"])
        info["source"] = "cnpj.biz + cnpj.ws"
    elif cnpjws_error is not None:
        # If cnpj.ws is unavailable, fall back to ReceitaWS so the user can still proceed.
        try:
            receitaws_payload = _fetch_receitaws_json(cnpj)
        except Exception as exc:
            raise ConnectionError("A consulta online falhou. Tente novamente ou preencha manualmente.") from exc

        info["source"] = "cnpj.biz + receitaws"
        info["razao_social"] = _first_filled(receitaws_payload.get("nome"))
        info["nome_fantasia"] = _first_filled(receitaws_payload.get("fantasia"))
        info["apelido"] = _guess_apelido(info["razao_social"], info["nome_fantasia"])
        info["abertura"] = _date_br_to_iso(_first_filled(receitaws_payload.get("abertura")))
        info["situacao"] = _first_filled(receitaws_payload.get("situacao"))
        info["capital_social"] = _first_filled(receitaws_payload.get("capital_social"))
        info["cidade"] = _first_filled(receitaws_payload.get("municipio"))
        info["uf"] = _first_filled(receitaws_payload.get("uf")).upper()
        info["porte"] = _first_filled(receitaws_payload.get("porte"))
        receitaws_nat = str(receitaws_payload.get("natureza_juridica") or "").strip()
        if receitaws_nat:
            if " - " in receitaws_nat:
                nat_id, nat_desc = receitaws_nat.split(" - ", 1)
            else:
                nat_id, nat_desc = "", receitaws_nat
            info["natureza_juridica"] = _fmt_natureza_juridica(nat_id, nat_desc)
        simples_txt = str(receitaws_payload.get("simples", "") or "").upper()
        simei_txt = str(receitaws_payload.get("simei", "") or "").upper()
        if simples_txt in {"SIM", "S", "TRUE", "1"}:
            info["simples_optante"] = 1
        if simei_txt in {"SIM", "S", "TRUE", "1"}:
            info["mei_optante"] = 1
        info["regime"] = "MEI" if info["mei_optante"] else ("Simples Nacional (ME/EPP)" if info["simples_optante"] else "Lucro Presumido")
        return info

    missing_fields = [
        field for field in ["razao_social", "nome_fantasia", "cidade", "uf", "abertura", "situacao", "capital_social", "porte", "natureza_juridica"]
        if not str(info.get(field, "")).strip()
    ]
    if missing_fields:
        try:
            receitaws_payload = _fetch_receitaws_json(cnpj)
        except Exception:
            receitaws_payload = {}
        if isinstance(receitaws_payload, dict) and receitaws_payload:
            info["source"] = "cnpj.biz + cnpj.ws + receitaws"
            info["razao_social"] = _first_filled(info["razao_social"], receitaws_payload.get("nome"))
            info["nome_fantasia"] = _first_filled(info["nome_fantasia"], receitaws_payload.get("fantasia"))
            info["abertura"] = _first_filled(info["abertura"], _date_br_to_iso(receitaws_payload.get("abertura")))
            info["situacao"] = _first_filled(info["situacao"], receitaws_payload.get("situacao"))
            info["capital_social"] = _first_filled(info["capital_social"], receitaws_payload.get("capital_social"))
            info["cidade"] = _first_filled(info["cidade"], receitaws_payload.get("municipio"))
            info["uf"] = _first_filled(info["uf"], receitaws_payload.get("uf")).upper()
            info["porte"] = _first_filled(info["porte"], receitaws_payload.get("porte"))
            receitaws_nat = str(receitaws_payload.get("natureza_juridica") or "").strip()
            if receitaws_nat and not info["natureza_juridica"]:
                if " - " in receitaws_nat:
                    nat_id, nat_desc = receitaws_nat.split(" - ", 1)
                else:
                    nat_id, nat_desc = "", receitaws_nat
                info["natureza_juridica"] = _fmt_natureza_juridica(nat_id, nat_desc)
            simples_txt = str(receitaws_payload.get("simples", "") or "").upper()
            simei_txt = str(receitaws_payload.get("simei", "") or "").upper()
            if not info["simples_optante"] and simples_txt in {"SIM", "S", "TRUE", "1"}:
                info["simples_optante"] = 1
            if not info["mei_optante"] and simei_txt in {"SIM", "S", "TRUE", "1"}:
                info["mei_optante"] = 1
            info["regime"] = "MEI" if info["mei_optante"] else ("Simples Nacional (ME/EPP)" if info["simples_optante"] else info["regime"])
            info["apelido"] = _guess_apelido(info["razao_social"], info["nome_fantasia"])

    return info


def fetch_empresa_cadastro_on_web(cnpj: str) -> dict:
    return fetch_empresa_cadastro_on(cnpj)


def clean_cell(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def load_empresas(active_only: bool = True) -> pd.DataFrame:
    active_expr = "COALESCE(is_ativo, CASE WHEN COALESCE(inativo,0)=1 THEN 0 ELSE 1 END)"
    where = f"WHERE {active_expr}=1" if active_only else ""
    return query_df(
        f"""
        SELECT id, cnpj, razao_social, COALESCE(nome_fantasia,'') AS nome_fantasia,
               COALESCE(apelido,'') AS apelido, COALESCE(regime,'') AS regime,
               COALESCE(mensalidade,'') AS mensalidade, COALESCE(cidade,'') AS cidade,
               COALESCE(uf,'') AS uf, COALESCE(inativo,0) AS inativo,
               COALESCE(funcionarios,0) AS funcionarios,
               {active_expr} AS is_ativo, atualizado_em
        FROM empresas
        {where}
        ORDER BY razao_social COLLATE NOCASE
        """
    )


def format_brl_currency(val: str) -> str:
    if not val:
        return ""
    clean = str(val).upper().replace("R$", "").replace("$", "").strip()
    if not clean:
        return ""
    try:
        num_chars = []
        for char in clean:
            if char.isdigit() or char in [".", ","]:
                num_chars.append(char)
        num_str = "".join(num_chars)
        if not num_str:
            return clean
            
        if "," in num_str:
            parts = num_str.split(",")
            integer_part = parts[0].replace(".", "")
            decimal_part = parts[1]
            val_float = float(f"{integer_part}.{decimal_part}")
        else:
            if "." in num_str:
                dot_parts = num_str.split(".")
                if len(dot_parts) == 2 and len(dot_parts[1]) != 3:
                    val_float = float(num_str)
                else:
                    val_float = float(num_str.replace(".", ""))
            else:
                val_float = float(num_str)
        
        if val_float.is_integer():
            formatted = f"{int(val_float):,}".replace(",", ".") + " R$"
        else:
            formatted = f"{val_float:,.2f}"
            formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".") + " R$"
        return formatted
    except Exception:
        s = str(val).strip()
        if s and not s.upper().endswith("R$") and not s.upper().endswith("R $"):
            return f"{s} R$"
        return s


def save_empresa(data: dict, empresa_id: int | None = None) -> None:
    timestamp = now_str()
    before_existing = empresa_row(int(empresa_id)) if empresa_id else {}

    def txt_field(key: str, default: str = "") -> str:
        if key not in data:
            return str(before_existing.get(key, default) or "")
        value = str(data.get(key, "") or "").strip()
        if not value and before_existing.get(key):
            return str(before_existing.get(key, "") or "")
        return value

    def int_field(key: str, default: int = 0) -> int:
        if key not in data:
            return int(before_existing.get(key, default) or 0)
        return int(data.get(key, default) or 0)

    inativo = int_field("inativo", 0)
    is_ativo = 0 if inativo else 1
    simples_optante = int_field("simples_optante", 0)
    mei_optante = int_field("mei_optante", 0)
    normalized = {
        "cnpj": normalize_cnpj(txt_field("cnpj")),
        "razao_social": txt_field("razao_social"),
        "nome_fantasia": txt_field("nome_fantasia"),
        "apelido": txt_field("apelido"),
        "regime": txt_field("regime"),
        "abertura": txt_field("abertura"),
        "situacao": txt_field("situacao"),
        "porte": txt_field("porte"),
        "natureza_juridica": txt_field("natureza_juridica"),
        "capital_social": txt_field("capital_social"),
        "simples_optante": simples_optante,
        "mei_optante": mei_optante,
        "mensalidade": format_brl_currency(txt_field("mensalidade")),
        "cidade": txt_field("cidade"),
        "uf": txt_field("uf").upper(),
        "funcionarios": int_field("funcionarios", 0),
        "link_rapido": txt_field("link_rapido"),
        "senhas_acessos": txt_field("senhas_acessos"),
        "observacoes": txt_field("observacoes"),
        "inativo": inativo,
        "is_ativo": is_ativo,
        "timestamp": timestamp,
    }
    if not normalized["cnpj"] or not normalized["razao_social"]:
        raise ValueError("CNPJ e razao social sao obrigatorios.")
    if empresa_id:
        before = empresa_snapshot(before_existing)
        regime_before = str(before.get("regime", "") or "").strip()
        regime_after = str(normalized["regime"] or "").strip()
        if regime_before and regime_after and regime_before != regime_after and not str(data.get("regime_vigencia", "") or "").strip():
            raise ValueError("Informe a data de vigencia para alterar o regime.")
        execute(
            """
            UPDATE empresas
               SET cnpj=?, razao_social=?, nome_fantasia=?, apelido=?, regime=?,
                   abertura=?, situacao=?, porte=?, natureza_juridica=?, capital_social=?,
                   simples_optante=?, mei_optante=?, mensalidade=?, cidade=?, uf=?,
                   funcionarios=?, link_rapido=?, senhas_acessos=?, observacoes=?,
                   inativo=?, is_ativo=?, atualizado_em=?
             WHERE id=?
            """,
            (
                normalized["cnpj"],
                normalized["razao_social"],
                normalized["nome_fantasia"],
                normalized["apelido"],
                normalized["regime"],
                normalized["abertura"],
                normalized["situacao"],
                normalized["porte"],
                normalized["natureza_juridica"],
                normalized["capital_social"],
                normalized["simples_optante"],
                normalized["mei_optante"],
                normalized["mensalidade"],
                normalized["cidade"],
                normalized["uf"],
                normalized["funcionarios"],
                normalized["link_rapido"],
                normalized["senhas_acessos"],
                normalized["observacoes"],
                normalized["inativo"],
                normalized["is_ativo"],
                timestamp,
                int(empresa_id),
            ),
        )
        after = empresa_snapshot(empresa_row(int(empresa_id)))
        if before and after and any(str(before.get(key, "")) != str(after.get(key, "")) for key in [
            "cnpj", "razao_social", "nome_fantasia", "apelido", "regime",
            "abertura", "situacao", "porte", "natureza_juridica", "capital_social",
            "simples_optante", "mei_optante", "mensalidade", "cidade", "uf",
            "inativo", "is_ativo",
        ]):
            before_active = int(before.get("is_ativo", 1) or 1)
            after_active = int(after.get("is_ativo", 1) or 1)
            if before_active == 1 and after_active == 0:
                action = "EXCLUSAO"
            elif before_active == 0 and after_active == 1:
                action = "REATIVACAO"
            else:
                action = "ALTERACAO"
            record_empresa_history(int(empresa_id), action, before, after)
        if regime_before and regime_after and regime_before != regime_after:
            record_historico_regime(
                int(empresa_id),
                normalized["cnpj"],
                regime_before,
                regime_after,
                str(data.get("regime_vigencia", "") or "").strip(),
            )
    else:
        execute(
            """
            INSERT INTO empresas
                (cnpj, razao_social, nome_fantasia, apelido, regime, abertura, situacao,
                 porte, natureza_juridica, capital_social, simples_optante, mei_optante,
                 mensalidade, cidade, uf, funcionarios, link_rapido, senhas_acessos, observacoes,
                 inativo, is_ativo, criado_em, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["cnpj"],
                normalized["razao_social"],
                normalized["nome_fantasia"],
                normalized["apelido"],
                normalized["regime"],
                normalized["abertura"],
                normalized["situacao"],
                normalized["porte"],
                normalized["natureza_juridica"],
                normalized["capital_social"],
                normalized["simples_optante"],
                normalized["mei_optante"],
                normalized["mensalidade"],
                normalized["cidade"],
                normalized["uf"],
                normalized["funcionarios"],
                normalized["link_rapido"],
                normalized["senhas_acessos"],
                normalized["observacoes"],
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
               COALESCE(abertura,'') AS abertura, COALESCE(situacao,'') AS situacao,
               COALESCE(porte,'') AS porte, COALESCE(natureza_juridica,'') AS natureza_juridica,
               COALESCE(capital_social,'') AS capital_social,
               COALESCE(simples_optante,0) AS simples_optante,
               COALESCE(mei_optante,0) AS mei_optante,
               COALESCE(mensalidade,'') AS mensalidade, COALESCE(cidade,'') AS cidade,
               COALESCE(uf,'') AS uf, COALESCE(inativo,0) AS inativo,
               COALESCE(funcionarios,0) AS funcionarios,
               COALESCE(link_rapido,'') AS link_rapido,
               COALESCE(senhas_acessos,'') AS senhas_acessos,
               COALESCE(observacoes,'') AS observacoes,
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






def empresa_row(empresa_id: int) -> dict:
    df = query_df(
        """
        SELECT id, cnpj, razao_social, COALESCE(nome_fantasia,'') AS nome_fantasia,
               COALESCE(apelido,'') AS apelido, COALESCE(regime,'') AS regime,
               COALESCE(abertura,'') AS abertura, COALESCE(situacao,'') AS situacao,
               COALESCE(porte,'') AS porte, COALESCE(natureza_juridica,'') AS natureza_juridica,
               COALESCE(capital_social,'') AS capital_social,
               COALESCE(simples_optante,0) AS simples_optante,
               COALESCE(mei_optante,0) AS mei_optante,
               COALESCE(mensalidade,'') AS mensalidade, COALESCE(cidade,'') AS cidade,
               COALESCE(uf,'') AS uf, COALESCE(inativo,0) AS inativo,
               COALESCE(funcionarios,0) AS funcionarios,
               COALESCE(link_rapido,'') AS link_rapido,
               COALESCE(senhas_acessos,'') AS senhas_acessos,
               COALESCE(observacoes,'') AS observacoes,
               COALESCE(is_ativo, CASE WHEN COALESCE(inativo,0)=1 THEN 0 ELSE 1 END) AS is_ativo,
               atualizado_em, criado_em
          FROM empresas
         WHERE id=?
         LIMIT 1
        """,
        (int(empresa_id),),
    )
    return df.iloc[0].to_dict() if not df.empty else {}


def empresa_snapshot(row: dict | None) -> dict:
    if not row:
        return {}
    data = dict(row)
    return {
        "id": int(data.get("id", 0) or 0),
        "cnpj": str(data.get("cnpj", "") or ""),
        "razao_social": str(data.get("razao_social", "") or ""),
        "nome_fantasia": str(data.get("nome_fantasia", "") or ""),
        "apelido": str(data.get("apelido", "") or ""),
        "regime": str(data.get("regime", "") or ""),
        "abertura": str(data.get("abertura", "") or ""),
        "situacao": str(data.get("situacao", "") or ""),
        "porte": str(data.get("porte", "") or ""),
        "natureza_juridica": str(data.get("natureza_juridica", "") or ""),
        "capital_social": str(data.get("capital_social", "") or ""),
        "simples_optante": int(data.get("simples_optante", 0) or 0),
        "mei_optante": int(data.get("mei_optante", 0) or 0),
        "mensalidade": str(data.get("mensalidade", "") or ""),
        "cidade": str(data.get("cidade", "") or ""),
        "uf": str(data.get("uf", "") or ""),
        "funcionarios": int(data.get("funcionarios", 0) or 0),
        "link_rapido": str(data.get("link_rapido", "") or ""),
        "senhas_acessos": str(data.get("senhas_acessos", "") or ""),
        "observacoes": str(data.get("observacoes", "") or ""),
        "inativo": int(data.get("inativo", 0) or 0),
        "is_ativo": int(data.get("is_ativo", 1) or 1),
        "atualizado_em": str(data.get("atualizado_em", "") or ""),
        "criado_em": str(data.get("criado_em", "") or ""),
    }


def record_empresa_history(empresa_id: int, action: str, before: dict, after: dict) -> None:
    labels = {
        "cnpj": "CNPJ",
        "razao_social": "Razão social",
        "nome_fantasia": "Nome fantasia",
        "apelido": "Apelido",
        "regime": "Regime",
        "mensalidade": "Mensalidade",
        "cidade": "Cidade",
        "uf": "UF",
        "inativo": "Inativo",
        "is_ativo": "Ativo",
    }
    changed_fields = []
    for key, label in labels.items():
        if str(before.get(key, "")) != str(after.get(key, "")):
            changed_fields.append(label)
    summary = ", ".join(changed_fields) if changed_fields else action
    usuario = str(st.session_state.get("auth_user", "")).strip() or "sistema"
    execute(
        """
        INSERT INTO historico_empresas
            (empresa_id, acao, usuario, resumo, snapshot_anterior, snapshot_atual, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(empresa_id),
            action,
            usuario,
            summary,
            json.dumps(before, ensure_ascii=False),
            json.dumps(after, ensure_ascii=False),
            now_str(),
        ),
    )


def record_historico_regime(empresa_id: int, cnpj: str, regime_anterior: str, regime_novo: str, data_inicio: str) -> None:
    usuario = str(st.session_state.get("auth_user", "") or st.session_state.get("user_name", "") or "sistema").strip()
    criado_em = now_str()
    execute(
        """
        INSERT INTO historico_regime
            (empresa_id, cnpj, regime_anterior, regime_novo, vigencia_inicio, data_inicio, registrado_em, criado_em, usuario, origem)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(empresa_id),
            normalize_cnpj(cnpj),
            str(regime_anterior or ""),
            str(regime_novo or ""),
            str(data_inicio or ""),
            str(data_inicio or ""),
            criado_em,
            criado_em,
            usuario,
            "web",
        ),
    )


def load_historico_regime(empresa_id: int) -> pd.DataFrame:
    return query_df(
        """
        SELECT regime_anterior, regime_novo,
               COALESCE(data_inicio, vigencia_inicio, '') AS data_inicio,
               COALESCE(usuario,'') AS usuario,
               COALESCE(criado_em, registrado_em, '') AS criado_em
          FROM historico_regime
         WHERE empresa_id=?
         ORDER BY COALESCE(criado_em, registrado_em, '') DESC, id DESC
        """,
        (int(empresa_id),),
    )


def load_empresa_demandas(empresa_id: int) -> set[str]:
    df = query_df("SELECT tipo FROM empresa_demandas WHERE empresa_id=?", (int(empresa_id),))
    return set(df["tipo"].astype(str).tolist()) if not df.empty else set()


def save_empresa_demandas(empresa_id: int, tipos: list[str]) -> None:
    execute("DELETE FROM empresa_demandas WHERE empresa_id=?", (int(empresa_id),))
    for tipo in sorted(set(tipos)):
        execute(
            "INSERT INTO empresa_demandas (empresa_id, tipo) VALUES (?, ?) ON CONFLICT(empresa_id, tipo) DO NOTHING",
            (int(empresa_id), str(tipo)),
        )


def move_empresa_to_trash(empresa_id: int) -> None:
    row = empresa_row(int(empresa_id))
    if not row:
        raise ValueError("Empresa nao encontrada.")
    payload = {**row, "inativo": 1}
    save_empresa(payload, int(empresa_id))


def restore_empresa_from_trash(empresa_id: int) -> None:
    row = empresa_row(int(empresa_id))
    if not row:
        raise ValueError("Empresa nao encontrada.")
    payload = {**row, "inativo": 0}
    save_empresa(payload, int(empresa_id))


def empresas_export_csv(df: pd.DataFrame) -> bytes:
    export_cols = [
        "id",
        "cnpj",
        "razao_social",
        "nome_fantasia",
        "apelido",
        "regime",
        "mensalidade",
        "cidade",
        "uf",
        "inativo",
        "is_ativo",
    ]
    export_df = df.copy()
    for col in export_cols:
        if col not in export_df.columns:
            export_df[col] = ""
    export_df = export_df[export_cols].fillna("")
    return export_df.to_csv(index=False).encode("utf-8-sig")


def empresas_import_dataframe(uploaded_file) -> pd.DataFrame:
    name = str(getattr(uploaded_file, "name", "") or "").lower()
    if name.endswith(".csv") or name.endswith(".txt"):
        df = pd.read_csv(uploaded_file)
    elif name.endswith(".xlsx") or name.endswith(".xls"):
        df = pd.read_excel(uploaded_file)
    else:
        raise ValueError("Formato não suportado. Use CSV ou XLSX.")
    df.columns = [str(col).strip().lower() for col in df.columns]
    return df


def empresas_apply_import(df: pd.DataFrame) -> tuple[int, int]:
    updated = 0
    created = 0
    if df.empty:
        return updated, created

    for _, row in df.iterrows():
        raw_id = row.get("id", "")
        raw_cnpj = row.get("cnpj", "")
        existing = {}
        empresa_id = None

        if pd.notna(raw_id) and str(raw_id).strip():
            try:
                empresa_id = int(float(str(raw_id).replace(",", ".")))
                existing = empresa_row(empresa_id)
            except Exception:
                empresa_id = None

        if not existing and pd.notna(raw_cnpj) and str(raw_cnpj).strip():
            existing = empresa_row_by_cnpj(str(raw_cnpj))
            if existing:
                empresa_id = int(existing.get("id", 0) or 0)

        if not existing and not empresa_id:
            empresa_id = None

        def pick(field: str, default: str = "") -> str:
            value = row.get(field, "")
            if pd.isna(value) or str(value).strip() == "":
                return str(existing.get(field, default) if existing else default)
            return str(value).strip()

        payload = {
            "cnpj": normalize_cnpj(pick("cnpj", existing.get("cnpj", "") if existing else "")),
            "razao_social": pick("razao_social", existing.get("razao_social", "") if existing else "").strip(),
            "nome_fantasia": pick("nome_fantasia", existing.get("nome_fantasia", "") if existing else "").strip(),
            "apelido": pick("apelido", existing.get("apelido", "") if existing else "").strip(),
            "regime": pick("regime", existing.get("regime", "") if existing else "").strip(),
            "mensalidade": pick("mensalidade", existing.get("mensalidade", "") if existing else "").strip(),
            "cidade": pick("cidade", existing.get("cidade", "") if existing else "").strip(),
            "uf": pick("uf", existing.get("uf", "") if existing else "").strip().upper(),
            "inativo": int(float(str(row.get("inativo", existing.get("inativo", 0) if existing else 0) or 0).replace(",", "."))),
        }

        if not payload["cnpj"] or not payload["razao_social"]:
            continue

        if empresa_id and existing:
            save_empresa(payload, empresa_id)
            updated += 1
        else:
            save_empresa(payload, None)
            created += 1

    return updated, created

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
        df["status"] = df["feito"].map(lambda v: "Concluida" if int(v or 0) else "Pendente")
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
    st.warning("Banco de dados ainda nao encontrado para este projeto web.")
    uploaded = st.file_uploader("Enviar cnpjs.db", type=["db", "sqlite", "sqlite3"])
    if uploaded:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_DB_PATH.write_bytes(uploaded.getbuffer())
        st.success("Banco recebido. Recarregue a pagina para abrir o sistema.")
    if st.button("Criar banco vazio"):
        init_db()
        st.rerun()


def sync_auth_passwords_txt(users: dict[str, str]) -> None:
    return


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
    ensure_auth_sessions_table()
    if st.session_state.get("authenticated") or st.session_state.get("is_authenticated"):
        return True
    if _restore_persistent_auth_session():
        return True
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
            st.session_state["page_label"] = AUTH_SESSION_DEFAULT_LABEL
        if "page" not in st.session_state:
            st.session_state["page"] = AUTH_SESSION_DEFAULT_PAGE
        with st.sidebar:
            user = st.session_state.get("auth_user", "")
            if user:
                st.caption(str(user))
            if st.button("Sair", help="Sair do sistema"):
                _logout_authenticated_session()
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
            user = st.text_input("Usuario")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
    if submitted:
        if users.get(user) == password:
            token = create_auth_session(user)
            _set_auth_persistence(token)
            st.session_state["authenticated"] = True
            st.session_state["auth_user"] = user
            st.session_state["page_label"] = AUTH_SESSION_DEFAULT_LABEL
            st.session_state["page"] = AUTH_SESSION_DEFAULT_PAGE
            st.query_params["page"] = AUTH_SESSION_DEFAULT_PAGE
            st.rerun()
        else:
            st.error("Usuario ou senha invalidos.")
    return False


def render_sidebar() -> tuple[str, str]:
    menu_map = {
        "📂 Módulos": "Modulos",
        "📊 Painel": "Painel",
        "👤 Novo Cliente": "Novo Cliente",
        "🏢 Empresas": "Empresas",
        "📋 Demandas": "Demandas",
        "🤖 Automação": "Automacao",
        "💰 Faturamento": "Faturamento",
        "💾 Backup": "Backup",
    }
    menu_items = list(menu_map.keys())
    requested_page = normalize_page(st.query_params.get("page", st.session_state.get("page", "Modulos")) or "Modulos")
    requested_label = next((label for label, page in menu_map.items() if page == requested_page), "📂 Módulos")
    if requested_label not in menu_items:
        requested_label = st.session_state.get("page_label", "📂 Módulos")
    if requested_label not in menu_items:
        requested_label = "📂 Módulos"
    menu_index = menu_items.index(requested_label)
    with st.sidebar:
        render_company_logo()
        page_label = st.radio("Menu", menu_items, index=menu_index)
        page = menu_map[page_label]
        st.session_state["page_label"] = page_label
        st.session_state["page"] = page
        if st.query_params.get("page") != page:
            st.query_params["page"] = page
        saved_competencia = (
            st.session_state.get("competencia")
            or st.session_state.get("ultima_competencia")
            or get_setting("ultima_competencia", current_competencia())
        )
        st.session_state["ultima_competencia"] = saved_competencia
        current_year, current_month = parse_competencia(saved_competencia)
        years = list(range(current_year - 5, current_year + 6))
        month_options = [f"{m:02d}" for m in range(1, 13)]
        y1, y2 = st.sidebar.columns(2)
        year = y1.selectbox("Ano", years, index=years.index(current_year))
        month = y2.selectbox("Mes", month_options, index=month_options.index(f"{current_month:02d}"))
        competencia = f"{int(year)}-{month}"
        st.session_state["competencia"] = competencia
        if st.session_state.get("ultima_competencia") != competencia:
            st.session_state["ultima_competencia"] = competencia
            set_setting("ultima_competencia", competencia)
        touch_active_session(page)
        active_now = load_active_sessions()
        st.sidebar.caption(f"Usuarios online: {active_now['usuario'].nunique()} | Sessoes: {len(active_now)}")
        if not active_now.empty:
            names = ", ".join(active_now["usuario"].drop_duplicates().tolist()[:4])
            st.sidebar.caption(names)
    return page, competencia


def require_login_secure() -> bool:
    ensure_database_ready()
    ensure_auth_sessions_table()
    if _restore_persistent_auth_session():
        return True
    legacy_users = configured_users()
    total_users = query_df("SELECT COUNT(*) AS total FROM users")
    has_users = not total_users.empty and int(total_users.iloc[0]["total"] or 0) > 0
    has_legacy = bool(legacy_users)
    if not has_users and not has_legacy:
        with st.container(border=True, key="login_card_secure"):
            st.markdown(
                """
                <div class="login-brand"><span class="login-mark">E</span>Excelencia Contabilidade</div>
                <div class="login-title">Controle de Empresas</div>
                <div class="login-subtitle">Acesso bloqueado. Configure usuários na tabela, em secrets ou por variável de ambiente.</div>
                """,
                unsafe_allow_html=True,
            )
            st.warning(
                "Defina ao menos um usuário em `users`, `[auth.users]` no secrets.toml ou via `CONTROLE_EMPRESAS_USER`/`CONTROLE_EMPRESAS_PASSWORD`.",
            )
        return False

    if st.session_state.get("authenticated") or st.session_state.get("is_authenticated"):
        username = current_username()
        user_row = get_user_row(username)
        if user_row and int(user_row.get("ativo", 1) or 0) == 0:
            remove_active_session()
            _logout_authenticated_session()
            st.error("Usuário inativo. Procure o administrador.")
            return False
        if user_row:
            st.session_state["user_role"] = user_role_for(username, user_row.get("role", "usuario"))
            st.session_state["user_name"] = user_display_name_for(username, user_row.get("nome", username))
        if "page_label" not in st.session_state:
            st.session_state["page_label"] = AUTH_SESSION_DEFAULT_LABEL
        if "page" not in st.session_state:
            st.session_state["page"] = AUTH_SESSION_DEFAULT_PAGE
        return True

    with st.container(border=True, key="login_card_secure"):
        st.markdown(
            """
            <div class="login-brand"><span class="login-mark">E</span>Excelencia Contabilidade</div>
            <div class="login-title">Controle de Empresas</div>
            <div class="login-subtitle">Acesso restrito ao controle operacional.</div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_form_secure"):
            user = st.text_input("Usuario")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
    if submitted:
        username_norm = normalize_username(user)
        user_row = get_user_row(username_norm)
        if user_row and int(user_row.get("ativo", 1) or 0) == 0:
            st.error("Usuário inativo. Procure o administrador.")
            return False
        if user_row and verify_password(password, user_row.get("senha_hash", "")):
            set_authenticated_session(username_norm, user_row.get("role", "usuario"), user_row.get("nome", username_norm))
            token = create_auth_session(username_norm)
            _set_auth_persistence(token)
            update_user_last_login(username_norm)
            st.session_state["page_label"] = AUTH_SESSION_DEFAULT_LABEL
            st.session_state["page"] = AUTH_SESSION_DEFAULT_PAGE
            st.query_params["page"] = AUTH_SESSION_DEFAULT_PAGE
            st.rerun()
        legacy_password = legacy_users.get(username_norm)
        if legacy_password and legacy_password == password:
            role = user_role_for(username_norm, user_row.get("role", "usuario") if user_row else "usuario")
            nome = user_display_name_for(username_norm, user_row.get("nome", username_norm) if user_row else username_norm)
            if user_row:
                execute(
                    """
                    UPDATE users
                       SET senha_hash=COALESCE(NULLIF(senha_hash,''), ?),
                           role=?,
                           ativo=1,
                           nome=COALESCE(NULLIF(nome,''), ?),
                           responsavel=COALESCE(NULLIF(responsavel,''), ?),
                           atualizado_em=?,
                           ultimo_login=?
                     WHERE UPPER(username)=UPPER(?)
                    """,
                    (hash_password(password), role, nome, username_norm, now_str(), now_str(), username_norm),
                )
            else:
                upsert_user_record(
                    username=username_norm,
                    nome=nome,
                    senha_hash=hash_password(password),
                    role=role,
                    ativo=1,
                    criado_por=username_norm,
                    responsavel=username_norm,
                    observacao="Migrado automaticamente do login legado.",
                    ultimo_login=now_str(),
                )
            set_authenticated_session(username_norm, role, nome)
            token = create_auth_session(username_norm)
            _set_auth_persistence(token)
            update_user_last_login(username_norm)
            st.session_state["page_label"] = AUTH_SESSION_DEFAULT_LABEL
            st.session_state["page"] = AUTH_SESSION_DEFAULT_PAGE
            st.query_params["page"] = AUTH_SESSION_DEFAULT_PAGE
            st.rerun()
        else:
            st.error("Usuario ou senha invalidos.")
    return False


def render_sidebar_secure() -> tuple[str, str]:
    menu_map = {
        "📂 Módulos": "Modulos",
        "📊 Painel": "Painel",
        "👤 Novo Cliente": "Novo Cliente",
        "🏢 Empresas": "Empresas",
        "📋 Demandas": "Demandas",
        "🤖 Automação": "Automacao",
        "💰 Faturamento": "Faturamento",
        "💾 Backup": "Backup",
    }
    if can_access_users_page():
        menu_map["👥 Usuários"] = "usuarios"

    requested_page = normalize_page(st.query_params.get("page", st.session_state.get("page", "Modulos")) or "Modulos")
    if requested_page == "usuarios" and not can_access_users_page():
        st.warning("Você não tem permissão para acessar esta área.")
        requested_page = "Modulos"
        st.query_params["page"] = "Modulos"
        st.session_state["page"] = "Modulos"
        st.session_state["page_label"] = "📂 Módulos"

    requested_label = next((label for label, page in menu_map.items() if page == requested_page), "📂 Módulos")
    if requested_label not in menu_map:
        requested_label = st.session_state.get("page_label", "📂 Módulos")
    if requested_label not in menu_map:
        requested_label = "📂 Módulos"
    menu_items = list(menu_map.keys())
    menu_index = menu_items.index(requested_label)

    with st.sidebar:
        render_company_logo(72)
        st.markdown(
            f"<div style='margin:0.08rem 0 0.03rem 0; line-height:1.05;'><strong>Usuário:</strong> {current_user_display_name()}</div>"
            f"<div style='margin:0 0 0.08rem 0; line-height:1; color:var(--nexus-muted); font-size:0.88rem;'>Perfil: {user_role_label(current_user_role())}</div>",
            unsafe_allow_html=True,
        )
        page_label = st.radio("Menu", menu_items, index=menu_index, key="menu_secure")
        page = menu_map[page_label]
        st.session_state["page_label"] = page_label
        st.session_state["page"] = page
        if st.query_params.get("page") != page:
            st.query_params["page"] = page

        saved_competencia = (
            st.session_state.get("competencia")
            or st.session_state.get("ultima_competencia")
            or get_setting("ultima_competencia", current_competencia())
        )
        st.session_state["ultima_competencia"] = saved_competencia
        current_year, current_month = parse_competencia(saved_competencia)
        years = list(range(current_year - 5, current_year + 6))
        month_options = [f"{m:02d}" for m in range(1, 13)]
        y1, y2 = st.sidebar.columns(2)
        year = y1.selectbox("Ano", years, index=years.index(current_year), key="ano_secure")
        month = y2.selectbox("Mes", month_options, index=month_options.index(f"{current_month:02d}"), key="mes_secure")
        competencia = f"{int(year)}-{month}"
        st.session_state["competencia"] = competencia
        if st.session_state.get("ultima_competencia") != competencia:
            st.session_state["ultima_competencia"] = competencia
            set_setting("ultima_competencia", competencia)
        touch_active_session(page)
        active_now = load_active_sessions()
        st.caption(f"Online: {active_now['usuario'].nunique()} | Sessões: {len(active_now)}")
    return page, competencia


def render_usuarios() -> None:
    if not can_access_users_page():
        st.warning("Você não tem permissão para acessar esta área.")
        st.stop()

    st.title("Gestão de Usuários")
    st.caption("Crie, visualize e gerencie acessos ao sistema.")

    all_users = get_users_df()
    visible_users = get_visible_users_df()
    scope_df = visible_users.copy()

    if is_admin_geral():
        total_users = len(all_users)
        active_users = int((all_users["ativo"] == 1).sum()) if not all_users.empty else 0
        inactive_users = int((all_users["ativo"] == 0).sum()) if not all_users.empty else 0
        active_now = load_active_sessions()
        online_users = active_now["usuario"].nunique()
    else:
        total_users = len(scope_df)
        active_users = int((scope_df["ativo"] == 1).sum()) if not scope_df.empty else 0
        inactive_users = int((scope_df["ativo"] == 0).sum()) if not scope_df.empty else 0
        active_now = load_active_sessions()
        if not scope_df.empty:
            allowed_users = set(scope_df["username"].astype(str).str.upper().tolist())
            online_users = int(active_now["usuario"].astype(str).str.upper().isin(allowed_users).sum())
        else:
            online_users = 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", total_users)
    c2.metric("Ativos", active_users)
    c3.metric("Inativos", inactive_users)
    c4.metric("Online", int(online_users))

    if is_admin_geral() and not all_users.empty:
        role_counts = all_users["role"].fillna("usuario").value_counts().to_dict()
        cols = st.columns(min(4, len(role_counts)) or 1)
        for idx, (role, qty) in enumerate(role_counts.items()):
            cols[idx % len(cols)].metric(user_role_label(role), int(qty))

    filters = st.columns([1.3, 0.8, 0.8])
    search = filters[0].text_input("Buscar por nome ou login", key="usuarios_busca")
    role_options = ["Todos"] + list(USER_ROLES.keys())
    role_filter = filters[1].selectbox("Perfil", role_options, key="usuarios_perfil")
    status_filter = filters[2].selectbox("Status", ["Todos", "Ativos", "Inativos"], key="usuarios_status")

    filtered = scope_df.copy()
    if not filtered.empty and search:
        mask = (
            filtered["username"].astype(str).str.contains(search, case=False, na=False)
            | filtered["nome"].astype(str).str.contains(search, case=False, na=False)
        )
        filtered = filtered.loc[mask].copy()
    if not filtered.empty and role_filter != "Todos":
        filtered = filtered.loc[filtered["role"].astype(str).eq(role_filter)].copy()
    if not filtered.empty and status_filter == "Ativos":
        filtered = filtered.loc[filtered["ativo"] == 1].copy()
    if not filtered.empty and status_filter == "Inativos":
        filtered = filtered.loc[filtered["ativo"] == 0].copy()

    st.dataframe(
        filtered[["id", "username", "nome", "role", "ativo", "responsavel", "criado_por", "criado_em", "atualizado_em", "ultimo_login", "observacao"]]
        if not filtered.empty
        else filtered,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": st.column_config.NumberColumn("id"),
            "username": st.column_config.TextColumn("username"),
            "nome": st.column_config.TextColumn("nome"),
            "role": st.column_config.TextColumn("role"),
            "ativo": st.column_config.NumberColumn("ativo"),
            "responsavel": st.column_config.TextColumn("responsavel"),
            "criado_por": st.column_config.TextColumn("criado_por"),
            "criado_em": st.column_config.TextColumn("criado_em"),
            "atualizado_em": st.column_config.TextColumn("atualizado_em"),
            "ultimo_login": st.column_config.TextColumn("ultimo_login"),
            "observacao": st.column_config.TextColumn("observacao"),
        },
    )

    if can_manage_users():
        with st.expander("+ Criar novo usuário", expanded=is_admin_geral()):
            with st.form("create_user_form", clear_on_submit=True):
                nome = st.text_input("Nome")
                username = st.text_input("Usuário/login")
                if is_admin_geral():
                    role = st.selectbox("Perfil", list(USER_ROLES.keys()), index=3)
                    responsavel = st.text_input("Responsável")
                else:
                    role = st.selectbox("Perfil", ["estagiario", "usuario"], index=0)
                    responsavel = st.text_input("Responsável", value="RAFAEL", disabled=True)
                senha = st.text_input("Senha", type="password")
                confirmar = st.text_input("Confirmar senha", type="password")
                ativo = st.checkbox("Ativo", value=True)
                observacao = st.text_area("Observação")
                submit_create = st.form_submit_button("Criar usuário")
            if submit_create:
                username_norm = normalize_username(username)
                if not username_norm:
                    st.error("Usuário/login é obrigatório.")
                elif get_user_row(username_norm):
                    st.error("Já existe um usuário com esse login.")
                elif not senha or not confirmar:
                    st.error("Informe a senha e a confirmação.")
                elif len(senha) < PASSWORD_MIN_LENGTH:
                    st.error(f"A senha deve ter pelo menos {PASSWORD_MIN_LENGTH} caracteres.")
                elif senha != confirmar:
                    st.error("Senha e confirmação não conferem.")
                elif not is_admin_geral() and role not in {"estagiario", "usuario"}:
                    st.error("RAFAEL não pode criar esse perfil.")
                else:
                    responsavel_final = normalize_username(responsavel) if is_admin_geral() else "RAFAEL"
                    if not is_admin_geral():
                        responsavel_final = "RAFAEL"
                    upsert_user_record(
                        username=username_norm,
                        nome=nome or username_norm,
                        senha_hash=hash_password(senha),
                        role=role,
                        ativo=1 if ativo else 0,
                        criado_por=current_username(),
                        responsavel=responsavel_final or username_norm,
                        observacao=observacao,
                    )
                    st.success("Usuário criado com sucesso.")
                    st.rerun()

    if filtered.empty:
        st.info("Nenhum usuário encontrado com os filtros aplicados.")
        return

    for _, row in filtered.sort_values(["username"]).iterrows():
        username = str(row["username"])
        display_title = f'{username} - {row.get("nome", "")}'.strip(" -")
        with st.expander(display_title, expanded=False):
            editable = can_manage_user(row)
            if not editable:
                st.info("Você não tem permissão para editar este usuário.")
                continue
            row_role = str(row.get("role") or "usuario")
            is_special_user = normalize_username(username) in SPECIAL_USER_ROLES
            with st.form(f"edit_user_{row['id']}"):
                nome = st.text_input("Nome", value=str(row.get("nome", "")))
                if is_admin_geral() and not is_special_user:
                    role = st.selectbox("Perfil", list(USER_ROLES.keys()), index=list(USER_ROLES.keys()).index(row_role) if row_role in USER_ROLES else 3)
                    responsavel = st.text_input("Responsável", value=str(row.get("responsavel", "")))
                    criado_por = st.text_input("Criado por", value=str(row.get("criado_por", "")))
                else:
                    role = row_role
                    responsavel = str(row.get("responsavel", ""))
                    criado_por = str(row.get("criado_por", ""))
                    st.text_input("Perfil", value=user_role_label(role), disabled=True)
                    st.text_input("Responsável", value=responsavel, disabled=True)
                ativo = st.checkbox("Ativo", value=int(row.get("ativo", 1) or 1) == 1)
                observacao = st.text_area("Observação", value=str(row.get("observacao", "")))
                submit_edit = st.form_submit_button("Salvar alterações")
            if submit_edit:
                role_final = row_role if not is_admin_geral() or is_special_user else role
                if not is_admin_geral() and role_final not in {"estagiario", "usuario", "contador"}:
                    st.error("Perfil não permitido para este usuário.")
                    continue
                if normalize_username(username) == "DMLIMA":
                    role_final = "admin_geral"
                    responsavel = "DMLIMA"
                if normalize_username(username) == "RAFAEL":
                    role_final = "contador"
                    responsavel = "RAFAEL"
                if int(row.get("ativo", 1) or 1) == 1 and not ativo and not can_disable_user_record(row.to_dict()):
                    st.error("Não é permitido desativar o último administrador ativo.")
                    continue
                execute(
                    """
                    UPDATE users
                       SET nome=?,
                           role=?,
                           ativo=?,
                           responsavel=?,
                           criado_por=?,
                           observacao=?,
                           atualizado_em=?
                     WHERE id=?
                    """,
                    (
                        nome,
                        role_final,
                        1 if ativo else 0,
                        normalize_username(responsavel) or normalize_username(username),
                        normalize_username(criado_por) or str(row.get("criado_por", "")),
                        observacao,
                        now_str(),
                        int(row["id"]),
                    ),
                )
                st.success("Usuário atualizado.")
                st.rerun()

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if int(row.get("ativo", 1) or 1) == 1:
                    disable_confirm = st.checkbox("Confirmo a desativação", key=f"disable_confirm_{row['id']}")
                    if st.button("Desativar", key=f"disable_btn_{row['id']}", disabled=not disable_confirm):
                        if not can_disable_user_record(row.to_dict()):
                            st.error("Não é permitido desativar o último administrador ativo.")
                        else:
                            execute("UPDATE users SET ativo=0, atualizado_em=? WHERE id=?", (now_str(), int(row["id"])))
                            st.success("Usuário desativado.")
                            st.rerun()
                else:
                    if st.button("Reativar", key=f"reactivate_btn_{row['id']}"):
                        execute("UPDATE users SET ativo=1, atualizado_em=? WHERE id=?", (now_str(), int(row["id"])))
                        st.success("Usuário reativado.")
                        st.rerun()
            with col_b:
                with st.form(f"reset_pwd_{row['id']}"):
                    nova_senha = st.text_input("Nova senha", type="password")
                    confirmar_nova = st.text_input("Confirmar nova senha", type="password")
                    submit_reset = st.form_submit_button("Resetar senha")
                if submit_reset:
                    if not nova_senha or len(nova_senha) < PASSWORD_MIN_LENGTH:
                        st.error(f"A senha deve ter pelo menos {PASSWORD_MIN_LENGTH} caracteres.")
                    elif nova_senha != confirmar_nova:
                        st.error("Senha e confirmação não conferem.")
                    else:
                        execute(
                            "UPDATE users SET senha_hash=?, atualizado_em=? WHERE id=?",
                            (hash_password(nova_senha), now_str(), int(row["id"])),
                        )
                        st.success("Senha redefinida.")
                        st.rerun()
            with col_c:
                st.caption(f"Criado em: {row.get('criado_em', '')}")
                st.caption(f"Último login: {row.get('ultimo_login', '')}")


def render_modulos() -> None:
    left_pad, content_col, right_pad = st.columns([0.12, 0.76, 0.12])
    with content_col:
        st.markdown(
            """
            <div class="launcher-shell">
                <div class="launcher-kicker">Portal Principal | Selecao de modulo</div>
                <div class="launcher-title">Acesso ao SISTEMA EXCELENCIA CONTABILIDADE</div>
                <div class="launcher-subtitle">Selecione o ambiente de trabalho para iniciar sua operacao.</div>
            </div>
            <div class="launcher-grid-wrap">
            """,
            unsafe_allow_html=True,
        )
        for start in range(0, len(MODULES), 2):
            cols = st.columns(2, gap="small")
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
                        target = normalize_page(str(item["page"]))
                        label = next((menu_label for menu_label, menu_page in NAV_MENU.items() if menu_page == target), item["title"])
                        st.button(
                            "Acessar modulo",
                            key=f"module_open_{safe_key}",
                            use_container_width=False,
                            on_click=set_navigation_target,
                            args=(target, label),
                        )
                    else:
                        st.button("Disponivel em breve", key=f"module_disabled_{safe_key}", disabled=True)
        st.markdown("</div>", unsafe_allow_html=True)
    return

    st.markdown(
        """
        <div class="launcher-shell">
            <div class="launcher-kicker">Portal Principal | Selecao de modulo</div>
            <div class="launcher-title">Acesso ao SISTEMA EXCELENCIA CONTABILIDADE</div>
            <div class="launcher-subtitle">Selecione o ambiente de trabalho para iniciar sua operacao.</div>
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
                    target = normalize_page(str(item["page"]))
                    label = next((menu_label for menu_label, menu_page in NAV_MENU.items() if menu_page == target), item["title"])
                    if st.button("🚀 Acessar módulo", key=f"module_open_{safe_key}", use_container_width=False):
                        navigate_to_page(target, label)
                else:
                    st.button("Disponível em breve", key=f"module_disabled_{safe_key}", disabled=True)
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
    c4.metric("Demandas do mes", total_demandas)
    c5.metric("Concluidas", concluidas)
    c6.metric("Pendentes", pendentes)

    st.caption(f"Competencia selecionada: {competencia}")

    if demandas.empty:
        st.info("Sem demandas para esta competencia. O painel continua mostrando os demais indicadores do banco.")

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
            st.write("Sem dados para consolidar nesta competencia.")
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
            st.info("Sem faturamento MEI para esta competencia.")
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
                    "observacao": st.column_config.TextColumn("Observacao", width=180),
                },
            )

    c_left, c_right = st.columns([1.05, 0.95])
    with c_left:
        st.subheader("Pendencias")
        pendentes_df = demandas[demandas["feito"] == 0][["demanda", "razao_social", "cnpj", "regime", "observacao"]] if not demandas.empty else demandas
        if pendentes_df.empty:
            st.success("Nenhuma pendencia aberta nesta competencia.")
        else:
            show_table(
                pendentes_df,
                key=f"painel_pendentes_{competencia}",
                height=320,
                editable=False,
                disabled=True,
                column_config={
                    "demanda": st.column_config.TextColumn("Demanda", width=220),
                    "razao_social": st.column_config.TextColumn("Razao social", width=300),
                    "cnpj": st.column_config.TextColumn("CNPJ", width=150),
                    "regime": st.column_config.TextColumn("Regime", width=120),
                    "observacao": st.column_config.TextColumn("Observacao", width=260),
                },
            )

    with c_right:
        st.subheader("Leitura rapida")
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
            st.caption("Top clientes com pendencias")
            if top_pendentes.empty:
                st.write("Sem pendencias por cliente.")
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
                        "pendencias": st.column_config.NumberColumn("Pendencias", width=100),
                    },
                )

    if not demandas.empty:
        st.subheader("Ultimas movimentacoes")
        ultimas = demandas.sort_values(["atualizado_em", "id"], ascending=[False, False]).head(12)
        show_table(
            ultimas[["demanda", "razao_social", "status", "atualizado_em", "observacao"]],
            key=f"painel_ultimas_{competencia}",
            height=260,
            editable=False,
            disabled=True,
            column_config={
                "demanda": st.column_config.TextColumn("Demanda", width=220),
                "razao_social": st.column_config.TextColumn("Razao social", width=280),
                "status": st.column_config.TextColumn("Status", width=110),
                "atualizado_em": st.column_config.TextColumn("Atualizado em", width=160),
                "observacao": st.column_config.TextColumn("Observacao", width=240),
            },
        )


def reset_empresa_cadastro_on_state() -> None:
    st.session_state["empresa_cadastro_on_open"] = False
    st.session_state["empresa_cadastro_on_mode"] = "lookup"
    st.session_state["empresa_cadastro_on_result"] = {}
    st.session_state["empresa_cadastro_on_error"] = ""
    st.session_state["empresa_cadastro_on_existing_id"] = 0
    st.session_state["empresa_cadastro_on_lookup_value"] = ""


def render_empresa_cadastro_on_panel() -> None:
    if not st.session_state.get("empresa_cadastro_on_open", False):
        return

    with st.container(border=True):
        st.markdown("<h5 style='margin-top: 0px; margin-bottom: 4px;'>Cadastro On / Incluir por CNPJ</h5>", unsafe_allow_html=True)
        st.caption("Digite apenas o CNPJ. Se existir na base, o sistema oferece atualizar os dados cadastrais.")
        with st.form("empresa_cadastro_on_lookup_form", clear_on_submit=False):
            cnpj_lookup = st.text_input("CNPJ", value=str(st.session_state.get("empresa_cadastro_on_lookup_value", "")))
            c1, c2 = st.columns(2)
            submit_lookup = c1.form_submit_button(f"{BUTTON_LABELS['buscar']} e incluir", type="primary")
            cancel_lookup = c2.form_submit_button(BUTTON_LABELS["cancelar"], key="btn_cadastro_on_cancelar")

        if cancel_lookup:
            reset_empresa_cadastro_on_state()
            st.rerun()

        if submit_lookup:
            digits = cnpj_digits(cnpj_lookup)
            st.session_state["empresa_cadastro_on_lookup_value"] = digits
            if len(digits) != 14:
                st.session_state["empresa_cadastro_on_error"] = "CNPJ invalido. Informe 14 digitos."
                st.session_state["empresa_cadastro_on_mode"] = "manual"
                st.rerun()

            existing = empresa_row_by_cnpj(normalize_cnpj(digits))
            try:
                lookup_data = fetch_empresa_cadastro_on(digits)
                lookup_data["cnpj"] = digits
                if existing:
                    st.session_state["empresa_cadastro_on_result"] = lookup_data
                    st.session_state["empresa_cadastro_on_existing_id"] = int(existing.get("id", 0) or 0)
                    st.session_state["empresa_cadastro_on_error"] = "CNPJ ja cadastrado. Use a atualizacao para trazer os dados cadastrais mais recentes."
                    st.session_state["empresa_cadastro_on_mode"] = "review"
                    st.rerun()

                save_empresa(lookup_data, None)
                st.session_state["empresa_save_notice"] = f"Cliente incluido com sucesso por CNPJ {normalize_cnpj(digits)}."
                reset_empresa_cadastro_on_state()
                st.rerun()
            except Exception as exc:
                st.session_state["empresa_cadastro_on_error"] = str(exc)
                st.session_state["empresa_cadastro_on_mode"] = "manual"
                if existing:
                    st.session_state["empresa_cadastro_on_result"] = existing
                    st.session_state["empresa_cadastro_on_existing_id"] = int(existing.get("id", 0) or 0)
                st.rerun()

        if st.session_state.get("empresa_cadastro_on_error"):
            st.error(st.session_state["empresa_cadastro_on_error"])

        if st.session_state.get("empresa_cadastro_on_mode") == "review" and st.session_state.get("empresa_cadastro_on_result"):
            review_data = st.session_state["empresa_cadastro_on_result"]
            existing_id = int(st.session_state.get("empresa_cadastro_on_existing_id", 0) or 0)
            st.info(
                f"CNPJ localizado. Razao social: {review_data.get('razao_social', '')}. "
                "Clique para atualizar os dados cadastrais do cliente existente."
            )
            c1, c2 = st.columns(2)
            if c1.button(f"{BUTTON_LABELS['atualizar']} dados cadastrais", key="btn_cadastro_on_atualizar", type="primary", use_container_width=True):
                save_empresa(review_data, existing_id)
                st.session_state["empresa_save_notice"] = f"Dados cadastrais atualizados para {normalize_cnpj(review_data.get('cnpj', ''))}."
                reset_empresa_cadastro_on_state()
                st.rerun()
            if c2.button(BUTTON_LABELS["cancelar"], key="btn_cadastro_on_cancelar_review", use_container_width=True):
                reset_empresa_cadastro_on_state()
                st.rerun()

        if st.session_state.get("empresa_cadastro_on_mode") == "manual":
            base_row = st.session_state.get("empresa_cadastro_on_result") or {}
            with st.form("empresa_cadastro_on_manual_form", clear_on_submit=False):
                m1, m2 = st.columns(2)
                manual_cnpj = m1.text_input("CNPJ", value=st.session_state.get("empresa_cadastro_on_lookup_value", ""))
                manual_razao = m2.text_input("Razao social", value=str(base_row.get("razao_social", "")))
                manual_fantasia = m1.text_input("Nome fantasia", value=str(base_row.get("nome_fantasia", "")))
                manual_apelido = m2.text_input("Apelido", value=str(base_row.get("apelido", "")))
                manual_regime = m1.selectbox("Regime", REGIMES, index=REGIMES.index(_regime_option(base_row.get("regime", REGIMES[0]))) if _regime_option(base_row.get("regime", REGIMES[0])) in REGIMES else 0)
                manual_cidade = m2.text_input("Cidade", value=str(base_row.get("cidade", "")))
                manual_uf = m1.text_input("UF", value=str(base_row.get("uf", "")), max_chars=2)
                manual_abertura = m2.text_input("Abertura", value=str(base_row.get("abertura", "")))
                manual_situacao = m1.text_input("Situação", value=str(base_row.get("situacao", "")))
                manual_porte = m2.text_input("Porte", value=str(base_row.get("porte", "")))
                manual_natureza = m1.text_input("Natureza jurídica", value=str(base_row.get("natureza_juridica", "")))
                manual_capital = m2.text_input("Capital social", value=str(base_row.get("capital_social", "")))
                manual_simples = m1.checkbox("Simples optante", value=int(base_row.get("simples_optante", 0) or 0) == 1)
                manual_mei = m2.checkbox("MEI optante", value=int(base_row.get("mei_optante", 0) or 0) == 1)
                manual_inativo = st.checkbox("Inativa", value=int(base_row.get("inativo", 0) or 0) == 1)
                b1, b2 = st.columns(2)
                submit_manual = b1.form_submit_button(f"{BUTTON_LABELS['salvar']} manualmente", type="primary")
                cancel_manual = b2.form_submit_button(BUTTON_LABELS["cancelar"], key="btn_cadastro_on_cancelar_manual")
            if cancel_manual:
                reset_empresa_cadastro_on_state()
                st.rerun()
            if submit_manual:
                manual_payload = {
                    "cnpj": manual_cnpj,
                    "razao_social": manual_razao,
                    "nome_fantasia": manual_fantasia,
                    "apelido": manual_apelido,
                    "regime": manual_regime,
                    "cidade": manual_cidade,
                    "uf": manual_uf,
                    "abertura": manual_abertura,
                    "situacao": manual_situacao,
                    "porte": manual_porte,
                    "natureza_juridica": manual_natureza,
                    "capital_social": manual_capital,
                    "simples_optante": 1 if manual_simples else 0,
                    "mei_optante": 1 if manual_mei else 0,
                    "inativo": 1 if manual_inativo else 0,
                }
                if len(cnpj_digits(manual_cnpj)) != 14:
                    st.error("CNPJ invalido. Informe 14 digitos.")
                elif not manual_razao.strip():
                    st.error("Razao social e obrigatoria.")
                else:
                    existing_id = int(st.session_state.get("empresa_cadastro_on_existing_id", 0) or 0)
                    save_empresa(manual_payload, existing_id or None)
                    st.session_state["empresa_save_notice"] = "Cadastro salvo manualmente."
                    reset_empresa_cadastro_on_state()
                    st.rerun()


def reset_empresa_cadastro_on_state() -> None:
    st.session_state["show_cadastro_on"] = False
    st.session_state["empresa_cadastro_on_mode"] = "lookup"
    st.session_state["empresa_cadastro_on_result"] = {}
    st.session_state["empresa_cadastro_on_error"] = ""
    st.session_state["empresa_cadastro_on_existing_id"] = 0
    st.session_state["empresa_cadastro_on_lookup_value"] = ""


def clear_empresa_cadastro_on_state() -> None:
    st.session_state["empresa_cadastro_on_mode"] = "lookup"
    st.session_state["empresa_cadastro_on_result"] = {}
    st.session_state["empresa_cadastro_on_error"] = ""
    st.session_state["empresa_cadastro_on_existing_id"] = 0
    st.session_state["empresa_cadastro_on_lookup_value"] = ""


def render_empresa_cadastro_on_panel() -> None:
    if not st.session_state.get("show_cadastro_on", False):
        return

    with st.container(border=True):
        head_left, head_right = st.columns([3, 1])
        head_left.markdown(
            "<h5 style='margin-top:0;margin-bottom:4px;'>Cadastro On / Incluir por CNPJ</h5>",
            unsafe_allow_html=True,
        )
        if head_right.button("❌ Fechar Cadastro On", use_container_width=True):
            reset_empresa_cadastro_on_state()
            st.rerun()

        st.caption("Digite o CNPJ, busque os dados e complete manualmente antes de salvar.")

        with st.form("form_cadastro_on_cnpj", clear_on_submit=False):
            lookup_value = st.text_input(
                "CNPJ",
                value=str(st.session_state.get("empresa_cadastro_on_lookup_value", "")),
                placeholder="Digite apenas números",
            )
            submitted_lookup = st.form_submit_button("🔎 Buscar dados")

        if submitted_lookup:
            digits = cnpj_digits(lookup_value)
            st.session_state["empresa_cadastro_on_lookup_value"] = digits
            if len(digits) != 14:
                st.session_state["empresa_cadastro_on_error"] = "CNPJ inválido. Informe 14 dígitos."
                st.session_state["empresa_cadastro_on_mode"] = "lookup"
                st.rerun()

            fetched = {}
            try:
                fetched = fetch_empresa_cadastro_on(digits)
            except Exception as exc:
                st.session_state["empresa_cadastro_on_error"] = str(exc) or "Falha ao buscar dados do CNPJ."

            existing = empresa_row_by_cnpj(normalize_cnpj(digits))
            if existing:
                st.warning("CNPJ já cadastrado.")
                st.session_state["empresa_cadastro_on_existing_id"] = int(existing.get("id", 0) or 0)
                base_row = {**existing, **fetched}
            else:
                st.session_state["empresa_cadastro_on_existing_id"] = 0
                base_row = fetched

            base_row["cnpj"] = normalize_cnpj(digits)
            st.session_state["empresa_cadastro_on_result"] = base_row
            st.session_state["empresa_cadastro_on_mode"] = "edit"
            st.rerun()

        if st.session_state.get("empresa_cadastro_on_error"):
            st.error(st.session_state["empresa_cadastro_on_error"])

        base_row = st.session_state.get("empresa_cadastro_on_result") or {}
        if st.session_state.get("empresa_cadastro_on_mode") == "edit":
            with st.container(border=True):
                st.markdown("#### Dados cadastrais")
                with st.form("form_cadastro_on_dados", clear_on_submit=False):
                    c1, c2 = st.columns(2)
                    cnpj = c1.text_input("CNPJ", value=str(base_row.get("cnpj", st.session_state.get("empresa_cadastro_on_lookup_value", ""))), disabled=True)
                    razao = c2.text_input("Razão social", value=str(base_row.get("razao_social", "")))
                    fantasia = c1.text_input("Nome fantasia", value=str(base_row.get("nome_fantasia", "")))
                    apelido = c2.text_input("Apelido", value=str(base_row.get("apelido", "")))
                    regime = c1.selectbox(
                        "Regime",
                        REGIMES,
                        index=REGIMES.index(_regime_option(base_row.get("regime", REGIMES[0]))) if _regime_option(base_row.get("regime", REGIMES[0])) in REGIMES else 0,
                    )
                    existing_id_for_regime = int(st.session_state.get("empresa_cadastro_on_existing_id", 0) or 0)
                    existing_regime = _regime_option(empresa_row(existing_id_for_regime).get("regime", "")) if existing_id_for_regime else ""
                    regime_vigencia = ""
                    if existing_regime and regime != existing_regime:
                        regime_vigencia = c2.date_input("Vigencia do regime").isoformat()
                    abertura = c2.text_input("Abertura", value=str(base_row.get("abertura", "")))
                    natureza_juridica = c1.text_input("Natureza jurídica", value=str(base_row.get("natureza_juridica", "")))
                    situacao = c2.text_input("Situação", value=str(base_row.get("situacao", "")))
                    capital_social = c1.text_input("Capital social", value=str(base_row.get("capital_social", "")))
                    porte = c2.text_input("Porte", value=str(base_row.get("porte", "")))
                    cidade = c1.text_input("Cidade", value=str(base_row.get("cidade", "")))
                    uf = c2.text_input("UF", value=str(base_row.get("uf", "")), max_chars=2)
                    simples_optante = c1.checkbox("Simples optante", value=int(base_row.get("simples_optante", 0) or 0) == 1)
                    mei_optante = c2.checkbox("MEI optante", value=int(base_row.get("mei_optante", 0) or 0) == 1)
                    mensalidade = c1.text_input("Mensalidade", value=str(base_row.get("mensalidade", "")))
                    inativo = c2.checkbox("Inativa", value=int(base_row.get("inativo", 0) or 0) == 1)

                    b1, b2, b3 = st.columns(3)
                    save_clicked = b1.form_submit_button("💾 Salvar cliente")
                    clear_clicked = b2.form_submit_button("🧹 Limpar")
                    cancel_clicked = b3.form_submit_button("❌ Cancelar")

                if clear_clicked:
                    clear_empresa_cadastro_on_state()
                    st.rerun()

                if cancel_clicked:
                    reset_empresa_cadastro_on_state()
                    st.rerun()

                if save_clicked:
                    if len(cnpj_digits(cnpj)) != 14:
                        st.error("CNPJ inválido. Informe 14 dígitos.")
                    elif not razao.strip():
                        st.error("Razão social é obrigatória.")
                    else:
                        payload = {
                            "cnpj": cnpj,
                            "razao_social": razao,
                            "nome_fantasia": fantasia,
                            "apelido": apelido,
                            "regime": regime,
                            "abertura": abertura,
                            "natureza_juridica": natureza_juridica,
                            "situacao": situacao,
                            "capital_social": capital_social,
                            "cidade": cidade,
                            "uf": uf,
                            "porte": porte,
                            "simples_optante": 1 if simples_optante else 0,
                            "mei_optante": 1 if mei_optante else 0,
                            "mensalidade": mensalidade,
                            "inativo": 1 if inativo else 0,
                            "regime_vigencia": regime_vigencia,
                        }
                        existing_id = int(st.session_state.get("empresa_cadastro_on_existing_id", 0) or 0)
                        if not existing_id:
                            existing_now = empresa_row_by_cnpj(normalize_cnpj(cnpj))
                            if existing_now:
                                existing_id = int(existing_now.get("id", 0) or 0)
                        save_empresa(payload, existing_id or None)
                        st.session_state["empresa_save_notice"] = "✅ Cliente salvo com sucesso"
                        st.toast("✅ Cliente salvo com sucesso")
                        reset_empresa_cadastro_on_state()
                        st.session_state["page"] = "Empresas"
                        st.query_params["page"] = "Empresas"
                        st.rerun()


def _selected_empresa_options(df: pd.DataFrame) -> list[int]:
    if df.empty or "id" not in df.columns:
        return []
    return [int(x) for x in df["id"].dropna().astype(int).tolist()]


def _empresa_option_label(empresa_id: int) -> str:
    row = empresa_row(int(empresa_id))
    if not row:
        return str(empresa_id)
    return f"{row.get('id')} - {row.get('apelido') or row.get('razao_social')} ({row.get('cnpj')})"


def _empresa_payload_from_form(
    *,
    cnpj: str,
    razao_social: str,
    nome_fantasia: str,
    apelido: str,
    regime: str,
    mensalidade: str,
    cidade: str,
    uf: str,
    funcionarios: bool,
    inativo: bool,
    abertura: str = "",
    natureza_juridica: str = "",
    situacao: str = "",
    capital_social: str = "",
    porte: str = "",
    simples_optante: bool = False,
    mei_optante: bool = False,
    link_rapido: str = "",
    senhas_acessos: str = "",
    observacoes: str = "",
    regime_vigencia: str = "",
) -> dict:
    return {
        "cnpj": cnpj,
        "razao_social": razao_social,
        "nome_fantasia": nome_fantasia,
        "apelido": apelido,
        "regime": regime,
        "mensalidade": mensalidade,
        "cidade": cidade,
        "uf": uf,
        "funcionarios": 1 if funcionarios else 0,
        "inativo": 1 if inativo else 0,
        "abertura": abertura,
        "natureza_juridica": natureza_juridica,
        "situacao": situacao,
        "capital_social": capital_social,
        "porte": porte,
        "simples_optante": 1 if simples_optante else 0,
        "mei_optante": 1 if mei_optante else 0,
        "link_rapido": link_rapido,
        "senhas_acessos": senhas_acessos,
        "observacoes": observacoes,
        "regime_vigencia": regime_vigencia,
    }


def apply_cadastro_on_to_editor_state(empresa_id: int, prefix: str) -> None:
    row = empresa_row(int(empresa_id))
    cnpj = row.get("cnpj", "") if row else ""
    if not cnpj_valido(cnpj):
        st.error("Empresa sem CNPJ valido para Cadastro On.")
        return
    try:
        info = fetch_empresa_cadastro_on(cnpj)
    except Exception as exc:
        st.error(f"Falha no Cadastro On: {exc}")
        return
    for key in [
        "cnpj",
        "razao_social",
        "nome_fantasia",
        "apelido",
        "regime",
        "abertura",
        "natureza_juridica",
        "situacao",
        "capital_social",
        "cidade",
        "uf",
        "porte",
        "simples_optante",
        "mei_optante",
    ]:
        st.session_state[f"{prefix}_{key}_{empresa_id}"] = info.get(key, "")
    st.toast("Dados do Cadastro On carregados para revisao.")


def render_empresa_quick_editor(empresa_id: int) -> None:
    row = empresa_row(int(empresa_id))
    if not row:
        st.warning("Empresa selecionada nao encontrada.")
        return

    with st.container(border=True):
        st.markdown("#### Edicao rapida")
        with st.form(f"empresa_quick_form_{empresa_id}", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            cnpj = c1.text_input("CNPJ", value=str(row.get("cnpj", "")), key=f"quick_cnpj_{empresa_id}")
            razao = c2.text_input("Razao Social", value=str(row.get("razao_social", "")), key=f"quick_razao_social_{empresa_id}")
            fantasia = c3.text_input("Nome Fantasia", value=str(row.get("nome_fantasia", "")), key=f"quick_nome_fantasia_{empresa_id}")
            apelido = c1.text_input("Apelido", value=str(row.get("apelido", "")), key=f"quick_apelido_{empresa_id}")
            regime_before = _regime_option(row.get("regime", REGIMES[0]))
            regime = c2.selectbox("Regime", REGIMES, index=REGIMES.index(regime_before), key=f"quick_regime_{empresa_id}")
            mensalidade = c3.text_input("Mensalidade", value=str(row.get("mensalidade", "")), key=f"quick_mensalidade_{empresa_id}")
            cidade = c1.text_input("Cidade", value=str(row.get("cidade", "")), key=f"quick_cidade_{empresa_id}")
            uf = c2.text_input("UF", value=str(row.get("uf", "")), max_chars=2, key=f"quick_uf_{empresa_id}")
            funcionarios = c3.checkbox("Tem funcionarios", value=int(row.get("funcionarios", 0) or 0) == 1, key=f"quick_funcionarios_{empresa_id}")
            inativo = c1.checkbox("Inativo", value=int(row.get("inativo", 0) or 0) == 1, key=f"quick_inativo_{empresa_id}")
            regime_vigencia = ""
            if regime != regime_before:
                regime_vigencia = c2.date_input("Vigencia do regime").isoformat()
            b1, b2, b3, b4 = st.columns(4)
            save_clicked = b1.form_submit_button("Salvar")
            cadastro_on_clicked = b2.form_submit_button("Cadastro On")
            full_clicked = b3.form_submit_button("Editar completo")
            trash_clicked = b4.form_submit_button("Mover para lixeira")

        if cadastro_on_clicked:
            apply_cadastro_on_to_editor_state(empresa_id, "quick")
            st.rerun()
        if full_clicked:
            st.session_state["empresa_full_edit_id"] = int(empresa_id)
            st.rerun()
        if trash_clicked:
            move_empresa_to_trash(int(empresa_id))
            st.toast("Empresa movida para a lixeira.")
            st.session_state["empresa_quick_edit_id"] = 0
            st.rerun()
        if save_clicked:
            payload = _empresa_payload_from_form(
                cnpj=cnpj,
                razao_social=razao,
                nome_fantasia=fantasia,
                apelido=apelido,
                regime=regime,
                mensalidade=mensalidade,
                cidade=cidade,
                uf=uf,
                funcionarios=funcionarios,
                inativo=inativo,
                regime_vigencia=regime_vigencia,
            )
            save_empresa(payload, int(empresa_id))
            st.toast("Empresa atualizada.")
            st.rerun()


def render_editor_empresa(emp_id: int) -> None:
    row = empresa_row(int(emp_id))
    if not row:
        st.warning("Empresa selecionada nao encontrada.")
        return

    with st.container(border=True):
        st.markdown(f"#### Editor completo - {row.get('razao_social', '')}")
        regime_before = _regime_option(row.get("regime", REGIMES[0]))
        with st.form(f"empresa_full_form_{emp_id}", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            cnpj = c1.text_input("CNPJ", value=str(row.get("cnpj", "")), key=f"full_cnpj_{emp_id}")
            razao = c2.text_input("Razao Social", value=str(row.get("razao_social", "")), key=f"full_razao_social_{emp_id}")
            fantasia = c3.text_input("Nome Fantasia", value=str(row.get("nome_fantasia", "")), key=f"full_nome_fantasia_{emp_id}")
            apelido = c1.text_input("Apelido", value=str(row.get("apelido", "")), key=f"full_apelido_{emp_id}")
            regime = c2.selectbox("Regime", REGIMES, index=REGIMES.index(regime_before), key=f"full_regime_{emp_id}")
            mensalidade = c3.text_input("Mensalidade", value=str(row.get("mensalidade", "")), key=f"full_mensalidade_{emp_id}")
            funcionarios = c1.checkbox("Tem funcionarios", value=int(row.get("funcionarios", 0) or 0) == 1, key=f"full_funcionarios_{emp_id}")
            abertura = c2.text_input("Abertura", value=str(row.get("abertura", "")), key=f"full_abertura_{emp_id}")
            natureza = c3.text_input("Natureza Juridica", value=str(row.get("natureza_juridica", "")), key=f"full_natureza_juridica_{emp_id}")
            situacao = c1.text_input("Situacao", value=str(row.get("situacao", "")), key=f"full_situacao_{emp_id}")
            capital = c2.text_input("Capital Social", value=str(row.get("capital_social", "")), key=f"full_capital_social_{emp_id}")
            cidade = c3.text_input("Cidade", value=str(row.get("cidade", "")), key=f"full_cidade_{emp_id}")
            uf = c1.text_input("UF", value=str(row.get("uf", "")), max_chars=2, key=f"full_uf_{emp_id}")
            porte = c2.text_input("Porte", value=str(row.get("porte", "")), key=f"full_porte_{emp_id}")
            simples = c1.checkbox("Simples Optante", value=int(row.get("simples_optante", 0) or 0) == 1, key=f"full_simples_optante_{emp_id}")
            mei = c2.checkbox("MEI Optante", value=int(row.get("mei_optante", 0) or 0) == 1, key=f"full_mei_optante_{emp_id}")
            inativo = c3.checkbox("Inativo", value=int(row.get("inativo", 0) or 0) == 1, key=f"full_inativo_{emp_id}")
            link_rapido = st.text_input("Link rapido", value=str(row.get("link_rapido", "")), key=f"full_link_rapido_{emp_id}")
            senhas = st.text_area("Senhas/Acessos", value=str(row.get("senhas_acessos", "")), key=f"full_senhas_acessos_{emp_id}")
            observacoes = st.text_area("Observacoes", value=str(row.get("observacoes", "")), key=f"full_observacoes_{emp_id}")
            regime_vigencia = ""
            if regime != regime_before:
                regime_vigencia = st.date_input("Data de vigencia do novo regime").isoformat()
            b1, b2, b3, b4, b5 = st.columns(5)
            save_clicked = b1.form_submit_button("Salvar")
            cadastro_on_clicked = b2.form_submit_button("Cadastro On")
            trash_clicked = b3.form_submit_button("Mover lixeira")
            back_clicked = b4.form_submit_button("Voltar")

        if cadastro_on_clicked:
            apply_cadastro_on_to_editor_state(emp_id, "full")
            st.rerun()
        if back_clicked:
            st.session_state["empresa_full_edit_id"] = 0
            st.rerun()
        if trash_clicked:
            move_empresa_to_trash(int(emp_id))
            st.toast("Empresa movida para a lixeira.")
            st.session_state["empresa_full_edit_id"] = 0
            st.rerun()
        if save_clicked:
            payload = _empresa_payload_from_form(
                cnpj=cnpj,
                razao_social=razao,
                nome_fantasia=fantasia,
                apelido=apelido,
                regime=regime,
                mensalidade=mensalidade,
                cidade=cidade,
                uf=uf,
                funcionarios=funcionarios,
                inativo=inativo,
                abertura=abertura,
                natureza_juridica=natureza,
                situacao=situacao,
                capital_social=capital,
                porte=porte,
                simples_optante=simples,
                mei_optante=mei,
                link_rapido=link_rapido,
                senhas_acessos=senhas,
                observacoes=observacoes,
                regime_vigencia=regime_vigencia,
            )
            save_empresa(payload, int(emp_id))
            st.toast("Empresa salva.")

            checked_tipos = []
            for tipo_code, label in DEMAND_TYPES:
                if st.session_state.get(f"demanda_vinc_{emp_id}_{tipo_code}", False):
                    checked_tipos.append(tipo_code)
            save_empresa_demandas(int(emp_id), checked_tipos)
            st.rerun()

        l1, l2, l3 = st.columns(3)
        l1.link_button("Abrir CNPJ.biz", cnpj_biz_url(row.get("cnpj", "")), use_container_width=True)
        l2.text_input("Copiar CNPJ", value=str(row.get("cnpj", "")), key=f"copy_cnpj_{emp_id}")
        l3.caption(f"Atualizado em: {row.get('atualizado_em', '')}")

        st.markdown("##### Demandas vinculadas")
        selected_tipos = load_empresa_demandas(int(emp_id))
        cols = st.columns(3)
        for idx, (tipo_code, label) in enumerate(DEMAND_TYPES):
            with cols[idx % 3]:
                st.checkbox(label, value=tipo_code in selected_tipos, key=f"demanda_vinc_{emp_id}_{tipo_code}")
        if st.button("Salvar demandas vinculadas", key=f"save_demandas_vinc_{emp_id}", type="primary"):
            checked_tipos = [
                tipo_code for tipo_code, _ in DEMAND_TYPES
                if st.session_state.get(f"demanda_vinc_{emp_id}_{tipo_code}", False)
            ]
            save_empresa_demandas(int(emp_id), checked_tipos)
            st.toast("Demandas vinculadas salvas.")
            st.rerun()

        hist = load_historico_regime(int(emp_id))
        if not hist.empty:
            st.markdown("##### Historico de regime")
            show_table(hist, key=f"hist_regime_{emp_id}", auto_height=True, row_height=28, editable=False, disabled=True)


def render_empresas() -> None:
    st.markdown("**Empresas**")

    if msg := st.session_state.pop("empresa_save_notice", None):
        st.toast(msg, icon="✅")

    if "empresa_selected_id" not in st.session_state:
        st.session_state["empresa_selected_id"] = 0
    if "empresa_quick_edit_id" not in st.session_state:
        st.session_state["empresa_quick_edit_id"] = 0
    if "empresa_full_edit_id" not in st.session_state:
        st.session_state["empresa_full_edit_id"] = 0
    if "empresas_view_mode" not in st.session_state:
        st.session_state["empresas_view_mode"] = "ativas"
    if "show_import_uploader" not in st.session_state:
        st.session_state["show_import_uploader"] = False
    if "show_cadastro_on" not in st.session_state:
        st.session_state["show_cadastro_on"] = False
    if "empresa_cadastro_on_mode" not in st.session_state:
        st.session_state["empresa_cadastro_on_mode"] = "lookup"
    if "empresa_cadastro_on_result" not in st.session_state:
        st.session_state["empresa_cadastro_on_result"] = {}
    if "empresa_cadastro_on_error" not in st.session_state:
        st.session_state["empresa_cadastro_on_error"] = ""
    if "empresa_cadastro_on_existing_id" not in st.session_state:
        st.session_state["empresa_cadastro_on_existing_id"] = 0
    if "empresa_cadastro_on_lookup_value" not in st.session_state:
        st.session_state["empresa_cadastro_on_lookup_value"] = ""

    inject_scroll_keeper("empresas")

    with st.container(border=True):
        c1, c2, c3, c4, c5, c6, c7 = st.columns([1.8, 1.0, 1.2, 0.7, 0.8, 0.8, 0.8])
        search = c1.text_input(BUTTON_LABELS["buscar"], value=st.session_state.get("empresa_search", ""), label_visibility="collapsed", placeholder=BUTTON_LABELS["buscar"])
        st.session_state["empresa_search"] = search
        regime_filter = c2.selectbox("Regime", ["📋 Todos", *REGIMES], index=0, label_visibility="collapsed")

        empresas = load_empresas(active_only=False)
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
        if regime_filter != "📋 Todos":
            filtered = filtered[filtered["regime"] == regime_filter]
        if st.session_state["empresas_view_mode"] == "excluidas":
            filtered = filtered[filtered["is_ativo"] == 0]
        else:
            filtered = filtered[filtered["is_ativo"] == 1]

        display_df = filtered[["id", "cnpj", "razao_social", "nome_fantasia", "apelido", "regime", "mensalidade", "cidade", "uf"]].copy() if not filtered.empty else filtered
        export_df = display_df if not display_df.empty else filtered

        if c3.button(BUTTON_LABELS["incluir_cnpj"], key="btn_empresas_incluir_cnpj", type="primary", use_container_width=True):
            st.session_state["show_cadastro_on"] = True
            st.session_state["empresa_cadastro_on_mode"] = "lookup"
            st.session_state["empresa_cadastro_on_error"] = ""
            st.rerun()
        if c4.button(BUTTON_LABELS["ativas"], key="btn_empresas_ativas", type="primary" if st.session_state["empresas_view_mode"] == "ativas" else "secondary", use_container_width=True):
            st.session_state["empresas_view_mode"] = "ativas"
            st.rerun()
        if c5.button(BUTTON_LABELS["excluidas"], key="btn_empresas_excluidas", type="primary" if st.session_state["empresas_view_mode"] == "excluidas" else "secondary", use_container_width=True):
            st.session_state["empresas_view_mode"] = "excluidas"
            st.rerun()
        if c6.button(BUTTON_LABELS["importar"], key="btn_empresas_importar", type="primary" if st.session_state.get("show_import_uploader", False) else "secondary", use_container_width=True):
            st.session_state["show_import_uploader"] = not st.session_state.get("show_import_uploader", False)
            st.rerun()
        c7.download_button(
            BUTTON_LABELS["exportar"],
            data=empresas_export_csv(export_df),
            file_name=f"empresas_export_{datetime.now():%Y%m%d_%H%M%S}.csv",
            mime="text/csv",
            use_container_width=True,
        )
        selected_options = _selected_empresa_options(display_df)
        if selected_options:
            a1, a2, a3, a4, a5 = st.columns([2.2, 0.8, 1.1, 1.1, 1.0])
            selected_id = a1.selectbox(
                "Empresa selecionada",
                selected_options,
                index=selected_options.index(int(st.session_state.get("empresa_selected_id") or selected_options[0]))
                if int(st.session_state.get("empresa_selected_id") or selected_options[0]) in selected_options else 0,
                format_func=_empresa_option_label,
                label_visibility="collapsed",
                key="empresa_selected_select",
            )
            st.session_state["empresa_selected_id"] = int(selected_id)
            if a2.button("Recarregar", key="btn_empresas_recarregar", use_container_width=True):
                st.rerun()
            if a3.button("Editar selecionada", key="btn_empresas_editar", type="primary", use_container_width=True):
                st.session_state["empresa_quick_edit_id"] = int(selected_id)
                st.rerun()
            if st.session_state["empresas_view_mode"] == "excluidas":
                if a4.button("Restaurar", key="btn_empresas_restaurar", use_container_width=True):
                    restore_empresa_from_trash(int(selected_id))
                    st.toast("Empresa restaurada.")
                    st.session_state["empresas_view_mode"] = "ativas"
                    st.rerun()
            else:
                if a4.button("Mover para lixeira", key="btn_empresas_lixeira", use_container_width=True):
                    move_empresa_to_trash(int(selected_id))
                    st.toast("Empresa movida para a lixeira.")
                    st.rerun()
            if a5.button("Editor completo", key="btn_empresas_editor_completo", use_container_width=True):
                st.session_state["empresa_full_edit_id"] = int(selected_id)
                st.rerun()

    editable_mode = st.session_state["empresas_view_mode"] != "excluidas"

    render_empresa_cadastro_on_panel()
    if int(st.session_state.get("empresa_quick_edit_id", 0) or 0):
        render_empresa_quick_editor(int(st.session_state["empresa_quick_edit_id"]))
    if int(st.session_state.get("empresa_full_edit_id", 0) or 0):
        render_editor_empresa(int(st.session_state["empresa_full_edit_id"]))

    if st.session_state.get("show_import_uploader", False):
        with st.container(border=True):
            st.markdown("<h5 style='margin-top: 0px; margin-bottom: 4px;'>Importar Empresas</h5>", unsafe_allow_html=True)
            st.caption("Faca upload de uma planilha Excel (.xlsx, .xls) ou arquivo CSV para cadastrar ou atualizar empresas em massa por ID ou CNPJ.")
            uploaded_import = st.file_uploader(
                "Upload de arquivo",
                type=["csv", "xlsx", "xls"],
                label_visibility="collapsed",
                key="empresas_import_uploader",
            )
            if uploaded_import is not None:
                import_hash = hash(uploaded_import.getvalue())
                if st.session_state.get("empresas_last_import_hash") != import_hash:
                    try:
                        imported_df = empresas_import_dataframe(uploaded_import)
                        updated, created = empresas_apply_import(imported_df)
                        st.session_state["empresas_last_import_hash"] = import_hash
                        st.session_state["empresa_save_notice"] = f"Importacao concluida. Atualizados: {updated}. Criados: {created}."
                        st.session_state["show_import_uploader"] = False
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Nao foi possivel importar o arquivo. Detalhe: {exc}")

    if filtered.empty:
        st.info("Nenhuma empresa encontrada.")
        return

    table_height = calc_empresas_table_height(len(display_df))
    edited_df = show_table(
        display_df,
        key="empresas_editor",
        height=table_height,
        auto_height=True,
        editable=editable_mode,
        disabled=["id"],
        row_height=35,
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

    if editable_mode:
        try:
            changed = 0
            original = display_df.set_index("id")
            for _, edited_row in edited_df.iterrows():
                empresa_id = int(edited_row["id"])
                if empresa_id not in original.index:
                    continue
                orig_row = original.loc[empresa_id]
                payload = {
                    "cnpj": clean_cell(edited_row.get("cnpj", "")),
                    "razao_social": clean_cell(edited_row.get("razao_social", "")),
                    "nome_fantasia": clean_cell(edited_row.get("nome_fantasia", "")),
                    "apelido": clean_cell(edited_row.get("apelido", "")),
                    "regime": clean_cell(edited_row.get("regime", "")),
                    "mensalidade": clean_cell(edited_row.get("mensalidade", "")),
                    "cidade": clean_cell(edited_row.get("cidade", "")),
                    "uf": clean_cell(edited_row.get("uf", "")),
                }
                if any(payload[key] != clean_cell(orig_row[key]) for key in payload):
                    save_empresa(payload, empresa_id)
                    changed += 1
            if changed:
                st.toast(f"✅ Alterações salvas automaticamente. Registros atualizados: {changed}.", icon="✅")
                mark_restore_scroll("empresas")
        except Exception as exc:
            st.error(f"Nao foi possivel salvar as alteracoes. Detalhe: {exc}")
    else:
        st.caption("Exibindo somente empresas exclu?das.")

    restore_scroll_if_needed("empresas")

def clear_novo_cliente_cadastro_on_state() -> None:
    st.session_state["novo_cliente_on_lookup"] = ""
    st.session_state["novo_cliente_on_data"] = {}
    st.session_state["novo_cliente_on_error"] = ""


def render_novo_cliente() -> None:
    st.subheader("Novo cliente")
    st.caption("Preencha os campos abaixo para criar um novo cadastro.")

    if "novo_cliente_on_lookup" not in st.session_state:
        st.session_state["novo_cliente_on_lookup"] = ""
    if "novo_cliente_on_data" not in st.session_state:
        st.session_state["novo_cliente_on_data"] = {}
    if "novo_cliente_on_error" not in st.session_state:
        st.session_state["novo_cliente_on_error"] = ""

    with st.container(border=True):
        st.markdown("<h5 style='margin-top:0;margin-bottom:4px;'>Cadastro On</h5>", unsafe_allow_html=True)
        st.caption("Use o CNPJ para consultar os dados cadastrais e preencher o formul?rio manual antes de salvar.")
        c1, c2, c3 = st.columns([1.3, 0.7, 0.7])
        lookup_cnpj = c1.text_input("CNPJ", value=st.session_state.get("novo_cliente_on_lookup", ""), label_visibility="collapsed", placeholder="CNPJ")
        if c2.button(BUTTON_LABELS["cadastro_on"], key="btn_novo_cliente_cadastro_on", type="primary", use_container_width=True):
            digits = only_digits(lookup_cnpj)
            if not cnpj_valido(digits):
                st.session_state["novo_cliente_on_error"] = "Informe um CNPJ v?lido com 14 d?gitos."
            else:
                try:
                    info = fetch_empresa_cadastro_on(digits)
                    st.session_state["novo_cliente_on_lookup"] = digits
                    st.session_state["novo_cliente_on_data"] = info
                    st.session_state["novo_cliente_on_error"] = ""
                except Exception as exc:
                    st.session_state["novo_cliente_on_error"] = str(exc) or "A consulta online falhou. Tente novamente ou preencha manualmente."
                st.rerun()
        if c3.button(BUTTON_LABELS["limpar"], key="btn_novo_cliente_limpar", use_container_width=True):
            clear_novo_cliente_cadastro_on_state()
            st.rerun()
        if st.session_state.get("novo_cliente_on_error"):
            st.error(st.session_state["novo_cliente_on_error"])
        if st.session_state.get("novo_cliente_on_data"):
            info = st.session_state["novo_cliente_on_data"]
            st.info(f"Dados carregados de {info.get('source', 'consulta online')}.")

    prefill = st.session_state.get("novo_cliente_on_data") or {}

    with st.container(border=True):
        with st.form("novo_cliente_form"):
            c1, c2 = st.columns(2)
            cnpj = c1.text_input("CNPJ", value=_first_filled(prefill.get("cnpj"), st.session_state.get("novo_cliente_on_lookup", "")))
            razao = c2.text_input("Razao social", value=_first_filled(prefill.get("razao_social")))
            fantasia = c1.text_input("Nome fantasia", value=_first_filled(prefill.get("nome_fantasia")))
            apelido = c2.text_input("Apelido", value=_first_filled(prefill.get("apelido")))
            regime = c1.selectbox("Regime", REGIMES, index=REGIMES.index(_regime_option(prefill.get("regime", REGIMES[0]))) if _regime_option(prefill.get("regime", REGIMES[0])) in REGIMES else 0)
            abertura = c2.text_input("Abertura", value=_first_filled(prefill.get("abertura")))
            natureza_juridica = c1.text_input("Natureza juridica", value=_first_filled(prefill.get("natureza_juridica")))
            situacao = c2.text_input("Situacao", value=_first_filled(prefill.get("situacao")))
            capital_social = c1.text_input("Capital social", value=_first_filled(prefill.get("capital_social")))
            porte = c2.text_input("Porte", value=_first_filled(prefill.get("porte")))
            cidade = c1.text_input("Cidade", value=_first_filled(prefill.get("cidade")))
            uf = c2.text_input("UF", value=_first_filled(prefill.get("uf")), max_chars=2)
            simples_optante = c1.checkbox("Simples optante", value=int(prefill.get("simples_optante", 0) or 0) == 1)
            mei_optante = c2.checkbox("MEI optante", value=int(prefill.get("mei_optante", 0) or 0) == 1)
            mensalidade = c1.text_input("Mensalidade", value=_first_filled(prefill.get("mensalidade", "")))
            inativo = c2.checkbox("Inativa", value=int(prefill.get("inativo", 0) or 0) == 1)
            csave, ccancel = st.columns(2)
            save_new = csave.form_submit_button(f"{BUTTON_LABELS['salvar']} novo")
            cancel_new = ccancel.form_submit_button(BUTTON_LABELS["voltar"])

        if cancel_new:
            clear_novo_cliente_cadastro_on_state()
            st.session_state["page"] = "Empresas"
            st.query_params["page"] = "Empresas"
            st.rerun()

        if save_new:
            if not cnpj or not razao:
                st.error("CNPJ e razao social sao obrigatorios.")
            else:
                try:
                    save_empresa(
                        {
                            "cnpj": cnpj,
                            "razao_social": razao,
                            "nome_fantasia": fantasia,
                            "apelido": apelido,
                            "regime": regime,
                            "abertura": abertura,
                            "natureza_juridica": natureza_juridica,
                            "situacao": situacao,
                            "capital_social": capital_social,
                            "cidade": cidade,
                            "uf": uf,
                            "porte": porte,
                            "simples_optante": 1 if simples_optante else 0,
                            "mei_optante": 1 if mei_optante else 0,
                            "mensalidade": mensalidade,
                            "inativo": inativo,
                        },
                        None,
                    )
                    st.success("Novo cliente salvo.")
                    clear_novo_cliente_cadastro_on_state()
                    st.session_state["page"] = "Empresas"
                    st.query_params["page"] = "Empresas"
                    st.rerun()
                except Exception as exc:
                    st.error(f"Nao foi possivel salvar o novo cliente. Detalhe: {exc}")


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
        editable=False,
        disabled=True,
        auto_height=True,
        row_height=28,
        max_height=50000,
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
    st.subheader("Automacao")
    st.caption("Painel com acoes fiscais rapidas e atalhos para rotinas operacionais.")

    actions = [
        ("Baixar Guias do MEI", "Use a extensao: Baixar Guias_DMLS!"),
        ("Baixar NFe (Portal do Contribuinte)", "Rotina depende das credenciais e do fluxo do Portal do Contribuinte. A versao web sera ligada ao mesmo cadastro de acessos."),
        ("Extrair XML", "Use a extensao: Extrator XML (dmls)."),
        ("Analisar XML", "Selecione os XMLs na versao web para gerar uma analise simplificada."),
        ("Emitir Certidao Negativa", "Funcao em preparacao para integracao web."),
        ("Importar Pendencias", "Funcao em preparacao para integracao web."),
        ("Relatorio Fiscal", "Funcao em preparacao para integracao web."),
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
            st.warning("Leitura fiscal detalhada sera conectada na proxima etapa para espelhar o relatorio do desktop.")


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
            "razao_social": st.column_config.TextColumn("Razao social", width=260),
            "competencia": st.column_config.TextColumn("Competencia", width=110),
            "valor": st.column_config.TextColumn("Valor", width=90),
            "valor_nota_fiscal": st.column_config.TextColumn("NF", width=90),
            "valor_mov_extrato": st.column_config.TextColumn("Extrato", width=90),
            "observacao": st.column_config.TextColumn("Observacao", width=220),
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
        observacao = st.text_area("Observacao")
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
    st.write("Use esta tela para baixar uma copia dos dados ou substituir a base SQLite local.")

    if using_postgres():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for table in [
                "empresas",
                "empresa_demandas",
                "demandas",
                "historico_empresas",
                "historico_regime",
                "faturamento_mei",
                "settings",
                "users",
                "logs_sistema",
            ]:
                df = query_df(f"SELECT * FROM {table}")
                zf.writestr(f"{table}.csv", df.to_csv(index=False).encode("utf-8-sig"))
        st.download_button(
            "Baixar backup CSV",
            data=buffer.getvalue(),
            file_name=f"controle_empresas_backup_{datetime.now():%Y%m%d_%H%M%S}.zip",
            mime="application/zip",
        )
        st.info("Em modo PostgreSQL, a substituicao direta por arquivo .db fica desativada.")
        return

    if DB_PATH.exists():
        st.download_button(
            "Baixar cnpjs.db",
            data=DB_PATH.read_bytes(),
            file_name=f"cnpjs_backup_{datetime.now():%Y%m%d_%H%M%S}.db",
            mime="application/octet-stream",
        )

    uploaded = st.file_uploader("Substituir banco por outro cnpjs.db", type=["db", "sqlite", "sqlite3"])
    if uploaded and st.button("Confirmar substituicao"):
        backup_path = DB_PATH.with_suffix(f".bak_{datetime.now():%Y%m%d_%H%M%S}.db")
        if DB_PATH.exists():
            shutil.copy2(DB_PATH, backup_path)
        DB_PATH.write_bytes(uploaded.getbuffer())
        st.success("Banco substituido. Recarregue a pagina.")


def main() -> None:
    st.set_page_config(page_title="Controle de Empresas", layout="wide", initial_sidebar_state="expanded")
    apply_nexus_theme()
    ensure_database_ready()

    if not require_login_secure():
        return

    render_topbar()
    st.title("Controle de Empresas")

    if not db_exists():
        render_setup()
        return

    requested_page = normalize_page(st.query_params.get("page", st.session_state.get("page", "Modulos")) or "Modulos")
    if requested_page == "usuarios" and not can_access_users_page():
        st.warning("Você não tem permissão para acessar esta área.")
        st.query_params["page"] = "Modulos"
        st.session_state["page"] = "Modulos"
        st.session_state["page_label"] = "📂 Módulos"

    page, competencia = render_sidebar_secure()

    if page == "Modulos":
        render_modulos()
    elif page == "Painel":
        render_painel(competencia)
    elif page == "Novo Cliente":
        render_novo_cliente()
    elif page == "Empresas":
        render_empresas()
    elif page == "Demandas":
        render_demandas(competencia)
    elif page == "Automacao":
        render_automacao()
    elif page in ("Faturamento", "Faturamento MEI"):
        render_faturamento(competencia)
    elif page == "Backup":
        render_backup()
    elif page == "usuarios":
        render_usuarios()


if __name__ == "__main__":
    main()


