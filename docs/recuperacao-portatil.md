# Recuperação portátil · v0.11

A cópia `.nexobak` continua cifrada com a chave local. O novo kit permite transportar essa chave, também cifrada, para uma instalação que não tenha a conta Windows nem o ficheiro DPAPI original. A recuperação cria uma base nova; não substitui o laboratório ativo.

## Criar o teu kit no computador de origem

1. Executar **copia-seguranca.cmd** para guardar os dados atuais. O Docker deve estar iniciado.
2. Executar **exportar-chave-portatil.cmd**. A exportação usa a cópia mais recente já existente e mostra qual foi selecionada; não cria uma nova cópia automaticamente.
3. Escolher e confirmar uma **frase-passe própria de 20 a 256 caracteres** no terminal. A entrada fica oculta. Usar uma frase longa e imprevisível, diferente da palavra-passe de acesso ao portal; o mínimo de caracteres não garante resistência a adivinhação.
4. Guardar a pasta de kit indicada, situada em `%LOCALAPPDATA%\Nexo\Kits`. Cada exportação cria uma pasta nova, sem substituir kits anteriores.

O kit contém **copia.nexobak**, **chave.nexokey** e instruções em **LE-ME.txt**. A frase-passe não fica no kit. Guardá-la separadamente, por exemplo num gestor de palavras-passe ou num registo protegido independente do suporte do kit. Transportar os dois ficheiros cifrados por um meio adequado; o programa não faz upload nem envia mensagens.

O código e as dependências da aplicação também são necessários. O kit não contém uma instalação autónoma do portal, imagens Docker ou um ambiente Python. Copiar apenas o `.venv` de outro computador não prepara um ambiente compatível.

Se a frase-passe do kit for esquecida, não há reposição desse segredo. Enquanto o computador de origem e a chave DPAPI estiverem disponíveis, pode exportar-se outro kit com outra frase. Sem um kit previamente exportado e sem acesso ao contexto DPAPI original, as cópias antigas podem continuar irrecuperáveis.

## Recuperar noutro Windows

Preparar o código do projeto e Python 3.12 ou superior. Na pasta do projeto, caso ainda não exista um ambiente local:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Verificar primeiro o kit, introduzindo a frase-passe quando for pedida:

```powershell
.\recuperacao-portatil.ps1 -Acao Verificar -Kit 'D:\kit-nexo'
```

Restaurar numa pasta **que ainda não exista**, dentro da pasta de restauros do utilizador atual:

```powershell
$destinoNexo = Join-Path $env:LOCALAPPDATA 'Nexo\Restauros\recuperado'
.\recuperacao-portatil.ps1 -Acao Restaurar -Kit 'D:\kit-nexo' -Destino $destinoNexo
```

Estas operações não leem nem criam `Keys\backup.dpapi` no computador de destino. A chave portátil é usada em memória e não substitui uma chave local que já exista. As pastas de restauro Windows recebem permissões para o utilizador atual e SYSTEM. Não é preciso Docker para estes comandos de verificação/restauro.

## Recuperar em Linux

Preparar um ambiente virtual compatível e instalar `requirements.txt`. Num terminal interativo:

```bash
python -m app.portable verify --kit /caminho/kit-nexo
mkdir -m 700 "$HOME/nexo-restauros"
python -m app.portable restore --kit /caminho/kit-nexo --destination "$HOME/nexo-restauros/recuperado"
```

A frase é pedida com entrada oculta. O comando recusa um terminal sem essa capacidade, em vez de escrever o segredo com eco. Não existe uma opção de linha de comandos para passar a frase-passe. O caminho pai do destino tem de existir; a pasta final tem de ser nova. Em Unix, a pasta restaurada usa modo 0700 e o ficheiro SQLite 0600.

O protocolo JSON por stdin de `app.portable` mantém-se disponível para os scripts locais. Transporta a frase codificada em Base64 para preservar UTF-8 no Windows PowerShell 5; **Base64 não é cifra**. Esse protocolo é usado apenas entre processos locais de confiança e não deve ser guardado num ficheiro, histórico de comandos ou log.

## O que acontece após o restauro

O resultado é um `nexo.db` novo. Contas, perfis, hashes de palavras-passe, incidentes, histórico e evidências são preservados. As sessões são removidas e as ligações de monitorização ficam pausadas. O restauro fica registado na auditoria.

Antes de colocar essa base em serviço, rever a configuração, as contas, os endereços autorizados e as políticas. A promoção para um volume ativo continua a exigir manutenção explícita. O comando não altera `DATABASE_PATH`, não configura certificados e não publica serviços.

A chave do kit protege a mesma chave usada pelas cópias locais dessa instalação. Por isso, um kit também pode permitir abrir outras cópias cifradas sob essa chave. Exportar novamente com outra frase-passe **não revoga os kits anteriores**. Rotação da chave dos dados e recifragem de cópias antigas não fazem parte desta entrega.

## Formato e proteção

O ficheiro `chave.nexokey` tem 84 bytes: identificador `NEXOKEY1`, salt aleatório de 16 bytes, nonce aleatório de 12 bytes e chave de dados de 32 bytes cifrada com tag de autenticação de 16 bytes. Usa AES-256-GCM e uma chave derivada da frase-passe com scrypt (`N=131072`, `r=8`, `p=1`, saída de 32 bytes). O custo de memória da derivação é aproximadamente 128 MiB, além do processo e dos dados. O suporte depende da biblioteca `cryptography` compatível.

Os parâmetros são fixos para esta versão de formato e associados à autenticação; um ficheiro alterado não pode pedir valores de custo arbitrários. Salt/nonce são novos em cada exportação. A biblioteca criptográfica implementa os algoritmos; o projeto apenas define o formato e o fluxo.

São rejeitados ficheiros alterados, frase incorreta, chaves de outro arquivo, tamanhos excessivos, links/junctions e destinos existentes. Antes de publicar um kit final, o exportador verifica a cópia, volta a decifrar a chave e confirma os ficheiros gravados. Uma falha pode deixar uma pasta `.partial`, que não é anunciada como kit concluído.

O arquivo de dados mantém o formato anterior, incluindo manifesto autenticado, hashes, verificação de esquema, contagens, integridade e referências. Não foram alteradas a chave DPAPI nem as cópias existentes. O limite continua a ser 32 MiB de base de dados. Esquemas incompatíveis exigem migração própria.

A cifra não impede tentativas offline de adivinhar a frase. Também não protege contra alguém que controle a sessão do utilizador, leia a memória dos processos ou obtenha os ficheiros e a frase. As referências ao segredo são libertadas e os buffers mutáveis são limpos quando possível; isso não é uma garantia de apagamento de toda a memória. A base restaurada é um SQLite sem cifra própria, sujeito às proteções do dispositivo.

## Validação realizada

- Testes automatizados de transporte da chave, aleatoriedade, Unicode, frase errada, alteração de cada região do formato, tamanho, par de ficheiros errado, erros sem ecoar segredos, restauração e uso interativo sem fallback com eco.
- Scripts completos no **Windows PowerShell 5.1 e PowerShell 7.6**, com chaves e dados fictícios: exportação, verificação e restauro; outro diretório de perfil sem DPAPI; frase com caracteres Unicode; recusa de frase errada e de substituição de uma base existente. A chave local da fixture permaneceu intacta.
- Uma cópia real do laboratório foi recuperada num **contentor Linux sem rede, sem montagem dos ficheiros originais, sem DPAPI e sem privilégios adicionais**. Preservou nove incidentes, sessenta entradas de histórico e os registos de onze tabelas comparadas por hash. A aplicação arrancou sobre a base recuperada e passou login, consulta e pesquisa. A chave Windows de origem permaneceu inalterada.

O teste Linux correu no mesmo computador físico através do Docker, não num segundo computador físico. A duração registada em `validacao-portatil-linux.json` cobre o restauro e a verificação da aplicação após decifrar a chave; não é um RTO completo. O ensaio utilizou uma frase aleatória temporária, apenas em memória, e **não guardou um kit dos dados reais** com esse segredo. Para criar um kit pessoal utilizável, executar o exportador e escolher a própria frase no terminal.

Evidências: `validacao-kit-windows.json`, `validacao-kit-powershell7.json` e `validacao-portatil-linux.json`. As fixtures Windows são sintéticas e ficam na pasta de ensaios local, fora do OneDrive. O contentor Linux temporário é removido no fim. Não se testaram perda real de hardware, todas as versões de sistema operativo, capacidade no limite máximo, restauro dos volumes completos de Prometheus/Loki ou promoção automática para produção.

Fontes: [scrypt e derivação de chaves em cryptography](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/#scrypt) e [parâmetros de custo OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#scrypt). A utilização desses parâmetros não constitui certificação do projeto.

Suite final: **141 testes aprovados** em 182,25 segundos, com um aviso de descontinuação do adaptador httpx/Starlette. O laboratório foi atualizado para a v0.11.0 após criar uma cópia cifrada.
