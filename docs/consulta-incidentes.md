# Consulta de incidentes · v0.20 local

A página **Incidentes** passa a consultar a API com filtros, em páginas de até 50 casos. Os três perfis podem consultar; as permissões para alterar incidentes permanecem no servidor.

## Utilização

1. Escolher **Ativos**, **Resolvidos** (inclui fechados) ou **Todos**.
2. Introduzir o número, como `INC-010` ou `10`, ou texto do título, descrição, serviço ou responsável.
3. Combinar serviço, prioridade, estado específico, responsável, origem e dias de registo. **Por atribuir** corresponde a um responsável vazio.
4. Selecionar **Aplicar filtros**. Escolher um estado específico muda a vista para **Todos**, evitando que a vista Ativos esconda um caso fechado.
5. Abrir o incidente e fechar a janela para continuar com os mesmos critérios. Usar **Ver incidentes mais antigos** para avançar no histórico ou **Atualizar recentes** para regressar ao início, preservando os filtros.

Mudar de separador mantém os restantes filtros e remove o estado específico. **Limpar filtros** mostra Todos. Os filtros aplicados ficam em memória durante a sessão; não são preferências persistentes. A atualização periódica não substitui esta página enquanto se consulta o histórico.

O texto é pesquisado como sequência literal, sem distinguir maiúsculas/minúsculas Unicode. `%`, `_` e aspas não são operadores. Um número isolado ou a forma INC-número procura o identificador exato, respeitando os restantes filtros. Para procurar números na descrição, incluir contexto, por exemplo `HTTP 503`.

## Contrato da API

`GET /api/incidents/browse` requer sessão. Aceita `view=active|history|all`, `status`, `severity`, `service_id`, `assignee_id` (0 significa por atribuir), `scope=all|operational|examples`, `q` até 200 caracteres e `date_from`/`date_to` em formato ISO. Ambos os dias UTC de registo são incluídos. Scope examples seleciona origens demo; operational inclui laboratório e registos manuais e não prova origem numa empresa real.

`limit` tem valor inicial 50 e admite 1 a 100. A resposta inclui `items`, `snapshot_id`, `next_before_id`, `limit`, `date_timezone` e `order=id_desc`. As páginas seguintes devem reenviar os mesmos filtros e snapshot_id, com before_id igual ao cursor devolvido. Datas invertidas, enums desconhecidos, limites e identificadores inválidos devolvem 422.

Os casos são ordenados por identificador decrescente, independentemente da prioridade. A visão geral mantém a sua ordenação operacional anterior. O cursor exclui números criados depois do limite inicial e não usa offsets. Não constitui uma fotografia imutável dos casos: estados, atribuições e outros campos podem mudar entre consultas e alterar a pertença aos filtros. Uma consulta à API usa uma transação de leitura consistente para essa resposta.

A rota anterior `/api/incidents` continua a devolver a lista original para compatibilidade. O carregamento comum da aplicação ainda usa essa rota para os painéis e a escolha de conhecimento aplicado; este incremento limita a consulta da página de incidentes, mas não resolve por si só o custo global de um histórico muito grande. Essa separação fica como dívida técnica explícita nesta versão. A v0.21 local passa a usar resumos limitados nos painéis; consultar contexto-incidentes.md para o estado posterior.

## Validação e limites

Testes em bases temporárias verificam os três perfis, ausência de alterações nos casos, filtros combinados, texto literal, limites, identificadores numéricos longos, paginação além de 100 casos, novos registos e alterações de estado durante consultas. Os testes Node cobrem o envio dos critérios, escape do texto e pesquisas fora de ordem usando o ficheiro real da interface com DOM mínimo.

A consulta visual no laboratório não introduz falhas nem cria incidentes. Resultados específicos em `validacao-consulta-incidentes.json`; captura em `consulta-incidentes-v020.png`. As alterações estão locais e não foram enviadas para GitHub nesta etapa. O esquema SQLite e as dependências não mudaram.
