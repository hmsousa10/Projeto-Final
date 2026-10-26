# Recuperação do conhecimento · v0.8

O portal pesquisa casos resolvidos ou fechados e apresenta o registo original. Não inventa diagnósticos, não escreve uma nova resolução nem executa o runbook. O operador confirma se o caso anterior se aplica ao incidente atual.

## Experimentar

1. Com o laboratório iniciado, abrir `http://127.0.0.1:8001/#knowledge`.
2. Pesquisar «As faturas ficam por emitir e os trabalhos pendentes não avançam». O exemplo sintético da fila de faturação surge como caso semelhante.
3. Comparar Híbrido, Semântico, BM25 e TF-IDF. Abrir o excerto e o incidente original para verificar a explicação.
4. Filtrar por serviço e origem. Os exemplos sintéticos são identificados; os casos detetados por Prometheus são sondagens do laboratório, não ocorrências numa empresa real.
5. Num incidente, consultar as sugestões na área de apoio à triagem. O próprio incidente é excluído antes da classificação.

A consulta e os filtros permanecem na página até nova pesquisa ou navegação; o refrescamento dos indicadores não elimina os resultados. Depois de fechar um caso, o índice é atualizado em segundo plano. Voltar a pesquisar para obter a atualização.

## Métodos e pontuações

- **TF-IDF**: baseline anterior preservado, com título, descrição, causa e resolução. Cosseno textual.
- **BM25**: pesquisa lexical com os mesmos campos e também prevenção, runbook e serviço; k1=1,2 e b=0,75. Esta comparação inclui diferenças nos campos, não isola apenas o algoritmo.
- **Semântico**: maior cosseno entre a consulta e até três excertos por caso. Só inclui resultados com cosseno ≥0,35; este limiar é uma heurística, não uma confiança calibrada.
- **Híbrido**: fusão por posição das listas BM25 e semântica. Cada presença acrescenta 1/(60+posição). A lista lexical pode introduzir resultados sem suporte semântico.

As pontuações não são probabilidades de diagnóstico correto. Resultados baixos, falsos positivos e ausência de correspondência são possíveis. O modelo pode aproximar frases sobre temas diferentes que partilham vocabulário. As palavras em comum são explicação lexical; o excerto é a secção com maior cosseno, não uma explicação causal do modelo.

O corpus global inclui os **100 incidentes resolvidos ou fechados mais recentes**, ordenados por ID. Os filtros e a exclusão do próprio caso restringem esse conjunto antes da classificação. A API informa a dimensão e se existem casos anteriores fora do corpus. Todos os perfis autenticados consultam o mesmo espaço de trabalho; estes filtros não implementam separação entre empresas ou equipas.

## Modelo local e limites

Usa-se `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revisão `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, ONNX `model_quint8_avx2.onnx`. Os dois artefactos descarregados têm SHA-256 verificado durante o build; ver `semantic/model.json`. Não se executa código Python fornecido pelo repositório do modelo. Licença declarada pelo fornecedor: Apache-2.0.

O serviço usa CPU, tokenizador local, mean pooling com máscara de atenção e normalização L2, produzindo 384 dimensões. Cada caso fornece até três excertos: sintomas, causa/resolução e prevenção/runbook. Cada excerto contém os primeiros 600 caracteres da concatenação desses campos e é truncado a 128 tokens. A consulta aceita até 2 000 caracteres e também é truncada a 128 tokens. Informação posterior pode ficar de fora. BM25 consulta os campos completos; não se deve atribuir toda a diferença observada exclusivamente aos embeddings.

A cache SQLite é identificada pelo hash da secção/conteúdo e pela versão exata do modelo. Um excerto alterado não reutiliza o vetor anterior. O trabalhador prepara até 16 excertos a cada cinco segundos e remove entradas obsoletas. Se faltar algum vetor da seleção, a pesquisa usa BM25 com aviso. Em caso de erro, timeout ou ocupação, o método efetivamente utilizado aparece explicitamente. Até dois pedidos semânticos do portal podem estar em curso; o encoder admite uma inferência de cada vez. Isto limita recursos, sem constituir uma avaliação de capacidade.

## Isolamento e segurança

O contentor `semantic` não publica portas e pertence apenas à rede interna do Compose. Usa um segredo próprio, processo sem privilégios, sistema de ficheiros só de leitura, todas as capabilities removidas, `no-new-privileges`, limite de 1 GiB e duas CPUs. Não monta o socket Docker. O encoder não necessita de Internet durante a inferência; a telemetria ONNX está desativada. O download do modelo ocorre no build, sem transmitir o histórico da aplicação.

O cliente utiliza apenas o endereço configurado pela instalação, ignora proxies do ambiente, recusa redirecionamentos, limita a resposta a 1 MiB e valida versão, número, dimensão, finitude e norma dos vetores. O serviço rejeita corpos acima de 64 KiB, lotes acima de 16 e textos vazios ou acima de 2 000 caracteres. Não regista textos nem segredos no access log. A rota pública de pesquisa exige uma sessão válida e nunca recebe um URL de destino do utilizador. Os resultados são escapados no HTML.

Consultas enviadas como GET podem ficar no histórico do navegador; evitar incluir segredos. A partir da v0.10 o access log Uvicorn omite a query string; logs antigos ou de proxies externos não são apagados por essa alteração. A base SQLite, os vetores e os segredos locais exigem as mesmas proteções de ficheiros e cópias de segurança que os restantes dados. Este bloco não constitui certificação nem prova de invulnerabilidade.

## Avaliação reproduzível

O ficheiro `evaluation/benchmark.json` foi congelado antes da primeira execução. Tem dez casos fictícios, quatro consultas de desenvolvimento e dezasseis de teste: doze com um caso esperado e quatro sem resposta útil. Inclui paráfrases em português, duas consultas de teste em inglês e perguntas fora do domínio. Não é lido nem inserido na base de incidentes.

O conjunto dev verifica o processo; não foi feito ajuste do modelo, limiar ou pesos após observar test. A separação por consulta não separa famílias de incidentes: ambos os grupos pesquisam o mesmo corpus fixo. As relevâncias são juízos manuais do autor do ensaio, ainda sem revisão independente. Trata-se de uma verificação pequena e sintética, não de um benchmark representativo ou teste estatístico.

Execução a partir da pasta do projeto, com Docker disponível no PATH:

```powershell
docker compose -p nexo-lab -f compose.observability.yaml exec -T nexo python -m app.evaluate_knowledge --output /tmp/knowledge-evaluation.json
docker compose -p nexo-lab -f compose.observability.yaml exec -T nexo python -c "from pathlib import Path; print(Path('/tmp/knowledge-evaluation.json').read_text())" | Set-Content evaluation/results-repeat.json -Encoding utf8
docker compose -p nexo-lab -f compose.observability.yaml exec -T nexo python -m evaluation.check_service
```

Os resultados originais estão em `evaluation/results-v0.8.json`, com SHA-256 do dataset, modelo, parâmetros, tempos e todas as listas devolvidas. A execução foi em CPU no Docker Desktop deste computador. Não substituir o resultado original ao repetir.

No grupo test, sem ajustar os parâmetros:

- TF-IDF: Recall@3 **0,50**, MRR@3 **0,50**, Precision@3 **0,1667**; abstenção correta em **2/4** perguntas sem resposta.
- BM25: Recall@3 **0,6667**, MRR@3 **0,6667**, Precision@3 **0,2222**; abstenção correta em **2/4**.
- Semântico: Recall@3 **1,00**, MRR@3 **0,9583**, Precision@3 **0,3333**; abstenção correta em **3/4**.
- Híbrido: Recall@3 **1,00**, MRR@3 **0,9444**, Precision@3 **0,3333**; abstenção correta em **2/4**.

Recall@3 e MRR@3 usam apenas as doze consultas com relevância. Precision@3 divide sempre por três, mesmo quando há menos resultados; com um caso relevante por consulta o máximo é 1/3. MRR é truncado a três. A abstenção é avaliada separadamente nas quatro consultas negativas. Tempos médios da primeira execução: TF-IDF 0,58 ms, BM25 0,61 ms, semântico 9,32 ms e híbrido 10,00 ms. A preparação dos 30 excertos demorou 299,63 ms. Os tempos semânticos incluem inferência e HTTP interno; não incluem indexação, autenticação, acesso à base, interface ou carga concorrente. Não são garantias de latência.

O semântico recuperou melhor estas paráfrases, mas devolveu três sugestões indevidas para «alterar a morada de faturação de um cliente». O híbrido também encontrou um falso positivo lexical para «criar relatórios contabilísticos em formato PDF». Guardaram-se estes erros; o limiar não foi alterado para melhorar retroativamente o teste. A melhoria neste conjunto não demonstra redução de MTTR ou qualidade em dados empresariais.

Próxima avaliação: corpus maior e revisto por outra pessoa, grupos por família de falha, calibração apenas em dev, novo teste reservado, comparação dos métodos com os mesmos campos e cenários operacionais repetidos.

## Validação da entrega

Suite completa: 103 testes aprovados. Após o reforço final, repetiram-se os doze testes de recuperação/cache/fallback/filtros/perfis/validação de vetores/métricas/limite do corpus; todos passaram, incluindo um novo teste (104 testes distintos aprovados no total). Há um aviso de descontinuação do adaptador httpx do TestClient. Validação adicional: build das duas imagens, inferência real, verificações negativas do encoder e pesquisa no navegador. O modelo foi parado e o aviso BM25 confirmado; depois foi reposto. As evidências visuais estão em `conhecimento-v08.png` e `conhecimento-v08-fallback.png`.

Fontes técnicas: [modelo e arquitetura](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) e [similaridade em Sentence Transformers](https://www.sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html).
