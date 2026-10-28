# API empresarial HTTPS · versão 0.31 local

O ambiente `nexo-preproduction` passa a incluir uma API empresarial fictícia da Aurora, acessível pelo Nexo através de HTTPS. A ligação valida o certificado, o nome `enterprise-api`, a identidade empresarial, o contrato dos dados e a chave Bearer. Os dados continuam de laboratório; o transporte, a autenticação e a recolha automática são reais.

## O que muda nos três grupos Docker

- `nexo-lab`: demonstração principal com Nexo, portal Aurora, monitorização HTTP, logs e serviço semântico. Mantém os endereços anteriores 8001/8002.
- `nexo-test-atlas`: segunda instalação com base e credenciais próprias, utilizada nos ensaios de cópia e manutenção. Mantém o endereço 8003.
- `nexo-preproduction`: Nexo em modo de produção, Caddy para a entrada HTTPS e agora `enterprise-api`, uma API privada de referência também com TLS.

Não existe uma porta publicada para `enterprise-api`. Só o Nexo e a API partilham a rede empresarial interna. O proxy de entrada fica fora dessa rede. O backend Nexo recebe apenas o certificado público da CA empresarial e o token de leitura; a chave privada do servidor TLS é montada apenas na API, em modo de leitura.

## Arranque e verificação

```powershell
.venv\Scripts\python.exe scripts/preproduction.py iniciar --build
.venv\Scripts\python.exe scripts/validar-api-https.py
```

O atalho `iniciar-preproducao.cmd` continua disponível. A preparação atualiza um ambiente 0.30 existente acrescentando um conjunto de ficheiros próprios para a API, preservando o administrador, a base e a CA do Caddy. Se um conjunto TLS já existir mas estiver incompleto, é recusado; não se recriam silenciosamente as chaves em falta.

O comando de validação repete os testes da entrada HTTPS e verifica a API autenticada, a CA adicional por integração, a rejeição de outra CA e de um nome incorreto, a recusa de uma chave Bearer errada, a recolha automática e as observações persistidas. As consultas negativas do ensaio são independentes do coletor; não introduzem observações falsas nem incidentes.

O serviço da API é criado no inventário pela ligação empresarial, reutilizando o mecanismo de regras e incidentes existente. As consultas automáticas usam o mesmo cliente HTTPS que as consultas autenticadas da interface. Uma falha de TLS conta como falha técnica da integração; não demonstra a indisponibilidade de toda a empresa.

## Configuração do cliente

`ENTERPRISE_API_CA_FILE` é opcional e exclusivo de uma API HTTPS configurada. O certificado indicado é acrescentado ao contexto SSL **deste cliente**, mantendo as raízes do sistema e a verificação de nomes. Não se altera `SSL_CERT_FILE`, não se substitui a política global de TLS e não se instala uma autoridade no Windows.

Uma API com certificado público normalmente não precisa desta opção: usa a confiança padrão do sistema. Uma API privada com uma CA própria exige um ficheiro de confiança escolhido pelo responsável pela implantação. A opção não é recebida pelo navegador nem é um mecanismo para aceitar certificados arbitrários enviados por utilizadores.

São recusadas configurações com CA mas sem API, com CA e URL HTTP, ou com um ficheiro de CA inválido. As falhas de transporte não devolvem tokens, corpos de erro do fornecedor ou detalhes internos ao navegador. Redirecionamentos continuam bloqueados.

## Certificados de ensaio

Os ficheiros ficam em `data/preproduction/enterprise-tls`, ignorados pelo Git:

- `ca.crt`: certificado público da autoridade exclusiva da API de ensaio.
- `server.crt`: certificado do servidor com SAN `enterprise-api`, uso de autenticação de servidor e validade de 90 dias.
- `server.key`: chave privada do servidor.
- `read.key`: token de leitura, diferente do administrador e dos outros ambientes.

A chave de assinatura da CA é gerada apenas em memória e não é gravada pelo gerador. O conjunto é de laboratório: não há renovação automática destes certificados. Uma expiração ou substituição exige uma operação explícita de renovação/rotação e revisão da confiança. Não se deve usar este gerador como infraestrutura de certificados de uma empresa real.

A validação local verifica cadeia, nome, validade e correspondência da chave do servidor. No Windows, estes ficheiros herdam as permissões da pasta do utilizador; não são um cofre de segredos. As chaves e as políticas devem ser protegidas também nas cópias do anfitrião e em eventuais sincronizações de pastas.

A CA da API é diferente da CA do Caddy usada no acesso ao portal. O ensaio confirmou que apresentar a CA do portal como se fosse a da API não faz a ligação ser aceite. Continua a não ser necessário instalar qualquer uma no Windows para executar os testes.

## Limites

Ainda se trata da Aurora fictícia. Não houve acesso a uma empresa real, publicação externa, emissão de certificado público ou alteração da confiança do navegador. O endereço HTTPS do portal pode continuar a apresentar um aviso num navegador que não confie na CA local; os testes usam confiança explícita e verificação de nome, sem contornar avisos.

A API de referência não inclui controlos de falha nem portal comercial. Os certificados e a chave de leitura não fazem parte das cópias da base SQLite: precisam de procedimentos próprios de conservação e rotação. A topologia é um ensaio local de três serviços; uma API empresarial real pode estar noutro servidor e exigir outra autenticação ou contrato. O Nexo deste ensaio só está ligado a redes internas: para uma API externa será também necessária uma rota ou política de saída de rede autorizada.

Consultar também [pré-produção HTTPS](preproducao-https.md), [conectores](conectores-empresariais.md), [alertas da API](alertas-api-empresarial.md) e [validação de execução](validacao-api-https-runtime.json).

## Resultado desta entrega

**306 testes Python e 40 testes da interface aprovados**, com um aviso de descontinuação Starlette/httpx. O ensaio real confirmou a API privada HTTPS, as recusas de CA/nome/token indevidos e a recolha automática com observações persistidas. Após recriação, o mesmo serviço e os ficheiros TLS/token mantiveram-se válidos. O serviço empresarial passou a existir apenas no inventário da pré-produção; os históricos anteriores da Aurora e da Atlas mantiveram os mesmos hashes nas tabelas verificadas.

[Registo final e hashes](validacao-api-https.json). Nenhum commit, push ou publicação externa foi realizado.
