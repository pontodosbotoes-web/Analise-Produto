import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

def get_engine():
    cred = st.secrets["sql_server"]
    db_url = f"mssql+pymssql://{cred['username']}:{cred['password']}@{cred['server']}:{cred['port']}/{cred['database']}"
    return create_engine(db_url)

@st.cache_data(ttl=3600)
def carregar_fabricantes():
    engine = get_engine()
    query = text("SELECT DISTINCT NOMEFABR FROM Fabricantes WITH (NOLOCK) WHERE NOMEFABR IS NOT NULL ORDER BY NOMEFABR")
    with engine.connect() as conn:
        df = pd.read_sql_query(query, conn)
    return df['NOMEFABR'].tolist()

@st.cache_data(ttl=3600)
def carregar_departamentos():
    engine = get_engine()
    query = text("""
        SELECT DISTINCT LEFT(CodGrupo, 2) AS Codigo, NomeGrupo 
        FROM Grupos WITH (NOLOCK)
        WHERE LEN(REPLACE(CodGrupo, '.', '')) = 2 OR LEN(CodGrupo) = 2
        ORDER BY NomeGrupo
    """)
    with engine.connect() as conn:
        df = pd.read_sql_query(query, conn)
    return dict(zip(df['NomeGrupo'], df['Codigo']))

@st.cache_data(ttl=3600)
def carregar_grupos(cod_depto=None):
    engine = get_engine()
    query_str = """
        SELECT DISTINCT CodGrupo AS Codigo, NomeGrupo 
        FROM Grupos WITH (NOLOCK)
        WHERE (LEN(REPLACE(CodGrupo, '.', '')) = 4 OR LEN(CodGrupo) = 5)
    """
    params = {}
    if cod_depto:
        query_str += " AND LEFT(CodGrupo, 2) = :depto"
        params['depto'] = str(cod_depto)
    query_str += " ORDER BY NomeGrupo"
    
    with engine.connect() as conn:
        df = pd.read_sql_query(text(query_str), conn, params=params)
    return dict(zip(df['NomeGrupo'], df['Codigo']))

@st.cache_data(ttl=3600)
def carregar_subgrupos(cod_grupo=None):
    engine = get_engine()
    query_str = """
        SELECT DISTINCT CodGrupo AS Codigo, NomeGrupo 
        FROM Grupos WITH (NOLOCK)
        WHERE (LEN(REPLACE(CodGrupo, '.', '')) > 5 OR LEN(CodGrupo) >= 8)
    """
    params = {}
    if cod_grupo:
        query_str += " AND LEFT(CodGrupo, 5) = :grupo"
        params['grupo'] = str(cod_grupo)
    query_str += " ORDER BY NomeGrupo"
    
    with engine.connect() as conn:
        df = pd.read_sql_query(text(query_str), conn, params=params)
    return dict(zip(df['NomeGrupo'], df['Codigo']))

def buscar_produtos_movimentacao_completa(fornecedor, depto, grupo, subgrupo, data_ini_venda, data_fim_venda, data_ini_compra, data_fim_compra):
    engine = get_engine()
    
    dt_v_ini = f"{data_ini_venda.strftime('%Y-%m-%d')} 00:00:00"
    dt_v_fim = f"{data_fim_venda.strftime('%Y-%m-%d')} 23:59:59"
    dt_c_ini = f"{data_ini_compra.strftime('%Y-%m-%d')} 00:00:00"
    dt_c_fim = f"{data_fim_compra.strftime('%Y-%m-%d')} 23:59:59"
    dias_periodo = max((data_fim_venda - data_ini_venda).days + 1, 1)

    # 1. Filtro base de produtos
    where_prod = ["LEFT(g.CodGrupo, 2) NOT IN ('09', '10')", "p.ProdutoInativo = 'N'"]
    params_prod = {}

    if fornecedor:
        where_prod.append("f.NOMEFABR = :fornecedor")
        params_prod['fornecedor'] = fornecedor
    if depto:
        where_prod.append("LEFT(g.CodGrupo, 2) = :depto")
        params_prod['depto'] = depto
    if grupo:
        where_prod.append("LEFT(g.CodGrupo, 5) = :grupo")
        params_prod['grupo'] = grupo
    if subgrupo:
        where_prod.append("g.CodGrupo = :subgrupo")
        params_prod['subgrupo'] = subgrupo

    sql_produtos = f"""
        SELECT 
            p.IdProduto,
            p.CODPRODUTO AS [Código],
            p.CodProdutoFabr AS [Ref. Fabr.],
            p.NOMEPRODUTO AS [Descrição],
            p.UNID AS [Unid],
            CAST(ISNULL(p.CustoCompra, 0) AS FLOAT) AS [Custo Compra]
        FROM Produtos p WITH (NOLOCK)
        LEFT JOIN Fabricantes f WITH (NOLOCK) ON f.CODFABR = p.CODFABR
        LEFT JOIN Grupos g WITH (NOLOCK) ON g.IdGrupo = p.IdGrupo
        WHERE {" AND ".join(where_prod)}
    """

    # 2. Vendas
    sql_vendas = """
        SELECT 
            i.IdProduto,
            SUM(CASE WHEN m.CodFilial = 1 THEN (CAST(ISNULL(i.Qtd, 0) AS FLOAT) - CAST(ISNULL(i.QtdCancel, 0) AS FLOAT)) / NULLIF(CAST(i.FatorConvUnid AS FLOAT), 0) ELSE 0 END) AS [Venda PBAL],
            SUM(CASE WHEN m.CodFilial = 2 THEN (CAST(ISNULL(i.Qtd, 0) AS FLOAT) - CAST(ISNULL(i.QtdCancel, 0) AS FLOAT)) / NULLIF(CAST(i.FatorConvUnid AS FLOAT), 0) ELSE 0 END) AS [Venda PBVIA],
            SUM(CASE WHEN m.CodFilial = 3 THEN (CAST(ISNULL(i.Qtd, 0) AS FLOAT) - CAST(ISNULL(i.QtdCancel, 0) AS FLOAT)) / NULLIF(CAST(i.FatorConvUnid AS FLOAT), 0) ELSE 0 END) AS [Venda PBZS],
            SUM(CASE WHEN m.CodFilial = 4 THEN (CAST(ISNULL(i.Qtd, 0) AS FLOAT) - CAST(ISNULL(i.QtdCancel, 0) AS FLOAT)) / NULLIF(CAST(i.FatorConvUnid AS FLOAT), 0) ELSE 0 END) AS [Venda PBZN],
            SUM((CAST(ISNULL(i.Qtd, 0) AS FLOAT) - CAST(ISNULL(i.QtdCancel, 0) AS FLOAT)) / NULLIF(CAST(i.FatorConvUnid AS FLOAT), 0)) AS [Total Vendas]
        FROM ItensMov i WITH (NOLOCK)
        INNER JOIN Movimento m WITH (NOLOCK) ON m.IdMov = i.IdMov
        WHERE m.TipoMov = '2.4' AND m.NfeStatus = 'U'
          AND m.CodCliFor NOT IN ('C08327','F00074','C08328','F10077','C22206','F15703','C16205','F14688','C30965','F16834')
          AND m.DtFinalizacao >= :dt_v_ini AND m.DtFinalizacao <= :dt_v_fim
        GROUP BY i.IdProduto
    """

    # 3. Compras
    sql_compras = """
        SELECT 
            i.IdProduto,
            SUM((CAST(ISNULL(i.Qtd, 0) AS FLOAT) - CAST(ISNULL(i.QtdCancel, 0) AS FLOAT)) / NULLIF(CAST(i.FatorConvUnid AS FLOAT), 0)) AS [Qtd Comprada]
        FROM ItensMov i WITH (NOLOCK)
        INNER JOIN Movimento m WITH (NOLOCK) ON m.IdMov = i.IdMov
        WHERE m.TipoMov = '1.1'
          AND m.CodCliFor NOT IN ('C08327','F00074','C08328','F10077','C22206','F15703','C16205','F14688','C30965','F16834')
          AND m.DtFinalizacao >= :dt_c_ini AND m.DtFinalizacao <= :dt_c_fim
        GROUP BY i.IdProduto
    """

    # 4. Estoque
    sql_estoque = """
        SELECT 
            e.IdProduto,
            SUM(CASE WHEN e.CodFilial = 1 THEN CAST(e.EstoqueAtual AS FLOAT) ELSE 0 END) AS [Est. Alecrim],
            SUM(CASE WHEN e.CodFilial = 2 THEN CAST(e.EstoqueAtual AS FLOAT) ELSE 0 END) AS [Est. Via Direta],
            SUM(CASE WHEN e.CodFilial = 3 THEN CAST(e.EstoqueAtual AS FLOAT) ELSE 0 END) AS [Est. Zona Sul],
            SUM(CASE WHEN e.CodFilial = 4 THEN CAST(e.EstoqueAtual AS FLOAT) ELSE 0 END) AS [Est. Zona Norte],
            SUM(CAST(e.EstoqueAtual AS FLOAT)) AS [Est. Total]
        FROM EstqProdutos e WITH (NOLOCK)
        WHERE e.CodLocal = '01'
        GROUP BY e.IdProduto
    """

    with engine.connect() as conn:
        df_produtos = pd.read_sql_query(text(sql_produtos), conn, params=params_prod)
        if df_produtos.empty:
            return pd.DataFrame()

        df_vendas = pd.read_sql_query(text(sql_vendas), conn, params={'dt_v_ini': dt_v_ini, 'dt_v_fim': dt_v_fim})
        df_compras = pd.read_sql_query(text(sql_compras), conn, params={'dt_c_ini': dt_c_ini, 'dt_c_fim': dt_c_fim})
        df_estoque = pd.read_sql_query(text(sql_estoque), conn)

    # Consolidação dos Dados via Pandas
    df_res = df_produtos.merge(df_vendas, on='IdProduto', how='left')
    df_res = df_res.merge(df_compras, on='IdProduto', how='left')
    df_res = df_res.merge(df_estoque, on='IdProduto', how='left')

    df_res.drop(columns=['IdProduto'], inplace=True)
    df_res.fillna(0, inplace=True)

    # Filtra apenas itens movimentados ou estocados
    df_res = df_res[(df_res['Total Vendas'] > 0) | (df_res['Qtd Comprada'] > 0) | (df_res['Est. Total'] > 0)]

    if not df_res.empty:
        df_res["Venda Média/Dia"] = df_res["Total Vendas"] / dias_periodo
        df_res["Cobertura (Dias)"] = df_res.apply(
            lambda r: round(r["Est. Total"] / r["Venda Média/Dia"], 1) if r["Venda Média/Dia"] > 0 else (999.0 if r["Est. Total"] > 0 else 0.0),
            axis=1
        )
        df_res["Valor em Estoque (R$)"] = df_res["Est. Total"] * df_res["Custo Compra"]
        df_res.sort_values(by="Descrição", inplace=True)

    return df_res