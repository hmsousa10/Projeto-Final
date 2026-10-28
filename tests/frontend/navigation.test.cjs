const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../web/app.js'),'utf8');
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
function fixture(id){return {id,service_id:id,title:`Caso ${id}`,description:'Descrição confirmada',severity:'P1',status:'closed',source:'manual',timeline:[],evidence:[],resolution:'',assignee_id:1};}
function setup(){
  const handlers={},modalHandlers={},nodes={};
  function element(){return {innerHTML:'',textContent:'',open:false,isConnected:true,dataset:{},attributes:{},
    classList:{add(){},remove(){},toggle(){}},focus(){},setAttribute(k,v){this.attributes[k]=v;},removeAttribute(k){delete this.attributes[k];},
    addEventListener(){},showModal(){this.open=true;},close(){this.open=false;queueMicrotask(()=>modalHandlers.close?.());}};}
  for(const id of ['modal','modal-content','main','app','toast','breadcrumb','updated','nav-count','login-form'])nodes['#'+id]=element();
  nodes['#modal'].addEventListener=(name,fn)=>{modalHandlers[name]=fn;};
  const document={activeElement:element(),querySelector:s=>nodes[s]||null,querySelectorAll:()=>[],addEventListener:(name,fn)=>{handlers[name]=fn;}};
  const context=vm.createContext({document,window:{addEventListener:(name,fn)=>{handlers[name]=fn;}},location:{hash:'#services'},
    fetch:()=>new Promise(()=>{}),setInterval(){},clearInterval(){},setTimeout(){},clearTimeout(){},queueMicrotask,
    URLSearchParams,FormData:class{constructor(form){return new Map(Object.entries(form.values||{}));}},console});
  vm.runInContext(source,context,{filename:'web/app.js'});
  vm.runInContext(`user={id:1,name:'Operador',role:'admin'};config={};page='services';data={services:[{id:1,name:'Serviço 1',logs_available:false},{id:2,name:'Serviço 2',logs_available:false}],users:[{id:1,name:'Operador'}],incidentContext:{attention:[],laboratory:[],references:[],references_more:false},summary:{generated_at:'2026-10-28T12:00:00Z',active_incidents:0}};`,context);
  context.case1=fixture(1);context.case2=fixture(2);
  return {context,nodes,handlers,modalHandlers,run:code=>vm.runInContext(code,context)};
}
function caseApi(env){env.run(`api=async p=>p.startsWith('/knowledge')?{method:'Híbrido',results:[]}:p==='/incidents/1'?case1:case2;`);}

function companyFixture(){return {configured:true,status:'connected',adapter:'orders-summary-v1',checked_at:'2026-10-28T14:00:00Z',cache_seconds:5,latency_ms:2,summary:{company_id:'aurora',company_name:'Aurora <test>',environment:'laboratory',generated_at:'2026-10-28T14:00:00Z',orders:{total:3,preparing:1,shipped:1,delivered:1}}};}

function monitoringFixture(){return {configured:true,enabled:false,service_id:9,collection_state:'paused',last_sample:null,interval_seconds:10,active_incident_id:12,rule:{config:{failure_samples:2,recovery_samples:2}}};}

test('a retoma empresarial é explícita e só é apresentada ao administrador',()=>{
  const e=setup();e.context.monitoring=monitoringFixture();
  assert.match(e.run('enterpriseMonitoring(monitoring)'),/Recolha pausada/);
  assert.match(e.run('enterpriseMonitoring(monitoring)'),/Retomar recolha automática/);
  e.run("user={id:3,name:'Consulta',role:'viewer'}");
  assert.doesNotMatch(e.run('enterpriseMonitoring(monitoring)'),/data-action="enterprise-toggle"/);
});

test('o incidente da API continua acessível quando o resumo de negócio falha',async()=>{
  const e=setup();e.context.company={configured:true,status:'unavailable',checked_at:'2026-10-28T14:00:00Z',monitoring:monitoringFixture()};
  e.run('api=async()=>company;');const html=await e.run('enterprisePage()');
  assert.match(html,/Tratar INC-012/);assert.doesNotMatch(html,/Resumo dos pedidos/);
});

test('as regras incluem a API empresarial sem depender de uma ligação Prometheus',async()=>{
  const e=setup();e.run(`data.services=[{id:9,name:'Aurora API',enterprise_monitoring:{enabled:true}}];api=async p=>p==='/alert-rules'?[{service_id:9,service_name:'Aurora API',version:0,effective_latency_ms:500,config:{enabled:true,failure_samples:2,recovery_samples:2}}]:{status:'running'};`);
  const html=await e.run('alertRulesPage()');assert.match(html,/Aurora API/);assert.match(html,/Configurar regra/);
});

test('integração apresenta a empresa e identifica os dados fictícios sem HTML imposto',async()=>{
  const e=setup();e.context.company=companyFixture();e.run('api=async()=>company;');
  const html=await e.run('enterprisePage()');
  assert.match(html,/Aurora &lt;test&gt;/);assert.match(html,/os pedidos são fictícios/);
  assert.match(html,/Resumo dos pedidos/);assert.match(html,/Resposta validada/);
  assert.doesNotMatch(html,/<test>/);
});

test('uma falha na API empresarial não apresenta totais falsos nem sucesso',async()=>{
  for(const status of ['unavailable','unauthorized','stale','invalid_payload','not_configured']) {
    const e=setup();e.context.company={configured:status!=='not_configured',status,checked_at:'2026-10-28T14:00:00Z'};
    e.run('api=async()=>company;');const html=await e.run('enterprisePage()');
    assert.doesNotMatch(html,/Resumo dos pedidos|Resposta validada/);
    if(status!=='not_configured')assert.match(html,/Não se assume/);
  }
});

test('uma resposta empresarial atrasada não substitui outra página',async()=>{
  const e=setup();e.context.slow=deferred();e.run("page='enterprise';api=()=>slow.promise;servicesPage=()=>'<h1>Serviços atuais</h1>';");
  const pending=e.run('render()');await e.run("page='services';render()");
  e.context.slow.resolve(companyFixture());await pending;
  assert.equal(e.nodes['#main'].innerHTML,'<h1>Serviços atuais</h1>');
});

test('a área empresarial só é anunciada no menu quando configurada',()=>{
  const e=setup();e.run('config.enterprise=true;shell()');assert.match(e.nodes['#app'].innerHTML,/Integração empresarial/);
  e.run('config.enterprise=false;shell()');assert.doesNotMatch(e.nodes['#app'].innerHTML,/Integração empresarial/);
});

test('a avaliação preservada usa os nomes e estados guardados e escapa texto',()=>{
  const e=setup();e.context.entry={action:'Impacto potencial preservado',note:JSON.stringify({schema_version:1,evaluated_at:'2026-10-28T12:00:00Z',root:{id:1,name:'Base <antiga>',status:'unknown'},dependents:[{id:2,name:'Portal <antigo>',team:'Equipa',status:'down',parent_id:1,depth:1}],truncated:true})};
  e.run("data.services=[{id:2,name:'Nome posterior',dependencies:[]}]");
  const html=e.run('timelineNote(entry)');
  assert.match(html,/Portal &lt;antigo&gt;/);assert.match(html,/Indisponível/);
  assert.match(html,/lista parcial/);assert.match(html,/não confirma impacto real/);
  assert.doesNotMatch(html,/Nome posterior/);
  e.context.entry.note='<formato desconhecido>';
  assert.equal(e.run('timelineNote(entry)'),'<p>&lt;formato desconhecido&gt;</p>');
});

test('guardar avaliação só aparece para escrita em casos não fechados',async()=>{
  const e=setup();caseApi(e);
  await e.run('incidentModal(1)');assert.doesNotMatch(e.nodes['#modal-content'].innerHTML,/data-action="save-impact"/);
  e.context.case1={...fixture(1),status:'investigating'};
  await e.run('incidentModal(1)');assert.match(e.nodes['#modal-content'].innerHTML,/data-action="save-impact"/);
  e.run("user={id:3,name:'Consulta',role:'viewer'}");
  await e.run('incidentModal(1)');assert.doesNotMatch(e.nodes['#modal-content'].innerHTML,/data-action="save-impact"/);
});

test('guardar impacto não reabre um caso depois de mudar de janela',async()=>{
  const e=setup();caseApi(e);e.context.saved=deferred();
  e.run("const savedApi=api;api=(p,o)=>o?.method==='POST'?saved.promise:savedApi(p,o);modal('Caso original');");
  const target={dataset:{action:'save-impact',id:'1'},isConnected:true,disabled:false};
  const pending=e.handlers.click({target:{closest:()=>target}});
  e.run("closeModal();modal('<h2>Outro contexto</h2>')");target.isConnected=false;
  e.context.saved.resolve({ok:true});await pending;
  assert.match(e.nodes['#modal-content'].innerHTML,/Outro contexto/);assert.doesNotMatch(e.nodes['#modal-content'].innerHTML,/Caso 1/);
});

test('impacto percorre dependentes e deduplica uma cadeia com vários caminhos',()=>{
  const e=setup();
  e.context.catalog=[{id:1,dependencies:[]},{id:2,dependencies:[1,1]},{id:3,dependencies:[1]},{id:4,dependencies:[2,3]}];
  const result=e.run('dependencyImpact(1,catalog)');
  assert.deepEqual(Array.from(result.items,item=>[item.id,item.depth]),[[2,1],[3,1],[4,2]]);
  assert.deepEqual(Array.from(result.items[2].path),[1,2,4]);
  assert.equal(result.truncated,false);assert.equal(result.incomplete,false);
});

test('impacto não confunde pré-requisitos com serviços dependentes',()=>{
  const e=setup();e.context.catalog=[{id:1,dependencies:[]},{id:2,dependencies:[1]},{id:3,dependencies:[2,1]}];
  assert.deepEqual(Array.from(e.run('dependencyImpact(2,catalog)').items,item=>item.id),[3]);
  const result=e.run('dependencyImpact(1,catalog)');
  assert.equal(result.items.find(item=>item.id===3).depth,1);
});

test('ciclos antigos no inventário não bloqueiam a consulta nem incluem a raiz',()=>{
  const e=setup();e.context.catalog=[{id:1,dependencies:[3]},{id:2,dependencies:[1]},{id:3,dependencies:[2]}];
  const result=e.run('dependencyImpact(1,catalog)');
  assert.deepEqual(Array.from(result.items,item=>item.id),[2,3]);
});

test('impacto limita a 50 dependentes e avisa apenas quando há outros',()=>{
  const e=setup();e.context.catalog=Array.from({length:52},(_,n)=>({id:n+1,dependencies:n?[n]:[]}));
  const result=e.run('dependencyImpact(1,catalog)');
  assert.equal(result.items.length,50);assert.equal(result.truncated,true);
  assert.equal(result.items.at(-1).depth,50);
  e.context.catalog.pop();assert.equal(e.run('dependencyImpact(1,catalog)').truncated,false);
});

test('inventário incompleto não é apresentado como ausência de impacto',()=>{
  const e=setup();e.context.catalog=[{id:1,dependencies:[]},{id:2,dependencies:[99]}];
  assert.equal(e.run('dependencyImpact(1,catalog)').incomplete,true);
  assert.equal(e.run('dependencyImpact(42,catalog)').available,false);
  e.run('data.services=catalog');
  assert.match(e.run('impactPanel(1)'),/consulta parcial/);
  assert.doesNotMatch(e.run('impactPanel(1)'),/Não existem serviços dependentes/);
});

test('impacto distingue relações potenciais e estados observados com texto escapado',()=>{
  const e=setup();e.context.catalog=[{id:1,name:'Base <dados>',dependencies:[]},{id:2,name:'Portal <script>',team:'Equipa <b>',status:'healthy',dependencies:[1]}];
  e.run('data.services=catalog');const html=e.run('impactPanel(1)');
  assert.match(html,/1 serviço dependente/);assert.match(html,/Portal &lt;script&gt;/);
  assert.match(html,/Base &lt;dados&gt;/);assert.match(html,/Operacional/);
  assert.match(html,/não prova que este incidente o afetou/);assert.match(html,/não uma reconstituição/);
  assert.doesNotMatch(html,/<script>/);
});

test('incidentes e inventário apresentam o contexto de impacto sem operações de escrita',async()=>{
  const e=setup();caseApi(e);
  e.run(`data.services=[{id:1,name:'Base',dependencies:[],status:'unknown'},{id:2,name:'Portal',dependencies:[1],status:'healthy'}];`);
  await e.run('incidentModal(1)');assert.match(e.nodes['#modal-content'].innerHTML,/Impacto potencial · 1 serviço dependente/);
  assert.match(e.nodes['#modal-content'].innerHTML,/Relatório Markdown/);
  e.run('serviceModal(1)');assert.match(e.nodes['#modal-content'].innerHTML,/Impacto potencial · 1 serviço dependente/);
});

test('o carregamento comum usa resumos limitados em vez da lista completa',async()=>{
  const e=setup();e.context.paths=[];
  e.run(`api=async p=>{paths.push(p);return p==='/summary'?{services:[]}:p==='/incidents/context'?{attention:[],laboratory:[],references:[],references_more:false}:[];};`);
  await e.run('load()');
  assert.ok(e.context.paths.includes('/incidents/context'));
  assert.ok(!e.context.paths.includes('/incidents'));
  assert.equal(e.run('data.incidentContext.references.length'),0);
});

test('casos antigos podem ser indicados por número no conhecimento aplicado',async()=>{
  const e=setup();caseApi(e);e.context.case1={...fixture(1),status:'investigating'};
  await e.run('incidentModal(1)');
  assert.match(e.nodes['#modal-content'].innerHTML,/list="reference-cases"/);
  assert.match(e.nodes['#modal-content'].innerHTML,/Podes indicar o número de um caso mais antigo/);
  const posts=[];e.context.posts=posts;
  e.run(`api=async(p,o)=>{if(o?.method==='POST')posts.push(JSON.parse(o.body));return {ok:true};};load=async()=>true;render=async()=>false;`);
  const button={disabled:false},form={id:'knowledge-use-form',dataset:{id:'1'},values:{source_incident_id:'83',reason:'Passos consultados no caso mais antigo.'},isConnected:true,querySelector:s=>s==='button[type="submit"]'?button:{textContent:''}};
  // Simulate the dialog closing after a successful save, without opening another case.
  e.run('incidentModal=async()=>false;');
  await e.handlers.submit({target:form,preventDefault(){}});
  assert.equal(posts[0].source_incident_id,83);
});

test('referências inválidas não são arredondadas nem enviadas à API',async()=>{
  for(const value of ['1e3','-2','0','9007199254740993','INC-008']) {
    const e=setup();e.context.posts=[];e.run(`api=async()=>{posts.push(true);return {};};modal('Caso aberto');`);
    const error={textContent:''},form={id:'knowledge-use-form',dataset:{id:'1'},values:{source_incident_id:value,reason:'Passos consultados anteriormente.'},isConnected:true,querySelector:s=>s==='button[type="submit"]'?{disabled:false}:error};
    await e.handlers.submit({target:form,preventDefault(){}});
    assert.equal(e.context.posts.length,0);assert.match(error.textContent,/número de incidente válido/);
  }
});

test('a lista de incidentes envia os filtros e escapa o texto apresentado',async()=>{
  const e=setup();e.context.paths=[];
  e.run(`page='incidents';incidentFilters={view:'all',q:'<script>',service_id:'2',severity:'P1'};incidentCursor={before_id:'10',snapshot_id:'20'};api=async p=>{paths.push(p);return {items:[],limit:50,snapshot_id:20,next_before_id:5};};`);
  await e.run('render()');
  const params=new URLSearchParams(e.context.paths[0].split('?')[1]);
  assert.equal(params.get('q'),'<script>');assert.equal(params.get('service_id'),'2');
  assert.equal(params.get('before_id'),'10');assert.equal(params.get('snapshot_id'),'20');
  assert.match(e.nodes['#main'].innerHTML,/value="&lt;script&gt;"/);
  assert.match(e.nodes['#main'].innerHTML,/data-before="5"/);
});

test('filtrar por estado específico reinicia o cursor e seleciona todos os casos',async()=>{
  const e=setup();e.context.paths=[];
  e.run(`page='incidents';incidentCursor={before_id:'10',snapshot_id:'20'};api=async p=>{paths.push(p);return {items:[],limit:50,snapshot_id:20,next_before_id:null};};`);
  const button={disabled:false},form={id:'incident-filter-form',dataset:{},values:{status:'closed',service_id:'2',q:'INC-010'},isConnected:true,querySelector:s=>s==='button[type="submit"]'?button:{textContent:''}};
  await e.handlers.submit({target:form,preventDefault(){}});
  const params=new URLSearchParams(e.context.paths[0].split('?')[1]);
  assert.equal(params.get('status'),'closed');assert.equal(params.get('view'),'all');assert.equal(params.get('before_id'),null);
  assert.equal(params.get('q'),'INC-010');assert.equal(button.disabled,false);
});

test('uma pesquisa de incidentes atrasada não substitui outra seleção',async()=>{
  const e=setup();e.context.slow=deferred();
  e.run(`page='incidents';api=p=>p.includes('view=active')?slow.promise:Promise.resolve({items:[case2],limit:50,snapshot_id:2,next_before_id:null});`);
  const pending=e.run('render()');
  await e.run("incidentFilters={view:'all',q:'Caso 2'};render()");
  e.context.slow.resolve({items:[fixture(1)],limit:50,snapshot_id:2,next_before_id:null});await pending;
  assert.match(e.nodes['#main'].innerHTML,/Caso 2/);assert.doesNotMatch(e.nodes['#main'].innerHTML,/Caso 1/);
});

test('uma resposta antiga não substitui o incidente aberto mais recentemente',async()=>{
  const e=setup();e.context.slow=deferred();
  e.run(`api=async p=>p==='/incidents/1'?slow.promise:p==='/incidents/2'?case2:{method:'Híbrido',results:[]};`);
  const older=e.run('incidentModal(1)');assert.match(e.nodes['#modal-content'].innerHTML,/A carregar/);
  await e.run('incidentModal(2)');e.context.slow.resolve(fixture(1));await older;
  assert.match(e.nodes['#modal-content'].innerHTML,/Caso 2/);assert.doesNotMatch(e.nodes['#modal-content'].innerHTML,/Caso 1/);
});

test('fechar durante a consulta impede a reabertura tardia',async()=>{
  const e=setup();e.context.slow=deferred();e.run('api=()=>slow.promise;');
  const pending=e.run('incidentModal(1)');e.run('closeModal()');e.context.slow.resolve(fixture(1));await pending;
  assert.equal(e.nodes['#modal'].open,false);assert.doesNotMatch(e.nodes['#modal-content'].innerHTML,/Caso 1/);
});

test('erro de consulta antiga não altera outra janela',async()=>{
  const e=setup();e.context.slow=deferred();e.run('api=()=>slow.promise;');
  const pending=e.run('logsModal(1)');e.run("modal('<h2>Serviço escolhido depois</h2>')");
  e.context.slow.reject(new Error('Falha antiga'));await pending;
  assert.equal(e.nodes['#modal-content'].innerHTML.includes('Falha antiga'),false);
  assert.match(e.nodes['#modal-content'].innerHTML,/Serviço escolhido depois/);
});

test('evento close pendente não invalida uma nova janela',async()=>{
  const e=setup();e.context.slow=deferred();
  const pending=e.run("modal('Anterior');closeModal();modalContent(()=>slow.promise)");
  await Promise.resolve();e.context.slow.resolve('<h2>Atual</h2>');await pending;
  assert.equal(e.nodes['#modal'].open,true);assert.match(e.nodes['#modal-content'].innerHTML,/Atual/);
});

test('a página anterior não substitui a rota escolhida depois',async()=>{
  const e=setup();e.context.slow=deferred();e.run("sloPage=()=>slow.promise;servicesPage=()=>'<h1>Inventário atual</h1>';page='slo';");
  const pending=e.run('render()');await e.run("page='services';render()");e.context.slow.resolve('<h1>SLO antigo</h1>');await pending;
  assert.equal(e.nodes['#main'].innerHTML,'<h1>Inventário atual</h1>');assert.equal(e.nodes['#breadcrumb'].textContent,'Serviços');
  assert.equal(e.nodes['#main'].attributes['aria-busy'],undefined);
});

test('paginação antiga não invade outra página',async()=>{
  const e=setup();e.context.slow=deferred();const pending=e.run("pageContent(()=>slow.promise)");
  e.run("page='knowledge'");e.context.slow.resolve('<h1>Eventos antigos</h1>');await pending;
  assert.doesNotMatch(e.nodes['#main'].innerHTML,/Eventos antigos/);
});

test('falha nas sugestões permite consultar o incidente',async()=>{
  const e=setup();e.run("api=async p=>{if(p.startsWith('/knowledge'))throw new Error('Serviço de pesquisa indisponível');return case1;}");
  await e.run('incidentModal(1)');assert.match(e.nodes['#modal-content'].innerHTML,/Caso 1/);
  assert.match(e.nodes['#modal-content'].innerHTML,/Podes continuar a tratar o incidente/);
});

test('guardar uma nota não reabre o caso depois de mudar de janela',async()=>{
  const e=setup();caseApi(e);e.context.saved=deferred();e.run("const savedApi=api;api=(p,o)=>o?.method==='POST'?saved.promise:savedApi(p,o);load=async()=>true;servicesPage=()=>'<h1>Serviços</h1>';modal('Formulário original');");
  const button={disabled:false},error={textContent:''};
  const form={id:'comment-form',dataset:{id:'1'},values:{note:'Investigação confirmada'},isConnected:true,querySelector:s=>s==='button[type="submit"]'?button:error};
  const pending=e.handlers.submit({target:form,preventDefault(){}});
  e.run("closeModal();modal('<h2>Novo contexto</h2>')");form.isConnected=false;e.context.saved.resolve({ok:true});await pending;
  assert.match(e.nodes['#modal-content'].innerHTML,/Novo contexto/);assert.doesNotMatch(e.nodes['#modal-content'].innerHTML,/Caso 1/);
});

test('guardar evidência não substitui a janela que entretanto foi aberta',async()=>{
  const e=setup();caseApi(e);e.context.saved=deferred();e.run("const savedApi=api;api=(p,o)=>o?.method==='POST'?saved.promise:savedApi(p,o);modal('Incidente original');");
  const target={dataset:{action:'save-evidence',id:'1'},isConnected:true,disabled:false};
  const pending=e.handlers.click({target:{closest:()=>target}});
  e.run("closeModal();modal('<h2>Outro serviço</h2>')");target.isConnected=false;e.context.saved.resolve({id:3});await pending;
  assert.match(e.nodes['#modal-content'].innerHTML,/Outro serviço/);
});

test('uma resposta 401 antiga não termina uma sessão iniciada depois',async()=>{
  const e=setup();e.context.slow=deferred();e.context.fetch=()=>e.context.slow.promise;
  const pending=e.run("api('/services')");e.run("user={id:2,name:'Nova sessão',role:'viewer'};");
  e.context.slow.resolve({ok:false,status:401,json:async()=>({detail:'Sessão antiga expirada'})});
  await assert.rejects(pending,/Sessão antiga expirada/);assert.equal(e.run('user.id'),2);
});


test('erro de carregamento da página oferece uma nova tentativa',async()=>{
  const e=setup();e.run("sloPage=async()=>{throw new Error('<erro de rede>')};page='slo';");
  await e.run('render({loading:true})');
  assert.match(e.nodes['#main'].innerHTML,/Voltar a tentar/);assert.match(e.nodes['#main'].innerHTML,/&lt;erro de rede&gt;/);
  assert.equal(e.nodes['#main'].attributes['aria-busy'],undefined);
});

test('criar um incidente não fecha outra janela escolhida enquanto guardava',async()=>{
  const e=setup();caseApi(e);e.context.saved=deferred();
  e.run("const savedApi=api;api=(p,o)=>o?.method==='POST'?saved.promise:savedApi(p,o);load=async()=>true;modal('Novo incidente');");
  const button={disabled:false},form={id:'incident-form',dataset:{},values:{service_id:'1',title:'Falha confirmada'},isConnected:true,querySelector:s=>s==='button[type="submit"]'?button:{textContent:''}};
  const pending=e.handlers.submit({target:form,preventDefault(){}});
  e.run("closeModal();modal('<h2>Outro contexto</h2>')");form.isConnected=false;e.context.saved.resolve(fixture(1));await pending;
  assert.match(e.nodes['#modal-content'].innerHTML,/Outro contexto/);
});

test('a consulta de logs e os históricos apresentam os seus resultados',async()=>{
  const e=setup();e.run(`api=async p=>p.endsWith('/logs')?{service_name:'Pedidos Aurora',scope:{service_key:'portal-lab',path:'/api/orders',target_url:'http://portal-lab:8080/api/orders'},entries:[]}:[{version:2,actor:'Operador',config:{enabled:true,failure_samples:2,recovery_samples:2}}];`);
  await e.run('logsModal(1)');assert.match(e.nodes['#modal-content'].innerHTML,/Pedidos Aurora/);
  await e.run('sloHistory(1)');assert.match(e.nodes['#modal-content'].innerHTML,/Histórico de SLOs/);
  await e.run('ruleHistory(1)');assert.match(e.nodes['#modal-content'].innerHTML,/Versões da regra/);
});


test('marcar notificações não substitui a página visitada durante a gravação',async()=>{
  const e=setup();caseApi(e);e.context.saved=deferred();
  e.run("const savedApi=api;api=(p,o)=>o?.method==='POST'?saved.promise:savedApi(p,o);page='notifications';notificationsPage=async()=>'<h1>Notificações antigas</h1>';");
  const target={dataset:{action:'notices-read',through:'20'},disabled:false};
  const pending=e.handlers.click({target:{closest:()=>target}});
  await e.run("page='services';servicesPage=()=>'<h1>Serviços atuais</h1>';render()");
  e.context.saved.resolve({ok:true});await pending;
  assert.equal(e.nodes['#main'].innerHTML,'<h1>Serviços atuais</h1>');
});


test('outra empresa de referência não é apresentada como Aurora',async()=>{
  const e=setup();e.context.company=companyFixture();
  e.context.company.summary.company_id='atlas';e.context.company.summary.company_name='Atlas';
  e.run('api=async()=>company;');
  const html=await e.run('enterprisePage()');
  assert.match(html,/Atlas/);assert.doesNotMatch(html,/Aurora/);
});

test('instalação sem demonstração identifica integração configurada sem assumir sucesso',()=>{
  const e=setup();e.run('config.demo=false;config.enterprise=true;shell()');
  assert.match(e.nodes['#app'].innerHTML,/Integração empresarial configurada/);
  assert.doesNotMatch(e.nodes['#app'].innerHTML,/Telemetria externa ainda não ligada/);
});


test('a interface distingue o modo de produção do ambiente local',()=>{
  const e=setup();e.run("config.demo=false;config.environment='production';shell()");
  assert.match(e.nodes['#app'].innerHTML,/MODO PRODUÇÃO/);
  assert.doesNotMatch(e.nodes['#app'].innerHTML,/>AMBIENTE LOCAL</);
});
