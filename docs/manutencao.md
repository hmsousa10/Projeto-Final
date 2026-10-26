# Promoção controlada e reversão · v0.13

O restauro isolado pode agora ser promovido para o portal através de um procedimento local. A base ativa continua a chamar-se `/app/data/nexo.db`, no mesmo volume: os comandos de arranque e de cópia existentes continuam a usar o caminho correto. Não existe endpoint HTTP de substituição da base.

## Utilização no laboratório habitual

Executar na pasta do projeto, com Docker Desktop e a imagem atualizados:

```powershell
# Consultar sem trocar a base.
powershell -ExecutionPolicy Bypass -File .\manutencao.ps1 -Acao Estado

# Criar uma copia cifrada atual e preparar uma base candidata.
powershell -ExecutionPolicy Bypass -File .\manutencao.ps1 -Acao Preparar

# Parar o portal, guardar retorno, trocar, iniciar e verificar.
powershell -ExecutionPolicy Bypass -File .\manutencao.ps1 -Acao Promover

# Depois de consultar contas, historico e configuracao recuperados:
powershell -ExecutionPolicy Bypass -File .\manutencao.ps1 -Acao Retomar

# Confirmar a geracao e permitir preparar outra, conservando os ficheiros.
powershell -ExecutionPolicy Bypass -File .\manutencao.ps1 -Acao Concluir
```

Para usar uma cópia específica, acrescentar `-Arquivo 'C:\caminho\copia.nexobak'` a **Preparar**. Este comando usa a chave DPAPI atual; um kit portátil deve primeiro ser recuperado através do procedimento próprio. Uma cópia antiga volta ao estado antigo: os dados posteriores não são fundidos automaticamente.

**Promover** e **Reverter** interrompem temporariamente o portal. Coordenar uma janela de manutenção e terminar o trabalho em curso antes da operação. São comandos do administrador local do computador, que já controla o Docker, e não permissões adicionais atribuídas a um perfil do portal.

Para voltar à base anterior:

```powershell
powershell -ExecutionPolicy Bypass -File .\manutencao.ps1 -Acao Reverter
```

Se só existir uma preparação, **Reverter** cancela-a sem substituir a base ativa. Após uma promoção, repõe o ponto guardado imediatamente antes da troca. As sessões desse ponto são revogadas: é necessário voltar a iniciar sessão. Alterações feitas entretanto na base promovida não são fundidas no estado anterior; antes de a substituir, é guardado um snapshot `before-rollback-…db` para recuperação posterior.

## Verificações antes e depois da troca

1. Confirmar o projeto Docker, o serviço, a imagem efetiva, o volume e o caminho esperado. Não são aceites volumes arbitrários fornecidos pela linha de comandos.
2. Preparar uma pasta nova e privada dentro do volume, verificar a cópia AES-GCM e o esquema, revogar sessões e pausar todas as ligações na candidata. O portal atual continua a funcionar durante esta preparação.
3. Parar o contentor Nexo e confirmar que deixou de estar ativo. O helper usa rede desativada, sistema apenas de leitura fora do volume, utilizador sem privilégios, limites de CPU/memória e ausência de socket Docker montado.
4. Fazer checkpoint do SQLite e mudar para modo de journal DELETE; recusar uma ligação que ainda impeça o acesso exclusivo ou a existência de ficheiros transitórios. Criar uma base de retorno consistente, sem sessões, com auditoria e hash. O conteúdo de onze tabelas históricas é registado por hash.
5. Escrever o diário de manutenção antes da troca, instalar uma cópia por substituição atómica no mesmo volume e sincronizar ficheiro e diretório. A candidata e o ponto de retorno permanecem guardados.
6. Iniciar o portal, verificar `/api/health`, integridade, referências e os hashes das onze tabelas históricas. Até esta verificação terminar, os pedidos de alteração são recusados com **503**. Login e logout continuam possíveis para diagnóstico.
7. Libertar as alterações apenas após a verificação. A monitorização permanece pausada até **Retomar**.

Se o arranque ou a verificação falhar, o script tenta parar o portal, repor o ponto anterior e verificar o novo arranque e o histórico. O comando original termina com erro e o relatório regista a reversão; uma reversão bem-sucedida não transforma a promoção falhada num sucesso.

Um diário `prepared`, `switching` ou `rolling_back` encontrado no arranque bloqueia o servidor antes da inicialização e dos workers. Isto evita arrancar normalmente após uma interrupção a meio da operação. Consultar **Estado** e executar **Reverter**. Se a própria reversão não ficar confirmada, o script apresenta esse resultado explicitamente; não há garantia de recuperação perante falha do disco ou corrupção que impeça as verificações SQLite.

## Retomar sem reativar ligações indevidas

É guardada a lista de ligações que estavam ativas no arquivo original, antes de o restauro as pausar. **Retomar** só volta a ativar essas ligações, preservando as que já estavam pausadas. Os endereços têm de continuar iguais e autorizados pela política efetiva do contentor atual; caso contrário, toda a retoma é recusada na mesma transação. Não são introduzidas URLs novas pelo comando.

As ligações retomadas recebem um novo `updated_at` e perdem apenas o estado transitório de alerta correspondente. Precisam de novas sondagens: dados antigos não confirmam recuperação nem uma nova falha. O comando repetido não limpa novamente o estado das ligações já ativas. A retoma também é auditada.

## Ficheiros e limites

- Relatórios locais: `%LOCALAPPDATA%\Nexo\Manutencao`, com permissões para o utilizador e SYSTEM. Não contêm a chave, o arquivo cifrado ou palavras-passe.
- Dados da operação: `/app/data/maintenance/GERACAO`, no volume Docker. Incluem candidata, retorno, snapshots anteriores à reversão e diário. São bases SQLite sem cifra própria, com permissões restritas, tal como a base ativa. Não são eliminados automaticamente.
- O estado corrente está em `/app/data/maintenance/state.json`. **Concluir** permite preparar outra geração; os ficheiros anteriores continuam guardados, mas o comando local atua sobre a geração corrente.
- As cópias `.nexobak` habituais continuam a copiar a base ativa e os dados nela contidos; não incluem estas pastas auxiliares nem todo o volume Docker. Guardar uma cópia cifrada após validar uma promoção.
- A manutenção tem limite de 32 MiB por base. Não inclui migrações entre esquemas incompatíveis, restauro dos volumes Prometheus/Loki ou comutação sem interrupção.

O bloqueio do helper impede duas operações locais simultâneas. O procedimento pressupõe que nenhum outro administrador inicia outro processo de escrita sobre o volume durante a manutenção. O acesso exclusivo SQLite verifica ligações presentes no momento da preparação, mas não substitui controlo administrativo do Docker. Durabilidade depende também do armazenamento e do cumprimento de `fsync` pela plataforma; não é uma certificação de recuperação de desastre.

## Ensaio isolado

```powershell
powershell -ExecutionPolicy Bypass -File .\validar-manutencao.ps1
```

O projeto **nexo-maintenance-test** usa um volume próprio e a porta local **8013**. O ensaio cria uma cópia cifrada atual do portal habitual, promove-a sobre uma base sintética distinguível, verifica login, incidentes, linha temporal e post-mortems via HTTP, retoma as ligações aprovadas e reverte. Depois provoca deliberadamente uma falha de verificação para confirmar a reversão automática. O controlo `-SimularFalha` só é aceite com `-Ensaio` e ação **Promover**.

Contentores e rede são removidos no fim; o volume de teste fica conservado com os pontos de retorno. Uma nova execução recusa reutilizá-lo implicitamente. A opção `-RetomarEnsaioInicial` só permite continuar uma instalação inicial sem qualquer preparação de manutenção anterior; não apaga nem reinicia os dados. Para repetir um ensaio que terminou com reversão confirmada, usar explicitamente `-RepetirEnsaioRevertido`. Esta opção só aceita a fase `rolled_back` e conserva as gerações anteriores. Os resultados ficam em novos ficheiros `docs/validacao-manutencao-…json`.

## Resultado observado

Ensaio concluído em **2026-10-26T00:09:30.1343198Z**, no Windows PowerShell 5, com resultado **aprovado**. A base sintética tinha **3 incidentes e 15 entradas de histórico**. A promoção apresentou via HTTP os **9 incidentes e 60 entradas** da cópia do portal. Foram confirmadas onze tabelas históricas por hash, o registo de auditoria da geração e todas as ligações pausadas antes da retoma.

A retoma voltou a ativar **3 ligações**, conservando a ligação já pausada na origem. A reversão manual regressou aos **3 incidentes e 15 entradas** iniciais. Na falha de verificação deliberada, a promoção devolveu erro e a reversão automática regressou ao mesmo estado, com arranque e hashes confirmados. Login, consulta de histórico, post-mortems e pesquisa BM25 foram verificados através de pedidos HTTP reais na porta 8013.

Consultar [resultado completo da repetição com auditoria](validacao-manutencao-20261026-000842-6d66a4ec.json). A [primeira execução](validacao-manutencao-20261026-000347-75c4a3a5.json) parou na verificação HTTP inicial, antes de qualquer promoção, devido a um erro no helper de teste; esse erro foi corrigido. O volume inicial foi reutilizado explicitamente. O [primeiro ciclo aprovado](validacao-manutencao-20261026-000423-1088e677.json) também ficou conservado. A repetição seguinte verificou adicionalmente os registos de auditoria de promoção e reversão.

A suite automática passou com **158 testes** e um aviso de depreciação Starlette/httpx. Os testes de manutenção foram repetidos após o reforço da auditoria e da validação do diário. Incluem interrupção após a troca, bloqueio de arranque e de escritas, tentativa de promoção com leitor SQLite aberto, adulteração da candidata e do retorno, preservação de alterações anteriores à reversão, política de retoma e rejeição de caminhos manipulados. Não foi feita uma avaliação independente de segurança.

O ensaio usa um único computador com Docker Linux. Confirma a sequência operacional e os controlos observados, sem demonstrar um tempo garantido de recuperação ou tolerância a falha física de armazenamento. O portal habitual recebe apenas a atualização do código; a sua base não é substituída por este ensaio.


Verificação final: o [portal habitual em 0.13.0](validacao-manutencao-portal.json) manteve **9 incidentes e 60 entradas de histórico**, com login e pesquisa híbrida funcionais. Os caminhos HTTP de manutenção, recuperação e marcador de ensaio devolveram 404. O comando local Estado confirmou uma instalação sem promoção pendente; o hash do módulo no contentor coincide com o ficheiro local.

Após a repetição Docker foi acrescentada a rejeição explícita de diários JSON que não sejam objetos. Listas e null foram recusados numa verificação separada, os 12 testes de manutenção passaram novamente e a imagem final foi reconstruída. O relatório do ensaio conserva os hashes do código efetivamente medido nessa execução; a verificação final regista os hashes do código implantado. Nenhuma destas verificações substituiu a base do portal habitual.
