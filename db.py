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

def buscar_analise_pontuacao_completa(fornecedor, depto, grupo, subgrupo, data_ini, data_fim):
    engine = get_engine()
    
    dt_ini_str = data_ini.strftime('%Y-%m-%d')
    dt_fim_str = data_fim.strftime('%Y-%m-%d')

    cond_prod_list = ["LEFT(g.CodGrupo, 2) NOT IN ('09', '10')", "p.ProdutoInativo = 'N'"]
    
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
        WITH ProdutosBase AS (
            SELECT
                p.IdProduto, p.CODPRODUTO, p.CodProdutoFabr, p.NOMEPRODUTO, p.UNID, p.CODFABR, f.NOMEFABR,
                g.CodGrupo, g.NomeGrupo,
                LEFT(g.CodGrupo, 2) AS CodDepartamento,
                LEFT(g.CodGrupo, 5) AS CodGrupoNivel,
                p.CustoCompra, p.PrecoVenda1, p.PrecoVenda2, p.PrecoVenda3, p.PrecoVenda4
            FROM Produtos p WITH (NOLOCK)
            LEFT JOIN Fabricantes f WITH (NOLOCK) ON f.CODFABR = p.CODFABR
            LEFT JOIN Grupos g WITH (NOLOCK) ON g.IdGrupo = p.IdGrupo
            WHERE {cond_prod}
        ),
        Compras AS (
            SELECT
                i.IdProduto, m.CodFilial,
                SUM((i.Qtd - ISNULL(i.QtdCancel, 0)) / NULLIF(i.FatorConvUnid, 0)) AS QtdComprada
            FROM ItensMov i WITH (NOLOCK)
            INNER JOIN Movimento m WITH (NOLOCK) ON m.IdMov = i.IdMov
            INNER JOIN ProdutosBase pb ON pb.IdProduto = i.IdProduto
            WHERE m.TipoMov = '1.1'
              AND m.CodCliFor NOT IN ('C08327','F00074','C08328','F10077','C22206','F15703','C16205','F14688','C30965','F16834')
              AND m.DtFinalizacao >= '{dt_ini_str}' AND m.DtFinalizacao < DATEADD(DAY, 1, '{dt_fim_str}')
              AND m.CodFilial IN (1, 2, 3, 4, 5)
            GROUP BY i.IdProduto, m.CodFilial
        ),
        Vendas AS (
            SELECT
                i.IdProduto, m.CodFilial,
                SUM((i.Qtd - ISNULL(i.QtdCancel, 0)) / NULLIF(i.FatorConvUnid, 0)) AS QtdVendida
            FROM ItensMov i WITH (NOLOCK)
            INNER JOIN Movimento m WITH (NOLOCK) ON m.IdMov = i.IdMov
            INNER JOIN ProdutosBase pb ON pb.IdProduto = i.IdProduto
            WHERE m.TipoMov = '2.4' AND m.NfeStatus = 'U'
              AND m.CodCliFor NOT IN ('C08327','F00074','C08328','F10077','C22206','F15703','C16205','F14688','C30965','F16834')
              AND m.DtFinalizacao >= '{dt_ini_str}' AND m.DtFinalizacao < DATEADD(DAY, 1, '{dt_fim_str}')
              AND m.CodFilial IN (1, 2, 3, 4, 5)
            GROUP BY i.IdProduto, m.CodFilial
        ),
        DiasVendaAtiva AS (
            SELECT
                i.IdProduto, m.CodFilial,
                COUNT(DISTINCT CAST(m.DtFinalizacao AS DATE)) AS DiasAtivo
            FROM ItensMov i WITH (NOLOCK)
            INNER JOIN Movimento m WITH (NOLOCK) ON m.IdMov = i.IdMov
            INNER JOIN ProdutosBase pb ON pb.IdProduto = i.IdProduto
            WHERE m.TipoMov = '2.4' AND m.NfeStatus = 'U'
              AND m.CodCliFor NOT IN ('C08327','F00074','C08328','F10077','C22206','F15703','C16205','F14688','C30965','F16834')
              AND m.DtFinalizacao >= '{dt_ini_str}' AND m.DtFinalizacao < DATEADD(DAY, 1, '{dt_fim_str}')
              AND m.CodFilial IN (1, 2, 3, 4, 5)
            GROUP BY i.IdProduto, m.CodFilial
        ),
        TransferenciasResumo AS (
            SELECT
                i.IdProduto, m.CodFilial,
                SUM(CASE WHEN m.TipoMov IN ('1.1','1.2') THEN (i.Qtd - ISNULL(i.QtdCancel, 0)) / NULLIF(i.FatorConvUnid, 0) ELSE 0 END) AS QtdTransferidaRecebida,
                SUM(CASE WHEN m.TipoMov IN ('2.2','2.4','2.9') THEN (i.Qtd - ISNULL(i.QtdCancel, 0)) / NULLIF(i.FatorConvUnid, 0) ELSE 0 END) AS QtdTransferidaEnviada
            FROM ItensMov i WITH (NOLOCK)
            INNER JOIN Movimento m WITH (NOLOCK) ON m.IdMov = i.IdMov
            INNER JOIN ProdutosBase pb ON pb.IdProduto = i.IdProduto
            WHERE m.CodCliFor IN ('C08327','F00074','C08328','F10077','C22206','F15703','C16205','F14688','C30965','F16834')
              AND m.TipoMov IN ('1.1','1.2','2.2','2.4','2.9')
              AND (m.TipoMov IN ('1.1','1.2','2.2') OR (m.TipoMov IN ('2.4','2.9') AND m.NfeStatus = 'U'))
              AND m.DtFinalizacao >= '{dt_ini_str}' AND m.DtFinalizacao < DATEADD(DAY, 1, '{dt_fim_str}')
              AND m.CodFilial IN (1, 2, 3, 4, 5)
            GROUP BY i.IdProduto, m.CodFilial
        ),
        ProdutoFilial AS (
            SELECT pb.*, f.CodFilial,
                CASE f.CodFilial WHEN 1 THEN 'ALECRIM' WHEN 2 THEN 'VIA DIRETA' WHEN 3 THEN 'ZONA SUL' WHEN 4 THEN 'ZONA NORTE' WHEN 5 THEN 'ATACADO' END AS Filial,
                CASE f.CodFilial WHEN 1 THEN 'PBAL' WHEN 2 THEN 'PBVIA' WHEN 3 THEN 'PBZS' WHEN 4 THEN 'PBZN' WHEN 5 THEN 'PBAT' END AS SiglaFilial
            FROM ProdutosBase pb
            CROSS JOIN (SELECT 1 AS CodFilial UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5) f
        ),
        ResultadoBase AS (
            SELECT
                pf.IdProduto, pf.CODPRODUTO AS CodigoProduto, pf.CodProdutoFabr AS ReferenciaFabricante, pf.NOMEPRODUTO AS Produto, pf.UNID AS Embalagem,
                pf.CODFABR AS CodigoFabricante, pf.NOMEFABR AS Fabricante, pf.CodDepartamento AS CodigoDepartamento, pf.CodGrupoNivel AS CodigoGrupo, pf.CodGrupo AS CodigoSubgrupo, pf.NomeGrupo,
                pf.CodFilial AS CodigoFilial, pf.Filial, pf.SiglaFilial,
                CAST(ISNULL(pf.CustoCompra, 0) AS DECIMAL(18, 2)) AS CustoCompra,
                CAST(CASE pf.CodFilial WHEN 1 THEN ISNULL(pf.PrecoVenda1, 0) WHEN 2 THEN ISNULL(pf.PrecoVenda2, 0) WHEN 3 THEN ISNULL(pf.PrecoVenda3, 0) WHEN 4 THEN ISNULL(pf.PrecoVenda4, 0) WHEN 5 THEN ISNULL(pf.PrecoVenda1, 0) END AS DECIMAL(18, 2)) AS PrecoVenda,
                CAST(ISNULL(c.QtdComprada, 0) AS DECIMAL(18, 2)) AS QtdComprada,
                CAST(ISNULL(tr.QtdTransferidaRecebida, 0) AS DECIMAL(18, 2)) AS QtdTransferidaRecebida,
                CAST(ISNULL(tr.QtdTransferidaEnviada, 0) AS DECIMAL(18, 2)) AS QtdTransferidaEnviada,
                CAST(ISNULL(v.QtdVendida, 0) AS DECIMAL(18, 2)) AS QtdVendida,
                ISNULL(dva.DiasAtivo, 0) AS DiasAtivo,
                CAST(ISNULL(v.QtdVendida, 0) * ISNULL(pf.CustoCompra, 0) AS DECIMAL(18, 2)) AS ValorVendidoCusto,
                CAST(ISNULL(v.QtdVendida, 0) * CASE pf.CodFilial WHEN 1 THEN ISNULL(pf.PrecoVenda1, 0) WHEN 2 THEN ISNULL(pf.PrecoVenda2, 0) WHEN 3 THEN ISNULL(pf.PrecoVenda3, 0) WHEN 4 THEN ISNULL(pf.PrecoVenda4, 0) WHEN 5 THEN ISNULL(pf.PrecoVenda1, 0) END AS DECIMAL(18, 2)) AS ValorVendidoVenda,
                CAST(ISNULL(c.QtdComprada, 0) + ISNULL(tr.QtdTransferidaRecebida, 0) - ISNULL(tr.QtdTransferidaEnviada, 0) - ISNULL(v.QtdVendida, 0) AS DECIMAL(18, 2)) AS SaldoProvavel
            FROM ProdutoFilial pf
            LEFT JOIN Compras c ON c.IdProduto = pf.IdProduto AND c.CodFilial = pf.CodFilial
            LEFT JOIN Vendas v ON v.IdProduto = pf.IdProduto AND v.CodFilial = pf.CodFilial
            LEFT JOIN DiasVendaAtiva dva ON dva.IdProduto = pf.IdProduto AND dva.CodFilial = pf.CodFilial
            LEFT JOIN TransferenciasResumo tr ON tr.IdProduto = pf.IdProduto AND tr.CodFilial = pf.CodFilial
            WHERE ISNULL(c.QtdComprada, 0) <> 0 OR ISNULL(tr.QtdTransferidaRecebida, 0) <> 0 OR ISNULL(tr.QtdTransferidaEnviada, 0) <> 0 OR ISNULL(v.QtdVendida, 0) <> 0
        ),
        RankingFilial AS (
            SELECT rb.*,
                SUM(rb.ValorVendidoVenda) OVER (PARTITION BY rb.CodigoFilial ORDER BY rb.ValorVendidoVenda DESC, rb.IdProduto ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS AcumuladoVendaValorFilial,
                SUM(rb.ValorVendidoVenda) OVER (PARTITION BY rb.CodigoFilial) AS TotalVendaFilial
            FROM ResultadoBase rb
        ),
        CurvaFilial AS (
            SELECT rf.*,
                CAST(CASE WHEN rf.TotalVendaFilial = 0 THEN NULL ELSE rf.AcumuladoVendaValorFilial / rf.TotalVendaFilial END AS DECIMAL(18, 4)) AS AcumuladoVendaPorcFilial
            FROM RankingFilial rf
        )
        SELECT 
            cf.CodigoProduto AS [Código],
            cf.ReferenciaFabricante AS [Ref. Fabr.],
            cf.Produto AS [Descrição],
            cf.Embalagem AS [Unid],
            cf.Fabricante,
            cf.Filial,
            cf.CustoCompra AS [Custo],
            cf.PrecoVenda AS [Preço Venda],
            cf.QtdVendida AS [Qtd Vendida],
            cf.ValorVendidoVenda AS [Venda Total (R$)],
            cf.SaldoProvavel AS [Saldo Provável],
            CASE
                WHEN cf.AcumuladoVendaPorcFilial <= 0.30 THEN 'A'
                WHEN cf.AcumuladoVendaPorcFilial <= 0.55 THEN 'B'
                WHEN cf.AcumuladoVendaPorcFilial <= 0.75 THEN 'C'
                WHEN cf.AcumuladoVendaPorcFilial <= 0.90 THEN 'D'
                ELSE 'E'
            END AS [Curva Venda Filial],
            CAST(CASE WHEN cf.AcumuladoVendaPorcFilial IS NULL THEN 0.0 ELSE (1.0 - cf.AcumuladoVendaPorcFilial) * 100 END AS DECIMAL(18, 2)) AS [Pontuação Giro]
        FROM CurvaFilial cf
        ORDER BY cf.ValorVendidoVenda DESC;
    """
    
    with engine.connect() as conn:
        df = pd.read_sql(text(query_sql), conn)
    
    return df