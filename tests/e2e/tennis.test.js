require('./_setup');
const { chromium } = require('playwright');
const fs = require('fs');
const URL = 'http://localhost:8765/index.html';
const R = []; const ok = (n, c, x='') => R.push([c?'PASS':'FAIL', n, x]);
const TN = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions_tennis.json','utf8'));
const now = Date.now();
const T2 = JSON.parse(JSON.stringify(TN)); T2.games.forEach((g,i)=>{ g.start = new Date(now + 86400e3 + i*3600e3).toISOString(); g.date = g.start.slice(0,10); }); T2.generated_at = new Date(now-60e3).toISOString();
const Phi = z => 0.5*(1+(()=>{ const s=z<0?-1:1,x=Math.abs(z)/Math.SQRT2,t=1/(1+0.3275911*x); return s*(1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x)); })());
const bad = async p => { const t = await p.locator('body').innerText(); return /NaN|undefined|Infinity|\bnull\b/.test(t) ? (t.match(/.{0,30}(NaN|undefined|Infinity|null).{0,30}/)||[''])[0] : ''; };
async function open(b, results) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } }); const p = await ctx.newPage(); p.errs=[]; p.crestReqs=[];
  p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => { if (m.type()==='error' && !/Failed to load resource/.test(m.text())) p.errs.push(m.text()); });
  p.on('request', r => { if (/crests\/tennis/.test(r.url())) p.crestReqs.push(r.url()); });
  await p.route('**/predictions_tennis.json', r => r.fulfill({ json: T2 }));
  if (results) await p.route('**/results.json', r => r.fulfill({ json: results }));
  await p.goto(URL); await p.waitForSelector('.card, .empty'); return p;
}
(async () => {
  const b = await chromium.launch();
  let p = await open(b);
  const sports = await p.locator('.sport').allInnerTexts();
  ok('sport switch lists NBA, NFL, College, Tennis, Football', JSON.stringify(sports)==='["NBA","NFL","College","Tennis","Football"]', sports.join('|'));
  await p.click('[data-sport=tennis]'); await p.waitForSelector('.mrow[data-open]');
  ok('tennis has two tabs: Matches and Best bets', (await p.locator('.tab').count())===2, (await p.locator('.tab').allInnerTexts()).join('|'));
  ok('one row per upcoming match', (await p.locator('.mrow[data-open]').count())===T2.games.length);
  const row = await p.locator('.mrow[data-open]').first().innerText();
  const g = T2.games[0];
  ok('row shows both players, win chances, expected games and best-of', row.includes(g.home) && row.includes(g.away) && (row.match(/\d+%/g)||[]).length===2 && /About \d+ games/.test(row) && /Best of 3/.test(row), row.replace(/\n/g,' | '));
  const pcts = (row.match(/(\d+)%/g)||[]).map(x=>parseInt(x));
  ok('the two win chances add up to 100% (rounding allowed)', Math.abs(pcts[0]+pcts[1]-100)<=1, pcts.join('+'));
  ok('home chance equals the Elo chance', Math.abs(pcts[0]/100 - g.p_home) < 0.011, `${pcts[0]} vs ${g.p_home}`);
  ok('no crest image requests for tennis (initials badges only)', p.crestReqs.length===0 && (await p.locator('.mrow .crest.ph').count())===2*T2.games.length, p.crestReqs.join(','));
  ok('no NaN/undefined', (await bad(p))==='', await bad(p));
  await p.locator('.mrow[data-open]').first().click(); await p.waitForSelector('.mk');
  const titles = await p.locator('.mk-title').allInnerTexts();
  ok('detail shows Match winner, Games handicap, Total games (no player props toggle)', titles.join('|').toLowerCase()==='match winner|games handicap|total games' && (await p.locator('[data-mv]').count())===0, titles.join('|'));
  const ml = await p.locator('.mk').first().locator('.opct').allInnerTexts();
  ok('match winner on the detail page matches the model', Math.abs(parseInt(ml[0])/100 - g.p_home) < 0.011, ml.join(','));
  const labs = await p.locator('.mk').nth(2).locator('.olab').allInnerTexts();
  ok('total games options say "games"', labs.every(l=>/games$/.test(l)), labs.join('|'));
  // independent check of the default total games line
  const line = parseFloat(await p.locator('.mk').nth(2).locator('[data-field=mline]').inputValue());
  const nb = g.nba; const over = 1 - Phi((line - nb.mu_total)/nb.sd_total);
  const shown = parseInt((await p.locator('.mk').nth(2).locator('.opct').first().innerText()))/100;
  ok(`over ${line} total games matches an independent calculation`, Math.abs(shown-over) < 0.02, `${shown} vs ${over.toFixed(3)}`);
  ok('handicap line is half a game (no push)', /\.5$/.test(String(await p.locator('.mk').nth(1).locator('[data-field=mline]').inputValue())));
  // type odds -> verdict card in Best bets
  await p.locator('.mk').first().locator('input[data-field=modds]').first().fill('1.60'); await p.waitForTimeout(300);
  ok('typing odds shows an edge', /edge|%/.test(await p.locator('.mk').first().locator('.oedge').first().innerText()));
  ok('tennis page: no errors', p.errs.length===0, p.errs.join('|'));
  await p.close();
  // track + settle: first player wins 2-0 in sets; bet on first player to win
  const key = `${g.date}|${g.home}`;
  const mkRes = (extra) => ({ generated_at: new Date().toISOString(), days: 21, nba_stats:['pts','reb','ast','fg3'], football_stats:['shots','sot','goals','assists'], nba:[], football:[], nfl:[], cfb:[],
    tennis: [Object.assign({ key, home:g.home, away:g.away, home_pts:12, away_pts:5, home_sets:2, away_sets:0, void:false, players:{} }, extra)] });
  for (const [name, extra, expect] of [['a bet on the winner is settled as won', {}, /won/i], ['a retirement voids the bet', { void:true }, /void/i]]) {
    p = await open(b, mkRes(extra));
    await p.click('[data-sport=tennis]'); await p.waitForSelector('.mrow[data-open]'); await p.locator('.mrow[data-open]').first().click(); await p.waitForSelector('.mk');
    await p.locator('.mk').first().locator('input[data-field=modds]').first().fill('1.8'); await p.waitForTimeout(300);
    await p.locator('.mk').first().locator('.trk').first().click(); await p.waitForTimeout(300);
    await p.click('#recbtn'); await p.waitForTimeout(500);
    const txt = await p.locator('#list').innerText();
    ok(name, expect.test(txt) && !/waiting for the result/.test(txt), txt.slice(0,220).replace(/\n/g,' | '));
    await p.close();
  }
  await b.close();
  R.forEach(r => console.log(r.join(' | '))); const f = R.filter(r=>r[0]==='FAIL').length; console.log(`${R.length-f} passed, ${f} failed`);
})().catch(e => { console.log('CRASH', e); process.exit(1); });
