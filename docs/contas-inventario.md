# Contas e inventário · versão 0.5

## Gestão de acessos

A página **Utilizadores**, acessível apenas a administradores, permite criar contas e editar nome, email, perfil e estado ativo. A lista administrativa não inclui hashes, palavras-passe ou tokens. Operações e Leitura continuam a ter acesso apenas à lista mínima necessária para mostrar responsáveis no histórico.

Para criar uma conta:

1. Abrir http://127.0.0.1:8001/#users com um administrador.
2. Escolher **Novo utilizador** e indicar nome, email, perfil e palavra-passe inicial.
3. Entregar as credenciais à pessoa através de um canal apropriado. Esta versão não envia convites por email.
4. No primeiro acesso, o utilizador deve substituir a palavra-passe inicial. Até o fazer, só pode consultar a própria sessão, alterar a palavra-passe ou terminar sessão; as operações funcionais ficam bloqueadas na API.

As novas palavras-passe têm entre 15 e 200 caracteres. Não são impostas misturas obrigatórias de letras, algarismos ou símbolos. Espaços não são removidos. Existe uma pequena lista local de valores previsíveis bloqueados, incluindo a palavra-passe da demonstração; não é uma base completa de credenciais comprometidas. Os erros de validação não devolvem os valores submetidos.

Qualquer utilizador ativo pode usar **Minha conta** para alterar a própria palavra-passe, indicando a atual. A alteração revoga todas as sessões anteriores e emite uma nova sessão para o pedido bem-sucedido. São permitidas até cinco tentativas de alteração por utilizador em dez minutos; o contador é persistente e não é reposto por iniciar outra sessão.

As contas existentes são migradas sem alterar a palavra-passe nem forçar uma troca não solicitada. As contas conhecidas de demonstração continuam destinadas apenas à execução local. A política das rotas novas não constitui uma certificação NIST nem validação integral do deployment.

## Desativação e perfis

- Alterar perfil, email ou estado ativo revoga as sessões da conta. Pedidos seguintes têm de voltar a autenticar-se.
- Uma conta desativada não consegue iniciar sessão nem ser atribuída a novos incidentes.
- Uma conta que ainda não tenha alterado a palavra-passe inicial também não pode assumir um incidente.
- Antes de desativar uma pessoa, ou de a passar a Leitura, é necessário reatribuir os seus incidentes ativos.
- Não é permitido desativar ou retirar o perfil ao último administrador ativo. A verificação é feita dentro de uma transação que coordena alterações concorrentes.
- As contas não são apagadas. Os IDs, atribuições anteriores e nomes registados nas linhas temporais permanecem no histórico.

As verificações são aplicadas na API, independentemente dos botões apresentados. A auditoria regista a criação, os campos administrativos alterados e as alterações de palavra-passe, sem guardar segredos nesses eventos.

Não estão implementados MFA, SSO, recuperação por email, convite de utilização única, gestão de permissões por equipa nem um fluxo administrativo de reposição de palavra-passe. Não ativar uma conta de validação desativada sem primeiro preparar uma credencial utilizável através de um procedimento futuro de recuperação.

## Editar serviços

Abrir os detalhes de um serviço no inventário ou em Monitorização e escolher **Editar serviço**. O administrador pode atualizar nome, equipa, descrição, criticidade, metas de disponibilidade/latência e dependências.

A edição preserva o ID do serviço, o endereço associado à monitorização, observações, incidentes e evidências. Não existem eliminações em cascata neste fluxo. O endereço da ligação continua a ser gerido separadamente e permanece imutável para preservar a identidade do histórico.

São rejeitadas dependências inexistentes, dependência de si próprio e ciclos indiretos. A validação e a escrita decorrem na mesma transação, para que duas alterações concorrentes não criem um ciclo.

Uma alteração do objetivo de latência exige novas sondagens para confirmar o estado e a recuperação dos alertas. As amostras anteriores ficam no histórico; não são reinterpretadas como novas ocorrências. As metas continuam a ser valores de referência, sem cálculo completo de orçamento de erro ou cumprimento de SLA por janela.

As alterações do inventário ficam na auditoria e são assinaladas na linha temporal dos incidentes ativos do serviço. As referências do laboratório usam a chave de monitorização na interface, pelo que o respetivo nome de apresentação pode mudar sem desligar os controlos de teste.

## Verificação

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/validar-acessos.py
```

O ensaio em Docker cria uma conta com credenciais aleatórias temporárias, verifica primeiro acesso, alteração de palavra-passe, revogação de sessões, restrições de Leitura e desativação. A conta é desativada no fim e as credenciais não são escritas no resultado. Evidência: validacao-acessos.json.

A edição pela interface foi verificada no serviço **Exemplo · Ligação HTTP pausada**: equipa **Demonstração · Operações**, criticidade **Média**, objetivo de latência **600 ms** e dependência do serviço de referência **Laboratório · Portal HTTP**. A ligação **service-8** permaneceu pausada e com o mesmo ID.

Validação em 24/10/2026: **68 testes automáticos passaram**, com um aviso de depreciação Starlette/httpx. O ensaio de acessos em Docker terminou às 20:44:47 UTC; a conta de validação **4** ficou desativada. As contas de demonstração anteriores mantiveram o respetivo acesso. Os testes usam bases temporárias para verificar a proteção do último administrador, atribuições históricas, desativação, troca de palavra-passe, sessões, dependências e alterações concorrentes.

Os formulários de criação e edição de utilizadores foram inspecionados no navegador; a gravação da conta de validação manteve o estado desativado. A aplicação foi reiniciada com contas e alterações do inventário preservadas. Imagem da página de utilizadores.

Referência para a escolha do comprimento e ausência de regras de composição: [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html). O projeto ainda não foi avaliado integralmente contra esse documento.
