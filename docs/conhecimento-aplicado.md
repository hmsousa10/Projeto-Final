# Conhecimento aplicado · v0.16

No detalhe de um incidente ainda não fechado, a secção **Conhecimento aplicado** permite selecionar outro caso resolvido ou fechado e explicar como ajudou. Consulta primeiro o caso de referência e confirma a pertinência da solução. As sugestões da pesquisa continuam a ser recomendações; abrir uma sugestão não regista utilização nem executa comandos.

O registo contém o autor autenticado, data, identificador de referência, justificação e uma cópia do título, origem, estado, resolução, causa raiz, prevenção e runbook disponíveis nesse momento. O histórico apresenta essa cópia numa secção expansível. O dossier Markdown/JSON inclui o mesmo evento integral. Não demonstra, por si só, que houve melhoria de tempo de resolução: é uma declaração do operador.

## Regras

- Administradores e operações podem registar; leitores podem consultar e exportar.
- O incidente de destino não pode estar fechado. A referência tem de estar resolvida ou fechada e ser outro incidente.
- Uma referência só pode ser associada uma vez a cada incidente; para corrigir ou complementar a decisão, acrescenta uma nota de investigação. O registo original permanece no histórico.
- Máximo de 20 referências por incidente, com justificação de 10 a 2000 caracteres.
- Exemplos sintéticos são identificados na seleção e a sua origem fica preservada. Não devem ser apresentados como evidência operacional real.

## Implementação

`POST /api/incidents/{id}/knowledge-use` recebe `source_incident_id` e `reason`. Usa uma transação SQLite BEGIN IMMEDIATE para verificar estado, duplicados e limite, capturar o conteúdo e registar evento e auditoria atomicamente. Não altera a prioridade nem o estado de nenhum incidente.

O evento `Conhecimento aplicado` usa JSON com schema_version=1 na coluna note da linha temporal. Não foi alterado o esquema SQLite, mantendo compatibilidade com cópias, restauro e verificação histórica existentes. O dossier preserva o evento; não são incluídos dados de autenticação. A interface escapa o texto antes de o apresentar.

## Validação

Testes isolados verificam permissões, destino fechado, autorreferência, referência ainda ativa ou inexistente, identificadores inválidos, justificação, tentativa de forjar o autor, duplicados, auditoria, preservação após alterações no caso de origem e inclusão no dossier. Os ensaios não registam utilização fictícia no histórico do laboratório principal.

Resultado: 12 testes de conhecimento aplicado/exportação e 23 testes de ciclo de incidentes/segurança passaram (35 no total). Aviso existente de descontinuação Starlette/httpx. Não foi repetida a suite completa nesta etapa. Verificação do laboratório v0.16: 9 incidentes e 60 eventos preservados, escrita pelo leitor recusada com 403 e formulário confirmado no navegador. Evidência em validacao-conhecimento-aplicado.json.
