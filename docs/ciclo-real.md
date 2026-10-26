> **Atualização v0.12:** o ensaio repetível e os resultados atuais estão em [Ensaio operacional](ensaio-operacional.md). O registo de validação v0.3 no fim desta página é histórico.

> Para a configuração de novos serviços, disponível desde a versão 0.4, consultar [Monitorização](monitorizacao.md). O percurso de falha descrito abaixo mantém-se.

# Da empresa monitorizada ao incidente · versão 0.3

O **Nexo é a plataforma de operações**, separada do portal usado pelos clientes da empresa. A **Aurora é uma empresa fictícia de demonstração**, com uma página de consulta de pedidos e um serviço HTTP efetivo. Os pedidos apresentados são exemplos fixos; não é um ERP nem uma integração com uma empresa real.

## Experimentar o desafio

1. Executar `iniciar-laboratorio.cmd`, com o Docker Desktop ativo.
2. Abrir o Nexo em http://127.0.0.1:8001/#laboratory. As contas locais mantêm-se: `admin@local.test`, `operacoes@local.test` e `leitor@local.test`, com a palavra-passe inicial `EstudoLocal2026!`.
3. Abrir a Aurora em http://127.0.0.1:8002 e confirmar que os pedidos carregam.
4. No Nexo, no cartão **Portal de clientes**, escolher **Provocar falha HTTP 503**. A API `/api/orders` e o endpoint de saúde passam realmente a devolver 503. A Aurora mostra o erro na próxima atualização ou ao clicar em **Atualizar pedidos**.
5. Aguardar duas sondagens de falha. O blackbox exporter mede o serviço, o Prometheus recolhe as amostras e o Nexo abre um incidente P1. Com os intervalos atuais, a deteção costuma levar 20–40 segundos, sem garantia de prazo se a stack estiver indisponível.
6. Abrir **Tratar INC-…**, atribuir um responsável, reconhecer e iniciar a investigação. Consultar os logs do Loki e os casos anteriores. **Recolher logs para o caso** preserva até 50 registos da janela atual como evidência persistente.
7. No laboratório, escolher **Recuperar serviço**. Confirmar os pedidos na Aurora e aguardar duas sondagens saudáveis. A recuperação fica na linha temporal, sem resolver automaticamente o incidente.
8. Descrever a resolução. Fechar com causa raiz, prevenção e, se útil, runbook. O caso passa a estar disponível para pesquisa na base de conhecimento.
9. Repetir o ensaio: uma nova ocorrência pode recuperar o caso fechado através da pesquisa TF-IDF. A pesquisa híbrida com embeddings locais está disponível desde a v0.8; selecionar o âmbito operacional e o serviço para consultar ocorrências anteriores.

As falhas de laboratório expiram automaticamente após dois minutos. A API de teste separada tem atraso de base de 800 ms; recuperar esse alvo repõe o atraso de base, pelo que continua degradado face ao objetivo de 500 ms. Para o primeiro percurso completo, usar o Portal de clientes.

## Regras de deteção implementadas

São necessárias duas amostras distintas e recentes, separadas por, no máximo, 25 segundos. Não são usadas amostras com mais de 45 segundos para confirmar o estado. Consultar repetidamente a mesma amostra não conta como novas falhas.

- Duas sondagens sem sucesso: incidente P1.
- Duas sondagens bem-sucedidas com duração acima da meta do serviço: incidente P2.
- Uma indisponibilidade confirmada após degradação eleva o incidente ativo para P1 e regista a alteração.
- Sondagens repetidas não duplicam o incidente ativo. O estado do alerta e o índice de unicidade persistem em SQLite; a avaliação decorre na mesma transação de importação.
- Duas sondagens dentro da meta confirmam recuperação. O fecho é humano. Resolver um incidente automático exige recuperação recente confirmada.
- Fechar um caso não abre outro imediatamente para a mesma falha contínua. Uma recuperação seguida de nova falha permite um novo caso; se o anterior ainda estiver ativo, a recorrência é agrupada nele.

A descrição acima corresponde à configuração inicial. Desde a v0.6 existem regras por serviço e escalonamento por prazo; desde a v0.7 existem janelas de SLO. Notificações externas e manutenção programada continuam pendentes.

## Logs e histórico

Cada serviço de teste envia ao Loki logs dos pedidos HTTP efetivamente atendidos: método, caminho conhecido, código de estado e duração. Não são recolhidos cookies, palavras-passe, cabeçalhos, endereços IP nem query strings. O envio usa uma fila limitada e é best effort: registos podem perder-se quando o Loki está indisponível ou a fila enche. Não constitui auditoria inviolável nem entrega garantida.

O Nexo consulta até 50 registos dos últimos 15 minutos, mediante sessão válida e mapeamento fixo do serviço. Uma falha no Loki devolve erro explícito, não uma lista vazia interpretada como sucesso. A configuração de retenção central é de 24 horas, com limpeza assíncrona.

As evidências recolhidas para o incidente ficam em SQLite, juntamente com autor e data, e continuam consultáveis quando o Loki está desligado ou os logs centrais expiraram. Há um limite de 20 recolhas por incidente. O caso fechado não aceita novas evidências. A linha temporal e a auditoria registam as intervenções, a recuperação e o fecho.

## Isolamento dos controlos de teste

Os controlos exigem `LAB_MODE=1`, modo de demonstração e perfil Administrador ou Operações. O arranque recusa LAB_MODE em produção. Uma chave aleatória é criada em `data/lab-control.key` e montada como segredo Docker; o seu valor não é entregue ao navegador nem incluído na imagem ou no Git. O alvo valida a chave em cada comando. Não existem comandos de shell, URLs arbitrárias nem acesso ao socket Docker.

Apenas os portais Nexo e Aurora publicam portas, ambas em loopback. Prometheus, Loki, exporter e API de teste não publicam portas. As imagens correm sem privilégios de root, com capabilities removidas e sistema de ficheiros apenas de leitura, exceto os volumes de dados. Existem consulta de vulnerabilidades de dependências e ensaios de restauro nas versões 0.9–0.11. Um pentest independente continua pendente.

## Como se aplica a uma empresa real

O portal da empresa continua a ser o portal que já existe. É necessário obter autorização, identificar os serviços e respetivos responsáveis, escolher endpoints de saúde ou instrumentação, configurar ligações e credenciais com permissões mínimas e mapear métricas/logs para o inventário do Nexo. O laboratório inclui dois mapeamentos de referência. Desde a v0.4 é possível configurar novos serviços para endereços autorizados pela instalação.

O percurso operacional é o mesmo: medições, deteção, incidente, intervenção humana, evidência e conhecimento. Os controlos de falha aqui implementados pertencem exclusivamente à empresa fictícia de teste. A validação em sistemas de uma organização deve ser preparada em homologação, dentro do âmbito autorizado.

## Validação

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/validar-ciclo-real.py
```

O segundo comando provoca falhas reais nos serviços locais de teste, trata e fecha um caso, procura-o no histórico e provoca nova ocorrência. Repõe o serviço após cada falha e deixa o segundo incidente recuperado mas aberto para tratamento manual. Não apaga casos anteriores. O resultado observado é guardado em [validacao-ciclo-real.json](validacao-ciclo-real.json).

As médias de MTTA/MTTR do dashboard ainda misturam os exemplos iniciais com os ensaios locais. Não são resultados de uma avaliação de ganhos numa empresa real.

Validação observada em 24/10/2026: **39 testes automáticos passaram**, com um aviso de depreciação Starlette/httpx. O ensaio real terminou às 20:15:25 UTC: caso **INC-006** fechado, com logs preservados, e nova ocorrência **INC-007** recuperada, ainda aberta para tratamento manual. A Aurora voltou a responder HTTP 200. O primeiro ensaio também deixou o caso INC-005 fechado; todos são ensaios académicos identificados nas notas, não ocorrências de uma organização real.

Interface verificada no navegador: navegação no laboratório, controlo de recuperação, consulta do caso fechado e visualização das evidências preservadas. Imagens: [Nexo](laboratorio-v03.png) e [Aurora](aurora-v03.png).

Referências técnicas: [API Loki](https://grafana.com/docs/loki/latest/reference/loki-http-api/) e [configuração de armazenamento local](https://grafana.com/docs/loki/latest/configure/examples/configuration-examples/).
