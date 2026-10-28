# Contexto dos painéis · v0.21 local

O carregamento comum da interface deixa de pedir `/api/incidents`, que devolve o histórico completo. Usa `/api/incidents/context`, autenticado para os três perfis, com uma transação de leitura por resposta e campos próprios de cada utilização.

- **Visão geral:** até cinco incidentes ativos, ordenados por prioridade e depois por data decrescente, com identificador como desempate. Os indicadores totais continuam a vir de `/api/summary`, não desta lista limitada.
- **Laboratório:** até dois incidentes automáticos ativos, um para cada alvo interno portal-lab/api-lab. A seleção é independente da fila de cinco, para um caso do laboratório não desaparecer por existirem outros mais prioritários. Casos de ligações personalizadas continuam em Incidentes e Monitorização.
- **Referências:** os 100 casos resolvidos/fechados com maior identificador. Só são enviados id, título, estado e origem. `references_more` indica se há casos anteriores, sem transferir a lista completa.

As listas não incluem descrição, resolução, runbook, linha temporal nem dados de autenticação. O detalhe de um caso continua disponível na rota autenticada própria. A página Incidentes mantém a consulta paginada de v0.20. A rota antiga permanece compatível, mas a interface deixa de a usar no arranque e nas atualizações periódicas.

## Conhecimento aplicado e casos antigos

No formulário **Conhecimento aplicado**, o campo **Número do caso de referência** aceita o identificador numérico, por exemplo `8`. A lista de sugestões apresenta números e títulos recentes; pode indicar-se um número anterior que não esteja nessa lista. A indicação não consulta nem aplica automaticamente o caso. O utilizador deve consultar o caso em Incidentes e justificar o que aproveitou antes de registar a associação.

O servidor continua a verificar existência, estado resolvido/fechado, diferença em relação ao caso atual, ausência de associação duplicada, limite de referências, autorização para escrita e estado do destino. O conteúdo usado é preservado na linha temporal. A validação da interface recusa números inválidos ou que ultrapassem os inteiros representáveis com exatidão em JavaScript; a API mantém o contrato de inteiros SQLite.

## Validação e limites

Os testes do contexto verificam autenticação nos três perfis, limites, campos enviados, ausência de alterações nos casos e a manutenção de um caso de laboratório fora dos cinco mais prioritários. Uma base temporária com 250 casos longos adicionais verifica que o JSON serializado do contexto ocupa menos de um décimo da lista anterior nesse conjunto. Esta comparação mede bytes serializados no teste, não latência nem ganho universal de desempenho.

Também é testada a associação de uma referência anterior às 100 sugestões. Os testes Node executam o código real da interface com DOM mínimo, confirmando a nova rota e a recusa de identificadores inválidos antes de os enviar. Os ensaios com escrita são feitos apenas em bases temporárias.

O limite reduz os registos e campos transferidos para estes componentes. Não demonstra escalabilidade global: resumo, serviços e utilizadores mantêm as suas consultas existentes, e consultas filtradas ainda podem percorrer muitos registos. Não foram adicionados índices, migrações ou dependências nesta etapa.

Resultados e âmbito em `validacao-contexto-incidentes.json`. Entrega local, sem commit nem push.
