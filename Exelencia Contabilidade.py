# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import hashlib
import hmac
import json
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
    }
}


st.set_page_config(page_title="Controle de Empresas", page_icon="logo.png", layout="wide")


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #eef3f9;
            --ink: #0f172a;
            --muted: #64748b;
            --primary: #6d28d9;
            --primary-strong: #4c1d95;
            --table-bg: #090817;
            --table-alt: #111026;
            --table-line: #1d2140;
            --table-head: #8b5cf6;
        }
        .stApp { background: var(--bg); color: var(--ink); }
        .block-container { padding-top: 1.2rem; max-width: 1500px; }
        h1, h2, h3 { letter-spacing: 0; }
        [data-testid="stSidebar"] { background: #f8fafc; border-right: 1px solid #dbe3ee; }
        div.stButton > button {
            width: 100%;
            border-radius: 8px;
            min-height: 42px;
            font-weight: 800;
            border: 1px solid #d7deea;
        }
        div.stButton > button[kind="primary"] {
            background: var(--primary);
            border-color: var(--primary);
            color: #fff;
        }
        .simple-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 18px;
        }
        .brand-title {
            font-size: 1.9rem;
            font-weight: 900;
            color: var(--ink);
            margin: 0;
        }
        .brand-subtitle {
            color: var(--muted);
            margin-top: 4px;
            font-size: 0.92rem;
        }
        .dmls-table {
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
            background: var(--table-bg);
            color: #f8fafc;
            border: 1px solid #c4f1ff;
            font-size: 0.78rem;
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
        .dmls-table tbody tr:hover { background: #3b3f86; }
        .metric-row {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin: 12px 0 16px;
        }
        .metric-card {
            background: #fff;
            border: 1px solid #dbe3ee;
            border-radius: 8px;
            padding: 12px 14px;
        }
        .metric-card span { color: var(--muted); font-size: .82rem; }
        .metric-card strong { display:block; font-size:1.7rem; margin-top:4px; }
        @media (max-width: 900px) {
            .metric-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .dmls-table { font-size: 0.70rem; }
            .dmls-table th, .dmls-table td { padding: 0.34rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_user(value: str) -> str:
    return str(value or "").strip().upper()


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


def is_admin() -> bool:
    return current_profile() in {"admin", "contador"}


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
                st.session_state["page"] = "home"
                st.rerun()
            else:
                st.error("Usuario ou senha invalidos.")


def sidebar(metadata: dict) -> str:
    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=72)
        st.markdown(f"**Usuario:** {current_user()}")
        st.caption(f"Perfil: {current_profile()}")
        st.divider()
        competencia = str(metadata.get("competencia_atual") or "2026-05")
        st.caption(f"Competencia: {competencia}")
        st.caption(f"Atualizado: {metadata.get('data_ultima_atualizacao', '')}")
        if st.button("Recarregar dados"):
            load_data.clear()
            st.rerun()
        if st.button("Sair"):
            st.session_state.clear()
            st.rerun()
    return str(metadata.get("competencia_atual") or "2026-05")


def go(page: str) -> None:
    st.session_state["page"] = page
    st.rerun()


def header(title: str, subtitle: str = "") -> None:
    st.markdown(
        f"""
        <div class="simple-top">
            <div>
                <div class="brand-title">{title}</div>
                <div class="brand-subtitle">{subtitle}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def home() -> None:
    header("Controle de Empresas", "Painel simples para empresas e demandas.")
    c1, c2 = st.columns(2)
    if c1.button("Cadastro de Empresas", key="home_empresas"):
        go("empresas")
    if c2.button("Controle de Demandas", key="home_demandas", type="primary"):
        go("demandas")


def render_table(df: pd.DataFrame, widths: dict[str, str]) -> None:
    colgroup = "<colgroup>" + "".join(
        f"<col style='width:{widths.get(str(col), 'auto')}'>" for col in df.columns
    ) + "</colgroup>"
    html = df.fillna("").to_html(index=False, escape=True, classes="dmls-table")
    html = html.replace("<table ", f"<table ", 1).replace(">\n  <thead>", f">\n  {colgroup}\n  <thead>", 1)
    st.markdown(html, unsafe_allow_html=True)


def empresas_page(empresas: pd.DataFrame) -> None:
    header("Cadastro de Empresas", "Consulta simples. Cadastro completo fica no Python.")
    if st.button("Voltar"):
        go("home")

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


def demandas_page(empresas: pd.DataFrame, demandas: pd.DataFrame, competencia_padrao: str) -> None:
    header("Controle de Demandas", "Mesmas colunas da grade do Python.")
    if st.button("Voltar"):
        go("home")

    df = normalize_demandas(demandas, empresas)
    if df.empty:
        st.info("Nenhuma demanda encontrada.")
        return

    f1, f2, f3, f4 = st.columns([0.9, 1.4, 1, 1])
    competencia = f1.text_input("Competencia", value=competencia_padrao)
    busca = f2.text_input("Buscar", placeholder="cliente, CNPJ, tipo")
    status = f3.selectbox("Status", ["Todos", "pendente", "em_andamento", "concluida"])
    minhas = f4.checkbox("So minhas", value=False)

    if competencia:
        df = df[df["competencia"].astype(str).eq(competencia)].copy()
    if status != "Todos":
        df = df[df["status"].astype(str).eq(status)].copy()
    if busca:
        q = busca.strip().upper()
        blob = (df["empresa"] + " " + df["cnpj"] + " " + df["tipo_demanda"] + " " + df["observacao"]).str.upper()
        df = df[blob.str.contains(q, regex=False)].copy()
    if minhas and not is_admin():
        user = current_user()
        df = df[
            df["responsavel_operacional"].astype(str).str.upper().eq(user)
            | df["estagiario_responsavel"].astype(str).str.upper().eq(user)
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
    render_table(grid, {"ID": "7%", "Cliente": "22%", "CNPJ": "18%", "Tipo": "29%", "Competencia": "10%", "Observacao": "14%"})

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


def main() -> None:
    inject_css()
    if not st.session_state.get("usuario"):
        login_screen()
        return

    empresas, demandas, _usuarios, metadata = load_data()
    competencia = sidebar(metadata)
    page = st.session_state.get("page", "home")
    if page == "empresas":
        empresas_page(empresas)
    elif page == "demandas":
        demandas_page(empresas, demandas, competencia)
    else:
        home()


if __name__ == "__main__":
    main()
