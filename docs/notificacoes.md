# Central de notificações · v0.14

O portal dispõe de uma central de avisos em **Notificações**, acessível também pelo sino no cabeçalho. O contador representa avisos que a conta atual ainda não marcou como lidos. Não equivale ao número de incidentes ativos.

## Utilizar

1. Abrir `http://127.0.0.1:8001/#notifications` após iniciar sessão.
2. Consultar o evento, o serviço, a data, o estado e a prioridade atual do incidente.
3. Escolher **Abrir caso** para consultar o histórico, evidências e sugestões de conhecimento.
4. Escolher **Marcar todas como lidas** para guardar a leitura na conta atual. Este gesto não atribui, reconhece, resolve ou fecha um incidente.

No primeiro acesso, os eventos operacionais já existentes aparecem por ler. As ocorrências anteriores continuam no histórico mesmo depois do fecho do caso. A mensagem do evento é histórica; o estado e a prioridade apresentados são os atuais. Os exemplos com origem `demo…` ficam excluídos desta central.

## Eventos incluídos

- Novos incidentes manuais e alertas confirmados pelas sondagens.
- Recorrências agrupadas num caso existente e elevações de prioridade.
- Atribuição de responsável e recuperação confirmada do serviço.
- Escalonamento por falta de reconhecimento ou prazo ultrapassado quando o caso já está em P1.

Os prazos são os do motor de regras existente. Quando a regra de escalonamento está ativa e o prazo termina, o motor regista um evento único. A central apresenta esse evento; não calcula um segundo escalonamento nem duplica a linha temporal. Não existe aviso antecipado antes do prazo nesta versão.

## Atualização e leitura

O sino consulta o servidor a cada dez segundos enquanto a página está visível e a sessão é válida. Funciona também durante a consulta do conhecimento ou de um incidente, sem substituir esses conteúdos. A lista de notificações permanece estável durante a leitura; se surgirem novos eventos, aparece uma indicação para atualizar.

A leitura usa um cursor monotónico por utilizador, guardado em `settings`. Não exige uma nova tabela ou alteração de esquema. Abrange os avisos até ao identificador observado quando a lista foi carregada. Um evento chegado entretanto continua por ler. Um pedido antigo não faz recuar o cursor. Leitores podem guardar a sua própria leitura, mantendo a proibição de alterar incidentes.

**Marcar todas** inclui os avisos mais antigos que a página atual. Nas páginas antigas esse botão dá lugar a **Voltar às recentes**, para não marcar inadvertidamente novos eventos que não foram apresentados. A navegação usa páginas de 30 avisos; a API permite de 1 a 50 e utiliza paginação pelo identificador do último evento. Excerto limitado a 400 caracteres, com indicação de truncamento; o conteúdo completo está no incidente.

Os eventos são obtidos diretamente do histórico persistente, sem uma fila de entrega separada. Recarregar ou reiniciar o portal não os duplica. As cópias existentes continuam compatíveis porque o esquema não mudou; novas cópias incluem os cursores de leitura. Num restauro, a preferência corresponde ao estado guardado nessa cópia.

## Segurança e alcance

As consultas e os pedidos de leitura exigem sessão válida e respeitam a troca obrigatória da palavra-passe inicial. O utilizador do cursor vem da sessão, nunca de um identificador submetido pelo cliente. A API recusa identificadores futuros ou eventos fora do conjunto operacional, valores acima do intervalo SQLite, tipos inválidos e campos adicionais.

Todos os perfis veem atualmente o mesmo inventário e os mesmos incidentes; a central respeita esse alcance existente. Não implementa equipas isoladas ou permissões por serviço. O texto variável é escapado na interface. Os pedidos de leitura herdam a proteção de origem e o bloqueio de alterações durante uma verificação de manutenção.

Esta versão entrega avisos **dentro do portal**. Não envia email, SMS, mensagens para terceiros ou notificações do sistema operativo. Um navegador fechado não recebe avisos; ao voltar a abrir, o histórico é consultável. Não existe promessa de entrega externa, alarme imediato ou funcionamento se o próprio Nexo estiver indisponível.

Os ficheiros CSS e JavaScript são agora referenciados com a versão da aplicação e um hash do conteúdo e o HTML inicial usa `Cache-Control: no-store`. Isto evita misturar a interface atual com estilos de uma versão anterior mantidos na cache do navegador.

## Validação

Testes automáticos verificam autenticação, separação da leitura entre contas, persistência após novo login, manutenção do estado do incidente, chegada de um novo aviso durante a marcação, cursor monotónico, paginação sem repetições, limites e excertos, rejeição de campos indevidos e um único aviso produzido pelo motor de prazos real.

Os ensaios de escrita usam bases temporárias. A instalação habitual é verificada por leitura, sem acrescentar incidentes nem marcar os avisos do utilizador como lidos. Resultados e imagem da interface são guardados na pasta `docs` após a verificação.
