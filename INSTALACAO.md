# Instalação no servidor

Guia para colocar o robô de inventário rodando num servidor que fique
permanentemente ligado. Vale para Windows Server e Linux — as diferenças estão
sinalizadas.

---

## 1. Pré-requisitos

| Item | Observação |
|---|---|
| Python 3.10+ | `python --version` |
| Google Chrome | O driver é baixado automaticamente na primeira execução |
| Git | Só se este servidor for publicar o site |

Acesso de rede necessário:

- `https://sipac.rn.gov.br` — **obrigatório**, é a origem dos dados
- `https://pypi.org` e `https://dl.google.com` — instalação das bibliotecas e do driver
- `https://github.com` — só se este servidor publicar o site

> Já foi verificado que o SIPAC recusa conexões vindas de provedores de nuvem
> (Google Cloud, AWS). Um servidor dentro da rede da SESAP não deve ter esse
> problema, mas confirme com um teste antes de prosseguir:
>
> ```
> curl -v --max-time 15 https://sipac.rn.gov.br/sipac/?modo=classico
> ```
>
> Se ficar preso em "Trying..." até o timeout, o acesso está bloqueado e nada
> mais vai funcionar — resolva isso primeiro.

---

## 2. Baixar o programa

```bash
git clone https://github.com/joeltonfb/Gestao-de-Estoque-SESAP.git
cd Gestao-de-Estoque-SESAP
```

O catálogo mestre de materiais já vem junto (`dados/BASE_DADOS_COMPLETA.xlsx`),
então não é preciso copiar nada à mão.

---

## 3. Instalar as bibliotecas

```bash
pip install -r requirements.txt
```

Em Linux, se aparecer `externally-managed-environment`, use um ambiente isolado:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 4. Configurar as credenciais

Copie o modelo e preencha:

```bash
# Windows
copy config.ini.exemplo config.ini

# Linux
cp config.ini.exemplo config.ini
```

Edite o `config.ini`:

```ini
[sipac]
usuario = <login do SIPAC>
senha   = <senha>

[navegador]
headless = true      # true em servidor sem interface gráfica

[execucao]
publicar = true
```

O `config.ini` está no `.gitignore` — a senha nunca é enviada ao repositório.

**Alternativa mais segura:** em vez de gravar a senha no arquivo, defina as
variáveis de ambiente `SIPAC_USUARIO` e `SIPAC_SENHA`. Elas têm prioridade sobre
o `config.ini` e não deixam a senha em disco.

> **Recomendação:** use uma conta de serviço do SIPAC, não o CPF de uma pessoa.
> Assim as ações automatizadas não ficam registradas em nome de um servidor
> específico, e o robô não para de funcionar quando alguém troca de senha ou de
> lotação.

---

## 5. Testar

Comece sem publicar nada, para validar só o acesso e a extração:

```bash
python executar.py --sem-publicar
```

Deve terminar com `CONCLUÍDO`. Os arquivos gerados ficam em `saida/`.

Se este servidor também for publicar o site, teste o fluxo completo:

```bash
python executar.py
```

Na primeira publicação o Git vai pedir autenticação. Em servidor, o usual é
usar um **token de acesso pessoal** do GitHub ou uma **deploy key** SSH — evite
depender de login interativo, que não existe em execução agendada.

---

## 6. Agendar a execução diária

### Windows Server — Agendador de Tarefas

```
Programa:    C:\caminho\para\python.exe
Argumentos:  executar.py
Iniciar em:  C:\caminho\para\Gestao-de-Estoque-SESAP
```

Marque **"Executar estando o usuário conectado ou não"**. Com essa opção não há
sessão gráfica, então `headless = true` no `config.ini` é obrigatório.

### Linux — cron

```bash
crontab -e
```

```cron
# Todo dia às 06:00
0 6 * * * cd /opt/Gestao-de-Estoque-SESAP && /usr/bin/python3 executar.py >> /var/log/inventario-sesap.log 2>&1
```

---

## 7. Manutenção

**Unidade nova ou renumerada no SIPAC.** O SIPAC às vezes renumera unidades
(aconteceu com 4 delas em julho/2026). Quando isso ocorre, o painel perde o nome
"amigável" daquela unidade e o programa avisa no fim da execução com a linha
pronta para colar em `nomes_almoxarifados.json`. Vale conferir o log de vez em
quando.

**O site mostra dados antigos.** É o cache do GitHub Pages; propaga sozinho em
alguns minutos, ou force com Ctrl+F5.

**A execução falhou.** O `executar.py` termina com código de saída diferente de
zero, o que o agendador registra como falha. O log traz a mensagem completa.

---

## Estrutura das pastas

```
Gestao-de-Estoque-SESAP/
├── executar.py                 ← ponto de entrada (é este que o agendador chama)
├── config.py                   ← caminhos e leitura das credenciais
├── config.ini                  ← suas credenciais (não versionado)
├── config.ini.exemplo          ← modelo
├── robo_inventario.py          ← etapa 1: raspagem do SIPAC
├── gerar_base_estoque.py       ← etapa 2: matriz → base tratada
├── atualizar_dashboard.py      ← etapa 3: base → painel → publicação
├── nomes_almoxarifados.json    ← nomes amigáveis das unidades
├── index.html                  ← o painel publicado
├── sesap-data.js               ← dados do painel
├── dados/
│   └── BASE_DADOS_COMPLETA.xlsx  ← catálogo mestre de materiais
└── saida/                      ← planilhas geradas (não versionado)
```
