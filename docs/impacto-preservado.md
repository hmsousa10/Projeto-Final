# Avaliações de impacto preservadas · v0.23 local

A consulta expansível **Impacto potencial** continua a apresentar o inventário carregado pela interface. Nos incidentes que ainda não estão fechados, Operações e Administrador podem escolher **Guardar avaliação atual no caso**.

O servidor volta a consultar o inventário e a calcular os dependentes. Guarda o resultado na linha temporal, com o autor autenticado e a data. O resultado pode diferir da consulta anterior da interface se o inventário ou as observações tiverem mudado. Não se aceita do navegador um inventário, estado, autor ou instante fornecido pelo cliente.

## Conteúdo guardado

O evento **Impacto potencial preservado** contém um registo JSON de versão 1 com:

- Instante da avaliação e indicação de que foi calculada a partir do inventário desse momento.
- Serviço de origem: identificador, nome, equipa, criticidade, estado classificado, data e origem da última observação.
- Até 50 dependentes, com os mesmos campos, distância mínima e identificador do pré-requisito usado no caminho apresentado.
- Limite e indicadores de lista parcial, relações incompletas ou campos de texto limitados.

A interface mostra a cópia guardada dentro do evento, separada da consulta atual. Alterações posteriores nos serviços não substituem os nomes e estados dessa recolha. O dossier Markdown/JSON já inclui a linha temporal e, por isso, também inclui a avaliação. Não é necessário alterar o esquema SQLite.

O registo descreve impacto **potencial** no momento da recolha. Não prova que um dependente falhou, não estabelece causa raiz e não reconstrói o inventário no início do incidente. Uma recolha feita muito depois da falha mantém essa limitação. Os estados respeitam as regras de frescura e autorização das sondagens usadas pelo inventário.

## Permissões e limites

`POST /api/incidents/{iid}/impact` recebe `{}` e exige permissão de escrita. O perfil Leitura pode consultar recolhas existentes. Incidentes fechados devolvem 409; um caso inexistente devolve 404; campos não previstos no corpo devolvem 422.

Cada incidente admite até 20 recolhas, verificadas numa transação que também protege a verificação do estado do caso. Cada JSON é limitado a 64 KiB. Os campos textuais têm limites explícitos e sinalizam qualquer limitação aplicada. Apenas campos selecionados do inventário são guardados; não se copiam descrições, credenciais, endereços de ligação ou histórico completo de observações.

A recolha é auditada como `incident.impact.captured`. Não modifica prioridade, responsável, estado ou relações do inventário. Fechar a janela não cancela uma gravação já enviada, mas uma resposta atrasada não substitui a janela escolhida depois.

## Validação

Os testes em bases temporárias verificam permissões, rejeição de conteúdo imposto pelo cliente, cálculo no servidor, caminhos indiretos, estados observados, preservação após alterações no inventário, exportação e limite de recolhas sob concorrência. Um teste cria uma cópia cifrada e confirma que o restauro conserva exatamente o evento guardado. A suite de recuperação existente é executada com esse teste.

Os testes Node usam o ficheiro real da interface com DOM mínimo. Verificam a separação dos dados preservados, escape de texto, visibilidade do botão por perfil/estado e resposta atrasada após mudança de janela.

A verificação visual no laboratório principal consulta apenas o botão e os avisos. Não guarda avaliações de teste no histórico do utilizador.
