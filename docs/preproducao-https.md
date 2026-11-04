# Pré-produção HTTPS · versão 0.30 local

**Evolução 0.31:** a API empresarial privada foi entretanto ligada por HTTPS. As descrições abaixo documentam o ensaio original 0.30. Consultar [API empresarial HTTPS](api-empresarial-https.md) para a configuração e validação atuais.

Esta entrega acrescenta um terceiro ambiente, `nexo-preproduction`, separado da Aurora e da Atlas. Executa o Nexo em modo de produção para testar transporte, autenticação e proxy. Ainda não é uma implantação comercial nem integra uma API empresarial real.

## Arranque

Com Docker Desktop iniciado, executar **`iniciar-preproducao.cmd`**. Pelo terminal:

```powershell
.venv\Scripts\python.exe scripts/preproduction.py iniciar --build
.venv\Scripts\python.exe scripts/preproduction.py estado
.venv\Scripts\python.exe scripts/preproduction.py parar
```

O ambiente publica apenas `127.0.0.1:8443` para HTTPS e `127.0.0.1:8084` para redireção HTTP. O endereço lógico de teste é `https://preprod.localhost:8443`. O backend não tem porta publicada. Os volumes, a conta `admin@preprod.test` e o segredo inicial são próprios desta instalação; não se copiam contas nem bases de outro portal.

A palavra-passe inicial é gerada em `data/preproduction/initial-admin.key`, ignorada pelo Git. Repetir a preparação não a substitui. No Windows, o ficheiro herda as permissões da pasta do utilizador, tal como os segredos dos ensaios anteriores; este mecanismo não é um gestor de segredos de produção.

O modo de produção impede demonstração e controlos de falha, exige origem HTTPS, usa cookies `Secure`, `HttpOnly` e `SameSite=Strict`, e desativa `/docs` e `/openapi.json`. A interface identifica este modo; isso descreve a configuração de execução, não uma certificação de prontidão comercial.

## Certificado local e navegador

O Caddy cria uma autoridade local e certificados para o domínio de ensaio. O script exporta **somente o certificado público da CA** para `data/preproduction/root.crt` e mostra o seu hash. A chave privada da CA fica no volume do proxy, sem montagem no backend. Uma CA diferente não substitui silenciosamente o certificado exportado.

**Não foi instalado qualquer certificado no Windows, nem alterado o ficheiro hosts.** Um navegador que ainda não confie nesta CA pode mostrar um aviso. Não é necessário ignorar esse aviso para validar esta entrega: o ensaio abaixo verifica TLS através de uma ligação própria, usando a CA exportada e o nome esperado como SNI. A confiança de um navegador deve ser uma decisão explícita do utilizador; num domínio público pretende-se um certificado de uma autoridade pública, sem instalar uma CA de desenvolvimento nos clientes.

A validação TLS não usa `verify=False`, não desativa a verificação do nome e não aceita certificados arbitrários. O teste confirma também que o contexto de confiança padrão recusa esta CA local.

## Repetir a validação

```powershell
.venv\Scripts\python.exe scripts/validar-https.py
```

O comando liga diretamente a `127.0.0.1` com o nome TLS `preprod.localhost`, sem depender da resolução local de nomes. Verifica saúde HTTPS, certificado e nome, protocolo TLS, redireção para a origem fixa, HSTS, CSP, cookies, autenticação, logout, recusa de origem cruzada e de Host incorreto, e ausência de documentação de desenvolvimento.

Cria um serviço identificado de ensaio apenas no catálogo da pré-produção e reutiliza-o nas execuções seguintes. Não inventa amostras de monitorização nem incidentes. Este ambiente não tem ainda API empresarial nem telemetria externa configuradas; os portais Aurora e Atlas continuam a ter os seus próprios percursos de integração.

O ensaio inspeciona ainda a configuração Docker e inicia um contentor descartável sem privilégios na rede privada para tentar declarar HTTPS por cabeçalhos. Esse pedido é recusado pelo Nexo, porque a origem da ligação não é o proxy autorizado. O registo de tentativas de autenticação também é verificado para confirmar que um endereço forjado pelo cliente não foi usado pelo limitador.

 Os testes do navegador não foram usados para contornar avisos de certificados.

## Proxy e isolamento

A entrada usa Caddy 2.11.7, com imagem base fixada por digest. O executável oficial tem uma capacidade para portas privilegiadas; a imagem derivada remove essa capacidade porque só escuta portas altas. Caddy e Nexo executam sem root, com raiz apenas para leitura, capacidades removidas, limites de recursos e sem acesso ao socket Docker.

A rede privada usa `172.30.250.0/29`: o proxy tem `.2` e o Nexo `.3`. O Uvicorn confia nos cabeçalhos de encaminhamento **apenas de `.2`**, sem wildcard. O Caddy substitui `X-Forwarded-Proto` e `X-Forwarded-For`, e remove `Forwarded` enviado pelo cliente. Esta configuração assume um único proxy; uma futura CDN ou outro balanceador exige uma revisão própria da cadeia de confiança.

O proxy tem uma rede de entrada própria; o Nexo fica apenas na rede interna. Existe uma verificação de vida HTTP em `127.0.0.1:8081` dentro do contentor Caddy, sem porta publicada e sem encaminhamento para a aplicação. Os testes HTTPS verificam separadamente o transporte real através da entrada 8443.

A terminação TLS ocorre no proxy. Entre proxy e Nexo usa-se HTTP na rede Docker privada. Não se trata de cifragem TLS até ao processo da aplicação nem de isolamento contra um administrador do anfitrião.

Se a sub-rede ou as portas já estiverem ocupadas, o arranque é recusado. Não se removem redes nem serviços existentes para resolver o conflito. Alterar a sub-rede exige manter alinhados o endereço do proxy, o IP do backend, a política do Uvicorn e o ensaio de verificação.

## Domínio público: referência, ainda não publicada

`deployment/https/Caddyfile.public.example` é uma referência de adaptação, não é carregado pelo Compose local. Foi convertido para JSON com `caddy adapt` usando `example.com` num contentor **sem rede**; não houve emissão de certificados ou contacto com uma autoridade pública.

Para uma implantação futura, serão necessários um domínio autorizado, DNS para o servidor, portas externas 80/443 encaminhadas para 8080/8443, a origem pública exata em `APP_ORIGIN` e o domínio em `ALLOWED_HOSTS`. A configuração pública deixa de usar `tls internal`; a emissão e renovação passam a depender do ambiente real e da autoridade pública.

Não basta substituir o nome no ensaio local e publicar as portas. Continuam necessários configuração de segredos e API empresarial HTTPS, cópias independentes, atualização e reversão por instalação, revisão de acessos, validação de segurança e operação do servidor. Esta entrega não criou domínio, servidor remoto, regras de firewall públicas ou contas externas.

## Referências

- [Caddy: HTTPS automático e autoridades locais](https://caddyserver.com/docs/automatic-https).
- [Caddy: reverse proxy e cabeçalhos de encaminhamento](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
- [Caddy: opções globais](https://caddyserver.com/docs/caddyfile/options).
- [Caddy 2.11.7: versão oficial](https://github.com/caddyserver/caddy/releases/tag/v2.11.7).
- [Uvicorn: proxies e cabeçalhos encaminhados](https://uvicorn.dev/deployment/).

## Resultado da entrega

**297 testes Python e 40 testes da interface aprovados**, com um aviso de descontinuação Starlette/httpx. O ensaio TLS real passou, incluindo a recriação dos contentores com dados, segredo inicial e CA preservados. Os hashes das tabelas históricas dos portais anteriores coincidiram com os valores recolhidos antes da validação; Aurora manteve 9 serviços, 10 incidentes e 73 entradas na linha temporal, e Atlas manteve 2 serviços e nenhum incidente. Os dois foram atualizados para 0.30.0.

 Não houve commit, push ou publicação externa nesta entrega.
