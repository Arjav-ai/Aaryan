require('./_setup');
const { chromium } = require('playwright');
const fs = require('fs');
const URL = 'http://localhost:8765/index.html';
const R = []; const ok = (n, c, x='') => R.push([c?'PASS':'FAIL', n, x]);
const NBA = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions.json','utf8'));
const now = Date.now();
const N2 = JSON.parse(JSON.stringify(NBA)); N2.games.forEach((g,i)=>{ g.start = new Date(now + 86400e3 + i*600e3).toISOString(); g.date = g.start.slice(0,10); }); N2.generated_at = new Date(now-60e3).toISOString();
const bad = async p => { const t = await p.locator('body').innerText(); return /NaN|undefined|Infinity|\bnull\b/.test(t) ? (t.match(/.{0,30}(NaN|undefined|Infinity|null).{0,30}/)||[''])[0] : ''; };
async function open(b) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } }); const p = await ctx.newPage(); p.errs=[];
  p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => { if (m.type()==='error' && !/Failed to load resource/.test(m.text())) p.errs.push(m.text()); });
  await p.route('**/predictions.json', r => r.fulfill({ json: N2 }));
  await p.goto(URL); await p.waitForSelector('.card'); return { p, ctx };
}
(async () => {
  const b = await chromium.launch();
  let { p, ctx } = await open(b);
  ok('no slip bar when the slip is empty', await p.locator('#slipbar').isHidden());
  // two cards on Most probable, type odds on each
  const cards = p.locator('article.card[data-key]');
  const c0 = cards.nth(0), c1 = cards.nth(1);
  ok('no "Add to slip" before odds are typed', (await p.locator('.slp').count())===0);
  await c0.locator('[data-field=odds]').fill('1.90'); await p.waitForTimeout(250);
  ok('Add to slip appears once odds are typed', (await c0.locator('.slp').count())===1 && /Add to slip/.test(await c0.locator('.slp').innerText()));
  await c0.locator('.slp').click(); await p.waitForTimeout(250);
  ok('slip bar shows 1 bet', await p.locator('#slipbar').isVisible() && /Slip · 1/.test(await p.locator('#slipbar').innerText()), await p.locator('#slipbar').innerText());
  ok('the button now says In slip', /In slip/.test(await p.locator('article.card[data-key]').nth(0).locator('.slp').innerText()));
  await p.locator('article.card[data-key]').nth(1).locator('[data-field=odds]').fill('2.10'); await p.waitForTimeout(250);
  await p.locator('article.card[data-key]').nth(1).locator('.slp').click(); await p.waitForTimeout(250);
  ok('slip bar shows 2 bets with combined odds 3.99 (1.90 x 2.10)', /Slip · 2/.test(await p.locator('#slipbar').innerText()) && /3\.99/.test(await p.locator('#slipbar').innerText()), await p.locator('#slipbar').innerText());
  await p.click('#slipopen'); await p.waitForSelector('#slipcalc');
  const legs = await p.locator('.brow').allInnerTexts();
  ok('slip lists both bets', legs.length===2, legs.join(' || ').replace(/\n/g,' '));
  const chances = legs.map(t => parseInt(/(\d+)% chance/.exec(t)[1]) / 100);
  const tiles = await p.locator('#slipcalc .tile b').allInnerTexts();
  ok('combined odds tile = 3.99', tiles[0].trim()==='3.99', tiles.join(','));
  const expP = chances[0]*chances[1];
  const shownP = /(\d+)%|under 1%/.exec(tiles[1]); const sp = shownP[1] ? parseInt(shownP[1])/100 : 0;
  ok('combined chance = product of the two chances (within rounding)', Math.abs(sp - expP) <= 0.02, `${sp} vs ${expP.toFixed(3)}`);
  const edgeShown = parseInt(tiles[2].replace('−','-').replace('+','')) / 100;
  ok('edge = chance x odds - 1', Math.abs(edgeShown - (expP*3.99 - 1)) <= 0.05, `${edgeShown} vs ${(expP*3.99-1).toFixed(3)}`);
  ok('a verdict sentence and a break-even figure are shown', /break even/.test(await p.locator('#slipcalc .verdict').innerText()) && /\d\.\d\d/.test(await p.locator('#slipcalc .verdict').innerText()));
  // bookmaker's own price changes the edge
  await p.fill('#slipbook', '3.00'); await p.waitForTimeout(200);
  const tiles2 = await p.locator('#slipcalc .tile b').allInnerTexts(); const spans = await p.locator('#slipcalc .tile span').allInnerTexts();
  const e2 = parseInt(tiles2[2].replace('−','-').replace('+',''))/100;
  ok('typing the bookmaker price recalculates the edge at that price', /your price/.test(spans[2]) && Math.abs(e2 - (expP*3.00 - 1)) <= 0.05, `${e2} vs ${(expP*3-1).toFixed(3)} | ${spans[2]}`);
  ok('combined odds tile still shows the multiplied odds', (await p.locator('#slipcalc .tile b').first().innerText()).trim()==='3.99');
  const sameGame = legs.length===2 && (await p.locator('#slipcalc .notice').count())===1;
  const gl = await p.locator('.brow .meta').allInnerTexts();
  ok('a warning appears only when two bets are from the same game', sameGame === (gl[0]===gl[2]), gl.join(' | '));
  // persistence
  await p.reload(); await p.waitForSelector('.card'); ok('the slip survives a reload', await p.locator('#slipbar').isVisible() && /Slip · 2/.test(await p.locator('#slipbar').innerText()));
  await p.click('#slipopen'); await p.waitForSelector('#slipcalc');
  await p.locator('[data-slipdel]').first().click(); await p.waitForTimeout(200);
  ok('Remove takes one bet out', (await p.locator('.brow').count())===1);
  await p.locator('[data-slipclear]').click(); await p.waitForTimeout(250);
  ok('Clear empties the slip and hides the bar', await p.locator('#slipbar').isHidden());
  ok('no NaN/undefined', (await bad(p))==='', await bad(p));
  ok('no page errors', p.errs.length===0, p.errs.join('|'));
  // empty slip view
  await ctx.close();
  // two bets from the same game raise the warning
  ({ p, ctx } = await open(b));
  const gm = N2.players[0].game; await p.click('[data-tab=matches]'); await p.waitForSelector('.mrow[data-open]');
  await p.locator(`.mrow[data-open="${gm}"]`).click(); await p.waitForSelector('.srow');
  const rows = p.locator('.srow');
  for (const i of [0,1]) { await rows.nth(i).locator('[data-field=odds]').fill('1.9'); await p.waitForTimeout(200); await rows.nth(i).locator('.slp').click(); await p.waitForTimeout(200); }
  await p.click('#slipopen'); await p.waitForSelector('#slipcalc');
  ok('two bets from one game show the linked-bets warning', /same game/.test(await p.locator('#slipcalc').innerText()), (await p.locator('#slipcalc').innerText()).slice(0,200));
  await ctx.close();
  await b.close();
  R.forEach(r => console.log(r.join(' | '))); const f = R.filter(r=>r[0]==='FAIL').length; console.log(`${R.length-f} passed, ${f} failed`);
})().catch(e => { console.log('CRASH', e); process.exit(1); });
