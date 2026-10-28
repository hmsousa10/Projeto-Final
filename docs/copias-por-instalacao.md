# Cópias por instalação · versão 0.28 local

As instalações dedicadas de ensaio passam a ter cópias e chaves próprias. A Atlas usa `%LOCALAPPDATA%\Nexo\Installations\atlas`, fora do repositório. O laboratório principal mantém os caminhos e comandos anteriores, sem `-Instancia`.

## Criar uma cópia da Atlas

Abrir o Docker Desktop e executar **`copia-cliente-ensaio.cmd`**. O atalho chama:

```powershell
.\copia-seguranca.ps1 -Acao Criar -Instancia atlas
```

O comando exige o perfil já existente e verifica o projeto, serviço, identidade, caminho da base e nome do volume antes de consultar o contentor. Não cria outra instalação nem troca de base. A base lida é `/app/data/nexo.db` no contentor identificado da Atlas.

O snapshot usa a API de cópia SQLite, incluindo dados confirmados em WAL. Verifica esquema, integridade e referências; retira as sessões da cópia e cifra o conteúdo com AES-256-GCM. O limite herdado desta entrega é **32 MiB por base**. Dados maiores são recusados; não se trunca a cópia.

A chave aleatória de 32 bytes fica em `Keys/backup.dpapi`, protegida por DPAPI no contexto do utilizador Windows atual. `Backups/` contém os arquivos `.nexobak`, com nomes únicos. As pastas recebem permissões restritas para o utilizador e SYSTEM. O comando não mostra a chave, não a passa na linha de comandos e não a monta na aplicação; envia-a ao processo de cópia por entrada padrão.

A gravação começa num ficheiro `.partial`. Só depois da verificação criptográfica, da integridade e do hash gravado o ficheiro recebe o nome final. Não se substituem cópias existentes nem se gera uma nova chave quando há arquivos existentes e a chave original desapareceu.

## Identidade dentro da cópia

O manifesto cifrado passa a conter `installation_id`, validado também contra a ligação empresarial da própria base. A ferramenta por instalação exige que ambos correspondam ao identificador pedido. Renomear o arquivo não muda esta identidade. Uma chave errada, outra identidade ou um arquivo alterado são recusados.

As cópias genéricas antigas continuam válidas nos comandos anteriores. Um arquivo antigo sem identidade explícita não é aceite silenciosamente pela recuperação dedicada com `-Instancia`. Deve manter-se o percurso original ou preparar-se uma migração explícita.

Esta proteção reduz trocas operacionais entre instalações; não impede um administrador que já controla o anfitrião, as bases e as chaves de modificar esses elementos.

## Verificar e restaurar sem substituir o portal

Selecionar o caminho do arquivo apresentado na criação:

```powershell
.\copia-seguranca.ps1 -Acao Verificar -Instancia atlas -Arquivo 'C:\caminho\nexo-atlas.nexobak'

$destinoAtlas = Join-Path $env:LOCALAPPDATA 'Nexo\Installations\atlas\Restauros\ensaio-novo'
.\copia-seguranca.ps1 -Acao Restaurar -Instancia atlas -Arquivo 'C:\caminho\nexo-atlas.nexobak' -Destino $destinoAtlas
```

O destino deve ser uma pasta nova dentro de `Restauros` da instalação. O comando recusa pastas existentes, destinos fora dessa raiz e ligações simbólicas/junctions. Cria `nexo.db` separado e não altera o volume ativo.

A base restaurada conserva contas e histórico, mas não sessões válidas. As sondagens e a recolha empresarial ficam pausadas; o estado transitório dos alertas é removido. A monitorização exige revisão e retoma explícitas. A restauração não demonstra, por si só, que uma troca da base em produção foi concluída.

## Recuperar sem o contexto DPAPI original

Uma chave DPAPI isolada não resolve a perda do computador ou da conta Windows. Antes desse cenário, exportar um kit protegido por uma frase-passe escolhida pelo utilizador:

```powershell
.\recuperacao-portatil.ps1 -Acao Exportar -Instancia atlas
```

O script escolhe a cópia mais recente da Atlas, mostra o caminho e pede uma frase-passe em entrada oculta, com confirmação. Os kits ficam em `Installations/atlas/Kits`. Incluem o arquivo e a chave cifrada por scrypt e AES-GCM, além de instruções com o identificador da instalação. Guardar a frase separadamente e manter uma cópia do kit num suporte independente; estas ferramentas não fazem upload ou replicação externa.

Num Windows preparado com o código e dependências compatíveis:

```powershell
.\recuperacao-portatil.ps1 -Acao Verificar -Instancia atlas -Kit 'D:\kit-atlas'
.\recuperacao-portatil.ps1 -Acao Restaurar -Instancia atlas -Kit 'D:\kit-atlas' -Destino $destinoAtlas
```

Estes dois comandos não exigem o perfil local nem a chave DPAPI antigos. Exigem o kit, a frase correta, o identificador correspondente e um destino novo. Em Linux, o CLI Python aceita também `--company atlas`, mantendo as regras do [guia de recuperação portátil](recuperacao-portatil.md).

O kit não contém a imagem Docker, a configuração de implantação ou as chaves de leitura da API empresarial. Estes elementos precisam de procedimentos próprios de conservação e rotação. Uma cópia cifrada guardada apenas no mesmo disco não protege contra a perda desse disco.

## Ensaio realizado

Foi criada e verificada uma cópia real da Atlas pelo script Windows e efetuado um restauro isolado. A base recuperada manteve os dois serviços e o registo identificado do ensaio anterior, com zero sessões e recolha empresarial pausada. Foi também iniciada através do TestClient ASGI, com autenticação da conta existente, consulta dos serviços e saída da sessão de verificação; terminou novamente sem sessões. Este teste não publicou a base recuperada numa porta de rede. Aurora e Atlas mantiveram as contagens de serviços, incidentes, linha temporal e sessões durante a verificação e o restauro. A referência dessas contagens foi recolhida após a criação do arquivo.

A exportação portátil por empresa foi testada com chaves, bases e frases descartáveis. Não foi escolhido nem criado um kit real da Atlas com uma frase-passe conhecida pelo assistente. O percurso interativo Windows do kit por cliente foi analisado e a sintaxe validada; a exportação interativa completa continua a exigir uma frase escolhida pelo utilizador.

Resultados detalhados em [validação de execução](validacao-copias-instalacoes-runtime.json). Os testes verificam identidade no manifesto e na base, rejeição de outra empresa/chave, restauro sem sobrescrita, sessões revogadas, monitorização pausada e compatibilidade das cópias anteriores.

## Limites e próximo passo

Continuam pendentes agendamento, retenção automática, armazenamento independente, cópias da configuração/segredos, ensaio operacional de promoção da base por cliente e publicação com HTTPS. Nesta entrega, a recuperação cria uma base nova para inspeção; não automatiza a substituição de uma instalação ativa.

## Validação final

**287 testes Python e 39 testes da interface aprovados.** Um aviso de descontinuação Starlette/httpx permanece. Os scripts PowerShell passaram a análise de sintaxe e o percurso de criação/verificação/restauro da Atlas foi executado no Windows. Os dois portais respondem com a versão 0.28.0. Consultar [o registo final e hashes](validacao-copias-instalacoes.json). Não foi feito commit nem push nesta entrega.
