# Conectores empresariais · versão 0.26 local

O cliente HTTP já não conhece o formato das encomendas. O transporte autenticado, a cache, os limites da resposta e a classificação das falhas ficam em `app/enterprise.py`. A validação e normalização do contrato ficam em `app/connectors/orders.py`; o registo de conectores suportados fica em `app/connectors/__init__.py`.

## Configuração por instalação

- `ENTERPRISE_CONNECTOR=orders-summary-v1`: seleciona um conector incluído e revisto no código. Valores desconhecidos impedem o arranque; não se importam módulos indicados na configuração.
- `ENTERPRISE_COMPANY_ID=aurora`: identidade esperada na resposta. Outra empresa pode usar este mesmo conector se cumprir o contrato, incluindo a sua própria identidade.
- `ENTERPRISE_API_URL`: endpoint completo, sem credenciais, parâmetros de consulta ou fragmento. Exige HTTPS em produção. O HTTP da Aurora só é permitido no laboratório local explícito.
- `ENTERPRISE_API_TOKEN_FILE`: caminho de um ficheiro com a chave de leitura, montado como segredo. Não se guarda a chave no código, na configuração apresentada no navegador ou na base de dados.

O Compose do laboratório passa o conector explicitamente. Instalações anteriores que não definam `ENTERPRISE_CONNECTOR` mantêm `orders-summary-v1`. Estas variáveis são lidas do ambiente do processo: um ficheiro `.env` isolado não as injeta automaticamente num serviço Docker.

## Compatibilidade e histórico

Cada instalação continua associada a uma empresa e a uma API. O registo persistido passa também a conter `connector_id`. Um registo da versão 0.25 sem esse campo é reconhecido como `orders-summary-v1`, preservando serviço, histórico e estado de pausa. A atualização não cria um serviço adicional.

Trocar empresa, endpoint ou conector numa base com histórico provoca erro de arranque. Uma mudança legítima exige uma migração explícita ou outra base; não basta editar a configuração e misturar os dados antigos. Rodar a chave de acesso sem mudar a ligação continua permitido.

A resposta autenticada mantém `adapter` por compatibilidade e acrescenta metadados públicos do conector: identificador, nome e tipo de resumo. Não apresenta o endpoint nem a chave. A interface continua a apresentar o resumo de encomendas; ainda não existe um painel universal para todos os domínios empresariais.

## Adicionar um contrato diferente

1. Implementar um conector com identificador versionado, nome, tipo de resumo e `normalize(payload, company_id)`.
2. Validar estritamente a identidade, os campos, os limites e a atualidade do contrato. Devolver somente o resumo normalizado autorizado. Dados desatualizados levantam `StalePayload`; dados incompatíveis levantam `ValueError`.
3. Registar o conector no código e testar respostas válidas, identidades erradas, conteúdo inválido, dados antigos e ausência de exposição de segredos.
4. Acrescentar a apresentação desse tipo de resumo e, se necessário, um transporte de autenticação diferente. O transporte atual suporta apenas Bearer fixo; OAuth não está implementado.
5. Publicar uma versão comum do Nexo e selecionar o conector na configuração da instalação apropriada.

O motor de incidentes recebe o estado técnico da ligação e a latência, independentemente do formato empresarial. Não interpreta totais de encomendas como métricas de disponibilidade.

## Primeiros clientes

A direção prevista é uma instalação por cliente, com o mesmo código e bases, volumes, credenciais e cópias independentes. Para executar várias instalações num mesmo anfitrião, nomes dos projetos Compose, portas, volumes e segredos devem ser distintos. O laboratório Aurora não é um modelo de produção nem deve ser copiado com contas de demonstração para a Internet.

O provisionamento automatizado por cliente, domínio e HTTPS, operação de cópias e atualizações e validação independente de segurança continuam pendentes. Esta alteração cria o ponto de extensão dos conectores; não implementa SaaS com várias organizações nem comprova prontidão comercial. Não houve acesso a qualquer empresa real.

## Validação

Os testes de integração usam um servidor HTTP e bases temporárias. Cobrem reutilização do mesmo contrato por outra empresa, rejeição de identidade cruzada, conectores desconhecidos, atualização de registos antigos e rejeição atómica de mudanças no histórico. Os testes existentes continuam a cobrir autenticação, redirecionamentos, limites de resposta, cache, deteção automática, recuperação confirmada e restauro em pausa.

A validação completa identificou também uma regressão anterior na referência a casos fechados. O motor mantém a supressão de duplicados num episódio contínuo, mas descarta referências fechadas após recuperação ou enquanto os alertas estão suspensos, permitindo detetar uma nova falha após retoma. A correção foi verificada com os testes de alertas e o ciclo HTTP empresarial completo.

Resultados: 266 testes passaram na execução geral e um revelou a regressão descrita acima. Após a correção, os 54 testes das áreas afetadas passaram, incluindo o teste que falhava. Os 37 testes da interface passaram. A suite geral não foi repetida integralmente após a correção. Detalhes e hashes em [validação dos conectores](validacao-conectores.json); captura em [conectores-v026.png](conectores-v026.png).
