import streamlit as st
import pandas as pd
import io
from datetime import date, timedelta
from db import (
    carregar_fabricantes, 
    carregar_departamentos, 
    carregar_grupos, 
    carregar_subgrupos, 
    buscar_produtos_movimentacao_completa
)
from reportlab.lib.pagesizes import A4, portrait
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas

st.set_page_config(page_title="Ponto dos Botões - Gestão de Giro e Estoque", layout="wide", page_icon="🛍️")

hoje = date.today()
dias_30_atras = hoje - timedelta(days=30)

def limpar_filtros():
    st.session_state["venda_inicio"] = dias_30_atras
    st.session_state["venda_fim"] = hoje
    st.session_state["compra_inicio"] = dias_30_atras
    st.session_state["compra_fim"] = hoje
    for k in ["venda_datas", "compra_datas", "fornecedor_sel", "depto_sel", "grupo_sel", "subgrupo_sel", "df_mov"]:
        if k in st.session_state:
            del st.session_state[k]

lista_fornecedores = carregar_fabricantes()
dict_deptos = carregar_departamentos()

st.markdown('<h2 style="text-align: center; margin-bottom: 20px;">🛍️ Ponto dos Botões — Análise Completa de Giro, Vendas e Estoque</h2>', unsafe_allow_html=True)

col_venda, col_compra, col_forn, col_dep, col_grp, col_sub, col_btn_consultar, col_btn_limpar = st.columns([1.8, 1.8, 2.2, 1.6, 1.6, 1.6, 0.5, 0.5])

with col_venda:
    venda_datas = st.date_input(
        "Período Venda",
        value=(st.session_state.get("venda_inicio", dias_30_atras), st.session_state.get("venda_fim", hoje)),
        format="DD/MM/YYYY",
        key="venda_datas"
    )

with col_compra:
    compra_datas = st.date_input(
        "Período Compra",
        value=(st.session_state.get("compra_inicio", dias_30_atras), st.session_state.get("compra_fim", hoje)),
        format="DD/MM/YYYY",
        key="compra_datas"
    )

with col_forn:
    fornecedor_sel = st.selectbox("Fabricante / Fornecedor", options=lista_fornecedores, index=None, placeholder="Todos...", key="fornecedor_sel")

with col_dep:
    depto_sel = st.selectbox("Departamento", options=list(dict_deptos.keys()), index=None, placeholder="Todos...", key="depto_sel")
    cod_depto = dict_deptos.get(depto_sel) if depto_sel else None

dict_grupos = carregar_grupos(cod_depto)
with col_grp:
    grupo_sel = st.selectbox("Grupo", options=list(dict_grupos.keys()), index=None, placeholder="Todos...", key="grupo_sel")
    cod_grupo = dict_grupos.get(grupo_sel) if grupo_sel else None

dict_subgrupos = carregar_subgrupos(cod_grupo)
with col_sub:
    subgrupo_sel = st.selectbox("Subgrupo", options=list(dict_subgrupos.keys()), index=None, placeholder="Todos...", key="subgrupo_sel")
    cod_subgrupo = dict_subgrupos.get(subgrupo_sel) if subgrupo_sel else None

with col_btn_consultar:
    btn_consultar = st.button("🔍", type="primary", use_container_width=True, help="Consultar")

with col_btn_limpar:
    btn_limpar = st.button("🧹", on_click=limpar_filtros, use_container_width=True, help="Limpar Filtros")

v_ini = venda_datas[0] if isinstance(venda_datas, tuple) and len(venda_datas) > 0 else dias_30_atras
v_fim = venda_datas[1] if isinstance(venda_datas, tuple) and len(venda_datas) > 1 else v_ini
c_ini = compra_datas[0] if isinstance(compra_datas, tuple) and len(compra_datas) > 0 else dias_30_atras
c_fim = compra_datas[1] if isinstance(compra_datas, tuple) and len(compra_datas) > 1 else c_ini

if btn_consultar:
    with st.spinner("Consultando dados de movimentação e estoque comercial..."):
        df = buscar_produtos_movimentacao_completa(
            fornecedor_sel, 
            cod_depto, 
            cod_grupo, 
            cod_subgrupo, 
            v_ini, 
            v_fim, 
            c_ini, 
            c_fim
        )
        st.session_state["df_mov"] = df
        st.session_state["fornecedor_atual"] = fornecedor_sel

if "df_mov" in st.session_state:
    df = st.session_state["df_mov"]
    fornecedor = st.session_state.get("fornecedor_atual")
    
    # Cards de Resumo Executivo
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Itens Encontrados", f"{len(df):,}")
    m2.metric("Total Vendido (Unid)", f"{df['Total Vendas'].sum():,.0f}")
    m3.metric("Estoque Comercial (Unid)", f"{df['Est. Total'].sum():,.0f}")
    m4.metric("Valor Total Estoque", f"R$ {df['Valor em Estoque (R$)'].sum():,.2f}")

    st.markdown("---")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=620,
        column_config={
            "Código": st.column_config.TextColumn("Código", width="small"),
            "Ref. Fabr.": st.column_config.TextColumn("Ref. Fabr.", width="small"),
            "Descrição": st.column_config.TextColumn("Descrição", width="large"),
            "Unid": st.column_config.TextColumn("Unid", width="small"),
            "Custo Compra": st.column_config.NumberColumn("Custo (R$)", format="R$ %.2f"),
            "Est. Alecrim": st.column_config.NumberColumn("Est. AL", format="%.0f"),
            "Est. Via Direta": st.column_config.NumberColumn("Est. VIA", format="%.0f"),
            "Est. Zona Sul": st.column_config.NumberColumn("Est. ZS", format="%.0f"),
            "Est. Zona Norte": st.column_config.NumberColumn("Est. ZN", format="%.0f"),
            "Est. Total": st.column_config.NumberColumn("Est. Total", format="%.0f"),
            "Venda PBAL": st.column_config.NumberColumn("Vda AL", format="%.0f"),
            "Venda PBVIA": st.column_config.NumberColumn("Vda VIA", format="%.0f"),
            "Venda PBZS": st.column_config.NumberColumn("Vda ZS", format="%.0f"),
            "Venda PBZN": st.column_config.NumberColumn("Vda ZN", format="%.0f"),
            "Total Vendas": st.column_config.NumberColumn("Tot. Vendas", format="%.0f"),
            "Qtd Comprada": st.column_config.NumberColumn("Qtd Compra", format="%.0f"),
            "Cobertura (Dias)": st.column_config.NumberColumn("Cobertura (Dias)", format="%.1f d"),
            "Valor em Estoque (R$)": st.column_config.NumberColumn("Valor Est. (R$)", format="R$ %.2f"),
        }
    )