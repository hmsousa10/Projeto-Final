# Promoção e reversão por instalação · versão 0.29 local

O procedimento de manutenção passa a aceitar `-Instancia atlas`, selecionando exclusivamente o projeto `nexo-test-atlas`, o volume da Atlas, a sua chave DPAPI e a sua pasta de registos. O laboratório principal continua a usar os comandos anteriores, sem este parâmetro. Não existe uma rota HTTP para trocar bases.

## Preparar

Com o Docker Desktop iniciado e a instalação de ensaio já existente:

```powershell
.\manutencao.ps1 -Acao Estado -Instancia atlas
.\manutencao.ps1 -Acao Preparar -Instancia atlas
```

Sem `-Arquivo`, a preparação cria uma cópia cifrada nova da Atlas e seleciona esse arquivo. Pode usar-se `-Arquivo 'C:\caminho\nexo-atlas.nexobak'` para uma cópia escolhida. O script valida o perfil, o projeto, o serviço, o volume e a identidade configurada do contentor.

O processo auxiliar usa a mesma imagem do Nexo, sem rede, sem capacidades adicionais, com sistema de ficheiros de raiz apenas para leitura e apenas o volume selecionado montado. Recebe a chave e o arquivo pela entrada padrão. A cópia deve conter a identidade da Atlas tanto no manifesto cifrado como na própria base.

A candidata fica numa pasta própria de uma geração de manutenção. As sessões são removidas e a monitorização é pausada. A base ativa ainda não é substituída nesta fase. O diário regista a empresa, a geração, o hash da candidata e resumos do histórico. A ferramenta recusa usar um diário de outra empresa ou abrir um diário dedicado sem indicar a empresa correspondente.

## Promover e confirmar

```powershell
.\manutencao.ps1 -Acao Promover -Instancia atlas
.\manutencao.ps1 -Acao Concluir -Instancia atlas
```

A promoção para apenas o contentor Nexo da Atlas. O auxiliar confirma que a base deixou de estar em uso, faz checkpoint dos ficheiros transitórios SQLite e guarda um ponto de retorno antes de instalar a candidata. Depois, o script inicia o Nexo e verifica a resposta de saúde, as tabelas históricas e o registo de auditoria da geração.

O bloqueio de escritas da aplicação fica ativo durante a verificação. Se a troca for interrompida numa fase pendente, o arranque é recusado. Só uma promoção verificada pode ser concluída. Mesmo após `Concluir`, o ponto de retorno desta geração continua disponível; não é apagado automaticamente.

A verificação compara hashes das tabelas históricas definidas pelo mecanismo de manutenção, incluindo contas, serviços, dependências, incidentes, linha temporal, evidências e regras. Não é uma comparação binária de toda a base: sessões, auditoria, observações contínuas e definições operacionais têm alterações previstas.

## Reverter

```powershell
.\manutencao.ps1 -Acao Reverter -Instancia atlas
```

O script volta a parar o Nexo da Atlas e reinstala o ponto de retorno. Antes disso, preserva também uma cópia da base que vai retirar, para não descartar silenciosamente escritas feitas após a promoção. Isso conserva os dados para inspeção, mas não os funde automaticamente no estado anterior.

As sessões antigas são revogadas. Na reversão dedicada, a monitorização HTTP e empresarial fica pausada e o estado transitório dos alertas é limpo. A API empresarial deve ser retomada explicitamente na página **Integração empresarial**, após rever a ligação e as regras. `Retomar` no script não é um atalho para ativar essa API.

Uma promoção que falhe depois de parar o portal provoca uma tentativa automática de reversão. O relatório distingue o erro inicial do resultado da recuperação. Uma falha não deixa de ser uma falha só porque o portal voltou a responder: deve consultar-se o estado e o relatório antes de repetir. Não forçar o arranque se o estado ficar pendente.

## Ensaiar uma falha de verificação

Apenas numa instalação local de ensaio:

```powershell
.\manutencao.ps1 -Acao Preparar -Instancia atlas
.\manutencao.ps1 -Acao Promover -Instancia atlas -SimularFalha
```

A simulação provoca um erro depois de a candidata arrancar, para exercitar a reversão automática. O comando termina com erro, como esperado, e o relatório deve confirmar a reposição do ponto anterior e o arranque. Esta opção é recusada no laboratório principal sem selecionar um modo de ensaio. Não pode combinar-se `-Instancia` com o ensaio fixo `-Ensaio`.

## Registos e limites

Os relatórios Windows ficam em `%LOCALAPPDATA%\Nexo\Installations\atlas\Manutencao`. O diário durável, a candidata, o ponto de retorno e a base preservada antes da reversão ficam na pasta `maintenance` do volume da Atlas. Estes ficheiros SQLite do volume contêm dados em claro; não se devem confundir com os arquivos cifrados `.nexobak`.

A operação implica uma interrupção do portal selecionado e invalida as suas sessões. Uma promoção repõe também as contas, palavras-passe e perfis ao instante do arquivo; num ambiente real, os acessos devem ser revistos antes de reabrir o serviço. Deve usar-se uma janela de manutenção e verificar se o ponto temporal do arquivo é o pretendido. O limite da base continua a ser 32 MiB. A proteção do anfitrião, a retenção dos pontos e as cópias independentes continuam necessárias.

Este procedimento foi preparado para as instalações fictícias locais. Não configura domínio, HTTPS, alta disponibilidade, restauro distribuído ou operação comercial. O próximo bloco é preparar uma configuração de pré-produção com HTTPS, mantendo estes mecanismos de recuperação.

## Ensaio real da Atlas

Foi preparada uma cópia nova da Atlas, promovida, verificada e concluída, seguida de reversão. Numa segunda geração, foi provocada uma falha de verificação depois do arranque da candidata. O comando terminou com erro intencional e conservou esse resultado; o relatório confirmou reversão automática, saúde do portal e correspondência do histórico.

Os hashes das tabelas históricas da Aurora e da Atlas coincidiram com os valores recolhidos antes dos dois percursos. A Aurora manteve 9 serviços, 10 incidentes e 73 entradas na linha temporal; a Atlas manteve 2 serviços e nenhum incidente. As sessões antigas da Atlas foram revogadas, como previsto. Foram conservados dois pontos de retorno e duas cópias anteriores à reversão.

Após verificar o estado recuperado, a recolha empresarial da Atlas foi retomada explicitamente através da API autenticada e foi confirmada uma nova amostra válida. O ensaio não provocou uma falha no serviço empresarial nem criou incidentes fictícios. Consultar [a validação de execução](validacao-manutencao-instalacoes-runtime.json).

## Validação final

**292 testes Python e 39 testes da interface aprovados**, com um aviso de descontinuação Starlette/httpx. Os scripts passaram a análise de sintaxe PowerShell. Os dois portais respondem com a versão 0.29.0. A única operação de ensaio com estado `failed` é a falha provocada: o registo conserva esse resultado e confirma a reversão automática. [Registo final e hashes](validacao-manutencao-instalacoes.json). Não foi feito commit nem push.
