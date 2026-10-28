# Alertas da API empresarial · v0.25 local

A integração autenticada de v0.24 passa a ter recolha automática, independente de manter a página aberta. Um serviço próprio, inicialmente **Aurora · API de operações**, representa a ligação. A criação do serviço é auditada e não cria, por si só, um incidente.

## Ciclo da ligação

Uma consulta é tentada a cada dez segundos. HTTP sem resposta utilizável, autenticação recusada, JSON fora do contrato e dados fora da janela de frescura são resultados de falha da integração. Uma resposta validada é um resultado com sucesso. A duração inclui a consulta e validação, não só a latência do servidor da empresa.

As observações usam origem enterprise-api. A resposta do adaptador pode ser reutilizada durante cinco segundos; o mesmo instante de consulta só é gravado uma vez. Um resultado busy não é convertido numa amostra de falha nem de sucesso. Lacunas superiores aos limites da regra não contam como confirmações consecutivas. Dados com mais de 45 segundos deixam de ser apresentados como recentes.

O serviço entra em **Regras de alerta**, reutilizando os limites e versões existentes. Por omissão são exigidas duas falhas e duas respostas válidas dentro do limite de latência, mas os números e prioridades podem ser configurados. A latência elevada também pode abrir um incidente. O escalonamento por falta de reconhecimento funciona se for ativado na regra; continua desligado por omissão.

Os incidentes têm origem enterprise-alert, distinta das sondagens Prometheus e dos exemplos sintéticos. O caso preserva a regra na deteção, a classificação do resultado da API e a linha temporal. Recorrências são agrupadas no caso ativo dessa ligação. Se o caso anterior estiver fechado, reativar regras durante uma nova falha não deve deixar esse caso antigo como referência ativa: é criado um caso novo após as confirmações exigidas. Uma condição mais grave pode elevar a prioridade, sem descida automática.

A recuperação é registada após as confirmações exigidas, mas não resolve nem fecha o caso automaticamente. O servidor impede a resolução antes da recuperação recente, tal como faz com as sondagens Prometheus. A equipa continua a atribuir, reconhecer, investigar, justificar a resolução e preencher o post-mortem. O dossier e a pesquisa de conhecimento mantêm a proveniência da API.

Uma falha da integração não prova indisponibilidade de toda a empresa. Por exemplo, uma chave recusada pode afetar o acesso do Nexo e deixar o portal comercial disponível. A descrição distingue a origem e a classificação da consulta. Os totais de pedidos continuam fictícios na Aurora e não são usados como regra de negócio nesta etapa.

## Pausa e restauro

O administrador pode pausar ou retomar a recolha em **Integração empresarial**. Os restantes perfis consultam o estado e os casos. Pausar não confirma recuperação e não fecha incidentes. A consulta manual do resumo continua disponível, mas não grava amostras enquanto a recolha automática estiver pausada.

A retoma, o reinício da aplicação e alterações ao limite de latência exigem amostras novas. Uma resposta iniciada antes de uma pausa/retoma é descartada se a configuração mudou entretanto. O modo sintético é bloqueado para o serviço gerido por este adaptador, e esse mesmo serviço não pode receber uma ligação Prometheus paralela pela API de configuração.

O restauro de uma cópia cifrada pausa também esta recolha. Reiniciar a aplicação não a reativa silenciosamente. Depois da verificação do restauro/manutenção, o administrador retoma explicitamente na área empresarial. A ação de manutenção já existente retoma os alvos Prometheus elegíveis; não substitui esta retoma da API.

O URL e a empresa esperada identificam o histórico desta ligação por uma impressão SHA-256, sem guardar o URL ou a chave nos metadados do coletor. Trocar a API/empresa numa base que já contém essa ligação é recusado; exige uma base separada ou migração explícita. Rotação da chave para a mesma API não mistura outros históricos. Nesta versão há uma ligação empresarial por instalação.

## Proteção e persistência

`PUT /api/enterprise/monitoring` recebe apenas `{"enabled": true}` ou false e exige Administrador. A recolha usa a chave de leitura e as políticas de transporte de v0.24; o navegador não pode fornecer URL, chave ou resultado de sondagem. Os metadados, observações e incidentes usam as tabelas existentes, sem alteração do esquema.

A gravação usa uma transação de escrita: verifica novamente a configuração, impede amostras repetidas e avalia as regras de forma serializada. O bloqueio de manutenção impede a recolha automática durante uma fase incompatível com escrita. A auditoria distingue criação do serviço, pausa e retoma. Não há envio de notificações para fora do portal nesta versão.

## Validação

Os testes verificam confirmação, deduplicação concorrente, respostas ocupadas, pausa durante uma consulta, recorrência, prioridades, prazo de reconhecimento, bloqueio de resolução prematura, exportação e pausa depois de restauro. Há um ensaio com servidor HTTP real isolado: respostas 503 abrem o caso; duas respostas JSON válidas confirmam recuperação; o caso é tratado, fechado e exportado. Os testes Node verificam os controlos por perfil, o acesso ao incidente durante falhas e a regra sem dependência de Prometheus.

No laboratório principal apenas se ativa a ligação saudável. O inventário passa a incluir o serviço da API; não são introduzidas falhas de teste nem fechados casos anteriores. Resultados em validacao-alertas-api.json e captura em alertas-api-v025.png. Alterações locais, sem commit/push.

## Validação académica sem empresa parceira

Não ter uma empresa parceira não impede construir e ensaiar o sistema. A Aurora pode suportar um caso de estudo controlado, com condições, dados, passos e resultados reproduzíveis. Essa validação técnica deve ser distinguida de avaliação com utilizadores e de evidência em ambiente empresarial real.

Nos requisitos preliminares locais, o parceiro ainda está por confirmar; isso não determina uma obrigação institucional. O âmbito e método de avaliação devem ser confirmados com o orientador. Não se devem apresentar entrevistas, testes com participantes ou ganhos de operação numa empresa como realizados sem essa evidência. A ausência de validação numa organização real deve ficar como limitação explícita.
