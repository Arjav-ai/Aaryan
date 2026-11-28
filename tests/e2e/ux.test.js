require('./_setup');
const { chromium } = require('playwright');
const URL = 'http://localhost:8765/index.html';
const R = []; const ok = (n, c, x='') => R.push([c?'PASS':'FAIL', n, x]);
(async () => {
  const b = await chromium.launch();
  const mk = async (opts={}, w=390) => { const c = await b.newContext(Object.assign({ viewport: { width: w, height: 844 } }, opts)); const p = await c.newPage(); p.errs=[]; p.on('pageerror', e=>p.errs.push(String(e))); await p.goto(URL); await p.waitForSelector('.card, .empty, .mrow'); await p.waitForTimeout(400); return p; };
  // first visit: guide shown, dismissed for good
  let p = await mk({ firstVisit: true });
  ok('first visit shows the short guide', await p.locator('#intro').isVisible() && /Type the line and odds/.test(await p.locator('#intro').innerText()));
  ok('filters start collapsed on a first visit', await p.locator('#fpanel').isHidden());
  await p.click('#introok'); ok('"Got it" hides the guide', await p.locator('#intro').isHidden());
  await p.reload(); await p.waitForSelector('.card, .mrow'); ok('guide stays hidden after reload', await p.locator('#intro').isHidden());
  await p.click('#helpbtn'); ok('Help brings the guide back', await p.locator('#intro').isVisible());
  await p.click('#intromore'); ok('"How accurate is this?" opens the details', await p.evaluate(()=>document.querySelector('#about').open));
  // filters toggle (they live on the Most probable / Best bets screens)
  await p.click('[data-tab=probable]'); await p.waitForSelector('article.card');
  await p.click('#fbtn'); ok('More filters opens game + starting line', await p.locator('#fpanel').isVisible() && await p.locator('#game').isVisible());
  await p.click('#fbtn'); ok('and closes again', await p.locator('#fpanel').isHidden());
  // bottom dock
  const dock = await p.locator('.dock').boundingBox();
  ok('bottom bar sits at the bottom of the screen', dock && Math.abs(dock.y + dock.height - 844) < 2, JSON.stringify(dock));
  const names = await p.locator('.dock .tab, .dock .dockbtn').allInnerTexts();
  ok('bottom bar: Games, Best bets, Most probable, Live', names.length===4 && /Games/.test(names[0]) && /Live/.test(names[3]), names.join('|'));
  // phone ergonomics
  const small = await p.evaluate(() => [...document.querySelectorAll('button:not([hidden]),input:not([hidden]),select')].filter(e => { const r=e.getBoundingClientRect(); return r.width>0 && (r.height<34) && !e.closest('[hidden]') && !e.closest('details:not([open])') ; }).map(e => (e.id||e.className||e.tagName)+':'+Math.round(e.getBoundingClientRect().height)));
  ok('every visible button and field is at least 34px tall', small.length===0, small.slice(0,6).join(','));
  const fs = await p.evaluate(() => [...document.querySelectorAll('input,select')].filter(e=>e.getBoundingClientRect().width>0).map(e=>parseFloat(getComputedStyle(e).fontSize)).filter(s=>s<16).length);
  ok('inputs use 16px text (iPhone does not zoom in when you tap them)', fs===0, String(fs));
  for (const w of [320, 360, 390, 430]) { const q = await mk({}, w); ok(`no sideways scroll at ${w}px`, await q.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), String(await q.evaluate(()=>document.documentElement.scrollWidth))); await q.context().close(); }
  // content is never hidden under the bottom bar
  await p.evaluate(()=>window.scrollTo(0,document.body.scrollHeight)); await p.waitForTimeout(200);
  const last = await p.evaluate(()=>{ const a=document.querySelector('.about').getBoundingClientRect(); return a.bottom; });
  ok('the end of the page can be scrolled clear of the bottom bar', last <= (await p.locator('.dock').boundingBox()).y + 1, String(last));
  ok('no page errors', p.errs.length===0, p.errs.join('|'));
  // first screen: new visitors land on Games; open bets are pinned at the top
  p = await mk({ firstVisit: true }); await p.click('#introok');
  ok('a new visitor lands on Games', /Games/.test(await p.locator('.tab[aria-selected=true]').innerText()) && (await p.locator('.mrow[data-open]').count())>0);
  ok('no open-bets strip when nothing is tracked', (await p.locator('.pin').count())===0);
  await p.evaluate(() => localStorage.setItem('propfinder-ledger', JSON.stringify([{ id: 'x1', t: Date.now(), sp: 'nba', od: 1.9, ln: 20.5, ty: 'prop', gk: '2099-01-01|ZZZ', pl: 'Test Player', st: 'pts', sd: 'over', p: 0.55, pr: 0.55, pp: 0, lab: 'Test Player over 20.5 points', gl: 'AAA at ZZZ' }])));
  await p.reload(); await p.waitForSelector('.mrow[data-open], .card'); await p.waitForTimeout(500);
  ok('an open bet is pinned above the games with its odds', (await p.locator('.pin').count())===1 && /Your open bets \(1\)/.test(await p.locator('.pin').innerText()) && /Test Player over 20\.5 points/.test(await p.locator('.pin').innerText()) && /1\.90/.test(await p.locator('.pin').innerText()), await p.locator('.pin').innerText().catch(()=>''));
  await p.click('#pinall'); await p.waitForTimeout(300);
  ok('"See all" opens My bets', /Your record/.test(await p.locator('#list').innerText()));
  await b.close();
  R.forEach(r => console.log(r.join(' | '))); const f = R.filter(r=>r[0]==='FAIL').length; console.log(`${R.length-f} passed, ${f} failed`);
})().catch(e => { console.log('CRASH', e); process.exit(1); });
