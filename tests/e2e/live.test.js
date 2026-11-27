require('./_setup');
const { chromium } = require('playwright');
const fs = require('fs');
const URL = 'http://localhost:8765/index.html';
const R = []; const ok = (n, c, x='') => R.push([c?'PASS':'FAIL', n, x]);
const now = Date.now(), iso = ms => new Date(now+ms).toISOString().slice(0,16)+'Z';
const g = (o) => Object.assign({sport:'football',league:'eng.1',league_name:'Premier League',id:'1',start:iso(-3600e3),state:'in',detail:"34'",clock:"34'",period:1,home_id:'360',away_id:'359',home_code:'',away_code:'',home:'Man United',away:'Arsenal',home_score:1,away_score:0}, o);
const LIVE = { generated_at: new Date(now-120e3).toISOString(), games: [
  g({}), g({id:'2',sport:'nba',league:'nba',league_name:'NBA',state:'in',detail:'Q3 5:12',clock:'5:12',home:'Boston Celtics',away:'Miami Heat',home_code:'BOS',away_code:'MIA',home_score:78,away_score:70}),
  g({id:'3',state:'post',detail:'FT',home:'Chelsea',away:'Everton',home_score:2,away_score:2,start:iso(-5*3600e3)}),
  g({id:'4',state:'post',detail:'FT',home:'Leeds',away:'Fulham',home_score:0,away_score:3,start:iso(-6*3600e3)}),
  g({id:'5',state:'pre',detail:'',home:'Spurs',away:'Villa',home_score:0,away_score:0,start:iso(5*3600e3)}) ]};
const FAKE = `window.__calls=[]; window.claude={use:async n=>{ if(n==='mcp') return {callTool:async(s,t,a)=>{window.__calls.push([s,t,a]);return {}}}; return null; }};`;
async function open(b, live, claude=true) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } }); const p = await ctx.newPage(); p.errs=[];
  p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => { if (m.type()==='error'&&!/live\.json|404|Failed to load resource/.test(m.text())) p.errs.push(m.text()); });
  if (claude) await p.addInitScript(FAKE);
  if (live==='none') await p.route('**/live.json*', r => r.fulfill({status:404,body:''}));
  else if (live) await p.route('**/live.json*', r => r.fulfill({ json: live }));
  await p.goto(URL); await p.waitForSelector('.card'); await p.waitForTimeout(500); return p;
}
(async () => {
  const b = await chromium.launch();
  let p = await open(b, LIVE);
  ok('Live button visible with count of games in play (2)', (await p.locator('#livebtn').innerText()).replace(/\s/g,'')==='Live2', await p.locator('#livebtn').innerText());
  await p.click('#livebtn'); await p.waitForTimeout(300);
  const txt = await p.locator('#list').innerText();
  ok('In play section lists both live games', /IN PLAY NOW \(2\)/i.test(txt) && /Man United/.test(txt) && /Boston Celtics/.test(txt));
  ok('Shows the score and clock', /78/.test(txt) && /Q3 5:12/.test(txt) && /34'/.test(txt));
  ok('Finished and coming up sections', /FINISHED \(2\)/i.test(txt) && /COMING UP \(1\)/i.test(txt) && /Chelsea/.test(txt) && /Spurs/.test(txt));
  ok('Shows how old the scores are (2 min)', /Scores as of/.test(txt) && /2 min ago/.test(txt), txt.slice(0,160));
  ok('No section tab is highlighted while Live is open', (await p.locator('.tab[aria-selected=true]').count())===0);
  ok('Live button pressed state', (await p.locator('#livebtn').getAttribute('aria-pressed'))==='true');
  ok('No page errors', p.errs.length===0, p.errs.join('|'));
  // update button fires the live trigger, not the daily refresh
  await p.click('[data-lv=update]'); await p.waitForTimeout(400);
  const calls = await p.evaluate(()=>window.__calls);
  ok('Update scores calls fire_trigger once', calls.length===1 && calls[0][1]==='fire_trigger', JSON.stringify(calls));
  ok('...with the live trigger id, not the daily one', calls[0] && calls[0][2].trigger_id==='trig_016A94reGVvY7Fo9xme6h1CL' && calls[0][2].trigger_id!=='trig_0167Fv1vujkW4gn7qbYy18dQ');
  ok('Button then disabled with a "requested" message', await p.locator('[data-lv=update]').isDisabled() && /requested at/.test(await p.locator('#list').innerText()));
  await p.click('[data-lv=update]', {force:true}).catch(()=>{}); await p.waitForTimeout(200);
  ok('A second tap does not fire again', (await p.evaluate(()=>window.__calls)).length===1);
  await p.click('#livebtn'); await p.waitForTimeout(200);
  ok('Closing Live returns to the normal page', await p.locator('#tabs').isVisible() && !/IN PLAY NOW/i.test(await p.locator('#list').innerText()));
  await p.context().close();
  // no live.json at all
  p = await open(b, 'none');
  ok('No live file: no badge, no crash', (await p.locator('#livebtn').innerText()).trim()==='Live' && p.errs.length===0, p.errs.join('|'));
  await p.click('#livebtn'); await p.waitForTimeout(300);
  ok('No live file: friendly message', /No scores yet/.test(await p.locator('#list').innerText()));
  await p.context().close();
  // no connector (opened outside claude.ai): shows scores, update disabled
  p = await open(b, LIVE, false); await p.click('#livebtn'); await p.waitForTimeout(300);
  ok('Without the connector scores still show and Update is disabled', /Man United/.test(await p.locator('#list').innerText()) && await p.locator('[data-lv=update]').isDisabled());
  await p.context().close();
  // quiet day
  p = await open(b, {generated_at:new Date().toISOString(),games:[]}); await p.click('#livebtn'); await p.waitForTimeout(300);
  ok('Empty day: clear message, no badge', /No games right now/.test(await p.locator('#list').innerText()) && (await p.locator('#livebtn').innerText()).trim()==='Live');
  await b.close();
  R.forEach(r => console.log(r.join(' | '))); const f = R.filter(r=>r[0]==='FAIL').length; console.log(`${R.length-f} passed, ${f} failed`);
})().catch(e => { console.log('CRASH', e); process.exit(1); });
