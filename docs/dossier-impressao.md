# Dossier de impressão · v0.34

Abrir um incidente e escolher **Imprimir / guardar PDF** na área Guardar dossier.
A nova página reúne identificação, datas, sintomas, resolução, post-mortem,
cronologia completa, evidências e regra preservada. Os formatos Markdown e JSON
continuam disponíveis.

Para criar um PDF, usar Ctrl+P no navegador, escolher Guardar como PDF e papel A4.
Desativar cabeçalhos e rodapés do navegador para evitar incluir o endereço local.
Rever a pré-visualização: paginação e margens finais dependem do navegador.
O servidor devolve HTML para impressão; não gera um PDF automaticamente.

O dossier usa uma única fotografia consistente da base de dados, tal como os
formatos existentes. Não altera casos, leitura de notificações ou auditoria. É
acessível aos três perfis autenticados. O ficheiro contém dados internos; rever
antes de partilhar. Um documento aberto mantém a fotografia da exportação;
recarregar cria uma nova fotografia. Não é backup, assinatura digital nem prova
de que a recolha estava completa. Evidências ausentes são indicadas explicitamente.

A origem dos exemplos sintéticos é identificada. Datas com fuso são convertidas
para UTC e as ausentes são apresentadas como não registadas. Nomes de serviço e
responsável são os do inventário no momento da exportação.

O documento não carrega fontes, imagens ou scripts externos. O texto variável é
escapado, incluindo notas e payloads de evidência. A política CSP bloqueia scripts,
recursos externos, formulários e incorporação; só permite o CSS com o hash esperado.
A resposta usa no-store. Guardar localmente continua a criar um ficheiro fora da
gestão de sessões do portal; terminar sessão não apaga ficheiros já guardados.

## Validação

Os testes verificam autenticação, acesso dos três perfis, consistência da exportação, ausência de escrita e de execução de conteúdo não confiável. A impressão efetiva em PDF depende do navegador e deve ser conferida na pré-visualização.

Consultar [desenvolvimento e testes](../CONTRIBUTING.md) para repetir as verificações.
