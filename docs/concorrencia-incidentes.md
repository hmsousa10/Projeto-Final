# Colaboração segura no tratamento de incidentes

## Problema e comportamento

Dois operadores podem consultar o mesmo caso e decidir responsáveis diferentes.
Uma atualização automática de prioridade também pode ocorrer enquanto um operador
prepara a resolução. A versão 0.32 permite detetar que o formulário deixou de
representar o estado atual antes de aceitar uma atribuição ou transição.

Cada incidente tem um contador `revision`. O navegador envia a revisão que
apresentou através de `expected_revision`. O servidor começa uma transação
`BEGIN IMMEDIATE`, lê o incidente e compara as revisões antes de qualquer escrita.
Uma revisão desatualizada recebe HTTP 409. Não altera o incidente, a auditoria ou
a cronologia. O navegador mantém os campos preenchidos e apresenta instruções
para copiar o texto e reabrir o caso. Não volta a tentar automaticamente.

O contador é incrementado por um trigger em cada UPDATE da linha do incidente,
incluindo atualizações efetuadas pelos coletores e escalonamento. Uma operação
pode executar vários UPDATEs: o contador é um token monotónico, não a contagem
de ações humanas. Notas e evidências adicionais não substituem os campos do
incidente e não incrementam este contador.

## Compatibilidade e limites

A migração acrescenta a coluna e o trigger no arranque, preservando os dados.
É idempotente. Novos incidentes começam em zero; casos existentes recebem zero
na migração, sem reconstruir versões anteriores.

O portal envia sempre uma revisão válida. A API mantém o campo opcional para
compatibilidade com os scripts anteriores: clientes que o omitirem ou enviarem
null conservam o comportamento anterior. Esses clientes não têm a proteção contra
gravações desatualizadas. A revisão não substitui autenticação ou permissões.

Cópias de segurança usam validação exata de esquema. Uma cópia criada na v0.31
deve ser recuperada com o código v0.31 e só depois aberta na v0.32 para migrar.
Não editar manifestos ou desativar a verificação. Depois da atualização, criar
uma nova cópia v0.32. Uma instalação em execução só muda após reconstrução e
reinício do respetivo serviço Docker; o commit não atualiza os contentores.

## Demonstração manual

1. Abrir o mesmo incidente ativo em dois navegadores ou separadores.
2. No primeiro, guardar uma atribuição.
3. No segundo, escolher outro responsável e guardar: aparece o aviso de conflito.
4. Confirmar que o primeiro responsável continua guardado.
5. Reabrir o incidente no segundo separador, rever o estado e guardar a decisão atual.

O mesmo controlo aplica-se ao reconhecimento, investigação, resolução e fecho.
As regras de transição, responsável e recuperação continuam a ser verificadas.

## Validação

Os testes exercitam duas escritas concorrentes sobre a mesma revisão, rejeição
sem efeitos secundários, leitura e nova tentativa, revisões inválidas, permissões,
atualizações diretas e reinicialização idempotente. Os testes JavaScript executam
o envio dos dois formulários e verificam que o conflito mantém o texto e reativa
o botão. Estes testes usam DOM mínimo e não substituem a demonstração em dois
navegadores.

## Recuperar um conflito no formulário · v0.33

O servidor identifica especificamente os conflitos de revisão no cabeçalho
`X-Nexo-Conflict: incident-revision`. Outros erros 409, como uma transição inválida
ou recuperação ainda não confirmada, mantêm a sua mensagem habitual.

Após um conflito de revisão, a interface consulta o caso sem substituir o
formulário. O painel apresenta revisão, estado, prioridade, responsável e campos
de resolução já guardados. A consulta não escreve na base de dados.

Se o estado continuar igual, **Usar versão consultada** atualiza apenas a revisão
do formulário. O texto e a seleção de responsável mantêm-se. O operador tem de
rever e carregar novamente no botão de guardar: não existe repetição automática.
Se alguém alterar entretanto o caso, o servidor volta a recusar a gravação.

Se o ciclo tiver avançado, o painel não permite reutilizar o formulário antigo.
É necessário conservar o texto pretendido e reabrir o caso para consultar as ações
do novo estado. **Consultar novamente** atualiza apenas a comparação. Respostas
fora de ordem ou de uma janela já fechada não substituem o contexto atual.

Os rascunhos ficam apenas no formulário em memória. Fechar a janela, atualizar a
página ou terminar a sessão pode perdê-los. Esta versão não guarda texto no
armazenamento do navegador nem faz fusões automáticas entre decisões.

### Validação da v0.33
