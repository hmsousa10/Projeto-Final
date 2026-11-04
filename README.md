# Nexo

Plataforma Web de Observabilidade e Operações Assistidas por IA para Sistemas Empresariais.

Projeto I de Engenharia Informática · Hugo Sousa · a22405716 · 2026/27.

Esta é a **versão 0.32 local**: inventário, gestão de incidentes, pesquisa semântica local, cópias cifradas e restauro isolado, com um laboratório Docker que inclui um portal empresarial fictício, sondagens HTTP reais, logs Loki, incidentes automáticos e evidências preservadas. Os serviços de laboratório estão identificados; os exemplos anteriores continuam sintéticos. O portal completo ainda está em desenvolvimento.

**Prioridade atual:** implementar e validar o portal por etapas, procurando chegar a uma versão completa em cerca de um mês, com prazo ajustável aos resultados. A documentação de Projeto I continua em paralelo; a entrega preliminar mantém-se em 9 de novembro de 2026.

## Laboratório Docker · recomendado

Com o Docker Desktop iniciado, executar **iniciar-laboratorio.cmd**. Abrir **http://127.0.0.1:8001** e usar a conta de demonstração abaixo. A porta 8000 mantém o protótipo anterior; o laboratório tem dados independentes.

O portal mostra o estado de recolha, um alvo HTTP rápido e outro com atraso deliberado de 800 ms. As medições são reais; os alvos são de teste. Consultar [arranque, arquitetura e validação](docs/laboratorio.md).

O [roteiro do ciclo real](docs/ciclo-real.md) explica como provocar uma falha na Aurora, detetá-la, tratar o incidente, preservar logs e reutilizar o conhecimento.

A página [Monitorização](http://127.0.0.1:8001/#monitoring) já permite ligar serviços a endereços autorizados e pausar/retomar a recolha. Consultar [o guia das ligações](docs/monitorizacao.md).

Já estão disponíveis a [gestão de utilizadores](http://127.0.0.1:8001/#users), a alteração de palavra-passe em **Minha conta** e a edição de serviços, com auditoria. Consultar [Contas e inventário](docs/contas-inventario.md).

As [Regras de alerta](http://127.0.0.1:8001/#alert-rules) já são configuráveis por serviço, com versões e escalonamento único por falta de reconhecimento. Consultar [regras e prazos](docs/regras-alerta.md).

A página [Objetivos e SLOs](http://127.0.0.1:8001/#slo) já apresenta avaliações por janela, cobertura real, limites para dados desconhecidos, orçamento de erro e objetivos versionados. Consultar [definições e validação](docs/slis-slos.md).

A [Base de conhecimento](http://127.0.0.1:8001/#knowledge) permite comparar TF-IDF, BM25, embeddings locais e pesquisa híbrida, com filtros, origem, excertos e fallback explícito. Consultar [o método, a avaliação e as limitações](docs/conhecimento.md). O primeiro build descarrega cerca de 127 MB de modelo/tokenizador; a inferência funciona sem acesso externo no contentor interno.

Para guardar o histórico, executar **copia-seguranca.cmd**. A cópia é cifrada e verificada, fica fora do OneDrive e permite restauro numa pasta nova. Consultar [instruções, ensaio e limitações da recuperação](docs/copias-restauro.md), incluindo a dependência da chave DPAPI e a exclusão dos volumes completos Prometheus/Loki.

A v0.10 acrescenta limites de leitura/CPU/concorrência, proteção dos access logs, otimização dos painéis e um ensaio isolado de carga e segurança. Consultar [correções, resultados e limitações](docs/seguranca-carga.md). Para repetir, executar `validar-seguranca-carga.ps1`.

A v0.11 permite exportar a chave num kit protegido por frase-passe e restaurar sem o DPAPI original. Executar `exportar-chave-portatil.cmd` depois de criar uma cópia atual. Consultar [recuperação portátil, instruções e ensaios](docs/recuperacao-portatil.md).

A v0.12 acrescenta um ensaio operacional isolado e repetível: três falhas HTTP reais, incidentes automáticos, evidências Loki, consulta híbrida do caso anterior e fecho com histórico. Executar `validar-ciclo-operacional.ps1`. Consultar [protocolo, tempos e limites](docs/ensaio-operacional.md). Os passos de tratamento são executados por script; não medem MTTA/MTTR humano.

A v0.13 acrescenta promoção local de uma cópia recuperada, verificação do histórico, bloqueio temporário de alterações, retoma explícita e reversão com ponto guardado. Consultar [procedimento de manutenção e ensaio isolado](docs/manutencao.md). Começar por `manutencao.ps1 -Acao Estado`; executar `validar-manutencao.ps1` para ensaiar numa instalação separada.

A v0.14 acrescenta a [central de Notificações](http://127.0.0.1:8001/#notifications), com avisos operacionais, prazos ultrapassados e leitura por conta. Consultar [funcionamento e validação](docs/notificacoes.md). Os avisos são entregues dentro do portal; não existe envio externo nesta versão.

Próximos blocos: avaliação com participantes, notificações externas e revisão independente. As conclusões dos testes devem acompanhar cada bloco antes de declarar a aplicação concluída.

## Começar no Windows

Requisito: Python 3.12 ou superior, com o comando `py` disponível e acesso à Internet na primeira instalação. Foi validado neste computador com Python 3.14.3.

1. Abre a pasta `Projeto` que contém este README.
2. Faz duplo clique em **iniciar.cmd**. O script cria um ambiente virtual local e instala as dependências.
3. Mantém a janela aberta e visita **http://127.0.0.1:8000**.
4. Entra com `admin@local.test` e a palavra-passe `EstudoLocal2026!`.
5. Abre **Guia do projeto** na barra lateral ou segue [o roteiro de demonstração](docs/roteiro.md).

Para parar, usa `Ctrl+C` na janela do servidor. Para voltar a abrir, executa novamente `iniciar.cmd`. Se a porta 8000 estiver ocupada, verifica se já existe uma instância aberta. Não inicies duas instâncias sobre a mesma base de dados.

Durante o desenvolvimento foi deixada uma pré-visualização local em segundo plano. Se ainda estiver ativa, `iniciar.cmd` reconhece-a. Para parar especificamente essa pré-visualização, faz duplo clique em `parar-preview.cmd`; o script verifica o processo registado antes de o parar. Depois podes usar o arranque normal com janela visível.

Também podes iniciar pelo terminal, sem ativar o ambiente virtual:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --limit-concurrency 32 --backlog 64 --timeout-keep-alive 5
```

## Contas de demonstração

As três contas usam inicialmente `EstudoLocal2026!`:

- `admin@local.test`: cria serviços, gere incidentes e consulta a auditoria.
- `operacoes@local.test`: consulta serviços, gere incidentes e executa cenários.
- `leitor@local.test`: consulta serviços, incidentes e conhecimento; não altera dados.

As palavras-passe são guardadas com PBKDF2-HMAC-SHA256 e salt. A sessão usa um cookie HttpOnly e SameSite Strict, expira após oito horas e tem apenas o hash do token guardado na base de dados. Esta configuração destina-se a uma demonstração local. Não publiques as contas de exemplo nem exponhas o servidor na rede.

## O que já funciona

- Inventário: criar serviços, definir equipa, criticidade, SLO de disponibilidade/latência e dependências; consultar serviços dependentes.
- Dashboard: estado da última observação, histórico de latência, percentagem de sondagens com sucesso e indicadores calculados a partir dos incidentes.
- Incidentes: registo P1–P4, atribuição, reconhecimento, investigação, resolução, fecho, notas e post-mortem.
- Histórico e auditoria: persistência em SQLite; eventos com autor e data; auditoria acessível ao administrador.
- Conhecimento: TF-IDF, BM25, embeddings multilíngues locais e fusão RRF; incidente de origem, resolução, runbook e excertos comparados. Avaliação separada em `evaluation/`. Não existe modelo generativo nem execução automática de sugestões.
- Laboratório: simular indisponibilidade, latência elevada e recuperação; agrupar alertas repetidos por serviço.
- Autenticação e três perfis com permissões verificadas no servidor.

## O que ainda falta para o MVP

Adaptação a APIs de empresas reais, integração geral de logs, notificações externas e escalas operacionais, avaliação dos objetivos com dados de uma organização real, normalização de equipas e permissões por equipa e validação experimental documentada. ChatOps e deteção de anomalias ficam para fases posteriores. Os embeddings locais já estão implementados. Consulta [o estado dos requisitos e o plano](docs/plano.md).

## Interpretar os indicadores

As observações iniciais e os três incidentes históricos são **sintéticos**. No primeiro arranque são criadas 24 amostras por serviço, espaçadas cinco minutos, cobrindo aproximadamente duas horas; o dashboard filtra as amostras das últimas 24 horas. O simulador sintético acrescenta amostras apenas quando é acionado. O laboratório Docker recolhe sondagens reais periodicamente e apresenta-as como origem distinta. Não há ligação a uma empresa real.

Os exemplos sintéticos ficam «Sem dados recentes» após 15 minutos sem observações; as sondagens Prometheus, após 45 segundos. A percentagem mostrada é `sondagens bem-sucedidas / sondagens totais`; não é disponibilidade temporal nem evidência de cumprimento de SLA. A avaliação por janela, a cobertura e o orçamento de erros estão em Objetivos e SLOs; a percentagem simplificada do inventário não substitui essa avaliação.

MTTA é a média entre registo e reconhecimento. MTTR é a média entre registo e resolução. Apenas entram em cada média os incidentes que têm o respetivo timestamp; o dashboard mostra a quantidade usada. O histórico sintético entra nas médias. Estes números não provam melhoria: a comparação controlada com e sem plataforma ainda tem de ser feita.

## Dados e configuração

Por omissão, a base de dados é `data/nexo.db`. Os ficheiros dessa pasta estão ignorados pelo Git. Os dados sobrevivem ao reinício e o seed só é executado numa base sem utilizadores. Mudar `DEMO_PASSWORD` depois do primeiro arranque não altera contas já existentes.

Variáveis opcionais:

- `DATABASE_PATH`: caminho para outra base de dados SQLite.
- `DEMO_MODE=1`: valor inicial; cria os exemplos e ativa o simulador.
- `DEMO_PASSWORD`: palavra-passe inicial das contas de demonstração.
- `DEMO_MODE=0`: não cria exemplos e desativa o simulador. Usa **outra base de dados vazia**; mudar o modo não apaga exemplos de uma base já existente.
- `INITIAL_ADMIN_EMAIL` e `INITIAL_ADMIN_PASSWORD`: conta inicial em modo sem demonstração; palavra-passe de 12 a 200 caracteres localmente e 15 a 200 em produção, com rejeição da lista local de palavras-passe comuns/demonstração.
- `COOKIE_SECURE=1`: para uso posterior atrás de HTTPS. Não ativar na demonstração HTTP local.

O programa lê variáveis do processo; não carrega `.env` automaticamente. Exemplo para um ambiente limpo:

O modo sem demonstração recusa agora bases que tenham sido inicializadas como demo, sem apagar os dados existentes. `ALLOWED_HOSTS` aceita nomes explícitos e permite apenas `127.0.0.1,localhost` por omissão. `APP_ENV=production` recusa demonstração, exige `APP_ORIGIN` HTTPS num host permitido, força cookies Secure e recusa pedidos HTTP de aplicação. Esse perfil não configura certificados nem reverse proxy e não torna a aplicação pronta para publicação.

```powershell
$env:DEMO_MODE = '0'
$env:DATABASE_PATH = 'data/limpo.db'
$env:INITIAL_ADMIN_PASSWORD = 'EscolheUmaPalavraPasseLocal'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --limit-concurrency 32 --backlog 64 --timeout-keep-alive 5
```

Para cópias consistentes e cifradas da stack Docker, usa `copia-seguranca.cmd` e segue [cópias e restauro](docs/copias-restauro.md). Não copies apenas o ficheiro SQLite de um servidor em execução: podem existir alterações no WAL. Para experimentar sem perder trabalho, usa um novo `DATABASE_PATH`.

## Testes

O [GitHub Actions](https://github.com/hmsousa10/Projeto-Final/actions) executa a suite Python, `pip check` e a verificação de sintaxe JavaScript. Consultar o [guia de desenvolvimento](CONTRIBUTING.md#testes-automáticos-no-github) para âmbito e limitações.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes usam bases temporárias. Cobrem o percurso completo do incidente, validações, permissões, sessões, origem de pedidos, pesquisa, persistência, estado de observações antigas e alertas concorrentes. A primeira validação passou os 12 testes. A dependência Starlette emitiu um aviso de depreciação sobre o cliente de testes httpx, sem falhas nos testes.

Após revisão de segurança foram acrescentados testes de regressão para Host, isolamento de dados demo, rate limit persistente por conta/IP sem reposição por outra conta, HTTPS/cookies em perfil de produção e limite de corpo de 64 KiB, incluindo chunks sem Content-Length. O controlo de tentativas não é uma garantia contra DoS e o perfil de produção ainda precisa de validação de deployment independente.

Validação de 24/10/2026: **141 testes aprovados**, com um aviso de depreciação do cliente de testes httpx/Starlette. O laboratório Docker foi construído e executado, incluindo o ciclo real de falha e recuperação. Foram executados controlos HTTP e consultados avisos OSV para os pacotes Python das imagens; não foram executados testes de penetração completos, auditoria integral ASVS ou análise integral do sistema operativo das imagens.

`requirements-lock.txt` regista todas as versões do ambiente validado, incluindo ferramentas de teste. Para reproduzir esse ambiente, instala esse ficheiro em vez dos requisitos mínimos.

## Docker

Existe um `Dockerfile` e um `compose.yaml` para a aplicação e um volume de dados:

```powershell
docker compose up --build
```

O `compose.yaml` simples publica apenas a aplicação em `127.0.0.1:8000`. Para a stack completa validada, usar `iniciar-laboratorio.cmd`: prepara a chave de controlo local e arranca `compose.observability.yaml` com sete contentores. Nexo em `127.0.0.1:8001`, Aurora em `127.0.0.1:8002`; os componentes de telemetria não publicam portas. Consultar [o ciclo real](docs/ciclo-real.md).

## Manutenção e documentação

Consulta o [índice da documentação](docs/README.md) e o [guia de desenvolvimento](CONTRIBUTING.md). Os relatórios de validação são evidências datadas; os resultados históricos não representam automaticamente a versão atual.

## Estrutura

```text
app/                 API, base de dados, permissões, seed e pesquisa
web/                 Interface HTML, CSS e JavaScript, sem build
tests/               Testes de integração e recuperação
docs/plano.md        Requisitos, prioridades e próximas entregas
docs/arquitetura.md   Decisões e modelo de dados
docs/roteiro.md       Percurso de demonstração e estudo
data/                Base de dados local, fora do Git
```

A documentação interativa da API está em `/docs` e o estado do servidor em `/api/health`. A proteção dos dados é aplicada nas rotas da API; consultar o esquema da API não concede acesso aos dados.

As apresentações e o enunciado originais permanecem fora desta aplicação, sem alterações.

A v0.15 permite guardar o [dossier de cada incidente](docs/dossier-incidentes.md) em Markdown ou JSON, com linha temporal e evidências preservadas.

A v0.16 regista [conhecimento aplicado](docs/conhecimento-aplicado.md): associa um caso resolvido à investigação, preservando a justificação e o conteúdo consultado no histórico e no dossier.

A v0.17 acrescenta [auditoria pesquisável](docs/auditoria.md), com filtros, datas UTC e paginação estável para consultar eventos anteriores aos últimos 200.

A v0.18 local acrescenta [logs diretamente ligados ao serviço](docs/logs-diretos.md), incluindo o endpoint de pedidos da Aurora, com origem e filtro preservados nas evidências.

A v0.19 local melhora a [navegação assíncrona](docs/navegacao-assincrona.md): carregamento explícito e proteção contra respostas antigas ao mudar de página ou incidente.

A v0.20 local acrescenta [pesquisa e filtros do histórico de incidentes](docs/consulta-incidentes.md), com paginação e consulta por número.

A v0.21 local limita o [contexto de incidentes enviado aos painéis](docs/contexto-incidentes.md), preservando consulta e associação de casos antigos.

A v0.22 local apresenta [impacto potencial pelas dependências do inventário](docs/impacto-potencial.md) nos serviços e incidentes, distinguindo relações potenciais de estados observados.

A v0.23 local permite [preservar avaliações de impacto no incidente](docs/impacto-preservado.md), com cálculo no servidor, autor, data e inclusão no dossier.

A v0.24 local acrescenta a [integração empresarial por API](docs/integracao-empresarial.md): a Aurora serve um resumo autenticado dos seus pedidos e o Nexo apresenta-o numa área própria. Os dados empresariais continuam fictícios; a integração HTTP é real.

A v0.25 local liga a [API empresarial à deteção automática de incidentes](docs/alertas-api-empresarial.md), com regras versionadas, pausa/retoma e recuperação confirmada.

## Conectores empresariais · 0.26 local

A validação do contrato empresarial foi separada do transporte HTTP, com seleção por `ENTERPRISE_CONNECTOR` e proteção do histórico contra trocas de empresa, API ou conector. A Aurora mantém o contrato `orders-summary-v1`. Consultar [Conectores empresariais](docs/conectores-empresariais.md) para configuração, compatibilidade e limites.

## Instalações por cliente · 0.27 local

Existe um ensaio local independente, com base, redes e segredos próprios, sem contas predefinidas de demonstração. Executa `iniciar-cliente-ensaio.cmd` para preparar e iniciar a Atlas em `http://localhost:8003`. A palavra-passe inicial é gerada num ficheiro privado em `data/installations/atlas/initial-admin.key`; não é mostrada pelo script. Consultar [Instalações isoladas](docs/instalacoes-isoladas.md) para arranque, paragem, limites e validação.

## Cópias por instalação · 0.28 local

O atalho `copia-cliente-ensaio.cmd` cria uma cópia cifrada e verificada da Atlas. Cada instalação tem pastas e chave DPAPI próprias; o arquivo valida a identidade empresarial e o restauro cria uma base separada, sem sessões e com monitorização pausada. O kit portátil aceita também `-Instancia atlas`. Consultar [Cópias por instalação](docs/copias-por-instalacao.md).

## Manutenção por instalação · 0.29 local

`manutencao.ps1 -Instancia atlas` prepara, promove, verifica e reverte uma base da instalação selecionada, com diário e ponto de retorno próprios. A identidade é verificada na base, na cópia e no diário. Consultar [Manutenção por instalação](docs/manutencao-por-instalacao.md) para efeitos nas sessões, monitorização e recuperação de falhas.

## Pré-produção HTTPS · 0.30 local

`iniciar-preproducao.cmd` cria um terceiro ambiente isolado, em modo de produção e com entrada HTTPS apenas em loopback. O ensaio verifica o certificado com a CA local exportada, sem alterar a confiança do Windows. Consultar [Pré-produção HTTPS](docs/preproducao-https.md) para validação, limitações do navegador e futura adaptação a um domínio público.

## API empresarial HTTPS · 0.31 local

A pré-produção liga agora a uma API fictícia da Aurora também por HTTPS, com CA própria configurada apenas no cliente empresarial, validação do nome e chave de leitura. O serviço é acompanhado pelo coletor automático. Executa `scripts/validar-api-https.py` para repetir a verificação e consulta [API empresarial HTTPS](docs/api-empresarial-https.md).

## Ensaio operacional HTTPS

`scripts/https_cycle.py` executa dois ciclos de falha e recuperação apenas na API fictícia da pré-produção. Confirma deteção automática, recusa de resolução prematura, fecho, pesquisa de conhecimento anterior e dossiers exportados. Cada execução conserva os incidentes identificados de ensaio. Consultar [Ciclo operacional HTTPS](docs/ciclo-operacional-https.md).

## Entrega consolidada

Consultar [Entrega consolidada 0.31](docs/entrega-consolidada-031.md) para o âmbito publicado, validação disponível e separação entre código e dados locais.

## Colaboração entre operadores · v0.32

A atribuição e as transições de incidentes comparam a versão aberta no formulário
com a versão atual, dentro da mesma transação de escrita. Se outro operador ou a
recolha automática tiver alterado o caso, o portal recusa a gravação e preserva
o texto do formulário para consulta e revisão.

Consultar [funcionamento, compatibilidade e demonstração](docs/concorrencia-incidentes.md).
