# Segurança e carga · v0.10

Este bloco combina revisão direta do código, testes de regressão, controlos HTTP numa instalação isolada, consulta de avisos de dependências Python e um ensaio curto de concorrência. A ferramenta especializada prevista pela skill de revisão não estava disponível; não foi produzida uma revisão independente por esse agente.

## Correções entregues

- Leitura do corpo do pedido limitada a **dez segundos no total**, incluindo pedidos por chunks. O limite anterior de 64 KiB mantém-se. Um corpo que não chega a tempo recebe HTTP 408 antes da desserialização.
- No máximo **duas operações de palavras-passe por processo**: login, criação de conta e alteração de palavra-passe. Excesso recebe HTTP 429 com `Retry-After: 2`. O rate limit persistente por conta/IP continua separado desta proteção de CPU.
- O administrador inicial em produção exige 15–200 caracteres e recusa as entradas da lista local de palavras-passe comuns/demonstração. Instalações locais sem demonstração aceitam 12–200. A lista de rejeição é limitada; não é um serviço completo de pesquisa de palavras-passe comprometidas.
- O access log Uvicorn guarda método, caminho e estado, removendo a query string. Uma alteração incompatível do contrato desse logger suprime o registo em vez de deixar passar dados. Corpos, cookies e palavras-passe não são acrescentados ao logger. URLs noutros logs/proxies e o histórico do navegador precisam de proteção própria.
- O painel calcula contagens e disponibilidade das últimas 24 horas em SQL e só materializa as **48 medições** que mostra no gráfico. A proporção continua a usar todas as medições da janela.
- Os cálculos de SLO são serializados e podem ser reutilizados por até **três segundos**, por janela. Nova observação, política, edição de serviço ou alteração do alvo invalidam a reutilização. A mudança de intervalo de dez segundos também invalida. Alterações SQL fora da aplicação são cobertas pelo TTL, sem promessa de invalidação imediata.
- A API SLO devolve `cache_age_seconds`, `cache_max_age_seconds` e o `generated_at` do cálculo original. Se outro cálculo ocupar o acesso por mais de cinco segundos, o pedido recebe 503 com `Retry-After: 1`. A cache preserva as regras de cobertura, política parcial e intervalos desconhecidos.
- O servidor Docker e o arranque local usam limite de concorrência 32, backlog 64 e keep-alive de cinco segundos. O limite inclui ligações, podendo rejeitar pedidos com 503 antes de chegarem à aplicação. São limites por processo; não constituem uma proteção completa contra DoS.
- O instalador `pip` foi removido das imagens finais da aplicação e do encoder depois da instalação das dependências. As atualizações passam por reconstruir a imagem. O Python local de desenvolvimento mantém o seu instalador.

O prazo de dez segundos cobre o corpo **depois de os headers chegarem à aplicação**. Não mede nem limita todos os cenários de headers lentos, TLS, proxies ou conexões exteriores. A configuração de produção continua a exigir HTTPS, host/origem explícitos e ausência de dados demo; esta entrega não configura certificados nem publica o portal na Internet.

## Controlos verificados

As regressões cobrem autenticação, revogação de sessões, perfis, origem/Host, limite de corpo e tentativas, palavras-passe iniciais, concorrência no trabalho criptográfico, prazo de leitura, remoção da query dos logs e manutenção dos totais quando o histórico apresentado é limitado. O teste de SLO verifica cálculo único sob oito pedidos concorrentes, invalidação por alteração de serviço/nova observação e expiração da cache.

Em HTTP real, a instalação isolada passou **22 verificações**: acesso anónimo a dados, ficheiros/segredos fora do diretório público, inexistência de upload de restauro, tentativa de SQL injection no login, flags de cookies locais, ausência de hashes na resposta, permissões de leitura, cabeçalhos de segurança, erros sem ecoar valores submetidos e término da sessão. Ver `validacao-seguranca-v010.json`. O cookie local HTTP não é apresentado como cookie Secure; esse atributo é verificado nos testes do perfil HTTPS.

Os access logs do ensaio também foram inspecionados: as linhas de `/api/knowledge` não continham query strings. Isso verifica este logger, não elimina parâmetros já guardados em execuções anteriores.

## Dependências

Foram inventariadas as versões efetivamente instaladas nas imagens: **17 distribuições na aplicação e 29 no encoder** após remover o instalador. Apenas nomes e versões públicos foram enviados à API OSV. A consulta completa final não devolveu avisos conhecidos para essas versões. Resultados e inventários: `validacao-dependencias.json`, `dependencias-app.json` e `dependencias-encoder.json`.

A primeira consulta sinalizou `pip 25.0.1` na imagem do encoder. O resultado foi preservado em `validacao-dependencias-inicial.json`; o instalador não é necessário para inferência e foi removido da imagem final. Este achado não demonstra que o portal disponibilizasse uma forma de explorar esse componente. Não se classificaram todos os avisos como ataques aplicáveis à aplicação.

Ausência de avisos na consulta não significa ausência de vulnerabilidades. Não foi feita análise integral do sistema operativo das imagens, proveniência de todos os artefactos, malware de dependências, revisão integral ASVS, teste de penetração ou avaliação de exposição à Internet. O código, os dados, as chaves e o dispositivo continuam sujeitos a outros riscos.

## Ensaio de carga

O projeto Compose **nexo-load** cria a sua própria rede, encoder e base temporária em tmpfs. Não monta o volume nexo-data, não liga Prometheus/Loki e não usa o encoder do laboratório ativo. A aplicação de ensaio só arranca com `LOAD_TEST_MODE=1` e o caminho fixo `/app/data/load-test.db`. O cliente só aceita `127.0.0.1:8010` e exige o marcador de fixture antes de enviar carga.

A fixture contém **17 376 observações, 103 incidentes e seis serviços**. É toda sintética. O corpus global fica limitado aos cem casos mais recentes; há dez conteúdos diferentes repetidos para exercitar o limite, não para medir qualidade de pesquisa. Os embeddings são preparados antes do ensaio. A aplicação tem uma CPU e 256 MiB; o encoder tem duas CPUs e 1 GiB. O relatório guarda versões, hashes de fontes/dataset e recursos do contentor.

O ensaio usa clientes em circuito fechado, sem tempo de reflexão, e uma ligação TCP nova por pedido. Não equivale a utilizadores reais nem a uma taxa aberta constante. Mistura resumo, serviços, incidentes, pesquisa híbrida e SLO de 24 horas. O resultado final desta execução foi:

- Um cliente, 40 pedidos: **40 respostas 200**, p95 de 34,94 ms nos aceites.
- Quatro clientes, 40 pedidos: **40 respostas 200**, p95 de 228,78 ms.
- Doze clientes, 40 pedidos: **40 respostas 200**, p95 de 2 612,21 ms.
- Pico de 48 clientes, 96 pedidos ao resumo: **28 respostas 200 e 68 respostas 503**. As rejeições não contam como sucesso nem entram nos percentis dos aceites.

As 24 pesquisas medidas nas três fases usaram efetivamente o método híbrido. O relatório identifica o método de cada resposta para não confundir fallback textual com execução semântica. Após o pico, o resumo respondeu 200 em 19,05 ms. Um corpo deliberadamente incompleto recebeu 408 ao fim de dez segundos. Oito logins inválidos simultâneos produziram dois 401 e seis 429 na fixture recém-criada.

As políticas SLO da fixture são recentes: a janela de 24 horas tem política parcial. O ensaio exercita a leitura e agregação do histórico, mas não é uma medição de capacidade com políticas que cubram toda a janela; esses cálculos são verificados funcionalmente nos testes de SLO.

O processo registou RSS máximo de 92 088 KiB; o pico de memória reportado pelo cgroup foi 84 054 016 bytes. São métricas diferentes, com contabilização diferente, não valores intercambiáveis de capacidade. O pico do encoder não foi usado para declarar capacidade total do sistema.

### Falha inicial preservada

O primeiro ensaio encontrou oito timeouts nas oito consultas SLO da fase com doze clientes. Está preservado em `validacao-carga-inicial.json`. Os leitores concorrentes repetiam o cálculo e provocavam contenção. Depois do cálculo único/cache curta, o mesmo tipo de ensaio terminou sem timeouts nas fases de 1/4/12 clientes. Os dados guardados permitem inspecionar ambas as execuções.

Uma repetição com prazo de espera de dois segundos também devolveu um 503 na fase de doze clientes. Ficou preservada em alidacao-carga-repeticao-inicial.json. A espera máxima passou a cinco segundos e foi acrescentado um teste do limite de espera. A repetição final passou e o script removeu apenas os contentores temporários. A aceitação final continua a exigir 40 respostas 200 em cada fase de 1/4/12 clientes; o critério não foi alargado para aceitar rejeições nessas fases.

A cache troca até três segundos de reutilização por menor trabalho repetido; não é uma comparação de cálculos integralmente novos por pedido. Foram execuções curtas, na mesma máquina de desenvolvimento, com outros processos ativos e sem isolamento de CPU física. Não há inferência estatística, promessa de latência, ensaio prolongado, rede externa, TLS ou garantia de capacidade empresarial. A latência com doze clientes ainda é relevante e não deve ser apresentada como desempenho elevado garantido.

## Repetir sem tocar nos dados ativos

Com Docker iniciado, executar na pasta do projeto:

```powershell
.\validar-seguranca-carga.ps1
```

O script constrói as imagens, recria apenas a instalação temporária, espera pelo marcador e executa carga e controlos HTTP. Guarda os resultados com o sufixo `-repeticao` e remove os contentores/redes do projeto `nexo-load` no fim. Isso apaga apenas os dados temporários do ensaio. A porta 8010 tem de estar livre. Não arranca nem substitui o laboratório `nexo-lab`; o build apenas prepara imagens locais.

A consulta de dependências pode ser repetida com `python -m evaluation.audit_dependencies --output resultado.json inventario-app.json inventario-encoder.json`. Os inventários têm de ser gerados novamente das imagens a avaliar; consultar um inventário antigo não avalia uma imagem nova. Uma falha de acesso à OSV fica marcada como incompleta e não como resultado limpo.

## O que falta

A recuperação portátil foi acrescentada na [v0.11](recuperacao-portatil.md). Continuam pendentes o procedimento de promoção de uma base recuperada, testes de carga mais longos e com volumes maiores, análise do sistema operativo das imagens, revisão independente e configuração de deployment HTTPS. Incidentes, utilizadores e conhecimento continuam num único espaço de trabalho; não se oferece isolamento multiempresa. A avaliação operacional com cenários repetidos e medição de MTTA/MTTR ainda está por realizar.

Fontes técnicas: [limites e timeouts Uvicorn](https://uvicorn.dev/settings/), [comportamento sob concorrência](https://uvicorn.dev/server-behavior/) e [API oficial OSV](https://github.com/google/osv.dev/blob/master/docs/api/post-v1-querybatch.md).

Validação final: 123 testes aprovados em 170,34 segundos, com um aviso de descontinuação do adaptador httpx/Starlette. O laboratório ficou ativo na v0.10.0 com nove incidentes e sessenta entradas de linha temporal preservados. Foi criada uma cópia cifrada antes da atualização.
