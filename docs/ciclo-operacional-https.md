# Ciclo operacional completo sobre HTTPS

Este ensaio usa a API fictícia privada de `nexo-preproduction`. Não altera a aplicação nem a versão 0.31: acrescenta uma verificação operacional reproduzível do fluxo já implementado.

## Repetir

```powershell
.venv\Scripts\python.exe scripts/https_cycle.py
```

São necessários os três ambientes ativos para a comparação do histórico. Só a API privada da pré-produção é interrompida. O script verifica projeto, serviço, comando da API fictícia, identidade, TLS, ausência de porta publicada e estado ativo antes de admitir uma interrupção. Também exige API saudável, recolha ativa, regras de confirmação 2/2 e ausência de um incidente ativo dessa API. Não muda as regras para forçar um resultado.

## O percurso realizado

1. Parar o contentor da API privada e aguardar o incidente criado pelas falhas reais de consulta HTTPS.
2. Atribuir um responsável, reconhecer e investigar o caso, com nota explícita de ensaio automatizado.
3. Tentar resolver enquanto a API está parada e confirmar a recusa do servidor.
4. Reiniciar o serviço e aguardar o evento de recuperação, após as amostras válidas exigidas.
5. Resolver, fechar com causa/prevenção/runbook e exportar o dossier.
6. Repetir a interrupção; neste segundo caso, pesquisar o primeiro com BM25 e preservar a referência aplicada antes do fecho.

Na execução de 28/10/2026, foram gerados e fechados os casos **INC-1 e INC-2 na pré-produção**. O segundo preserva a referência ao primeiro. Estes números pertencem à base isolada da pré-produção; não são os incidentes da Aurora principal ou da Atlas.

Os tempos registados foram cerca de 19,5 segundos para deteção e 20,5 segundos para recuperação confirmada. São tempos de um script e incluem a cadência de recolha e consulta; não medem desempenho humano, MTTA/MTTR humano ou melhoria numa empresa real.

## Evidências e estado final

O relatório da execução está em [validação do ciclo](validacao-ciclo-https-runtime.json). Os dossiers completos e o relatório por execução ficam em `data/https-cycles/<run_id>/`, ignorados pelo Git. A aplicação manteve a API disponível e a recolha ativa no final. Os hashes das tabelas históricas dos outros dois portais coincidiram com os valores anteriores ao ensaio.

As interrupções e os casos são reais no ambiente de ensaio; a empresa e as encomendas são fictícias. Não foram inseridas observações manualmente. A recuperação do conhecimento usou BM25 sobre um caso gerado no primeiro ciclo; não houve diagnóstico por um modelo generativo nem execução autónoma de uma recomendação de IA.

Cada repetição bem-sucedida cria dois novos incidentes de ensaio e conserva-os. O script tenta reiniciar o contentor se houver um erro depois da paragem e guarda um relatório da falha. Não fecha automaticamente um caso interrompido por um erro do teste: é necessário rever e tratar esse caso antes de repetir. Uma falha do Docker/anfitrião pode impedir a recuperação automática e exige intervenção; os relatórios não devem ser confundidos com uma garantia para qualquer avaria.

## Verificação desta entrega

Os testes dirigidos de monitorização e guardas iniciais passaram (15 testes). A guarda final, que exige também o comando da API fictícia, passou em 7 testes. Os dois ciclos reais e a consulta final dos casos fechados passaram. A aplicação não foi alterada; não foi repetida a suite completa de 306 testes da entrega anterior.
