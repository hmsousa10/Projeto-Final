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

Antes de publicar código, revê os ficheiros a incluir, sobretudo relatórios e capturas que possam conter nomes internos. Os commits devem separar mudanças compreensíveis e indicar a validação realizada. O repositório privado do projeto é https://github.com/hmsousa10/Projeto-Final. O primeiro commit reúne o estado existente; as alterações seguintes devem usar commits focados. Não está configurado um pipeline CI nesta entrega; testes locais não equivalem a revisão independente.

## Dívida técnica conhecida

O ficheiro principal da API e o JavaScript da interface ainda concentram várias responsabilidades. A modularização será incremental, preservando contratos HTTP e comportamento. Falta uniformizar a formatação do código, configurar análise estática e automatizar verificações em CI. Não confundir organização académica funcional com prontidão para produção.

## Fluxo Git

A branch principal é `main`. Para novas alterações, usa uma branch `codex/nome-da-alteracao`, executa os testes relevantes, revê `git diff` e cria um commit com uma mensagem concreta. Envia a branch e abre um pull request para revisão antes de integrar em main. A privacidade do repositório não dispensa a exclusão de segredos. As cópias cifradas dos dados são mantidas separadamente do código.
