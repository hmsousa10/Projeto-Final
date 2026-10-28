# Logs diretamente ligados ao serviço · v0.18 local

A ligação configurável da Aurora a `http://portal-lab:8080/api/orders` passa a consultar e preservar os seus logs no próprio incidente. O identificador gerado da ligação (`service-N`) já não impede a consulta da origem de logs correspondente.

## Mapeamento explícito

O catálogo de `app/logs.py` associa os endereços aprovados a origens Loki conhecidas. Os dois endereços `/health` de referência mostram os pedidos do respetivo serviço HTTP. O endereço `/api/orders` da Aurora usa a origem `portal-lab` e filtra apenas esse endpoint. Um endereço autorizado para sondagens não ganha automaticamente acesso a logs: precisa também de constar deste catálogo. Não existe nesta versão uma interface para configurar fontes Loki de outras empresas.

O filtro do endpoint é aplicado no Loki antes do limite de 50 registos e verificado novamente na resposta. São recusadas origens incorretas e ignorados caminhos fora do âmbito e timestamps fora da janela. O limite mantém-se em 15 minutos, 50 linhas e resposta máxima de 512 KiB, com timeout de 5 segundos. Não são aceites consultas LogQL arbitrárias do navegador.

A remoção de um endereço da política de monitorização bloqueia novas consultas aos seus logs. A pausa das sondagens mantém a consulta dos logs já recolhidos para diagnóstico. As evidências preservadas continuam disponíveis mesmo depois de a ligação ser bloqueada ou de o Loki ficar indisponível.

## Interface e evidências

No detalhe de um serviço com logs ligados existe **Consultar logs deste serviço**. Num incidente ainda não fechado, os logs surgem diretamente, com **Recolher logs para o caso** para operações e administradores.

Cada nova recolha preserva o serviço, a data de consulta, o endereço monitorizado, a origem Loki, o filtro de caminho e as linhas devolvidas. Esses campos ficam guardados no payload existente de incident_evidence e acompanham o dossier JSON/Markdown. Recolhas antigas não são alteradas e a interface indica quando não foi guardado um mapeamento específico.

Logs recentes não correspondem necessariamente a toda a duração de um incidente. O operador continua a decidir a relevância dos registos. Casos fechados não recebem novas evidências; a demonstração INC-010 mantém o histórico original e a referência à recolha efetuada no INC-007.

## Validação e estado de entrega

Testes isolados verificam o mapeamento de uma ligação configurável, filtro no Loki e na resposta, origem incorreta, limites temporais, política revogada, consulta com sondagens pausadas, preservação no caso correto, exportação e permissões de leitura/escrita. As integrações anteriores e o dossier também são testados.

Esta entrega foi preparada e validada localmente. Não foi criado commit nem enviado código para o GitHub nesta etapa, por preferência do autor. Consultar validacao-logs-diretos.json para os resultados registados.

Resultado final: 32 testes afetados passaram em 56,71 s, com o aviso existente Starlette/httpx. A suite completa não foi repetida nesta etapa. O Loki real devolveu 50 linhas exclusivamente de /api/orders para a Aurora; o stream de referência mantém /health e /api/orders. A base conserva 10 incidentes e 73 eventos de linha temporal. Captura em logs-diretos-v018.png.
