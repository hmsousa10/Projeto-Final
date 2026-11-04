> Este documento descreve uma etapa anterior do protótipo. Para o estado atual da versão 0.3, consultar [o ciclo real e a arquitetura de integração](ciclo-real.md).

# Laboratório de observabilidade · versão 0.2

Esta versão acrescenta sondagens HTTP reais ao protótipo. Os alvos são serviços de teste locais, não sistemas de uma empresa. Os quatro serviços anteriores e os respetivos incidentes continuam a ser exemplos sintéticos.

## Arranque

Com o Docker Desktop ativo, executar `iniciar-laboratorio.cmd` ou, na pasta do projeto:

```powershell
docker compose -p nexo-lab -f compose.observability.yaml up -d --build
```

Abrir http://127.0.0.1:8001 e iniciar sessão com `admin@local.test` / `EstudoLocal2026!`. Aguardar até 30 segundos pela primeira recolha. O arranque Python anterior mantém-se na porta 8000; este laboratório usa uma base independente num volume Docker.

Para parar sem apagar dados:

```powershell
docker compose -p nexo-lab -f compose.observability.yaml stop
```

## Percurso dos dados

O blackbox exporter faz GET `/health` a dois serviços HTTP. O Prometheus recolhe `probe_success` e `probe_duration_seconds` a cada dez segundos. O Nexo consulta a API do Prometheus a cada dez segundos e guarda as amostras com o instante original e a origem `prometheus`. A chave única impede duplicação quando as janelas de consulta se sobrepõem.

- **Laboratório · Portal HTTP:** resposta rápida, normalmente operacional.
- **Laboratório · API HTTP:** atraso configurado de 800 ms, acima do objetivo de 500 ms; deve aparecer degradado.

O atraso é deliberado, mas o tempo mostrado resulta de um pedido HTTP efetivo. As sondagens reais expiram após 45 segundos. Uma falha de recolha aparece no painel; nunca é convertida numa observação bem-sucedida. O simulador de dados sintéticos não pode alterar estes serviços.

O indicador de 24 horas é a proporção das sondagens disponíveis nessa janela. Pode conter apenas alguns minutos de amostras e não equivale a disponibilidade temporal, cobertura completa ou cumprimento de SLA. Os indicadores MTTA/MTTR ainda incluem exemplos sintéticos.

## Validação reproduzível

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/validar-laboratorio.py
```

O segundo comando é um teste de integração sobre o projeto Docker **nexo-lab**: para e recupera apenas o alvo HTTP de laboratório e o Prometheus, confirma indisponibilidade e expiração dos dados e volta a iniciar ambos mesmo em caso de falha. Não o usar contra uma instalação de produção.

## Limites e proteção

Apenas o portal publica uma porta, ligada a `127.0.0.1`. Prometheus, exporter e alvos ficam numa rede interna. O portal tem ainda uma rede de acesso para permitir o encaminhamento de porta do Docker Desktop. Os contentores têm limites de memória/CPU, sistema de ficheiros apenas de leitura, capabilities removidas e proibição de novos privilégios. Os volumes de dados continuam graváveis. O socket Docker não é montado.

As contas conhecidas destinam-se exclusivamente à demonstração local. Esta configuração não é uma configuração de produção nem uma certificação de segurança. Faltam logs centralizados com Loki, alertas reais, retenção das observações SQLite, auditoria das dependências/imagens, testes de carga e validação de restauro. A recolha usa um único processo da aplicação; não iniciar vários workers antes de separar o coletor.

As versões das imagens estão fixadas por tag; ainda não por digest. Referências: [API do Prometheus](https://prometheus.io/docs/prometheus/latest/querying/api/) e [blackbox exporter](https://github.com/prometheus/blackbox_exporter).

## Evidência de execução · 24 de outubro de 2026

Validação efetuada neste computador com Docker Desktop 29.9.2:

- Suite completa: **31 testes passaram**, com um aviso de depreciação do cliente de testes Starlette/httpx.
- Stack com cinco contentores iniciada; portal com healthcheck saudável.
- Teste `scripts/validar-laboratorio.py`: ligação ao Prometheus, alvo saudável, alvo degradado por latência, paragem real do alvo detetada, recuperação detetada, indisponibilidade do coletor visível, expiração das amostras e recuperação da recolha — todos passaram.
- Na conclusão do teste, portal HTTP com 1,83 ms e API HTTP com 801,99 ms; valores pontuais, não resultados de um ensaio de desempenho.
- Aplicação reconstruída e reiniciada após o teste; sessão e histórico de sondagens preservados no volume.
- Interface verificada no navegador, com as duas origens identificadas. Imagem: laboratorio-v02.png.

Estes testes verificam a primeira integração operacional. Não demonstram conformidade integral com o enunciado nem segurança de produção.
