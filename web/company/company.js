'use strict';
const connection = document.querySelector('#connection'), orders = document.querySelector('#orders'), button = document.querySelector('#refresh');
const escapeText = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let busy = false;
async function refresh() {
  if (busy) return;
  busy = true; button.disabled = true;
  const started = performance.now();
  try {
    const response = await fetch('/api/orders',{signal:AbortSignal.timeout(5000),cache:'no-store'});
    if (!response.ok) throw new Error(`O serviço de pedidos respondeu com HTTP ${response.status}. Tenta novamente dentro de instantes.`);
    const body = await response.json(), elapsed = Math.round(performance.now()-started);
    connection.className = ''; connection.textContent = `Serviço disponível · resposta em ${elapsed} ms · atualizado às ${new Date().toLocaleTimeString('pt-PT')}`;
    orders.innerHTML = body.orders.map(order=>`<article class="order-row"><strong>${escapeText(order.id)}</strong><span>${escapeText(order.item)}</span><span>${escapeText(order.state)}</span></article>`).join('');
  } catch(error) {
    connection.className = 'failure'; connection.textContent = 'Não foi possível carregar os pedidos.';
    orders.innerHTML = `<p class="failure-message">${escapeText(error.name==='TimeoutError'?'O serviço excedeu o tempo de resposta.':error.message)}</p>`;
  } finally {busy=false;button.disabled=false;}
}
button.addEventListener('click',refresh); refresh(); setInterval(()=>{if(!document.hidden)refresh();},5000);
