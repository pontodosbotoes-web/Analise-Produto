import streamlit as st
import pandas as pd
import io
from datetime import date, timedelta
from db import (
    carregar_fabricantes, 
    carregar_departamentos, 
    carregar_grupos, 
    carregar_subgrupos, 
    buscar_produtos_movimentacao
)
from reportlab.lib.pagesizes import A4, portrait
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.setFont("Helvetica", 7)
        self.setFillColor(colors.HexColor('#64748B'))
        page_text = f"Página {self._pageNumber} de {page_count}"
        self.drawCentredString(A4[0] / 2.0, 10, page_text)

def gerar_pdf(df, fornecedor, p_venda, p_compra):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=portrait(A4), rightMargin=10, leftMargin=10, topMargin=15, bottomMargin=25
    )
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=11, leading=13, textColor=colors.HexColor('#1E293B'), alignment=1)
    sub_style = ParagraphStyle('SubStyle', parent=styles['Normal'], fontSize=7, leading=9, textColor=colors.HexColor('#475569'), alignment=1)
    
    elements.append(Paragraph(f"<b>Ponto dos Botões - Relatório de Movimentação ({fornecedor or 'Geral'})</b>", title_style))
    elements.append(Paragraph(f"Período Venda: {p_venda} | Período Compra: {p_compra} | Total Itens: {len(df)}", sub_style))
    elements.append(Spacer(1, 8))
    
    cell_style = ParagraphStyle('CellText', parent=styles['Normal'], fontSize=6, leading=7)
    cell_header = ParagraphStyle('CellHeader', parent=styles['Normal'], fontSize=6, leading=7, textColor=colors.white, fontName='Helvetica-Bold', alignment=1)

    headers = [Paragraph(col, cell_header) for col in df.columns]
    table_data = [headers]

    for _, row in df.iterrows():
        row_cells = []
        for col, val in row.items():
            if 'Descrição' in col:
                row_cells.append(Paragraph(str(val), cell_style))
            elif isinstance(val, (int, float)):
                row_cells.append(f"{val:,.0f}" if val != 0 else "0")
            else:
                row_cells.append(str(val))
        table_data.append(row_cells)

    col_widths = [18, 40, 45, 200, 25, 30, 30, 30, 30, 38, 38]
    
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (3, 1), (3, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')])
    ]))
    
    elements.append(t)
    doc.build(elements, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer

st.set_page_config(page_title="Ponto dos Botões - Análise Web", layout="wide", page_icon="🛍️")

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

st.markdown('<h2 style="text-align: center; margin-bottom: 20px;">🛍️ Ponto dos Botões — Movimentação e Análise de Produtos</h2>', unsafe_allow_html=True)

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
    with st.spinner("Consultando banco de dados DBcronos..."):
        df = buscar_produtos_movimentacao(
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
    
    col_inf, col_m1, col_m2, col_btn_pdf = st.columns([3, 2, 2, 1.5])
    col_inf.caption(f"**Filtro:** {fornecedor or 'Geral'} ({len(df)} produtos localizados)")
    col_m1.caption(f"**Total Comprado:** {df['Qtd Comprada'].sum():,.0f}" if 'Qtd Comprada' in df.columns else "")
    col_m2.caption(f"**Total Vendido:** {df['Total Vendas'].sum():,.0f}" if 'Total Vendas' in df.columns else "")

    with col_btn_pdf:
        pdf_bytes = gerar_pdf(
            df, 
            fornecedor, 
            f"{v_ini.strftime('%d/%m/%Y')} a {v_fim.strftime('%d/%m/%Y')}",
            f"{c_ini.strftime('%d/%m/%Y')} a {c_fim.strftime('%d/%m/%Y')}"
        )
        st.download_button(
            label="📄 PDF",
            data=pdf_bytes,
            file_name=f"Movimentacao_{fornecedor or 'Geral'}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

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
            "Venda PBAL": st.column_config.NumberColumn("Alecrim", format="%.0f"),
            "Venda PBVIA": st.column_config.NumberColumn("Via Direta", format="%.0f"),
            "Venda PBZS": st.column_config.NumberColumn("Zona Sul", format="%.0f"),
            "Venda PBZN": st.column_config.NumberColumn("Zona Norte", format="%.0f"),
            "Total Vendas": st.column_config.NumberColumn("Tot. Vendas", format="%.0f"),
            "Qtd Comprada": st.column_config.NumberColumn("Qtd Compra", format="%.0f"),
        }
    )