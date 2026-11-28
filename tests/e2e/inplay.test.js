require('./_setup');
const { chromium } = require('playwright');
const fs = require('fs');
const URL = 'http://localhost:8765/index.html';
const R = []; const ok = (n, c, x='') => R.push([c?'PASS':'FAIL', n, x]);
const NBA = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions.json','utf8'));
// make game 0 started one hour ago, the rest tomorrow, so the test does not depend on the real clock
const now = Date.now(), G0 = NBA.games[0];
const NBA2 = JSON.parse(JSON.stringify(NBA)); NBA2.games.forEach((g,i)=>{ g.start = new Date(now + (i===0 ? -3600e3 : 86400e3 + i*3600e3)).toISOString(); }); NBA2.generated_at = new Date(now-600e3).toISOString();
const live = (sec, extra={}) => Object.assign({ generated_at: new Date(now - sec*1000).toISOString(), games: [ { sport:'nba', league:'nba', league_name:'NBA', id: G0.id, start:new Date(now-3600e3).toISOString(), state:'in', detail:'7:06 - 2nd', clock:'7:06', period:2, home_id:'1', away_id:'2', home_code:G0.home, away_code:G0.away, home: G0.home_name||G0.home, away: G0.away_name||G0.away, home_score:25, away_score:43 } ] }, extra);
const FAKE = (dbDoc) => `window.__calls=[]; window.__snap=null; window.claude={use:async n=>{
  if(n==='mcp') return {callTool:async(s,t,a)=>{window.__calls.push([s,t,a]);return {}}};
  if(n==='user') return {id:async()=>'u1'};
  if(n==='db') return {doc:p=>({get:async()=>({exists:false,data:()=>({})}),set:async()=>{},onSnapshot:(f)=>{ if(p==='live/current'){window.__snap=f; ${dbDoc?`f({exists:true,data:()=>(${JSON.stringify(dbDoc)})});`:''}} return ()=>{}; }})};
  return null; }};`;
async function open(b, o={}) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } }); const p = await ctx.newPage(); p.errs=[];
  p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => { if (m.type()==='error'&&!/live\.json|404|Failed to load resource/.test(m.text())) p.errs.push(m.text()); });
  await p.addInitScript(FAKE(o.db));
  await p.route('**/predictions.json', r => r.fulfill({ json: NBA2 }));
  if (o.live==='none') await p.route('**/live.json*', r => r.fulfill({status:404,body:''})); else await p.route('**/live.json*', r => r.fulfill({ json: o.live }));
  await p.goto(URL); await p.waitForSelector('.card'); await p.click('[data-tab=matches]'); await p.waitForTimeout(500); return p;
}
(async () => {
  const b = await chromium.launch();
  let p = await open(b, { live: live(120) });
  let txt = await p.locator('#list').innerText();
  ok('a game in play shows at the top of Games with its score', /IN PLAY NOW|In play now/i.test(txt) && /43/.test(txt) && /25/.test(txt) && /7:06 - 2nd/.test(txt), txt.slice(0,160));
  ok('it says how old the scores are', /scores 2 min ago/.test(txt));
  ok('only the started game is in the in-play group; the others are normal rows', (await p.locator('[data-live]').count())===1 && (await p.locator('[data-open]').count())===NBA2.games.length-1);
  await p.click('[data-live]'); await p.waitForTimeout(300);
  ok('tapping it opens a live card with the big score', /43\s*–\s*25/.test(await p.locator('.bigscore').innerText()) && /Bets and props close/.test(await p.locator('#list').innerText()));
  ok('the live card shows what the model expected before the start', /Before the start the model expected/.test(await p.locator('#list').innerText()));
  await p.click('[data-back]'); ok('back returns to the list', await p.locator('[data-live]').count()===1);
  ok('no page errors', p.errs.length===0, p.errs.join('|'));
  // newer scores pushed through the live database replace older ones; older ones are ignored
  await p.close();
  p = await open(b, { live: live(120) });
  const gid = G0.id;
  await p.evaluate(g=>window.__snap({exists:true,data:()=>({generated_at:new Date().toISOString(),tracking_until:new Date(Date.now()+3600e3).toISOString(),games:[{sport:'nba',league_name:'NBA',id:g,start:new Date().toISOString(),state:'in',detail:'3:00 - 3rd',home_code:'X',away_code:'Y',home:'Home',away:'Away',home_score:70,away_score:80}]})}), gid);
  await p.waitForTimeout(300); txt = await p.locator('#list').innerText();
  ok('a newer pushed update shows at once (80 / 70, 3rd quarter)', /80/.test(txt) && /70/.test(txt) && /3:00 - 3rd/.test(txt), txt.slice(0,200));
  ok('it says live tracking is on and hides the start button', /tracking on/.test(txt) && (await p.locator('[data-lv=track]').count())===0);
  await p.evaluate(g=>window.__snap({exists:true,data:()=>({generated_at:new Date(Date.now()-3600e3).toISOString(),games:[{sport:'nba',league_name:'NBA',id:g,start:new Date().toISOString(),state:'in',detail:'OLD',home_code:'X',away_code:'Y',home:'Home',away:'Away',home_score:1,away_score:2}]})}), gid);
  await p.waitForTimeout(300); ok('an older update is ignored', !/OLD/.test(await p.locator('#list').innerText()));
  await p.click('#livebtn'); await p.waitForTimeout(300);
  ok('the Live screen shows tracking on until a time', /Live tracking is on/.test(await p.locator('#list').innerText()));
  await p.close();
  // start tracking
  p = await open(b, { live: live(1800) });
  ok('with old scores the Keep live and Update once buttons are offered', (await p.locator('[data-lv=track]').count())>=1 && (await p.locator('[data-lv=update]').count())>=1);
  await p.locator('[data-lv=track]').first().click(); await p.waitForTimeout(500);
  const calls = await p.evaluate(()=>window.__calls);
  ok('Keep scores live fires the tracking task, once', calls.length===1 && calls[0][1]==='fire_trigger' && calls[0][2].trigger_id==='trig_0158WZiXw3yghvKLSPm1eBCA', JSON.stringify(calls));
  ok('and the button is then disabled (no double start)', (await p.locator('[data-lv=track]').count())===0 || await p.locator('[data-lv=track]').first().isDisabled());
  await p.close();
  // nothing loaded at all
  p = await open(b, { live: 'none' });
  txt = await p.locator('#list').innerText();
  ok('without any score data the started game still appears, saying the score is not loaded', /Score not loaded yet/.test(txt) && (await p.locator('[data-live]').count())===1, txt.slice(0,120));
  await p.click('[data-live]'); await p.waitForTimeout(200);
  ok('and its card does not crash', /Bets and props close/.test(await p.locator('#list').innerText()) && p.errs.length===0, p.errs.join('|'));
  await b.close();
  R.forEach(r => console.log(r.join(' | '))); const f = R.filter(r=>r[0]==='FAIL').length; console.log(`${R.length-f} passed, ${f} failed`);
})().catch(e => { console.log('CRASH', e); process.exit(1); });
