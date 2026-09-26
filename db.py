import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

def get_engine():
    cred = st.secrets["sql_server"]
    db_url = f"mssql+pymssql://{cred['username']}:{cred['password']}@{cred['server']}:{cred['port']}/{cred['database']}"
    return create_engine(db_url)

@st.cache_data(ttl=3600)
def carregar_fabricantes():
    engine = get_engine()
    query = "SELECT DISTINCT NOMEFABR FROM Fabricantes WHERE NOMEFABR IS NOT NULL ORDER BY NOMEFABR"
    with engine.raw_connection() as conn:
        df = pd.read_sql_query(query, conn)
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
    with engine.raw_connection() as conn:
        df = pd.read_sql_query(query, conn)
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
        depto_esc = str(cod_depto).replace("'", "''")
        query += f" AND LEFT(CodGrupo, 2) = '{depto_esc}'"
    query += " ORDER BY NomeGrupo"
    
    with engine.raw_connection() as conn:
        df = pd.read_sql_query(query, conn)
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
        grupo_esc = str(cod_grupo).replace("'", "''")
        query += f" AND LEFT(CodGrupo, 5) = '{grupo_esc}'"
    query += " ORDER BY NomeGrupo"
    
    with engine.raw_connection() as conn:
        df = pd.read_sql_query(query, conn)
    return dict(zip(df['NomeGrupo'], df['Codigo']))

def buscar_produtos_movimentacao_completa(fornecedor, depto, grupo, subgrupo, data_ini_venda, data_fim_venda, data_ini_compra, data_fim_compra):
    engine = get_engine()
    
    dt_v_ini_str = data_ini_venda.strftime('%Y-%m-%d')
    dt_v_fim_str = data_fim_venda.strftime('%Y-%m-%d')
    dt_c_ini_str = data_ini_compra.strftime('%Y-%m-%d')
    dt_c_fim_str = data_fim_compra.strftime('%Y-%m-%d')
    
    dias_periodo = max((data_fim_venda - data_ini_venda).days + 1, 1)

    where_clauses = ["LEFT(g.CodGrupo, 2) NOT IN ('09', '10')", "p.ProdutoInativo = 'N'"]

    if fornecedor:
        fornecedor_esc = str(fornecedor).replace("'", "''")
        where_clauses.append(f"f.NOMEFABR = '{fornecedor_esc}'")
    if depto:
        depto_esc = str(depto).replace("'", "''")
        where_clauses.append(f"LEFT(g.CodGrupo, 2) = '{depto_esc}'")
    if grupo:
        grupo_esc = str(grupo).replace("'", "''")
        where_clauses.append(f"LEFT(g.CodGrupo, 5) = '{grupo_esc}'")
    if subgrupo:
        subgrupo_esc = str(subgrupo).replace("'", "''")
        where_clauses.append(f"g.CodGrupo = '{subgrupo_esc}'")

    cond_prod = " AND ".join(where_clauses)

    # Nomes dos aliases ajustados sem caracteres especiais no SQL (a renomeacao final é feita pelo Pandas)
    query_sql = f"""
        WITH ProdutosBase AS (
            SELECT
                p.IdProduto,
                p.CODPRODUTO,
                p.CodProdutoFabr,
                p.NOMEPRODUTO,
                p.UNID,
                p.CODFABR,
                f.NOMEFABR,
                g.CodGrupo,
                g.NomeGrupo,
                p.CustoCompra
            FROM Produtos p WITH (NOLOCK)
            LEFT JOIN Fabricantes f WITH (NOLOCK) ON f.CODFABR = p.CODFABR
            LEFT JOIN Grupos g WITH (NOLOCK) ON g.IdGrupo = p.IdGrupo
            WHERE {cond_prod}
        ),
        ComprasBase AS (
            SELECT
                i.IdProduto,
                SUM((i.Qtd - ISNULL(i.QtdCancel, 0)) / NULLIF(i.FatorConvUnid, 0)) AS QtdComprada
            FROM ItensMov i WITH (NOLOCK)
            INNER JOIN Movimento m WITH (NOLOCK) ON m.IdMov = i.IdMov
            INNER JOIN ProdutosBase pb ON pb.IdProduto = i.IdProduto
            WHERE m.TipoMov = '1.1'
              AND m.CodCliFor NOT IN ('C08327','F00074','C08328','F10077','C22206','F15703','C16205','F14688','C30965','F16834')
              AND m.DtFinalizacao >= '{dt_c_ini_str}'
              AND m.DtFinalizacao < DATEADD(DAY, 1, '{dt_c_fim_str}')
            GROUP BY i.IdProduto
        ),
        VendasBase AS (
            SELECT
                i.IdProduto,
                SUM(CASE WHEN m.CodFilial = 1 THEN (i.Qtd - ISNULL(i.QtdCancel, 0)) / NULLIF(i.FatorConvUnid, 0) ELSE 0 END) AS VendaPBAL,
                SUM(CASE WHEN m.CodFilial = 2 THEN (i.Qtd - ISNULL(i.QtdCancel, 0)) / NULLIF(i.FatorConvUnid, 0) ELSE 0 END) AS VendaPBVIA,
                SUM(CASE WHEN m.CodFilial = 3 THEN (i.Qtd - ISNULL(i.QtdCancel, 0)) / NULLIF(i.FatorConvUnid, 0) ELSE 0 END) AS VendaPBZS,
                SUM(CASE WHEN m.CodFilial = 4 THEN (i.Qtd - ISNULL(i.QtdCancel, 0)) / NULLIF(i.FatorConvUnid, 0) ELSE 0 END) AS VendaPBZN,
                SUM((i.Qtd - ISNULL(i.QtdCancel, 0)) / NULLIF(i.FatorConvUnid, 0)) AS TotalVendas
            FROM ItensMov i WITH (NOLOCK)
            INNER JOIN Movimento m WITH (NOLOCK) ON m.IdMov = i.IdMov
            INNER JOIN ProdutosBase pb ON pb.IdProduto = i.IdProduto
            WHERE m.TipoMov = '2.4' AND m.NfeStatus = 'U'
              AND m.CodCliFor NOT IN ('C08327','F00074','C08328','F10077','C22206','F15703','C16205','F14688','C30965','F16834')
              AND m.DtFinalizacao >= '{dt_v_ini_str}'
              AND m.DtFinalizacao < DATEADD(DAY, 1, '{dt_v_fim_str}')
            GROUP BY i.IdProduto
        ),
        EstoqueBase AS (
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
        )
        SELECT 
            pb.CODPRODUTO AS Codigo,
            pb.CodProdutoFabr AS RefFabr,
            pb.NOMEPRODUTO AS Descricao,
            pb.UNID AS Unid,
            CAST(ISNULL(pb.CustoCompra, 0) AS DECIMAL(18, 2)) AS CustoCompra,
            
            ISNULL(eb.EstPBAL, 0) AS EstAlecrim,
            ISNULL(eb.EstPBVIA, 0) AS EstViaDireta,
            ISNULL(eb.EstPBZS, 0) AS EstZonaSul,
            ISNULL(eb.EstPBZN, 0) AS EstZonaNorte,
            ISNULL(eb.EstTotal, 0) AS EstTotal,
            
            ISNULL(vb.VendaPBAL, 0) AS VendaPBAL,
            ISNULL(vb.VendaPBVIA, 0) AS VendaPBVIA,
            ISNULL(vb.VendaPBZS, 0) AS VendaPBZS,
            ISNULL(vb.VendaPBZN, 0) AS VendaPBZN,
            ISNULL(vb.TotalVendas, 0) AS TotalVendas,
            
            ISNULL(cb.QtdComprada, 0) AS QtdComprada
        FROM ProdutosBase pb
        LEFT JOIN VendasBase vb ON vb.IdProduto = pb.IdProduto
        LEFT JOIN ComprasBase cb ON cb.IdProduto = pb.IdProduto
        LEFT JOIN EstoqueBase eb ON eb.IdProduto = pb.IdProduto
        WHERE ISNULL(vb.TotalVendas, 0) > 0 OR ISNULL(cb.QtdComprada, 0) > 0 OR ISNULL(eb.EstTotal, 0) > 0
        ORDER BY pb.NOMEPRODUTO
    """
    
    # Execução através do driver pymssql direto (ignora SQLAlchemy wrapper)
    with engine.raw_connection() as conn:
        df = pd.read_sql_query(query_sql, conn)
        
    if not df.empty:
        # Renomeia colunas no Pandas para exibição limpa no Streamlit
        df = df.rename(columns={
            "Codigo": "Código",
            "RefFabr": "Ref. Fabr.",
            "Descricao": "Descrição",
            "CustoCompra": "Custo Compra",
            "EstAlecrim": "Est. Alecrim",
            "EstViaDireta": "Est. Via Direta",
            "EstZonaSul": "Est. Zona Sul",
            "EstZonaNorte": "Est. Zona Norte",
            "EstTotal": "Est. Total",
            "VendaPBAL": "Venda PBAL",
            "VendaPBVIA": "Venda PBVIA",
            "VendaPBZS": "Venda PBZS",
            "VendaPBZN": "Venda PBZN",
            "TotalVendas": "Total Vendas",
            "QtdComprada": "Qtd Comprada"
        })
        
        df["Venda Média/Dia"] = df["Total Vendas"] / dias_periodo
        df["Cobertura (Dias)"] = df.apply(
            lambda r: round(r["Est. Total"] / r["Venda Média/Dia"], 1) if r["Venda Média/Dia"] > 0 else (999.0 if r["Est. Total"] > 0 else 0.0), 
            axis=1
        )
        df["Valor em Estoque (R$)"] = df["Est. Total"] * df["Custo Compra"]
    
    return df