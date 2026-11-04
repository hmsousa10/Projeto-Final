# Instalações isoladas · versão 0.27 local

A Atlas é uma segunda empresa fictícia para ensaiar instalações dedicadas. Usa o mesmo código e a mesma imagem Nexo da Aurora, com outra base de dados, credenciais, redes e porta. Não representa um cliente real nem uma instalação pública pronta para vender.

## Arrancar sem configurar manualmente o Docker

1. Abrir o Docker Desktop e aguardar o motor.
2. Executar `iniciar-cliente-ensaio.cmd` na pasta do projeto. O comando usa o Python da `.venv`, constrói a imagem e aguarda os serviços saudáveis.
3. Abrir `http://localhost:8003`. Usar a conta `admin@atlas.test` e consultar a palavra-passe inicial no ficheiro `data/installations/atlas/initial-admin.key`. Não publicar esse ficheiro nem enviá-lo para o GitHub.
4. Em Integração empresarial, confirmar a identidade Atlas, os totais fictícios e a recolha automática.

A primeira preparação gera dois segredos diferentes: acesso inicial do administrador e leitura da API. Repetir o arranque mantém os segredos e a base; não cria contas novas nem redefine palavras-passe. O ficheiro inicial deixa de representar a palavra-passe atual se esta for alterada dentro do portal.

A pasta `data` e os ficheiros `.key` são ignorados pelo Git. No Windows, os ficheiros herdam as permissões da pasta do utilizador; não são ficheiros cifrados. A proteção do anfitrião, das cópias e de eventuais sincronizações de pastas continua necessária. O Docker Compose monta-os apenas para leitura, como segredos de ficheiro; isto não é um cofre de segredos de produção.

## Gestão pelo terminal

Na raiz do repositório:

```powershell
.venv\Scripts\python.exe scripts/customer_installation.py estado
.venv\Scripts\python.exe scripts/customer_installation.py parar
.venv\Scripts\python.exe scripts/customer_installation.py iniciar
.venv\Scripts\python.exe scripts/customer_installation.py recriar
```

`parar` mantém contentores, volumes e histórico. `recriar` substitui os dois contentores da Atlas mantendo o volume. O script não inclui uma operação de eliminação de dados. Não usar comandos `down -v` se for necessário conservar o ensaio.

Outra instalação de ensaio pode ser criada com `iniciar --instancia boreal --porta 8004 --build`. Cada identificador origina um projeto `nexo-test-<identificador>`, uma pasta de segredos e volumes próprios. As portas permitidas são 8003 a 8999, protegendo as portas dos laboratórios principais. Perfis existentes não mudam de porta silenciosamente e um segredo perdido não é regenerado automaticamente. A preparação não importa bases de outro cliente.

O perfil `data/installations/<identificador>/profile.json` contém apenas identidade, email e porta. O script valida estes campos e passa argumentos ao Docker diretamente, sem construir comandos para uma shell. O ficheiro Compose exige as variáveis do perfil; não deve ser executado diretamente com valores improvisados.

## O que está separado

O projeto principal `nexo-lab` mantém o seu volume e as redes existentes. A Atlas usa `nexo-test-atlas_customer-data`, uma rede privada interna e uma rede de acesso ao portal. Só a porta do Nexo é publicada, em `127.0.0.1:8003`. A API empresarial não tem porta publicada no anfitrião e só está ligada à rede privada do ensaio.

A Atlas arranca com `DEMO_MODE=0` e `LAB_MODE=0`: tem um administrador próprio e o serviço criado pela integração empresarial. Não recebe contas, incidentes nem inventário semeados da Aurora. A API de referência continua a fornecer encomendas fictícias, explicitamente identificadas como laboratório. O endpoint de controlo de falhas e o portal comercial da Aurora não são disponibilizados por esta API privada.

A palavra-passe inicial pode agora ser lida de `INITIAL_ADMIN_PASSWORD_FILE`. O mecanismo antigo por `INITIAL_ADMIN_PASSWORD` permanece compatível; configurar ambos para a criação da conta inicial é rejeitado. A leitura do ficheiro preserva espaços. Reiniciar com uma base já inicializada não altera a palavra-passe guardada.

Para consultar as duas instalações no mesmo navegador, usar **Aurora em `http://127.0.0.1:8001`** e **Atlas em `http://localhost:8003`**. As cookies não são isoladas por porta: usar o mesmo nome de anfitrião nas duas pode substituir a cookie de sessão e obrigar a entrar novamente. A verificação do servidor continua a recusar uma sessão da outra base; o uso dos dois nomes evita essa interferência no ensaio. Em produção, cada instalação deverá ter o seu domínio HTTPS.

## Repetir a verificação

Com a Aurora e a Atlas ativas na mesma imagem:

```powershell
.venv\Scripts\python.exe scripts/validar-instalacoes.py
```

O ensaio verifica as identidades, a recusa de sessões cruzadas nos dois sentidos, a ausência de contas de demonstração na Atlas, a API sem porta publicada, as redes e volumes independentes e os segredos montados apenas para leitura. Cria um serviço identificado como ensaio **apenas na Atlas**, recria os seus contentores e confirma a persistência. O registo permanece para permitir demonstração visual; repetir o ensaio reutiliza-o. Não injeta falhas nem altera serviços ou incidentes na Aurora. A autenticação de verificação acrescenta os registos normais de auditoria de acesso.

O resultado fica em validação de execução. Estes testes verificam a configuração e os percursos descritos; não constituem um teste de intrusão nem certificação de isolamento contra comprometimento do anfitrião.

## Limites e próximo bloco

Este Compose destina-se apenas ao ensaio local e usa HTTP em loopback. Não inclui domínio, certificados, proxy HTTPS, um gestor de segredos, recuperação operacional por cliente, serviços semânticos dedicados ou uma política de atualização e reversão em produção. Na Atlas, a pesquisa usa o modo textual disponível; não herda o serviço semântico nem o histórico de conhecimento da Aurora.

O passo seguinte é preparar a configuração de um servidor de pré-produção com HTTPS e um procedimento de cópia, atualização e recuperação por instalação, validando-os antes de um piloto autorizado numa empresa real. Não publicar este Compose de ensaio na Internet.

## Resultado desta entrega

A suite geral terminou com **277 testes Python aprovados** e um aviso de descontinuação Starlette/httpx. Os **39 testes da interface** passaram. O ensaio Docker confirmou a mesma imagem, recusa de sessões cruzadas, redes e volumes separados, segredos montados apenas para leitura e persistência após recriação. A Aurora manteve 9 serviços, 10 incidentes e 73 entradas na linha temporal. A Atlas ficou com a API monitorizada e o serviço identificado de ensaio, sem incidentes.

A interface foi verificada no navegador, com recolha ativa, texto da empresa corrigido e sem erros/avisos de consola. Registo da validação e captura da Atlas.
