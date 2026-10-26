# Ensaio operacional repetível · versão 0.12

O ensaio verifica a cadeia completa entre uma falha HTTP real na empresa fictícia Aurora e um caso fechado, com logs preservados e conhecimento disponível para uma nova ocorrência. O tratamento é executado por um script, não por um participante humano.

## Repetir no Windows

Com Docker Desktop e o ambiente Python do projeto preparados, executar na pasta do projeto:

```powershell
powershell -ExecutionPolicy Bypass -File .\validar-ciclo-operacional.ps1
```

São iniciados sete contentores do projeto Docker **nexo-cycle**. Nexo e Aurora usam exclusivamente as portas locais **8011 e 8012**; o portal habitual continua em **8001 e 8002**. A base SQLite, o Prometheus e o Loki do ensaio usam memória temporária `tmpfs`. Não são montadas bases ou volumes de dados do portal habitual. Apenas configurações em leitura e os segredos de integração já existentes são montados; as redes dos projetos são distintas.

O script constrói as imagens locais, recusa substituir um ensaio já existente, aguarda o marcador da instalação e executa três repetições. No fim remove os seus contentores e redes, mesmo em caso de falha. Cada resultado fica num novo ficheiro `docs/validacao-operacional-DATA-HORA-ID.json`; resultados anteriores não são substituídos. A história completa dos três casos é exportada antes de o armazenamento temporário desaparecer. Se uma fase falhar, o resultado identifica a falha e contém as fases já observadas; não é marcado como aprovado.

O teste direto `python -m evaluation.cycle_test --output NOVO-FICHEIRO.json` só aceita os endereços fixos 8011/8012 e o marcador com base temporária e protocolo correspondente. Não existe opção para o apontar à instalação principal. Este marcador previne enganos operacionais; não é autenticação contra um utilizador que controle a máquina local.

## Protocolo definido antes da medição

O protocolo encontra-se em [cycle_protocol.json](../evaluation/cycle_protocol.json). O seu SHA-256 e os hashes do código servido são incluídos nos resultados. Não existem alterações a regras, introdução manual de observações ou criação manual dos incidentes do alvo durante o ensaio.

Cada repetição exige:

1. Provocar a falha e observar **HTTP 503** no endpoint real `/api/orders`.
2. Receber um novo incidente **P1 automático**, proveniente das sondagens Prometheus do endpoint de saúde.
3. Atribuir um responsável, reconhecer e iniciar investigação. Tentar resolver antes da recuperação tem de devolver **409**.
4. Consultar o Loki e guardar no incidente pelo menos um registo 503 posterior à injeção desta repetição. Logs de repetições anteriores não satisfazem este critério.
5. Consultar pesquisa **híbrida efetiva**, com o modelo local, âmbito operacional e filtro do serviço. O caso atual é excluído. Na primeira repetição não existe caso anterior deste serviço; nas duas seguintes o último caso fechado tem de aparecer nos primeiros cinco resultados **antes da recuperação**. Fallback textual não satisfaz este ensaio.
6. Manter a falha mais 12 segundos e verificar que sondagens repetidas não duplicam o caso ativo.
7. Remover explicitamente a falha, observar **HTTP 200** e aguardar a confirmação de recuperação por sondagens recentes.
8. Resolver e fechar com causa raiz, prevenção e runbook. O histórico tem de conter as transições e as evidências. Um comentário posterior ao fecho tem de ser recusado com **409**; o caso tem de ser pesquisável.

As falhas do laboratório mantêm o limite automático de dois minutos. A reposição do serviço é tentada em `finally`; o encerramento dos contentores isolados constitui a limpeza adicional. A API de teste com atraso de base pode manter um incidente separado, que não faz parte do alvo nem dos resultados deste protocolo.

## Significado dos tempos

Os intervalos usam o relógio monotónico do cliente. Cada evento também contém uma data UTC. O início da injeção e da recuperação é registado **antes** do pedido de controlo; o fim do pedido também é registado, pelo que a duração do comando está incluída no intervalo observado.

- **Deteção observada:** início da injeção até à primeira consulta que encontra o novo incidente automático.
- **Confirmação de recuperação observada:** início do comando de recuperação até à primeira consulta que encontra a recuperação recente na linha temporal.
- **Reconhecimento por script:** primeira observação do incidente até ao fim do pedido de reconhecimento. Não representa MTTA de uma pessoa.
- **Injeção até fecho por script:** inclui investigação automatizada, espera de indexação/pesquisa, pausa deliberada de 12 segundos, sondagens e pedidos de tratamento. Não representa MTTR humano ou duração exclusiva da indisponibilidade.

A consulta periódica ocorre a cada segundo e acrescenta até um intervalo de polling, além dos tempos de rede e escalonamento. As datas internas do incidente e da linha temporal também são preservadas, mas não são misturadas com o relógio monotónico para fabricar maior precisão. Os resumos apresentam mínimo, mediana e máximo de apenas três observações; não fornecem um intervalo de confiança nem uma garantia de serviço.

## Evidências e limites

Cada JSON contém protocolo, versão, hashes, identificador único da instalação, eventos UTC e intervalos, incidente completo, contexto da regra de deteção, linha temporal, snapshots de logs, resultados da consulta de conhecimento e testes negativos. O ficheiro adjacente `.json.ambiente.json` regista as imagens efetivas, limites de recursos, montagens, redes e portas, sem exportar valores dos segredos. O hash do caso ajuda a detetar alterações acidentais ao comparar ficheiros; não constitui uma assinatura ou prova inviolável.

Este é um ensaio de integração com falhas deliberadas numa empresa fictícia. Não demonstra ganhos de produtividade, redução de MTTR ou eficácia numa empresa real. A comparação com e sem a plataforma, usando participantes, tarefas equivalentes e ordem controlada, continua pendente. A qualidade geral da pesquisa é avaliada separadamente em [Conhecimento](conhecimento.md); encontrar os dois casos anteriores deste ensaio não substitui esse benchmark.

Os contentores estão quentes; o arranque fica fora das métricas. Os recursos físicos são partilhados com o portal habitual. Nexo tem limite de 1 CPU/256 MiB e o encoder 2 CPU/1 GiB. Três repetições idênticas não cobrem falhas de rede, perda do coletor, corrupção de armazenamento ou indisponibilidade da máquina. Segurança de produção, revisão independente e promoção controlada após restauro continuam a exigir trabalho próprio.

## Resultado observado

Execução concluída em **2026-10-25T23:50:22.298719+00:00**, com **3/3 repetições aprovadas** e pesquisa híbrida efetiva nas três. A deteção observada variou entre **19.63 e 29.87 segundos** (mediana 29.87); a confirmação de recuperação, entre **18.51 e 27.89 segundos** (mediana 27.84). São tempos técnicos deste laboratório, nas condições descritas acima.

Os casos temporários INC-005, INC-006 e INC-007 pertencem exclusivamente à instalação identificada no JSON; os seus números não identificam os casos com igual número no portal habitual. Os três ficaram fechados e os históricos completos foram exportados. A primeira consulta não devolveu casos anteriores do serviço; a segunda recuperou INC-005; a terceira recuperou INC-006 e INC-005.

Evidências: [resultado completo](validacao-operacional-20261025-234634-7f44fd94.json) e [ambiente Docker observado](validacao-operacional-20261025-234634-7f44fd94.json.ambiente.json). Os sete contentores e as duas redes temporárias foram removidos automaticamente no fim. A suite automática passou com **146 testes**, em 246,54 segundos, com um aviso de depreciação Starlette/httpx. As verificações de sintaxe Python, JavaScript e PowerShell também passaram.


Após a atualização do portal habitual para 0.12.0, foram confirmados os mesmos **9 incidentes e 60 entradas de histórico** observados antes do ensaio. Login de leitor e pesquisa híbrida continuaram funcionais; o marcador exclusivo do ensaio devolveu 404 no portal habitual. Ver [verificação do portal](validacao-operacional-portal.json).
