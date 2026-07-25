# -*- coding: utf-8 -*-
"""
================================================================================
 GERADOR DA BASE-MÃE DE ESTOQUE (esquema estático para dashboard)
================================================================================
Converte o relatório raspado (matriz WIDE, que muda de linhas/colunas a cada
extração) em uma base LONG/tidy com ESQUEMA FIXO, enriquecida pelo catálogo
mestre de materiais.

  - Cada linha = 1 material em 1 almoxarifado (não mais 1 coluna por almox).
  - Almoxarifado novo vira LINHA, nunca coluna -> o dashboard nunca quebra.
  - Modo SNAPSHOT: a saída é substituída a cada execução (estoque atual).
  - Mantém apenas Quantidade > 0.

Como usar: ajuste os 3 caminhos em CONFIG e rode:  python gerar_base_estoque.py
================================================================================
"""

import os
import re
import sys
from datetime import datetime

import pandas as pd

# ============================== CONFIG =========================================
ARQ_MATRIZ   = r"C:\Users\User\Downloads\01_Inventario_Estoque\relatorio_inventario_CONSOLIDADO_MATRIZ.xlsx"
ARQ_CATALOGO = r"C:\Users\User\Downloads\DASH ALMOXARIFE V1\BASE_DADOS_COMPLETA.xlsx"
ARQ_SAIDA    = r"C:\Users\User\Downloads\DASH ALMOXARIFE V1\BASE_ESTOQUE.xlsx"

ABA_CATALOGO = "Materiais"          # aba do catálogo mestre
ABA_SAIDA    = "Estoque"            # aba gerada (lida pelo dashboard)
MANTER_ZERO  = False               # False = só Quantidade > 0 (snapshot de estoque)
# ===============================================================================

# Colunas do resultado final — ORDEM E NOMES FIXOS (nunca mudam entre extrações)
COLUNAS_FINAIS = [
    "Codigo", "Denominacao", "UnidadeMedida",
    "GrupoCodigo", "GrupoDenominacao", "SubgrupoMaterial",
    "CATMAT", "ElementoDespesa",
    "Almoxarifado", "Almox_Codigo",
    "Quantidade", "Data_Extracao",
]

RE_CODIGO_MATERIAL = re.compile(r"^\d{6,}$")          # material real = só dígitos, 6+
RE_CODIGO_ALMOX    = re.compile(r"(\d{2}(?:\.\d+)+)\s*$")  # código 20.xx.xx no fim do nome


def log(msg=""):
    print(msg, flush=True)


def carregar_matriz(caminho):
    """Lê a matriz raspada. Usa a 1ª aba se 'Inventario_Consolidado' não existir."""
    xls = pd.ExcelFile(caminho)
    aba = "Inventario_Consolidado"
    if aba not in xls.sheet_names:
        aba = xls.sheet_names[0]
    df = pd.read_excel(caminho, sheet_name=aba, dtype=str)
    df = df.dropna(axis=1, how="all")            # remove colunas 100% vazias
    df.columns = [str(c).strip() for c in df.columns]
    return df, aba


def carregar_catalogo(caminho, aba):
    cat = pd.read_excel(caminho, sheet_name=aba, dtype=str)
    cat.columns = [str(c).strip() for c in cat.columns]
    # normaliza chave e remove duplicatas de código (fica a 1ª ocorrência)
    cat["CodigoMaterial"] = cat["CodigoMaterial"].astype(str).str.strip()
    cat = cat.drop_duplicates(subset=["CodigoMaterial"], keep="first")
    return cat


def separar_nome_e_codigo_almox(nome_coluna):
    """'ALMOX ... - SIGLA 20.00.28.13' -> ('ALMOX ... - SIGLA', '20.00.28.13')"""
    m = RE_CODIGO_ALMOX.search(nome_coluna)
    codigo = m.group(1) if m else ""
    nome = RE_CODIGO_ALMOX.sub("", nome_coluna).strip().rstrip("-").strip()
    return nome, codigo


def gerar():
    # ---- validação de existência -------------------------------------------
    for rotulo, caminho in [("matriz", ARQ_MATRIZ), ("catálogo", ARQ_CATALOGO)]:
        if not os.path.exists(caminho):
            log(f"[ERRO] Arquivo de {rotulo} não encontrado:\n       {caminho}")
            sys.exit(1)

    log("=" * 70)
    log(" GERANDO BASE-MÃE DE ESTOQUE (snapshot)")
    log("=" * 70)

    # ---- 1) leitura ---------------------------------------------------------
    matriz, aba_usada = carregar_matriz(ARQ_MATRIZ)
    log(f"[1] Matriz lida: aba '{aba_usada}', {matriz.shape[0]} linhas x {matriz.shape[1]} colunas")

    # primeiras 3 colunas = identidade (Código / Denominação / Unid. Medida) por POSIÇÃO
    col_cod, col_den, col_uni = matriz.columns[:3]
    cols_almox = list(matriz.columns[3:])
    log(f"    Colunas de identidade: {col_cod!r}, {col_den!r}, {col_uni!r}")
    log(f"    Almoxarifados (colunas a despivotar): {len(cols_almox)}")

    # ---- 2) limpeza de linhas de lixo --------------------------------------
    cod = matriz[col_cod].astype(str).str.strip()
    eh_material = cod.str.match(RE_CODIGO_MATERIAL)
    # segurança extra: descarta linhas-cabeçalho de grupo (Denominação == Unid. Medida)
    eh_grupo = matriz[col_den].astype(str).str.strip() == matriz[col_uni].astype(str).str.strip()
    limpo = matriz[eh_material & ~eh_grupo].copy()
    descartadas = len(matriz) - len(limpo)
    log(f"[2] Limpeza: {descartadas} linhas de lixo removidas "
        f"(cabeçalhos de grupo, 'Total Geral', 'SEM MATERIAL')")
    log(f"    Materiais válidos: {len(limpo)}")

    # ---- 3) WIDE -> LONG (unpivot) -----------------------------------------
    longo = limpo.melt(
        id_vars=[col_cod, col_den, col_uni],
        value_vars=cols_almox,
        var_name="Almoxarifado_Full",
        value_name="Quantidade",
    )
    longo = longo.rename(columns={col_cod: "Codigo", col_den: "Denominacao", col_uni: "UnidadeMedida"})

    # ---- 4) Quantidade numérica + filtro > 0 -------------------------------
    longo["Quantidade"] = pd.to_numeric(longo["Quantidade"], errors="coerce").fillna(0)
    if not MANTER_ZERO:
        longo = longo[longo["Quantidade"] > 0].copy()
    # inteiro quando não há casas decimais
    if (longo["Quantidade"] % 1 == 0).all():
        longo["Quantidade"] = longo["Quantidade"].astype("int64")
    log(f"[3] Despivotado -> {len(longo)} linhas material×almoxarifado "
        f"({'todas' if MANTER_ZERO else 'apenas Quantidade > 0'})")

    # ---- 5) separar nome/código do almoxarifado ----------------------------
    nomes_cods = longo["Almoxarifado_Full"].map(separar_nome_e_codigo_almox)
    longo["Almoxarifado"] = nomes_cods.map(lambda t: t[0])
    longo["Almox_Codigo"] = nomes_cods.map(lambda t: t[1])
    longo["Codigo"] = longo["Codigo"].astype(str).str.strip()

    # ---- 6) enriquecer com o catálogo mestre -------------------------------
    cat = carregar_catalogo(ARQ_CATALOGO, ABA_CATALOGO)
    cols_cat = ["CodigoMaterial", "Denominacao", "UnidadeMedida",
                "CATMAT", "SubgrupoMaterial", "GrupoCodigo", "GrupoDenominacao", "ElementoDespesa"]
    cols_cat = [c for c in cols_cat if c in cat.columns]
    cat_j = cat[cols_cat].add_suffix("_cat")

    merged = longo.merge(cat_j, left_on="Codigo", right_on="CodigoMaterial_cat", how="left")

    # preferir texto do catálogo (canônico); cair para o raspado se faltar
    def prefere_catalogo(col_base, col_cat):
        if col_cat in merged.columns:
            return merged[col_cat].where(merged[col_cat].notna() & (merged[col_cat] != ""), merged[col_base])
        return merged[col_base]

    merged["Denominacao"]   = prefere_catalogo("Denominacao", "Denominacao_cat")
    merged["UnidadeMedida"] = prefere_catalogo("UnidadeMedida", "UnidadeMedida_cat")
    for alvo, origem in [("GrupoCodigo", "GrupoCodigo_cat"),
                         ("GrupoDenominacao", "GrupoDenominacao_cat"),
                         ("SubgrupoMaterial", "SubgrupoMaterial_cat"),
                         ("CATMAT", "CATMAT_cat"),
                         ("ElementoDespesa", "ElementoDespesa_cat")]:
        merged[alvo] = merged[origem] if origem in merged.columns else ""

    sem_cat = merged["CodigoMaterial_cat"].isna().sum()
    log(f"[4] Enriquecido pelo catálogo: {len(merged) - sem_cat} linhas casadas, "
        f"{sem_cat} sem correspondência no catálogo")

    # ---- 7) montar esquema final fixo --------------------------------------
    merged["Data_Extracao"] = datetime.now().strftime("%Y-%m-%d")
    for c in COLUNAS_FINAIS:
        if c not in merged.columns:
            merged[c] = ""
    final = merged[COLUNAS_FINAIS].copy()
    final = final.sort_values(["GrupoCodigo", "Denominacao", "Almoxarifado"]).reset_index(drop=True)

    # ---- 8) gravar (snapshot: substitui) -----------------------------------
    try:
        with pd.ExcelWriter(ARQ_SAIDA, engine="openpyxl") as w:
            final.to_excel(w, sheet_name=ABA_SAIDA, index=False)
    except PermissionError:
        log(f"\n[ERRO] Não consegui gravar em:\n       {ARQ_SAIDA}")
        log("       Feche o arquivo no Excel/OneDrive e rode de novo.")
        sys.exit(1)

    # ---- resumo -------------------------------------------------------------
    log("=" * 70)
    log(" RESUMO")
    log("=" * 70)
    log(f"  Linhas geradas .............. {len(final):,}".replace(",", "."))
    log(f"  Materiais distintos ......... {final['Codigo'].nunique():,}".replace(",", "."))
    log(f"  Almoxarifados distintos ..... {final['Almoxarifado'].nunique()}")
    log(f"  Quantidade total ............ {final['Quantidade'].sum():,}".replace(",", "."))
    log(f"  Data do snapshot ............ {final['Data_Extracao'].iloc[0]}")
    log(f"  Arquivo gerado .............. {ARQ_SAIDA}  (aba '{ABA_SAIDA}')")
    log("=" * 70)


if __name__ == "__main__":
    gerar()
