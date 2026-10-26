# Dossier de incidentes · v0.15

Abre um incidente no portal e usa **Relatório Markdown** ou **Dados JSON**, na secção **Guardar dossier**. O navegador descarrega um ficheiro com o número do incidente. Markdown é texto estruturado que pode servir de base a um anexo; JSON preserva os campos para análise por ferramentas. Não é gerado um PDF nesta versão.

## Conteúdo

Inclui identificação, origem, prioridade, estado, datas, responsável, descrição, resolução, causa raiz, prevenção, runbook, linha temporal completa, contexto da regra na deteção, escalonamento e todas as recolhas de logs já preservadas. Os dados atuais do serviço e o nome atual do responsável estão explicitamente identificados como dados do momento da exportação.

A exportação não consulta Loki nem recalcula sugestões da pesquisa. Uma sugestão visualizada não prova que foi aplicada; para documentar a utilização de conhecimento anterior, regista essa decisão nas notas do incidente. Casos abertos também podem ser exportados, mas o ficheiro não acompanha alterações posteriores.

## API e consistência

`GET /api/incidents/{id}/export?format=markdown` (por omissão) ou `format=json`. Todos os perfis autenticados com acesso aos incidentes podem exportar. São aplicadas as verificações de sessão existentes. Formato inválido: 422; caso inexistente: 404; sem sessão: 401.

Uma única transação de leitura SQLite cobre o incidente, o serviço, o responsável, a linha temporal e as evidências, evitando misturar estados de alterações concorrentes. A operação não modifica o caso. A resposta usa attachment, no-store e nosniff; o nome do ficheiro depende apenas do identificador numérico. A versão do esquema JSON é 1.

O Markdown coloca conteúdo fornecido pelos utilizadores em blocos literais com delimitadores ajustados ao conteúdo. Não interpreta HTML, ligações ou instruções presentes nas notas. Não inclui tabelas de sessões, palavras-passe, endereços de email das contas ou tentativas de login. Notas e logs podem, ainda assim, conter informação interna: revê o ficheiro antes de o partilhares. Não é uma cópia de segurança cifrada nem um documento assinado.

## Verificação

Os testes em `tests/test_dossier.py` cobrem autenticação, formato inválido, casos inexistentes, exportação pelo leitor, evidências, post-mortem de casos fechados, ausência de alterações no caso, tratamento literal de Markdown e consistência perante escrita concorrente. A validação do laboratório é apenas de leitura dos dados operacionais.

Resultado final: 174 testes passaram (244,71 s), com um aviso de descontinuação Starlette/httpx. No laboratório v0.15, os dois formatos foram verificados nos 9 incidentes e os 60 eventos permaneceram intactos. Registo em validacao-dossier.json; captura em dossier-v015.png.
