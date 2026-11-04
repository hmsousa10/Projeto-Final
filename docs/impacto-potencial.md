# Impacto potencial por dependências · v0.22 local

As janelas de serviço e incidente incluem a secção expansível **Impacto potencial**. Esta consulta reaproveita os serviços e relações já carregados pelo portal. Não acrescenta pedidos de rede nem altera registos.

## Interpretação

Se Portal depende de API e API depende de Base de dados, uma falha na Base de dados pode propagar-se à API e ao Portal. A consulta percorre as relações nesse sentido: do pré-requisito para quem depende dele. Não apresenta os pré-requisitos do serviço como se fossem seus dependentes.

Cada serviço aparece uma vez, com equipa, criticidade e última classificação de estado disponível no inventário consultado. **Dependência direta** corresponde a uma ligação; **Dependência indireta** indica o número mínimo de ligações. A cadeia pode ser expandida para perceber a relação. Havendo vários caminhos mínimos, é apresentado um deles, com desempate por identificador; não são enumerados todos os caminhos possíveis.

As relações são hipóteses de propagação. Um dependente pode continuar operacional; um estado degradado pode ter outra causa. A consulta não confirma impacto em clientes, não mede custo de indisponibilidade e não identifica causa raiz. O estado resulta dos controlos de frescura e recolha existentes no servidor, no momento em que os serviços foram carregados.

O instante da consulta do inventário aparece no bloco. Nos casos fechados, continua a ser o inventário atual da consulta, não a topologia nem os estados que existiam na data da falha. A consulta de dependências não é preservada na linha temporal nem acrescentada ao dossier do incidente. Evidências preservadas mantêm os mecanismos próprios. Na versão seguinte, v0.23 local, a recolha explícita de uma avaliação passa a ser possível; consultar impacto-preservado.md.

## Limites

São apresentados até 50 dependentes. Ao encontrar um serviço adicional, surge um aviso de lista parcial. O número apresentado não deve ser tratado como o total quando esse aviso existe. A seleção percorre primeiro dependentes mais próximos e, em cada expansão, identificadores crescentes.

Relações duplicadas não duplicam os serviços. A visita controlada impede repetição infinita mesmo perante ciclos em dados antigos; a edição do inventário continua a rejeitar novos ciclos. Quando faltam serviços ou relações no catálogo recebido, a interface avisa que não pode concluir ausência de impacto. A inexistência de relações registadas também não prova inexistência de dependências reais.

O processamento percorre o catálogo e as ligações já existentes na memória do navegador, sem um novo motor de grafos. O limite de apresentação não reduz o tamanho do inventário carregado nem constitui validação de escala empresarial.

## Validação

Os testes Node usam o código real da interface com DOM mínimo. Verificam sentido das relações, caminhos indiretos e mínimos, deduplicação, ciclos, truncagem, inventário incompleto, escape de nomes e apresentação em serviços e incidentes. Os restantes testes de navegação permanecem na mesma suite.

A verificação no laboratório consulta o serviço de exemplo Base de dados e os seus dependentes, sem provocar falhas ou alterar as relações. Estes serviços são exemplos sintéticos, identificados no portal; não estão ligados à base SQLite interna do Nexo. A captura não demonstra uma falha real.

 A alteração é de interface, além do número da versão; não muda o esquema, as dependências ou os contratos da API. Não se repetiu a suite Python nesta etapa.
