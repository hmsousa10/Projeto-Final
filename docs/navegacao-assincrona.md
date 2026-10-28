# Navegação e consultas assíncronas · v0.19 local

As janelas de incidentes, logs, históricos e ligação de serviços abrem imediatamente com uma indicação de carregamento. Cada consulta tem um identificador associado à janela, à página e à sessão que a iniciou. Se abrires outra janela, mudares de página ou fechares a consulta, a resposta antiga deixa de poder atualizar a interface.

A navegação entre páginas e a paginação de auditoria/notificações seguem o mesmo princípio: a última consulta válida é a que pode apresentar o resultado. A atualização periódica volta a verificar se existe uma janela aberta ou um campo em edição antes de substituir a página. Se uma página falhar ao carregar, apresenta uma mensagem e o botão **Voltar a tentar**.

## Incidentes e pesquisa

Uma indisponibilidade na pesquisa de casos semelhantes apresenta um aviso e permite continuar a consultar e tratar o incidente. Não são fabricadas recomendações para substituir a pesquisa indisponível. Se a sessão expirar, mantêm-se os controlos de autenticação existentes.

Respostas de sessões antigas não devem terminar uma nova sessão que entretanto tenha sido iniciada. As permissões continuam a ser verificadas pela API.

## Gravações em curso

Fechar uma janela não cancela uma gravação já enviada à API. A operação pode concluir e ficar guardada no histórico, mas a resposta não reabre o incidente anterior nem fecha a janela que entretanto escolheste. O comportamento é aplicado aos formulários de incidentes e aos restantes formulários operacionais, incluindo recolha de evidências.

Esta proteção impede alterações tardias da interface; não cancela obrigatoriamente o pedido de rede em curso. Os limites e timeouts do servidor continuam em vigor.

## Testes

`tests/frontend/navigation.test.cjs` usa o runner nativo do Node e executa o ficheiro real web/app.js num contexto controlado com respostas atrasadas. Cobre respostas fora de ordem, fecho, erros antigos, eventos close pendentes, rotas, paginação, gravações tardias, falha na pesquisa, nova sessão e resultados normais de logs/históricos.

Executar com Node instalado:

```powershell
node --test tests/frontend/navigation.test.cjs
```

São testes da lógica assíncrona com um DOM mínimo, não uma suite completa de testes de navegador. A verificação visual é feita separadamente. A configuração local do GitHub Actions já inclui este comando e será enviada quando o autor decidir fazer o próximo push.

## Estado

Entrega local, mantendo as alterações de v0.18. Não foi criado commit nem efetuado push nesta etapa. Não houve alteração ao esquema SQLite nem às regras do ciclo de incidentes. Resultados em validacao-navegacao.json.
