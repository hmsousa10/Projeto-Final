# Plano de implementação

**Atualização de 24/10/2026:** a prioridade acordada é implementar e validar o portal por etapas, usando cerca de um mês como meta flexível e mantendo a documentação académica em paralelo. A entrega preliminar mantém-se em 9 de novembro de 2026. A versão 0.3 já realiza o ciclo de falha HTTP real até ao conhecimento; consultar [o estado atual](ciclo-real.md). A descrição da entrega 1 abaixo é histórica.

**Estado da entrega 2:** portal fictício Aurora, sondagens Prometheus, logs Loki, incidentes automáticos P1/P2, escalonamento de P2 para P1 por indisponibilidade, recuperação confirmada e evidências persistentes implementados. A avaliação experimental e as notificações externas continuam pendentes; alvos, regras e escalonamento por prazo foram implementados nas versões seguintes. A versão 0.4 generaliza as ligações a endereços autorizados, com descoberta dinâmica, pausa e retoma; consultar [Monitorização](monitorizacao.md). A versão 0.5 acrescenta gestão de contas, desativação, troca obrigatória da palavra-passe inicial, revogação de sessões e edição do inventário com prevenção de ciclos; consultar [Contas e inventário](contas-inventario.md). A versão 0.6 acrescenta regras configuráveis, versões e escalonamento único por falta de reconhecimento; consultar [Regras de alerta](regras-alerta.md). A versão 0.7 acrescenta SLIs/SLOs por janela, cobertura explícita, objetivos versionados e orçamento de erro com dados desconhecidos; consultar [SLIs e SLOs](slis-slos.md). A versão 0.8 acrescenta embeddings locais, pesquisa híbrida, proveniência e avaliação reproduzível; consultar [Recuperação do conhecimento](conhecimento.md). A versão 0.9 acrescenta cópias cifradas, chave DPAPI e restauro isolado verificado; consultar [Cópias e restauro](copias-restauro.md). A versão 0.10 acrescenta reforço de segurança, consulta OSV, otimização e ensaio de carga; consultar [Segurança e carga](seguranca-carga.md). A versão 0.11 acrescenta kit de chave protegido por frase-passe e restauro Windows/Linux sem DPAPI no destino; consultar [Recuperação portátil](recuperacao-portatil.md). A versão 0.12 acrescenta cenários operacionais repetidos em ambiente isolado, com logs, pesquisa híbrida e tempos de tratamento por script; consultar [Ensaio operacional](ensaio-operacional.md). A versão 0.13 acrescenta promoção local, diário durável, verificação e reversão de uma base recuperada; consultar [Manutenção](manutencao.md). A versão 0.14 acrescenta notificações dentro do portal e cursores de leitura pessoais; consultar [Notificações](notificacoes.md). Próximo bloco: revisão independente, entrega externa de notificações e avaliação com participantes.

## Objetivo

Construir um portal local que permita perceber que serviço falhou, avaliar o impacto, atribuir um responsável, acompanhar a resolução e consultar o que funcionou em incidentes anteriores. O enunciado do professor define os requisitos académicos. As apresentações são a proposta inicial do aluno e não significam que as funcionalidades já estejam implementadas.

O nome Nexo é um nome de trabalho para a aplicação e pode ser alterado.

## Entrega 1 disponível

A versão 0.1 permite experimentar o percurso completo de um incidente com persistência e dados sintéticos. Esta entrega reduz a incerteza sobre o produto antes de integrar vários sistemas de telemetria.

- RF01 Inventário: criação, consulta, equipa responsável, criticidade, dependências e metas de disponibilidade/latência implementadas. Edição, eliminação e gestão de equipas ficam por implementar.
- RF02 Telemetria: apenas observações sintéticas persistentes e visualização. A recolha externa de métricas/logs ainda não está implementada.
- RF03 Alertas: P1 para indisponibilidade e P2 para latência acima do limite, apenas no simulador; alertas repetidos agrupados por serviço. P3/P4 podem ser escolhidos em incidentes manuais. Regras configuráveis e escalonamento ficam por implementar.
- RF04 Incidentes: registo, atribuição, reconhecimento, investigação, resolução e fecho implementados com linha temporal e post-mortem obrigatório no fecho. Reabertura fica por implementar.
- RF05 Apoio inteligente: TF-IDF, BM25, embeddings locais e recuperação híbrida implementados com origem, excertos e runbook. Avaliação quantitativa sintética separada registada; validação com dados representativos continua pendente.
- RF06 Segurança: sessões locais, administrador/operações/leitor, verificação de permissões na API e auditoria implementados. Gestão de contas e recuperação de acesso ficam por implementar.
- RF07 Entregáveis: código, README, guia de demonstração, esquema de dados e configuração inicial Docker disponíveis. Validação Docker, guia da stack final, relatório experimental e anexos finais ficam pendentes.

## Entrega 2 · âmbito e pendências

Integrar um serviço de teste instrumentado com Prometheus e um agregador de logs como Loki. Fixar a arquitetura final e a janela dos SLOs antes de escolher a configuração. Não é necessário implementar Prometheus e OpenTelemetry como alternativas concorrentes: escolher os componentes pelo papel que desempenham.

Critério de conclusão: provocar uma falha real no serviço de teste e observar a sequência completa, sem introduzir amostras manualmente: recolha, dashboard, alerta com evidências, incidente e recuperação do serviço.

Trabalho previsto:

1. Criar uma aplicação empresarial de teste com endpoint de saúde, métricas e falhas controladas.
2. Recolher métricas periodicamente e registos pesquisáveis.
3. Acrescentar configurações de ligação e mapear séries/registos para serviços do inventário.
4. Definir SLIs e janelas, por exemplo proporção de pedidos bem-sucedidos e latência p95.
5. Persistir regras e condições de abertura/recuperação para evitar alertas instáveis.
6. Implementar escalonamento por prioridade e prazo, registando cada escalonamento.
7. Validar o Docker Compose com todos os serviços e volume de dados.

## Entrega 3

Implementação inicial concluída na v0.8; consultar conhecimento.md e ../evaluation/results-v0.8.json. Resultados e limitações estão registados, sem ajuste posterior ao teste. Uma avaliação maior e independente fica pendente.

Melhorar a recuperação do histórico. Criar um conjunto de incidentes de teste, consultas e relevâncias esperadas. Separar os casos usados para preparar os dados dos casos de avaliação. Medir Precision@k, Recall@k ou MRR para o baseline TF-IDF e comparar com embeddings. Registar tempos de resposta e casos em que não existe uma sugestão útil.

Critério de conclusão: apresentar sugestões verificáveis e uma comparação reproduzível. O valor de similaridade não deve ser apresentado como probabilidade de a recomendação estar correta.

## Entrega 4

Validar cenários com e sem a plataforma. Definir previamente o instante inicial de deteção, reconhecimento e recuperação; usar a mesma convenção nos dois cenários. Registar tempos, intervenções, disponibilidade e limitações. Repetir cenários suficientes para a comparação ser interpretável e separar o efeito da pesquisa do efeito do dashboard.

Critério de conclusão: relatório com resultados observados, sem atribuir aos dados sintéticos ganhos que não foram medidos. Completar guia de operação, ERD final, regras e exemplos de post-mortem.

## Fora da prioridade inicial

ChatOps com Teams/Slack, deteção de anomalias, cálculo de custo de indisponibilidade, execução automática de runbooks e funcionalidades de produção distribuída. As três primeiras são extensões no enunciado. A execução automática não faz parte desta proposta inicial.

## O que deves fazer agora

Executar o roteiro, entender os três perfis e acompanhar um incidente até ao fecho. Ler `app/main.py` por grupos de rotas e `app/search.py` para perceber a pesquisa. Registar dúvidas e eventuais comentários do professor. As Entregas 2 e 3 já têm implementações e validações documentadas acima. A Entrega 4 tem agora um ensaio técnico repetível por script; a avaliação com participantes e comparação sem a plataforma continua pendente.

Os prazos e requisitos académicos estão documentados em `../../Documentação/Projeto I/COMEÇAR_AQUI.md`.

## Incremento v0.15 · dossier do caso

Implementada a exportação autenticada de incidentes em Markdown e JSON, incluindo linha temporal, post-mortem, contexto da deteção, escalonamento e evidências preservadas. Serve de apoio aos anexos da avaliação, sem substituir a avaliação com participantes. Consultar dossier-incidentes.md e validacao-dossier.json.

## Incremento v0.16 · conhecimento aplicado

Associação explícita de casos resolvidos à investigação, com justificação e cópia do conhecimento usado preservadas na linha temporal e no dossier. Consultar conhecimento-aplicado.md. Avaliação com participantes continua pendente.
