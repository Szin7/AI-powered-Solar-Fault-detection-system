const $ = id => document.getElementById(id);
let token = '', role = 'viewer', selected = 'roof-east', socket, frozen = false, cursor = 0, busy = false, refreshTimer, reconnectTimer;
const human = value => String(value ?? 'unavailable').replaceAll('_', ' ');
const number = (value, digits = 1) => Number.isFinite(value) ? value.toFixed(digits) : '—';
const date = value => value ? new Date(typeof value === 'number' ? value * 1000 : value).toLocaleString() : '—';
function text(id, value) { $(id).textContent = value; }
function error(message = '') { text('error', message); $('error').hidden = !message; }
async function api(path, body) {
  const response = await fetch('/api/v1' + path, {method: body === undefined ? 'GET' : 'POST', headers: {...(token ? {Authorization: 'Bearer ' + token} : {}), ...(body === undefined ? {} : {'Content-Type': 'application/json'})}, body: body === undefined ? undefined : JSON.stringify(body)});
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail));
  return value;
}
function element(tag, value, className) { const node = document.createElement(tag); if (value !== undefined) node.textContent = value; if (className) node.className = className; return node; }
function measure(container, label, value) { const node = element('div', undefined, 'measure'); node.append(element('span', label), element('strong', value)); container.append(node); }
function chart(rows) {
  const svg = $('chart'); svg.replaceChildren();
  rows = rows.filter(r => r.result && Number.isFinite(r.payload.ac_power_w)).sort((a,b) => a.observed_at.localeCompare(b.observed_at));
  if (!rows.length) return;
  const max = Math.max(30, ...rows.flatMap(r => [r.payload.ac_power_w, r.result.expected_power_w || 0])) * 1.1;
  const add = (tag, attrs, value) => { const node = document.createElementNS('http://www.w3.org/2000/svg', tag); Object.entries(attrs).forEach(([k,v]) => node.setAttribute(k,v)); if(value !== undefined) node.textContent = value; svg.append(node); };
  for (let i=0;i<4;i++) { const y=20+i*55; add('line',{x1:45,x2:790,y1:y,y2:y,stroke:'#e5ece7'}); add('text',{x:0,y:y+4}, Math.round(max*(1-(y-20)/165))+' W'); }
  for (const [field,color] of [['ac_power_w','#18735b'],['expected_power_w','#c9942b']]) {
    const points=rows.map((r,i)=>[45+i/Math.max(1,rows.length-1)*740,185-(field==='ac_power_w'?r.payload[field]:(r.result[field]||0))/max*165]);
    add('path',{d:points.map(([x,y],i)=>(i?'L':'M')+x.toFixed(2)+','+y.toFixed(2)).join(' '),fill:'none',stroke:color,'stroke-width':2.5});
  }
  add('text',{x:45,y:212},date(rows[0].observed_at)); add('text',{x:790,y:212,'text-anchor':'end'},date(rows.at(-1).observed_at));
}
function stationDetail(station, history, forecast) {
  const result=station.latest, reading=station.reading;
  text('station-id',station.id.toUpperCase()); text('station-name',station.name);
  text('station-status',station.online?'ONLINE · '+(station.config.source_mode || 'simulated').toUpperCase():'OFFLINE / STALE');
  $('measurements').replaceChildren();
  for(const [label,key,unit] of [['DC voltage','voltage_v',' V'],['DC current','current_a',' A'],['Irradiance','irradiance_wm2',' W/m²'],['Panel temperature','surface_temp_c',' °C']]) measure($('measurements'),label,number(reading?.[key])+unit);
  text('diagnosis',human(result?.stabilized_class)); text('resolution',result?.resolution || 'Waiting for committed inference.');
  $('prediction-details').replaceChildren();
  const details={'Raw class':human(result?.raw_class),'Decision':human(result?.decision_state),'Probability method':human(result?.probability_method),'Confidence':result?.confidence == null?'—':number(result.confidence*100)+'%','Input quality':human(result?.quality_state),'Sustained deficit':result?.sustained_deficit?'Yes (>25%, three samples)':'No','Recent votes':result?.stabilization_votes?.map(human).join(', ') || '—','Relay state':reading && (reading.source_kind !== 'hardware' || reading.hardware_protocol === 'espnow_gateway')?String(reading.relay_on?'ON':'OFF'):'—'};
  for(const [key,value] of Object.entries(details)) $('prediction-details').append(element('dt',key),element('dd',value));
  $('explanation').replaceChildren();
  for(const item of result?.explanation || []) { const p=element('p'); p.append(element('span',human(item.feature)+' = '+number(item.value,3)),element('strong',(item.contribution>=0?'+':'')+number(item.contribution,3))); $('explanation').append(p); }
  if(!result?.explanation?.length) $('explanation').append(element('p','Explanations are computed for valid, non-normal decisions.'));
  text('times','Event time: '+date(reading?.observed_at)+' · Last received: '+date(station.last_seen)+' · Model: '+(result?.model_version || 'unavailable'));
  chart(history.readings);
  $('forecast').replaceChildren();
  if(forecast.state==='available') for(const [h,item] of Object.entries(forecast.horizons_minutes)) $('forecast').append(element('strong',h+' min: '+number(item.power_w)+' W ('+item.method+')'));
  else text('forecast',human(forecast.state)+': '+forecast.reason);
}
async function refresh() {
  if(frozen || busy) return;
  busy=true;
  try {
    const fleet=await api('/stations'); if(frozen)return; cursor=fleet.cursor; text('source-mode',fleet.source+' DATA');
    text('clock','Server: '+date(fleet.server_time)); $('fleet').replaceChildren();
    for(const station of fleet.stations) {
      const button=element('button',undefined,'station-card'+(selected===station.id?' selected':''));
      const top=element('div',undefined,'card-top'); top.append(element('h3',station.name),element('span',station.online?'Online':'Offline',station.online?'online':'offline'));
      button.append(top,element('strong',number(station.reading?.ac_power_w)+' W'),element('small',human(station.latest?.stabilized_class)+' · '+(station.online?'live telemetry':'last known values')));
      button.onclick=()=>{selected=station.id; refresh();}; $('fleet').append(button);
    }
    const [history,forecast,incidents,commands,reviews]=await Promise.all([api('/stations/'+selected+'/history'),api('/stations/'+selected+'/forecast'),api('/incidents'),api('/commands'),api('/reviews')]);
    if(frozen)return;
    const station=fleet.stations.find(s=>s.id===selected); if(station) stationDetail(station,history,forecast);
    $('incidents').replaceChildren();
    for(const incident of incidents.incidents) {
      const tr=element('tr'), main=element('td',human(incident.label)); main.append(element('small',incident.station_id+' · #'+incident.id));
      const times=element('td',date(incident.opened_at)); times.append(element('small','Event: '+date(incident.observed_at)));
      const jobs=incidents.events.filter(e=>e.incident_id===incident.id).map(e=>incidents.notifications.find(n=>n.event_id===e.id)).filter(Boolean);
      const action=element('td'); if(!incident.acknowledged_at) {const button=element('button','Acknowledge'); button.disabled=role!=='operator'; button.onclick=()=>act(()=>api('/incidents/'+incident.id+'/ack',{})); action.append(button);} else action.textContent='Acknowledged';
      tr.append(main,times,element('td',incident.status),element('td',jobs.map(j=>j.payload.kind+': '+j.status+' ('+j.attempts+')').join('; ')),action); $('incidents').append(tr);
    }
    if(!incidents.incidents.length){const tr=element('tr');const td=element('td','No incidents recorded.');td.colSpan=5;tr.append(td);$('incidents').append(tr);}
    const command=commands.find(c=>c.station_id===selected);
    if(command) text('command-status','Last command #'+command.id+': requested '+(command.desired?'ON':'OFF')+' · '+command.status+(command.confirmed===null?'':' · confirmed '+(command.confirmed?'ON':'OFF')));
    $('review-queue').replaceChildren();
    for(const item of reviews.queue.slice(0,8)) { const button=element('button','#'+item.telemetry_id+' · '+item.station_id+' · '+human(item.result.decision_state),'secondary');button.onclick=()=>{$('reading-id').value=item.telemetry_id;};$('review-queue').append(button); }
    if(!reviews.queue.length) text('review-queue','No uncertain or invalid readings in the last 500 results.');
    error();
  } catch(err) { error(err.message); } finally { busy=false; }
}
async function evidence() {
  const report=await api('/model'); $('benchmarks').replaceChildren();
  measure($('benchmarks'),'Held-out accuracy',number(report.classification.accuracy*100,2)+'%'); measure($('benchmarks'),'Macro F1',number(report.classification.macro_f1,4)); measure($('benchmarks'),'Accepted coverage',number(report.coverage*100,1)+'%');
  text('comparison',Object.entries(report.baselines).map(([name,value])=>human(name)+': test F1 '+number(value.test.macro_f1,4)).join(' · '));
  text('model-version','Release '+report.model_version+' · '+report.dataset.rows+' synthetic rows · Whole-session splits · Seed '+report.seed);
}
function connectSocket() {
  clearTimeout(reconnectTimer);
  socket=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
  socket.onopen=()=>socket.send(JSON.stringify({token,cursor}));
  socket.onmessage=event=>{const value=JSON.parse(event.data); if(!frozen) text('connection','Live subscription'); if(value.type==='connected'||value.type==='changed') refresh();};
  socket.onclose=()=>{text('connection','Reconnecting…');reconnectTimer=setTimeout(connectSocket,2500);};
  socket.onerror=()=>socket.close();
}
async function act(fn) { try { await fn(); error(); await refresh(); } catch(err) { error(err.message); } }
$('login').onsubmit=async event=>{event.preventDefault();token=$('token').value.trim(); try{const me=await api('/me');role=me.role;if(role==='device')throw new Error('Use a viewer or operator key.');$('token').value='';text('role','Connected as '+role+' · key kept only in this page’s memory');for(const id of ['apply','schedule','relay-on','relay-off','review-submit'])$(id).disabled=role!=='operator';if(socket){socket.onclose=null;socket.close();}await refresh();await evidence();connectSocket();clearInterval(refreshTimer);refreshTimer=setInterval(refresh,2000);}catch(err){error(err.message);}};
$('freeze').onclick=()=>{frozen=!frozen;text('freeze',frozen?'Resume display':'Freeze display');text('connection',frozen?'Frozen at '+new Date().toLocaleTimeString():'Live subscription');if(!frozen)refresh();};
$('scenario-form').onsubmit=event=>{event.preventDefault();act(()=>api('/stations/'+selected+'/scenario',{fault:$('fault').value,severity:Number($('severity').value),network:$('network').value,cloud:1,enabled:true}));};
$('schedule').onclick=()=>act(()=>api('/stations/'+selected+'/scenario',{enabled:false}));
for(const [id,relay] of [['relay-on',true],['relay-off',false]])$(id).onclick=()=>act(()=>api('/stations/'+selected+'/commands',{relay_on:relay,ttl_seconds:30}));
$('review-form').onsubmit=event=>{event.preventDefault();act(()=>api('/readings/'+$('reading-id').value+'/reviews',{label:$('review-label').value,reason:$('reason').value}));};
