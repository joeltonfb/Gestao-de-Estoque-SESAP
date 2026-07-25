# -*- coding: utf-8 -*-
"""
================================================================================
 ATUALIZADOR DO DASHBOARD (BASE_ESTOQUE.xlsx -> HTML publicado)
================================================================================
Fecha a ponte entre o robô local e o site publicado:

  1. Lê BASE_ESTOQUE.xlsx (base long gerada por gerar_base_estoque.py)
  2. Gera sesap-data.js no formato compacto que o painel espera
  3. Injeta esse JS dentro do bundle do "Painel Estoques SESAP.html"
     (o HTML guarda cada asset em base64+gzip num <script type="__bundler/manifest">)
  4. Opcionalmente faz commit+push pro GitHub, publicando via GitHub Pages

Os nomes "bonitos" dos almoxarifados vivem em nomes_almoxarifados.json, indexados
pelo código da unidade. Código novo que apareça no SIPAC e não esteja lá recebe um
nome derivado automaticamente E é avisado no fim da execução, para você editar o
JSON depois se quiser um nome melhor.

Como usar:  python atualizar_dashboard.py [--push]
================================================================================
"""

import base64
import gzip
import io
import json
import os
import re
import subprocess
import sys

import pandas as pd

# ============================== CONFIG =========================================
PASTA        = os.path.dirname(os.path.abspath(__file__))
ARQ_ESTOQUE  = os.path.join(PASTA, "BASE_ESTOQUE.xlsx")
ARQ_NOMES    = os.path.join(PASTA, "nomes_almoxarifados.json")
ARQ_DATA_JS  = os.path.join(PASTA, "sesap-data.js")
ARQ_HTML     = os.path.join(PASTA, "index.html")  # index.html = URL limpa no GitHub Pages

ABA_ESTOQUE  = "Estoque"
# ===============================================================================

RE_SIGLA = re.compile(r"^ALMOXARIFADO\s*", re.IGNORECASE)


def log(msg=""):
    print(msg, flush=True)


def carregar_nomes():
    """Mapa codigo -> {nome, tipo}. Arquivo editável à mão."""
    if not os.path.exists(ARQ_NOMES):
        log(f"[AVISO] {os.path.basename(ARQ_NOMES)} não encontrado — todos os nomes serão derivados automaticamente.")
        return {}
    with io.open(ARQ_NOMES, encoding="utf-8") as f:
        return json.load(f)


def derivar_nome(nome_bruto):
    """Fallback para unidade nova: 'ALMOXARIFADO NUTRICIONAL DO X' -> 'Nutricional Do X'."""
    nome = RE_SIGLA.sub("", str(nome_bruto)).strip()
    nome = re.sub(r"\s+", " ", nome).strip(" -")
    return nome.title() if nome else str(nome_bruto)


def derivar_tipo(nome_bruto):
    return "N" if "NUTRICIONAL" in str(nome_bruto).upper() else "G"


def gerar_data_js():
    """BASE_ESTOQUE.xlsx -> string 'window.SESAP_DATA = {...};'"""
    if not os.path.exists(ARQ_ESTOQUE):
        log(f"[ERRO] Base de estoque não encontrada:\n       {ARQ_ESTOQUE}")
        sys.exit(1)

    df = pd.read_excel(ARQ_ESTOQUE, sheet_name=ABA_ESTOQUE, dtype=str)
    df["Quantidade"] = pd.to_numeric(df["Quantidade"], errors="coerce").fillna(0)
    df = df[df["Quantidade"] > 0].copy()
    log(f"[1] BASE_ESTOQUE lida: {len(df)} linhas com saldo")

    nomes = carregar_nomes()

    # ---- lista de almoxarifados (ordenada por código, como no painel original) --
    pares = df[["Almox_Codigo", "Almoxarifado"]].drop_duplicates().values.tolist()
    pares.sort(key=lambda p: str(p[0]))

    alms, idx_por_codigo, sem_nome = [], {}, []
    for codigo, nome_bruto in pares:
        codigo = str(codigo).strip()
        info = nomes.get(codigo)
        if info:
            nome, tipo = info["nome"], info.get("tipo") or derivar_tipo(nome_bruto)
        else:
            nome, tipo = derivar_nome(nome_bruto), derivar_tipo(nome_bruto)
            sem_nome.append((codigo, nome_bruto, nome))
        idx_por_codigo[codigo] = len(alms)
        alms.append({"n": nome, "c": codigo, "t": tipo})
    log(f"[2] Almoxarifados: {len(alms)}")

    # ---- dicionário de grupos ----------------------------------------------
    grupos = {}
    for cod, den in df[["GrupoCodigo", "GrupoDenominacao"]].drop_duplicates().values.tolist():
        cod = str(cod).strip()
        if cod and cod.lower() != "nan":
            grupos[cod] = str(den).strip()
    grupos = dict(sorted(grupos.items()))
    log(f"[3] Grupos: {len(grupos)}")

    # ---- itens: 1 por material, com q = {indice_almox: quantidade} ----------
    itens = []
    for codigo_mat, bloco in df.groupby("Codigo", sort=False):
        primeira = bloco.iloc[0]
        q = {}
        for _, linha in bloco.iterrows():
            i = idx_por_codigo.get(str(linha["Almox_Codigo"]).strip())
            if i is None:
                continue
            qtd = float(linha["Quantidade"])
            q[str(i)] = int(qtd) if qtd == int(qtd) else round(qtd, 3)
        if not q:
            continue
        itens.append({
            "cd": str(codigo_mat).strip(),
            "nm": str(primeira["Denominacao"]).strip(),
            "un": str(primeira["UnidadeMedida"]).strip(),
            "g":  str(primeira["GrupoCodigo"]).strip(),
            "q":  q,
        })
    itens.sort(key=lambda it: (it["g"], it["nm"]))
    log(f"[4] Materiais: {len(itens)}")

    payload = {"alms": alms, "grupos": grupos, "items": itens}
    js = "window.SESAP_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";"

    with io.open(ARQ_DATA_JS, "w", encoding="utf-8") as f:
        f.write(js)
    log(f"[5] sesap-data.js gravado ({len(js):,} caracteres)".replace(",", "."))

    return js, sem_nome


def injetar_no_html(js):
    """Substitui o asset de dados dentro do bundle base64+gzip do HTML."""
    if not os.path.exists(ARQ_HTML):
        log(f"[ERRO] HTML do painel não encontrado:\n       {ARQ_HTML}")
        sys.exit(1)

    with io.open(ARQ_HTML, encoding="utf-8") as f:
        html = f.read()

    m = re.search(r'(<script type="__bundler/manifest">)(.*?)(</script>)', html, re.S)
    if not m:
        log("[ERRO] Não encontrei o <script type=\"__bundler/manifest\"> no HTML.")
        log("       O painel pode ter sido exportado em outro formato.")
        sys.exit(1)

    manifest = json.loads(m.group(2))

    # localiza o asset que contém os dados (procura pela marca SESAP_DATA)
    uuid_dados = None
    for uuid, entry in manifest.items():
        try:
            bruto = base64.b64decode(entry["data"])
            if entry.get("compressed"):
                bruto = gzip.decompress(bruto)
        except Exception:
            continue
        if b"SESAP_DATA" in bruto:
            uuid_dados = uuid
            break

    if uuid_dados is None:
        log("[ERRO] Não achei o asset com window.SESAP_DATA dentro do bundle.")
        sys.exit(1)

    entrada = manifest[uuid_dados]
    bytes_js = js.encode("utf-8")
    if entrada.get("compressed"):
        # mtime=0 mantém o gzip determinístico (evita diff no git quando os dados não mudam)
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
            gz.write(bytes_js)
        bytes_js = buf.getvalue()

    entrada["data"] = base64.b64encode(bytes_js).decode("ascii")

    novo_manifest = json.dumps(manifest, ensure_ascii=False, separators=(",", ": "))
    html = html[: m.start(2)] + novo_manifest + html[m.end(2):]

    with io.open(ARQ_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    log(f"[6] HTML atualizado: asset {uuid_dados} substituído")


def publicar_no_github():
    """git add/commit/push. Só roda se a pasta já for um repositório configurado."""
    if not os.path.isdir(os.path.join(PASTA, ".git")):
        log("\n[AVISO] Esta pasta ainda não é um repositório git — pulei a publicação.")
        log("        Rode sem --push, ou configure o repositório primeiro.")
        return

    def git(*args):
        return subprocess.run(["git", "-C", PASTA, *args], capture_output=True, text=True)

    git("add", "-A")
    st = git("status", "--porcelain")
    if not st.stdout.strip():
        log("\n[7] Nada mudou desde a última publicação — nenhum commit criado.")
        return

    data_snapshot = pd.read_excel(ARQ_ESTOQUE, sheet_name=ABA_ESTOQUE, dtype=str)["Data_Extracao"].iloc[0]
    c = git("commit", "-m", f"Atualiza estoque - snapshot {data_snapshot}")
    if c.returncode != 0:
        log(f"\n[ERRO] Falha no commit:\n{c.stdout}\n{c.stderr}")
        return

    p = git("push")
    if p.returncode != 0:
        log(f"\n[ERRO] Falha no push:\n{p.stdout}\n{p.stderr}")
        log("       Verifique se o remote e a autenticação do GitHub estão configurados.")
        return

    log("\n[7] Publicado no GitHub! O site atualiza em ~1 minuto.")


def main():
    log("=" * 70)
    log(" ATUALIZANDO DASHBOARD")
    log("=" * 70)

    js, sem_nome = gerar_data_js()
    injetar_no_html(js)

    if sem_nome:
        log("")
        log("!" * 70)
        log(f" {len(sem_nome)} ALMOXARIFADO(S) SEM NOME AMIGÁVEL DEFINIDO")
        log("!" * 70)
        log(f" Edite {os.path.basename(ARQ_NOMES)} para dar um nome melhor a estes:")
        for codigo, bruto, derivado in sem_nome:
            log(f'   "{codigo}": {{"nome": "{derivado}", "tipo": "G"}}   <- veio de: {bruto}')
        log("!" * 70)

    if "--push" in sys.argv:
        publicar_no_github()
    else:
        log("\n[7] Publicação pulada (rode com --push para enviar ao GitHub).")

    log("=" * 70)
    log(" PRONTO")
    log("=" * 70)


if __name__ == "__main__":
    main()
