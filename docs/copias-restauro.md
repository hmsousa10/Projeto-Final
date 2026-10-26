# Cópias de segurança e restauro · v0.9

A entrega permite criar uma cópia cifrada e consistente da base SQLite, verificar a sua integridade e recuperar os dados numa pasta nova. O restauro não substitui automaticamente a base do laboratório.

## Criar uma cópia

Com o laboratório Docker iniciado e o ambiente Python preparado, fazer duplo clique em **copia-seguranca.cmd**. Em alternativa, na pasta do projeto:

```powershell
.\copia-seguranca.ps1 -Acao Criar
```

O comando apresenta o caminho do ficheiro `.nexobak` e o número de incidentes. Só publica o ficheiro final depois de verificar a cifra, a base recuperada e o hash dos bytes gravados. Nunca substitui uma cópia existente. Uma falha de gravação pode deixar um `.partial`, que não é apresentado como cópia válida.

As cópias ficam em `%LOCALAPPDATA%\Nexo\Backups`, fora da pasta OneDrive do projeto. A chave fica em `%LOCALAPPDATA%\Nexo\Keys\backup.dpapi`. As pastas usam permissões para o utilizador atual e SYSTEM; isso não impede um administrador do computador de tomar posse dos ficheiros. Não há eliminação ou agendamento automático de cópias.

## Verificar uma cópia

```powershell
.\copia-seguranca.ps1 -Acao Verificar -Arquivo 'C:\Users\hugom\AppData\Local\Nexo\Backups\nome-da-copia.nexobak'
```

Uma cópia só é aceite depois de validar a autenticação AES-GCM, o formato, o tamanho, o SHA-256 da base, o esquema compatível com esta aplicação, as contagens de linhas, `integrity_check` e `foreign_key_check`. Alterar o ficheiro ou usar outra chave faz falhar a verificação. A mensagem de erro não reproduz a chave nem os dados decifrados.

## Restaurar sem afetar o laboratório

Escolher uma **pasta nova** dentro de `%LOCALAPPDATA%\Nexo\Restauros`. O script prepara a pasta principal com permissões restritas; a pasta final ainda não pode existir.

```powershell
.\copia-seguranca.ps1 -Acao Restaurar `
  -Arquivo 'C:\Users\hugom\AppData\Local\Nexo\Backups\nome-da-copia.nexobak' `
  -Destino 'C:\Users\hugom\AppData\Local\Nexo\Restauros\ensaio-novo'
```

O resultado é `nexo.db` nessa pasta. As contas e respetivos hashes de palavras-passe são preservados; é preciso iniciar sessão novamente. Todas as ligações de monitorização ficam pausadas, o estado transitório dos alertas é limpo e fica um registo `recovery.restored` na auditoria. A configuração externa do Docker não é alterada.

Antes de promover uma base recuperada: verificar o histórico, escolher a configuração do ambiente, rever as contas, definir se as regras continuam adequadas e só depois retomar explicitamente a recolha. Desde a v0.13 existe um [procedimento de manutenção próprio](manutencao.md) para promover e reverter no volume ativo; o comando Restaurar continua a criar apenas uma base isolada. Não arrancar uma base de laboratório como se fosse uma instalação de produção.

## O que é copiado

São incluídos os utilizadores e perfis, serviços, dependências, incidentes, linha temporal, evidências de logs já preservadas no caso, observações SQLite, regras e versões, políticas SLO, auditoria, configurações internas e cache de embeddings, quando existente. As sessões são removidas apenas do snapshot: as sessões do portal ativo permanecem válidas. Usa-se `secure_delete` e `VACUUM` no snapshot para não conservar os valores eliminados em páginas livres.

O snapshot usa a API `sqlite3.backup`, incluindo transações confirmadas presentes no WAL. Não é uma cópia direta do ficheiro `.db` em utilização. Há limite de 32 MiB de base e um prazo de 20 segundos nas verificações de progresso do backup; chamadas de disco podem ultrapassar esse prazo. O limite protege este fluxo em memória e não constitui um ensaio de capacidade no tamanho máximo.

## Proteção e limites

O arquivo usa AES-256-GCM, chave aleatória de 32 bytes e nonce aleatório de 12 bytes por cópia. O cabeçalho do formato é autenticado. O manifesto e a base são cifrados em conjunto. A implementação utiliza a biblioteca `cryptography`, fixada na versão 50.0.2; não implementa o algoritmo de cifra.

No Windows, a chave é protegida com DPAPI `CurrentUser`. A chave em claro passa ao processo através de stdin, não em argumentos, variáveis de ambiente, logs ou endpoints HTTP. A cifra ocorre dentro do contentor antes da transferência para o Windows. A aplicação web não fornece uma rota de criação, upload ou substituição de cópias; são operações locais do administrador do computador.

**DPAPI vincula a chave ao contexto da conta Windows.** Copiar o `.nexobak` e o `backup.dpapi` para outra instalação não garante recuperação. É necessário preservar o perfil/contexto DPAPI e a chave. A partir da v0.11 existe um [kit portátil protegido por frase-passe](recuperacao-portatil.md), que deve ser exportado antes de perder o contexto original. O fluxo DPAPI descrito nesta página continua local; para recuperar sem essa conta usam-se o kit e a frase-passe, não apenas o ficheiro DPAPI.

As cópias não incluem os volumes completos do Prometheus ou Loki, os ficheiros secretos do Compose, o código ou as imagens Docker. Os logs preservados como evidência nos incidentes estão incluídos; os restantes logs Loki não. A chave nunca deve ser colocada no Git ou entregue juntamente com uma cópia em claro. Os ficheiros temporários decifrados são criados em diretórios temporários privados e removidos após a operação; no Docker ficam no tmpfs `/tmp`, e no Windows podem passar pelo disco local. A remoção não é uma promessa de apagamento forense em SSD. A base restaurada é um ficheiro SQLite sem cifra própria e deve manter as permissões restritas e a proteção do dispositivo.

A cifra não protege contra malware a executar com a conta Windows desbloqueada, administradores que controlem a máquina ou uma cópia de origem já comprometida. Não equivale a certificação nem a invulnerabilidade. Esquemas futuros exigem migração explícita; a verificação recusa estruturas diferentes, vistas e triggers inesperados. Diferentes indentação/espaçamento SQL de migrações anteriores são normalizados sem alterar literais.

## Ensaio realizado

Foi criada uma cópia cifrada do volume ativo, verificada no Windows PowerShell 5 e restaurada numa pasta nova. A aplicação abriu a base recuperada com integrações externas desligadas. O ensaio confirmou:

- Nove incidentes e sessenta entradas de linha temporal preservados.
- Igualdade por hash dos registos de onze tabelas de histórico, incluindo contas, serviços, incidentes, evidências, regras, escalonamentos e políticas SLO.
- Ausência de sessões antes do login e quatro ligações de monitorização pausadas.
- Login, consulta de um incidente fechado, resolução, causa, linha temporal e pesquisa do histórico funcionais.
- Perfil de leitura sem acesso à gestão de contas e ausência de endpoint público de restauro.

Evidências: `validacao-restauro.json` e `referencia-restauro-v09.json`. A duração registada é apenas a verificação da aplicação recuperada; não mede um RTO completo nem um RPO. A suite inclui testes com WAL aberto, adulteração, chave errada, destino existente, esquema inesperado, referências inválidas, limites, remoção física das sessões e compatibilidade das migrações anteriores. Os resultados finais da suite são registados no README.

Fontes técnicas: [SQLite Online Backup API](https://www.sqlite.org/backup.html), [Python sqlite3.backup](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup), [AES-GCM em cryptography](https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM) e [Microsoft DPAPI](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.protecteddata).
