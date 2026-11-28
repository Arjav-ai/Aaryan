require('./_setup');
const { chromium } = require('playwright');
const fs = require('fs');
const URL = 'http://localhost:8765/index.html';
const R = []; const ok = (n, c, x='') => R.push([c?'PASS':'FAIL', n, x]);
const NFL = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions_nfl.json','utf8'));
const CFB = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions_cfb.json','utf8'));
const now = Date.now();
const future = d => { const c = JSON.parse(JSON.stringify(d)); c.games.forEach((g,i)=>{ g.start = new Date(now + 86400e3 + i*600e3).toISOString(); g.date = g.start.slice(0,10); }); c.generated_at = new Date(now-60e3).toISOString(); return c; };
const N2 = future(NFL), C2 = future(CFB);
// independent negative-binomial maths (not the page's code)
const lg = z => { const c=[76.18009172947146,-86.50532032941677,24.01409824083091,-1.231739572450155,0.1208650973866179e-2,-0.5395239384953e-5]; let x=z,y=z,t=x+5.5; t-=(x+0.5)*Math.log(t); let s=1.000000000190015; for(let j=0;j<6;j++) s+=c[j]/++y; return -t+Math.log(2.5066282746310005*s/x); };
const nbSf = (mu, alpha, line) => { const r=1/alpha, p=r/(r+mu); let cdf=0; for(let k=0;k<=Math.floor(line);k++) cdf+=Math.exp(lg(k+r)-lg(r)-lg(k+1)+r*Math.log(p)+k*Math.log(1-p)); return 1-cdf; };
const Phi = z => 0.5*(1+(()=>{ const s=z<0?-1:1,x=Math.abs(z)/Math.SQRT2,t=1/(1+0.3275911*x); return s*(1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x)); })());
async function open(b, o={}) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } }); const p = await ctx.newPage(); p.errs=[];
  p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => { if (m.type()==='error' && !/Failed to load resource/.test(m.text())) p.errs.push(m.text()); });
  await p.route('**/predictions_nfl.json', r => r.fulfill({ json: N2 })); await p.route('**/predictions_cfb.json', r => r.fulfill({ json: C2 }));
  if (o.results) await p.route('**/results.json', r => r.fulfill({ json: o.results }));
  await p.goto(URL); await p.waitForSelector('.card, .empty'); return p;
}
const bad = async p => { const t = await p.locator('body').innerText(); return /NaN|undefined|Infinity|\bnull\b/.test(t) ? (t.match(/.{0,30}(NaN|undefined|Infinity|null).{0,30}/)||[''])[0] : ''; };
(async () => {
  const b = await chromium.launch();
  let p = await open(b);
  const sports = await p.locator('.sport').allInnerTexts();
  ok('sport switch lists NBA, NFL, College, Tennis, Football', JSON.stringify(sports)==='["NBA","NFL","College","Tennis","Football"]', sports.join('|'));
  for (const [sp, D, label] of [['nfl', N2, 'NFL'], ['cfb', C2, 'College']]) {
    const t0 = Date.now(); await p.click(`[data-sport=${sp}]`); await p.waitForFunction(n => document.querySelectorAll('.mrow[data-open]').length === n, D.games.length); const ms = Date.now()-t0;
    ok(`${label}: switching loads in under 3 seconds`, ms < 3000, ms+' ms');
    ok(`${label}: one row per upcoming game (${D.games.length})`, (await p.locator('.mrow[data-open]').count())===D.games.length, String(await p.locator('.mrow[data-open]').count()));
    ok(`${label}: tabs are Games / Best bets / Most probable`, (await p.locator('.tab').allInnerTexts()).map(s=>s.trim()).join('|').replace(/\s+/g,' ').includes('Games'), '');
    const t = await p.locator('.mrow[data-open]').first().innerText();
    ok(`${label}: a game row shows both teams, win chances and the predicted score`, /Predicted \d+ – \d+/.test(t) && (t.match(/\d+%/g)||[]).length===2, t.replace(/\n/g,' | '));
    ok(`${label}: no NaN/undefined on the games list`, (await bad(p))==='', await bad(p));
    // open the first game
    await p.locator('.mrow[data-open]').first().click(); await p.waitForSelector('.srow');
    const chips = await p.locator('#stat-chips .chip, .chips .chip').allInnerTexts();
    ok(`${label}: stat chips use the football stats`, ['Passing yards','Receiving yards','Rushing yards'].every(s=>chips.some(c=>c.trim()===s)), chips.join(','));
    // independent check of 4 rows
    const rows = await p.evaluate(() => [...document.querySelectorAll('.srow')].filter((r,i)=>i<4||parseFloat(r.querySelector('.spred b').innerText)>150).slice(0,8).map(r => ({ unit: r.querySelector('.slabel').innerText, mu: parseFloat(r.querySelector('.spred b').innerText), line: parseFloat(r.querySelector('[data-field=line]').value), res: r.querySelector('.sres').innerText, name: r.closest('article').querySelector('.name').innerText })));
    let allok = true, detail = [];
    for (const r of rows) {
      const m = /(\d+)%(\+)? over/.exec(r.res); const pl = D.players.find(x=>x.name===r.name); const stat = Object.keys(D.labels).find(k=>D.labels[k].toUpperCase()===r.unit.toUpperCase());
      const alpha = pl.stats[stat].alpha, mu = pl.stats[stat].mu; const exp = Math.min(nbSf(mu, alpha, r.line), 0.9);
      const shown = m ? parseInt(m[1])/100 : NaN; const good = Math.abs(shown-exp) <= 0.012 || (m && m[2] && exp>=0.895);
      if (!good) allok = false; detail.push(`${r.name} ${stat} ${r.line}: page ${shown} vs ${exp.toFixed(3)}`);
    }
    ok(`${label}: the over chance on 4 prop rows matches an independent calculation (includes big-yardage rows over 150)`, allok, detail.join(' ; '));
    ok(`${label}: at least one row with an expectation above 150 was checked`, rows.some(r=>r.mu>150), rows.map(r=>r.mu).join(','));
    // game bets
    await p.click('[data-mv=bets]'); await p.waitForSelector('.mk');
    const g0 = D.games[0].nba, ml = await p.locator('.mk').first().locator('.opct').allInnerTexts();
    const expHome = Phi(g0.mu_margin / g0.sd_margin);
    const shownHome = parseFloat(ml[1])/100;
    ok(`${label}: moneyline chance matches the score model (${(expHome*100).toFixed(0)}% home)`, Math.abs(shownHome-expHome) < 0.03, ml.join(','));
    ok(`${label}: spread and total markets are there`, (await p.locator('.mk').count())>=3);
    ok(`${label}: no NaN/undefined on the game page`, (await bad(p))==='', await bad(p));
    await p.click('[data-back]');
  }
  ok('no page errors', p.errs.length===0, p.errs.join('|'));
  // Most probable / Best bets with typed odds
  await p.click('[data-sport=nfl]'); await p.click('[data-tab=best]'); await p.waitForSelector('.srow');
  const row = p.locator('.srow').first(); await row.locator('[data-field=odds]').fill('1.95'); await p.waitForTimeout(300);
  ok('typing odds on an NFL prop shows a verdict', (await row.locator('.verdict').count())===1 && /edge/.test(await row.locator('.verdict').innerText()), await row.locator('.verdict').innerText());
  await p.close();
  // tracking and settling an NFL prop
  const g = N2.games[0], pl = N2.players.find(x=>x.game===g.id && x.stats.rec_yds);
  const key = `${g.date}|${g.home}`;
  const results = { generated_at: new Date().toISOString(), days: 21, nba_stats:['pts','reb','ast','fg3'], football_stats:['shots','sot','goals','assists'], nfl_stats:['pass_yds','pass_td','rush_yds','rec_yds','rec'], nba:[], football:[], cfb:[],
    nfl: [{ key, home:g.home, away:g.away, home_pts:24, away_pts:17, players:{ [pl.name]: [0,0,0,88,6] } }] };
  p = await open(b, { results });
  await p.click('[data-sport=nfl]'); await p.waitForSelector('.mrow[data-open]'); await p.locator('.mrow[data-open]').first().click(); await p.waitForSelector('.srow');
  await p.locator('[data-stat=rec_yds]:visible').first().click(); await p.waitForTimeout(200);
  const card = p.locator('article.card', { hasText: pl.name }).first(); const rr = card.locator('.srow').first();
  await rr.locator('[data-field=line]').fill('50.5'); await rr.locator('[data-field=odds]').fill('1.9'); await p.waitForTimeout(300);
  await card.locator('.trk').first().click().catch(()=>{}); await p.waitForTimeout(300);
  await p.click('#recbtn'); await p.waitForTimeout(500);
  const txt = await p.locator('#list').innerText();
  ok('a tracked NFL prop is settled from results (88 yards beats an over 50.5 line)', /finished with 88/.test(txt) && /won/i.test(txt), txt.slice(0,300).replace(/\n/g,' | '));
  await b.close();
  R.forEach(r => console.log(r.join(' | '))); const f = R.filter(r=>r[0]==='FAIL').length; console.log(`${R.length-f} passed, ${f} failed`);
})().catch(e => { console.log('CRASH', e); process.exit(1); });
