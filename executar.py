# -*- coding: utf-8 -*-
"""
================================================================================
 EXECUTAR — fluxo completo, do SIPAC ao site publicado
================================================================================
Ponto de entrada único. É este arquivo que o agendador (Task Scheduler no Windows,
cron no Linux) deve chamar.

    SIPAC  ->  matriz  ->  base tratada  ->  painel  ->  GitHub Pages

Cada etapa roda no mesmo processo Python (não em subprocessos), então uma falha
em qualquer ponto interrompe o fluxo com mensagem clara e código de saída != 0 —
que é o que o agendador usa para saber que a execução falhou.

Uso:
    python executar.py                 # fluxo completo
    python executar.py --sem-publicar   # não envia ao GitHub (útil para teste)
    python executar.py --so-painel      # pula a raspagem, reaproveita a base atual
================================================================================
"""

import sys
import traceback
from datetime import datetime

# Saída sem buffer: sob agendador (Task Scheduler / cron) o stdout vai para arquivo,
# e o Python só descarregaria o texto no fim — se a execução travasse, o log ficaria
# vazio justamente quando é mais necessário. Também força UTF-8, senão acentos
# quebram no console do Windows (cp1252).
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
except AttributeError:
    pass  # Python < 3.7

import config


def cabecalho(titulo):
    print()
    print("=" * 70)
    print(f" {titulo}")
    print("=" * 70)


def main():
    inicio = datetime.now()
    so_painel = "--so-painel" in sys.argv
    publicar = config.PUBLICAR and "--sem-publicar" not in sys.argv

    cabecalho(f"INVENTÁRIO SESAP — início {inicio.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f" {config.resumo()}")

    try:
        # ---- 1. Raspagem do SIPAC ------------------------------------------
        if so_painel:
            print("\n[1/3] Raspagem PULADA (--so-painel): reaproveitando a matriz existente.")
            if not __import__("os").path.exists(config.ARQ_MATRIZ):
                raise SystemExit(
                    f"[ERRO] --so-painel exige uma matriz já existente, e não há nenhuma em:\n"
                    f"       {config.ARQ_MATRIZ}"
                )
        else:
            cabecalho("[1/3] RASPANDO O SIPAC")
            import robo_inventario
            robo_inventario.executar()

        # ---- 2. Base tratada -----------------------------------------------
        cabecalho("[2/3] GERANDO A BASE DE ESTOQUE")
        import gerar_base_estoque
        gerar_base_estoque.gerar()

        # ---- 3. Painel + publicação ----------------------------------------
        cabecalho("[3/3] ATUALIZANDO O PAINEL")
        import atualizar_dashboard
        js, sem_nome = atualizar_dashboard.gerar_data_js()
        atualizar_dashboard.injetar_no_html(js)

        if sem_nome:
            print()
            print("!" * 70)
            print(f" {len(sem_nome)} ALMOXARIFADO(S) SEM NOME AMIGÁVEL DEFINIDO")
            print("!" * 70)
            print(f" Edite nomes_almoxarifados.json para dar um nome melhor a estes:")
            for codigo, bruto, derivado in sem_nome:
                print(f'   "{codigo}": {{"nome": "{derivado}", "tipo": "G"}}   <- veio de: {bruto}')
            print("!" * 70)

        if publicar:
            atualizar_dashboard.publicar_no_github()
        else:
            print("\n[!] Publicação desativada nesta execução.")

    except SystemExit:
        raise
    except Exception:
        cabecalho("FALHA NA EXECUÇÃO")
        traceback.print_exc()
        sys.exit(1)

    duracao = datetime.now() - inicio
    cabecalho(f"CONCLUÍDO em {int(duracao.total_seconds() // 60)}min {int(duracao.total_seconds() % 60)}s")


if __name__ == "__main__":
    main()
