const { chromium } = require('playwright');
const fs = require('fs');
const URL = 'http://localhost:8765/index.html';
const results = []; const dump = [];
const ok = (name, cond, extra='') => { results.push([cond ? 'PASS' : 'FAIL', name, extra]); };
const cards = p => p.locator('#list article.card');
const bad = async p => { const t = await p.locator('body').innerText(); return /NaN|undefined|Infinity|null/.test(t) ? (t.match(/.{0,30}(NaN|undefined|Infinity|null).{0,30}/)||[''])[0] : ''; };
async function fresh(b, opts={}) {
  const ctx = await b.newContext({ viewport: { width: opts.w||390, height: 844 }, colorScheme: opts.dark?'dark':'light' });
  const p = await ctx.newPage(); p.errs=[];
  p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => { if (m.type()==='error') p.errs.push(m.text()); });
  if (opts.route) await p.route('**/predictions.json', opts.route);
  await p.goto(URL); await p.waitForTimeout(400);
  return p;
}
(async () => {
  const b = await chromium.launch();
  let p = await fresh(b); await p.waitForSelector('#list article.card');

  // 1 load
  ok('loads with no console/page errors', p.errs.length===0, JSON.stringify(p.errs));
  ok('shows 40 cards first', await cards(p).count()===40, String(await cards(p).count()));
  ok('header shows data date + updated', /Games to .* updated/.test(await p.locator('#asof').innerText()), await p.locator('#asof').innerText());
  ok('no NaN/undefined text on first load', (await bad(p))==='', await bad(p));

  // 2 tabs
  await p.click('#tab-best'); await p.waitForSelector('.srow');
  ok('Best bets tab selected', (await p.getAttribute('#tab-best','aria-selected'))==='true');
  ok('Best bets lists players with 4 stat rows each', (await p.locator('.srow').count())===160, String(await p.locator('.srow').count()));
  await p.click('#tab-probable');
  ok('back to Most probable', (await p.getAttribute('#tab-probable','aria-selected'))==='true' && await cards(p).first().locator('.pct').count()===1);

  // 3 stat chips
  for (const [stat,label] of [['pts','Points'],['reb','Rebounds'],['ast','Assists'],['fg3','Threes']]) {
    await p.click(`button[data-stat=${stat}]`);
    const metas = await cards(p).locator('.meta').allInnerTexts();
    ok(`stat filter ${label}`, metas.length>0 && metas.every(m=>m.startsWith(label)), metas.slice(0,2).join(' | '));
  }
  await p.click('button[data-stat=all]');

  // 4 game filter
  const opts = await p.locator('#game option').evaluateAll(o=>o.map(x=>[x.value,x.textContent]));
  ok('game dropdown has all 12 games + All', opts.length===13, String(opts.length));
  await p.selectOption('#game', opts[1][0]);
  const [away,, home] = opts[1][1].split(' ');
  const m1 = await cards(p).locator('.meta').allInnerTexts();
  ok('game filter only shows that game', m1.length>0 && m1.every(m=>m.includes(away)||m.includes(home)), opts[1][1]+' -> '+m1.slice(0,2).join(' | '));
  await p.selectOption('#game','all');

  // 5 search
  await p.fill('#q','wemban'); await p.waitForTimeout(1000);
  const names = await cards(p).locator('.name').allInnerTexts();
  ok('player search', names.length>0 && names.every(n=>/wemban/i.test(n)), names.join(','));
  await p.fill('#q','zzzzqq'); await p.waitForTimeout(1000);
  ok('search no match shows empty message', /No props match/.test(await p.locator('#list').innerText()));
  await p.fill('#q',''); await p.waitForTimeout(1000);

  // 6 side
  const before = await cards(p).first().locator('.pct').innerText();
  await p.click('#side-under');
  ok('Under toggle changes wording', /stay under/.test(await cards(p).first().locator('.pct').innerText()), before.replace(/\n/g,' '));
  const ps = (await cards(p).locator('.pct').allInnerTexts()).map(t=>parseInt(t));
  ok('Under cards ranked high to low', ps.every((v,i)=>i===0||ps[i-1]>=v), ps.slice(0,6).join(','));
  await p.click('#side-over');

  // 7 target
  for (const t of ['0.7','0.9']) {
    await p.selectOption('#target', t);
    const pcts=(await cards(p).locator('.pct').allInnerTexts()).map(x=>parseInt(x));
    ok(`starting line ${t*100}%: all cards >= ${t*100}%`, pcts.every(v=>v>=t*100-1), pcts.slice(0,5).join(','));
  }
  await p.selectOption('#target','0.8');

  // 8 minimum odds
  for (const side of ['over','under']) {
    await p.click('#side-'+side);
    for (const min of ['1.5','3']) {
      await p.fill('#min',min); await p.waitForTimeout(1000);
      const be=(await cards(p).locator('.res .pill').first().innerText());
      const bes=(await cards(p).evaluateAll(cs=>cs.map(c=>[...c.querySelectorAll('.res .pill')].map(x=>x.textContent).find(t=>t.startsWith('Break-even'))))).map(t=>parseFloat(t.replace('Break-even odds ','')));
      const n=bes.length;
      ok(`min odds ${min} (${side}): ${n} cards, all break-even >= ${min}`, n>0 && bes.every(v=>v>=parseFloat(min)-0.011), `n=${n} min=${Math.min(...bes)}`);
    }
  }
  ok('target select disabled when min odds set', await p.isDisabled('#target'));
  // typed odds below min hide the card
  await p.click('#side-over'); await p.fill('#min','1.5'); await p.waitForTimeout(900);
  const firstName = await cards(p).first().locator('.name').innerText();
  await cards(p).first().locator('[data-field=odds]').fill('1.2'); await p.waitForTimeout(1200);
  const names2 = await cards(p).locator('.name').allInnerTexts();
  ok('card with odds under minimum is hidden', !(await cards(p).evaluateAll((cs,n)=>cs.some(c=>c.querySelector('.name').textContent===n&&c.querySelector('[data-field=odds]').value==='1.2'),firstName)), firstName);
  await p.fill('#min',''); await p.waitForTimeout(1000);
  ok('clearing minimum re-enables target + shows cards', !(await p.isDisabled('#target')) && await cards(p).count()>0);

  // clean state for numeric checks
  await p.evaluate(()=>localStorage.clear()); await p.reload(); await p.waitForSelector('#list article.card');

  // 9 numeric check dump: type line+odds on 12 cards (over and under)
  for (const side of ['over','under']) {
    await p.click('#side-'+side);
    for (let i=0;i<6;i++) {
      const c = cards(p).nth(i);
      const base = await c.evaluate(e=>e.dataset.base);
      await c.locator('[data-field=line]').fill(String([14.5,20.5,6,3.5,1.5,24][i]));
      await c.locator('[data-field=odds]').fill(['1.85','2.10','1.50','2.5','1.3','1.95'][i]);
      await p.waitForTimeout(150);
      const t = await c.evaluate(e=>({pct:e.querySelector('.pct').innerText, res:e.querySelector('.res').innerText, name:e.querySelector('.name').textContent, meta:e.querySelector('.meta').textContent}));
      dump.push({side, base, name:t.name, unit:t.meta.split(' · ')[0], line:[14.5,20.5,6,3.5,1.5,24][i], odds:parseFloat(['1.85','2.10','1.50','2.5','1.3','1.95'][i]), pct:t.pct.replace(/\n/g,' '), res:t.res.replace(/\n/g,' ')});
    }
    await p.waitForTimeout(900);
  }
  ok('integer lines handled (no NaN)', (await bad(p))==='');
  fs.writeFileSync(process.argv[2]+'/dump.json', JSON.stringify(dump));

  // 10 invalid input
  await p.evaluate(()=>localStorage.clear()); await p.reload(); await p.waitForSelector('#list article.card');
  const c0 = cards(p).first();
  for (const v of ['-5','0','abc','','1e9','0.5']) { await c0.locator('[data-field=odds]').fill(v).catch(()=>{}); await c0.locator('[data-field=line]').fill(v).catch(()=>{}); }
  await p.waitForTimeout(1000);
  ok('bad/odd input never shows NaN/undefined', (await bad(p))==='', await bad(p));
  ok('no JS errors after bad input', p.errs.length===0, JSON.stringify(p.errs));

  // 11 pinning: odds keep their line when starting-line setting changes
  await p.evaluate(()=>localStorage.clear()); await p.reload(); await p.waitForSelector('#list article.card');
  const pc = cards(p).nth(2); const pn = await pc.locator('.name').innerText(); const pu=(await pc.locator('.meta').innerText()).split(' · ')[0];
  const lineBefore = await pc.locator('[data-field=line]').inputValue();
  await pc.locator('[data-field=odds]').fill('1.8'); await p.waitForTimeout(1000);
  await p.selectOption('#target','0.9'); await p.fill('#q',pn); await p.waitForTimeout(1000);
  const same = await cards(p).evaluateAll((cs,[n,u])=>cs.filter(c=>c.querySelector('.name').textContent===n&&c.querySelector('.meta').textContent.startsWith(u)).map(c=>[c.querySelector('[data-field=line]').value,c.querySelector('[data-field=odds]').value]),[pn,pu]);
  ok('line stays pinned after changing starting line', same.length>0 && same[0][0]===lineBefore && same[0][1]==='1.8', `${pn} ${pu}: before ${lineBefore}, after ${JSON.stringify(same)}`);
  await p.fill('#q',''); await p.selectOption('#target','0.8');

  // 12 persistence
  await p.fill('#min','1.4'); await p.click('button[data-stat=reb]'); await p.waitForTimeout(900);
  await p.reload(); await p.waitForSelector('#list article.card');
  ok('settings survive reload (min odds, stat, odds)', (await p.inputValue('#min'))==='1.4' && (await p.getAttribute('button[data-stat=reb]','aria-pressed'))==='true');
  await p.fill('#min',''); await p.click('button[data-stat=all]'); await p.waitForTimeout(900);

  // 13 show more
  await p.evaluate(()=>localStorage.clear()); await p.reload(); await p.waitForSelector('#list article.card');
  await p.click('#more'); ok('Show more adds cards', await cards(p).count()===80, String(await cards(p).count()));

  // 14 best bets: worth / not worth + all-players structure + typing focus
  await p.click('#tab-best'); await p.waitForSelector('.srow');
  const rowsBefore = await p.locator('.srow').count();
  await p.click('button[data-stat=pts]'); ok('Best bets stat filter -> 1 row per player', (await p.locator('.srow').count())===40, String(await p.locator('.srow').count()));
  await p.click('button[data-stat=all]');
  const gh = await p.locator('h3.gh').count(); ok('game headings shown', gh>=1, String(gh));
  const odd = p.locator('.srow').first().locator('[data-field=odds]');
  await odd.click(); await odd.pressSequentially('2.40',{delay:150}); await p.waitForTimeout(1300);
  const hasFocus = await p.evaluate(()=>document.activeElement && document.activeElement.dataset && document.activeElement.dataset.field==='odds');
  ok('typing odds keeps focus and full value', hasFocus, 'active='+await p.evaluate(()=>document.activeElement.tagName));
  const h3s = await p.locator('h3').allInnerTexts();
  ok('typed bet moves into Worth taking / Not worth it', h3s.some(t=>/WORTH TAKING|NOT WORTH IT/i.test(t)), h3s.slice(0,3).join(' | '));
  ok('tab count updates', /^\d+$/.test(await p.locator('#n-best').innerText()));
  // empty-state (fresh)
  await p.evaluate(()=>localStorage.clear()); await p.reload(); await p.waitForSelector('#list article.card');
  await p.click('#tab-best'); await p.waitForSelector('.srow');
  ok('fresh Best bets shows all-players list, no empty-state crash', (await p.locator('.srow').count())>0 && (await bad(p))==='');
  await p.click('#more'); ok('Best bets show more players', (await p.locator('article.card').count())>40, String(await p.locator('article.card').count()));

  // 15 responsive / theme
  for (const w of [360,390,768,1280]) { const q=await fresh(b,{w}); await q.waitForSelector('#list article.card');
    ok(`no horizontal scroll at ${w}px`, !(await q.evaluate(()=>document.documentElement.scrollWidth>innerWidth)), '');
    if(w===360){ await q.screenshot({path:process.argv[2]+'/t360.png'}); } await q.context().close(); }
  const dq = await fresh(b,{dark:true}); await dq.waitForSelector('#list article.card');
  const bg = await dq.evaluate(()=>getComputedStyle(document.body).backgroundColor); ok('dark theme background applied', bg!=='rgb(255, 255, 255)' && bg!=='rgba(0, 0, 0, 0)', bg); await dq.context().close();

  // 16 failure + stale handling
  const f = await fresh(b,{route:r=>r.abort()}); await f.waitForTimeout(800);
  ok('load failure shows a clear message', /Could not load the predictions/.test(await f.locator('#list').innerText())); await f.context().close();
  const old = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions.json','utf8'));
  const st = await fresh(b,{route:r=>r.fulfill({json:{...old,generated_at:new Date(Date.now()-3*864e5).toISOString()}})}); await st.waitForSelector('#list article.card');
  ok('stale notice appears when predictions are 3 days old', await st.locator('#stale').isVisible(), await st.locator('#stale').innerText().catch(()=>'')); await st.context().close();
  const fr = await fresh(b,{route:r=>r.fulfill({json:{...old,generated_at:new Date(Date.now()-3600e3).toISOString()}})}); await fr.waitForSelector('#list article.card');
  ok('no stale notice when fresh', !(await fr.locator('#stale').isVisible())); await fr.context().close();

  for (const [s,n,e] of results) console.log(s, '|', n, e?('| '+e):'');
  console.log('\n'+results.filter(r=>r[0]==='PASS').length+' passed, '+results.filter(r=>r[0]==='FAIL').length+' failed');
  await b.close();
})();
