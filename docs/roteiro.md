> Este documento descreve uma etapa anterior do protótipo. Para o estado atual da versão 0.3, consultar [o ciclo real e a arquitetura de integração](ciclo-real.md).

# Roteiro de demonstração e estudo

## Preparação

Executa `iniciar.cmd`, abre http://127.0.0.1:8000 e usa a conta `admin@local.test` com a palavra-passe inicial `EstudoLocal2026!`. Se a palavra-passe foi configurada antes de criar a base de dados, usa o valor configurado. A sessão pode já estar iniciada se estiveres a usar a pré-visualização deixada aberta durante o desenvolvimento.

Os dados guardados são de demonstração. Qualquer cenário executado durante a verificação da interface também fica guardado e aparece no histórico/auditoria. Não é necessário apagar dados para voltar a experimentar.

## Experiência guiada

1. Em **Visão geral**, identifica os quatro serviços e as médias iniciais. Explica que os três incidentes históricos são exemplos, pelo que as médias não demonstram ganhos reais.
2. Em **Serviços**, abre o Portal de vendas. Vê que depende da API de pagamentos e da Base de dados. Cria um serviço chamado «Portal de marcações», com equipa e objetivos próprios, se quiseres testar o inventário. O novo serviço não recebe observações automaticamente.
3. Volta à **Visão geral** e escolhe **Simular cenário**. Seleciona um serviço e «Indisponibilidade». É criado um P1. Se já houver um alerta ativo do simulador nesse serviço, o alerta será associado ao mesmo incidente.
4. No incidente, escolhe um responsável e guarda a atribuição. Clica em **Reconhecer incidente**, depois em **Iniciar investigação**. Observa os novos eventos na timeline.
5. Acrescenta uma nota, por exemplo «Confirmados erros HTTP 503 após alteração de configuração». Abre um caso semelhante para consultar a resolução anterior. Fecha e volta ao incidente ativo pela lista quando necessário.
6. Para simular a recuperação, fecha a janela do incidente, executa «Recuperação» no mesmo serviço e volta ao incidente. O serviço fica saudável, mas o incidente permanece em investigação.
7. Regista a resolução, por exemplo «Revertida a configuração e confirmadas respostas HTTP sem erro». O MTTR passa a incluir o novo caso.
8. Fecha com causa raiz, prevenção e um runbook. Explica que é uma conclusão escrita para o cenário de teste, sem prova de uma falha empresarial real. Exemplo de causa: «Configuração inválida introduzida no último deploy». Prevenção: «Validar variáveis de ambiente no pipeline antes de publicar».
9. Abre **Base de conhecimento** e pesquisa «configuração HTTP». O caso fechado deve aparecer entre os resultados se tiver esses termos. O número mostrado é similaridade, não probabilidade de a solução ser correta.
10. Abre **Auditoria** e confirma quem criou, atribuiu e fez avançar o incidente.
11. Termina a sessão e entra como `leitor@local.test` com a mesma palavra-passe inicial. Confirma que consegues consultar os registos e que as operações de escrita não aparecem. A API também recusa escrita deste perfil.

## Como explicar o projeto

O portal combina informação de serviços, incidentes e conhecimento histórico para apoiar uma equipa de operações. Nesta primeira versão, o ciclo operacional é funcional, mas os dados de monitorização são simulados. O próximo passo é integrar uma aplicação de teste instrumentada e uma stack de telemetria real.

Um SLI é o indicador medido; um SLO é o objetivo desse indicador; um SLA é um compromisso formal de serviço. Não há promessa de 100% de disponibilidade ou respostas instantâneas. O projeto deve medir e tornar visíveis os objetivos acordados.

O módulo atual recupera texto relevante com TF-IDF. Embeddings serão uma evolução a comparar experimentalmente, não uma dependência necessária para testar já o percurso. A aplicação apresenta o incidente de origem e mantém a decisão na pessoa responsável.

## O que estudar no código

Primeiro acompanha uma ação do browser: formulário em `web/app.js`, pedido JSON, contrato em `app/models.py`, rota em `app/main.py` e escrita SQL em `app/db.py`. Depois lê a pesquisa em `app/search.py` e experimenta consultas com palavras diferentes. Por fim, lê os testes para perceber que regras são verificadas e que casos de erro devem ser recusados.

Se o professor perguntar se o MVP está concluído, a resposta é não: esta é a versão 0.1, com o primeiro percurso funcional. A recolha externa, o escalonamento e a avaliação por cenários ainda estão no plano.
