# Ações de prevenção · v0.36

Depois de resolver ou fechar um incidente, abrir o caso e escolher **Acrescentar
ação de prevenção**. Indicar medida, responsável e prazo. A ação começa pendente.
O prazo corresponde ao dia UTC: só aparece ultrapassado a partir do dia seguinte.
É possível registar um prazo passado, para documentar medidas que já estão atrasadas.

Operações e Administração podem criar ações e registar a sua conclusão ou
cancelamento com uma nota obrigatória de 10 a 2000 caracteres. Podem tratar qualquer
ação da instalação, não apenas as que lhes estão atribuídas. Leitura apenas consulta.
O responsável escolhido tem de ser uma conta ativa de Operações ou Administração,
com o primeiro acesso concluído. O nome do responsável é preservado na criação;
renomear ou desativar a conta não reescreve esse registo histórico.

A ação acompanha trabalho decidido pela equipa. Marcá-la concluída não executa
alterações na empresa nem comprova por si que uma correção foi aplicada. A nota
final deve indicar o que foi feito e como foi verificado. Cancelar exige motivo.
Não existe edição, remoção ou reabertura de ações nesta versão; uma medida que
precise de substituição pode ser cancelada e registada numa nova ação. O limite
é de 20 ações por incidente, incluindo concluídas e canceladas.

O estado do incidente, datas de resolução/fecho, post-mortem e revisão não mudam
quando se trata uma ação. Os novos eventos são acrescentados à cronologia mesmo
num caso fechado, identificando autor e data. Duas decisões concorrentes sobre
a mesma ação não são aceites: a primeira termina a ação, a segunda recebe conflito.

## Persistência e exportação

A criação e a decisão ficam em eventos estruturados da tabela timeline e em auditoria,
na mesma transação de escrita. O estado atual é obtido desses eventos, sem uma nova
tabela ou mudança de esquema. Cada ação admite uma única decisão terminal; o máximo
normal é de 40 eventos de ações por incidente. Os eventos e a lista de ações fazem
parte dos dossiers JSON, Markdown e impressão, com indicação dos prazos ultrapassados.
As cópias cifradas existentes já incluem a cronologia; novas cópias incluem as ações.
Um ensaio automático verifica cópia cifrada e restauro numa pasta temporária nova.

Não existe envio de email, lembrete automático nem painel global de ações nesta
versão. O estado e os atrasos são consultados ao abrir cada incidente. Para encontrar
um caso já fechado, usar a vista Resolvidos ou Todos na página Incidentes.

## Validação

Os testes verificam permissões, responsáveis, datas, limite de ações, decisões concorrentes, exportação e restauro cifrado. A interface é verificada quanto a escaping, leitura e respostas atrasadas.

Consultar [desenvolvimento e testes](../CONTRIBUTING.md) para repetir as verificações.
