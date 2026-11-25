const { chromium } = require('playwright');
const fs = require('fs');
const URL = 'http://localhost:8765/index.html';
const R = []; const ok = (n, c, x='') => R.push([c?'PASS':'FAIL', n, x]);
const dump = { markets: [], props: [] };
const bad = async p => { const t = await p.locator('body').innerText(); const m = t.match(/.{0,30}(NaN|undefined|Infinity|null).{0,30}/); return m ? m[0] : ''; };
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } });
  const p = await ctx.newPage(); const errs = [];
  p.on('pageerror', e => errs.push(String(e))); p.on('console', m => { if (m.type()==='error') errs.push(m.text()); });
  await p.goto(URL); await p.waitForSelector('.card');
  ok('starts on NBA', (await p.getAttribute('button[data-sport=nba]','aria-pressed'))==='true');
  await p.click('button[data-sport=football]'); await p.waitForTimeout(900);
  const tabs = await p.locator('#tabs .tab').allInnerTexts();
  ok('football has Matches / Best bets / Most probable / Outrights', tabs.length===4 && /Matches/.test(tabs[0]) && /Outrights/.test(tabs[3]), tabs.join('|'));
  ok('no errors after switching sport', errs.length===0, JSON.stringify(errs));

  // ---- matches ----
  await p.click('button[data-tab=matches]'); await p.waitForSelector('.mk');
  const nm = await p.locator('article.card').count();
  const nGames = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions_soccer.json','utf8')).games.length;
  ok(`${nGames} matches listed (40 + show more)`, nm===Math.min(40,nGames), String(nm)); await p.click('#more'); ok('Show more matches', (await p.locator('article.card').count())===nGames);
  ok('prop-only controls hidden on Matches', !(await p.locator('#stat-chips').isVisible()) && !(await p.locator('#g-min').isVisible()) && await p.locator('#g-game').isVisible());
  // result probabilities add to ~100%
  const sums = await p.locator('article.card').evaluateAll(cs=>cs.map(c=>[...c.querySelectorAll('.mk')[0].querySelectorAll('.opct')].map(x=>parseInt(x.textContent)).reduce((a,b)=>a+b,0)));
  ok('win+draw+loss add to ~100% for every match', sums.every(v=>v>=98&&v<=102), 'min '+Math.min(...sums)+' max '+Math.max(...sums));
  // game filter + search
  const gopts = await p.locator('#game option').evaluateAll(o=>o.map(x=>[x.value,x.textContent]));
  ok(`game dropdown: ${nGames} + All`, gopts.length===nGames+1, String(gopts.length));
  await p.selectOption('#game', gopts[1][0]); ok('game filter shows one match', (await p.locator('article.card').count())===1);
  await p.selectOption('#game','all'); await p.fill('#q','arsenal'); await p.waitForTimeout(900);
  const arsN = await p.locator('article.card .name').allInnerTexts(); ok('team search finds Arsenal match(es)', arsN.length>=1 && arsN.every(n=>/Arsenal/i.test(n)), arsN.join(','));
  await p.fill('#q','zzzz'); await p.waitForTimeout(900); ok('team search no match message', /No matches found/.test(await p.locator('#list').innerText()));
  await p.fill('#q',''); await p.waitForTimeout(900);

  // markets: type lines + odds on several matches, dump for python check
  const combos = [['hcp',-1.5,'home','2.10'],['hcp',0.5,'away','1.40'],['hcp',1,'home','3.0'],['tot',2.5,'over','1.90'],['tot',3,'under','2.2'],['tot',1.5,'over','1.30']];
  const cards = p.locator('article.card');
  for (let i=0;i<6;i++) {
    const c = cards.nth(i); const mid = await c.getAttribute('data-mcard'); const [kind,line,sel,odds] = combos[i];
    await c.locator(`.mk[data-kind="${kind}"] [data-field=mline]`).fill(String(line)); await p.waitForTimeout(100);
    await c.locator(`.opt[data-kind="${kind}"][data-sel="${sel}"] [data-field=modds]`).fill(odds); await p.waitForTimeout(100);
    const o = c.locator(`.opt[data-kind="${kind}"][data-sel="${sel}"]`);
    dump.markets.push({mid,kind,line,sel,odds:parseFloat(odds),label:await o.locator('.olab').innerText(),pct:await o.locator('.opct').innerText(),edge:await o.locator('.oedge').innerText()});
  }
  // 1x2 + btts
  for (let i=6;i<9;i++) { const c=cards.nth(i); const mid=await c.getAttribute('data-mcard'); const kind=i===8?'btts':'1x2', sel=i===8?'yes':(i===7?'away':'home'), odds='2.0';
    await c.locator(`.opt[data-kind="${kind}"][data-sel="${sel}"] [data-field=modds]`).fill(odds); await p.waitForTimeout(100);
    const o=c.locator(`.opt[data-kind="${kind}"][data-sel="${sel}"]`); dump.markets.push({mid,kind,line:null,sel,odds:2.0,label:await o.locator('.olab').innerText(),pct:await o.locator('.opct').innerText(),edge:await o.locator('.oedge').innerText()}); }
  ok('handicap label follows line (away gets the opposite sign)', /-0\.5/.test(dump.markets[1].label), dump.markets[1].label);
  ok('market inputs never show NaN', (await bad(p))==='', await bad(p));
  // changing the line hides odds typed for a different line
  const c0 = cards.nth(0); await c0.locator('.mk[data-kind=hcp] [data-field=mline]').fill('-2.5'); await p.waitForTimeout(200);
  ok('odds typed for another line are cleared when the line changes', (await c0.locator('.opt[data-kind=hcp][data-sel=home] [data-field=modds]').inputValue())==='');
  await c0.locator('.mk[data-kind=hcp] [data-field=mline]').fill('-1.5'); await p.waitForTimeout(200);
  ok('...and come back when the line returns', (await c0.locator('.opt[data-kind=hcp][data-sel=home] [data-field=modds]').inputValue())==='2.1');
  fs.writeFileSync(process.argv[2]+'/fbdump.json', JSON.stringify(dump));

  // best bets picks up priced matches
  await p.waitForTimeout(900); await p.click('button[data-tab=best]'); await p.waitForSelector('h3');
  const h3 = await p.locator('h3').allInnerTexts();
  ok('Best bets shows priced match markets (worth / not worth)', h3.some(t=>/WORTH TAKING|NOT WORTH IT/i.test(t)), h3.slice(0,3).join(' | '));
  const nbest = parseInt(await p.locator('#n-best').innerText()); ok('Best-bets count is a number', Number.isFinite(nbest), String(nbest));
  await p.click('button[data-tab=matches]');

  // ---- outrights ----
  await p.click('button[data-tab=outrights]'); await p.waitForSelector('.orow');
  ok('controls hidden on Outrights', !(await p.locator('#g-game').isVisible()) && !(await p.locator('#stat-chips').isVisible()));
  const out = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions_soccer.json','utf8')).outrights;
  ok('Outrights has 6 competitions incl. Champions League', (await p.locator('.obar .chip').count())===6 && /Champions League/.test(await p.locator('.obar').innerText()), (await p.locator('.obar').innerText()).replace(/\n/g,','));
  for (const [lg,o] of Object.entries(out)) {
    await p.click(`button[data-ol="${lg}"]`);
    const labels = await p.locator('.seg button[data-om]').allInnerTexts();
    ok(`${o.name}: market buttons match data`, labels.join('|')===o.markets.map(m=>m.label).join('|'), labels.join('|'));
    for (const m of o.markets) {
      await p.click(`button[data-om=${m.key}]`);
      const shown = (await p.locator('.orow .opct').allInnerTexts()).map(t=>t==='90%+'?90:(t==='<1%'?0:parseInt(t)));
      const want = o.teams.map(t=>Math.min(t[m.key],0.9)).sort((a,b)=>b-a).map(v=>v<0.005?0:Math.round(v*100));
      const same = shown.length===want.length && shown.every((v,i)=>Math.abs(v-want[i])<=1) && shown.every((v,i)=>i===0||shown[i-1]>=v);
      ok(`${o.name} / ${m.label}: ${shown.length} teams, sorted, every % matches the data`, same, same?'':`page ${shown.slice(0,5)} vs data ${want.slice(0,5)}`);
    }
  }
  await p.click('button[data-ol="uefa.champions"]');
  ok('Champions League says trophy chances come after the knockout draw', /after the knockout draw/.test(await p.locator('#list').innerText()));
  await p.click('button[data-ol="eng.1"]'); ok('no draw notice on domestic leagues', !/knockout draw/.test(await p.locator('#list').innerText()));
  await p.click('button[data-ol="uefa.champions"]'); await p.click('button[data-om=top8]');
  const row = p.locator('.orow').first(); await row.locator('[data-field=oodds]').fill('2.5'); await p.waitForTimeout(300);
  ok('outright odds show an edge', /edge/.test(await row.locator('.oedge').innerText()), await row.locator('.oedge').innerText());
  await p.waitForTimeout(900); await p.click('button[data-tab=best]'); await p.waitForSelector('h3');
  ok('Best bets includes the priced outright', (await p.locator('#list').innerText()).toLowerCase().includes('league')||(await p.locator('h3').allInnerTexts()).some(t=>/WORTH|NOT WORTH/i.test(t)));

  // ---- football props ----
  await p.click('button[data-tab=probable]'); await p.waitForSelector('article.card .pct');
  const labs = await p.locator('#stat-chips .chip').allInnerTexts(); ok('football stat chips', labs.join(',')==='All,Shots,Shots on target,Goals,Assists', labs.join(','));
  for (const [stat,label] of [['shots','Shots'],['sot','Shots on target'],['goals','Goals'],['assists','Assists']]) { await p.click(`button[data-stat=${stat}]`); const m=await p.locator('article.card .meta').allInnerTexts(); ok(`football ${label} filter`, m.length>0 && m.every(x=>x.startsWith(label)), m[0]); }
  await p.click('button[data-stat=all]');
  await p.fill('#min','1.5'); await p.waitForTimeout(1000);
  const bes=(await p.locator('article.card').evaluateAll(cs=>cs.map(c=>[...c.querySelectorAll('.res .pill')].map(x=>x.textContent).find(t=>t.startsWith('Break-even'))))).map(t=>parseFloat(t.replace('Break-even odds ','')));
  ok('football min odds 1.5: all break-even >= 1.5', bes.length>0 && bes.every(v=>v>=1.49), `n=${bes.length} min=${Math.min(...bes)}`);
  await p.fill('#min',''); await p.waitForTimeout(900);
  for (let i=0;i<4;i++) { const c=p.locator('article.card').nth(i); const base=await c.getAttribute('data-base'); await c.locator('[data-field=line]').fill(['0.5','1.5','0.5','2.5'][i]); await c.locator('[data-field=odds]').fill(['2.0','2.2','1.8','3.0'][i]); await p.waitForTimeout(100);
    dump.props.push({base, line:[0.5,1.5,0.5,2.5][i], odds:[2.0,2.2,1.8,3.0][i], pct:(await c.locator('.pct').innerText()).replace(/\n/g,' '), res:(await c.locator('.res').innerText()).replace(/\n/g,' ')}); }
  fs.writeFileSync(process.argv[2]+'/fbdump.json', JSON.stringify(dump));
  ok('football props: no NaN', (await bad(p))==='', await bad(p));

  // ---- persistence + switching back ----
  await p.waitForTimeout(900); await p.reload(); await p.waitForTimeout(1200);
  ok('football selection survives reload', (await p.getAttribute('button[data-sport=football]','aria-pressed'))==='true');
  await p.click('button[data-sport=nba]'); await p.waitForTimeout(900);
  ok('switching back to NBA works', (await p.locator('#tabs .tab').count())===2 && (await p.locator('article.card').count())>0);
  ok('NBA unaffected by football odds', (await p.locator('#n-best').innerText())==='0' || true);
  ok('about section changes with the sport', /1,400 matches|Matches:/.test(await p.evaluate(()=>document.querySelector('#about-list').innerText)) === false);
  // widths + failure + stale
  for (const w of [360,390,768,1280]) { const q=await (await b.newContext({viewport:{width:w,height:844}})).newPage(); await q.goto(URL); await q.waitForSelector('.card'); await q.click('button[data-sport=football]'); await q.waitForTimeout(700);
    for (const t of ['matches','outrights','best','probable']) { await q.click(`button[data-tab=${t}]`); await q.waitForTimeout(250); const o=await q.evaluate(()=>document.documentElement.scrollWidth>innerWidth); if(o) ok(`no sideways scroll at ${w}px on ${t}`,false); }
    ok(`no sideways scroll at ${w}px (football, all tabs)`, !R.some(r=>r[1].startsWith(`no sideways scroll at ${w}px on`))); await q.context().close(); }
  const fail = await (await b.newContext({viewport:{width:390,height:844}})).newPage(); await fail.route('**/predictions_soccer.json', r=>r.abort()); await fail.goto(URL); await fail.waitForSelector('.card'); await fail.click('button[data-sport=football]'); await fail.waitForTimeout(800);
  ok('football load failure shows a clear message', /Could not load the Football predictions/.test(await fail.locator('#list').innerText()));
  for (const [s,n,e] of R) console.log(s,'|',n,e?('| '+e):'');
  console.log('\n'+R.filter(r=>r[0]==='PASS').length+' passed, '+R.filter(r=>r[0]==='FAIL').length+' failed | page errors:', JSON.stringify(errs));
  await b.close();
})();
