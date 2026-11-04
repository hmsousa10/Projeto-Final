# Ligações de serviços · versão 0.4

O Nexo já permite associar novos serviços do inventário a endereços autorizados, sem alterar o código nem reiniciar a aplicação para cada ligação. O administrador escolhe o serviço e o endereço; o Prometheus descobre a ligação, o exporter faz as sondagens HTTP e o Nexo importa as medições e aplica as regras de incidente.

Esta versão não disponibiliza sondagens de qualquer URL introduzido pelo utilizador. A lista de destinos é uma decisão da instalação. O catálogo atual contém os dois endpoints de saúde do laboratório e o endpoint de consulta de pedidos da Aurora.

## Utilizar a interface

1. Iniciar a stack com `iniciar-laboratorio.cmd`.
2. Abrir http://127.0.0.1:8001/#services e criar um serviço com nome, equipa e objetivos. Para separar os históricos, escolher um serviço novo, sem observações sintéticas.
3. Abrir **Monitorização** e escolher **Ligar serviço**.
4. Selecionar o serviço do inventário e o endereço autorizado. É possível guardar a ligação já pausada ou ativar a recolha de imediato.
5. Aguardar novas sondagens. O catálogo atualiza-se a cada cinco segundos; as sondagens e a importação executam-se a cada dez segundos. São necessárias duas amostras distintas para confirmar alertas e recuperações.
6. Usar **Pausar recolha** ou **Retomar recolha** quando necessário. O histórico e os incidentes existentes mantêm-se.

Só o administrador pode criar ligações ou pausar/retomar a recolha. Operações e Leitura podem consultar o estado. Os alvos de referência do laboratório são geridos pela instalação e não podem ser alterados por este formulário.

O endereço de uma ligação com histórico é imutável. Para outro destino, criar um serviço separado. Existem limites de 50 endereços no catálogo e 50 ligações configuráveis, além das duas referências do laboratório.

## O que acontece durante uma pausa

A importação e a avaliação de alertas deixam de considerar o alvo assim que a pausa é guardada. O estado do serviço passa a desconhecido, mesmo que a última amostra tivesse sucesso. O incidente permanece aberto até ser tratado.

O Prometheus remove o alvo após a próxima atualização bem-sucedida da descoberta. **A pausa não garante interrupção instantânea dos pedidos HTTP:** se a descoberta estiver indisponível, o Prometheus pode continuar a usar a lista anterior. A importação no Nexo continua a rejeitar as amostras do alvo pausado.

Ao retomar, só contam sondagens posteriores à retoma. A aplicação não reutiliza amostras anteriores para declarar recuperação ou gerar um alerta. A resolução de um incidente automático exige alvo ativo, autorizado e recuperação recente confirmada.

## Autorizar destinos numa instalação

`MONITORING_ALLOWED_URLS` é uma lista JSON de endereços HTTP(S) completos, configurada pelo responsável pela instalação. No `compose.observability.yaml`, por exemplo:

```yaml
MONITORING_ALLOWED_URLS: '["http://portal-lab:8080/health","http://api-lab:8080/health","http://portal-lab:8080/api/orders"]'
```

A autorização exige correspondência exata: não existem wildcards, comparações por prefixo nem URLs livres. Não são aceites credenciais no URL, parâmetros de consulta, fragmentos ou esquemas diferentes de HTTP(S). O módulo de sondagem não segue redirecionamentos. A lista é validada no arranque e reaplicada na descoberta e na importação. Em perfil de produção não existe um catálogo implícito de destinos de laboratório.

Para uma empresa real, acrescentar apenas endpoints dentro do âmbito autorizado e preparar a conectividade de rede e a resolução DNS no deployment. A stack atual mantém o exporter numa rede interna Docker: adicionar um endereço externo ao catálogo, por si só, não cria conectividade. Credenciais para endpoints empresariais, TLS interno, política de saída por destino e integração geral de logs são trabalho de deployment e desenvolvimento ainda pendente.

A lista explícita reduz a exposição a sondagens indevidas, mas não substitui controlo de saída da rede ou gestão de DNS de confiança. Não é uma demonstração de ausência de SSRF em todos os deployments possíveis.

## Descoberta e segredos

O Prometheus consulta `/internal/targets` com uma chave própria em `Authorization: Bearer`. Uma sessão de utilizador não concede acesso a esse endpoint. A chave é gerada por `preparar-laboratorio.ps1`, guardada em `data/monitoring-discovery.key` e montada apenas no Nexo e no Prometheus; não é entregue ao navegador nem incluída na imagem. A pasta data é excluída do Git e do contexto de build.

As duas chaves locais são específicas da demonstração e devem ser substituídas e protegidas no deployment real. O transporte interno atual é HTTP numa rede Docker local; não está validado como deployment empresarial de produção.

O mapeamento das ligações e as datas de pausa/retoma são persistidos em SQLite. A migração do esquema é aditiva: preserva os IDs dos serviços, observações, incidentes e evidências existentes. As ações de configuração ficam na auditoria; pausas/retomas de serviços com incidentes ativos também ficam nas linhas temporais desses casos.

## Métricas e logs são ligações distintas

A configuração desta página recolhe sucesso HTTP e duração da sondagem. Não instala agentes nem recolhe automaticamente logs de uma empresa. Os logs Loki continuam mapeados apenas para os dois serviços de referência do laboratório; um novo serviço sem ligação de logs devolve «não ligado», em vez de simular registos ou tratar a ausência de logs como sucesso.

As amostras com mais de 45 segundos não definem estado atual. O importador consulta uma janela de dois minutos: uma interrupção prolongada da aplicação pode deixar lacunas no histórico SQLite, mesmo que o Prometheus conserve mais dados. As percentagens mostradas são proporções das amostras existentes, não comprovação de disponibilidade temporal ou SLA.

## Validação reproduzível

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/validar-monitorizacao.py
```

O ensaio configura **Aurora · Consulta de pedidos**, confirma a descoberta efetiva no Prometheus, provoca uma falha no serviço de laboratório, confirma o incidente, pausa a recolha e verifica a remoção do alvo e a preservação do histórico. Depois recupera o serviço, retoma as sondagens e fecha o caso com resolução e prevenção. O serviço fica ligado e operacional. Não executa falhas em endereços de empresas externas.

Validação observada em 24/10/2026: **57 testes passaram**, com um aviso de depreciação Starlette/httpx. O ensaio Docker terminou às 20:30:38 UTC com serviço **7**, alvo **service-7** e caso **INC-008** fechado. Resultado guardado em validacao-monitorizacao.json.

O percurso pela interface também foi verificado: criar serviço no inventário, selecionar endereço autorizado, guardar uma ligação inicialmente pausada e pausar/retomar uma ligação ativa. Foi deixado o serviço **Exemplo · Ligação HTTP pausada** sem iniciar sondagens, para experimentar a retoma. A ligação **Aurora · Consulta de pedidos** permanece ativa.

Após reiniciar a aplicação, os quatro mapeamentos foram preservados: três ativos e um pausado; o caso INC-008 continuou fechado. Imagem da interface validada.

Referência do protocolo: [HTTP Service Discovery do Prometheus](https://prometheus.io/docs/prometheus/latest/http_sd/).
