/* Interface sem dependências. Todos os dados operacionais vêm da API local. */
const $ = (s, root = document) => root.querySelector(s);
const e = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const states = {open:'Aberto', acknowledged:'Reconhecido', investigating:'Em investigação', resolved:'Resolvido', closed:'Fechado'};
const statuses = {healthy:'Operacional', down:'Indisponível', degraded:'Degradado', unknown:'Sem dados recentes'};
const roles = {admin:'Administrador',operator:'Operações',viewer:'Leitura'};
const icons = {
  overview:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  services:'<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M12 6.5h5M12 17.5h5"/>',
  incidents:'<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5M12 17h.01"/>',
  knowledge:'<path d="M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-2H4V4Zm16 0h-4a3 3 0 0 0-3 3m7-3v15h-3a4 4 0 0 0-4 2"/>',
  notifications:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  audit:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  guide:'<path d="M5 3h10l4 4v14H5V3Zm9 0v5h5M8 12h8M8 16h6"/>',
  arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  logout:'<path d="M9 4H4v16h5m5-13 5 5-5 5m-6-5h13"/>',
  search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.overview}</svg>`;
const fmtDate = value => value ? new Date(value).toLocaleString('pt-PT', {day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}) : '—';
const number = (value, digits=1) => value == null ? '—' : Number(value).toLocaleString('pt-PT',{maximumFractionDigits:digits});
const duration = seconds => seconds == null ? '—' : seconds < 60 ? `${number(seconds,0)} s` : `${number(seconds/60)} min`;
let user, config, data = {}, page = 'overview', sloWindow = '15m', refreshTimer, notificationTimer, lastFocus;
let visibleNoticeLatest=0, noticeBusy=false;
let pageRequest=0, modalRequest=0;
let incidentFilters={view:'active'}, incidentCursor={};
const editable = () => user?.role !== 'viewer';
const admin = () => user?.role === 'admin';

async function api(path, options = {}) {
  const requestUser=user;
  const response = await fetch(`/api${path}`, {credentials:'same-origin', ...options,
    headers:{'Content-Type':'application/json', ...(options.headers || {})}});
  let body;
  try { body = await response.json(); } catch { body = {}; }
  if (!response.ok) {
    if (response.status === 401 && path !== '/login' && requestUser===user) {
      clearInterval(refreshTimer); clearInterval(notificationTimer); user = null; closeModal(); loginScreen();
    }
    const detail = Array.isArray(body.detail) ? body.detail.map(x => `${x.loc.at(-1)}: ${x.msg}`).join(' · ') : body.detail;
    throw new Error(detail || `Pedido falhou (${response.status}).`);
  }
  return body;
}
const post = (path, body) => api(path, {method:'POST',body:JSON.stringify(body)});
function incidentRevision(form) {
  const raw=form.dataset.revision;
  const revision=Number(raw);
  if(!/^[0-9]+$/.test(raw||'') || !Number.isSafeInteger(revision))
    throw new Error('Reabre o incidente para obter a versão atual antes de guardar.');
  return revision;
}
function toast(message) {
  $('#toast').textContent = message; $('#toast').classList.add('visible');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => $('#toast').classList.remove('visible'), 4800);
}
function modal(html, wide = false) {
  const dialog=$('#modal');
  ++modalRequest;
  if(!dialog.open) lastFocus=document.activeElement;
  $('#modal-content').innerHTML = `<button class="close-modal" data-action="close" aria-label="Fechar janela">×</button>${html}`;
  dialog.classList.toggle('wide',wide);
  if(!dialog.open) dialog.showModal();
  return modalRequest;
}
function closeModal() { ++modalRequest; if($('#modal').open) $('#modal').close(); }
$('#modal').addEventListener('cancel',()=>{++modalRequest;});
$('#modal').addEventListener('close',()=>{
  // A queued close event may belong to a previous dialog, already replaced.
  if(!$('#modal').open) {++modalRequest;if(lastFocus?.isConnected)lastFocus.focus();}
});
async function modalContent(getHtml,wide=false) {
  const request=modal('<div class="request-state" role="status"><span class="eyebrow teal">CONSULTA EM CURSO</span><h2 id="modal-title">A carregar dados…</h2><p>Podes fechar esta janela enquanto aguardas.</p></div>',wide);
  const owner=user, origin=page;
  const current=()=>request===modalRequest && user===owner && page===origin && $('#modal').open;
  try {
    const html=await getHtml(current);
    if(!current()) return false;
    if(html==null) {closeModal();return false;}
    $('#modal-content').innerHTML=`<button class="close-modal" data-action="close" aria-label="Fechar janela">×</button>${html}`;
    return true;
  } catch(error) {
    if(current()) $('#modal-content').innerHTML=`<button class="close-modal" data-action="close" aria-label="Fechar janela">×</button><h2 id="modal-title">Não foi possível carregar</h2><p role="alert">${e(error.message)}</p><p class="muted">Fecha a janela e volta a tentar.</p>`;
    return false;
  }
}
async function pageContent(getHtml,{loading=false}={}) {
  const request=++pageRequest, owner=user, origin=page, root=$('#main');
  const current=()=>request===pageRequest && user===owner && page===origin && root===$('#main');
  root.setAttribute('aria-busy','true');
  if(loading) root.innerHTML='<div class="request-state" role="status"><h2>A carregar página…</h2></div>';
  try {
    const html=await getHtml();
    if(!current()) return false;
    root.innerHTML=html;return true;
  } catch(error) {
    if(current()) {
      if(loading) {root.innerHTML=`<div class="request-state" role="alert"><h2>Não foi possível carregar a página</h2><p>${e(error.message)}</p><button class="button secondary" data-action="retry-page">Voltar a tentar</button></div>`;return false;}
      throw error;
    }
    return false;
  }
  finally {if(current()) root.removeAttribute('aria-busy');}
}
$('#modal').addEventListener('click', event => { if (event.target === $('#modal')) closeModal(); });

function loginScreen(error = '') {
  ++pageRequest;closeModal();visibleNoticeLatest=0;data={};incidentFilters={view:'active'};incidentCursor={};
  $('#app').innerHTML = `<div class="login-layout">
    <section class="login-story"><a class="brand" href="/" aria-label="Nexo início"><img src="/static/favicon.svg" alt="">nexo<span>OPERAÇÕES</span></a>
      <div class="story-body"><span class="eyebrow">OBSERVABILIDADE COM CONTEXTO</span><h1>Perceber a falha.<br>Encontrar a resposta.</h1>
      <p>Serviços, incidentes e conhecimento operacional no mesmo lugar.</p><div class="signal-art" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span></div></div>
      <footer>PROJETO I · ENGENHARIA INFORMÁTICA <span>2026 / 27</span></footer></section>
    <main class="login-form" id="main"><div class="login-box"><span class="eyebrow teal">CENTRO DE OPERAÇÕES</span><h2>Bem-vindo ao Nexo</h2><p class="muted">Inicia sessão para acompanhar os teus serviços.</p>
      <form id="login-form"><label>Email<input name="email" type="email" autocomplete="username" value="${config?.demo ? 'admin@local.test' : ''}" required></label>
      <label>Palavra-passe<input name="password" type="password" autocomplete="current-password" required></label>
      <p class="form-error" role="alert">${e(error)}</p><button class="button primary full" type="submit">Entrar no centro de operações ${icon('arrow')}</button></form>
      ${config?.demo ? '<div class="demo-access"><span class="tag">DEMONSTRAÇÃO LOCAL</span><p>Palavra-passe inicial: <code>EstudoLocal2026!</code></p><small>Dados sintéticos para explorar o projeto. Se alteraste a palavra-passe na configuração, usa o novo valor.</small></div>' : ''}
      <p class="login-credit">Hugo Sousa · a22405716<br>Universidade Lusófona do Porto</p></div></main></div>`;
  $('#login-form').addEventListener('submit', async event => {
    event.preventDefault(); const button = $('button', event.target); button.disabled = true;
    try { user = await post('/login', Object.fromEntries(new FormData(event.target))); await start(); }
    catch(error) { $('.form-error', event.target).textContent = error.message; button.disabled = false; }
  });
}

function shell() {
  const navigation = [['overview','Visão geral'],['services','Serviços'],['incidents','Incidentes'],['knowledge','Base de conhecimento'],['notifications','Notificações']];
  if (config.enterprise) navigation.push(['enterprise','Integração empresarial']);
  if (config.telemetry==='prometheus') navigation.push(['slo','Objetivos e SLOs']);
  if (config.monitoring) navigation.push(['monitoring','Monitorização']);
  if (config.monitoring||config.enterprise) navigation.push(['alert-rules','Regras de alerta']);
  if (config.laboratory) navigation.push(['laboratory','Laboratório empresarial']);
  if (admin()) navigation.push(['users','Utilizadores'],['audit','Auditoria']);
  $('#app').innerHTML = `<div class="workspace"><aside class="sidebar"><a class="brand" href="#overview"><img src="/static/favicon.svg" alt="">nexo<span>OPERAÇÕES</span></a>
    <div class="workspace-label"><span class="workspace-icon">HS</span><div>Projeto académico<small>${config.environment==='production'?'Modo produção':'Ambiente local'}</small></div></div>
    <span class="nav-caption">ESPAÇO DE TRABALHO</span><nav aria-label="Navegação principal">${navigation.map(([id,label]) => `<a href="#${id}" data-page="${id}">${icon(id)}<span>${label}</span>${id==='incidents'?'<span id="nav-count" class="nav-count">0</span>':''}</a>`).join('')}</nav>
    <div class="sidebar-bottom"><a href="#guide" data-page="guide">${icon('guide')}Guia do projeto</a><div class="profile"><span class="avatar">${e(user.name.slice(0,2).toUpperCase())}</span><div><strong>${e(user.name)}</strong><small>${roles[user.role]}</small></div><button class="icon-button" data-action="logout" title="Terminar sessão" aria-label="Terminar sessão">${icon('logout')}</button></div></div></aside>
    <div class="workspace-body"><header class="topbar"><div><span class="topbar-label">NEXO /</span> <span id="breadcrumb">Visão geral</span></div><div class="topbar-right"><span class="tag">${config.demo?'DEMONSTRAÇÃO':config.environment==='production'?'MODO PRODUÇÃO':'AMBIENTE LOCAL'}</span><span id="updated"></span><a href="#notifications" class="notification-bell" id="notification-bell" aria-label="Notificações">${icon('notifications')}<span id="notification-count" aria-hidden="true">0</span></a><button class="text-button" data-action="account">Minha conta</button></div></header>
    ${config.demo ? `<div class="environment-note"><span class="dot"></span>Ambiente de demonstração <span class="note-detail">${config.telemetry==='prometheus'?'Sondagens reais no laboratório; exemplos sintéticos nos restantes serviços.':'Os serviços e as observações são sintéticos. Ainda sem ligação a sistemas reais.'}</span></div>` : '<div class="environment-note">'+(config.enterprise?'Integração empresarial configurada. Consulta o estado da ligação e dos serviços.':config.monitoring?'Monitorização configurada. Consulta o estado dos serviços.':'Ainda sem integração externa. Regista os teus serviços para começar.')+'</div>'}
    <main id="main" tabindex="-1"></main><footer class="workspace-footer"><span>Nexo <b>0.31</b> · Projeto I</span><span>Observabilidade e operações assistidas por IA</span></footer></div></div>`;
}

async function load() {
  const owner=user;
  const [summary, incidentContext, users, telemetry] = await Promise.all([api('/summary'), api('/incidents/context'), api('/users'), api('/telemetry')]);
  if(user!==owner || !user) return false;
  data = {summary, incidentContext, users, telemetry, services:summary.services};return true;
}
async function start() {
  if(user.must_change_password) {passwordScreen();return;}
  await load(); shell();
  page = location.hash.slice(1) || 'overview';
  await render();
  visibleNoticeLatest=page==='notifications'?visibleNoticeLatest:0;
  await refreshNotifications();
  clearInterval(notificationTimer);
  notificationTimer=setInterval(refreshNotifications,10000);
  clearInterval(refreshTimer);
  refreshTimer = setInterval(async () => {
    if ($('#modal').open || document.hidden || ['knowledge','notifications','audit','incidents'].includes(page) || ['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName)) return;
    const origin=page, request=pageRequest;
    try {await load();if(page===origin && pageRequest===request && !$('#modal').open && !['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName))await render();}catch(error){if(user)toast(error.message);}
  },10000);
}
const heading = (eyebrow,title,description,action='') => `<div class="page-heading"><div><span class="eyebrow teal">${eyebrow}</span><h1>${title}</h1><p>${description}</p></div>${action}</div>`;
const badge = (value,label=value) => `<span class="badge ${e(value)}">${e(label)}</span>`;
const empty = (title,text) => `<div class="empty">${icon('services')}<h3>${title}</h3><p>${text}</p></div>`;
function sparkline(samples) {
  if (!samples.length) return '<span class="muted">Sem amostras</span>';
  const max = Math.max(...samples.map(s=>s.latency_ms),1);
  const points = samples.map((s,i) => `${i*120/Math.max(samples.length-1,1)},${30-s.latency_ms/max*24}`).join(' ');
  return `<svg class="sparkline" viewBox="0 0 124 36" role="img" aria-label="Latência das últimas ${samples.length} observações"><path d="M0 32h124" class="chart-grid"/><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2"/></svg>`;
}
function serviceTable() {
  if (!data.services.length) return empty('Ainda sem serviços','Cria o primeiro serviço para definir responsáveis e objetivos.');
  return `<div class="table-scroll"><table><thead><tr><th>Serviço / equipa</th><th>Estado atual</th><th>Sucesso das sondagens · 24 h</th><th>Latência atual</th><th>Tendência</th><th></th></tr></thead><tbody>${data.services.map(s=>`<tr><td><button class="text-button service-name" data-service="${s.id}"><span class="service-glyph">${e(s.name.slice(0,1))}</span>${e(s.name)}</button><small class="cell-sub">${e(s.team)} · ${s.telemetry_source==='enterprise'?'API empresarial autenticada':s.telemetry_source==='prometheus'?'Sondagem HTTP':s.latest?.source==='demo'?'Exemplo sintético':'Sem integração'}</small></td><td>${badge(s.status,statuses[s.status])}</td><td><strong class="numeric">${number(s.availability,3)}${s.availability==null?'':'%'}</strong><small class="cell-sub">Objetivo: ${number(s.slo_availability,3)}% · ${s.sample_count} amostras</small></td><td><span class="numeric">${s.latest ? number(s.latest.latency_ms,0)+' ms':'—'}</span><small class="cell-sub">Objetivo ≤ ${s.slo_latency_ms} ms</small></td><td>${sparkline(s.history)}</td><td><button class="icon-button" data-service="${s.id}" aria-label="Ver ${e(s.name)}">${icon('arrow')}</button></td></tr>`).join('')}</tbody></table></div>`;
}
function incidentRows(rows) {
  if (!rows.length) return empty('Nenhum incidente nesta vista','Os novos incidentes aparecem aqui com a respetiva prioridade e responsável.');
  return `<div class="table-scroll"><table><thead><tr><th>Prioridade</th><th>Incidente</th><th>Estado</th><th>Responsável</th><th>Registo</th><th></th></tr></thead><tbody>${rows.map(i=>`<tr><td>${badge(i.severity)}</td><td><button class="text-button incident-title" data-incident="${i.id}">${e(i.title)}</button><small class="cell-sub">INC-${String(i.id).padStart(3,'0')} · ${e(i.service_name)}${i.source.startsWith('demo')?' · Exemplo sintético':''}</small></td><td>${badge(i.status,states[i.status])}</td><td>${e(i.assignee_name || 'Por atribuir')}</td><td class="nowrap muted">${fmtDate(i.created_at)}</td><td><button class="icon-button" data-incident="${i.id}" aria-label="Abrir incidente ${i.id}">${icon('arrow')}</button></td></tr>`).join('')}</tbody></table></div>`;
}
function telemetryPanel() {
  const t = data.telemetry;
  if (!t.enabled) return '';
  const labels = {connected:'Recolha ativa',incomplete:'Cobertura incompleta',unavailable:'Prometheus indisponível',waiting:'A aguardar recolha',no_targets:'Sem alvos ativos',stale:'Recolha desatualizada'};
  return `<section class="panel telemetry-panel" aria-label="Estado da telemetria"><div><span class="eyebrow teal">SONDAGENS HTTP REAIS</span><h2>${e(labels[t.status] || 'Estado desconhecido')}</h2><p>Prometheus recolhe os alvos ativos a cada 10 segundos. Os exemplos iniciais mantêm dados sintéticos e contribuem para os tempos médios de incidentes.</p></div><div class="telemetry-readout"><strong>${t.fresh_targets ?? 0}<small> / ${t.expected_targets ?? 0}</small></strong><span>alvos com amostras recentes</span><small>Última tentativa: ${fmtDate(t.last_attempt)}</small></div></section>`;
}
function overview() {
  const s = data.summary, healthy = data.services.filter(s=>s.status==='healthy').length;
  return heading('CENTRO DE OPERAÇÕES','O teu sistema, em perspetiva.','Acompanha o estado dos serviços e concentra a atenção no que precisa de resposta.',
    editable() && config.demo ? '<button class="button primary" data-action="scenario">'+icon('plus')+' Simular cenário</button>' : '')+
    telemetryPanel()+`<section class="metrics" aria-label="Indicadores de operação"><article><span>Serviços operacionais</span><strong>${healthy}<small> / ${data.services.length}</small></strong><p><span class="dot"></span> Estado da última observação</p></article>
    <article><span>Incidentes ativos</span><strong>${s.active_incidents.toString().padStart(2,'0')}</strong><p>${s.critical_incidents ? s.critical_incidents+' com prioridade crítica' : 'Nenhum incidente crítico ativo'}</p></article>
    <article><span>Tempo até reconhecer · MTTA</span><strong>${duration(s.mtta.seconds)}</strong><p>Desde o registo · ${s.mtta.count} incidentes</p></article>
    <article><span>Tempo até resolver · MTTR</span><strong>${duration(s.mttr.seconds)}</strong><p>Desde o registo · ${s.mttr.count} incidentes</p></article></section>
    <section class="panel"><div class="section-heading"><div><h2>Estado dos serviços</h2><p>Últimas 24 horas · amostras ${config.telemetry==='prometheus'?'reais no laboratório e sintéticas nos exemplos':config.demo?'de demonstração':'disponíveis'}</p></div><a href="#services" class="subtle-link">Ver inventário ${icon('arrow')}</a></div>${serviceTable()}<p class="panel-footnote">A percentagem é a proporção de sondagens bem-sucedidas, não disponibilidade temporal nem cumprimento de SLA. Sondagens Prometheus expiram ao fim de 45 segundos; exemplos sintéticos, ao fim de 15 minutos.</p></section>
    <section class="panel"><div class="section-heading"><div><h2>A necessitar de atenção</h2><p>Incidentes abertos, reconhecidos ou em investigação</p></div><a href="#incidents" class="subtle-link">Todos os incidentes ${icon('arrow')}</a></div>${incidentRows(data.incidentContext.attention)}</section>
    <div class="next-step"><span class="step-number">01</span><div><strong>Experimenta o ciclo completo</strong><p>Simula uma falha, atribui o incidente e regista a resolução. Cada ação fica na linha temporal.</p></div><button class="text-button" data-action="guide">Consultar guia ${icon('arrow')}</button></div>`;
}
function servicesPage() {
  return heading('INVENTÁRIO','Serviços e dependências','Define o que é crítico, quem responde e quais são os objetivos de cada serviço.',admin()?'<button class="button primary" data-action="new-service">'+icon('plus')+' Novo serviço</button>':'')+
    `<section class="panel"><div class="section-heading"><h2>Inventário <span class="count">${data.services.length}</span></h2><span class="muted">Seleciona um serviço para consultar dependências</span></div>${serviceTable()}</section>`;
}
async function incidentsPage() {
  // Capture the complete selection before awaiting: later requests may choose other filters.
  const filters={...incidentFilters}, cursor={...incidentCursor};
  const params=new URLSearchParams({...filters,...cursor,limit:'50'});
  const feed=await api('/incidents/browse?'+params);
  const select=(name,label,options)=>`<label>${label}<select name="${name}">${options.map(([value,text])=>`<option value="${e(value)}" ${String(filters[name]??'')===String(value)?'selected':''}>${e(text)}</option>`).join('')}</select></label>`;
  return heading('GESTÃO DE INCIDENTES','Da deteção à resolução.','Consulta os casos, encontra o contexto e acompanha cada decisão.',editable()?'<button class="button primary" data-action="new-incident">'+icon('plus')+' Registar incidente</button>':'')+
    `<section class="panel incident-browser"><div class="filter-bar"><div class="tabs" role="group" aria-label="Filtrar incidentes">${[['active','Ativos'],['history','Resolvidos'],['all','Todos']].map(([id,label])=>`<button data-filter="${id}" class="${filters.view===id?'selected':''}" aria-pressed="${filters.view===id}">${label}</button>`).join('')}</div><button class="text-button teal" data-action="incidents-refresh">Atualizar recentes</button></div>
    <form id="incident-filter-form" class="incident-filters"><label class="incident-query">Número ou texto<input name="q" type="search" maxlength="200" value="${e(filters.q||'')}" placeholder="INC-010 ou erro 503"></label>
    ${select('service_id','Serviço',[['','Todos os serviços'],...data.services.map(s=>[s.id,s.name])])}
    ${select('severity','Prioridade',[['','Todas as prioridades'],...['P1','P2','P3','P4'].map(p=>[p,p])])}
    ${select('status','Estado específico',[['','Todos os estados desta vista'],...Object.entries(states)])}
    ${select('assignee_id','Responsável',[['','Todos os responsáveis'],['0','Por atribuir'],...data.users.map(u=>[u.id,u.name])])}
    ${select('scope','Origem',[['all','Todas as origens'],['operational','Laboratório e registos manuais'],['examples','Exemplos sintéticos']])}
    <label>Desde · dia UTC<input type="date" name="date_from" value="${e(filters.date_from||'')}"></label><label>Até · dia UTC<input type="date" name="date_to" value="${e(filters.date_to||'')}"></label>
    <div class="incident-filter-actions"><button class="button primary" type="submit">Aplicar filtros</button><button class="button secondary" type="button" data-action="incidents-clear">Limpar filtros</button></div><p class="form-error" role="alert"></p></form></section>
    <section class="panel incident-results" aria-label="Resultados dos incidentes"><div class="section-heading"><div><span class="eyebrow teal">${cursor.before_id?'HISTÓRICO':'MAIS RECENTES'}</span><h2>${feed.items.length} ${feed.items.length===1?'incidente':'incidentes'} nesta página</h2><p>Ordenados pelo número, do mais recente para o mais antigo.</p></div><span class="tag">ATÉ ${feed.limit} POR PÁGINA</span></div>
    ${incidentRows(feed.items)}<div class="incident-pagination">${cursor.before_id?'<button class="button secondary" data-action="incidents-refresh">Voltar aos recentes</button>':''}${feed.next_before_id?`<button class="button secondary" data-action="incidents-older" data-before="${feed.next_before_id}" data-snapshot="${feed.snapshot_id}">Ver incidentes mais antigos</button>`:''}</div></section>
    <p class="incident-browser-note">Os filtros de data usam o dia de registo em UTC. Os horários são apresentados na hora local. Novos casos aparecem ao atualizar os recentes; estados e responsáveis refletem o momento de cada consulta.</p>`;
}
function enterpriseMonitoring(m) {
  if(!m?.service_id)return '';
  const labels={paused:'Recolha pausada',running:'Recolha ativa',waiting:'A aguardar consultas',stale:'Recolha desatualizada',disabled:'Recolha desativada'};
  return `<section class="panel enterprise-state"><span class="eyebrow teal">DETEÇÃO AUTOMÁTICA / API</span><h2>${e(labels[m.collection_state]||'Estado desconhecido')}</h2><p>Uma consulta a cada ${m.interval_seconds} segundos · ${m.rule.config.failure_samples} falhas para confirmar · ${m.rule.config.recovery_samples} respostas válidas dentro do limite para confirmar recuperação. As regras configuradas também avaliam latência e prazo de reconhecimento.</p><p>Última amostra: ${fmtDate(m.last_sample)}. Uma pausa não confirma recuperação nem fecha incidentes.</p><div class="enterprise-links"><button class="button secondary" data-service="${m.service_id}">Consultar serviço da API</button><a class="button secondary" href="#alert-rules">Consultar regras</a>${m.active_incident_id?`<button class="button primary" data-incident="${m.active_incident_id}">Tratar INC-${String(m.active_incident_id).padStart(3,'0')}</button>`:''}${admin()&&m.configured?`<button class="text-button teal" data-action="enterprise-toggle" data-enabled="${!m.enabled}">${m.enabled?'Pausar recolha automática':'Retomar recolha automática'}</button>`:''}</div></section>`;
}
async function enterprisePage() {
  const result=await api('/enterprise/summary');
  const monitoring=enterpriseMonitoring(result.monitoring);
  const labels={not_configured:'Integração por configurar',busy:'Consulta em curso',unavailable:'Ligação à API indisponível',unauthorized:'A API recusou a autenticação',invalid_payload:'Resposta fora do contrato esperado',stale:'Dados fora da janela de frescura'};
  const intro=heading('EMPRESA / API DE OPERAÇÕES','O negócio ligado à operação.','Consulta dados da API empresarial e acompanha a ligação aos serviços monitorizados.', '<button class="button secondary" data-action="enterprise-refresh">Atualizar consulta</button>');
  if(result.status!=='connected')return intro+`<section class="panel enterprise-state" role="status"><span class="eyebrow teal">ESTADO DA LIGAÇÃO</span><h2>${e(labels[result.status]||'Estado indisponível')}</h2><p>${result.configured?'Não há dados empresariais válidos para apresentar nesta consulta. Não se assume que os pedidos estejam disponíveis ou que os totais sejam zero.':'A ligação ainda não foi configurada nesta instalação.'}</p><p>Consulta Nexo: ${fmtDate(result.checked_at)}.</p><a class="button secondary" href="#monitoring">Consultar monitorização</a></section>`+monitoring;
  const summary=result.summary;
  return intro+`<section class="enterprise-hero"><div class="enterprise-mark" aria-hidden="true">${e(summary.company_name.slice(0,1))}</div><div><span class="eyebrow">${e(summary.company_id.toUpperCase())} / ${summary.environment==='laboratory'?'EMPRESA FICTÍCIA':'API EMPRESARIAL'}</span><h2>${e(summary.company_name)}</h2><p>${summary.environment==='laboratory'?'Dados de demonstração servidos pela API empresarial de referência. A ligação HTTP e a autenticação são reais; os pedidos são fictícios.':'Resumo fornecido pela API configurada. Confirma o âmbito e as definições com a organização.'}</p></div><span class="tag">API · LEITURA</span></section>
    <section class="metrics enterprise-metrics" aria-label="Resumo dos pedidos">${[['total','Pedidos no resumo'],['preparing','Em preparação'],['shipped','Expedidos'],['delivered','Entregues']].map(([key,label])=>`<article><span>${label}</span><strong>${number(summary.orders[key],0)}</strong><p>Fonte: API de ${e(summary.company_name)}</p></article>`).join('')}</section>
    <section class="panel enterprise-contract"><div class="section-heading"><div><span class="eyebrow teal">LIGAÇÃO AUTENTICADA</span><h2>Do portal empresarial ao Nexo</h2><p>Conector ${e(result.connector?.label||result.adapter)} · apenas consulta</p></div>${badge('healthy','Resposta validada')}</div><div class="enterprise-flow"><div><strong>01 · Portal da empresa</strong><p>A aplicação empresarial disponibiliza o resumo dos pedidos.</p></div><div><strong>02 · API de operações</strong><p>O Nexo autentica-se no servidor e valida o contrato e a data dos dados.</p></div><div><strong>03 · Observabilidade</strong><p>Serviços, sondagens e incidentes continuam a ser acompanhados no Nexo.</p></div></div><dl class="enterprise-times"><div><dt>Dados gerados pela empresa</dt><dd>${fmtDate(summary.generated_at)}</dd></div><div><dt>Consulta efetuada pelo Nexo</dt><dd>${fmtDate(result.checked_at)}</dd></div><div><dt>Tempo desta consulta à API</dt><dd>${number(result.latency_ms,1)} ms</dd></div></dl><p class="info-note">Estes totais representam o conjunto devolvido pela API, sem janela temporal implícita. Não medem disponibilidade nem volume de vendas. A recolha automática aplica as regras à ligação autenticada. Falhas HTTP, autenticação recusada, dados inválidos ou desatualizados contam como falhas da integração; não provam que todos os serviços da empresa estejam indisponíveis.</p><p class="muted">As chaves ficam nos servidores. A resposta apresenta apenas totais agregados. As consultas podem reutilizar uma resposta durante até ${result.cache_seconds} segundos.</p><div class="enterprise-links"><a class="button secondary" href="#services">Consultar serviços</a><a class="button secondary" href="#incidents">Consultar incidentes</a>${config.laboratory?'<a class="text-button teal" href="#laboratory">Testar o ciclo no laboratório ↗</a>':''}</div></section>`+monitoring;
}
async function knowledgePage() {
  const knowledge = await api('/knowledge');
  return heading('APOIO À TRIAGEM','O conhecimento fica na equipa.','Pesquisa incidentes anteriores e consulta os procedimentos que ajudaram a resolvê-los.')+
    `<section class="knowledge-search"><span class="eyebrow">HISTÓRICO / PESQUISA ASSISTIDA</span><form id="knowledge-form"><div class="knowledge-controls"><label class="search-field large">${icon('search')}<input name="q" type="search" maxlength="2000" placeholder="Descreve o erro, o serviço ou os sintomas…" aria-label="Pesquisar no histórico"></label><button class="button primary" type="submit">Pesquisar ${icon('arrow')}</button></div><div class="knowledge-filters"><label>Método<select name="method"><option value="hybrid">Híbrido · palavras + significado</option><option value="semantic">Semântico · embeddings locais</option><option value="bm25">Textual · BM25</option><option value="tfidf">Baseline · TF-IDF</option></select></label><label>Serviço<select name="service_id"><option value="">Todos os serviços</option>${data.services.map(s=>`<option value="${s.id}">${e(s.name)}</option>`).join('')}</select></label><label>Origem<select name="scope"><option value="all">Todo o histórico</option><option value="operational">Laboratório e registos manuais</option><option value="examples">Exemplos sintéticos</option></select></label></div><p class="form-error" role="alert"></p></form><p>Pesquisa entre os 100 incidentes resolvidos ou fechados mais recentes. Consulta sempre a origem e confirma se a solução se aplica ao caso atual.</p></section><div id="knowledge-results" aria-live="polite">${knowledgeReport(knowledge)}</div>`;
}
function knowledgeReport(result) {
  return `<div class="knowledge-status"><div><span class="eyebrow teal">${e(result.method)}</span><p>${result.corpus_size} casos nesta seleção · índice local: ${result.index.ready_chunks}/${result.index.total_chunks} excertos${!result.index.configured?' · modelo não configurado':''}</p></div><span class="tag">Validação humana</span></div>${result.warning?`<p class="info-note" role="status">${e(result.warning)}</p>`:''}${result.eligible_total>result.corpus_size?'<p class="info-note">A seleção ultrapassa o corpus global dos 100 casos mais recentes. Os casos anteriores não participam nesta pesquisa.</p>':''}${result.model?`<details class="knowledge-model"><summary>Modelo e interpretação das pontuações</summary><p>${e(result.model)}</p><p>O cosseno compara vetores; o limiar semântico é ${number(result.semantic_threshold,2)}. A fusão RRF combina posições das listas textual e semântica. As pontuações não são probabilidades nem garantem que a causa ou a resolução sejam as mesmas.</p><p>Cada caso usa até três excertos de 600 caracteres, limitados a 128 tokens por excerto. O texto é processado no laboratório local.</p></details>`:'<p class="muted">BM25 pontua palavras em comum; TF-IDF usa cosseno textual. As pontuações não são probabilidades de acerto.</p>'}${knowledgeResults(result.results)}`;
}
function knowledgeScore(i) {
  return i.score_kind==='hybrid'?`RRF ${number(i.score,5)}`:i.score_kind==='bm25'?`BM25 ${number(i.score,3)}`:`Cosseno ${number(i.score,3)}`;
}
function knowledgeResults(rows) {
  return rows.length ? `<div class="knowledge-list">${rows.map(i=>`<article class="knowledge-item"><div class="knowledge-meta"><span>INC-${String(i.id).padStart(3,'0')} · ${e(i.service_name)}</span>${i.score != null ? `<span class="tag">${knowledgeScore(i)}</span>`:badge(i.severity)}</div><h2><button class="text-button" data-incident="${i.id}">${e(i.title)}</button></h2><p class="muted">${e(i.provenance)} · ${e(states[i.status])} · ${fmtDate(i.closed_at||i.resolved_at)}</p><p>${e(i.description)}</p>${i.matched_terms?.length?`<p class="knowledge-terms">Palavras em comum: ${i.matched_terms.map(e).join(' · ')}</p>`:''}${i.excerpt?`<details class="knowledge-excerpt"><summary>Excerto com maior semelhança · ${e(i.matched_section)}</summary><blockquote>${e(i.excerpt)}</blockquote>${i.semantic_score!=null?`<p class="muted">Cosseno semântico: ${number(i.semantic_score,3)}${i.bm25_score!=null?' · BM25: '+number(i.bm25_score,3):''}</p>`:''}</details>`:''}<div class="resolution-preview"><span>RESOLUÇÃO REGISTADA</span><p>${e(i.resolution)}</p></div><button class="text-button teal" data-incident="${i.id}">Consultar incidente e runbook ${icon('arrow')}</button></article>`).join('')}</div>` : empty('Sem correspondências nesta pesquisa','Não foi encontrada uma correspondência pelos critérios deste método. Experimenta reformular os sintomas ou ajustar os filtros; a ausência de resultados não exclui uma causa.');
}
const sloLabels={met:'Dentro do objetivo',breached:'Fora do objetivo',insufficient_data:'Dados insuficientes',policy_partial:'Histórico da política insuficiente',policy_unavailable:'Política indisponível'};
const sloBadge = state => badge(state==='met'?'healthy':state==='breached'?'P1':'unknown',sloLabels[state]||state);
function coverageTimeline(bins) {
  const width=600/bins.length;
  return `<svg class="coverage-timeline" viewBox="0 0 600 40" role="img" aria-label="Cobertura da janela: cinzento sem dados, verde sem violações observadas, vermelho com falhas ou latência acima do limite">${bins.map((bin,i)=>`<rect x="${i*width}" y="2" width="${Math.max(width-1,1)}" height="36" class="coverage-empty"/><rect x="${i*width}" y="${38-36*bin.observed/bin.expected}" width="${Math.max(width-1,1)}" height="${36*bin.observed/bin.expected}" class="${bin.bad_availability||bin.bad_latency?'coverage-bad':'coverage-good'}"><title>${e(fmtDate(bin.start))}: ${bin.observed}/${bin.expected} intervalos observados; ${bin.bad_availability} falhas HTTP; ${bin.bad_latency} fora do objetivo de resposta</title></rect>`).join('')}</svg>`;
}
function sliMetric(label,metric) {
  const budget=metric.error_budget;
  return `<article class="sli-metric"><span class="eyebrow teal">${label}</span><div class="sli-value">${number(metric.observed_percent,3)}${metric.observed_percent==null?'':'%'}</div><p>Objetivo ≥ ${number(metric.target_percent,3)}% · ${metric.good_slots} bons / ${metric.good_slots+metric.bad_slots} observados</p>${sloBadge(metric.status)}<dl><div><dt>Intervalo possível na janela</dt><dd>${number(metric.lower_percent,3)}% a ${number(metric.upper_percent,3)}%</dd></div><div><dt>Orçamento de erro</dt><dd>${number(budget.allowed_slots,3)} sondagens</dd></div><div><dt>Falhas confirmadas</dt><dd>${budget.confirmed_bad_slots}</dd></div><div><dt>Orçamento restante possível</dt><dd>${number(budget.remaining_min_slots,3)} a ${number(budget.remaining_max_slots,3)}</dd></div></dl></article>`;
}
async function sloPage() {
  const report=await api('/slo?window='+encodeURIComponent(sloWindow));
  const windows=[['1m','1 minuto · ensaio'],['15m','15 minutos'],['1h','1 hora'],['24h','24 horas'],['7d','7 dias']];
  return heading('FIABILIDADE / JANELAS DE AVALIAÇÃO','Objetivos, com dados à vista.','Avalia sondagens HTTP reais, a cobertura das medições e o orçamento de erro. Dados em falta não são considerados sucessos.',`<label class="slo-window">Janela de avaliação<select id="slo-window">${windows.map(([value,label])=>`<option value="${value}" ${sloWindow===value?'selected':''}>${label}</option>`).join('')}</select></label>`)+
    `<section class="metrics"><article><span>Serviços monitorizados</span><strong>${report.services.length}</strong><p>Origem: sondagens Prometheus</p></article><article><span>Com conclusão na janela</span><strong>${report.services.filter(s=>['met','breached'].includes(s.status)).length}</strong><p>Objetivos consistentes e limites conclusivos</p></article><article><span>Intervalos esperados</span><strong>${number(report.expected_slots_per_service,0)}</strong><p>Por serviço · um a cada 10 segundos</p></article><article><span>Janela terminada às</span><strong class="rule-engine-label">${new Date(report.end).toLocaleTimeString('pt-PT')}</strong><p>Margem de 30 s para receber as medições</p></article></section><p class="slo-range">De ${fmtDate(report.start)} a ${fmtDate(report.end)} · início incluído, fim excluído</p>`+
    (report.services.length?report.services.map(s=>s.policy?`<section class="panel slo-service"><div class="section-heading"><div><span class="eyebrow teal">POLÍTICA V${s.policy.version} · ${e(s.team)}</span><h2>${e(s.service_name)}</h2><p>Objetivos vigentes desde ${fmtDate(s.policy.valid_from)}${s.collection_state!=='enabled'?' · recolha '+(s.collection_state==='paused'?'pausada':'bloqueada'):''}</p></div>${sloBadge(s.status)}</div><div class="slo-coverage"><div><strong>${number(s.eligible_coverage_percent,2)}%</strong><span> cobertura sob a política vigente · ${s.observed_slots}/${s.expected_slots} intervalos</span></div>${coverageTimeline(s.timeline)}<p>${s.unknown_slots} intervalos desconhecidos · cobertura de dados, incluindo políticas anteriores: ${number(s.data_coverage_percent,2)}% · ${s.raw_samples} amostras reais</p>${!s.policy_covers_window?'<p class="info-note">A política vigente não cobre toda a janela. Os valores são provisórios e não demonstram cumprimento ou violação do objetivo nessa janela.</p>':''}</div><div class="sli-grid">${sliMetric('DISPONIBILIDADE DAS SONDAGENS',s.availability)}${sliMetric('RESPOSTA COM SUCESSO DENTRO DE '+s.policy.latency_ms+' MS',s.latency)}</div><div class="slo-service-foot"><span>p95 descritivo das sondagens bem-sucedidas: <strong>${number(s.p95_successful_ms,2)}${s.p95_successful_ms==null?'':' ms'}</strong> · ${s.p95_successful_slots} intervalos</span><div><button class="text-button teal" data-action="slo-history" data-id="${s.service_id}">Histórico dos objetivos</button>${admin()?`<button class="text-button teal" data-action="edit-service" data-id="${s.service_id}">Editar objetivos</button>`:''}</div></div></section>`:'').join(''):empty('Ainda sem serviços ligados','Liga um serviço em Monitorização para começar a recolher dados reais.'))+
    `<section class="panel rule-help"><h2>O que estes indicadores permitem concluir</h2><p>A janela termina pelo menos 30 segundos antes da consulta, para permitir a chegada das medições. Cada intervalo de dez segundos conta uma única vez. Se houver mais de uma medição, prevalece o pior resultado do intervalo. Falhas HTTP também contam como respostas fora do objetivo de latência.</p><p>O intervalo possível assume, nos extremos, que os dados desconhecidos foram todos maus ou todos bons. Só há conclusão quando ambos os extremos ficam do mesmo lado do objetivo e a política cobre a janela inteira.</p><p>O orçamento é expresso em unidades de sondagem e pode ser fracionário. Não representa minutos de indisponibilidade. O p95 é descritivo, calculado apenas sobre sondagens com sucesso; não substitui a proporção de respostas boas.</p><p class="info-note">São objetivos de sondagens de laboratório, não SLAs contratuais nem medições de todos os pedidos dos utilizadores. Pausas e interrupções na recolha deixam lacunas. O histórico anterior à primeira versão dos objetivos não é certificado retroativamente.</p></section>`;
}
async function sloHistory(id) {
  return modalContent(async()=>{
  const rows=await api(`/services/${id}/slo/history`);
  return `<span class="eyebrow teal">OBJETIVOS VERSIONADOS</span><h2 id="modal-title">Histórico de SLOs</h2>${rows.map(r=>`<article class="rule-history-item"><h3>Versão ${r.version} · ${fmtDate(r.valid_from)}</h3><p>${e(r.actor)}</p><p>Disponibilidade ≥ ${number(r.availability_percent,3)}% · respostas com sucesso em até ${r.latency_ms} ms ≥ ${number(r.latency_percent,3)}%</p></article>`).join('')||'<p class="info-note">Ainda sem uma política registada.</p>'}`;

  },false);
}

async function alertRulesPage() {
  const [rules,engine]=await Promise.all([api('/alert-rules'),api('/alert-engine')]);
  data.rules=rules;
  const linked=rules.filter(r=>{const service=data.services.find(s=>s.id===r.service_id);return service?.monitoring||service?.enterprise_monitoring;});
  const engineLabel={running:'Ativo',waiting:'A iniciar',stale:'Sem sinal recente'}[engine.status]||'Desconhecido';
  return heading('DETEÇÃO / RESPOSTA','Da condição à prioridade.','Define quando abrir um incidente e quanto tempo pode ficar por reconhecer. Só administradores podem alterar as regras.')+
    `<section class="metrics"><article><span>Serviços ligados</span><strong>${linked.length}</strong><p>Uma regra por serviço</p></article><article><span>Escalonamento por prazo</span><strong>${linked.filter(r=>r.config.enabled&&r.config.escalation_enabled).length}</strong><p>Eleva incidentes sem reconhecimento para P1</p></article><article><span>Regras personalizadas</span><strong>${linked.filter(r=>r.version>0).length}</strong><p>Versões anteriores preservadas</p></article><article><span>Motor de prazos</span><strong class="rule-engine-label">${engineLabel}</strong><p>Última verificação: ${fmtDate(engine.last_tick)}</p></article></section><section class="panel"><div class="section-heading"><div><h2>Regras dos serviços monitorizados</h2><p>As regras aplicam-se a sondagens reais; o simulador sintético mantém o seu comportamento de demonstração.</p></div></div><div class="rules-list">${linked.map(r=>{const c=r.config;const service=data.services.find(s=>s.id===r.service_id);return `<article class="rule-row"><div><span class="eyebrow teal">${r.version?'VERSÃO '+r.version:'REGRA BASE'}</span><h3>${e(r.service_name)}</h3><p>${c.failure_samples} sondagens para confirmar · ${c.recovery_samples} para recuperar</p><p>Indisponibilidade: ${c.outage_enabled?c.outage_severity:'ignorada'} · Latência: ${c.latency_enabled?c.latency_severity+' acima de '+r.effective_latency_ms+' ms':'ignorada'}</p></div><div class="rule-actions">${badge(c.enabled?'healthy':'unknown',c.enabled?'Alertas ativos':'Alertas suspensos')}<small>${c.enabled&&c.escalation_enabled?'Sem reconhecimento em '+c.acknowledge_seconds+' s → P1':'Escalonamento por prazo desligado'}</small>${!(service.monitoring?.enabled??service.enterprise_monitoring?.enabled)?'<small>Recolha pausada: regra sem avaliação</small>':''}${admin()?`<div><button class="button secondary small" data-action="edit-alert-rule" data-id="${r.service_id}">Configurar regra</button><button class="text-button teal" data-action="rule-history" data-id="${r.service_id}">Histórico</button></div>`:''}</div></article>`;}).join('')||'<p class="info-note">Liga primeiro um serviço em Monitorização.</p>'}</div></section><section class="panel rule-help"><h2>Um prazo operacional, com histórico.</h2><p>O motor verifica os prazos a cada cinco segundos. Um incidente automático aberto e sem reconhecimento pode subir para P1 uma única vez. Se já for P1, regista-se a ultrapassagem do prazo.</p><p>Alterar a regra, o SLO de latência ou retomar a recolha dá início a um novo prazo para os casos ainda não escalonados. Reconhecer o incidente impede o escalonamento por falta de reconhecimento. Não são enviadas notificações externas.</p><p class="info-note">Suspender alertas não recupera o serviço nem fecha os casos existentes. O limite de alerta pode diferir do SLO do inventário: o estado técnico do dashboard continua a ser calculado pelo SLO.</p></section>`;
}
function alertRuleForm(id) {
  const rule=data.rules.find(r=>r.service_id===id), c=rule.config;
  const check=(key,label)=>`<label class="monitoring-checkbox"><input type="checkbox" name="${key}" ${c[key]?'checked':''}> ${label}</label>`;
  const severity=(key,values)=>`<select name="${key}">${values.map(v=>`<option ${c[key]===v?'selected':''}>${v}</option>`).join('')}</select>`;
  modal(`<span class="eyebrow teal">REGRA / ${rule.version?'VERSÃO '+rule.version:'BASE'}</span><h2 id="modal-title">${e(rule.service_name)}</h2><form id="alert-rule-form" data-id="${id}">${check('enabled','Ativar alertas deste serviço')}<fieldset><legend>Condições de deteção</legend>${check('outage_enabled','Alertar indisponibilidade HTTP')}<label>Prioridade de indisponibilidade${severity('outage_severity',['P1','P2'])}</label>${check('latency_enabled','Alertar latência elevada')}<div class="form-grid"><label>Limite de latência (ms)<input type="number" name="latency_ms" min="1" max="120000" value="${c.latency_ms??''}" placeholder="Usar SLO do serviço"></label><label>Prioridade de latência${severity('latency_severity',['P2','P3','P4'])}</label></div><small>Deixa o limite vazio para usar o SLO do inventário.</small></fieldset><div class="form-grid"><label>Sondagens de confirmação<input type="number" name="failure_samples" min="2" max="5" value="${c.failure_samples}" required></label><label>Sondagens de recuperação<input type="number" name="recovery_samples" min="2" max="5" value="${c.recovery_samples}" required></label></div><fieldset><legend>Prazo de reconhecimento</legend>${check('escalation_enabled','Escalonar se não for reconhecido')}<label>Prazo até P1 (segundos)<input type="number" name="acknowledge_seconds" min="15" max="86400" value="${c.acknowledge_seconds}" required></label><small>Aplica-se a incidentes automáticos abertos. O prazo reinicia após alterações à regra, ao SLO de latência ou retoma da recolha.</small></fieldset><p class="info-note">Guardar uma alteração cria uma versão e exige novas sondagens. O histórico anterior permanece guardado e as prioridades existentes nunca descem automaticamente.</p><p class="form-error" role="alert"></p><button class="button primary" type="submit">Guardar regra ${icon('check')}</button></form>`);
}
async function ruleHistory(id) {
  return modalContent(async()=>{
  const rows=await api(`/services/${id}/alert-rule/history`);
  return `<span class="eyebrow teal">HISTÓRICO DE CONFIGURAÇÃO</span><h2 id="modal-title">Versões da regra</h2>${rows.length?rows.map(r=>`<article class="rule-history-item"><h3>Versão ${r.version} · ${fmtDate(r.changed_at)}</h3><p>${e(r.actor)} · alertas ${r.config.enabled?'ativos':'suspensos'}</p><p>Confirmação: ${r.config.failure_samples} · recuperação: ${r.config.recovery_samples} · limite: ${r.config.latency_ms??'SLO do serviço'}${r.config.latency_ms?' ms':''}</p><p>Prioridades: ${r.config.outage_severity} / ${r.config.latency_severity} · prazo: ${r.config.escalation_enabled?r.config.acknowledge_seconds+' s':'desligado'}</p></article>`).join(''):'<p class="info-note">O serviço usa a regra base; ainda não existem alterações guardadas.</p>'}`;

  },false);
}

function passwordForm() {
  return `<form id="password-form"><p class="muted">Usa uma frase-passe com 15 a 200 caracteres. A alteração termina as sessões anteriores e mantém esta sessão com um novo identificador.</p><label>Palavra-passe atual<input type="password" name="current_password" autocomplete="current-password" maxlength="200" required></label><label>Nova palavra-passe<input type="password" name="new_password" autocomplete="new-password" minlength="15" maxlength="200" required></label><label>Confirmar nova palavra-passe<input type="password" name="confirm_password" autocomplete="new-password" minlength="15" maxlength="200" required></label><p class="form-error" role="alert"></p><button class="button primary full" type="submit">Guardar palavra-passe ${icon('check')}</button></form>`;
}
function passwordScreen() {
  clearInterval(refreshTimer);
  $('#app').innerHTML=`<main class="account-setup" id="main"><section class="panel"><a class="brand" href="/"><img src="/static/favicon.svg" alt="">nexo</a><span class="eyebrow teal">PRIMEIRO ACESSO</span><h1>Uma palavra-passe só tua.</h1><p>Antes de entrares, substitui a palavra-passe inicial da tua conta.</p>${passwordForm()}<button class="text-button" data-action="logout">Terminar sessão</button></section></main>`;
}
async function usersPage() {
  data.accounts=await api('/admin/users');
  return heading('ADMINISTRAÇÃO / ACESSOS','A equipa por trás da operação.','Gere contas e perfis. O histórico permanece associado a cada pessoa, mesmo quando o acesso é desativado.', '<button class="button primary" data-action="new-user">'+icon('plus')+' Novo utilizador</button>')+
    `<section class="metrics account-metrics"><article><span>Contas ativas</span><strong>${data.accounts.filter(u=>u.active).length}</strong><p>Com acesso autorizado</p></article><article><span>Administradores ativos</span><strong>${data.accounts.filter(u=>u.active&&u.role==='admin').length}</strong><p>Pelo menos um é necessário</p></article><article><span>Primeiro acesso pendente</span><strong>${data.accounts.filter(u=>u.active&&u.must_change_password).length}</strong><p>Exige alterar a palavra-passe inicial</p></article><article><span>Contas desativadas</span><strong>${data.accounts.filter(u=>!u.active).length}</strong><p>Histórico preservado</p></article></section><section class="panel"><div class="section-heading"><div><h2>Utilizadores</h2><p>Perfis: Administração, Operações e Leitura</p></div></div><div class="table-scroll"><table><thead><tr><th>Pessoa / email</th><th>Perfil</th><th>Acesso</th><th></th></tr></thead><tbody>${data.accounts.map(u=>`<tr><td><strong>${e(u.name)}${u.id===user.id?' · Tu':''}</strong><small class="cell-sub">${e(u.email)}</small></td><td>${e(roles[u.role])}</td><td>${badge(u.active?'healthy':'unknown',u.active?'Ativo':'Desativado')}${u.active&&u.must_change_password?'<small class="cell-sub">Palavra-passe inicial por alterar</small>':''}</td><td><button class="button secondary small" data-action="edit-user" data-id="${u.id}">Editar conta</button></td></tr>`).join('')}</tbody></table></div><p class="panel-footnote">As alterações de perfil, email ou estado revogam as sessões da conta. Reatribui os incidentes ativos antes de retirar o acesso ao responsável.</p></section>`;
}
function userForm(id=null) {
  const account=data.accounts?.find(u=>u.id===id)||{name:'',email:'',role:'viewer',active:1};
  modal(`<span class="eyebrow teal">GESTÃO DE ACESSOS</span><h2 id="modal-title">${id?'Editar conta':'Novo utilizador'}</h2><form id="user-form" ${id?`data-id="${id}"`:''}><label>Nome<input name="name" value="${e(account.name)}" minlength="2" maxlength="100" autocomplete="off" required></label><label>Email<input name="email" value="${e(account.email)}" type="email" maxlength="200" autocomplete="off" required></label><label>Perfil<select name="role">${Object.entries(roles).map(([value,label])=>`<option value="${value}" ${account.role===value?'selected':''}>${label}</option>`).join('')}</select></label>${id?`<label class="monitoring-checkbox"><input type="checkbox" name="active" ${account.active?'checked':''}> Conta ativa</label><p class="info-note">Alterar o perfil, email ou estado termina as sessões existentes. O último administrador ativo e os responsáveis por incidentes ativos têm proteção adicional.</p>`:'<label>Palavra-passe inicial<input name="password" type="password" autocomplete="new-password" minlength="15" maxlength="200" required></label><p class="info-note">O utilizador terá de substituir esta palavra-passe no primeiro acesso. Não é enviado um email automático.</p>'}<p class="form-error" role="alert"></p><button class="button primary" type="submit">${id?'Guardar conta':'Criar conta'} ${icon('check')}</button></form>`);
}
async function connectMonitoring() {
  return modalContent(async()=>{
  const options = await api('/monitoring/options');
  const available = data.services.filter(s=>!s.monitoring && s.sample_count===0);
  if (!available.length) return toast('Cria primeiro um serviço novo no inventário, sem observações de demonstração.');
  if (!options.urls.length) return toast('A instalação ainda não tem endereços autorizados.');
  return `<span class="eyebrow teal">LIGAÇÃO DE SERVIÇO</span><h2 id="modal-title">Começar a monitorizar</h2><p class="muted">Associa um serviço do inventário a um endereço previamente autorizado. As sondagens medem sucesso HTTP e duração da resposta.</p><form id="monitoring-form"><label>Serviço do inventário<select name="service_id">${available.map(s=>`<option value="${s.id}">${e(s.name)}</option>`).join('')}</select></label><label>Endereço autorizado<select name="url">${options.urls.map(url=>`<option value="${e(url)}">${e(url)}</option>`).join('')}</select></label><label class="monitoring-checkbox"><input type="checkbox" name="enabled" checked> Ativar recolha de imediato</label><p class="info-note">O endereço fica associado a este histórico. Para outro endereço, cria um serviço separado. Podes pausar a recolha a qualquer momento.</p><p class="form-error" role="alert"></p><button class="button primary" type="submit">Ligar serviço ${icon('arrow')}</button></form>`;

  },false);
}

function monitoringPage() {
  const services = data.services.filter(s=>s.monitoring);
  return heading('LIGAÇÕES / SONDAGENS HTTP','Cada serviço, uma ligação.','Associa o inventário a endereços autorizados e acompanha a recolha sem reiniciar a aplicação.', admin()?'<button class="button primary" data-action="connect-monitoring">'+icon('plus')+' Ligar serviço</button>':'')+
    telemetryPanel()+`<section class="panel"><div class="section-heading"><div><h2>Serviços ligados</h2><p>${services.length} ligações · histórico preservado quando a recolha é pausada</p></div><a class="subtle-link" href="#services">Abrir inventário ${icon('arrow')}</a></div>${services.length?`<div class="monitoring-list">${services.map(s=>{const m=s.monitoring;const label=!m.enabled?'Recolha pausada':!m.approved?'Bloqueada pela política':s.status==='unknown'?'A aguardar medições':'Recolha ativa';return `<article class="monitoring-row"><div><span class="eyebrow teal">${m.kind==='laboratory'?'REFERÊNCIA DO LABORATÓRIO':'SERVIÇO CONFIGURADO'}</span><h3><button class="text-button" data-service="${s.id}">${e(s.name)}</button></h3><code class="monitoring-url">${e(m.target_url)}</code><p>${e(s.team)} · objetivo de latência ≤ ${s.slo_latency_ms} ms</p></div><div class="monitoring-condition">${badge(m.enabled&&m.approved?s.status:'unknown',label)}<small>Última sondagem: ${fmtDate(s.latest?.observed_at)}</small><small>Estado do serviço: ${statuses[s.status]}</small>${admin()&&m.kind==='configured'?`<button class="button secondary small" data-action="toggle-monitoring" data-id="${s.id}">${m.enabled?'Pausar recolha':'Retomar recolha'}</button>`:'<small>Ligação gerida pela instalação</small>'}</div></article>`;}).join('')}</div>`:empty('Ainda sem ligações','Cria um serviço no inventário e associa-lhe um endereço autorizado.')}</section>`+
    `<section class="panel monitoring-help"><h2>Ligar um serviço em três passos</h2><ol><li>Cria o serviço no <a href="#services">inventário</a>, com equipa responsável e objetivos.</li><li>Escolhe <strong>Ligar serviço</strong> e seleciona um endereço autorizado.</li><li>Aguarda as sondagens. As falhas confirmadas abrem incidentes automaticamente.</li></ol><p class="info-note">A seleção de endereços é definida na instalação. A pausa suspende a importação e os alertas; o Prometheus deixa de sondar o alvo após atualizar a lista de descoberta. Pausar não significa que o serviço recuperou.</p><p class="muted">Esta ligação recolhe métricas HTTP. A integração de logs é independente: exige uma origem previamente mapeada na instalação. No laboratório, inclui os serviços HTTP de referência e o endpoint de pedidos da Aurora. Pausar sondagens não apaga os logs já recolhidos.</p></section>`;
}
function logsScope(snapshot) {
  if(!snapshot.scope) return '<p class="muted">Esta recolha antiga não guardou o mapeamento da origem.</p>';
  const scope=snapshot.scope;
  return `<p class="info-note"><strong>${e(snapshot.service_name||'Serviço monitorizado')}</strong><br>Origem Loki: ${e(scope.service_key)} · ${scope.path?`apenas o endpoint ${e(scope.path)}`:'pedidos do serviço HTTP completo'}.<br>Ligação: <code>${e(scope.target_url)}</code>${snapshot.queried_at?`<br>Consulta efetuada em ${fmtDate(snapshot.queried_at)}.`:''}</p>`;
}
function logsTable(entries) {
  if (!entries.length) return '<p class="info-note">Sem logs na janela consultada. Isto não confirma que o serviço esteja saudável.</p>';
  return `<div class="table-scroll log-table"><table><thead><tr><th>Quando</th><th>Pedido</th><th>HTTP</th><th>Duração</th></tr></thead><tbody>${entries.map(r=>`<tr><td>${fmtDate(new Date(Number(r.timestamp_ns)/1e6))}</td><td><code>${e(r.method)} ${e(r.path)}</code></td><td>${badge(r.status>=500?'P1':'healthy',r.status)}</td><td>${number(r.duration_ms,2)} ms</td></tr>`).join('')}</tbody></table></div>`;
}
async function logsModal(id) {
  return modalContent(async()=>{
  const result = await api(`/services/${id}/logs`);
  return `<span class="eyebrow teal">EVIDÊNCIAS / LOKI</span><h2 id="modal-title">Pedidos observados no serviço</h2><p class="muted">Últimos 15 minutos · até 50 registos · dados de laboratório</p>${logsScope(result)}${logsTable(result.entries)}`;

  },true);
}

function laboratoryPage() {
  if (!config.laboratory) return empty('Laboratório desativado','Os controlos de teste estão disponíveis apenas no ambiente local de demonstração.');
  const targets = [['portal-lab','Laboratório · Portal HTTP','Portal de clientes'],['api-lab','Laboratório · API HTTP','API com atraso de base']];
  return heading('EMPRESA FICTÍCIA / OPERAÇÃO REAL','Uma falha. O percurso completo.','A Aurora representa a empresa monitorizada. O Nexo é o espaço de trabalho da sua equipa de operações.', '<a class="button primary" href="http://127.0.0.1:8002/" target="_blank" rel="noopener">Abrir portal da Aurora ↗</a>')+
    `<section class="lab-journey" aria-label="Percurso de demonstração">${[['01','Provocar','O serviço passa a devolver HTTP 503.'],['02','Detetar','Duas sondagens confirmam a falha.'],['03','Tratar','O Nexo abre um incidente com evidências.'],['04','Aprender','A equipa resolve, fecha e guarda o conhecimento.']].map(([n,t,d])=>`<article><span>${n}</span><h2>${t}</h2><p>${d}</p></article>`).join('')}</section>`+
    telemetryPanel()+`<div class="lab-targets">${targets.map(([key,name,label])=>{const service=data.services.find(s=>s.monitoring?.target_key===key);const incidents=data.incidentContext.laboratory.filter(i=>i.service_id===service?.id);return `<section class="panel lab-target"><span class="eyebrow teal">${e(key)}</span><div class="lab-target-heading"><h2>${label}</h2>${badge(service?.status||'unknown',statuses[service?.status||'unknown'])}</div><p class="muted">Última sondagem: ${fmtDate(service?.latest?.observed_at)} · ${service?.latest?number(service.latest.latency_ms,0)+' ms':'sem amostras'}</p><div class="lab-actions">${editable()?`<button class="button secondary" data-action="lab-fault" data-target="${key}" data-kind="outage">Provocar falha HTTP 503</button><button class="button secondary" data-action="lab-fault" data-target="${key}" data-kind="latency">Introduzir latência</button><button class="button primary" data-action="lab-fault" data-target="${key}" data-kind="recovery">Recuperar serviço</button>`:'<p class="info-note">O perfil de leitura pode acompanhar o ensaio; a execução exige Operações ou Administrador.</p>'}</div><div class="lab-evidence">${service&&config.logs?`<button class="text-button teal" data-action="service-logs" data-id="${service.id}">Consultar logs HTTP ↗</button>`:''}${incidents.map(i=>`<button class="text-button teal" data-incident="${i.id}">Tratar INC-${String(i.id).padStart(3,'0')} · ${e(i.severity)} ↗</button>`).join('')||'<span class="muted">Sem incidente automático ativo.</span>'}</div></section>`;}).join('')}</div>`+
    `<section class="panel lab-instructions"><h2>Como experimentar</h2><ol><li>Abre o portal da Aurora e confirma que os pedidos carregam.</li><li>Provoca uma falha no <strong>Portal de clientes</strong>. A página da Aurora deixa de conseguir carregar os pedidos.</li><li>Aguarda a deteção, normalmente 20–40 segundos. Abre o incidente automático, atribui um responsável e inicia a investigação.</li><li>Consulta os logs HTTP e os casos anteriores. Recupera o serviço neste ecrã e aguarda duas sondagens saudáveis.</li><li>Regista a resolução e fecha com causa raiz, prevenção e runbook. O caso fica disponível na base de conhecimento para a próxima ocorrência.</li></ol><p class="info-note">Os controlos só afetam estes serviços de teste. Cada falha expira ao fim de 2 minutos. A recuperação não fecha o incidente automaticamente. A API tem um atraso de base de 800 ms; recuperar repõe esse comportamento e pode manter o alerta de latência.</p><p class="muted">Numa empresa real, as sondagens apontam para os seus serviços autorizados. Os controlos de falha do laboratório ficam desativados; os testes de resiliência são preparados num ambiente de ensaio.</p></section>`;
}
let auditFilters={};
async function auditPage(before=null,snapshot=null) {
  const params=new URLSearchParams(auditFilters);params.set('limit','50');
  if(before)params.set('before_id',before);if(snapshot)params.set('snapshot_id',snapshot);
  const feed=await api('/audit/events?'+params), rows=feed.items;
  const fields=[['actor','Utilizador · nome exato','text','Ex.: Hugo Sousa'],['action','Ação · código exato','text','Ex.: incident.transition'],['entity','Registo · identificador exato','text','Ex.: incident:9'],['q','Pesquisar texto','search','Palavras no evento ou no detalhe'],['date_from','Desde · dia UTC','date',''],['date_to','Até · dia UTC','date','']];
  return heading('RASTREABILIDADE','Cada ação tem uma origem.','Pesquisa o histórico de operações. Acesso reservado ao administrador.', '<button class="button secondary" data-action="audit-refresh">Atualizar recentes</button>')+
    `<section class="panel"><form id="audit-filter-form" class="audit-filters">${fields.map(([name,label,type,placeholder])=>`<label>${label}<input name="${name}" type="${type}" value="${e(auditFilters[name]||'')}" placeholder="${placeholder}" ${type==='date'?'':`maxlength="${name==='entity'||name==='q'?200:100}"`}></label>`).join('')}<div class="audit-filter-actions"><button class="button primary" type="submit">Aplicar filtros</button><button class="button secondary" type="button" data-action="audit-clear">Limpar filtros</button></div><p class="form-error" role="alert"></p></form></section>
    <section class="panel audit-results" aria-label="Eventos de auditoria"><div class="section-heading"><div><span class="eyebrow teal">${before?'HISTÓRICO':'MAIS RECENTES'}</span><h2>${rows.length} eventos nesta página</h2></div><span class="tag">CONSULTA</span></div><p class="muted">Datas do filtro em UTC. Os horários abaixo seguem a apresentação local. Novos eventos aparecem ao atualizar os recentes.</p><div class="table-scroll"><table><thead><tr><th>Evento / Quando</th><th>Quem</th><th>Ação</th><th>Registo</th><th>Detalhe</th></tr></thead><tbody>${rows.map(r=>`<tr><td class="nowrap"><strong>#${r.id}</strong><br>${fmtDate(r.created_at)}</td><td>${e(r.actor)}</td><td><code>${e(r.action)}</code></td><td>${/^incident:[1-9][0-9]*$/.test(r.entity)?`<button class="text-button" data-incident="${Number(r.entity.split(':')[1])}">${e(r.entity)}</button>`:e(r.entity)}</td><td class="audit-detail">${r.detail?`<details><summary>${e(r.detail.slice(0,100))}${r.detail.length>100?'…':''}</summary><p>${e(r.detail)}</p></details>`:'—'}</td></tr>`).join('')}</tbody></table></div>${!rows.length?empty('Sem eventos para estes filtros.','Revê os critérios ou limpa os filtros para consultar o histórico.'):''}<div class="audit-pagination">${before?'<button class="button secondary" data-action="audit-refresh">Voltar aos recentes</button>':''}${feed.next_before_id?`<button class="button secondary" data-action="audit-older" data-before="${feed.next_before_id}" data-snapshot="${feed.snapshot_id}">Ver eventos mais antigos</button>`:''}</div></section>`;
}

function guidePage() {
  return heading('PROJETO I · 2026 / 27','Começa por aqui.','Uma primeira versão para compreender, experimentar e evoluir o projeto.')+
    `<section class="guide-layout"><article class="panel guide-article"><span class="eyebrow teal">O TEU PRIMEIRO PERCURSO</span><h2>Do serviço ao conhecimento</h2><ol class="guide-steps"><li><strong>Explora o inventário.</strong><p>Consulta as equipas, os objetivos de disponibilidade e latência e as dependências dos quatro serviços de exemplo.</p></li><li><strong>Simula uma falha.</strong><p>Na visão geral, escolhe «Simular cenário». A indisponibilidade abre um P1 e a latência elevada abre um P2. São regras locais de demonstração.</p></li><li><strong>Assume o incidente.</strong><p>Abre o incidente, escolhe um responsável e avança para «Reconhecido». O tempo entre o registo e esse momento contribui para o MTTA.</p></li><li><strong>Investiga e regista a solução.</strong><p>Consulta casos semelhantes, acrescenta notas e avança para «Em investigação». Depois regista a resolução. O tempo desde o registo contribui para o MTTR.</p></li><li><strong>Fecha com um post-mortem.</strong><p>Indica a causa raiz, a prevenção e, se aplicável, o runbook. O incidente passa a integrar a base de conhecimento.</p></li></ol></article>
    <aside class="guide-aside"><span class="eyebrow teal">ESTADO DA ENTREGA</span><h2>Versão 0.31</h2><p>Inventário, incidentes, sessões, perfis, auditoria, SLOs e pesquisa híbrida local funcionam com persistência em SQLite.</p><h3>A seguir</h3><p>O laboratório já liga sondagens reais, logs Loki e incidentes automáticos. Regras, contas e pesquisa semântica já estão disponíveis. As cópias cifradas e o restauro isolado já foram validados. Na pasta do projeto, executa copia-seguranca.cmd para guardar o histórico. Os testes de segurança e carga já identificaram e permitiram corrigir limites de concorrência. O restauro portátil Windows/Linux também foi validado. Para criares um kit, executa exportar-chave-portatil.cmd e escolhe uma frase-passe no terminal. O ciclo operacional dispõe agora de um ensaio isolado e repetível, com tempos e evidências exportados para a pasta docs. Executa validar-ciclo-operacional.ps1 para repetir. Estes tempos correspondem a tratamento por script, sem medir o desempenho de uma pessoa. A promoção controlada e a reversão de uma base recuperada dispõem agora de um procedimento local: consulta docs/manutencao.md. Executa manutencao.ps1 -Acao Estado para consultar a fase. A promoção mantém a monitorização pausada até uma retoma explícita. A central de Notificações já reúne novos incidentes, atribuições, prioridades, recuperações e prazos ultrapassados, com leitura individual.</p><h3>Sobre os indicadores</h3><p>As médias são calculadas a partir das datas guardadas e incluem o histórico sintético. Não demonstram melhoria real. A percentagem de sondagens não equivale à disponibilidade temporal.</p><h3>Documentação do código</h3><p>Consulta o README e a pasta docs no projeto para requisitos, modelo de dados, decisões e roteiro de demonstração.</p></aside></section>`;
}
const noticeKinds={created:'Novo incidente',detected:'Deteção confirmada',recurrence:'Nova ocorrência',priority:'Prioridade elevada',deadline:'Prazo ultrapassado',assignment:'Atribuição',recovery:'Recuperação confirmada'};
async function refreshNotifications() {
  if(!user || user.must_change_password || document.hidden || noticeBusy) return;
  noticeBusy=true;const uid=user.id;
  try {
    const feed=await api('/notifications?limit=1');if(user?.id!==uid)return;
    const bell=$('#notification-bell'),count=$('#notification-count');
    if(count)count.textContent=feed.unread_count>99?'99+':String(feed.unread_count);
    if(bell){bell.classList.toggle('has-unread',feed.unread_count>0);bell.setAttribute('aria-label',`Notificações: ${feed.unread_count} não lidas`);}
    const update=$('#notice-updates');if(update)update.hidden=feed.latest_id<=visibleNoticeLatest;
  }catch(error){if($('#notification-bell'))$('#notification-bell').setAttribute('aria-label','Notificações indisponíveis');if($('#notification-count'))$('#notification-count').textContent='—';}
  finally{noticeBusy=false;}
}
async function notificationsPage(before=null) {
  const feed=await api('/notifications?limit=30'+(before?`&before_id=${before}`:''));
  visibleNoticeLatest=feed.latest_id;
  const action=before?'<button class="button secondary" data-action="notices-refresh">Voltar às recentes</button>':`<button class="button secondary" data-action="notices-read" data-through="${feed.latest_id}" ${feed.unread_count?'':'disabled'}>${icon('check')} Marcar todas como lidas</button>`;
  return `${heading('CENTRO DE ATENÇÃO','Notificações','Deteções, intervenções e recuperações, ligadas ao histórico de cada caso.',action)}
    <section class="notification-intro"><div><span class="eyebrow">POR ACOMPANHAR</span><strong>${number(feed.unread_count,0)} <span>não lidas</span></strong></div><p>A leitura é pessoal.<br>Para reconhecer, investigar ou resolver uma ocorrência, <b>abre o incidente</b>.</p><button class="button secondary" data-action="notices-refresh">${icon('arrow')} Atualizar</button></section>
    <p id="notice-updates" class="info-note" role="status" hidden>Existem novos avisos. <button class="text-button" data-action="notices-refresh">Mostrar recentes</button></p>
    <section class="panel notification-panel" aria-label="Histórico de notificações"><div class="section-heading"><div><span class="eyebrow teal">${before?'ARQUIVO':'ÚLTIMOS ACONTECIMENTOS'}</span><h2>O contexto vem primeiro.</h2></div><span class="tag">DENTRO DO PORTAL</span></div>
    ${feed.items.map(n=>`<article class="notification-row ${n.unread?'is-unread':''}"><span class="notice-signal ${n.kind==='deadline'||n.kind==='priority'?'urgent':''}" aria-label="${n.unread?'Não lida':'Lida'}"></span><div class="notification-content"><div class="notification-meta"><span class="notice-kind ${n.kind==='deadline'?'urgent':''}">${noticeKinds[n.kind]}</span><span>INC-${String(n.incident_id).padStart(3,'0')} · ${e(n.service_name)}</span></div><h3>${e(n.action)}</h3><p>${e(n.note)}${n.note_truncated?'…':''}</p><div class="notification-context">${badge(n.status,states[n.status])}<span>${e(n.source==='prometheus-alert'?'Sondagens HTTP':n.source==='enterprise-alert'?'API empresarial autenticada':'Registo manual')} · prioridade atual ${e(n.severity)}</span></div></div><div class="notification-side"><time datetime="${e(n.created_at)}">${fmtDate(n.created_at)}</time><button class="text-button" data-incident="${n.incident_id}" aria-label="Abrir incidente ${n.incident_id}">Abrir caso ${icon('arrow')}</button></div></article>`).join('')||empty('Tudo tranquilo por aqui.','Os novos eventos operacionais vão aparecer aqui. Os exemplos sintéticos estão separados deste histórico.')}
    ${feed.next_before_id?`<div class="notification-pagination"><button class="button secondary" data-action="notices-older" data-before="${feed.next_before_id}">Ver notificações mais antigas</button></div>`:''}</section>
    <p class="notification-footnote">Os avisos conservam o evento original e mostram o estado atual do caso. Marcar como lidas abrange os avisos anteriores ao que estás a consultar; novas ocorrências continuam por ler.</p>`;
}

async function render(options={}) {
  if (!user) return;
  if(user.must_change_password) {passwordScreen();return;}
  const titles = {enterprise:'Integração empresarial',overview:'Visão geral',services:'Serviços',incidents:'Incidentes',knowledge:'Base de conhecimento',notifications:'Notificações',audit:'Auditoria',guide:'Guia do projeto',laboratory:'Laboratório empresarial',monitoring:'Monitorização',users:'Utilizadores','alert-rules':'Regras de alerta',slo:'Objetivos e SLOs'};
  if (!titles[page] || (['audit','users'].includes(page) && !admin())) page='overview';
  const views = {enterprise:enterprisePage,overview,services:servicesPage,incidents:incidentsPage,knowledge:knowledgePage,notifications:notificationsPage,audit:auditPage,guide:guidePage,laboratory:laboratoryPage,monitoring:monitoringPage,users:usersPage,'alert-rules':alertRulesPage,slo:sloPage};
  const requestedPage=page;
  if(!await pageContent(()=>views[requestedPage](),options))return false;
  $('#breadcrumb').textContent = titles[page];
  $('#updated').textContent = 'Atualizado às '+new Date(data.summary.generated_at).toLocaleTimeString('pt-PT',{hour:'2-digit',minute:'2-digit'});
  $('#nav-count').textContent = data.summary.active_incidents;
  document.querySelectorAll('[data-page]').forEach(a=>{a.classList.toggle('active',a.dataset.page===page); if(a.dataset.page===page)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  document.title = `Nexo · ${titles[page]}`;return true;
}

const serviceOptions = (syntheticOnly=false) => data.services.filter(s=>!syntheticOnly || !['prometheus','enterprise'].includes(s.telemetry_source)).map(s=>`<option value="${s.id}">${e(s.name)}</option>`).join('');
// Follow reverse dependency edges: a dependent may be affected by its prerequisite.
function dependencyImpact(serviceId, services) {
  const catalog=new Map((services||[]).map(service=>[service.id,service]));
  if(!catalog.has(serviceId))return {available:false,items:[],truncated:false,incomplete:true};
  const dependents=new Map();let incomplete=false;
  for(const service of catalog.values()) {
    if(!Array.isArray(service.dependencies)){incomplete=true;continue;}
    for(const prerequisite of new Set(service.dependencies)) {
      if(!catalog.has(prerequisite)){incomplete=true;continue;}
      if(!dependents.has(prerequisite))dependents.set(prerequisite,new Set());
      dependents.get(prerequisite).add(service.id);
    }
  }
  const seen=new Set([serviceId]), queue=[{id:serviceId,depth:0,path:[serviceId]}], items=[];
  for(let cursor=0;cursor<queue.length;cursor++) {
    const current=queue[cursor];
    for(const id of [...(dependents.get(current.id)||[])].sort((a,b)=>a-b)) {
      if(seen.has(id))continue;
      seen.add(id);
      if(items.length===50)return {available:true,items,truncated:true,incomplete};
      const node={id,depth:current.depth+1,path:[...current.path,id]};
      items.push({...node,service:catalog.get(id)});queue.push(node);
    }
  }
  return {available:true,items,truncated:false,incomplete};
}
function impactPanel(serviceId, incident=null) {
  const result=dependencyImpact(serviceId,data.services);
  const label=!result.available?'inventário indisponível':result.incomplete?'consulta parcial':result.items.length?`${result.items.length}${result.truncated?' ou mais':''} ${result.items.length===1?'serviço dependente':'serviços dependentes'}`:'sem dependentes registados';
  const names=new Map((data.services||[]).map(s=>[s.id,s.name]));
  return `<details class="impact-panel"><summary>Impacto potencial · ${e(label)}</summary><div class="impact-content"><p>Relações do inventário consultado em ${fmtDate(data.summary?.generated_at)}. São dados atuais da consulta, não uma reconstituição do momento do incidente.</p>
    ${!result.available?'<p class="info-note">O serviço não está disponível no inventário desta consulta. Não é possível avaliar as dependências.</p>':result.incomplete?'<p class="info-note">O inventário contém relações incompletas. A lista pode omitir dependentes; não permite concluir ausência de impacto.</p>':''}
    ${result.items.length?`<ul class="impact-list">${result.items.map(item=>`<li><div><strong>${e(item.service.name)}</strong><small>${e(item.service.team)} · criticidade ${e(item.service.criticality||'não indicada')}</small></div>${badge(item.service.status||'unknown',statuses[item.service.status]||statuses.unknown)}<details class="impact-path"><summary>${item.depth===1?'Dependência direta':`Dependência indireta · ${item.depth} níveis`}</summary><p>Propagação potencial: ${item.path.map(id=>e(names.get(id)||id)).join(' → ')}</p></details></li>`).join('')}</ul>`:result.available&&!result.incomplete?'<p>Não existem serviços dependentes nas relações registadas. Dependências não registadas podem existir.</p>':''}
    ${result.truncated?'<p class="info-note">São apresentados os primeiros 50 dependentes encontrados. Existem outros; a lista não representa o impacto total.</p>':''}
    <p class="impact-note">As relações indicam possível propagação. O estado observado é a última classificação disponível de cada serviço; não prova que este incidente o afetou nem identifica a causa raiz.</p>${incident&&editable()&&incident.status!=='closed'?`<div class="impact-capture"><button class="button secondary small" data-action="save-impact" data-id="${incident.id}">Guardar avaliação atual no caso</button><p>O servidor recalcula as relações e os estados ao guardar. A cópia fica na linha temporal e no dossier.</p></div>`:''}</div></details>`;
}
function serviceModal(id) {
  const s = data.services.find(s=>s.id===id);
  modal(`<span class="eyebrow teal">INVENTÁRIO / SRV-${id}</span><h2 id="modal-title">${e(s.name)}</h2><p class="muted">${e(s.description || 'Sem descrição.')}</p><div class="detail-grid"><div><span>Equipa responsável</span><strong>${e(s.team)}</strong></div><div><span>Criticidade</span><strong>${e(s.criticality)}</strong></div><div><span>SLO de disponibilidade</span><strong>${number(s.slo_availability,3)}%</strong></div><div><span>SLO de latência</span><strong>${number(s.slo_latency_percent??95)}% com sucesso em até ${s.slo_latency_ms} ms</strong></div></div>${s.logs_available?`<p><button class="button secondary" data-action="service-logs" data-id="${s.id}">Consultar logs deste serviço</button></p>`:''}${admin()?`<p><button class="button secondary" data-action="edit-service" data-id="${s.id}">Editar serviço</button></p>`:''}<h3>Depende de</h3><p>${s.dependencies.length ? s.dependencies.map(id=>e(data.services.find(d=>d.id===id)?.name || id)).join(' · '):'Sem dependências registadas.'}</p>${impactPanel(id)}<div class="info-note">Estado: ${statuses[s.status]}. Última observação: ${fmtDate(s.latest?.observed_at)}. Origem: ${e(s.latest?.source || 'sem dados')}.</div>`);
}
function newService() {serviceForm();}
function serviceForm(id=null) {
  const s=data.services.find(s=>s.id===id)||{name:'',team:'',description:'',criticality:'Alta',slo_availability:99.9,slo_latency_ms:500,slo_latency_percent:95,dependencies:[]};
  modal(`<span class="eyebrow teal">INVENTÁRIO</span><h2 id="modal-title">${id?'Editar serviço':'Novo serviço'}</h2><form id="service-form" ${id?`data-id="${id}"`:''}><label>Nome do serviço<input name="name" minlength="2" maxlength="100" required value="${e(s.name)}" placeholder="Ex.: Portal de marcações"></label><label>Equipa responsável<input name="team" minlength="2" maxlength="100" required value="${e(s.team)}" placeholder="Ex.: Serviços digitais"></label><label>Descrição<textarea name="description" maxlength="1000" rows="2">${e(s.description)}</textarea></label><div class="form-grid"><label>Criticidade<select name="criticality">${['Alta','Média','Baixa'].map(value=>`<option ${s.criticality===value?'selected':''}>${value}</option>`).join('')}</select></label><label>SLO disponibilidade (%)<input name="slo_availability" type="number" min="0.001" max="100" step="0.001" value="${s.slo_availability}" required></label><label>Limite de latência (ms)<input name="slo_latency_ms" type="number" min="1" max="120000" value="${s.slo_latency_ms}" required></label><label>Respostas com sucesso dentro do limite (%)<input name="slo_latency_percent" type="number" min="0.001" max="100" step="0.001" value="${s.slo_latency_percent??95}" required></label></div><fieldset><legend>Depende destes serviços</legend>${data.services.filter(other=>other.id!==id).map(other=>`<label class="check-label"><input type="checkbox" name="dependencies" value="${other.id}" ${s.dependencies.includes(other.id)?'checked':''}>${e(other.name)}</label>`).join('') || '<p class="muted">Ainda sem outros serviços.</p>'}</fieldset>${id?'<p class="info-note">A alteração preserva o histórico e a ligação de monitorização. Se mudares o objetivo de latência, serão necessárias novas sondagens para confirmar o estado.</p>':''}<p class="form-error" role="alert"></p><button class="button primary" type="submit">${id?'Guardar alterações':'Criar serviço'} ${icon('check')}</button></form>`);
}
function newIncident() {
  if (!data.services.length) return toast('Cria um serviço antes de registar incidentes.');
  modal(`<span class="eyebrow teal">GESTÃO DE INCIDENTES</span><h2 id="modal-title">Registar incidente</h2><form id="incident-form"><label>Serviço afetado<select name="service_id">${serviceOptions()}</select></label><label>Título<input name="title" required minlength="5" maxlength="160" placeholder="O que está a acontecer?"></label><label>Descrição e evidências<textarea name="description" required minlength="10" maxlength="5000" rows="4" placeholder="Sintomas, mensagens de erro e impacto observado…"></textarea></label><label>Prioridade<select name="severity"><option value="P1">P1 · Crítica — serviço indisponível</option><option value="P2" selected>P2 · Alta — degradação grave</option><option value="P3">P3 · Média — impacto limitado</option><option value="P4">P4 · Baixa — aviso preventivo</option></select></label><p class="form-error" role="alert"></p><button class="button primary" type="submit">Registar incidente ${icon('plus')}</button></form>`);
}
function scenarioModal() {
  if (!data.services.length) return toast('Cria primeiro um serviço.');
  modal(`<span class="eyebrow teal">LABORATÓRIO LOCAL</span><h2 id="modal-title">Simular um cenário</h2><p class="muted">Gera uma observação sintética e testa a abertura de um alerta. Nenhum sistema externo é alterado.</p><form id="scenario-form"><label>Serviço<select name="service_id">${serviceOptions(true)}</select></label><label>Cenário<select name="kind"><option value="outage">Indisponibilidade → incidente P1</option><option value="latency">Latência elevada → incidente P2</option><option value="recovery">Recuperação → observação saudável</option></select></label><p class="info-note">Alertas repetidos são agrupados no incidente ativo do simulador. A recuperação do serviço não resolve automaticamente o incidente: regista a intervenção e a resolução.</p><p class="form-error" role="alert"></p><button class="button primary" type="submit">Executar cenário ${icon('arrow')}</button></form>`);
}

function preservedImpact(record) {
  if(record.schema_version!==1 || !record.root || !Array.isArray(record.dependents) || record.dependents.length>50)throw new Error('Formato de avaliação desconhecido');
  const names=new Map([record.root,...record.dependents].map(node=>[node.id,node.name]));
  return `<details class="preserved-impact"><summary>Avaliação preservada · ${record.dependents.length} ${record.dependents.length===1?'dependente':'dependentes'}${record.truncated?' · lista parcial':''}</summary><p>Recalculada no servidor em ${fmtDate(record.evaluated_at)}. Inventário desse momento; não confirma impacto real.</p><p><strong>${e(record.root.name)}</strong> · ${badge(record.root.status,statuses[record.root.status]||statuses.unknown)}</p>${record.dependents.length?`<ul>${record.dependents.map(node=>`<li><strong>${e(node.name)}</strong> · ${e(node.team)} · ${badge(node.status,statuses[node.status]||statuses.unknown)}<small>${node.depth===1?'Dependência direta':`Dependência indireta · ${e(node.depth)} níveis`} · depende de ${e(names.get(node.parent_id)||node.parent_id)}</small><small>Última observação: ${fmtDate(node.last_observed_at)} · origem ${e(node.observation_source||'sem dados')}</small></li>`).join('')}</ul>`:'<p>Sem dependentes nas relações preservadas. Dependências não registadas podem existir.</p>'}${record.truncated||record.incomplete||record.text_truncated?'<p class="info-note">Avaliação parcial: existem dependentes adicionais, relações incompletas ou campos limitados. A cópia pode não representar todo o inventário.</p>':''}<p>Os nomes e os estados acima são os guardados nesta recolha. Não são atualizados quando o inventário muda.</p></details>`;
}
function timelineNote(entry) {
  if(entry.action==='Impacto potencial preservado') {
    try{return preservedImpact(JSON.parse(entry.note));}catch{return `<p>${e(entry.note)}</p>`;}
  }
  if(entry.action==='Conhecimento aplicado') {
    try {
      const record=JSON.parse(entry.note), snapshot=record.source_snapshot;
      return `<p><strong>Referência INC-${e(record.source_incident_id)} · ${e(snapshot.title)}</strong></p><p>${e(record.reason)}</p><details><summary>Conteúdo preservado no momento da associação</summary><p>Origem: ${e(snapshot.source)} · estado: ${e(states[snapshot.status]||snapshot.status)}</p>${['resolution','root_cause','prevention','runbook'].map((key,index)=>`<h4>${['Resolução','Causa raiz','Prevenção','Runbook'][index]}</h4><p>${e(snapshot[key]||'Não registado')}</p>`).join('')}</details>`;
    } catch { return `<p>${e(entry.note)}</p>`; }
  }
  return entry.note?`<p>${e(entry.note)}</p>`:'';
}

async function incidentModal(id, replace=false) {
  return modalContent(async current=>{
  const i=await api(`/incidents/${id}`);if(!current())return;
  const service=data.services.find(s=>s.id===i.service_id);
  let suggestions;
  try {suggestions=await api('/knowledge?exclude_id='+i.id+'&q='+encodeURIComponent((i.title+' '+i.description).slice(0,2000)));}
  catch(error){suggestions={method:'Pesquisa indisponível',results:[],warning:'Não foi possível obter sugestões. Podes continuar a tratar o incidente. '+error.message};}
  if(!current())return;
  let logContext='';
  if(service?.logs_available && i.status!=='closed') {
    try {const snapshot=await api(`/services/${service.id}/logs`);logContext=logsScope(snapshot)+logsTable(snapshot.entries);} catch(error) {logContext=`<p class="info-note">${e(error.message)}</p>`;}
  }
  const next = {open:'acknowledged',acknowledged:'investigating',investigating:'resolved',resolved:'closed'}[i.status];
  const actions = {acknowledged:'Reconhecer incidente',investigating:'Iniciar investigação',resolved:'Registar resolução',closed:'Fechar com post-mortem'};
  const html = `<div class="incident-detail"><span class="eyebrow teal">INC-${String(i.id).padStart(3,'0')} / ${e(service?.name)}</span><h2 id="modal-title">${e(i.title)}</h2><div class="incident-badges">${badge(i.severity)}${badge(i.status,states[i.status])}<span class="muted">Registado ${fmtDate(i.created_at)}</span></div><p class="incident-description">${e(i.description)}</p>${impactPanel(i.service_id,i)}
    <section aria-label="Exportar dossier do incidente"><h3>Guardar dossier</h3><p class="muted">Fotografia do caso, com histórico e evidências preservadas. Os ficheiros podem conter informação interna.</p><a class="button secondary small" href="/api/incidents/${i.id}/export?format=markdown" download>Relatório Markdown</a> <a class="button secondary small" href="/api/incidents/${i.id}/export?format=json" download>Dados JSON</a></section>
    <div class="incident-layout"><div>${i.escalation?`<div class="info-note"><strong>Prazo de reconhecimento ultrapassado</strong><p>${fmtDate(i.escalation.escalated_at)} · ${e(i.escalation.from_severity)} → ${e(i.escalation.to_severity)} · prazo de ${i.escalation.deadline_seconds} s · regra v${i.escalation.rule_version}</p></div>`:''}${i.detection_context?`<p class="muted">Deteção pela regra v${i.detection_context.rule_version}: ${i.detection_context.config.failure_samples} sondagens · limite ${i.detection_context.config.effective_latency_ms} ms.</p>`:''}${logContext?`<section><h3>Logs do serviço · últimos 15 minutos</h3>${logContext}${editable() && i.status!=='closed'?`<button class="button secondary small" data-action="save-evidence" data-id="${i.id}">Recolher logs para o caso</button>`:''}<p class="muted">Logs recentes, não limitados a este incidente. Guarda as evidências relevantes nas notas de investigação.</p></section>`:''}${i.evidence?.length?`<section class="saved-evidence"><h3>Evidências preservadas</h3>${i.evidence.map(snapshot=>`<details><summary>Recolha ${snapshot.id} · ${fmtDate(snapshot.captured_at)} · ${e(snapshot.actor)}</summary>${logsScope(snapshot.payload)}${logsTable(snapshot.payload.entries)}</details>`).join('')}</section>`:''}<section><h3>Linha temporal</h3><ol class="timeline">${i.timeline.map(t=>`<li><span class="timeline-point"></span><div><strong>${e(t.action)}</strong><small>${fmtDate(t.created_at)} · ${e(t.actor)}</small>${timelineNote(t)}</div></li>`).join('')}</ol></section>
    ${editable() && i.status!=='closed' ? `<form id="comment-form" data-id="${i.id}" class="compact-form"><label>Acrescentar evidência ou nota<textarea name="note" required maxlength="5000" rows="2"></textarea></label><p class="form-error" role="alert"></p><button class="button secondary" type="submit">Guardar nota</button></form>`:''}
    ${i.resolution?`<section class="postmortem"><h3>Resolução</h3><p>${e(i.resolution)}</p>${i.root_cause?`<h3>Causa raiz</h3><p>${e(i.root_cause)}</p><h3>Prevenção</h3><p>${e(i.prevention)}</p>`:''}${i.runbook?`<h3>Runbook</h3><pre>${e(i.runbook)}</pre>`:''}</section>`:''}
    </div><aside class="incident-aside"><h3>Responsável</h3>${editable() && !['resolved','closed'].includes(i.status)?`<form id="assign-form" data-id="${i.id}" data-revision="${i.revision}"><label class="sr-only" for="assignee">Responsável pelo incidente</label><select id="assignee" name="user_id" required><option value="">Selecionar responsável…</option>${data.users.filter(u=>u.role!=='viewer' && u.active && !u.must_change_password).map(u=>`<option value="${u.id}" ${i.assignee_id===u.id?'selected':''}>${e(u.name)}</option>`).join('')}</select><button class="button secondary small" type="submit">Guardar atribuição</button><p class="form-error" role="alert"></p></form>`:`<p>${e(data.users.find(u=>u.id===i.assignee_id)?.name || 'Por atribuir')}</p>`}
    ${editable() && next ? `<form id="transition-form" data-id="${i.id}" data-revision="${i.revision}" data-next="${next}" class="transition-form"><h3>Próximo passo</h3>${next==='resolved'?'<label>Como foi resolvido?<textarea name="note" minlength="10" maxlength="5000" rows="3" required></textarea></label>':next==='closed'?'<label>Causa raiz<textarea name="root_cause" minlength="10" maxlength="5000" rows="2" required></textarea></label><label>Medida de prevenção<textarea name="prevention" minlength="10" maxlength="5000" rows="2" required></textarea></label><label>Runbook (opcional)<textarea name="runbook" maxlength="5000" rows="3" placeholder="Passos de diagnóstico e resolução"></textarea></label>':'<label>Nota (opcional)<textarea name="note" maxlength="5000" rows="2"></textarea></label>'}<p class="form-error" role="alert"></p><button class="button primary full" type="submit">${actions[next]}</button></form>`:''}
    ${editable() && i.status!=='closed'?`<form id="knowledge-use-form" data-id="${i.id}" class="compact-form"><h3>Conhecimento aplicado</h3><p class="muted">Regista apenas o conhecimento que realmente usaste. Consultar uma sugestão não executa uma solução.</p><label>Número do caso de referência<input name="source_incident_id" type="text" inputmode="numeric" pattern="[0-9]{1,16}" maxlength="16" list="reference-cases" placeholder="Ex.: 8" aria-describedby="reference-help" required></label><datalist id="reference-cases">${data.incidentContext.references.filter(c=>c.id!==i.id).map(c=>`<option value="${c.id}" label="INC-${c.id} · ${e(c.title)}${c.source.startsWith('demo')?' · exemplo sintético':''}"></option>`).join('')}</datalist><p class="muted" id="reference-help">Sugestões dos ${data.incidentContext.references.length} casos resolvidos ou fechados mais recentes${data.incidentContext.references_more?' · existem casos anteriores':''}. Podes indicar o número de um caso mais antigo. Consulta-o em Incidentes antes de registar como ajudou.</p><label>Como ajudou neste caso?<textarea name="reason" required minlength="10" maxlength="2000" rows="3" placeholder="Indica o diagnóstico ou os passos aproveitados e as adaptações necessárias."></textarea></label><p class="form-error" role="alert"></p><button class="button secondary small" type="submit">Registar utilização</button></form>`:''}
    <section class="suggestions"><span class="eyebrow teal">APOIO À TRIAGEM</span><h3>Casos semelhantes</h3><p class="muted">${e(suggestions.method)} · compara casos anteriores; confirma a aplicação da solução.</p>${suggestions.warning?`<p class="info-note">${e(suggestions.warning)}</p>`:''}${suggestions.results.slice(0,3).map(r=>`<button class="suggestion" data-related="${r.id}"><span>INC-${String(r.id).padStart(3,'0')} · ${knowledgeScore(r)}</span><strong>${e(r.title)}</strong><small>${e(r.provenance)}</small>${icon('arrow')}</button>`).join('') || '<p class="muted">Sem correspondências no histórico atual.</p>'}</section></aside></div></div>`;
  return html;
  },true);
}

document.addEventListener('click', async event => {
  const target = event.target.closest('button,a'); if (!target) return;
  const ownerPage=pageRequest, origin=page;
  try {
    if (target.dataset.incident) await incidentModal(Number(target.dataset.incident));
    else if (target.dataset.related) await incidentModal(Number(target.dataset.related),true);
    else if (target.dataset.service) serviceModal(Number(target.dataset.service));
    else if (target.dataset.filter) { incidentFilters={...incidentFilters,view:target.dataset.filter};delete incidentFilters.status;incidentCursor={};await render({loading:true}); }
    else if (target.dataset.action) {
      const action = target.dataset.action;
      if(action==='enterprise-toggle') {target.disabled=true;try{await api('/enterprise/monitoring',{method:'PUT',body:JSON.stringify({enabled:target.dataset.enabled==='true'})});await load();if(origin===page && ownerPage===pageRequest)await render({loading:true});}finally{target.disabled=false;}}
      if(action==='enterprise-refresh') await render({loading:true});
      if(action==='retry-page') await render({loading:true});
      if(action==='incidents-refresh') {incidentCursor={};await render({loading:true});}
      if(action==='incidents-older') {incidentCursor={before_id:target.dataset.before,snapshot_id:target.dataset.snapshot};await render({loading:true});}
      if(action==='incidents-clear') {incidentFilters={view:'all'};incidentCursor={};await render({loading:true});}
      if(action==='audit-refresh') await pageContent(()=>auditPage());
      if(action==='audit-older') await pageContent(()=>auditPage(Number(target.dataset.before),Number(target.dataset.snapshot)));
      if(action==='audit-clear') {auditFilters={};await pageContent(()=>auditPage());}
      if(action==='notices-refresh') {await pageContent(()=>notificationsPage());await refreshNotifications();}
      if(action==='notices-older') await pageContent(()=>notificationsPage(Number(target.dataset.before)));
      if(action==='notices-read') {
        target.disabled=true;
        try {await post('/notifications/read',{through_id:Number(target.dataset.through)});if(page==='notifications' && ownerPage===pageRequest)await pageContent(()=>notificationsPage());await refreshNotifications();toast('Notificações anteriores marcadas como lidas. Os incidentes mantêm o seu estado.');}finally{target.disabled=false;}
      }
      if(action==='close') closeModal();
      if(action==='new-service') newService();
      if(action==='edit-service') {closeModal();serviceForm(Number(target.dataset.id));}
      if(action==='new-user') userForm();
      if(action==='edit-alert-rule') alertRuleForm(Number(target.dataset.id));
      if(action==='slo-history') await sloHistory(Number(target.dataset.id));
      if(action==='rule-history') await ruleHistory(Number(target.dataset.id));
      if(action==='edit-user') userForm(Number(target.dataset.id));
      if(action==='account') modal(`<span class="eyebrow teal">MINHA CONTA</span><h2 id="modal-title">Alterar palavra-passe</h2>${passwordForm()}`);
      if(action==='new-incident') newIncident();
      if(action==='scenario') scenarioModal();
      if(action==='guide') location.hash='guide';
      if(action==='connect-monitoring') await connectMonitoring();
      if(action==='toggle-monitoring') {
        const service=data.services.find(s=>s.id===Number(target.dataset.id));
        target.disabled=true;
        try {await api(`/services/${service.id}/monitoring`,{method:'PUT',body:JSON.stringify({url:service.monitoring.target_url,enabled:!service.monitoring.enabled})});await load();if(origin===page && ownerPage===pageRequest)await render();toast(service.monitoring.enabled?'Recolha pausada. O histórico foi preservado.':'Recolha retomada. Aguarda novas sondagens.');}finally{target.disabled=false;}
      }
      if(action==='lab-fault') {
        target.disabled=true;
        try {const result=await post('/lab/fault',{target:target.dataset.target,kind:target.dataset.kind}); toast(result.kind==='recovery'?'Recuperação pedida. Aguarda a confirmação das sondagens.':'Falha aplicada ao serviço de teste durante, no máximo, 2 minutos. Aguarda as sondagens.');await load();if(origin===page && ownerPage===pageRequest)await render();} finally {target.disabled=false;}
      }
      if(action==='save-impact') {const request=modalRequest;target.disabled=true;try{await post(`/incidents/${Number(target.dataset.id)}/impact`,{});if(request===modalRequest && target.isConnected && await incidentModal(Number(target.dataset.id),true))toast('Avaliação de impacto potencial preservada no caso.');}finally{target.disabled=false;}}
      if(action==='save-evidence') {const request=modalRequest;target.disabled=true;try{await post(`/incidents/${Number(target.dataset.id)}/evidence`,{});if(request===modalRequest && target.isConnected && await incidentModal(Number(target.dataset.id),true))toast('Logs preservados no histórico do caso.');}finally{target.disabled=false;}}
      if(action==='service-logs') await logsModal(Number(target.dataset.id));
      if(action==='logout') {await post('/logout',{}); clearInterval(refreshTimer); clearInterval(notificationTimer); user=null; loginScreen();}
    }
  } catch(error) { toast(error.message); }
});
document.addEventListener('change', async event => {
  if(event.target.id==='slo-window') {sloWindow=event.target.value;try{await render();}catch(error){toast(error.message);}}
});
window.addEventListener('hashchange', async()=>{
  if(!user) return;
  if(location.hash==='#main') { $('#main').focus(); return; }
  closeModal();++pageRequest;page=location.hash.slice(1)||'overview';
  try{if(await render({loading:true}))$('#main').focus();}catch(error){toast(error.message);}
});
document.addEventListener('submit', async event => {
  const form = event.target;
  if(!['service-form','incident-form','scenario-form','assign-form','transition-form','comment-form','knowledge-use-form','audit-filter-form','incident-filter-form','knowledge-form','monitoring-form','user-form','password-form','alert-rule-form'].includes(form.id))return;
  event.preventDefault(); const values = Object.fromEntries(new FormData(form));
  const ownerModal=modalRequest, ownerPage=pageRequest;
  const currentModal=()=>ownerModal===modalRequest && $('#modal').open && form.isConnected;
  const button = $('button[type="submit"]',form); button.disabled=true;
  const errorBox=$('.form-error',form); if(errorBox)errorBox.textContent='';
  try {
    if(form.id==='incident-filter-form') {
      const proposed=Object.fromEntries(Object.entries(values).filter(([,value])=>value!==''));
      if(proposed.date_from && proposed.date_to && proposed.date_from>proposed.date_to) throw new Error('A data inicial não pode ser posterior à data final.');
      incidentFilters={...proposed,view:proposed.status?'all':incidentFilters.view};incidentCursor={};
      await render({loading:true});return;
    }
    if(form.id==='audit-filter-form') {
      const proposed=Object.fromEntries(Object.entries(values).filter(([,value])=>value!==''));
      if(proposed.date_from && proposed.date_to && proposed.date_from>proposed.date_to) throw new Error('A data inicial não pode ser posterior à data final.');
      auditFilters=proposed;await pageContent(()=>auditPage());return;
    }
    if(form.id==='knowledge-form') {
      const params=new URLSearchParams(values);if(!values.service_id)params.delete('service_id');
      const result=await api('/knowledge?'+params);
      if(ownerPage===pageRequest && page==='knowledge' && form.isConnected)$('#knowledge-results').innerHTML=knowledgeReport(result); return;
    }
    if(form.id==='alert-rule-form') {
      const body={...values};
      for(const key of ['enabled','outage_enabled','latency_enabled','escalation_enabled'])body[key]=new FormData(form).has(key);
      for(const key of ['failure_samples','recovery_samples','acknowledge_seconds'])body[key]=Number(values[key]);
      body.latency_ms=values.latency_ms===''?null:Number(values.latency_ms);
      await api(`/services/${Number(form.dataset.id)}/alert-rule`,{method:'PUT',body:JSON.stringify(body)});
      if(!currentModal())return;
      closeModal();await load();if(ownerPage!==pageRequest)return;await render();toast('Regra guardada. Novas sondagens confirmarão o estado; o prazo passa a contar da alteração.');
    } else if(form.id==='password-form') {
      if(values.new_password!==values.confirm_password) throw new Error('As palavras-passe não coincidem.');
      await post('/account/password',{current_password:values.current_password,new_password:values.new_password});
      if(!form.isConnected)return;
      user=await api('/me');closeModal();await start();toast('Palavra-passe alterada. As sessões anteriores foram terminadas.');
    } else if(form.id==='user-form') {
      if(form.dataset.id) await api(`/admin/users/${Number(form.dataset.id)}`,{method:'PUT',body:JSON.stringify({...values,active:new FormData(form).has('active')})});
      else await post('/admin/users',values);
      if(!currentModal())return;
      closeModal();user=await api('/me');await load();shell();await render();toast('Conta guardada. Alterações de acesso revogam as sessões anteriores.');
    } else if(form.id==='monitoring-form') {
      await api(`/services/${Number(values.service_id)}/monitoring`,{method:'PUT',body:JSON.stringify({url:values.url,enabled:new FormData(form).has('enabled')})});
      if(!currentModal())return;
      closeModal();await load();if(ownerPage!==pageRequest)return;await render();toast(values.enabled?'Serviço ligado. Aguarda as primeiras sondagens.':'Ligação guardada com recolha pausada.');
    } else if(form.id==='service-form') {
      await api(form.dataset.id?`/services/${Number(form.dataset.id)}`:'/services',{method:form.dataset.id?'PUT':'POST',body:JSON.stringify({...values,slo_availability:Number(values.slo_availability),slo_latency_ms:Number(values.slo_latency_ms),slo_latency_percent:Number(values.slo_latency_percent),dependencies:new FormData(form).getAll('dependencies').map(Number)})});
      if(!currentModal())return;
      closeModal();await load();if(ownerPage!==pageRequest)return;await render();toast(form.dataset.id?'Serviço atualizado.':'Serviço criado.');
    } else if(form.id==='incident-form') {
      const incident=await post('/incidents',{...values,service_id:Number(values.service_id)});
      if(!currentModal())return;
      closeModal();await load();if(ownerPage!==pageRequest || !await render())return;await incidentModal(incident.id);toast('Incidente registado.');
    } else if(form.id==='scenario-form') {
      const result=await post('/demo/scenario',{...values,service_id:Number(values.service_id)});
      if(!currentModal())return;
      closeModal();await load();if(ownerPage!==pageRequest || !await render())return; if(result.incident_id)await incidentModal(result.incident_id);
      toast(result.incident_id?'Cenário executado. Incidente disponível.':'Observação de recuperação registada.');
    } else {
      const id=Number(form.dataset.id);
      if(form.id==='assign-form') await post(`/incidents/${id}/assign`,{user_id:Number(values.user_id),expected_revision:incidentRevision(form)});
      if(form.id==='comment-form') await post(`/incidents/${id}/comments`,values);
      if(form.id==='knowledge-use-form') {
        const reference=Number(values.source_incident_id);
        if(!/^[0-9]{1,16}$/.test(values.source_incident_id) || !Number.isSafeInteger(reference) || reference<1) throw new Error('Indica um número de incidente válido.');
        await post(`/incidents/${id}/knowledge-use`,{source_incident_id:reference,reason:values.reason});
      }
      if(form.id==='transition-form')await api(`/incidents/${id}`,{method:'PATCH',body:JSON.stringify({...values,status:form.dataset.next,expected_revision:incidentRevision(form)})});
      await load();if(!currentModal())return;
      await render();if(currentModal() && await incidentModal(id,true))toast('Alteração guardada.');
    }
  }catch(error){if(errorBox)errorBox.textContent=error.message;else toast(error.message);}
  finally{button.disabled=false;}
});
(async()=>{
  try {
    config=await api('/config');
    const response=await fetch('/api/me');
    if(response.ok){user=await response.json();await start();}else loginScreen();
  }catch(error){$('#app').innerHTML='<main class="boot"><h1>Não foi possível iniciar o Nexo.</h1><p>'+e(error.message)+'</p><p>Confirma que o servidor está em execução e atualiza a página.</p></main>';}
})();
