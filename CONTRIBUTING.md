# Desenvolvimento e manutenção

## Responsabilidades

`app/main.py` compõe a aplicação, os controlos HTTP e as rotas ainda não extraídas. Funções de domínio vivem em módulos próprios: alertas, SLOs, recuperação, pesquisa e conhecimento aplicado. Novas funcionalidades devem seguir os módulos existentes, evitando ampliar desnecessariamente o ficheiro principal.

`app/models.py` define entradas e limites; `app/db.py` define persistência e migrações aditivas; `web/` contém a interface sem compilação; `tests/` contém testes isolados; `evaluation/` contém protocolos e ensaios experimentais; `observability/` e `semantic/` contêm integrações. Os scripts na raiz são pontos de entrada locais usados pelo aluno. `scripts/` reúne auxiliares. Os ficheiros de dados e segredos ficam fora do Git.

## Antes de alterar

Lê o README e o guia da funcionalidade em docs. Usa uma base temporária para testes. Não provoques falhas nem insiras dados de teste no laboratório principal quando o objetivo é apenas testar código. Mantém nomes e limites da API compatíveis ou documenta a alteração.

## Validação

Com o ambiente virtual preparado:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Para uma alteração localizada, executa primeiro os testes do módulo e das integrações afetadas. Por exemplo:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_use.py tests/test_dossier.py tests/test_workflow.py -q
```

Alterações em sessões, middleware, esquema de dados ou restauro exigem os testes correspondentes. Mudanças no esquema também exigem rever a validação estrita de backups e os fingerprints de recuperação. Alterações na interface exigem verificação no navegador e, quando Node está instalado, `node --check web/app.js`.

Regista o comando, resultado, data e limitações da validação. Nunca substituas um ensaio falhado por outro ficheiro com o mesmo nome para esconder o resultado anterior. Ensaios de carga, recuperação e falhas reais usam as stacks isoladas documentadas em docs.

## Base de dados

Mantemos SQLite e transações explícitas para operações compostas. A stack principal usa o volume Docker nexo-lab_nexo-data. Os testes usam bases temporárias. Não apagar volumes ou substituir a base ativa durante refatorações. A decisão de migrar para PostgreSQL deve resultar de necessidades medidas de concorrência ou implantação distribuída.

## Segurança e entrega

Valida permissões no servidor, não apenas na interface. Usa parâmetros SQL, limita entradas e escapa texto na apresentação. Não incluir bases de dados, ficheiros .env, chaves, palavras-passe reais nem cópias de segurança no controlo de versões. Os ficheiros ignorados ainda podem existir no disco e no OneDrive; o .gitignore não é uma cópia de segurança nem uma proteção do sistema de ficheiros.

Antes de publicar código, revê os ficheiros a incluir, sobretudo relatórios e capturas que possam conter nomes internos. Os commits devem separar mudanças compreensíveis e indicar a validação realizada. O repositório privado do projeto é https://github.com/hmsousa10/Projeto-Final. O primeiro commit reúne o estado existente; as alterações seguintes devem usar commits focados. O GitHub Actions executa os testes Python e verifica a sintaxe JavaScript em Linux. Resultados automáticos não equivalem a revisão independente.

## Dívida técnica conhecida

O ficheiro principal da API e o JavaScript da interface ainda concentram várias responsabilidades. A modularização será incremental, preservando contratos HTTP e comportamento. Falta uniformizar a formatação do código e configurar análise estática. Não confundir organização académica funcional com prontidão para produção.

## Fluxo Git

A branch principal é `main`. Para novas alterações, usa uma branch `codex/nome-da-alteracao`, executa os testes relevantes, revê `git diff` e cria um commit com uma mensagem concreta. Envia a branch e abre um pull request para revisão antes de integrar em main. A privacidade do repositório não dispensa a exclusão de segredos. As cópias cifradas dos dados são mantidas separadamente do código.

## Testes automáticos no GitHub

O workflow `.github/workflows/ci.yml` corre em pushes para `main`, em pull requests para `main` e por pedido manual no separador Actions. Usa Python 3.14, dependências fixadas em requirements-lock.txt e Node 24 para verificar a sintaxe dos dois ficheiros JavaScript. `pip check` valida compatibilidade das dependências e pytest executa a suite completa em bases temporárias.

A execução usa um runner Linux temporário, com timeout de 15 minutos, token de leitura e ações fixadas por SHA. Não recebe segredos do laboratório. A palavra-passe de demonstração é pública e usada apenas nas bases descartáveis dos testes. Execuções anteriores do mesmo evento/branch são canceladas quando chega uma atualização. Branches de trabalho são verificadas através do respetivo pull request, evitando duplicar a execução no mesmo push.

Consulta o separador Actions do GitHub ou os checks do pull request para ver o resultado e os logs. Este workflow não valida o arranque completo da stack Docker, o modelo semântico real nem os scripts Windows/DPAPI; esses ensaios mantêm os procedimentos isolados documentados. A criação deste check não ativa, por si só, uma regra de proteção de main.
