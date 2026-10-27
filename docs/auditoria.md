# Auditoria pesquisável · v0.17

A página Auditoria é exclusiva do administrador. Permite consultar o histórico em páginas de 50 eventos, filtrar por nome exato do utilizador, código exato da ação e identificador exato do registo, pesquisar texto e limitar por dias UTC.

Exemplo: entity `incident:9` reúne as ações auditadas sobre esse incidente. A pesquisa de texto abrange utilizador, ação, registo e detalhe; usa comparação Unicode sem distinguir maiúsculas/minúsculas. Os filtros de utilizador, ação e registo são exatos. O detalhe completo pode ser expandido e as referências a incidentes permitem abrir o caso.

## Histórico estável

A primeira página captura o maior identificador disponível. As páginas seguintes mantêm esse limite e usam um cursor por identificador, por isso novos eventos não deslocam os registos que estás a consultar. Atualizar recentes inicia uma nova consulta. A página não é substituída pelo temporizador de atualização do dashboard. Datas de filtro são inclusivas em UTC; os horários apresentados seguem o formato local do navegador.

## API e compatibilidade

`GET /api/audit/events` retorna items, snapshot_id, next_before_id, limit e date_timezone. Parâmetros: actor (100 caracteres), action (100), entity (200), q (200), date_from/date_to (AAAA-MM-DD), before_id, snapshot_id e limit (1 a 100). Intervalos de datas invertidos e limites inválidos são recusados com 422. Leitura usa uma transação SQLite e parâmetros SQL. A consulta não regista um novo evento nem altera eventos existentes.

A rota anterior `GET /api/audit` mantém a lista das últimas 200 ações para preservar compatibilidade. A interface utiliza a nova rota paginada, que permite alcançar eventos mais antigos. Não foram alterados o esquema SQLite nem os dados existentes.

## Limites

A auditoria regista as operações instrumentadas pela aplicação. Não é um registo inviolável ou uma auditoria externa; um administrador com acesso direto ao ficheiro pode alterar a base. Não existe nesta versão exportação geral da auditoria nem política de retenção automática. A pesquisa por texto e por dia pode percorrer o histórico, pelo que volumes empresariais maiores devem ser medidos antes de decidir índices ou outra base de dados.

## Testes

Testes isolados cobrem permissões, compatibilidade, mais de 200 eventos, cursores sem duplicados, inclusão de novos eventos apenas numa nova consulta, filtros exatos, pesquisa Unicode, caracteres SQL tratados como texto, dias UTC inclusivos, limites inválidos e ausência de escrita na consulta.
