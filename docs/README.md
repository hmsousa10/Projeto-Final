# Documentação do Nexo

## Começar e compreender

- [README principal](../README.md): arranque, contas de demonstração e configuração.
- [Arquitetura](arquitetura.md): decisões e modelo inicial; consultar também os guias das funcionalidades adicionadas posteriormente.
- [Plano](plano.md): entregas e pendências. As secções iniciais descrevem o estado dessas entregas na respetiva data.
- [Navegação assíncrona](navegacao-assincrona.md).
- [Desenvolvimento e manutenção](../CONTRIBUTING.md): organização, validação, dados e dívida técnica.

## Operar o portal

- [Integração empresarial por API · Aurora](integracao-empresarial.md) e [alertas da ligação autenticada](alertas-api-empresarial.md).

- [Laboratório](laboratorio.md) e [ciclo real](ciclo-real.md).
- [Logs diretamente ligados ao serviço](logs-diretos.md).
- [Monitorização](monitorizacao.md), [regras de alerta](regras-alerta.md) e [SLIs/SLOs](slis-slos.md).
- [Impacto potencial por dependências](impacto-potencial.md) e [avaliações preservadas](impacto-preservado.md).
- [Consulta e filtros de incidentes](consulta-incidentes.md) e [contexto limitado dos painéis](contexto-incidentes.md).
- [Auditoria pesquisável](auditoria.md).
- [Contas e inventário](contas-inventario.md) e [notificações](notificacoes.md).
- [Pesquisa de conhecimento](conhecimento.md), [conhecimento aplicado](conhecimento-aplicado.md) e [dossier de incidentes](dossier-incidentes.md).

## Proteger e recuperar dados

- [Cópias e restauro](copias-restauro.md).
- [Recuperação portátil](recuperacao-portatil.md).
- [Manutenção, promoção e reversão](manutencao.md).

## Evidências e avaliação

- [Ensaio operacional](ensaio-operacional.md): protocolo, resultados e limites da medição.
- [Segurança e carga](seguranca-carga.md): controlos testados e âmbito da validação.
- `validacao-*.json`: resultados específicos, alguns históricos e alguns de tentativas falhadas; consultar a data e a versão dentro do ficheiro.
- `*.png`: capturas das versões indicadas nos nomes; não são provas de testes de segurança.
- `../evaluation/`: scripts, protocolos e resultados experimentais reproduzíveis.

Os guias descrevem a implementação. A documentação académica de Projeto I permanece na pasta Documentação exterior a esta aplicação.

- [Conectores empresariais · 0.26 local](conectores-empresariais.md): contrato separado do transporte, configuração por instalação e proteção do histórico.

- [Instalações isoladas · 0.27 local](instalacoes-isoladas.md): segunda instalação, credenciais próprias e ensaio de persistência e separação de dados.

- [Cópias por instalação · 0.28 local](copias-por-instalacao.md): chaves separadas, identidade cifrada, recuperação isolada e kit portátil por empresa.

- [Manutenção por instalação · 0.29 local](manutencao-por-instalacao.md): promoção, verificação e reversão com identidade empresarial e pontos de retorno separados.

- [Pré-produção HTTPS · 0.30 local](preproducao-https.md): proxy, certificado local validado, modo de produção e isolamento da entrada.

- [API empresarial HTTPS · 0.31 local](api-empresarial-https.md): integração TLS privada, confiança por cliente e recolha automática autenticada.

- [Ciclo operacional HTTPS](ciclo-operacional-https.md): dois incidentes reais no ensaio isolado, conhecimento reutilizado e dossiers preservados.
