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

Validação local em 4 de novembro de 2026: bateria geral com 323 testes Python
aprovados, teste adicional de migração aprovado e 43 testes JavaScript aprovados.
A bateria Python apresentou um aviso de depreciação já existente no TestClient.
O ensaio manual em dois navegadores não foi executado nesta entrega.
