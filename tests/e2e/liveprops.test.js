require('./_setup');
const { chromium } = require('playwright');
const fs = require('fs');
const URL = 'http://localhost:8765/index.html';
const R = []; const ok = (n, c, x='') => R.push([c?'PASS':'FAIL', n, x]);
const NBA = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions.json','utf8'));
const now = Date.now(); const G0 = NBA.games[0];
const N2 = JSON.parse(JSON.stringify(NBA)); N2.games.forEach((g,i)=>{ g.start = new Date(now + (i===0 ? -3600e3 : 86400e3 + i*3600e3)).toISOString(); }); N2.generated_at = new Date(now-600e3).toISOString();
const gp = N2.players.filter(p=>p.game===G0.id);
const norm = s => s.normalize('NFKD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/[^a-z0-9 ]/g,'').trim().replace(/\s+(jr|sr|ii|iii|iv)$/,'');
// box score so far: first player has 14 pts, 6 reb (ahead of pace), second has 0 pts; f = 0.5 (halftime)
const box = {}; gp.forEach((p,i)=>{ box[norm(p.name)] = { pts: i===0?14:(i===1?0:Math.round(p.stats.pts.mu/2)), reb: i===0?6:2, ast: 2, fg3: 1, min: 18 }; });
const LIVE = { generated_at: new Date(now-60e3).toISOString(), games: [ { sport:'nba', league:'nba', league_name:'NBA', id:G0.id, start:new Date(now-3600e3).toISOString(), state:'in', detail:'Q3 12:00', clock:'12:00', period:3, f:0.5, home_id:'1', away_id:'2', home_code:G0.home, away_code:G0.away, home:G0.home_name, away:G0.away_name, home_score:55, away_score:50, players: box } ] };
// independent negative-binomial maths
const lg = z => { const c=[76.18009172947146,-86.50532032941677,24.01409824083091,-1.231739572450155,0.1208650973866179e-2,-0.5395239384953e-5]; let x=z,y=z,t=x+5.5; t-=(x+0.5)*Math.log(t); let s=1.000000000190015; for(let j=0;j<6;j++) s+=c[j]/++y; return -t+Math.log(2.5066282746310005*s/x); };
const nbSf = (size, mean, k) => { const p = size/(size+mean); let cdf=0; for(let i=0;i<=k;i++) cdf+=Math.exp(lg(i+size)-lg(size)-lg(i+1)+size*Math.log(p)+i*Math.log(1-p)); return 1-cdf; };
// Gamma-Poisson posterior predictive, derived from first principles: lambda ~ Gamma(shape r, rate r/mu) per unit of expected count
const W = {pts:0.25,reb:0.9,ast:0.9,fg3:1};
const restOver = (mu, alpha, f, cur, line, stat) => { const r=1/alpha, w=W[stat], size=r+w*cur, mean=mu*(1-f)*size/(r+w*mu*f); const need=Math.floor(line-cur); return need<0 ? 1 : nbSf(size, mean, need); };
async function open(b, live) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } }); const p = await ctx.newPage(); p.errs=[];
  p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => { if (m.type()==='error' && !/Failed to load resource/.test(m.text())) p.errs.push(m.text()); });
  await p.addInitScript(`window.claude={use:async n=>n==='mcp'?{callTool:async()=>({})}:null}`);
  await p.route('**/predictions.json', r => r.fulfill({ json: N2 }));
  await p.route('**/live.json*', r => r.fulfill({ json: live }));
  await p.goto(URL); await p.waitForSelector('.card, .mrow'); await p.click('[data-tab=matches]'); await p.waitForSelector('[data-live]'); return p;
}
(async () => {
  const b = await chromium.launch();
  let p = await open(b, LIVE);
  await p.click('[data-live]'); await p.waitForSelector('.lprow');
  const t = await p.locator('#list').innerText();
  ok('the live card has a Live props section', /Live props/.test(t) && (await p.locator('.lprow').count())>0, String(await p.locator('.lprow').count()));
  ok('only 12 rows at first, with a button to show all', (await p.locator('.lprow').count())===12 && (await p.locator('[data-lpall]').count())===1);
  // independent check on the first rows: chance of over at the default live line
  const rows = await p.evaluate(() => [...document.querySelectorAll('.lprow')].slice(0,12).map(r => ({ name: r.querySelector('.name').innerText, meta: r.querySelector('.meta').innerText, line: parseFloat(r.querySelector('[data-field=lpline]').value), res: r.querySelector('.lpres').innerText })));
  let allok = true, det = [];
  for (const r of rows.slice(0,8)) {
    const pl = gp.find(x=>x.name===r.name); const unit = /^(\w[\w ]*) ·/.exec(r.meta)[1]; const stat = Object.keys(N2.labels).find(k=>N2.labels[k]===unit);
    const cur = box[norm(pl.name)][stat]; const m = /Over [\d.]+: (\d+)%(\+)?/.exec(r.res);
    const exp = Math.min(restOver(pl.stats[stat].mu, pl.stats[stat].alpha, 0.5, cur, r.line, stat), 0.9); const shown = parseInt(m[1])/100;
    const good = Math.abs(shown-exp) <= 0.012 || (m[2] && exp>=0.895); if (!good) allok = false; det.push(`${pl.name} ${stat} cur ${cur} line ${r.line}: page ${shown} vs ${exp.toFixed(3)}`);
  }
  ok('chance of the final total going over matches an independent Gamma-Poisson calculation (8 rows)', allok, det.join(' ; '));
  // a player who is ahead of pace has a higher projected final than the pre-game expectation
  const p0 = gp[0]; const meta0 = await p.locator('.lprow', { hasText: p0.name }).filter({ hasText: 'Points' }).first().locator('.meta').innerText();
  const pace = parseFloat(/on pace for ([\d.]+)/.exec(meta0)[1]);
  ok(`${p0.name}: 14 points at halftime puts him on pace above his pre-game ${p0.stats.pts.mu}`, pace > p0.stats.pts.mu, meta0);
  const p1 = gp[1]; const meta1 = await p.locator('.lprow', { hasText: p1.name }).filter({ hasText: 'Points' }).first().locator('.meta').innerText();
  const pace1 = parseFloat(/on pace for ([\d.]+)/.exec(meta1)[1]);
  ok(`${p1.name}: 0 points at halftime puts him on pace below his pre-game ${p1.stats.pts.mu} but not near zero (lumpy scoring is weak evidence)`, pace1 < p1.stats.pts.mu && pace1 > p1.stats.pts.mu*0.15, meta1);
  // a line already passed: over is certain
  const row0 = p.locator('.lprow', { hasText: p0.name }).filter({ hasText: 'Points' }).first();
  await row0.locator('[data-field=lpline]').fill('9.5'); await p.waitForTimeout(250);
  ok('a line the player has already passed gives over 90%+ (capped), under under 1%', /Over 9\.5: 90%\+/.test(await row0.locator('.lpres').innerText()) && /Under: <1%/.test(await row0.locator('.lpres').innerText()), await row0.locator('.lpres').innerText());
  // odds -> verdict
  await row0.locator('[data-field=lpline]').fill('18.5'); await row0.locator('[data-field=lpo]').fill('1.95'); await p.waitForTimeout(250);
  ok('typing a live line and odds shows a verdict with an edge', /edge/.test(await row0.locator('.lpres .verdict').innerText()), await row0.locator('.lpres .verdict').innerText());
  // stat filter and show all
  await p.click('[data-lpstat=reb]'); await p.waitForTimeout(200);
  ok('stat chips filter the rows', (await p.locator('.lprow .meta').allInnerTexts()).every(x=>/Rebounds/.test(x)));
  await p.click('[data-lpstat=all]'); await p.click('[data-lpall]'); await p.waitForTimeout(200);
  ok('Show all lists every row (' + gp.length*4 + ' expected at most)', (await p.locator('.lprow').count()) > 12);
  ok('no NaN/undefined and no page errors', !/NaN|undefined|Infinity/.test(await p.locator('#list').innerText()) && p.errs.length===0, p.errs.join('|'));
  await p.close();
  // a game with no box score yet
  const L2 = JSON.parse(JSON.stringify(LIVE)); delete L2.games[0].players;
  p = await open(b, L2); await p.click('[data-live]'); await p.waitForTimeout(300);
  ok('without a box score the card says live props are not available yet (no crash)', (await p.locator('.lprow').count())===0 && p.errs.length===0, p.errs.join('|'));
  await b.close();
  R.forEach(r => console.log(r.join(' | '))); const f = R.filter(r=>r[0]==='FAIL').length; console.log(`${R.length-f} passed, ${f} failed`);
})().catch(e => { console.log('CRASH', e); process.exit(1); });
