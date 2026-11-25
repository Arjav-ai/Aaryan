const { chromium } = require('playwright');
const fs = require('fs');
const URL = 'http://localhost:8765/index.html';
const R = []; const ok = (n, c, x='') => R.push([c?'PASS':'FAIL', n, x]);
const DATA = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions.json','utf8'));
const games = DATA.games.filter(g => Date.parse(g.start) > Date.now());
const bad = async p => { const t = await p.locator('body').innerText(); const m = t.match(/.{0,30}(NaN|undefined|Infinity|null).{0,30}/); return m ? m[0] : ''; };
const outsOf = (g, home) => [...new Set(DATA.players.filter(p => p.game===g.id && p.home===home).flatMap(p => p.teammates_out||[]))];
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } });
  const p = await ctx.newPage(); const errs = [];
  p.on('pageerror', e => errs.push(String(e))); p.on('console', m => { if (m.type()==='error') errs.push(m.text()); });
  await p.goto(URL); await p.waitForSelector('.card');
  const tabs = await p.locator('#tabs .tab').allInnerTexts();
  ok('NBA tabs: Games / Best bets / Most probable', tabs.length===3 && /Games/.test(tabs[0]) && /Best bets/.test(tabs[1]) && /Most probable/.test(tabs[2]), tabs.join('|'));

  // ---- games list ----
  await p.click('button[data-tab=matches]'); await p.waitForSelector('.mrow');
  const rows = await p.locator('.mrow').evaluateAll(rs => rs.map(r => ({ id: r.dataset.open, t: r.innerText, names: [...r.querySelectorAll('.mname')].map(x=>x.innerText) })));
  ok(`${games.length} upcoming games listed, in tip-off order`, JSON.stringify(rows.map(r=>r.id))===JSON.stringify(games.map(g=>g.id)), String(rows.length));
  ok('away team listed first, with full team names', rows.every((r,i)=>r.names[0]===games[i].away_name && r.names[1]===games[i].home_name), rows[0].names.join(' / '));
  ok('NBA list has no win percentages (there is no game model) and no league chips / game dropdown', !rows.some(r=>/%/.test(r.t)) && !(await p.locator('#lg-chips').isVisible()) && !(await p.locator('#game').isVisible()) && await p.locator('#q').isVisible());
  ok('games are grouped under day headings', (await p.locator('#list h3.gh').count())>=1);
  ok('each row shows its player count and ruled-out count from the data', rows.every((r,i)=>{ const n=DATA.players.filter(x=>x.game===games[i].id).length; const o=outsOf(games[i],true).length+outsOf(games[i],false).length; return r.t.includes(n+' players') && (o?r.t.includes(o+' ruled out'):r.t.includes('No one ruled out')); }));
  for (const g of games) for (const c of [g.home,g.away]) if (!fs.existsSync(`/home/user/aaryan/site/crests/nba/${c}.png`)) ok(`logo file exists for ${c}`, false);
  ok('every team on the list has a logo file', !R.some(r=>r[0]==='FAIL'&&/logo file/.test(r[1])));
  await p.evaluate(()=>document.querySelectorAll('img.crest').forEach(i=>{i.loading='eager'})); await p.waitForTimeout(1200);
  const loaded = await p.evaluate(()=>[...document.querySelectorAll('.mrow img.crest')].map(i=>i.complete&&i.naturalWidth>0));
  ok('logos actually load', loaded.length===2*games.length && loaded.every(Boolean), `${loaded.filter(Boolean).length}/${loaded.length}`);
  await p.fill('#q','miami'); await p.waitForTimeout(900);
  const found = await p.locator('.mrow').count(); ok('team search by name finds the game', found===games.filter(g=>/miami/i.test(g.home_name+g.away_name)).length && found>=0, String(found));
  await p.fill('#q','PHI'); await p.waitForTimeout(900); ok('team search by code works too (matches anywhere in the name or code)', (await p.locator('.mrow').count())===games.filter(g=>(g.home_name+g.away_name+g.home+g.away).toLowerCase().includes('phi')).length && (await p.locator('.mrow').count())>=1);
  await p.fill('#q','zzzz'); await p.waitForTimeout(900); ok('no match says "No games found"', /No games found/.test(await p.locator('#list').innerText()));
  await p.fill('#q',''); await p.waitForTimeout(900);

  // ---- a game page ----
  const idx = games.findIndex(g => DATA.players.filter(x=>x.game===g.id).length>10 && (outsOf(g,true).length+outsOf(g,false).length)>0);
  const gi = idx>=0 ? idx : 0, g = games[gi];
  await p.locator('.mrow').nth(gi).click(); await p.waitForSelector('.srow');
  ok('game page: back button, two logos, no Match bets switch (NBA has props only)', await p.locator('[data-back]').isVisible() && (await p.locator('.dhead .crest').count())===2 && (await p.locator('button[data-mv]').count())===0);
  ok('says "at" between the teams, away first', /at/.test(await p.locator('.dvs').innerText()) && (await p.locator('.dteam span').allInnerTexts()).join('|')===[g.away_name,g.home_name].join('|'));
  ok('list filters are hidden inside the game page', !(await p.locator('.controls').isVisible()));
  const plist = DATA.players.filter(x=>x.game===g.id);
  const names = await p.locator('#list article.card .name').allInnerTexts();
  ok(`shows every player for the game (${plist.length})`, names.length===plist.length, String(names.length));
  ok('both teams under their own logo heading', (await p.locator('h3.tg').count())===2);
  ok('each player has 4 stat rows (points, rebounds, assists, threes)', (await p.locator('.srow').count())===plist.length*4);
  const order = await p.locator('h3.tg').allInnerTexts(); ok('away team group comes first', order[0].startsWith(g.away_name) && order[1].startsWith(g.home_name), order.join(' | '));
  const minsAway = await p.evaluate(()=>{ const hs=[...document.querySelectorAll('#list > *')]; const out=[]; let cur=null; for (const el of hs){ if (el.matches('h3.tg')) { cur=[]; out.push(cur);} else if (cur && el.matches('article.card')) { const m=/about (\d+) min/.exec(el.querySelector('.meta').innerText); cur.push(m?+m[1]:0);} } return out; });
  ok('players are ordered by minutes within each team', minsAway.every(a=>a.every((v,i)=>i===0||a[i-1]>=v)), JSON.stringify(minsAway.map(a=>a.slice(0,4))));
  const o1 = outsOf(g,false), o2 = outsOf(g,true);
  const notices = await p.locator('.notice').allInnerTexts();
  ok('ruled-out players are shown for each team that has some', (o1.length?notices.some(t=>t.includes('Ruled out for '+g.away_name) && o1.every(n=>t.includes(n))):true) && (o2.length?notices.some(t=>t.includes('Ruled out for '+g.home_name) && o2.every(n=>t.includes(n))):true), notices.map(t=>t.slice(0,60)).join(' || '));
  await p.click('#list [data-mt=home]'); ok('team filter: home only', (await p.locator('#list article.card .name').count())===plist.filter(x=>x.home).length);
  await p.click('#list [data-mt=away]'); ok('team filter: away only', (await p.locator('#list article.card .name').count())===plist.filter(x=>!x.home).length);
  await p.click('#list [data-mt=all]');
  await p.click('#list [data-stat=pts]'); ok('stat filter inside the game: Points only', (await p.locator('.srow').count())===plist.length && (await p.locator('.slabel').allInnerTexts()).every(t=>/^points$/i.test(t)));
  await p.click('#list [data-stat=all]');
  const sr = p.locator('.srow').first(); await sr.locator('[data-field=line]').fill('20.5'); await sr.locator('[data-field=odds]').fill('2.1'); await p.waitForTimeout(250);
  const first = await p.locator('#list article.card .name').first().innerText();
  ok('typing a line and odds shows an edge', /edge/.test(await sr.locator('.sres').innerText()), (await sr.locator('.sres').innerText()).replace(/\n/g,' '));
  await p.waitForTimeout(900); ok('no NaN in the game page', (await bad(p))==='');
  await p.click('[data-back]'); await p.waitForSelector('.mrow'); ok('Back returns to the full list', (await p.locator('.mrow').count())===games.length);
  // the priced prop shows in Best bets
  await p.click('button[data-tab=best]'); await p.waitForSelector('h3'); ok('the prop priced inside the game appears in Best bets', (await p.locator('#list').innerText()).includes(first), first);
  // Games tab and the other tabs coexist
  await p.click('button[data-tab=probable]'); await p.waitForSelector('article.card .pct'); ok('Most probable still works', (await p.locator('article.card').count())>0);
  await p.click('button[data-tab=matches]'); await p.waitForSelector('.mrow'); ok('Games tab opens on the list (not a stale game page)', (await p.locator('[data-back]').count())===0);

  // ---- switching sport lands on that sport's first tab ----
  await p.click('button[data-sport=football]'); await p.waitForTimeout(900);
  ok('switching to Football lands on Matches', (await p.getAttribute('button[data-tab=matches]','aria-selected'))==='true' && (await p.locator('.mrow').count())>0 && (await p.locator('#lg-chips').isVisible()));
  await p.click('button[data-sport=nba]'); await p.waitForTimeout(900);
  ok('switching back to NBA lands on Games', (await p.getAttribute('button[data-tab=matches]','aria-selected'))==='true' && (await p.locator('.mrow').count())===games.length && !(await p.locator('#lg-chips').isVisible()));
  ok('NBA about text unchanged by football', /Tested on past games/.test(await p.evaluate(()=>document.querySelector('#about-list').textContent)));

  // ---- layout, missing logos, empty week ----
  for (const w of [360,390,768,1280]) { const q=await (await b.newContext({viewport:{width:w,height:844}})).newPage(); await q.goto(URL); await q.waitForSelector('.card'); await q.click('button[data-tab=matches]'); await q.waitForSelector('.mrow'); let o=await q.evaluate(()=>document.documentElement.scrollWidth>innerWidth); await q.locator('.mrow').first().click(); await q.waitForSelector('.dhead'); o = o || await q.evaluate(()=>document.documentElement.scrollWidth>innerWidth); ok(`no sideways scroll at ${w}px (NBA list and game page)`, !o); await q.context().close(); }
  const nl = await (await b.newContext({viewport:{width:390,height:844}})).newPage(); await nl.route('**/crests/nba/*.png', r=>r.abort()); await nl.goto(URL); await nl.waitForSelector('.card'); await nl.click('button[data-tab=matches]'); await nl.waitForSelector('.mrow'); await nl.evaluate(()=>document.querySelectorAll('img.crest').forEach(i=>{i.loading='eager'})); await nl.waitForTimeout(1200);
  const ph = await nl.locator('.mrow .crest.ph').allInnerTexts(); ok('missing logos fall back to initials badges', ph.length===2*games.length && ph.every(t=>/^[A-Z0-9]{1,2}$/.test(t)), `${ph.length}: ${ph.slice(0,4).join(',')}`);
  const empty = await (await b.newContext({viewport:{width:390,height:844}})).newPage(); await empty.route('**/predictions.json', r=>r.fulfill({json:{...DATA, games:[], players:[]}})); await empty.goto(URL); await empty.waitForTimeout(900); await empty.click('button[data-tab=matches]'); await empty.waitForTimeout(300);
  ok('an empty week says there are no upcoming games', /No upcoming games right now/.test(await empty.locator('#list').innerText()));
  for (const [s,n,e] of R) console.log(s,'|',n,e?('| '+e):'');
  console.log('\n'+R.filter(r=>r[0]==='PASS').length+' passed, '+R.filter(r=>r[0]==='FAIL').length+' failed | page errors:', JSON.stringify(errs));
  await b.close();
})();
