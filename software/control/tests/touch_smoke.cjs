// Isolated browser. All application data are simulated; no Pico connection.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');

(async()=>{
  const root=path.resolve(__dirname,'..'),out=path.join(root,'test-results/touch');
  fs.mkdirSync(out,{recursive:true});
  const data=fs.mkdtempSync(path.join(root,'.runtime','touch-'));
  const python=process.env.WT_TEST_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
  const server=spawn(python,['-m','windtunnel','--port','8767','--data-dir',data],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let logs='',browser;server.stdout.on('data',d=>logs+=d);server.stderr.on('data',d=>logs+=d);
  try {
    for(let i=0;i<100;i++){
      try{if((await fetch('http://127.0.0.1:8767/openapi.json')).ok)break;}catch{}
      if(server.exitCode!=null)throw Error(logs);await new Promise(r=>setTimeout(r,100));
    }
    browser=await chromium.launch({headless:true,...(process.platform==='win32'?{channel:'chrome'}:{})});
    const context=await browser.newContext({viewport:{width:800,height:480},hasTouch:true});
    const page=await context.newPage(),errors=[],mutations=[];page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(r.method()==='POST')mutations.push(new URL(r.url()).pathname);});
    const url=fs.readFileSync(path.join(data,'local-access.html'),'utf8').match(/href="([^"]+)"/)[1];
    await page.goto(url);await page.locator('#stop:enabled').waitFor();
    const checks=[];
    const scroll=()=>page.locator('main').evaluate(e=>e.scrollTop);
    async function drag(x,y,dx,dy){await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+dx,y+dy,{steps:16});await page.mouse.up();}
    async function stopVisible(){const b=await page.locator('#stop').boundingBox();assert(b.y>=0&&b.y+b.height<=60&&b.height>=48);assert(await page.locator('#stop').isEnabled());}
    async function inputTap(selector){await page.locator(selector).click();await page.locator('#touch-editor:not([hidden])').waitFor();await stopVisible();}
    const key=t=>page.locator('#touch-keys').getByRole('button',{name:t,exact:true});
    await page.locator('[data-page="settings"]').click();
    await drag(740,360,0,-220);assert(await scroll()>100);
    await drag(740,160,0,200);assert(await scroll()<100);
    checks.push('mouse-emulated finger scrolls settings up and down');
    await page.waitForTimeout(450);
    await page.locator('#remote-on').scrollIntoViewIfNeeded();
    let b=await page.locator('#remote-on').boundingBox();
    await drag(b.x+b.width/2,b.y+b.height/2,0,-100);
    assert.equal((await page.evaluate(async()=>(await fetch('/api/v1/status')).json())).remote.enabled,false);
    await page.locator('#stop').click();
    checks.push('drag from remote ON does not activate it; immediate stop remains usable');
    await page.locator('#message-close').click();
    await page.locator('[data-page="test"]').click();await page.locator('#preset').click();
    assert.equal(await page.locator('#steps tr').count(),5);
    b=await page.locator('#steps tr:nth-child(2) button').last().boundingBox();
    await drag(b.x+b.width/2,b.y+b.height/2,0,-120);
    assert.equal(await page.locator('#steps tr').count(),5);assert(await scroll()>50);
    checks.push('table scroll has no nested vertical trap and does not delete a row');
    await page.waitForTimeout(450);
    await inputTap('#steps tr:first-child input[aria-label="PWM"]');
    const original=await page.locator('#steps tr:first-child input[aria-label="PWM"]').inputValue();
    await key('6').click();await key('0').click();
    assert.equal(await page.locator('#touch-value').inputValue(),'60');
    assert.equal(await page.locator('#steps tr:first-child input[aria-label="PWM"]').inputValue(),original);
    await page.screenshot({path:path.join(out,'numeric-keyboard.png')});
    await key('入力を決定').click();
    assert.equal(await page.locator('#steps tr:first-child input[aria-label="PWM"]').inputValue(),'60');
    assert(await page.locator('#touch-editor').isHidden());
    checks.push('numeric keypad buffers edits and commits through existing validation flow');
    await inputTap('#steps tr:first-child input[aria-label="PWM"]');
    await page.locator('#touch-value').fill('101');await key('入力を決定').click();
    assert(await page.locator('#touch-editor').isVisible());assert.equal(await page.locator('#touch-hint').getAttribute('data-error'),'true');
    await page.locator('#touch-value').fill('10');await key('入力を決定').click();assert((await page.locator('#touch-hint').innerText()).includes('20'));
    await page.locator('#stop').click();
    assert(await page.locator('#touch-editor').isHidden());assert.equal(await page.locator('#steps tr:first-child input[aria-label="PWM"]').inputValue(),'60');
    checks.push('range and unverified low PWM rejected; stop discards pending edits');
    await page.locator('#message-close').click();
    await inputTap('#test-name');
    for(const c of 'test')await key(c).click();
    await key('英字と数字記号を切替').click();await key('1').click();
    await page.screenshot({path:path.join(out,'text-keyboard.png')});
    await key('入力を決定').click();assert.equal(await page.locator('#test-name').inputValue(),'test1');
    await page.locator('#review').click();await page.locator('#confirmation:not([hidden])').waitFor();
    b=await page.locator('#start-run').boundingBox();
    await drag(b.x+b.width/2,b.y+b.height/2,0,-90);
    await page.waitForTimeout(450);assert(!mutations.includes('/api/v1/runs'));
    await page.locator('#dismiss').click();checks.push('drag beginning on start button never submits a run');
    await inputTap('#test-name');await page.locator('#touch-value').fill('discard');
    await page.locator('[data-page="settings"]').click();assert(await page.locator('#touch-editor').isHidden());
    assert.equal(await page.locator('#test-name').inputValue(),'test1');
    checks.push('text/symbol keyboard and navigation cancellation');
    await page.locator('#touch-keyboard-enabled').uncheck();
    await page.locator('[data-page="test"]').click();await page.locator('#test-name').click();
    assert(await page.locator('#touch-editor').isHidden());
    await page.reload();await page.locator('#stop:enabled').waitFor();
    assert.equal(await page.locator('#touch-keyboard-enabled').isChecked(),false);
    await page.locator('[data-page="settings"]').click();await page.locator('#touch-keyboard-enabled').check();
    checks.push('optional screen keyboard setting persists after reload');
    // Browser-native touch events are not intercepted by the mouse fallback.
    await page.locator('main').evaluate(e=>e.scrollTop=0);
    const cdp=await context.newCDPSession(page);
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:740,y:360}]});
    for(let i=1;i<=12;i++){
      await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:740,y:360-i*17}]});
      await page.waitForTimeout(16);
    }
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    await page.waitForTimeout(500);assert(await scroll()>100);
    await stopVisible();checks.push('native touch swipe works and stop stays fixed');
    assert(!mutations.includes('/api/v1/runs'),'Editing/scrolling must never start a run');
    assert(!mutations.includes('/api/v1/control/remote-permit'),'Dragging must never enable remote control');
    const s=await page.evaluate(async()=>(await fetch('/api/v1/status')).json());
    assert.equal(s.pwm_requested_percent,0);assert.equal(s.remote.enabled,false);assert.equal(s.active_run,null);
    assert.equal(errors.length,0,errors.join('\n'));checks.push('no start or permission request; no JavaScript errors');
    fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({passed:true,checks,page_errors:errors,final:s},null,2));
    console.log('TOUCH PASS',checks.length,'checks, mouse-emulated and native touch, fan commands unchanged');
  }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
