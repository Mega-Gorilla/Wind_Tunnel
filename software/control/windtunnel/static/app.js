"use strict";
const $ = id => document.getElementById(id);
let csrf = sessionStorage.getItem("wt_csrf"), status = null, page = "monitor", authorized = false;
let recipePending = null, draftVersion = 0, trend = [], lastSeq = null, historyOffset = 0;
let connectionLost = false, modeInitialized = false;
const labels = {IDLE:"停止待機", RUNNING:"試験中", FAULT:"異常", COMPLETED:"完了", CANCELLED:"中止", FAILED:"異常終了", INTERRUPTED:"中断"};
const faultLabels = {SIMULATED_OFFLINE:"模擬Picoの接続断", SIMULATED_SENSOR:"模擬センサー異常", SIMULATED_POWER:"模擬電源異常", STORAGE_OR_CONTROLLER_FAILURE:"記録・制御処理の異常", offline:"Pico接続断", sensor:"センサー異常", power:"電源異常"};
const reasonLabels = {recipe_complete:"すべての段階を完了", stop_requested:"停止ボタン / 停止API", run_cancelled:"試験の取消", remote_mode_off:"遠隔モードをOFF", remote_permit_expired:"遠隔許可の期限切れ", local_ui_heartbeat_lost:"本体画面との通信が途絶", client_revoked:"APIトークンの失効", service_shutdown:"サービス終了", service_restart:"サービス再起動", ...faultLabels};
const errors = {REMOTE_MODE_OFF:"遠隔モードがOFFです", CONTROL_BUSY:"別の試験を実行中です", TURN_REMOTE_MODE_OFF_FIRST:"本体から開始する前に遠隔モードをOFFにしてください", STALE_CONTROL_EPOCH:"停止または許可状態が変更されました。条件を確認し直してください", LOCAL_UI_HEARTBEAT_REQUIRED:"本体画面の通信を確認してください", DEVICE_NOT_READY:"模擬機器の異常を解消してください", INVALID_REQUEST:"入力範囲を確認してください（合計300秒以内）", FAULT_CAUSE_REMAINS:"先に模擬障害の原因を解消してください"};
Object.assign(faultLabels,{PICO_DISCONNECTED:"Pico USB接続断",PICO_SENSOR_ERROR:"センサー読出し異常",PICO_STALE:"Picoデータ更新停止",PICO_STOP_NOT_CONFIRMED:"停止設定未確認",PICO_FIRMWARE_MISMATCH:"Picoファームウェア不一致",CONNECTING:"Pico接続待ち",WARMING_UP:"センサー安定待ち"});
Object.assign(errors,{HARDWARE_MONITOR_ONLY:"実機は停止計測専用です。運転できません",FAULT_ACTIVE:"機器の異常または接続待ちです",DEVICE_NOT_READY:"機器の状態を確認してください",FAULT_CAUSE_REMAINS:"先に機器の異常を解消してください"});
Object.assign(labels,{ARMING:"開始確認中",STOPPING:"停止応答待ち"});
Object.assign(errors,{SUPPLY_CHECK_SW1:"12 V電源とSW1を確認してください",WAIT_FOR_FAN_STOP:"回転が止まるまで待ってください",STOPPED_CURRENT:"停止中の電流を確認してください",STOP_NOT_CONFIRMED:"Picoの停止応答を待ってください"});
Object.assign(faultLabels,{PICO_FW_LEASE_EXPIRED:"Picoの通信更新期限切れ",PICO_FW_TACH_MISSING:"回転パルス未検出",PICO_FW_CURRENT_RANGE:"電流異常",PICO_FW_SUPPLY_RANGE:"電源電圧異常",PICO_FW_PRESSURE_RANGE:"差圧上限超過",PICO_FW_SENSOR_ERROR:"Picoセンサー異常",PICO_RESTARTED:"Picoが再起動",PICO_CONTROLLER_HEARTBEAT_LOST:"制御処理の更新停止",PICO_STOP_UNCONFIRMED:"停止応答を確認できません"});
Object.assign(reasonLabels,faultLabels);
function icon(name) {
  const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
  svg.setAttribute("class","icon");svg.setAttribute("viewBox","0 0 24 24");svg.setAttribute("aria-hidden","true");svg.setAttribute("focusable","false");
  const use=document.createElementNS("http://www.w3.org/2000/svg","use");use.setAttribute("href",`/static/icons.svg#${name}`);svg.append(use);return svg;
}
function labelled(el, name, text, tone) {
  const key=`${name}|${text}`;
  if(el.dataset.label!==key){el.replaceChildren(icon(name),document.createTextNode(text));el.dataset.label=key;}
  if(tone)el.dataset.tone=tone;
}
function visual(state) {
  return {RUNNING:["play","running"],COMPLETED:["check","success"],CANCELLED:["stop","warning"],FAILED:["warning","error"],FAULT:["warning","error"],INTERRUPTED:["warning","warning"]}[state] || ["pause","neutral"];
}
function message(text, tone="info") {
  $("message-text").textContent=text;$("message").hidden=!text;$("message").dataset.tone=tone;
  $("message-icon").replaceChildren(icon({success:"check",error:"warning",warning:"warning"}[tone]||"info"));
}
$("message-close").onclick=()=>message("");
async function api(path, options = {}) {
  const headers = {...options.headers};
  if (options.method && options.method !== "GET") { headers["Content-Type"] = "application/json"; headers["X-CSRF-Token"] = csrf || ""; }
  const response = await fetch("/api/v1" + path, {...options, headers, signal:AbortSignal.timeout(4000)});
  if (!response.ok) { const error = await response.json().catch(()=>({code:"NETWORK_ERROR"})); throw new Error(errors[error.code] || error.code || response.status); }
  return response;
}
async function json(path, options) { return (await api(path, options)).json(); }
function write(path, value = {}, method = "POST", headers = {}) { return json(path, {method, body:JSON.stringify(value), headers}); }
function safe(handler) { return async (...args) => { try { await handler(...args); } catch (e) { message(e.message,"error"); } }; }
function showPage(name) {
  page = name; document.querySelectorAll(".page").forEach(el=>el.hidden=el.id!==name);
  document.querySelectorAll("nav button").forEach(el=>{const active=el.dataset.page===name;el.classList.toggle("selected",active);if(active)el.setAttribute("aria-current","page");else el.removeAttribute("aria-current");});
  document.querySelector("main").scrollTop=0;
  if (name==="history") safe(loadHistory)(); if(name==="settings") safe(loadClients)();
}
document.querySelectorAll("nav button").forEach(el=>el.onclick=()=>showPage(el.dataset.page));
function fmt(value, digits=1) { return value == null ? "—" : Number(value).toFixed(digits); }
function render(s) {
  const wasAcknowledging=status?.acknowledging;
  status=s; const t=s.telemetry; const real=!s.simulation; const locked=real&&!s.fan_control_available; const stale=t.age_ms==null || t.age_ms>1500 || !t.valid;
  if(!modeInitialized){if(real&&$("test-name").value==="模擬段階テスト")$("test-name").value="ファン段階テスト";modeInitialized=true;}
  if(wasAcknowledging&&!s.acknowledging)message(s.fault?`解除できません：${faultLabels[s.fault]||s.fault}`:"異常を解除しました。自動再開しません。",s.fault?"error":"success");
  $("mode-badge").textContent=real?(locked?"実測・停止専用":"実測・実機制御"):"SIMULATION";
  $("mode-badge").title=$("mode-badge").textContent;
  document.title=`WindTunnel · ${$("mode-badge").textContent}`;
  $("rpm-note").textContent=locked?"未計測 / 運転禁止":real?"Pico計数 · 2 pulse/rev 仮定":"推定値 · 2 pulse/rev 仮定";
  $("dp-note").textContent=real?"SDP810 · 符号付き実測":"符号付き · 風速換算未校正";
  $("measurement-note").textContent=locked?"実Pico → USB · ファン指令0固定 · RPM・風速は未計測/未校正":real?"実Pico計測 · 停止指令と惰性回転は別 · 風速は未校正":"すべて模擬値です。実機の風速・回転数ではありません。";
  $("hardware-test-note").hidden=!locked;$("hardware-details").hidden=!real;$("simulation-faults").hidden=real;$("remote-max-label").hidden=locked;
  $("sensor-details").textContent=real?`FW ${t.firmware||"未確認"} / ${t.device_id||"未接続"} · GP16 ${t.gp16_level===0?"LOW確認":t.pwm_applied_percent>0?"PWM適用中":"未確認"} · ${["sdp","bme","ina"].map(k=>`${k.toUpperCase()}: ${t.sensor_errors?.[k]|| (t.connected?"正常":"未確認")}`).join(" / ")}`:"";
  $("monitor").classList.toggle("stale",stale);
  $("control-mode").textContent=s.remote.enabled?"遠隔許可 ON":"本体操作";
  const [stateIcon,stateTone]=visual(s.state);
  labelled($("system-state"),stateIcon,locked&&s.state==="IDLE"?"停止計測":labels[s.state]||s.state,stateTone);
  labelled($("freshness"),stale?"warning":"check",stale?`要確認 · ${faultLabels[t.reason]||t.reason||"更新待ち"}`:(real?"実Pico · 2 Hz":"模擬Pico · 2 Hz"),stale?"error":"neutral");
  $("rpm").textContent=fmt(t.rpm_estimated,0); $("dp").textContent=fmt(t.differential_pressure_pa,2);
  $("environment").textContent=`${fmt(t.temperature_c)} °C / ${fmt(t.relative_humidity_percent,0)} %`;
  $("pressure").textContent=`${fmt(t.ambient_pressure_pa==null?null:t.ambient_pressure_pa/100)} hPa`;
  $("electrical").textContent=`${fmt(t.bus_voltage_v,2)} V / ${fmt(t.current_a==null?null:t.current_a*1000,0)} mA`;
  $("power").textContent=`${fmt(t.power_w,2)} W`;
  $("requested").textContent=`${fmt(s.pwm_requested_percent,0)}%`;
  $("applied").textContent=`${fmt(t.pwm_applied_percent,0)}%`;
  const run=s.active_run;
  $("run-progress").textContent=run?`${run.owner_name} · 段階 ${run.step_index+1} ${{record:"収録中",settle:"整定待ち",precheck:"開始確認中",stopping:"停止応答待ち"}[run.phase]||run.phase} · ${Math.floor(run.elapsed_s)} / ${run.duration_s}秒`:faultLabels[s.fault] || s.fault || "停止待機 / 自動再開なし";
  $("run-icon").replaceChildren(icon(s.fault?"warning":run?(run.phase==="record"?"file":"clock"):"pause"));
  $("run-meter").value=run?Math.min(100,run.elapsed_s/run.duration_s*100):0;
  $("run-meter").hidden=false;
  $("run-meter").setAttribute("aria-valuetext",run?`${Math.floor(run.elapsed_s)}秒 / ${run.duration_s}秒`:"実行中の試験なし");
  $("remote-mode").textContent=s.remote.enabled?"ON":"OFF";
  $("remote-icon").replaceChildren(icon(s.remote.enabled?"unlock":"lock"));
  $("remote-status").dataset.tone=s.remote.enabled?"running":"neutral";
  $("permit-note").textContent=s.remote.enabled?`無期限 · OFFするまで有効（異常・再起動・画面通信断は安全OFF）。許可IP＋APIトークンが必要${locked?"。現在は停止計測専用です。":` · 最大PWM ${s.remote.permit.max_pwm_percent}%`}`:"許可IP＋APIトークンがあっても、OFFでは開始できません。";
  $("remote-on").disabled=!!run || !!s.fault || stale; $("review").disabled=locked || !!run || s.remote.enabled || !!s.fault || stale;
  const sampleKey=`${t.boot_id||"sim"}:${t.seq}`;
  if(t.seq!=null && sampleKey!==lastSeq){lastSeq=sampleKey; trend.push(t); trend=trend.slice(-120);}
  const points=(key,scale)=>trend.filter(v=>v[key]!=null).map((v,i)=>`${30+i*360/119},${80-v[key]*scale}`).join(" ");
  $("rpm-line").setAttribute("points",points("rpm_estimated",72/2400));
  $("dp-line").setAttribute("points",points("differential_pressure_pa",-72/20));
  $("rpm-legend").textContent=locked?"RPM 未計測":"RPM";
  $("rpm-axis-top").textContent=locked?"":"2400";$("rpm-axis-bottom").textContent=locked?"":"0";
  const range=real?Math.max(1,...trend.map(v=>Math.abs(v.differential_pressure_pa||0)))*1.1:20;
  $("dp-axis-top").textContent=real?`+${fmt(range,1)} Pa`:"−20 Pa";$("dp-axis-bottom").textContent=real?`−${fmt(range,1)} Pa`:"0 Pa";
  if(real){if(locked)$("rpm-line").setAttribute("points","");$("dp-line").setAttribute("points",trend.map((v,i)=>v.differential_pressure_pa==null?null:`${30+i*360/119},${44-v.differential_pressure_pa*36/range}`).filter(Boolean).join(" "));}
}
async function poll() {
  try {
    render(await json("/status"));
    if(connectionLost){connectionLost=false;message("通信が復旧しました。表示を更新しました。","success");}
  } catch(e) {
    connectionLost=true;labelled($("system-state"),"unplug","接続断・停止未確認","error");
    labelled($("freshness"),"warning","更新停止・過去の値","error");$("control-mode").textContent="操作状態不明";
    $("monitor").classList.add("stale");status=null;$("review").disabled=true;$("remote-on").disabled=true;
    $("run-icon").replaceChildren(icon("warning"));$("run-progress").textContent="通信断 / 停止できたか未確認";$("run-meter").hidden=true;
    $("remote-mode").textContent="不明";$("remote-icon").replaceChildren(icon("warning"));$("remote-status").dataset.tone="error";
    $("permit-note").textContent="通信断のため、現在の遠隔許可状態を確認できません。";
    message("通信できません。表示値は現在値ではありません。","error");
  }
  setTimeout(poll,500);
}
async function heartbeat() {
  if (authorized && document.visibilityState === "visible") {
    try { await write("/local/heartbeat"); } catch(e) { message(e.message,"error"); }
  }
  setTimeout(heartbeat,1000);
}
$("stop").onclick=safe(async()=>{draftVersion++;recipePending=null; $("confirmation").hidden=true; render(await write("/stop")); message(status.simulation?"停止指令を送信しました。遠隔許可もOFFです（模擬環境）。":"停止要求を受け付けました。遠隔OFFです。適用設定と回転数の低下を確認してください。","success");});

function addStep(pwm=40, settle=2, record=3) {
  if($("steps").children.length>=12)return;
  const row=document.createElement("tr");
  const number=document.createElement("td"); row.append(number);
  [pwm,settle,record].forEach((v,index)=>{
    const cell=document.createElement("td"), input=document.createElement("input");
    input.type="number";input.value=v; input.min=index===2?1:0;input.max=index===0?100:120;input.step=1;
    input.setAttribute("aria-label",["PWM","整定待ち秒","収録秒"][index]);
    if(index===0){ const wrap=document.createElement("div");wrap.className="step-pwm";
      for(const delta of [-20,20]){const b=document.createElement("button");b.append(icon(delta<0?"minus":"plus"));b.setAttribute("aria-label",delta<0?"PWMを20ポイント下げる":"PWMを20ポイント上げる");b.type="button";b.onclick=()=>{input.value=Math.min(100,Math.max(0,Number(input.value)+delta));invalidate();};if(delta<0)wrap.append(b,input);else wrap.append(b);} cell.append(wrap);
    } else cell.append(input);
    input.oninput=invalidate; row.append(cell);
  });
  const last=document.createElement("td"), remove=document.createElement("button");labelled(remove,"trash","削除");remove.onclick=()=>{row.remove();renumber();invalidate();};last.append(remove);row.append(last);$("steps").append(row);renumber();invalidate();
}
function renumber(){[...$("steps").children].forEach((r,i)=>r.firstChild.textContent=String(i+1));}
function recipe(){return {name:$("test-name").value.trim(),mode:"pwm",repeat:Number($("repeat").value),steps:[...$("steps").children].map(r=>{const v=[...r.querySelectorAll("input")].map(i=>Number(i.value));return {pwm_percent:v[0],settle_s:v[1],record_s:v[2]};})};}
function invalidate(){draftVersion++;recipePending=null;$("confirmation").hidden=true;const r=recipe();labelled($("duration"),"clock",`合計 ${r.steps.reduce((n,s)=>n+s.settle_s+s.record_s,0)*r.repeat} 秒`);}
$("add-step").onclick=()=>addStep();$("repeat").oninput=invalidate;$("test-name").oninput=invalidate;
$("preset").onclick=()=>{$("steps").replaceChildren();[20,40,60,80,100].forEach(p=>addStep(p,status?.simulation?2:4,status?.simulation?3:6));};
$("review").onclick=safe(async()=>{const version=draftVersion;const r=recipe();const v=await write("/runs/validate",r);const s=await json("/status");if(version!==draftVersion)return;recipePending={body:{recipe:r,control_epoch:s.control_epoch},key:crypto.randomUUID()};$("confirm-text").textContent=`${s.simulation?"模擬試験":"実機ファンが回転します"}・${r.steps.length}段階・${v.duration_s}秒。終了後はPWM 0。${s.simulation?"":"周囲に接触物がないことを確認してください。"}`;message("");$("confirmation").hidden=false;$("confirmation").scrollIntoView({block:"nearest"});});
$("dismiss").onclick=()=>{draftVersion++;$("confirmation").hidden=true;recipePending=null;};
$("start-run").onclick=safe(async()=>{
  if(!recipePending)return;const pending=recipePending;const version=draftVersion;recipePending=null;$("start-run").disabled=true;
  try {await write("/runs",pending.body,"POST",{"Idempotency-Key":pending.key});$("confirmation").hidden=true;showPage("monitor");message("");}
  catch(e){if(version===draftVersion){recipePending=pending;message(`${e.message}。履歴で確認するか、同じ開始ボタンで同一要求を再確認できます。`,"error");}else message(e.message,"error");}
  finally {$("start-run").disabled=false;}
});
async function loadHistory(){
  const {items}=await json(`/runs?limit=10&offset=${historyOffset}`);$("history-list").replaceChildren();$("run-detail").hidden=true;
  if(!items.length){const empty=document.createElement("div");empty.className="empty-state";const title=document.createElement("strong");title.textContent="このページに試験履歴はありません";empty.append(icon("history"),title,document.createTextNode("「テスト」画面で試験を実行すると、条件と結果がここに保存されます。"));$("history-list").append(empty);}
  for(const r of items){
    const row=document.createElement("div");row.className="history-row";
    const state=document.createElement("span");state.className="status-pill";
    const [stateIcon,stateTone]=visual(r.state);labelled(state,stateIcon,labels[r.state]||r.state,stateTone);row.append(state);
    const info=document.createElement("div"), title=document.createElement("strong"), sub=document.createElement("small");info.className="history-info";title.textContent=r.recipe.name;sub.textContent=`${r.simulation?"模擬試験":"実測試験"} · ${r.duration_s}秒 · ${new Date(r.started_at).toLocaleString("ja-JP")}`;info.append(title,sub);row.append(info);
    const actions=document.createElement("div");actions.className="history-actions";
    for(const kind of ["詳細","CSV","JSON"]){const b=document.createElement("button");labelled(b,kind==="詳細"?"file":"download",kind);b.onclick=safe(async()=>{if(kind==="詳細"){showRunDetail(await json(`/runs/${r.id}`));}else{const response=await api(`/runs/${r.id}/export?format=${kind.toLowerCase()}`);const url=URL.createObjectURL(await response.blob());const a=document.createElement("a");a.href=url;a.download=`${r.simulation?"simulation":"measurement"}-${r.id}.${kind.toLowerCase()}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}});actions.append(b);}row.append(actions);$("history-list").append(row);
  }$("history-page").textContent=`${historyOffset/10+1}ページ`;$("history-prev").disabled=historyOffset===0;$("history-next").disabled=items.length<10;
}
function showRunDetail(run) {
  const target=$("run-detail");target.replaceChildren();
  const title=document.createElement("h2");labelled(title,"file",run.recipe.name);
  const grid=document.createElement("dl");grid.className="result-grid";
  const fields=[["結果",`${labels[run.state]||run.state} / ${run.simulation?"模擬試験":"実測試験"}`],["操作者",`${run.owner_name}（${run.source==="local"?"本体":"遠隔API"}）`],["時間",`${fmt(run.elapsed_s,1)}秒 / 予定${run.duration_s}秒`],["終了理由",reasonLabels[run.reason]||(run.reason?`未分類：${run.reason}`:"実行中")],["試験条件",`${run.recipe.steps.length}段階 × ${run.recipe.repeat}回`],["開始日時",new Date(run.started_at).toLocaleString("ja-JP")]];
  for(const [name,value] of fields){const item=document.createElement("div"),term=document.createElement("dt"),desc=document.createElement("dd");term.textContent=name;desc.textContent=value;item.append(term,desc);grid.append(item);}
  const raw=document.createElement("details"),summary=document.createElement("summary"),pre=document.createElement("pre");summary.textContent="開発者向け：元データ（JSON）";pre.textContent=JSON.stringify(run,null,2);raw.append(summary,pre);
  target.append(title,grid,raw);target.hidden=false;target.scrollIntoView({block:"nearest"});
}
$("refresh-history").onclick=safe(loadHistory);$("history-prev").onclick=safe(async()=>{historyOffset=Math.max(0,historyOffset-10);await loadHistory();});$("history-next").onclick=safe(async()=>{historyOffset+=10;await loadHistory();});
$("remote-on").onclick=safe(async()=>{await write("/control/remote-permit",{max_pwm_percent:Number($("remote-max").value)});render(await json("/status"));message("遠隔モードON・時間制限なし。許可IP・APIトークンの認証は維持します。");});
$("remote-off").onclick=safe(async()=>{await write("/control/remote-permit",{},"DELETE");render(await json("/status"));message("遠隔モードOFF。実行中の遠隔試験も停止しました。");});
async function loadClients(){
  const {items}=await json("/local/clients");$("clients").replaceChildren();
  if(!items.length){const hint=document.createElement("p");labelled(hint,"lock","未登録です。外部からの操作は許可されていません。");$("clients").append(hint);}
  for(const c of items){
    const row=document.createElement("div");row.className="client-row";
    const info=document.createElement("div"),name=document.createElement("strong"),ip=document.createElement("small"),scope=document.createElement("small");info.className="client-info";name.textContent=c.name;ip.textContent=`許可IP：${c.allowed_ips.join(", ")}`;scope.textContent=c.revoked?"失効済み":c.scopes.map(s=>({read:"読取り",plan:"条件検証",control:"試験開始",stop:"停止"}[s]||s)).join(" / ");info.append(name,ip,scope);
    const b=document.createElement("button");labelled(b,"lock","失効");b.disabled=c.revoked;b.onclick=safe(async()=>{await write(`/local/clients/${c.id}`,{},"DELETE");await loadClients();});row.append(icon(c.revoked?"lock":"key"),info,b);$("clients").append(row);
  }
}
$("create-client").onclick=safe(async()=>{const c=await write("/local/clients",{name:$("client-name").value.trim(),allowed_ips:$("client-ips").value.split(",").map(v=>v.trim()),scopes:$("client-control").checked?["read","plan","control","stop"]:["read","plan"]});$("new-token").value=c.token;$("new-token").type="password";$("token-result").hidden=false;await loadClients();message("APIトークンはこの欄で一度だけ確認できます。保存後は閉じてください。");});
$("show-token").onclick=()=>{$("new-token").type=$("new-token").type==="password"?"text":"password";};$("hide-token").onclick=()=>{$("new-token").value="";$("token-result").hidden=true;};
$("inject").onclick=safe(async()=>{render(await write("/local/simulation/fault",{fault:$("fault-select").value}));});
$("acknowledge").onclick=safe(async()=>{render(await write("/faults/acknowledge"));message(status.acknowledging?"Picoの異常解除を確認中です。":"異常を解除しました。試験は自動再開しません。",status.acknowledging?"info":"success");});
async function init(){
  document.querySelectorAll("[data-icon]").forEach(el=>{el.replaceChildren(icon(el.dataset.icon));el.setAttribute("aria-hidden","true");});
  addStep();
  const bootstrap=new URLSearchParams(location.hash.slice(1)).get("bootstrap");
  history.replaceState(null,"",location.pathname);
  try {
    if(bootstrap){const result=await write("/local/session",{code:bootstrap});csrf=result.csrf_token;sessionStorage.setItem("wt_csrf",csrf);}
    if(!csrf)return;
    await write("/local/heartbeat");authorized=true;$("login").hidden=true;$("stop").disabled=false;document.querySelectorAll("nav button").forEach(b=>b.disabled=false);showPage("monitor");heartbeat();poll();
  }catch(e){message(`認証できません：${e.message}。起動時の一回限りリンクを利用してください。`,"error");}
}
init();
