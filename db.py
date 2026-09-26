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

def buscar_produtos_movimentacao(fornecedor, depto, grupo, subgrupo, data_ini_venda, data_fim_venda, data_ini_compra, data_fim_compra):
    engine = get_engine()
    
    dt_v_ini_str = data_ini_venda.strftime('%Y-%m-%d')
    dt_v_fim_str = data_fim_venda.strftime('%Y-%m-%d')
    dt_c_ini_str = data_ini_compra.strftime('%Y-%m-%d')
    dt_c_fim_str = data_fim_compra.strftime('%Y-%m-%d')

    query_sql = """
        DECLARE @dataInicioVenda DATE = :dt_ini_venda;
        DECLARE @dataFimVenda DATE    = :dt_fim_venda;
        DECLARE @dataInicioCompra DATE = :dt_ini_compra;
        DECLARE @dataFimCompra DATE    = :dt_fim_compra;
        DECLARE @filtroFabricante VARCHAR(100) = :fornecedor;
        DECLARE @filtroDepto VARCHAR(10) = :depto;
        DECLARE @filtroGrupo VARCHAR(10) = :grupo;
        DECLARE @filtroSubgrupo VARCHAR(20) = :subgrupo;

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
            WHERE p.ProdutoInativo = 'N'
                AND m.CodLocal = '01'
                AND m.TipoMov IN ('2.4', '2.3', '2.8')
                AND (m.TipoMov != '2.4' OR m.NfeStatus = 'U')
                AND m.DtFinalizacao >= @dataInicioVenda
                AND m.DtFinalizacao < DATEADD(day, 1, @dataFimVenda)
                AND m.CodCliFor NOT IN ('C08327','F00074','C08328','F10077','C22206','F15703','C16205','F14688','C30965','F16834')
                AND (@filtroFabricante IS NULL OR f.NOMEFABR = @filtroFabricante)
                AND (@filtroDepto IS NULL OR LEFT(g.CodGrupo, 2) = @filtroDepto)
                AND (@filtroGrupo IS NULL OR LEFT(g.CodGrupo, 5) = @filtroGrupo)
                AND (@filtroSubgrupo IS NULL OR g.CodGrupo = @filtroSubgrupo)
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
            WHERE p.ProdutoInativo = 'N'
                AND m.CodLocal = '01'
                AND m.TipoMov IN ('1.1', '1.6')
                AND m.DtFinalizacao >= @dataInicioCompra
                AND m.DtFinalizacao < DATEADD(day, 1, @dataFimCompra)
                AND m.CodCliFor NOT IN ('C08327','F00074','C08328','F10077','C22206','F15703','C16205','F14688','C30965','F16834')
                AND (@filtroFabricante IS NULL OR f.NOMEFABR = @filtroFabricante)
                AND (@filtroDepto IS NULL OR LEFT(g.CodGrupo, 2) = @filtroDepto)
                AND (@filtroGrupo IS NULL OR LEFT(g.CodGrupo, 5) = @filtroGrupo)
                AND (@filtroSubgrupo IS NULL OR g.CodGrupo = @filtroSubgrupo)
            GROUP BY p.IdProduto
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
            WHERE p.ProdutoInativo = 'N'
              AND (@filtroFabricante IS NULL OR f.NOMEFABR = @filtroFabricante)
              AND (@filtroDepto IS NULL OR LEFT(g.CodGrupo, 2) = @filtroDepto)
              AND (@filtroGrupo IS NULL OR LEFT(g.CodGrupo, 5) = @filtroGrupo)
              AND (@filtroSubgrupo IS NULL OR g.CodGrupo = @filtroSubgrupo)
        )
        SELECT 
            ROW_NUMBER() OVER (ORDER BY pf.DescricaoProduto) AS [Nº],
            pf.CodigoProduto AS [Código],
            pf.ReferenciaFabricante AS [Ref. Fabr.],
            pf.DescricaoProduto AS [Descrição],
            pf.Unidade AS [Unid],
            pf.CustoCompra AS [Custo Compra],
            ISNULL(vp.QtdVendidaPBAL, 0)  AS [Venda PBAL],
            ISNULL(vp.QtdVendidaPBVIA, 0) AS [Venda PBVIA],
            ISNULL(vp.QtdVendidaPBZS, 0)  AS [Venda PBZS],
            ISNULL(vp.QtdVendidaPBZN, 0)  AS [Venda PBZN],
            ISNULL(vp.QtdTotalVendida, 0) AS [Total Vendas],
            ISNULL(cb.QtdComprada, 0)     AS [Qtd Comprada]
        FROM ProdutosFiltrados pf
        LEFT JOIN VendasPivot vp ON pf.IdProduto = vp.IdProduto
        LEFT JOIN ComprasBase cb ON pf.IdProduto = cb.IdProduto
        WHERE ISNULL(vp.QtdTotalVendida, 0) > 0 OR ISNULL(cb.QtdComprada, 0) > 0
        ORDER BY pf.DescricaoProduto;
    """
    
    params = {
        "fornecedor": fornecedor if fornecedor else None,
        "depto": depto if depto else None,
        "grupo": grupo if grupo else None,
        "subgrupo": subgrupo if subgrupo else None,
        "dt_ini_venda": dt_v_ini_str,
        "dt_fim_venda": dt_v_fim_str,
        "dt_ini_compra": dt_c_ini_str,
        "dt_fim_compra": dt_c_fim_str
    }
    
    with engine.connect() as conn:
        df = pd.read_sql(text(query_sql), conn, params=params)
    
    return df