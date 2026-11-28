require('./_setup');
const { chromium } = require('playwright');
const fs = require('fs');
const URL = 'http://localhost:8765/index.html';
const R = []; const ok = (n, c, x='') => R.push([c?'PASS':'FAIL', n, x]);
const NBA = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions.json','utf8'));
const FB = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions_soccer.json','utf8'));
// independent re-implementation of the chance maths (negative binomial) to check the page
function nb(mu, alpha) { const n=1/alpha, p=n/(n+mu); const pmf=[Math.pow(p,n)], cdf=[pmf[0]]; for (let k=0;k<300&&cdf[k]<0.999999;k++){ const x=pmf[k]*(k+n)/(k+1)*(1-p); pmf.push(x); cdf.push(cdf[k]+x);} return {pmf,cdf}; }
const C = (d,k)=>k<0?0:(k>=d.cdf.length?1:d.cdf[k]); const P = (d,k)=>(k<0||k>=d.pmf.length)?0:d.pmf[k];
function probs(d, line, side){ const f=Math.floor(line), whole=line===f; return side==='over'?{win:1-C(d,f),push:whole?P(d,f):0}:{win:whole?C(d,f-1):C(d,f),push:whole?P(d,f):0}; }
const money = (pr, odds) => { const w=Math.min(pr.win,0.9); return { w, ev: w*odds+pr.push-1, be: (1-pr.push)/w }; };
const word = ev => ev>=0.15?'Unusually large gap':ev>=0.08?'Strong value':ev>=0.03?'Some value':ev>-0.03?'Fair price':ev>-0.10?'Poor value':'Avoid';
const bad = async p => { const t = await p.locator('body').innerText(); const m = t.match(/.{0,30}(NaN|undefined|Infinity|null).{0,30}/); return m ? m[0] : ''; };
const upcoming = DATA => DATA.games.filter(g => Date.parse(g.start) > Date.now());
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } }); const p = await ctx.newPage(); const errs = [];
  p.on('pageerror', e => errs.push(String(e))); p.on('console', m => { if (m.type()==='error') errs.push(m.text()); });
  await p.goto(URL); await p.waitForSelector('.card'); await p.click('button[data-tab=matches]'); await p.waitForSelector('.mrow[data-open]');
  const g = upcoming(NBA).find(x => NBA.players.filter(y=>y.game===x.id).length>10);
  const gi = upcoming(NBA).indexOf(g); await p.locator('.mrow[data-open]').nth(gi).click(); await p.waitForSelector('.srow');
  const plist = NBA.players.filter(x=>x.game===g.id);
  const info = async i => p.evaluate(i => { const row=[...document.querySelectorAll('.srow')][i]; return { name: row.closest('article.card').querySelector('.name').textContent, label: row.querySelector('.slabel').textContent }; }, i);
  const KEY = {Points:'pts',Rebounds:'reb',Assists:'ast',Threes:'fg3'};
  const stat = async i => { const r = await info(i); const pl = plist.find(x=>x.name===r.name); return { ...r, s: pl.stats[KEY[r.label]] }; };

  // ---- the three boxes
  const first = p.locator('.srow').first();
  ok('each prop row has Line, Over and Under boxes', (await first.locator('[data-field=line]').count())===1 && (await first.locator('[data-field=odds]').count())===1 && (await first.locator('[data-field=odds2]').count())===1 && (await first.locator('.field > span').evaluateAll(e=>e.map(x=>x.textContent.trim()))).join('|')==='Line|Over|Under');
  ok('before any odds: no verdict, both sides show the model chance and break-even', (await first.locator('.verdict').count())===0 && /over/.test(await first.locator('.sres').innerText()) && /Under/.test(await first.locator('.oth').innerText()) && /Break-even/.test(await first.locator('.oth').innerText()));

  // ---- verdict words across the whole scale, checked against an independent calculation
  const scale = [[0.22,'Unusually large gap'],[0.11,'Strong value'],[0.05,'Some value'],[0.0,'Fair price'],[-0.06,'Poor value'],[-0.2,'Avoid']];
  const dump = [];
  for (let i=0;i<scale.length;i++) {
    const row = p.locator('.srow').nth(i); const st = await stat(i); const line = Math.floor(st.s.mu)+0.5; const d = nb(st.s.mu, st.s.alpha);
    const mo = money(probs(d,line,'over'),1); const oddsOver = +(mo.be*(1+scale[i][0])).toFixed(2);
    await row.locator('[data-field=line]').fill(String(line)); await row.locator('[data-field=odds]').fill(String(oddsOver)); await p.waitForTimeout(250);
    const evExact = money(probs(d,line,'over'),oddsOver).ev; const v = await row.locator('.verdict').innerText();
    dump.push({ i, line, oddsOver, ev: evExact, v, shown: await row.locator('.sres').innerText() });
    ok(`verdict for edge ${(evExact*100).toFixed(0)}%: "${word(evExact)}"`, v.includes(word(evExact)) && (evExact<0.03 ? true : v.includes('Over '+line)), v.replace(/\n/g,' ').slice(0,110));
    const cls = await row.locator('.verdict').getAttribute('class'); const wantCls = evExact>=0.15?'warn':evExact>=0.03?'good':evExact>-0.03?'':'bad';
    ok(`  colour for "${word(evExact)}"`, (wantCls?cls.includes(wantCls):!/good|bad|warn/.test(cls)), cls);
  }
  ok('only an Over price typed: the verdict says to type the Under odds to compare (when there is an edge or a loss)', /Type the under odds too/.test(await p.locator('.srow').nth(1).locator('.verdict').innerText()));
  ok('gaps over 15% are flagged as suspicious, not as a bargain', /missing something/.test(await p.locator('.srow').nth(0).locator('.verdict').innerText()));
  // chance and break-even shown on the page match the calculation, for both sides
  { const st = await stat(1); const d = nb(st.s.mu, st.s.alpha); const line = dump[1].line; const ov = probs(d,line,'over'), un = probs(d,line,'under'); const row = p.locator('.srow').nth(1);
    const sres = await row.locator('.sres').innerText(), oth = await row.locator('.oth').innerText();
    const pctOver = parseInt(sres.match(/(\d+)% over/)[1]), pctUnder = parseInt(oth.match(/Under [\d.]+: (\d+)%/)[1]);
    ok('Over and Under chances on the row match the calculation', Math.abs(pctOver-Math.round(ov.win*100))<=1 && Math.abs(pctUnder-Math.round(un.win*100))<=1, `page ${pctOver}/${pctUnder} vs ${Math.round(ov.win*100)}/${Math.round(un.win*100)}`);
    const beUnder = parseFloat(oth.match(/Break-even ([\d.]+)/)[1]); ok('Under break-even odds match', Math.abs(beUnder-money(un,1).be)<0.011, `${beUnder} vs ${money(un,1).be.toFixed(3)}`); }

  // ---- both sides priced
  { const row = p.locator('.srow').nth(2); const st = await stat(2); const d = nb(st.s.mu, st.s.alpha); const line = Math.floor(st.s.mu)+0.5;
    await row.locator('[data-field=line]').fill(String(line));
    const beO = money(probs(d,line,'over'),1).be, beU = money(probs(d,line,'under'),1).be;
    await row.locator('[data-field=odds]').fill((beO*0.9).toFixed(2)); await row.locator('[data-field=odds2]').fill((beU*0.9).toFixed(2)); await p.waitForTimeout(300);
    ok('both sides priced and both poor: "Neither side is worth it" with the better one named', /Neither side is worth it/.test(await row.locator('.verdict').innerText()) && /better one is (Over|Under)/.test(await row.locator('.verdict').innerText()), (await row.locator('.verdict').innerText()).replace(/\n/g,' '));
    await row.locator('[data-field=odds2]').fill((beU*1.12).toFixed(2)); await p.waitForTimeout(300);
    const v = await row.locator('.verdict').innerText(); ok('Under now priced well: the verdict picks Under', /on Under/.test(v) && /(Strong value|Some value)/.test(v), v.replace(/\n/g,' ').slice(0,100));
    ok('each priced side offers its own Track bet button', (await row.locator('.trk').count())===2);
    await row.locator('[data-field=odds]').fill((beO*1.12).toFixed(2)); await row.locator('[data-field=odds2]').fill((beU*1.02).toFixed(2)); await p.waitForTimeout(300);
    ok('Over priced better than Under: the verdict picks Over', /on Over/.test(await row.locator('.verdict').innerText()), (await row.locator('.verdict').innerText()).replace(/\n/g,' ').slice(0,90)); }
  // only the Under price typed
  { const row = p.locator('.srow').nth(7); const st = await stat(7); const d = nb(st.s.mu, st.s.alpha); const line = Math.floor(st.s.mu)+0.5; const beU = money(probs(d,line,'under'),1).be;
    await row.locator('[data-field=line]').fill(String(line)); await row.locator('[data-field=odds2]').fill((beU*1.1).toFixed(2)); await p.waitForTimeout(300);
    const v = await row.locator('.verdict').innerText(); ok('only an Under price typed: it is rated, and it asks for the Over odds', /on Under/.test(v) && /Type the over odds too/.test(v), v.replace(/\n/g,' ').slice(0,110)); }
  // whole-number line: a push is possible and is handled
  { const row = p.locator('.srow').nth(4); const st = await stat(4); const d = nb(st.s.mu, st.s.alpha); const line = Math.max(1, Math.round(st.s.mu));
    await row.locator('[data-field=line]').fill(String(line)); await row.locator('[data-field=odds]').fill('1.9'); await row.locator('[data-field=odds2]').fill('1.9'); await p.waitForTimeout(300);
    const ov = money(probs(d,line,'over'),1.9), un = money(probs(d,line,'under'),1.9); const txt = await row.locator('.sres').innerText()+' '+await row.locator('.oth').innerText();
    const edges = [...txt.matchAll(/([+−-]\d+)% edge/g)].map(m=>parseInt(m[1].replace('−','-')));
    ok(`whole-number line ${line}: edges include the refunded push (expected ${Math.round(ov.ev*100)}% / ${Math.round(un.ev*100)}%)`, edges.length===2 && Math.abs(edges[0]-Math.round(ov.ev*100))<=1 && Math.abs(edges[1]-Math.round(un.ev*100))<=1, edges.join(','));
    dump.push({ i: 4, line, whole: true }); }
  // the offered line is shared by both sides
  { const row = p.locator('.srow').nth(2); await row.locator('[data-field=line]').fill('13.5'); await p.waitForTimeout(250);
    ok('changing the offered line moves both Over and Under to it', /over 13\.5/.test(await row.locator('.sres').innerText()) && /Under 13\.5/.test(await row.locator('.oth').innerText())); }

  // ---- tracking each side
  await p.click('#recbtn'); const nBefore = 0; await p.click('#recbtn');
  { const row = p.locator('.srow').nth(2); await row.locator('.trk').nth(1).click(); await p.waitForTimeout(300);
    const led = await p.evaluate(()=>JSON.parse(localStorage.getItem('propfinder-ledger')||'[]')); ok('tracking the Under side stores an Under bet at the offered line', led.length===1 && led[0].sd==='under' && led[0].ln===13.5, JSON.stringify(led[0]||{}).slice(0,160)); }

  // ---- the Over/Under switch swaps which side is the main one, odds stay with their side
  { const row = p.locator('.srow').nth(7); const beforeUnder = await row.locator('[data-field=odds2]').inputValue();
    await p.click('button[data-tab=probable]'); await p.waitForSelector('article.card .pct'); await p.click('#side-under'); await p.waitForTimeout(400);
    await p.click('button[data-tab=matches]'); await p.waitForSelector('.mrow[data-open]'); await p.locator('.mrow[data-open]').nth(gi).click(); await p.waitForSelector('.srow'); const r2 = p.locator('.srow').nth(7);
    ok('with the switch on Under, the Under box (now the main one) still holds the Under price', (await r2.locator('[data-field=odds]').inputValue())===beforeUnder && (await r2.locator('.field > span').evaluateAll(e=>e.map(x=>x.textContent.trim()))).join('|')==='Line|Over|Under');
    await p.click('button[data-tab=probable]'); await p.waitForSelector('article.card .pct'); await p.click('#side-over'); await p.waitForTimeout(300); }

  // ---- cards (Most probable / Best bets) get the same boxes and verdict
  await p.click('button[data-tab=probable]'); await p.waitForSelector('article.card .pct');
  { const c = p.locator('article.card').first(); ok('Most probable cards have Line offered / Over odds / Under odds', (await c.locator('.field > span').evaluateAll(e=>e.map(x=>x.textContent.trim()))).join('|')==='Line offered|Over odds|Under odds');
    await c.locator('[data-field=odds2]').fill('2.2'); await p.waitForTimeout(300); ok('a card rates a typed Under price too', (await c.locator('.verdict').count())===1 && /Under/.test(await c.locator('.verdict').innerText())); }
  await p.waitForTimeout(900); await p.click('button[data-tab=best]'); await p.waitForSelector('h3'); const txt = await p.locator('#list').innerText();
  ok('Best bets lists props priced on either side', /Worth taking|Not worth it/i.test(txt) && (await p.locator('#n-best').innerText()).length>0);
  ok('no NaN / undefined anywhere', (await bad(p))==='', await bad(p));

  // ---- football props: same boxes, small numbers (0.5 lines)
  await p.click('button[data-sport=football]'); await p.waitForTimeout(900); await p.click('button[data-tab=matches]'); await p.waitForSelector('.mrow[data-open]');
  const fg = upcoming(FB).find(x => FB.players.filter(y=>y.game===x.id).length>15); await p.locator('.mrow[data-open]').nth(upcoming(FB).indexOf(fg)).click(); await p.waitForSelector('.srow');
  { const row = p.locator('.srow').first(); await row.locator('[data-field=line]').fill('0.5'); await row.locator('[data-field=odds]').fill('3.2'); await row.locator('[data-field=odds2]').fill('1.3'); await p.waitForTimeout(300);
    ok('football props rate both sides at a 0.5 line', (await row.locator('.verdict').count())===1 && /Over|Under|Neither|Fair/.test(await row.locator('.verdict').innerText()), (await row.locator('.verdict').innerText()).replace(/\n/g,' ').slice(0,100)); }
  ok('no page errors', errs.length===0, JSON.stringify(errs));
  for (const w of [360,390,768,1280]) { const q=await (await b.newContext({viewport:{width:w,height:844}})).newPage(); await q.goto(URL); await q.waitForSelector('.card'); await q.click('button[data-tab=matches]'); await q.waitForSelector('.mrow[data-open]'); await q.locator('.mrow[data-open]').nth(gi).click(); await q.waitForSelector('.srow');
    const r = q.locator('.srow').first(); await r.locator('[data-field=line]').fill('15.5'); await r.locator('[data-field=odds]').fill('1.95'); await r.locator('[data-field=odds2]').fill('1.85'); await q.waitForTimeout(300);
    ok(`no sideways scroll with three boxes and a verdict at ${w}px`, !(await q.evaluate(()=>document.documentElement.scrollWidth>innerWidth))); if (w===360) await q.screenshot({path:process.argv[2]+'/verdict360.png'}); await q.context().close(); }
  for (const [s,n,e] of R) console.log(s,'|',n,e?('| '+e):'');
  console.log('\n'+R.filter(r=>r[0]==='PASS').length+' passed, '+R.filter(r=>r[0]==='FAIL').length+' failed');
  await b.close();
})().catch(e=>{ for (const [s,n,x] of R) console.log(s,'|',n,x?('| '+x):''); console.log('CRASH:',String(e).split('\n')[0]); process.exit(1); });
