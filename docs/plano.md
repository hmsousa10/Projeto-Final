# Âmbito e trabalho pendente

## Percurso implementado

O laboratório permite provocar uma falha controlada na Aurora, recolher observações
e logs, gerar um incidente, atribuir responsável, investigar, consultar conhecimento
anterior e fechar o caso com histórico. Depois do fecho podem ser acompanhadas ações
de prevenção com prazos e decisões finais.

## Requisitos funcionais

- RF01 — inventário de serviços, equipas indicadas por serviço, criticidade, dependências e objetivos.
- RF02 — recolha de observações HTTP e logs com origem explícita, em laboratório e integrações autorizadas.
- RF03 — regras de alerta versionadas, agrupamento de ocorrências e escalonamento.
- RF04 — ciclo de incidentes, post-mortem, evidências, proteção de concorrência e ações de prevenção.
- RF05 — recuperação textual e semântica do conhecimento, com referência ao caso de origem.
- RF06 — sessões, perfis, gestão de contas e auditoria; aplicação de permissões no servidor.
- RF07 — execução Docker, dossiers exportáveis, cópias cifradas e restauro em destino separado.

## Pendências

1. Avaliar a utilização com participantes e dados representativos, distinguindo resultados humanos de ciclos executados por script.
2. Realizar revisão independente de segurança e um ensaio de implantação num ambiente de destino definido.
3. Desenvolver entrega externa de notificações e verificar falhas/repetições de entrega.
4. Validar um conector com uma empresa real e o respetivo contrato de API.
5. Evoluir a modularização da API e da interface e acrescentar análise estática.
6. Considerar um painel global de ações de prevenção e necessidades de separação por equipa.

## Limites atuais

O portal não executa correções automaticamente. Não existe recuperação de conta por
email, isolamento de equipas dentro da instalação, nem garantia de ausência de
vulnerabilidades. Empresas de referência e falhas controladas são fictícias. Uma
instalação empresarial e os respetivos dados exigem validação própria.
