# Entrega consolidada · 0.31

A publicação de 28/10/2026 reúne o código desenvolvido desde a base 0.17: consulta de incidentes, contexto e impacto preservado, navegação assíncrona, logs com ligação explícita, integração empresarial, recolha e alertas, conectores, instalações isoladas, cópias e manutenção por instalação, pré-produção HTTPS e ensaio operacional completo.

O histórico Git desta entrega agrupa o código/infraestrutura/testes e a documentação/evidências em commits distintos. Não reconstrói retroativamente um commit por versão experimental.

## Validação disponível

- A última suite completa da aplicação terminou com 306 testes Python aprovados; consultar `validacao-api-https.json`.
- Os 40 testes da interface passaram sobre o código real em Node VM; não substituem um ensaio completo de navegador.
- O novo ensaio operacional HTTPS foi verificado em duas execuções de falha/recuperação, com referência ao primeiro caso no segundo e dossiers exportados.
- Os testes dirigidos da monitorização e guardas iniciais passaram (15); a guarda final do novo comando passou em 7 testes. O CI executa também estes testes no conjunto completo após o push.
- Os ensaios Docker, Windows/DPAPI, TLS e manutenção estão registados nos respetivos guias; o workflow Linux não reproduz sozinho todos esses cenários.

Os JSON de validação preservam o commit-base e o estado local observados na altura de cada ensaio, incluindo a indicação de que ainda não tinha havido commit/push. São registos históricos, não declarações sobre o estado posterior desta publicação. Existem avisos de descontinuação Starlette/httpx documentados.

## Dados que ficam fora do Git

Bases SQLite, sessões, dados dos volumes, passwords/chaves, certificados privados, arquivos cifrados e dossiers completos de execução permanecem fora do repositório. O código contém apenas credenciais fictícias identificadas dos testes e os caminhos das configurações. Imagens Docker e segredos precisam de ser preparados no computador de destino; clonar o repositório não transporta o estado dos portais.

O projeto mantém-se em desenvolvimento e não foi publicado na Internet. A publicação no repositório privado não certifica segurança nem prontidão comercial. Para arranque e percursos disponíveis, consultar o README e o índice da documentação.
