# SLIs, SLOs e cobertura · versão 0.7

A página **Objetivos e SLOs** avalia as sondagens HTTP reais em janelas de um minuto, quinze minutos, uma hora, vinte e quatro horas e sete dias. A janela de um minuto serve sobretudo para ensaios rápidos. O resultado descreve os alvos monitorizados, não todos os pedidos de clientes nem disponibilidade contratual de uma empresa.

## Objetivos e versão aplicada

Cada serviço passa a ter dois objetivos percentuais:

- **Disponibilidade das sondagens:** proporção de intervalos com sondagem HTTP bem-sucedida; usa o objetivo de disponibilidade do inventário.
- **Resposta boa dentro do limite:** proporção de intervalos com sucesso HTTP e duração menor ou igual ao limite de latência. O objetivo percentual inicial é **95%**, editável no inventário. Um erro HTTP rápido não é uma boa resposta.

O administrador pode escolher **Editar objetivos** no cartão do serviço. Alterar disponibilidade, limite de latência ou percentagem de respostas boas cria uma versão com data e autor. Mudar apenas nome ou equipa não cria uma versão dos objetivos.

Os serviços anteriores recebem uma primeira fotografia dos objetivos no arranque da versão 0.7, com efeitos a partir desse instante. **Não se inventa uma política histórica para os dados anteriores.** Um serviço novo recebe a primeira versão quando é criado. O botão **Histórico dos objetivos** apresenta as versões, preservando os valores anteriores.

O resultado formal da janela exige que a política vigente cubra o período inteiro. Se a política foi criada ou alterada a meio da janela, aparece **Histórico da política insuficiente**, com valores provisórios. O relatório não mistura metas de versões diferentes para declarar cumprimento. As janelas selecionadas são avaliações de diagnóstico; os objetivos ainda não representam um acordo de serviço aprovado por uma organização.

## Janela e denominador

O tempo é dividido em intervalos UTC de **dez segundos**, alinhados com a cadência configurada no Prometheus. Uma janela de um minuto contém seis intervalos; quinze minutos, noventa; sete dias, 60 480.

A janela termina num limite de dez segundos, com **margem de trinta segundos** para a recolha e a importação chegarem à aplicação. Por exemplo, uma consulta às 10:05:39 avalia até às 10:05:00. O início é incluído e o fim excluído. O intervalo ainda em curso e os mais recentes em fase de chegada não são avaliados prematuramente.

Só são usadas observações com origem `prometheus`. Dados sintéticos ficam excluídos. Cada intervalo conta uma única vez; se tiver mais de uma medição, prevalece o pior resultado. Isso impede que amostras repetidas aumentem artificialmente a cobertura ou a taxa de sucesso.

O intervalo que contém uma alteração de política só é elegível se a política já estivesse em vigor desde o início desse intervalo. Valores inválidos ou latências não finitas não contam como observações válidas.

## Cobertura e incerteza

O relatório distingue:

- **Cobertura de dados:** intervalos com medições reais, incluindo dados anteriores à política atual.
- **Cobertura sob a política vigente:** intervalos observados que podem ser avaliados sem atravessar uma alteração de objetivo.
- **Desconhecidos:** intervalos esperados sem medição elegível, incluindo pausas, falhas de recolha e períodos anteriores à política vigente.

Com `N` intervalos esperados, `O` observados, `G` bons e `U = N − O` desconhecidos:

```text
SLI observado = 100 × G / O               (indefinido se O = 0)
Limite inferior = 100 × G / N
Limite superior = 100 × (G + U) / N
```

Os limites são determinísticos, não intervalos de confiança estatística. Assumem, nos extremos, que os desconhecidos foram todos maus ou todos bons.

Se a política cobre toda a janela:

- **Dentro do objetivo:** até o limite inferior atinge a meta.
- **Fora do objetivo:** nem o limite superior consegue atingir a meta.
- **Dados insuficientes:** os dados desconhecidos podem mudar a conclusão.

Assim, uma taxa observada de 100% sobre cinco dos seis intervalos não demonstra um SLO de 99,9% na janela inteira. Por outro lado, falhas conhecidas suficientes podem demonstrar uma violação mesmo com lacunas. A interrupção da recolha não é automaticamente classificada como falha do serviço.

O estado atual da recolha aparece separadamente. Uma pausa não apaga o período já observado; o resultado sempre se refere à janela apresentada, não ao estado instantâneo do serviço.

## Orçamento de erro

Para uma meta percentual `T`:

```text
Orçamento permitido = N × (1 − T / 100)
Falhas conhecidas = O − G
Restante mínimo = permitido − falhas conhecidas − U
Restante máximo = permitido − falhas conhecidas
```

O orçamento é expresso em **unidades de sondagem**, pode ser fracionário e não representa minutos de indisponibilidade. Valores negativos indicam défice nesse cenário; um intervalo que inclui valores negativos e positivos continua incerto. Quando a política não cobre a janela, estes valores também são provisórios.

As comparações com o objetivo usam aritmética decimal, evitando uma tolerância fixa que pudesse declarar sucesso para metas percentuais muito pequenas. As percentagens são formatadas na interface, mas a decisão usa os valores sem arredondamento de apresentação.

## Latência p95

O p95 apresentado é **descritivo**, por ordem estatística mais próxima, calculado sobre os intervalos elegíveis bem-sucedidos, usando a maior duração quando há duplicados. Não inclui erros HTTP rápidos e não substitui o SLI de respostas boas. O número de intervalos usado aparece ao lado. Sem sucessos, não é apresentado um p95 fictício.

## Validar

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/validar-slo.py
```

O ensaio usa a janela de um minuto: confirma seis intervalos reais no portal, disponibilidade adequada e violação do objetivo de latência na API com atraso de base. Para o Prometheus, confirma intervalos desconhecidos e conclusão inconclusiva no portal, repõe a recolha e aguarda que as lacunas saiam da janela móvel. Não injeta amostras sintéticas para obter estes resultados.

Resultado observado em 24/10/2026, às 21:24:31 UTC: seis intervalos e cobertura de 100% antes; durante a falha de recolha, cinco intervalos, um desconhecido, limites de disponibilidade de 83,333% a 100% e estado inconclusivo; depois, seis intervalos e resultado novamente avaliável. Evidência: validacao-slo.json.

**92 testes automáticos passaram**, com um aviso de depreciação Starlette/httpx. Incluem duplicados, valores inválidos, falhas rápidas, janelas incompletas, fronteiras de tempo, políticas, permissões e casos sem medições. A suite completa também detetou um problema de precisão no instante exato de escalonamento; a comparação foi corrigida para usar datas com a mesma precisão, com um teste de regressão determinístico.

A interface confirmou a mudança de janela e a edição do serviço **Exemplo · Ligação HTTP pausada**: o objetivo de respostas boas passou de 95% para **97,5% em até 600 ms**, guardando a política v2 e preservando a v1. O alvo permaneceu pausado.

Após reiniciar a aplicação, os objetivos, casos e ligações mantiveram-se. A janela de um minuto apresentou os dois portais rápidos dentro dos objetivos, a API lenta fora do objetivo de latência e o alvo pausado sem dados suficientes. Imagens: vista inicial e página completa.

## Limites operacionais

A cadência de dez segundos é uma hipótese explícita desta instalação. Alterá-la exige adaptar o cálculo e validar novamente a cobertura. Os relatórios têm, no máximo, sessenta grupos no gráfico por serviço, sem devolver todas as observações ao navegador.

O importador consulta os últimos dois minutos; interrupções mais longas da aplicação podem deixar lacunas em SQLite, mesmo que o Prometheus ainda conserve amostras antigas. Não existe recuperação integral desses períodos nem retenção/arquivo de longo prazo validado nesta entrega. As lacunas permanecem desconhecidas.

O histórico dos objetivos e as observações são preservados, mas ainda não existe relatório assinado ou inviolável. O restauro local e um ensaio curto de carga foram validados nas v0.9/v0.10. Faltam avaliação experimental numa organização real, ensaios prolongados e validação de produção. Os indicadores MTTA/MTTR anteriores continuam a incluir exemplos e ensaios; esta página exclui esses dados sintéticos do cálculo dos SLIs.

Referência conceptual para indicadores como razão de eventos bons/total e orçamento de erro: [Google SRE Workbook — Implementing SLOs](https://sre.google/workbook/implementing-slos/). As regras de intervalos, incerteza e versionamento acima descrevem as decisões concretas deste projeto.

Na v0.10 o cálculo é serializado e pode ser reutilizado por até três segundos, com invalidação por novas observações, políticas ou configuração. A API informa a idade e conserva o instante do cálculo original. Consultar seguranca-carga.md para o ensaio e os limites.
