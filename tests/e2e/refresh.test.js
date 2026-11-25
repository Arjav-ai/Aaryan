const { chromium } = require('playwright'); const fs = require('fs');
const URL = 'http://localhost:8765/index.html'; const R = []; const ok=(n,c,x='')=>R.push([c?'PASS':'FAIL',n,x]);
const FAKE = mode => `window.__calls=[]; window.__mode=${JSON.stringify(mode)};
 window.claude={use:async n=>{ if(n!=='mcp') return null; if(window.__mode==='null') return null; if(window.__mode==='reject') throw new Error('x');
   return {callTool: async (s,t,i)=>{ window.__calls.push([s,t,i]); await new Promise(r=>setTimeout(r,150)); const m=window.__fail; if(m) throw {code:m,message:'x'}; return {content:[],payload:{}}; }}; }};`;
async function page(b, {mode='ok', fail=null, w=390, fresh=false, store=null}={}) {
  const ctx = await b.newContext({ viewport:{width:w,height:844} }); const p = await ctx.newPage(); p.errs=[];
  p.on('pageerror',e=>p.errs.push(String(e))); p.on('console',m=>{ if(m.type()==='error') p.errs.push(m.text()); });
  if (mode!=='none') await p.addInitScript(FAKE(mode)+(fail?`window.__fail=${JSON.stringify(fail)};`:''));
  if (store!==null) await p.addInitScript(`try{localStorage.setItem('propfinder-refresh',${JSON.stringify(String(store))})}catch(e){}`);
  if (fresh) { const d=JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions.json','utf8')); d.generated_at=new Date(Date.now()-5*60000).toISOString(); await p.route('**/predictions.json',r=>r.fulfill({json:d})); }
  await p.goto(URL); await p.waitForSelector('#list article.card'); await p.waitForTimeout(250); return p;
}
const calls = p => p.evaluate(()=>window.__calls);
(async()=>{
  const b = await chromium.launch();
  // 1. no Claude connector available at all
  let p = await page(b,{mode:'none'}); ok('hidden when the page has no Claude runtime', !(await p.locator('#rbtn').isVisible()) && p.errs.length===0, JSON.stringify(p.errs));
  p = await page(b,{mode:'null'}); ok('hidden when the connector capability is unavailable', !(await p.locator('#rbtn').isVisible()));
  p = await page(b,{mode:'reject'}); ok('hidden (no errors) when the capability check fails', !(await p.locator('#rbtn').isVisible()) && p.errs.length===0, JSON.stringify(p.errs));
  // 2. normal flow
  p = await page(b); ok('button visible with the connector', await p.locator('#rbtn').isVisible() && (await p.locator('#rbtn').innerText())==='Refresh now');
  await p.click('#rbtn'); ok('tapping asks first (nothing started yet)', await p.locator('#rpanel').isVisible() && /Start a refresh now/.test(await p.locator('#rpanel').innerText()) && (await calls(p)).length===0);
  ok('confirm explains time and usage', /5 minutes/.test(await p.locator('#rpanel').innerText()) && /usage/.test(await p.locator('#rpanel').innerText()));
  await p.click('[data-r=cancel]'); ok('Cancel closes it, still nothing started', !(await p.locator('#rpanel').isVisible()) && (await calls(p)).length===0);
  await p.click('#rbtn'); await p.dblclick('[data-r=start]'); await p.waitForTimeout(500);
  const c = await calls(p);
  ok('Start calls the connector exactly once (even on a double-tap)', c.length===1, String(c.length));
  ok('...with the right connector, tool and schedule id', c[0][0]==='Claude Code Remote' && c[0][1]==='fire_trigger' && c[0][2].trigger_id==='trig_0167Fv1vujkW4gn7qbYy18dQ', JSON.stringify(c[0]));
  ok('after success the button shows Refresh started and is disabled', (await p.locator('#rbtn').innerText())==='Refresh started' && await p.locator('#rbtn').isDisabled());
  ok('success message says it updates by itself', /updates by itself/.test(await p.locator('#rpanel').innerText()) && /good/.test(await p.locator('#rpanel').getAttribute('class')), await p.locator('#rpanel').innerText());
  await p.screenshot({path:process.argv[2]+'/rf_ok.png'});
  await p.reload(); await p.waitForSelector('#list article.card'); await p.waitForTimeout(300);
  ok('after a reload it still remembers (no second run possible)', await p.locator('#rbtn').isDisabled() && (await calls(p)).length===0 && /was started at/.test(await p.locator('#rpanel').innerText()));
  await p.click('#rbtn',{force:true}).catch(()=>{}); ok('tapping the disabled button does nothing', (await calls(p)).length===0);
  p = await page(b,{store:Date.now()-11*60000}); ok('enabled again after 10 minutes', !(await p.locator('#rbtn').isDisabled()) && (await p.locator('#rbtn').innerText())==='Refresh now');
  // 3. fresh data hint
  p = await page(b,{fresh:true}); await p.click('#rbtn'); ok('says so when the data is already fresh', /only \d+ minutes old/.test(await p.locator('#rpanel').innerText()), (await p.locator('#rpanel').innerText()).replace(/\n/g,' '));
  // 4. every failure type
  const cases = [['approval_required',/permission/],['consent_required',/permission/],['not_in_manifest',/not allowed/],['server_not_connected',/connector is not available/],['needs_reauth',/Reconnect/],['blocked_by_policy',/organization/],['tool_error',/problem starting/],['server_unavailable',/Could not confirm/],['upstream_error',/Could not confirm/],['some_new_code',/Could not confirm/]];
  for (const [code,re] of cases) {
    p = await page(b,{fail:code}); await p.click('#rbtn'); await p.click('[data-r=start]'); await p.waitForTimeout(500);
    const t = await p.locator('#rpanel').innerText(); const bad = /bad/.test(await p.locator('#rpanel').getAttribute('class'));
    ok(`failure "${code}": clear message, button usable again`, re.test(t) && bad && !(await p.locator('#rbtn').isDisabled()) && (await p.evaluate(()=>localStorage.getItem('propfinder-refresh')))===null, t.slice(0,70));
  }
  // 5. the rest of the page still works with the button there
  p = await page(b); await p.click('button[data-sport=football]'); await p.waitForTimeout(900); await p.click('button[data-tab=matches]');
  ok('sport switching and tabs unaffected', (await p.locator('article.card').count())>0 && await p.locator('#rbtn').isVisible() && p.errs.length===0, JSON.stringify(p.errs));
  for (const w of [360,390,768,1280]) { const q = await page(b,{w}); await q.click('#rbtn'); const o = await q.evaluate(()=>document.documentElement.scrollWidth>innerWidth); ok(`no sideways scroll at ${w}px with the panel open`, !o); if(w===360) await q.screenshot({path:process.argv[2]+'/rf_open.png'}); await q.context().close(); }
  for (const [s,n,e] of R) console.log(s,'|',n,e?('| '+e):'');
  console.log('\n'+R.filter(r=>r[0]==='PASS').length+' passed, '+R.filter(r=>r[0]==='FAIL').length+' failed');
  await b.close();
})();
