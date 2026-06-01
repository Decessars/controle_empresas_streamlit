# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import hashlib
import hmac
import json
from html import escape
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
DATA_WEB_DIR = APP_DIR / "data_web"
EMPRESAS_CSV = DATA_WEB_DIR / "empresas_web.csv"
DEMANDAS_CSV = DATA_WEB_DIR / "demandas_web.csv"
USUARIOS_CSV = DATA_WEB_DIR / "usuarios_web.csv"
MARCACOES_CSV = DATA_WEB_DIR / "marcacoes_web.csv"
METADATA_JSON = DATA_WEB_DIR / "metadata_web.json"
LOGO_PATH = APP_DIR / "logo.png"

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
        navigate_to("Home", "🏠 Home", push_history=False)


def resolve_start_page() -> str:
    query_page = st.query_params.get("page", "")
    if isinstance(query_page, list):
        query_page = query_page[0] if query_page else ""
    page = normalize_page(query_page or st.session_state.get("page", "Home"))
    st.session_state["page"] = page
    st.session_state["page_label"] = {
        "Home": "🏠 Home",
        "Empresas": "🏢 Empresas",
        "Demandas": "📋 Demandas",
    }.get(page, page)
    if str(query_page or "") != page:
        st.query_params["page"] = page
    return page


@st.cache_data(ttl=60)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    empresas = pd.read_csv(EMPRESAS_CSV, dtype=str).fillna("") if EMPRESAS_CSV.exists() else pd.DataFrame()
    demandas = pd.read_csv(DEMANDAS_CSV, dtype=str).fillna("") if DEMANDAS_CSV.exists() else pd.DataFrame()
    usuarios = pd.read_csv(USUARIOS_CSV, dtype=str).fillna("") if USUARIOS_CSV.exists() else pd.DataFrame()
    metadata = {}
    if METADATA_JSON.exists():
        try:
            metadata = json.loads(METADATA_JSON.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}
    return empresas, demandas, usuarios, metadata


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
                st.session_state["page_label"] = "🏠 Home"
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
        if st.button("🏠 Home", use_container_width=True):
            navigate_to("Home", "🏠 Home")
        if st.button("🏢 Empresas", use_container_width=True):
            navigate_to("Empresas", "🏢 Empresas")
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
    page_label = st.session_state.get("page_label", "🏠 Home")
    c1, c2, c3, c4, c5 = st.columns([2.1, 1.0, 1.0, 0.55, 0.45], vertical_alignment="center")
    with c1:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=34)
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
        if st.button("🏠 Home", key="topbar_home", use_container_width=True):
            navigate_to("Home", "🏠 Home")
    with c5:
        if st.button("Sair", key="topbar_logout", use_container_width=True):
            st.session_state.clear()
            st.rerun()


def render_home() -> None:
    empresas, demandas, _, metadata = load_data()
    df_demandas = normalize_demandas(demandas, empresas)
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
                <div class="hint">Base carregada em data_web</div>
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

    st.markdown('<div class="section-title" style="margin-top:0.35rem;">Acesso rápido</div>', unsafe_allow_html=True)
    st.markdown('<div class="muted-text" style="margin-bottom:0.55rem;">Escolha uma área ativa do painel.</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            """
            <div class="module-card">
                <div class="icon">📋</div>
                <div class="title">Controle de Demandas</div>
                <div class="desc">Acompanhe pendências, status e andamento operacional da competência atual.</div>
                <div class="status-badge">Operação diária</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("📋 Abrir Demandas", key="home_demandas", type="primary"):
            navigate_to("Demandas", "📋 Demandas")
    with c2:
        st.markdown(
            """
            <div class="module-card">
                <div class="icon">🏢</div>
                <div class="title">Controle de Empresas</div>
                <div class="desc">Visualize a base de clientes e faça consultas rápidas sem excesso de telas.</div>
                <div class="status-badge">Base operacional</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("🏢 Abrir Empresas", key="home_empresas"):
            navigate_to("Empresas", "🏢 Empresas")


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


def render_empresas(empresas: pd.DataFrame) -> None:
    header("Cadastro de Empresas", "Consulta simples. Cadastro completo fica no Python.")

    if empresas.empty:
        st.info("Nenhuma empresa encontrada.")
        return

    busca = st.text_input("Buscar", placeholder="CNPJ, apelido ou razao social")
    df = empresas.copy().fillna("")
    if "ativo" in df.columns:
        df = df[df["ativo"].astype(str).isin(["1", "1.0", "True", "true", ""])]
    if busca:
        q = busca.strip().upper()
        blob = (
            df.get("cnpj", "").astype(str) + " "
            + df.get("apelido", "").astype(str) + " "
            + df.get("razao_social", "").astype(str) + " "
            + df.get("nome_fantasia", "").astype(str)
        ).str.upper()
        df = df[blob.str.contains(q, regex=False)]

    cols = {
        "empresa_id": "ID",
        "cnpj": "CNPJ",
        "apelido": "Cliente",
        "razao_social": "Razao Social",
        "regime": "Regime",
        "cidade": "Cidade",
        "uf": "UF",
    }
    view = df[[c for c in cols if c in df.columns]].rename(columns=cols)
    view = sort_controls(view, list(view.columns), "empresas")
    render_table(view, {"ID": "7%", "CNPJ": "18%", "Cliente": "22%", "Razao Social": "31%", "Regime": "12%", "Cidade": "8%", "UF": "2%"})


def can_mark(row: pd.Series) -> bool:
    if is_admin():
        return True
    user = current_user()
    return user in {
        normalize_user(row.get("responsavel_operacional", "")),
        normalize_user(row.get("estagiario_responsavel", "")),
    }


def append_marcacao(demanda_id: str, status: str, observacao: str) -> None:
    MARCACOES_CSV.parent.mkdir(parents=True, exist_ok=True)
    exists = MARCACOES_CSV.exists()
    with MARCACOES_CSV.open("a", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["marcacao_id", "demanda_id", "username", "acao", "status_novo", "observacao", "data_hora", "sincronizado"],
        )
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "marcacao_id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "demanda_id": demanda_id,
                "username": current_user(),
                "acao": "status",
                "status_novo": status,
                "observacao": observacao,
                "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sincronizado": "0",
            }
        )


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


def render_demandas(empresas: pd.DataFrame, demandas: pd.DataFrame, competencia_padrao: str) -> None:
    header("Controle de Demandas", "Mesmas colunas da grade do Python.")

    df = normalize_demandas(demandas, empresas)
    if df.empty:
        st.info("Nenhuma demanda encontrada.")
        return

    f1, f2, f3, f4 = st.columns([0.9, 1.4, 1, 1])
    competencia = f1.text_input("Competencia", value=competencia_padrao)
    busca = f2.text_input("Buscar", placeholder="cliente, CNPJ, tipo")
    status = f3.selectbox("Status", ["Todos", "pendente", "em_andamento", "concluida"])
    minhas = f4.checkbox("So minhas", value=not is_admin())

    if competencia:
        df = df[df["competencia"].astype(str).eq(competencia)].copy()
    if status != "Todos":
        df = df[df["status"].astype(str).eq(status)].copy()
    if busca:
        q = busca.strip().upper()
        blob = (df["empresa"] + " " + df["cnpj"] + " " + df["tipo_demanda"] + " " + df["observacao"]).str.upper()
        df = df[blob.str.contains(q, regex=False)].copy()
    if minhas:
        user = current_user()
        df = df[
            df["responsavel_operacional"].astype(str).map(normalize_user).eq(user)
            | df["estagiario_responsavel"].astype(str).map(normalize_user).eq(user)
        ].copy()

    total = len(df)
    pendentes = int(df["status"].astype(str).eq("pendente").sum()) if total else 0
    concluidas = int(df["status"].astype(str).eq("concluida").sum()) if total else 0
    metric_row(total, pendentes, concluidas)

    if df.empty:
        st.info("Nenhuma demanda encontrada com os filtros atuais.")
        return

    grid = df.rename(
        columns={
            "demanda_id": "ID",
            "empresa": "Cliente",
            "cnpj": "CNPJ",
            "tipo_demanda": "Tipo",
            "competencia": "Competencia",
            "observacao": "Observacao",
        }
    )[["ID", "Cliente", "CNPJ", "Tipo", "Competencia", "Observacao"]]
    grid = sort_controls(grid, list(grid.columns), "demandas")
    render_table(grid, {"ID": "7%", "Cliente": "22%", "CNPJ": "18%", "Tipo": "29%", "Competencia": "10%", "Observacao": "14%"})

    st.markdown('<div class="action-panel">', unsafe_allow_html=True)
    selected_id = st.selectbox(
        "Selecionar demanda para marcar",
        df["demanda_id"].astype(str).tolist(),
        format_func=lambda did: f"{did} - {df.loc[df['demanda_id'].astype(str).eq(str(did)), 'empresa'].iloc[0]}",
    )
    selected = df.loc[df["demanda_id"].astype(str).eq(str(selected_id))].iloc[0]
    allowed = can_mark(selected)
    if not allowed:
        st.warning("Somente o responsavel desta demanda pode marcar.")

    obs = st.text_area("Observacao curta", value=str(selected.get("observacao", "")), height=80)
    c1, c2 = st.columns(2)
    if c1.button("Concluir", disabled=not allowed, type="primary"):
        append_marcacao(str(selected_id), "concluida", obs)
        st.success("Marcacao registrada.")
    if c2.button("Em andamento", disabled=not allowed):
        append_marcacao(str(selected_id), "em_andamento", obs)
        st.success("Marcacao registrada.")
    st.markdown("</div>", unsafe_allow_html=True)


ACTIVE_PAGES = {
    "Home": {"label": "🏠 Home", "renderer": render_home},
    "Empresas": {"label": "🏢 Empresas", "renderer": render_empresas},
    "Demandas": {"label": "📋 Demandas", "renderer": render_demandas},
}


def main() -> None:
    inject_professional_ui_css()
    if not st.session_state.get("usuario"):
        login_screen()
        return

    empresas, demandas, _usuarios, metadata = load_data()
    competencia = sidebar(metadata)
    page = resolve_start_page()
    render_topbar(competencia)
    renderer = ACTIVE_PAGES[page]["renderer"]
    if page == "Home":
        renderer()
    elif page == "Empresas":
        renderer(empresas)
    elif page == "Demandas":
        renderer(empresas, demandas, competencia)


if __name__ == "__main__":
    main()
