# Nexo

Plataforma de observabilidade e gestão de incidentes para sistemas empresariais,
com consulta de conhecimento anterior assistida por pesquisa semântica local.
Projeto académico de Engenharia Informática · Hugo Sousa · 2026/27.

## Funcionalidades

- Inventário de serviços, dependências, monitorização HTTP e integração empresarial por API.
- Deteção de falhas, regras de alerta, escalonamento e objetivos de disponibilidade e latência.
- Incidentes com responsável, investigação, evidências, resolução e post-mortem.
- Proteção contra gravações desatualizadas entre operadores, com comparação da versão atual.
- Pesquisa TF-IDF, BM25, semântica e híbrida, com origem e registo do conhecimento aplicado.
- Ações de prevenção com responsável, prazo e decisão final.
- Dossiers JSON, Markdown e HTML para impressão ou gravação em PDF pelo navegador.
- Perfis Administração, Operações e Leitura, auditoria e notificações dentro do portal.
- Cópias cifradas, restauro isolado, manutenção e ensaios de instalações independentes.

## Executar com Docker Desktop

1. Iniciar o Docker Desktop e aguardar que o motor esteja disponível.
2. Executar `iniciar-laboratorio.cmd`, na raiz deste repositório.
3. Abrir [Nexo](http://127.0.0.1:8001) e [Aurora](http://127.0.0.1:8002).

O primeiro build requer Internet para obter imagens e o modelo semântico. A Aurora
é uma empresa fictícia usada para demonstrar falhas e recuperação em serviços reais
de laboratório. As contas abaixo são exclusivas deste ambiente de demonstração:

- `admin@local.test` — Administração.
- `operacoes@local.test` — Operações.
- `leitor@local.test` — Leitura.

Palavra-passe inicial das três contas: `EstudoLocal2026!`. Alterar a configuração
inicial depois da criação da base não modifica palavras-passe já guardadas.
Não expor estas contas na Internet.

Para parar os serviços, usar o botão Stop do grupo `nexo-lab` no Docker Desktop.
Os dados ficam no volume Docker; não eliminar o volume para parar a aplicação.
Consultar [o guia do laboratório](docs/laboratorio.md) para configuração e diagnóstico.

## Desenvolvimento local

Requer Python 3.12 ou superior; o ambiente de CI usa Python 3.14. Executar
`iniciar.cmd` para preparar o ambiente virtual e abrir a aplicação na porta 8000.
Esta instância usa uma base diferente da stack Docker da porta 8001.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

O programa lê variáveis do processo; não carrega `.env` automaticamente. Em modo
sem demonstração, usar uma base vazia e seguir as instruções de
[instalação isolada](docs/instalacoes-isoladas.md) e [pré-produção HTTPS](docs/preproducao-https.md).
As chaves, bases de dados, backups e resultados de ensaios locais ficam fora do Git.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --test tests/frontend/navigation.test.cjs
```

O [GitHub Actions](https://github.com/hmsousa10/Projeto-Final/actions) executa a
bateria Python, compatibilidade das dependências e verificações JavaScript.
Os testes usam bases temporárias. Os ensaios de Docker, recuperação Windows/DPAPI,
HTTPS e falhas reais têm scripts próprios; ver [CONTRIBUTING.md](CONTRIBUTING.md).
Resultados gerados por máquina, capturas e relatórios de execuções são mantidos
localmente. Os protocolos, scripts de avaliação e testes continuam versionados.

## Organização

- `app/` — API FastAPI, persistência SQLite, autenticação e regras de domínio.
- `web/` — interface HTML, CSS e JavaScript.
- `tests/` — testes automatizados de integração e interface.
- `observability/` e `semantic/` — configuração de telemetria e pesquisa local.
- `deployment/` e `compose*.yaml` — ambientes Docker e HTTPS.
- `scripts/` — validação, instalação e operações de recuperação.
- `evaluation/` — protocolos e avaliação da pesquisa de conhecimento.
- `docs/` — guias funcionais, arquitetura e procedimentos de operação.

## Documentação e alcance

Consultar o [índice dos guias](docs/README.md), a [arquitetura](docs/arquitetura.md)
e o [roteiro de demonstração](docs/ciclo-real.md).

A versão atual é a **0.36**. O sistema continua em desenvolvimento e validação.
Cada empresa é ensaiada numa instalação independente; não existe isolamento de
equipas dentro da mesma instalação. A integração com uma empresa real exige
validar o contrato da API, as credenciais, a rede e a operação dessa empresa.

A pesquisa sugere casos anteriores e não executa correções automaticamente.
A avaliação com participantes, notificações externas e revisão independente de
segurança continuam pendentes. O laboratório local não constitui uma certificação
de segurança nem uma implantação comercial pronta a publicar.
