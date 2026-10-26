# Regras de alerta e prazos · versão 0.6

A página **Regras de alerta** permite configurar a deteção por serviço. As regras atuam sobre sondagens HTTP reais, não sobre o simulador sintético. Só administradores podem gravar alterações e consultar versões anteriores; os restantes perfis autenticados podem consultar a configuração atual e o estado do motor.

## Configurar uma regra

Abrir http://127.0.0.1:8001/#alert-rules e escolher **Configurar regra** no serviço pretendido.

- Ativar ou suspender a criação de alertas do serviço.
- Ativar separadamente indisponibilidade e latência elevada.
- Exigir entre duas e cinco sondagens distintas para confirmar a falha e, separadamente, a recuperação.
- Definir um limite de latência entre 1 e 120 000 ms; deixar vazio para herdar o SLO do inventário.
- Escolher P1/P2 para indisponibilidade e P2/P3/P4 para latência.
- Ativar escalonamento por falta de reconhecimento e definir um prazo entre 15 e 86 400 segundos.

A regra base mantém duas sondagens de confirmação e duas de recuperação, P1 para indisponibilidade, P2 para latência e limite herdado do SLO. **O escalonamento por prazo está desligado por omissão**, preservando o comportamento dos incidentes anteriores.

As sondagens precisam de ser posteriores à última alteração da regra e à última ativação/alteração relevante da ligação. A amostra mais recente não pode ter mais de 45 segundos; as amostras consecutivas não podem ter intervalos superiores a 25 segundos. A confirmação com mais amostras usa uma sequência mais longa, sem contar repetidamente a mesma observação.

## Limite de alerta e objetivo do serviço

O limite da regra determina a abertura e a recuperação do alerta. O SLO do inventário continua a determinar o estado técnico mostrado no dashboard. Um serviço pode, por exemplo, estar acima do SLO de 500 ms e abaixo de um limite de alerta de 1 000 ms. Isso não comprova cumprimento do SLO.

As prioridades dos incidentes existentes nunca descem automaticamente. Uma nova condição técnica confirmada pode elevar a prioridade segundo a regra, mantendo o mesmo caso ativo. Suspender alertas não recupera o serviço nem fecha casos; a resolução exige as sondagens recentes de recuperação previstas pela configuração atual.

## Escalonamento por falta de reconhecimento

O motor verifica os prazos a cada cinco segundos, independentemente da recolha do Prometheus. Aplica-se a incidentes:

- De origem `prometheus-alert`.
- Ainda abertos e sem reconhecimento.
- Associados a um alvo ativo e autorizado.
- Com alertas e escalonamento por prazo ativados.

O prazo conta desde o instante mais recente entre criação do caso, alteração da regra e alteração relevante da ligação — incluindo retoma da recolha ou alteração do SLO de latência. Não se acumulam retroativamente minutos de uma regra anterior ou de uma pausa. Uma gravação sem alterações não cria versão nem reinicia o prazo.

Ao ultrapassar o prazo, o caso sobe para **P1**. Se já era P1, regista-se a ultrapassagem sem alegar mudança de prioridade. O registo é único por incidente e persiste após reinícios; concorrência entre verificações não cria escalonamentos repetidos.

Reconhecer o incidente impede este escalonamento. Atribuir um responsável, por si só, não equivale a reconhecer. A recuperação técnica também não reconhece nem fecha automaticamente o caso. Um alvo pausado, retirado da lista autorizada ou com alertas suspensos fica excluído da verificação.

O motor tem um sinal periódico de atividade. A interface mostra «Ativo» quando a última verificação ocorreu há, no máximo, vinte segundos, e «Sem sinal recente» quando o sinal envelhece. Uma interrupção no Prometheus não interrompe este motor; uma indisponibilidade da própria aplicação ou base de dados pode atrasar a execução. Não existe garantia de execução no segundo exato do prazo.

**Não são enviadas notificações externas.** Este escalonamento altera a prioridade e regista a ocorrência no Nexo. Encaminhamento por email/ChatOps, políticas de prevenção e escalas de pessoas de serviço continuam pendentes.

## Versões e histórico do caso

Cada alteração efetiva guarda uma versão, data, autor e configuração completa. O botão **Histórico** apresenta até cinquenta versões recentes; as versões mais antigas não são apagadas pelo endpoint.

Os novos incidentes automáticos guardam uma cópia da regra aplicada na deteção, incluindo limite efetivo de latência e chave do alvo. Os casos anteriores à versão 0.6 não recebem uma configuração histórica inventada. O escalonamento guarda a versão utilizada, prazo, instante e prioridades anterior/final.

Alterações a regras de serviços com casos ativos são assinaladas nas respetivas linhas temporais. Os incidentes fechados e o conhecimento anterior permanecem disponíveis. A base conserva o contexto de deteção mesmo que a regra atual seja diferente.

## Ensaio reproduzível

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/validar-regras.py
```

O ensaio usa o serviço de laboratório **Aurora · Consulta de pedidos**, sem alterar casos ativos anteriores. Configura três sondagens, latência acima de 500 ms, prioridade P3 e prazo de quinze segundos. Provoca latência real, confirma o P3, para o Prometheus e verifica que o motor independente eleva o caso para P1 uma única vez. Depois repõe o Prometheus, recupera o serviço, trata e fecha o caso e restaura a regra anterior.

Validação em 24/10/2026: **80 testes automáticos passaram**, com um aviso de depreciação Starlette/httpx. O ensaio real terminou às 21:01:34 UTC: **INC-009**, regra v1, P3 → P1 após ultrapassagem do prazo de quinze segundos; caso fechado e configuração anterior reposta como v2. Evidência: [validacao-regras.json](validacao-regras.json).

Na interface foi guardada a regra v1 do **Exemplo · Ligação HTTP pausada**, com três sondagens para confirmar e recuperar, prioridade P3 para latência e prazo configurado de sessenta segundos, **com escalonamento desligado**. A ligação permanece pausada. O histórico mostra a versão e o autor da gravação.

Após reiniciar a aplicação, o INC-009 permaneceu fechado, com um único evento de escalonamento, o motor voltou a apresentar atividade recente e os três alvos ativos voltaram a ter amostras recentes. Interface verificada: [regras por serviço](regras-v06.png) e [histórico do caso escalonado](incidente-escalonado-v06.png).

O motor é local, no processo da aplicação, e usa SQLite para coordenar as escritas. As verificações de concorrência e reinício não constituem validação de deployment distribuído ou alta disponibilidade. Os indicadores globais de MTTA/MTTR continuam a misturar exemplos sintéticos e ensaios locais; a avaliação experimental e as janelas formais de SLO são trabalho seguinte.
