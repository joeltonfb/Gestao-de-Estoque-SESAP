# -*- coding: utf-8 -*-
"""
================================================================================
 CONFIGURAÇÃO CENTRAL — caminhos e credenciais
================================================================================
Tudo que muda de máquina para máquina mora aqui. Nenhum outro script tem caminho
absoluto ou senha escrita no código, então a mesma pasta funciona no PC do
usuário, num Windows Server ou num Linux sem alterações.

Ordem de prioridade das credenciais (a primeira que existir vence):
  1. Variáveis de ambiente  (SIPAC_USUARIO / SIPAC_SENHA)
  2. Arquivo config.ini     (seção [sipac])

As variáveis de ambiente vêm primeiro porque é assim que cofres de senha e
agendadores corporativos costumam injetar segredos — sem deixar rastro em disco.
================================================================================
"""

import configparser
import os

# ---- Raiz do projeto: a pasta onde este arquivo está ------------------------
RAIZ = os.path.dirname(os.path.abspath(__file__))

PASTA_DADOS = os.path.join(RAIZ, "dados")    # entradas fixas (catálogo mestre)
PASTA_SAIDA = os.path.join(RAIZ, "saida")    # planilhas geradas a cada execução

for _p in (PASTA_DADOS, PASTA_SAIDA):
    os.makedirs(_p, exist_ok=True)

# ---- Arquivos --------------------------------------------------------------
ARQ_MATRIZ    = os.path.join(PASTA_SAIDA, "relatorio_inventario_CONSOLIDADO_MATRIZ.xlsx")
ARQ_ESTOQUE   = os.path.join(PASTA_SAIDA, "BASE_ESTOQUE.xlsx")
ARQ_CATALOGO  = os.path.join(PASTA_DADOS, "BASE_DADOS_COMPLETA.xlsx")
ARQ_NOMES     = os.path.join(RAIZ, "nomes_almoxarifados.json")
ARQ_DATA_JS   = os.path.join(RAIZ, "sesap-data.js")
ARQ_HTML      = os.path.join(RAIZ, "index.html")

ABA_CATALOGO  = "Materiais"
ABA_ESTOQUE   = "Estoque"
ABA_MATRIZ    = "Inventario_Consolidado"

# ---- Leitura do config.ini -------------------------------------------------
_ARQ_CONFIG = os.path.join(RAIZ, "config.ini")
_cfg = configparser.ConfigParser()
if os.path.exists(_ARQ_CONFIG):
    _cfg.read(_ARQ_CONFIG, encoding="utf-8")


def _opcao(secao, chave, padrao=""):
    try:
        return _cfg.get(secao, chave).strip()
    except (configparser.NoSectionError, configparser.NoOptionError):
        return padrao


def _booleano(secao, chave, padrao=False):
    valor = _opcao(secao, chave, "").lower()
    if valor in ("true", "sim", "1", "yes"):
        return True
    if valor in ("false", "nao", "não", "0", "no"):
        return False
    return padrao


# ---- Credenciais do SIPAC --------------------------------------------------
SIPAC_USUARIO = os.environ.get("SIPAC_USUARIO") or _opcao("sipac", "usuario")
SIPAC_SENHA   = os.environ.get("SIPAC_SENHA")   or _opcao("sipac", "senha")

URL_SIPAC_LOGIN     = "https://sipac.rn.gov.br/sipac/?modo=classico"
URL_SIPAC_PRINCIPAL = "https://sipac.rn.gov.br/sipac/portal/principal.jsf"

# ---- Comportamento ---------------------------------------------------------
# headless=true é obrigatório em servidor sem interface gráfica (Server Core / Linux)
HEADLESS  = _booleano("navegador", "headless", padrao=False)
PUBLICAR  = _booleano("execucao", "publicar", padrao=True)


def validar_credenciais():
    """Falha cedo e com mensagem clara se o login não foi configurado."""
    if not SIPAC_USUARIO or not SIPAC_SENHA:
        raise SystemExit(
            "\n[ERRO] Credenciais do SIPAC não configuradas.\n"
            "       Opção 1 — copie config.ini.exemplo para config.ini e preencha [sipac].\n"
            "       Opção 2 — defina as variáveis de ambiente SIPAC_USUARIO e SIPAC_SENHA.\n"
        )


def resumo():
    """Linha de diagnóstico útil no log do agendador."""
    return (
        f"raiz={RAIZ} | headless={HEADLESS} | publicar={PUBLICAR} | "
        f"usuario={'definido' if SIPAC_USUARIO else 'AUSENTE'}"
    )
