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
  ok('NBA list: no league chips / game dropdown, team search shown', !(await p.locator('#lg-chips').isVisible()) && !(await p.locator('#game').isVisible()) && await p.locator('#q').isVisible());
  const wp = rows.map(r => [...r.t.matchAll(/(90%\+|<1%|\d+%)/g)].map(m=>parseInt(m[1])));
  ok('every game shows two win chances that add to 100%', wp.every(a=>a.length===2 && Math.abs(a[0]+a[1]-100)<=1), JSON.stringify(wp.slice(0,3)));
  ok('win chances agree with the model (home favourite when predicted margin > 0)', rows.every((r,i)=>{ const a=[...r.t.matchAll(/(\d+)%/g)].map(m=>+m[1]); const home=a[1]; return (games[i].nba.mu_margin>0.5)?home>50:(games[i].nba.mu_margin<-0.5?home<50:true); }));
  ok('predicted score shown (away - home)', rows.every((r,i)=>r.t.includes(`Predicted ${Math.round(games[i].nba.mu_away)} \u2013 ${Math.round(games[i].nba.mu_home)}`)), rows[0].t.split('\n').filter(x=>/Predicted/.test(x))[0]);
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
  ok('game page: back button, two logos, Player props / Game bets switch', await p.locator('[data-back]').isVisible() && (await p.locator('.dhead .crest').count())===2 && (await p.locator('button[data-mv]').count())===2 && /Game bets/.test(await p.locator('button[data-mv=bets]').innerText()));
  ok('says "at" between the teams, away first', /at/.test(await p.locator('.dvs').innerText()) && (await p.locator('.dteam span').allInnerTexts()).join('|')===[g.away_name,g.home_name].join('|'));
  ok('list filters are hidden inside the game page', !(await p.locator('.controls').isVisible()));
  const plist = DATA.players.filter(x=>x.game===g.id);
  const names = await p.locator('#list article.card .name').allInnerTexts();
  ok(`shows every player for the game (${plist.length})`, names.length===plist.length, String(names.length));
  ok('both teams under their own logo heading', (await p.locator('h3.tg').count())===2);
  ok('each player has 4 stat rows (points, rebounds, assists, threes)', (await p.locator('.srow').count())===plist.length*4);
  ok('every prop row shows its last 5 games and how many beat the line', (await p.locator('.srow .srl5 b').count())===plist.length*4*5 && /\d of 5 (over|under) /.test(await p.locator('.srow .srl5').first().innerText()), (await p.locator('.srow .srl5').first().innerText()).replace(/\n/g,' '));
  { const r = await p.evaluate(()=>{ const row=document.querySelector('.srow'); return { name: row.closest('article.card').querySelector('.name').textContent, label: row.querySelector('.slabel').textContent, vals: [...row.querySelectorAll('.srl5 b')].map(x=>+x.textContent) }; });
    const key = {Points:'pts',Rebounds:'reb',Assists:'ast',Threes:'fg3'}[r.label]; const want = plist.find(x=>x.name===r.name).stats[key].last5;
    ok(`the last-5 values for ${r.name} (${r.label}) are the ones in the data`, JSON.stringify(r.vals)===JSON.stringify(want), JSON.stringify(r.vals)+' vs '+JSON.stringify(want)); }
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
  // ---- game bets (moneyline / spread / total points) ----
  await p.click('button[data-mv=bets]'); await p.waitForSelector('.mk');
  ok('Game bets view has Moneyline, Spread and Total points', (await p.locator('.mk').count())===3 && (await p.locator('.mk-title').evaluateAll(e=>e.map(x=>x.textContent))).join('|')==='Moneyline|Spread|Total points');
  const gm = g.nba;
  ok('spread starts at the model\'s own number', (await p.locator('.mk[data-kind="spr"] [data-field=mline]').inputValue())===String(-(Math.floor(gm.mu_margin)+0.5)), await p.locator('.mk[data-kind="spr"] [data-field=mline]').inputValue());
  ok('total starts at the model\'s own number', (await p.locator('.mk[data-kind="ptot"] [data-field=mline]').inputValue())===String(Math.floor(gm.mu_total)+0.5));
  const mlp = (await p.locator('.opt[data-kind="ml"] .opct').allInnerTexts()).map(x=>parseInt(x)); ok('moneyline chances add to 100%', Math.abs(mlp[0]+mlp[1]-100)<=1, mlp.join('+'));
  ok('spread labels follow the line (away gets the opposite sign)', /\+/.test((await p.locator('.opt[data-kind="spr"] .olab').allInnerTexts())[0]) !== /\+/.test((await p.locator('.opt[data-kind="spr"] .olab').allInnerTexts())[1]) || Number((await p.locator('.mk[data-kind="spr"] [data-field=mline]').inputValue()))===0);
  ok('NBA game bets use points, not goals', /points/.test(await p.locator('.opt[data-kind="ptot"] .olab').first().innerText()) && !/goals/.test(await p.locator('#list').innerText()));
  // type lines + odds in several games and dump them for an independent check against Python
  const dump = [];
  const combos = [['ml',null,'home','1.60'],['spr',-3.5,'home','1.91'],['spr',4,'away','1.95'],['spr',-7,'home','2.2'],['ptot',221.5,'over','1.9'],['ptot',230,'under','1.85'],['ptot',215.5,'over','1.4']];
  for (let i=0;i<combos.length;i++) {
    await p.click('[data-back]'); await p.waitForSelector('.mrow'); await p.locator('.mrow').nth(i % games.length).click(); await p.waitForSelector('button[data-mv=bets]'); await p.click('button[data-mv=bets]'); await p.waitForSelector('.mk');
    const c = p.locator('article[data-mcard]'); const mid = await c.getAttribute('data-mcard'); const [kind,line,sel,odds] = combos[i];
    if (line!==null) { await c.locator(`.mk[data-kind="${kind}"] [data-field=mline]`).fill(String(line)); await p.waitForTimeout(100); }
    await c.locator(`.opt[data-kind="${kind}"][data-sel="${sel}"] [data-field=modds]`).fill(odds); await p.waitForTimeout(100);
    const o = c.locator(`.opt[data-kind="${kind}"][data-sel="${sel}"]`);
    dump.push({mid,kind,line,sel,odds:parseFloat(odds),label:await o.locator('.olab').innerText(),pct:await o.locator('.opct').innerText(),edge:await o.locator('.oedge').innerText()});
    await p.waitForTimeout(800);
  }
  fs.writeFileSync(process.argv[2]+'/nbadump.json', JSON.stringify(dump));
  ok('no NaN in game bets', (await bad(p))==='', await bad(p));
  { await p.click('[data-back]'); await p.waitForSelector('.mrow'); await p.locator('.mrow').nth(0).click(); await p.click('button[data-mv=bets]'); await p.waitForSelector('.mk');
    ok('odds typed for another line are cleared, and return with the line', (await p.locator('.opt[data-kind="ml"][data-sel="home"] [data-field=modds]').inputValue())==='1.6');
    await p.locator('.mk[data-kind="ptot"] [data-field=mline]').fill('300'); await p.waitForTimeout(150); ok('changing the total line clears odds typed for the old line', (await p.locator('.opt[data-kind="ptot"][data-sel="over"] [data-field=modds]').inputValue())===''); }
  await p.waitForTimeout(900);
  await p.click('button[data-tab=best]'); await p.waitForSelector('h3'); const bh = await p.locator('h3').allInnerTexts();
  ok('Best bets shows the priced game markets (worth / not worth)', bh.some(x=>/WORTH TAKING|NOT WORTH IT/i.test(x)), bh.slice(0,2).join(' | '));
  ok('Best bets labels them with team names and says "Change it in Games"', /Change it in Games/.test(await p.locator('#list').innerText()) && /at /.test(await p.locator('#list').innerText()));
  await p.click('button[data-tab=matches]'); await p.waitForSelector('.mrow'); await p.locator('.mrow').nth(gi).click(); await p.waitForSelector('.srow');
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
  const old = await (await b.newContext({viewport:{width:390,height:844}})).newPage(); const oerr=[]; old.on('pageerror',e=>oerr.push(String(e)));
  await old.route('**/predictions.json', r=>r.fulfill({json:{...DATA, games: DATA.games.map(({nba,...g})=>g)}})); await old.goto(URL); await old.waitForSelector('.card'); await old.click('button[data-tab=matches]'); await old.waitForSelector('.mrow');
  await old.locator('.mrow').first().click(); await old.waitForSelector('.srow');
  ok('older data without game numbers still works (no win chances, no Game bets, props fine)', oerr.length===0 && (await old.locator('button[data-mv]').count())===0 && (await old.locator('.srow').count())>0);
  ok('...page errors with older data', oerr.length===0, JSON.stringify(oerr));
  for (const [s,n,e] of R) console.log(s,'|',n,e?('| '+e):'');
  console.log('\n'+R.filter(r=>r[0]==='PASS').length+' passed, '+R.filter(r=>r[0]==='FAIL').length+' failed | page errors:', JSON.stringify(errs));
  await b.close();
})();
