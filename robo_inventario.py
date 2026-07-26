# -*- coding: utf-8 -*-
"""
================================================================================
 ROBÔ DE INVENTÁRIO — SIPAC/RN  (v60, portável)
================================================================================
Acessa o SIPAC/RN, percorre todas as unidades de almoxarifado cadastradas, extrai
o relatório de inventário de cada uma e consolida os saldos numa matriz do Excel.

Diferenças da versão antiga (v51):
  - Sem caminho absoluto e sem senha no código: tudo vem de config.py
  - Modo headless configurável, para rodar em servidor sem interface gráfica
  - Grava a matriz em saida/, não na pasta de onde o script foi chamado

Rode por conta própria com:  python robo_inventario.py
Ou como parte do fluxo completo:  python executar.py
================================================================================
"""

import re
import time
from io import StringIO

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

import config


def limpar_valor_numerico(valor):
    """'R$ 1.234,50' -> 1234.5 ; vazio ou inválido -> 0.0 (não quebra os cálculos)."""
    try:
        texto = str(valor).strip()
        if "R$" in texto:
            texto = texto.replace("R$", "").strip()
        # vírgula como separador decimal (padrão brasileiro)
        if "," in texto and texto.find(",") > texto.find("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
        return float(texto)
    except (ValueError, TypeError):
        return 0.0


def montar_navegador():
    opcoes = ChromeOptions()
    if config.HEADLESS:
        opcoes.add_argument("--headless=new")
    # Necessárias em servidor/container Linux; inofensivas no Windows
    opcoes.add_argument("--no-sandbox")
    opcoes.add_argument("--disable-dev-shm-usage")
    opcoes.add_argument("--disable-gpu")
    opcoes.add_argument("--window-size=1920,1080")

    servico = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=servico, options=opcoes)


def executar():
    config.validar_credenciais()

    print(">>> ROBÔ DE INVENTÁRIO SIPAC/RN <<<")
    print(f"    {config.resumo()}")

    navegador = None
    try:
        print("Abrindo o navegador...")
        navegador = montar_navegador()
        wait = WebDriverWait(navegador, 60)

        # ---- login ---------------------------------------------------------
        print("Acessando a página de login...")
        navegador.get(config.URL_SIPAC_LOGIN)

        xpath_usuario = '//*[@id="conteudo"]/div[3]/form/table/tbody/tr[1]/td/input'
        xpath_senha   = '//*[@id="conteudo"]/div[3]/form/table/tbody/tr[2]/td/input'
        xpath_acessar = '//*[@id="conteudo"]/div[3]/form/table/tfoot/tr/td/input'

        wait.until(EC.presence_of_element_located((By.XPATH, xpath_usuario))).send_keys(config.SIPAC_USUARIO)
        wait.until(EC.presence_of_element_located((By.XPATH, xpath_senha))).send_keys(config.SIPAC_SENHA)
        navegador.find_element(By.XPATH, xpath_acessar).click()
        time.sleep(2)
        print("Login realizado.")

        def click_insistente(xpath, tentativas=3):
            """Contorna StaleElementReferenceException: a página JSF se redesenha
            entre a localização do elemento e o clique."""
            for _ in range(tentativas):
                try:
                    elemento = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                    navegador.execute_script(
                        "arguments[0].scrollIntoView({block: 'center', inline: 'center'});", elemento
                    )
                    time.sleep(0.5)
                    elemento.click()
                    return
                except StaleElementReferenceException:
                    print("  - Elemento 'velho' detectado. Tentando novamente...")
                    time.sleep(1)
            raise Exception(f"Erro ao clicar no elemento: {xpath}")

        # ---- descobre as unidades -----------------------------------------
        xpath_abrir_selecao   = '//*[@id="info-usuario"]/p[3]/a/img'
        xpath_caixa_selecao   = '//*[@id="conteudo"]/form/table/tbody/tr/td[2]/select'
        xpath_voltar_relatorio = '//*[@id="relatorio-rodape"]/p/table/tbody/tr/td[1]/a'

        print("Buscando unidades...")
        click_insistente(xpath_abrir_selecao)

        caixa = wait.until(EC.presence_of_element_located((By.XPATH, xpath_caixa_selecao)))
        nomes_das_unidades = [opcao.text for opcao in Select(caixa).options]
        print(f"Encontradas {len(nomes_das_unidades)} unidades.")

        dados_por_unidade = {}

        # ---- percorre cada unidade -----------------------------------------
        for i, unidade_atual in enumerate(nomes_das_unidades):
            # Subsecretarias agregam as unidades filhas e gerariam saldo duplicado
            if "SUBSECRETARIA" in unidade_atual.upper():
                print(f">>> IGNORANDO UNIDADE DUPLICADA: {unidade_atual} <<<")
                continue

            try:
                print("-" * 30)
                print(f"Processando: {unidade_atual}")

                caixa = wait.until(EC.presence_of_element_located((By.XPATH, xpath_caixa_selecao)))
                Select(caixa).select_by_index(i)
                navegador.find_element(
                    By.XPATH, '//*[@id="conteudo"]/form/table/tfoot/tr/td/input[2]'
                ).click()

                # Menu lateral: Módulos -> Almoxarifado -> Consultas -> Relatório de Inventário
                click_insistente('//*[@id="show-modulos-sipac"]')
                click_insistente('//*[@id="modulos"]/ul[1]/li[3]/a')
                click_insistente('//*[@id="elgen-14"]')
                click_insistente('//*[@id="relatorios-menualmoxarifado"]/ul/li[2]/ul/li[5]/a')
                click_insistente('//*[@id="conteudo"]/form/table[2]/tfoot/tr/td/input[1]')

                try:
                    # Espera curta: se a tabela não vier em 10s, a unidade está sem estoque
                    tabela = WebDriverWait(navegador, 10).until(
                        EC.presence_of_element_located(
                            (By.XPATH, "//table[.//th[contains(text(), 'Código')]]")
                        )
                    )
                    df_bruto = pd.read_html(StringIO(tabela.get_attribute("outerHTML")), header=0)[0]
                    df_bruto.dropna(subset=["Código"], inplace=True)

                    colunas = ["Código", "Denominação", "Unid. Medida", "Saldo", "Preço*", "Total"]
                    df_final = df_bruto[colunas].copy()
                    for coluna in ("Saldo", "Preço*", "Total"):
                        df_final[coluna] = df_final[coluna].apply(limpar_valor_numerico)

                except TimeoutException:
                    # Unidade sem material: entra zerada para não sumir da matriz
                    print("Relatório vazio. Criando zerado.")
                    df_final = pd.DataFrame({
                        "Código": [0], "Denominação": ["SEM MATERIAL"], "Unid. Medida": ["-"],
                        "Saldo": [0.0], "Preço*": [0.0], "Total": [0.0],
                    })

                dados_por_unidade[unidade_atual] = df_final

                click_insistente(xpath_voltar_relatorio)
                click_insistente(xpath_abrir_selecao)
                time.sleep(1)

            except Exception as erro_unidade:
                # Tolerância a falhas: volta ao portal e segue para a próxima unidade
                print(f"Erro na unidade: {erro_unidade}. Tentando recuperar...")
                try:
                    navegador.get(config.URL_SIPAC_PRINCIPAL)
                    time.sleep(3)
                    click_insistente(xpath_abrir_selecao)
                except Exception:
                    break  # nem a recuperação funcionou: para para não entrar em laço
                continue

        # ---- consolida em matriz ------------------------------------------
        if not dados_por_unidade:
            raise SystemExit("\n[ERRO] Nenhuma unidade foi extraída — nada a consolidar.")

        print("Consolidando dados...")
        tabelas = []
        for nome_unidade, df in dados_por_unidade.items():
            df["Unidade"] = re.sub(r"[\(\)]", "", nome_unidade).strip()
            tabelas.append(df)

        completo = pd.concat(tabelas, ignore_index=True)

        # Materiais nas linhas, unidades nas colunas; sem saldo = 0
        consolidado = completo.pivot_table(
            index=["Código", "Denominação", "Unid. Medida"],
            columns="Unidade",
            values="Saldo",
            fill_value=0,
        ).reset_index()
        consolidado.columns.name = None

        consolidado.to_excel(config.ARQ_MATRIZ, sheet_name=config.ABA_MATRIZ, index=False)
        print(f"\n>>> SUCESSO! Matriz salva em: {config.ARQ_MATRIZ} <<<")

    finally:
        if navegador:
            navegador.quit()


if __name__ == "__main__":
    executar()
