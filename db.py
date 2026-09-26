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
    query = "SELECT DISTINCT NOMEFABR FROM Fabricantes WHERE NOMEFABR IS NOT NULL ORDER BY NOMEFABR"
    df = pd.read_sql(query, engine)
    return df['NOMEFABR'].tolist()

@st.cache_data(ttl=3600)
def carregar_departamentos():
    engine = get_engine()
    query = """
        SELECT DISTINCT LEFT(CodGrupo, 2) AS Codigo, NomeGrupo 
        FROM Grupos 
        WHERE LEN(REPLACE(CodGrupo, '.', '')) = 2 OR LEN(CodGrupo) = 2
        ORDER BY NomeGrupo
    """
    df = pd.read_sql(query, engine)
    return dict(zip(df['NomeGrupo'], df['Codigo']))

@st.cache_data(ttl=3600)
def carregar_grupos(cod_depto=None):
    engine = get_engine()
    query = """
        SELECT DISTINCT CodGrupo AS Codigo, NomeGrupo 
        FROM Grupos 
        WHERE (LEN(REPLACE(CodGrupo, '.', '')) = 4 OR LEN(CodGrupo) = 5)
    """
    if cod_depto:
        query += f" AND LEFT(CodGrupo, 2) = '{cod_depto}'"
    query += " ORDER BY NomeGrupo"
    df = pd.read_sql(query, engine)
    return dict(zip(df['NomeGrupo'], df['Codigo']))

@st.cache_data(ttl=3600)
def carregar_subgrupos(cod_grupo=None):
    engine = get_engine()
    query = """
        SELECT DISTINCT CodGrupo AS Codigo, NomeGrupo 
        FROM Grupos 
        WHERE (LEN(REPLACE(CodGrupo, '.', '')) > 5 OR LEN(CodGrupo) >= 8)
    """
    if cod_grupo:
        query += f" AND LEFT(CodGrupo, 5) = '{cod_grupo}'"
    query += " ORDER BY NomeGrupo"
    df = pd.read_sql(query, engine)
    return dict(zip(df['NomeGrupo'], df['Codigo']))

def buscar_produtos_movimentacao_completa(fornecedor, depto, grupo, subgrupo, data_ini_venda, data_fim_venda, data_ini_compra, data_fim_compra):
    engine = get_engine()
    
    dt_v_ini_str = data_ini_venda.strftime('%Y-%m-%d')
    dt_v_fim_str = data_fim_venda.strftime('%Y-%m-%d')
    dt_c_ini_str = data_ini_compra.strftime('%Y-%m-%d')
    dt_c_fim_str = data_fim_compra.strftime('%Y-%m-%d')
    
    dias_periodo = max((data_fim_venda - data_ini_venda).days + 1, 1)

    # Construção dinâmica de filtros para evitar repetição de parâmetros no pymssql
    cond_prod_list = ["p.ProdutoInativo = 'N'"]
    
    if fornecedor:
        cond_prod_list.append(f"f.NOMEFABR = '{fornecedor.replace("'", "''")}'")
    if depto:
        cond_prod_list.append(f"LEFT(g.CodGrupo, 2) = '{depto}'")
    if grupo:
        cond_prod_list.append(f"LEFT(g.CodGrupo, 5) = '{grupo}'")
    if subgrupo:
        cond_prod_list.append(f"g.CodGrupo = '{subgrupo}'")
        
    cond_prod = " AND ".join(cond_prod_list)

    query_sql = f"""
        WITH VendasBase AS (
            SELECT 
                p.IdProduto,
                m.CodFilial,
                CASE 
                    WHEN m.TipoMov = '2.4' THEN (i.Qtd - ISNULL(i.QtdCancel, 0)) / NULLIF(i.FatorConvUnid, 0)
                    WHEN m.TipoMov IN ('2.3', '2.8') THEN -1 * ((i.Qtd - ISNULL(i.QtdCancel, 0)) / NULLIF(i.FatorConvUnid, 0))
                    ELSE 0
                END AS QtdVendidaLiquida
            FROM Produtos p WITH (NOLOCK)
            INNER JOIN Fabricantes f WITH (NOLOCK) ON p.CODFABR = f.CODFABR
            LEFT JOIN Grupos g WITH (NOLOCK) ON p.IdGrupo = g.IdGrupo
            INNER JOIN ItensMov i WITH (NOLOCK) ON p.IdProduto = i.IdProduto
            INNER JOIN Movimento m WITH (NOLOCK) ON i.IdMov = m.IdMov
            WHERE {cond_prod}
                AND m.CodLocal = '01'
                AND m.TipoMov IN ('2.4', '2.3', '2.8')
                AND (m.TipoMov != '2.4' OR m.NfeStatus = 'U')
                AND m.DtFinalizacao >= '{dt_v_ini_str}'
                AND m.DtFinalizacao < DATEADD(day, 1, '{dt_v_fim_str}')
                AND m.CodCliFor NOT IN ('C08327','F00074','C08328','F10077','C22206','F15703','C16205','F14688','C30965','F16834')
        ),
        VendasPivot AS (
            SELECT 
                v.IdProduto,
                SUM(CASE WHEN v.CodFilial = 1 THEN v.QtdVendidaLiquida ELSE 0 END) AS QtdVendidaPBAL,
                SUM(CASE WHEN v.CodFilial = 2 THEN v.QtdVendidaLiquida ELSE 0 END) AS QtdVendidaPBVIA,
                SUM(CASE WHEN v.CodFilial = 3 THEN v.QtdVendidaLiquida ELSE 0 END) AS QtdVendidaPBZS,
                SUM(CASE WHEN v.CodFilial = 4 THEN v.QtdVendidaLiquida ELSE 0 END) AS QtdVendidaPBZN,
                SUM(v.QtdVendidaLiquida) AS QtdTotalVendida
            FROM VendasBase v
            GROUP BY v.IdProduto
        ),
        ComprasBase AS (
            SELECT 
                p.IdProduto,
                SUM((i.Qtd - ISNULL(i.QtdCancel, 0)) / NULLIF(i.FatorConvUnid, 0)) AS QtdComprada
            FROM Produtos p WITH (NOLOCK)
            INNER JOIN Fabricantes f WITH (NOLOCK) ON p.CODFABR = f.CODFABR
            LEFT JOIN Grupos g WITH (NOLOCK) ON p.IdGrupo = g.IdGrupo
            INNER JOIN ItensMov i WITH (NOLOCK) ON p.IdProduto = i.IdProduto
            INNER JOIN Movimento m WITH (NOLOCK) ON i.IdMov = m.IdMov
            WHERE {cond_prod}
                AND m.CodLocal = '01'
                AND m.TipoMov IN ('1.1', '1.6')
                AND m.DtFinalizacao >= '{dt_c_ini_str}'
                AND m.DtFinalizacao < DATEADD(day, 1, '{dt_c_fim_str}')
                AND m.CodCliFor NOT IN ('C08327','F00074','C08328','F10077','C22206','F15703','C16205','F14688','C30965','F16834')
            GROUP BY p.IdProduto
        ),
        EstoquePivot AS (
            SELECT 
                e.IdProduto,
                SUM(CASE WHEN e.CodFilial = 1 THEN e.EstoqueAtual ELSE 0 END) AS EstPBAL,
                SUM(CASE WHEN e.CodFilial = 2 THEN e.EstoqueAtual ELSE 0 END) AS EstPBVIA,
                SUM(CASE WHEN e.CodFilial = 3 THEN e.EstoqueAtual ELSE 0 END) AS EstPBZS,
                SUM(CASE WHEN e.CodFilial = 4 THEN e.EstoqueAtual ELSE 0 END) AS EstPBZN,
                SUM(e.EstoqueAtual) AS EstTotal
            FROM EstqProdutos e WITH (NOLOCK)
            WHERE e.CodLocal = '01'
            GROUP BY e.IdProduto
        ),
        ProdutosFiltrados AS (
            SELECT DISTINCT
                p.IdProduto,
                p.CODPRODUTO AS CodigoProduto,
                p.CodProdutoFabr AS ReferenciaFabricante,
                p.NOMEPRODUTO AS DescricaoProduto,
                p.UNID AS Unidade,
                p.CustoCompra
            FROM Produtos p WITH (NOLOCK)
            INNER JOIN Fabricantes f WITH (NOLOCK) ON p.CODFABR = f.CODFABR
            LEFT JOIN Grupos g WITH (NOLOCK) ON p.IdGrupo = g.IdGrupo
            WHERE {cond_prod}
        )
        SELECT 
            ROW_NUMBER() OVER (ORDER BY pf.DescricaoProduto) AS [Nº],
            pf.CodigoProduto AS [Código],
            pf.ReferenciaFabricante AS [Ref. Fabr.],
            pf.DescricaoProduto AS [Descrição],
            pf.Unidade AS [Unid],
            pf.CustoCompra AS [Custo Compra],
            
            ISNULL(ep.EstPBAL, 0)  AS [Est. Alecrim],
            ISNULL(ep.EstPBVIA, 0) AS [Est. Via Direta],
            ISNULL(ep.EstPBZS, 0)  AS [Est. Zona Sul],
            ISNULL(ep.EstPBZN, 0)  AS [Est. Zona Norte],
            ISNULL(ep.EstTotal, 0) AS [Est. Total],
            
            ISNULL(vp.QtdVendidaPBAL, 0)  AS [Venda PBAL],
            ISNULL(vp.QtdVendidaPBVIA, 0) AS [Venda PBVIA],
            ISNULL(vp.QtdVendidaPBZS, 0)  AS [Venda PBZS],
            ISNULL(vp.QtdVendidaPBZN, 0)  AS [Venda PBZN],
            ISNULL(vp.QtdTotalVendida, 0) AS [Total Vendas],
            ISNULL(cb.QtdComprada, 0)     AS [Qtd Comprada]
        FROM ProdutosFiltrados pf
        LEFT JOIN VendasPivot vp ON pf.IdProduto = vp.IdProduto
        LEFT JOIN ComprasBase cb ON pf.IdProduto = cb.IdProduto
        LEFT JOIN EstoquePivot ep ON pf.IdProduto = ep.IdProduto
        WHERE ISNULL(vp.QtdTotalVendida, 0) > 0 OR ISNULL(cb.QtdComprada, 0) > 0 OR ISNULL(ep.EstTotal, 0) > 0
        ORDER BY pf.DescricaoProduto;
    """
    
    with engine.connect() as conn:
        df = pd.read_sql(text(query_sql), conn)
        
    if not df.empty:
        df["Venda Média/Dia"] = df["Total Vendas"] / dias_periodo
        df["Cobertura (Dias)"] = df.apply(
            lambda r: round(r["Est. Total"] / r["Venda Média/Dia"], 1) if r["Venda Média/Dia"] > 0 else (999.0 if r["Est. Total"] > 0 else 0.0), 
            axis=1
        )
        df["Valor em Estoque (R$)"] = df["Est. Total"] * df["Custo Compra"]
    
    return df