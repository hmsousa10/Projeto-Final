# Integração empresarial por API · v0.24 local

O Nexo é o portal da equipa de operações. A Aurora é a empresa fictícia cujo portal é observado. São aplicações distintas: o Nexo consulta APIs e telemetria da empresa, em vez de substituir o seu portal comercial.

A primeira ligação de negócio usa **GET /api/operations/summary**, disponibilizado pelo serviço da Aurora. Esse endpoint calcula totais a partir do mesmo conjunto de pedidos apresentado no portal empresarial. O Nexo autentica-se com uma chave própria de leitura e apresenta os resultados em **Integração empresarial**.

Os pedidos da Aurora continuam a ser dados fictícios, fixos, de demonstração. O transporte HTTP, a autenticação entre servidores e a validação do contrato são reais. Não existe acesso a uma empresa externa nesta entrega.

## Percurso disponível

1. Abrir o Nexo em http://127.0.0.1:8001 e escolher **Integração empresarial**.
2. Consultar a identificação Aurora, origem de laboratório, totais por estado e datas da resposta e da consulta.
3. Abrir o portal empresarial em http://127.0.0.1:8002 para comparar os três pedidos apresentados.
4. Para experimentar indisponibilidade, usar os controlos já existentes no Laboratório empresarial. A mesma falha temporária afeta o endpoint empresarial e as sondagens. A recuperação não fecha automaticamente o incidente.

Os testes que provocam falhas nesta etapa são executados em servidores HTTP e bases temporárias. A validação no laboratório principal apenas consulta a nova API, sem adicionar falhas ou incidentes.

## Dois canais com funções distintas

As sondagens Prometheus continuam a medir sucesso HTTP e latência das ligações autorizadas. Essas observações alimentam as regras que criam incidentes.

A API empresarial fornece um resumo de negócio. Os totais não medem disponibilidade, receita ou pedidos de um dia específico. Nesta versão referem-se ao conjunto de pedidos devolvido pela Aurora. Uma resposta inválida ou uma falha da nova ligação é apresentada como problema de integração; não é convertida em totais zero nem cria, por si só, um novo incidente de negócio.

## Contrato do adaptador orders-summary-v1

O endpoint deve devolver HTTP 200 e Content-Type application/json, com um objeto que contém exclusivamente estes campos:

```json
{
  "schema_version": 1,
  "company_id": "aurora",
  "company_name": "Aurora",
  "environment": "laboratory",
  "generated_at": "2026-10-28T14:00:00+00:00",
  "orders": {"total": 3, "preparing": 1, "shipped": 1, "delivered": 1}
}
```

O instante acima é ilustrativo: o servidor deve gerar um instante ISO com timezone em cada resposta. O Nexo recusa dados com mais de 120 segundos ou mais de 30 segundos no futuro. A identificação tem de corresponder à empresa configurada. environment admite laboratory ou production; essa indicação é fornecida pela API e não constitui certificação da origem. Os quatro totais são inteiros não negativos até um milhão, e total tem de ser igual à soma dos três estados. Valores booleanos e campos adicionais são rejeitados.

O adaptador não recolhe nomes de clientes, endereços, documentos ou linhas individuais de pedidos. A implementação da Aurora apenas agrega o conjunto de demonstração. Uma API empresarial com outros estados ou formatos exige um mapeamento explícito, não uma suposição de equivalência.

## Configuração e proteção

Na instalação do Nexo:

- `ENTERPRISE_API_URL`: URL exato do endpoint de resumo, definido na instalação, sem parâmetros, fragmentos ou credenciais embutidas.
- `ENTERPRISE_API_TOKEN_FILE`: caminho de um ficheiro que contém a chave Bearer de leitura.
- `ENTERPRISE_COMPANY_ID`: identificador esperado; por omissão aurora.

O menu só anuncia a área quando a ligação está configurada. Sem URL e chave, a integração fica desligada. Se apenas um deles existir, o arranque falha com mensagem de configuração. As rotas do Nexo exigem sessão e os três perfis podem consultar o resumo.

A chave está apenas nos servidores, através de um secret montado apenas para leitura. `preparar-laboratorio.ps1` cria enterprise-read.key de demonstração sem imprimir o valor; o ficheiro fica em data/, excluído do Git. É uma chave diferente da de controlo de falhas. Não permite acionar /_control. O navegador não recebe a chave nem faz pedidos autenticados diretamente à API da Aurora.

Fora dos endereços locais explícitos do laboratório, a configuração exige HTTPS. Em produção exige sempre HTTPS. Não se seguem redirecionamentos, nem proxies do ambiente. Há timeout de socket de três segundos, controlo de tempo entre leituras e limite de resposta de 16 KiB. Estes controlos não constituem um SLA de rede. Existe uma consulta por cliente de integração de cada vez; outra consulta simultânea recebe estado busy. Respostas e falhas podem ser reutilizadas durante cinco segundos para evitar chamadas excessivas.

Erros de autenticação da empresa são distintos da sessão no Nexo. O adaptador não expõe corpos de erro, cabeçalhos, tokens ou detalhes das exceções de transporte. Os access logs do laboratório registam apenas método, caminho aprovado, código e duração, sem cabeçalhos Authorization.

Para credenciais de uma organização real, usar um secret gerido fora do repositório e das pastas sincronizadas e atribuir exclusivamente o acesso necessário. A chave de demonstração não deve ser reutilizada. A rotação desta configuração exige reiniciar os dois serviços que leem a chave no arranque.

## Passagem a uma empresa concreta

Falta escolher uma API autorizada pela organização e obter documentação, ambiente de ensaio e credenciais de leitura. Depois é necessário mapear os identificadores de serviços, os estados e o âmbito temporal dos dados, adaptar o contrato de autenticação e validar timeouts, limites e permissões. Se a empresa já fornecer Prometheus, as métricas podem ser ligadas separadamente. Não é obrigatório alterar o portal comercial da empresa quando já existe uma API adequada.

Alertas de negócio com confirmação de amostras, histórico destes totais, equipas/permissões por organização, entrega externa de notificações e avaliação em ambiente representativo continuam por concluir. O ciclo de incidentes existente já pode ser reutilizado; a adaptação não equivale a começar o Nexo de novo. Esta entrega não representa uma instalação pronta para produção.

## Validação

Os testes usam servidores HTTP reais isolados para verificar Bearer, cache, redirecionamentos recusados, autenticação separada dos controlos, falha e recuperação, payloads inválidos, tamanhos, totais incoerentes e datas fora da janela. A API do Nexo é testada nos três perfis. Os testes Node verificam identificação da empresa, indicação de dados fictícios, escape de texto, estados sem totais falsos e navegação durante respostas atrasadas.

  O esquema SQLite e as dependências Python mantêm-se.

## Evolução posterior · v0.25 local

A limitação acima sobre ausência de incidentes automáticos aplica-se à v0.24. A v0.25 acrescenta recolha periódica, serviço próprio no inventário e avaliação pelas regras de alerta, com pausa/retoma e recuperação confirmada. Consultar alertas-api-empresarial.md.
