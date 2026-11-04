# Perfis e permissões · v0.35

**Minha conta** apresenta nome, email e perfil da sessão, as ações permitidas e as
restrições. A alteração de palavra-passe mantém o formulário existente. A secção
recolhível permite compreender os outros perfis sem sair da conta.

Na página **Utilizadores**, o administrador pode abrir a explicação dos três
perfis. Ao criar ou editar uma conta, a descrição debaixo do campo Perfil muda
com a seleção. Escolher uma opção não guarda a conta: é necessário submeter o
formulário existente, sujeito às verificações do servidor.

- Administração: trata incidentes, configura inventário, regras e monitorização,
  gere contas e consulta a auditoria.
- Operações: consulta a operação e trata incidentes, incluindo atribuição, notas,
  evidências, referências, resolução e fecho. Não gere utilizadores, inventário,
  regras ou ligações de monitorização e não consulta auditoria.
- Leitura: consulta serviços, casos e conhecimento; exporta dossiers e gere a
  sua leitura de notificações. Não altera casos nem pode ser responsável por um.

Os três perfis podem alterar a sua própria palavra-passe. As permissões reais
continuam verificadas pelo servidor. Este guia é explicativo e não acrescenta
novas autorizações, perfis ou separação de dados. Nesta instalação todos consultam
o mesmo inventário e os mesmos incidentes; não existe isolamento por equipa.

Cada pessoa deve ter uma conta individual para manter a identificação das decisões
no histórico. As contas Equipa de operações e Consulta são exemplos da demonstração.
Uma instalação empresarial não deve usar estas contas partilhadas de exemplo.

A v0.35 não altera o esquema da base de dados nem as regras de acesso. Foram
reexecutados os 51 testes JavaScript e os testes existentes de contas e inventário.
A bateria Python completa não foi repetida.
