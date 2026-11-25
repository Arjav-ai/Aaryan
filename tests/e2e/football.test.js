const { chromium } = require('playwright');
const fs = require('fs');
const URL = 'http://localhost:8765/index.html';
const R = []; const ok = (n, c, x='') => R.push([c?'PASS':'FAIL', n, x]);
const dump = { markets: [], props: [] };
const DATA = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions_soccer.json','utf8'));
const upcoming = DATA.games.filter(g => Date.parse(g.start) > Date.now());
const bad = async p => { const t = await p.locator('body').innerText(); const m = t.match(/.{0,30}(NaN|undefined|Infinity|null).{0,30}/); return m ? m[0] : ''; };
const pc = t => t.includes('90%+') ? 90 : (t.includes('<1%') ? 0 : parseInt(t.match(/(\d+)%/)[1]));
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } });
  const p = await ctx.newPage(); const errs = [];
  p.on('pageerror', e => errs.push(String(e))); p.on('console', m => { if (m.type()==='error') errs.push(m.text()); });
  await p.goto(URL); await p.waitForSelector('.card');
  await p.click('button[data-sport=football]'); await p.waitForTimeout(900);
  const tabs = await p.locator('#tabs .tab').allInnerTexts();
  ok('football has Matches / Best bets / Most probable / Outrights', tabs.length===4 && /Matches/.test(tabs[0]) && /Outrights/.test(tabs[3]), tabs.join('|'));
  ok('no errors after switching sport', errs.length===0, JSON.stringify(errs));

  // ---------- matches list ----------
  await p.click('button[data-tab=matches]'); await p.waitForSelector('.mrow');
  const nRows = await p.locator('.mrow').count();
  ok(`${upcoming.length} upcoming matches listed`, nRows===upcoming.length, String(nRows));
  ok('list: stat/odds filters hidden, league chips + team search shown, game dropdown hidden', !(await p.locator('#stat-chips').isVisible()) && !(await p.locator('#g-min').isVisible()) && await p.locator('#lg-chips').isVisible() && await p.locator('#q').isVisible() && !(await p.locator('#game').isVisible()));
  const rows = await p.locator('.mrow').evaluateAll(rs => rs.map(r => ({ t: r.innerText, id: r.dataset.open, lg: r.querySelector('.mmeta').innerText })));
  const sums = rows.map(r => { const l=r.t.split('\n'); const pcts=[...r.t.matchAll(/(90%\+|<1%|\d+%)/g)].map(m=>m[1]); return pcts; });
  const ok1 = rows.every((r,i) => { const [h,a,d] = [pc(r.t.split('\n').filter(x=>/%/.test(x))[0]), 0,0]; return true; });
  const tot = rows.map(r => { const m=[...r.t.matchAll(/(90%\+|<1%|\d+%)/g)].map(x=>pc(x[1])); return m[0]+m[1]+m[2]; });
  ok('win + away + draw add to about 100% on every row', tot.every(v=>v>=97&&v<=103), `min ${Math.min(...tot)} max ${Math.max(...tot)}`);
  const order = rows.map(r=>r.id); const want = upcoming.map(g=>g.id);
  ok('matches are in kick-off order', JSON.stringify(order)===JSON.stringify(want));
  ok('matches are grouped under day headings', (await p.locator('#list h3.gh').count())>=1, (await p.locator('#list h3.gh').allInnerTexts()).join(' | ').slice(0,80));
  // crests
  for (const g of upcoming) { for (const id of [g.home_id,g.away_id]) if (!fs.existsSync(`/home/user/aaryan/site/crests/${id}.png`)) ok(`crest file exists for team ${id}`, false); }
  ok('every club on the list has a crest file', !R.some(r=>r[0]==='FAIL' && /crest file/.test(r[1])));
  await p.evaluate(()=>document.querySelectorAll('img.crest').forEach(i=>{i.loading='eager'})); await p.waitForTimeout(1200);
  const loaded = await p.evaluate(()=>[...document.querySelectorAll('.mrow img.crest')].map(i=>i.complete&&i.naturalWidth>0));
  ok('crest images actually load on the list', loaded.length===2*upcoming.length && loaded.every(Boolean), `${loaded.filter(Boolean).length}/${loaded.length}`);
  // league filter
  const lgs = [...new Set(upcoming.map(g=>g.league))];
  ok('league chips: All + one per competition', (await p.locator('#lg-chips .chip').count())===lgs.length+1, String(await p.locator('#lg-chips .chip').count()));
  for (const lg of lgs) { await p.click(`#lg-chips [data-lg="${lg}"]`); const n = await p.locator('.mrow').count(); const names=new Set(await p.locator('.mrow .mmeta').evaluateAll(e=>e.map(x=>x.lastElementChild.innerText))); ok(`league filter ${lg}`, n===upcoming.filter(g=>g.league===lg).length && names.size===1, `${n} rows, ${[...names].join()}`); }
  await p.click('#lg-chips [data-lg="all"]');
  await p.fill('#q','arsenal'); await p.waitForTimeout(900);
  const ars = await p.locator('.mrow .mname').allInnerTexts(); ok('team search finds Arsenal', ars.length>=1 && ars.some(n=>/Arsenal/.test(n)), ars.join(','));
  await p.fill('#q','zzzz'); await p.waitForTimeout(900); ok('team search with no match says so', /No matches found/.test(await p.locator('#list').innerText()));
  await p.fill('#q',''); await p.waitForTimeout(900);

  // ---------- open a match -> player props ----------
  const withPlayers = upcoming.find(g => DATA.players.filter(x=>x.game===g.id).length>10);
  const idx = upcoming.indexOf(withPlayers);
  await p.locator('.mrow').nth(idx).click(); await p.waitForSelector('.srow');
  ok('tapping a match opens its page (back button, crests, two views)', await p.locator('[data-back]').isVisible() && (await p.locator('.dhead img.crest, .dhead .crest').count())===2 && (await p.locator('button[data-mv]').count())===2);
  ok('match page: list filters are gone, stat chips are inside the page', !(await p.locator('.controls').isVisible()) && (await p.locator('#list [data-stat]').count())===5);
  const plist = DATA.players.filter(x=>x.game===withPlayers.id);
  const cardsN = await p.locator('#list article.card .name').count() - 1;  // first .card is the match header (no .name)
  const names = await p.locator('#list article.card .name').allInnerTexts();
  ok(`shows every player for this match (${plist.length})`, names.length===plist.length, `${names.length}`);
  const teamsWithPlayers = new Set(plist.map(x=>x.team)).size;
  ok(`each team with players has its own crest heading (${teamsWithPlayers})`, (await p.locator('h3.tg').count())===teamsWithPlayers, String(await p.locator('h3.tg').count()));
  const rowsSh = await p.locator('.srow').count(); ok('each player shows all 4 stats', rowsSh===plist.length*4, `${rowsSh}`);
  await p.click(`#list [data-mt=home]`); const nh = await p.locator('#list article.card .name').count(); ok('team filter: home only', nh===plist.filter(x=>x.home).length, String(nh));
  await p.click(`#list [data-mt=away]`); const na = await p.locator('#list article.card .name').count(); ok('team filter: away only', na===plist.filter(x=>!x.home).length, String(na));
  await p.click(`#list [data-mt=all]`);
  await p.click('#list [data-stat=shots]'); ok('stat filter inside the match: Shots only', (await p.locator('.srow').count())===plist.length && (await p.locator('.slabel').allInnerTexts()).every(t=>/shots$/i.test(t)||/^SHOTS$/i.test(t)), String(await p.locator('.srow').count()));
  await p.click('#list [data-stat=all]');
  // type a line + odds on a player inside the match
  const srow = p.locator('.srow').first(); await srow.locator('[data-field=line]').fill('1.5'); await srow.locator('[data-field=odds]').fill('2.4'); await p.waitForTimeout(200);
  ok('props inside a match show an edge when odds are typed', /edge/.test(await srow.locator('.sres').innerText()), (await srow.locator('.sres').innerText()).replace(/\n/g,' '));
  await p.waitForTimeout(900);
  await p.click('button[data-mv=bets]'); await p.waitForSelector('.mk');
  ok('Match bets view shows 4 markets', (await p.locator('.mk').count())===4);
  await p.click('[data-back]'); await p.waitForSelector('.mrow');
  ok('Back returns to the full list', (await p.locator('.mrow').count())===upcoming.length);
  // a match with no player data
  const noP = upcoming.find(g => DATA.players.filter(x=>x.game===g.id).length===0);
  if (noP) { await p.locator('.mrow').nth(upcoming.indexOf(noP)).click(); await p.waitForTimeout(300); ok('match with no player data explains why, bets still there', /No player data/.test(await p.locator('#list').innerText())); await p.click('button[data-mv=bets]'); ok('...and match bets still work', (await p.locator('.mk').count())===4); await p.click('[data-back]'); await p.waitForSelector('.mrow'); }
  ok('list page: "N players" count matches the data', await p.evaluate(([id,n])=>{const r=document.querySelector(`.mrow[data-open="${id}"]`);return r.innerText.includes(n+' players')},[withPlayers.id,plist.length]));

  // ---------- match bets (typed lines + odds), checked against Python afterwards ----------
  async function openBets(i){ if (await p.locator('[data-back]').count()) await p.click('[data-back]'); await p.waitForSelector('.mrow'); await p.locator('.mrow').nth(i).click(); await p.waitForSelector('button[data-mv=bets]'); await p.click('button[data-mv=bets]'); await p.waitForSelector('.mk'); return p.locator('article[data-mcard]'); }
  const combos = [['hcp',-1.5,'home','2.10'],['hcp',0.5,'away','1.40'],['hcp',1,'home','3.0'],['tot',2.5,'over','1.90'],['tot',3,'under','2.2'],['tot',1.5,'over','1.30'],['1x2',null,'home','2.0'],['1x2',null,'away','2.0'],['btts',null,'yes','2.0']];
  for (let i=0;i<combos.length;i++) {
    const c = await openBets(i); const mid = await c.getAttribute('data-mcard'); const [kind,line,sel,odds] = combos[i];
    if (line!==null) { await c.locator(`.mk[data-kind="${kind}"] [data-field=mline]`).fill(String(line)); await p.waitForTimeout(100); }
    await c.locator(`.opt[data-kind="${kind}"][data-sel="${sel}"] [data-field=modds]`).fill(odds); await p.waitForTimeout(100);
    const o = c.locator(`.opt[data-kind="${kind}"][data-sel="${sel}"]`);
    dump.markets.push({mid,kind,line,sel,odds:parseFloat(odds),label:await o.locator('.olab').innerText(),pct:await o.locator('.opct').innerText(),edge:await o.locator('.oedge').innerText()});
    await p.waitForTimeout(800);
  }
  ok('handicap label follows the line (away gets the opposite sign)', /-0\.5/.test(dump.markets[1].label), dump.markets[1].label);
  ok('market inputs never show NaN', (await bad(p))==='', await bad(p));
  { const c0 = await openBets(0); await c0.locator('.mk[data-kind="hcp"] [data-field=mline]').fill('-2.5'); await p.waitForTimeout(200);
    ok('odds typed for another line are cleared when the line changes', (await c0.locator('.opt[data-kind="hcp"][data-sel="home"] [data-field=modds]').inputValue())==='');
    await c0.locator('.mk[data-kind="hcp"] [data-field=mline]').fill('-1.5'); await p.waitForTimeout(200);
    ok('...and come back when the line returns', (await c0.locator('.opt[data-kind="hcp"][data-sel="home"] [data-field=modds]').inputValue())==='2.1'); }
  fs.writeFileSync(process.argv[2]+'/fbdump.json', JSON.stringify(dump));
  await p.waitForTimeout(900); await p.click('[data-back]');

  // ---------- best bets picks up priced matches ----------
  await p.click('button[data-tab=best]'); await p.waitForSelector('h3');
  const h3 = await p.locator('h3').allInnerTexts();
  ok('Best bets shows priced match markets (worth / not worth)', h3.some(t=>/WORTH TAKING|NOT WORTH IT/i.test(t)), h3.slice(0,3).join(' | '));
  ok('Best-bets count is a number', Number.isFinite(parseInt(await p.locator('#n-best').innerText())));
  const nGames = upcoming.length;
  const gopts = await p.locator('#game option').evaluateAll(o=>o.map(x=>[x.value,x.textContent]));
  ok(`game dropdown (props tabs): ${nGames} + All`, gopts.length===nGames+1, String(gopts.length));

  // ---------- outrights ----------
  await p.click('button[data-tab=outrights]'); await p.waitForSelector('.orow');
  ok('controls hidden on Outrights', !(await p.locator('#g-game').isVisible()) && !(await p.locator('#stat-chips').isVisible()) && !(await p.locator('#lg-chips').isVisible()));
  const out = DATA.outrights;
  ok('Outrights has 6 competitions incl. Champions League', (await p.locator('.obar .chip').count())===6 && /Champions League/.test(await p.locator('.obar').innerText()));
  for (const [lg,o] of Object.entries(out)) {
    await p.click(`button[data-ol="${lg}"]`);
    const labels = await p.locator('.seg button[data-om]').allInnerTexts();
    ok(`${o.name}: market buttons match data`, labels.join('|')===o.markets.map(m=>m.label).join('|'), labels.join('|'));
    ok(`${o.name}: every club row has a crest`, (await p.locator('.orow .crest').count())===o.teams.length, `${await p.locator('.orow .crest').count()}/${o.teams.length}`);
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
  ok('Best bets includes the priced outright', (await p.locator('h3').allInnerTexts()).some(t=>/WORTH|NOT WORTH/i.test(t)));

  // ---------- football props on the Most probable tab ----------
  await p.click('button[data-tab=probable]'); await p.waitForSelector('article.card .pct');
  const labs = await p.locator('#stat-chips .chip').allInnerTexts(); ok('football stat chips', labs.join(',')==='All,Shots,Shots on target,Goals,Assists', labs.join(','));
  for (const [stat,label] of [['shots','Shots'],['sot','Shots on target'],['goals','Goals'],['assists','Assists']]) { await p.click(`#stat-chips [data-stat=${stat}]`); const m=await p.locator('article.card .meta').allInnerTexts(); ok(`football ${label} filter`, m.length>0 && m.every(x=>x.startsWith(label)), m[0]); }
  await p.click('#stat-chips [data-stat=all]');
  await p.fill('#min','1.5'); await p.waitForTimeout(1000);
  const bes=(await p.locator('article.card').evaluateAll(cs=>cs.filter(c=>!c.querySelector('[data-field=odds]').value).map(c=>[...c.querySelectorAll('.res .pill')].map(x=>x.textContent).find(t=>t.startsWith('Break-even'))))).map(t=>parseFloat(t.replace('Break-even odds ','')));
  ok('football min odds 1.5: all unpriced props have break-even >= 1.5', bes.length>0 && bes.every(v=>v>=1.49), `n=${bes.length} min=${Math.min(...bes)}`);
  await p.fill('#min',''); await p.waitForTimeout(900);
  for (let i=0;i<4;i++) { const c=p.locator('article.card').nth(i); const base=await c.getAttribute('data-base'); await c.locator('[data-field=line]').fill(['0.5','1.5','0.5','2.5'][i]); await c.locator('[data-field=odds]').fill(['2.0','2.2','1.8','3.0'][i]); await p.waitForTimeout(100);
    dump.props.push({base, line:[0.5,1.5,0.5,2.5][i], odds:[2.0,2.2,1.8,3.0][i], pct:(await c.locator('.pct').innerText()).replace(/\n/g,' '), res:(await c.locator('.res').innerText()).replace(/\n/g,' ')}); }
  fs.writeFileSync(process.argv[2]+'/fbdump.json', JSON.stringify(dump));
  ok('football props: no NaN', (await bad(p))==='', await bad(p));

  // ---------- persistence + switching back ----------
  await p.waitForTimeout(900); await p.reload(); await p.waitForTimeout(1200);
  ok('football selection survives reload', (await p.getAttribute('button[data-sport=football]','aria-pressed'))==='true');
  await p.click('button[data-sport=nba]'); await p.waitForTimeout(900);
  ok('switching back to NBA works', (await p.locator('#tabs .tab').count())===2 && (await p.locator('article.card').count())>0);
  ok('about section changes with the sport', !/Matches:/.test(await p.evaluate(()=>document.querySelector('#about-list').innerText)));

  // ---------- widths, failure of crests / data ----------
  for (const w of [360,390,768,1280]) { const q=await (await b.newContext({viewport:{width:w,height:844}})).newPage(); await q.goto(URL); await q.waitForSelector('.card'); await q.click('button[data-sport=football]'); await q.waitForTimeout(700);
    let overflow=false; for (const t of ['matches','outrights','best','probable']) { await q.click(`button[data-tab=${t}]`); await q.waitForTimeout(250); if (await q.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) overflow=t; if (t==='matches') { await q.locator('.mrow').first().click(); await q.waitForSelector('.dhead'); if (await q.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) overflow='match page'; await q.click('[data-back]'); } }
    ok(`no sideways scroll at ${w}px (football: list, match page, all tabs)`, !overflow, String(overflow)); await q.context().close(); }
  const noCrest = await (await b.newContext({viewport:{width:390,height:844}})).newPage(); await noCrest.route('**/crests/*.png', r=>r.abort()); await noCrest.goto(URL); await noCrest.waitForSelector('.card'); await noCrest.click('button[data-sport=football]'); await noCrest.waitForTimeout(700); await noCrest.click('button[data-tab=matches]'); await noCrest.waitForSelector('.mrow');
  await noCrest.evaluate(()=>document.querySelectorAll('img.crest').forEach(i=>{i.loading='eager'})); await noCrest.waitForTimeout(1200);
  const ph = await noCrest.locator('.mrow .crest.ph').allInnerTexts();
  ok('missing crests fall back to an initials badge (page still fine)', ph.length===2*upcoming.length && ph.every(t=>/^[A-Z0-9]{1,2}$/.test(t)), `${ph.length} badges, e.g. ${ph.slice(0,3).join(',')}`);
  const fail = await (await b.newContext({viewport:{width:390,height:844}})).newPage(); await fail.route('**/predictions_soccer.json', r=>r.abort()); await fail.goto(URL); await fail.waitForSelector('.card'); await fail.click('button[data-sport=football]'); await fail.waitForTimeout(800);
  ok('football load failure shows a clear message', /Could not load the Football predictions/.test(await fail.locator('#list').innerText()));
  for (const [s,n,e] of R) console.log(s,'|',n,e?('| '+e):'');
  console.log('\n'+R.filter(r=>r[0]==='PASS').length+' passed, '+R.filter(r=>r[0]==='FAIL').length+' failed | page errors:', JSON.stringify(errs));
  await b.close();
})();
