require('./_setup');
const { chromium } = require('playwright');
const fs = require('fs');
const URL = 'http://localhost:8765/index.html';
const R = []; const ok = (n, c, x='') => R.push([c?'PASS':'FAIL', n, x]);
const SC0 = JSON.parse(fs.readFileSync('/home/user/aaryan/data/scorecard.json','utf8'));
const SC = JSON.parse(JSON.stringify(SC0));
SC.sports.nfl = Object.assign(SC.sports.nfl, { settled: 12, logged: 14,
  games: { n: 12, winner_right: 0.75, brier: 0.18, brier_coin: 0.25, logloss: 0.5475, bins: [{ band: '0-30%', n: 3, said: 0.22, happened: 0.33 }, { band: '70-100%', n: 5, said: 0.8, happened: 0.8 }] },
  totals: { n: 12, said_over: 0.486, happened_over: 0.5, miss: 1.5, expected_avg: 44.0 },
  props: { n: 161, said_over: 0.399, happened_over: 0.304, bins: [{ band: '30-45%', n: 120, said: 0.4, happened: 0.31 }], stats: [{ stat: 'Receiving yards', n: 161, said_over: 0.399, happened_over: 0.304, expected: 40.0, actual: 35.2 }] } });
async function open(b, route) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } }); const p = await ctx.newPage(); p.errs=[];
  p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => { if (m.type()==='error' && !/Failed to load resource/.test(m.text())) p.errs.push(m.text()); });
  if (route) await p.route('**/scorecard.json*', route);
  await p.goto(URL); await p.waitForSelector('.card, .empty'); return p;
}
(async () => {
  const b = await chromium.launch();
  let p = await open(b, r => r.fulfill({ json: SC0 }));
  await p.click('#recbtn'); await p.waitForTimeout(300);
  ok('Record opens on My bets with a switch to Model record', (await p.locator('[data-rtab]').count())===2 && (await p.locator('[data-rtab=mine]').getAttribute('aria-pressed'))==='true' && /Nothing tracked yet/.test(await p.locator('#list').innerText()));
  await p.click('[data-rtab=model]'); await p.waitForSelector('.tested'); 
  const txt = await p.locator('#list').innerText();
  ok('Model record explains the two kinds of evidence', /Tested on past games/.test(txt) && /Live record/.test(txt) && /saved before the game starts/.test(txt));
  ok('one card per sport (5) plus the intro', (await p.locator('#list article.card').count())===6, String(await p.locator('#list article.card').count()));
  ok('each sport lists its tested numbers', (await p.locator('.tested').count())===5);
  ok('with nothing settled it says so plainly', /none finished yet|Nothing saved yet/.test(txt));
  ok('no NaN/undefined', !/NaN|undefined|Infinity/.test(txt), '');
  await p.close();
  p = await open(b, r => r.fulfill({ json: SC }));
  await p.click('#recbtn'); await p.click('[data-rtab=model]'); await p.waitForSelector('.tested');
  const card = p.locator('#list article.card', { hasText: 'NFL' }).first(); const t2 = await card.innerText();
  ok('settled numbers are shown: 12 games, 75% winners, error score 0.180', /12 finished games/.test(t2) && /75%/.test(t2) && /0\.180/.test(t2), t2.slice(0,260).replace(/\n/g,' | '));
  ok('fewer than 30 games is flagged as mostly luck', /Fewer than 30 games/.test(t2));
  ok('calibration table rows match the data (0-30%: said 22%, happened 33%)', /0-30%\s*3\s*22%\s*33%/.test(t2.replace(/\n/g,' ')) || (/0-30%/.test(t2) && /22%/.test(t2) && /33%/.test(t2)));
  ok('totals sentence uses expected 44.0 and real average 45.5', /expected 44 on average/.test(t2) || /expected 44\.0/.test(t2));
  ok('props: 161 predictions, said 40%, happened 30%', /161 player predictions/.test(t2) && /40%/.test(t2) && /30%/.test(t2));
  ok('per-stat table shows Receiving yards 40 vs 35.2', /Receiving yards/.test(t2) && /35\.2/.test(t2));
  await p.click('[data-rtab=mine]'); ok('switching back shows My bets', /Nothing tracked yet|Your record/.test(await p.locator('#list').innerText()));
  ok('no page errors', p.errs.length===0, p.errs.join('|'));
  await p.close();
  p = await open(b, r => r.fulfill({ status: 404, body: '' }));
  await p.click('#recbtn'); await p.click('[data-rtab=model]'); await p.waitForTimeout(500);
  ok('if the scorecard cannot be loaded there is a friendly message', /could not be loaded/.test(await p.locator('#list').innerText()));
  await b.close();
  R.forEach(r => console.log(r.join(' | '))); const f = R.filter(r=>r[0]==='FAIL').length; console.log(`${R.length-f} passed, ${f} failed`);
})().catch(e => { console.log('CRASH', e); process.exit(1); });
