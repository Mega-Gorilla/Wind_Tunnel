"use strict";
// Native touch scrolling is left to the browser. This fallback handles labwc's
// mouse-emulated touchscreen without changing the working display calibration.
(() => {
  const main=document.querySelector("main");
  const sheet=document.getElementById("touch-editor");
  const field=document.getElementById("touch-value");
  const keys=document.getElementById("touch-keys");
  const hint=document.getElementById("touch-hint");
  const toggle=document.getElementById("touch-keyboard-enabled");
  let enabled=true, drag=null, suppressClickUntil=0, target=null, symbols=false, upper=false;
  try { enabled=localStorage.getItem("wt_touch_keyboard")!=="off"; } catch {}
  toggle.checked=enabled;
  toggle.onchange=()=>{enabled=toggle.checked;try{localStorage.setItem("wt_touch_keyboard",enabled?"on":"off");}catch{}closeEditor();};
  document.addEventListener('pointerdown',e=>{
    const input=e.target.closest('main input');
    if(enabled&&input&&!input.disabled&&!input.readOnly&&['text','number'].includes(input.type))e.preventDefault();
  },true);

  function scrollChain(element) {
    const result=[];
    for(let el=element;el&&main.contains(el);el=el.parentElement) {
      const style=getComputedStyle(el);
      if(/auto|scroll/.test(style.overflowY+style.overflowX))result.push(el);
      if(el===main)break;
    }
    return result;
  }
  function moveScroll(chain,dx,dy) {
    for(const el of chain) {
      const x=el.scrollLeft,y=el.scrollTop;
      el.scrollLeft+=dx;el.scrollTop+=dy;
      dx-=el.scrollLeft-x;dy-=el.scrollTop-y;
    }
  }
  main.addEventListener("pointerdown",e=>{
    // Text selection/copy and native input editing retain their normal behavior.
    if(e.pointerType!=="mouse"||e.button!==0||!e.isPrimary||
       e.target.closest('input,textarea,select,pre,code,[contenteditable="true"]'))return;
    drag={id:e.pointerId,x:e.clientX,y:e.clientY,lastX:e.clientX,lastY:e.clientY,
          chain:scrollChain(e.target),moved:false};
  });
  window.addEventListener("pointermove",e=>{
    if(!drag||e.pointerId!==drag.id)return;
    if(!drag.moved&&Math.hypot(e.clientX-drag.x,e.clientY-drag.y)<10)return;
    if(!drag.moved){drag.moved=true;main.setPointerCapture(e.pointerId);main.classList.add("drag-scrolling");}
    e.preventDefault();
    moveScroll(drag.chain,drag.lastX-e.clientX,drag.lastY-e.clientY);
    drag.lastX=e.clientX;drag.lastY=e.clientY;
  },{passive:false});
  function endDrag(e) {
    if(!drag||(e&&e.pointerId!==undefined&&e.pointerId!==drag.id))return;
    const current=drag;drag=null;
    if(current.moved)suppressClickUntil=performance.now()+400;
    if(main.hasPointerCapture(current.id))main.releasePointerCapture(current.id);
    main.classList.remove("drag-scrolling");
  }
  window.addEventListener("pointerup",endDrag);
  window.addEventListener("pointercancel",endDrag);
  main.addEventListener("lostpointercapture",endDrag);
  window.addEventListener("blur",()=>{endDrag();closeEditor();});
  document.addEventListener("visibilitychange",()=>{if(document.hidden){endDrag();closeEditor();}});
  main.addEventListener("dragstart",e=>{if(drag)e.preventDefault();});

  // Capture runs before app.js's start/delete/permission click handlers.
  document.addEventListener("click",e=>{
    if(e.target.closest("#stop")){suppressClickUntil=0;closeEditor();return;}
    if(e.detail!==0&&performance.now()<suppressClickUntil){
      suppressClickUntil=0;e.preventDefault();e.stopImmediatePropagation();return;
    }
    if(e.target.closest("nav")){closeEditor();return;}
    const input=e.target.closest("main input");
    if(enabled&&input&&!input.disabled&&!input.readOnly&&['text','number'].includes(input.type)){
      e.preventDefault();e.stopImmediatePropagation();openEditor(input);
    }
  },true);

  function closeEditor() {
    sheet.hidden=true;main.inert=false;target=null;field.value="";hint.textContent="";
  }
  function button(label,action,className="",aria=label) {
    const b=document.createElement("button");b.type="button";b.textContent=label;
    b.className=className;b.setAttribute("aria-label",aria);
    // Preserve the editing cursor while using on-screen keys.
    b.onpointerdown=e=>e.preventDefault();b.onclick=action;return b;
  }
  function insert(text) {
    field.setRangeText(text,field.selectionStart,field.selectionEnd,"end");
    field.focus({preventScroll:true});hint.textContent="入力後に「決定」。運転は開始しません。";
  }
  function erase() {
    let a=field.selectionStart,b=field.selectionEnd;
    if(a===b)a=Math.max(0,a-1);
    field.setRangeText("",a,b,"end");field.focus({preventScroll:true});
  }
  function commit() {
    if(!target||!target.isConnected||target.disabled||target.readOnly){closeEditor();return;}
    const value=field.value;
    const copy=target.cloneNode(false);copy.value=value;
    let error="";
    if(target.type==="number") {
      if(!/^\d+(?:\.\d*)?$/.test(value.trim())||!copy.checkValidity())
        error=`${target.min||0}～${target.max||"上限なし"}の数値を入力してください。`;
      if(target.getAttribute("aria-label")==="PWM"&&Number(value)>0&&Number(value)<20)
        error="PWMは0、または20～100を入力してください。";
    } else if(target.maxLength>0&&value.length>target.maxLength)error=`${target.maxLength}文字以内にしてください。`;
    if(error){hint.textContent=error;hint.dataset.error="true";return;}
    const original=target;
    original.value=copy.value;
    original.dispatchEvent(new Event("input",{bubbles:true}));
    original.dispatchEvent(new Event("change",{bubbles:true}));
    closeEditor();original.focus({preventScroll:true});
  }
  function drawKeys() {
    keys.replaceChildren();const numeric=target.type==="number";
    keys.classList.toggle("numeric",numeric);
    const rows=numeric?['789','456','123','.0']:
      symbols?['1234567890','.,-_@:/+=','()[]!?%#&']:
        ['qwertyuiop','asdfghjkl','zxcvbnm'];
    for(const chars of rows){
      const row=document.createElement("div");row.className="touch-key-row";
      for(const char of chars){const letter=!symbols&&upper?char.toUpperCase():char;row.append(button(letter,()=>insert(letter)));}
      if(numeric&&chars==='.0')row.append(button('⌫',erase,'','1文字削除'));
      keys.append(row);
    }
    const actions=document.createElement("div");actions.className="touch-key-row touch-actions";
    if(!numeric){
      actions.append(button(symbols?'ABC':'123',()=>{symbols=!symbols;drawKeys();},'','英字と数字記号を切替'));
      actions.append(button(upper?'小文字':'大文字',()=>{upper=!upper;drawKeys();}));
      actions.append(button('空白',()=>insert(' ')),button('⌫',erase,'','1文字削除'));
    }
    actions.append(button('全消去',()=>{field.value='';field.focus({preventScroll:true});}));
    actions.append(button('取消',closeEditor,'','入力を取り消す'),button('決定',commit,'primary','入力を決定'));
    keys.append(actions);
  }
  function openEditor(input) {
    target=input;symbols=input.id==='client-ips';upper=false;
    const names={'test-name':'試験名','repeat':'繰返し回数','remote-max':'遠隔 最大PWM','client-name':'クライアント名','client-ips':'許可IP'};
    document.getElementById('touch-title').textContent=names[input.id]||input.getAttribute('aria-label')||'入力';
    field.value=input.value;field.maxLength=input.type==='number'?12:(input.maxLength>0?input.maxLength:256);
    hint.dataset.error='false';hint.textContent=input.type==='number'?`${input.min||0}～${input.max} / 決定では運転を開始しません。`:'英数字・記号を入力できます。日本語は外付けキーボードのIMEを使用。';
    sheet.hidden=false;main.inert=true;drawKeys();field.focus({preventScroll:true});field.select();
  }
  field.addEventListener('keydown',e=>{
    if(e.isComposing)return;
    if(e.key==='Enter'){e.preventDefault();commit();}
    if(e.key==='Escape'){e.preventDefault();closeEditor();}
  });
  document.getElementById('touch-cancel').onclick=closeEditor;
})();
