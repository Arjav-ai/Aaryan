require('./_setup');
const { chromium } = require('playwright');
const fs = require('fs');
const URL = 'http://localhost:8765/index.html';
const R = []; const ok = (n, c, x='') => R.push([c?'PASS':'FAIL', n, x]);
const NBA = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions.json','utf8'));
const FB = JSON.parse(fs.readFileSync('/home/user/aaryan/data/predictions_soccer.json','utf8'));
const LEDGER_PATH = 'data/users/u1/ledger';
const FAKE = (opts) => `
  window.__store = JSON.parse(sessionStorage.getItem('__fakeStore')||'null') || ${JSON.stringify(opts.store||{})}; window.__fail = ${JSON.stringify(!!opts.failWrite)}; window.__writes = 0;
  window.claude = { use: async n => {
    if (n==='user') return ${opts.db?'{ id: async () => "u1" }':'null'};
    if (n==='db') return ${opts.db?`{ doc: p => ({ get: async () => ({ exists: p in window.__store, data: () => JSON.parse(JSON.stringify(window.__store[p]||{})) }),
        set: async d => { if (window.__fail) throw {code:'invalid_argument'}; window.__writes++; window.__store[p] = JSON.parse(JSON.stringify(d)); sessionStorage.setItem('__fakeStore', JSON.stringify(window.__store)); } }) }`:'null'};
    return null; } };`;
async function open(b, o={}) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } }); const p = await ctx.newPage(); p.errs=[];
  p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => { if (m.type()==='error') p.errs.push(m.text()); });
  if (o.claude!==false) await p.addInitScript(FAKE(o));
  if (o.results) await p.route('**/results.json', r => r.fulfill({ json: o.results }));
  if (o.noResults) await p.route('**/results.json', r => r.abort());
  await p.goto(URL); await p.waitForSelector('.card'); await p.waitForTimeout(500); return p;
}
const store = p => p.evaluate(p0 => window.__store, null);
const tile = async p => (await p.locator('.tile b').allInnerTexts());
(async () => {
  const b = await chromium.launch();

  // ================= tracking through the real screens =================
  let p = await open(b, { db: true, results: { generated_at: new Date().toISOString(), days: 21, nba_stats:['pts','reb','ast','fg3'], football_stats:['shots','sot','goals','assists'], nba:[], football:[] } });
  ok('Record button visible', await p.locator('#recbtn').isVisible());
  await p.click('#recbtn'); ok('empty Record page explains how to track', /Nothing tracked yet/.test(await p.locator('#list').innerText()) && (await p.locator('.tab[aria-selected=true]').count())===0);
  await p.click('#recbtn'); ok('Record button toggles back to the tabs', await p.locator('#tabs').isVisible());
  const g = NBA.games.filter(x=>Date.parse(x.start)>Date.now())[0];
  await p.click('button[data-tab=matches]'); await p.waitForSelector('.mrow[data-open]'); await p.locator('.mrow[data-open]').first().click(); await p.waitForSelector('.srow');
  const row = p.locator('.srow').first(); ok('no Track button before odds are typed', (await row.locator('.trk').count())===0);
  await row.locator('[data-field=line]').fill('20.5'); await row.locator('[data-field=odds]').fill('2.0'); await p.waitForTimeout(250);
  ok('Track button appears once odds are typed', (await row.locator('.trk').count())===1 && /Track bet/.test(await row.locator('.trk').innerText()));
  await row.locator('.trk').click(); await p.waitForTimeout(300);
  ok('tapping it shows Tracked and disables the button', /Tracked/.test(await row.locator('.trk').innerText()) && await row.locator('.trk').isDisabled());
  let led = (await store(p))[LEDGER_PATH];
  ok('the bet is saved to the private account document', led && led.bets.length===1 && led.bets[0].ty==='prop' && led.bets[0].od===2 && led.bets[0].ln===20.5 && led.bets[0].gk===`${g.date}|${g.home}` && led.bets[0].sp==='nba', JSON.stringify(led&&led.bets[0]));
  ok('saved chance is the displayed (capped) chance, and the raw one is kept', led.bets[0].p<=0.9 && led.bets[0].pr>0 && led.bets[0].pr>=led.bets[0].p-1e-9);
  // game bets on the same game
  await p.click('button[data-mv=bets]'); await p.waitForSelector('.mk');
  await p.locator('.opt[data-kind="ml"][data-sel="home"] [data-field=modds]').fill('1.8'); await p.waitForTimeout(200);
  await p.locator('.opt[data-kind="ml"][data-sel="home"] .trk').click();
  await p.locator('.mk[data-kind="spr"] [data-field=mline]').fill('-4.5'); await p.locator('.opt[data-kind="spr"][data-sel="home"] [data-field=modds]').fill('1.95'); await p.waitForTimeout(200); await p.locator('.opt[data-kind="spr"][data-sel="home"] .trk').click();
  await p.locator('.mk[data-kind="ptot"] [data-field=mline]').fill('221.5'); await p.locator('.opt[data-kind="ptot"][data-sel="over"] [data-field=modds]').fill('1.9'); await p.waitForTimeout(200); await p.locator('.opt[data-kind="ptot"][data-sel="over"] .trk').click(); await p.waitForTimeout(400);
  led = (await store(p))[LEDGER_PATH];
  ok('game bets are tracked too (moneyline, spread, total) with their lines', led.bets.length===4 && led.bets.filter(x=>x.ty==='game').map(x=>x.kd+':'+x.se+':'+x.ln).sort().join()==='ml:home:null,ptot:over:221.5,spr:home:-4.5', led.bets.map(x=>x.kd||x.ty).join());
  await p.locator('.opt[data-kind="ml"][data-sel="home"] [data-field=modds]').fill('1.85'); await p.waitForTimeout(250);
  ok('changing the odds after tracking offers a new Track button', /Track bet/.test(await p.locator('.opt[data-kind="ml"][data-sel="home"] .trk').innerText()) && !(await p.locator('.opt[data-kind="ml"][data-sel="home"] .trk').isDisabled()));
  await p.locator('.opt[data-kind="ml"][data-sel="home"] .trk').click(); await p.waitForTimeout(300);
  ok('...and a second entry, not a replacement', (await store(p))[LEDGER_PATH].bets.length===5);
  await p.locator('.opt[data-kind="ml"][data-sel="home"] .trk').click({force:true}).catch(()=>{}); await p.waitForTimeout(200);
  ok('tapping a tracked bet again does not duplicate it', (await store(p))[LEDGER_PATH].bets.length===5);
  // football + outright
  await p.click('button[data-sport=football]'); await p.waitForTimeout(900); await p.click('button[data-tab=outrights]'); await p.waitForSelector('.orow');
  await p.locator('.orow').first().locator('[data-field=oodds]').fill('2.5'); await p.waitForTimeout(250); await p.locator('.orow').first().locator('.trk').click(); await p.waitForTimeout(300);
  led = (await store(p))[LEDGER_PATH]; ok('an outright can be tracked and is kept open', led.bets.length===6 && led.bets[5].ty==='outright' && !!led.bets[5].lab);
  await p.click('#recbtn'); await p.waitForTimeout(300);
  const txt = await p.locator('#list').innerText();
  ok('Record page lists the 6 bets as waiting / open', (await p.locator('.brow').count())===6 && /Waiting/.test(txt) && /Open/.test(txt), (await p.locator('.tile b').allInnerTexts()).join('|'));
  ok('says the record is saved to the Claude account', /Saved privately to your Claude account/.test(txt));
  await p.reload(); await p.waitForSelector('.card'); await p.waitForTimeout(600); await p.click('#recbtn'); await p.waitForTimeout(300);
  ok('the record survives a reload (loaded back from the account document)', (await p.locator('.brow').count())===6);
  await p.locator('.del').first().click(); await p.waitForTimeout(300);
  ok('Remove deletes a bet and saves it', (await p.locator('.brow').count())===5 && (await store(p))[LEDGER_PATH].bets.length===5);
  ok('no page errors while tracking', p.errs.length===0, JSON.stringify(p.errs));

  // ================= settling against known results =================
  const now = Date.now(), old = now - 30*864e5;
  const bet = (o) => ({ t: now-864e5, sp:'nba', ty:'prop', ln:null, p:.5, pr:.5, pp:0, lab:'x', gl:'g', od:2, ...o, id: Math.random().toString(36).slice(2) });
  const NK='2026-11-20|AAA', FK='9001';
  const bets = [
    bet({gk:NK,pl:'Alice',st:'pts',sd:'over', ln:24.5,od:1.9,p:.6,pr:.6,lab:'Alice over 24.5 points'}),      // 25 -> won +0.9
    bet({gk:NK,pl:'Alice',st:'pts',sd:'under',ln:24.5,od:1.9,p:.4,pr:.4}),                                    // lost -1
    bet({gk:NK,pl:'Alice',st:'pts',sd:'over', ln:25,  od:2.0,p:.45,pr:.45,pp:.05}),                           // push 0
    bet({gk:NK,pl:'Nobody',st:'reb',sd:'over',ln:3.5, od:2.0}),                                               // void
    bet({gk:NK,ty:'game',kd:'ml', se:'home',od:1.5,p:.7,pr:.7}),                                              // won +0.5
    bet({gk:NK,ty:'game',kd:'ml', se:'away',od:3.0,p:.3,pr:.3}),                                              // lost -1
    bet({gk:NK,ty:'game',kd:'spr',se:'home',ln:-10,  od:1.9,p:.48,pr:.48,pp:.04}),                            // margin 10 -> push
    bet({gk:NK,ty:'game',kd:'spr',se:'home',ln:-9.5, od:1.9,p:.52,pr:.52}),                                   // won +0.9
    bet({gk:NK,ty:'game',kd:'spr',se:'away',ln:-10.5,od:1.9,p:.48,pr:.48}),                                   // away +10.5 -> won +0.9
    bet({gk:NK,ty:'game',kd:'ptot',se:'over', ln:210,  od:1.9,p:.5,pr:.5,pp:.03}),                            // total 210 -> push
    bet({gk:NK,ty:'game',kd:'ptot',se:'under',ln:215.5,od:1.9,p:.55,pr:.55}),                                 // won +0.9
    bet({sp:'football',gk:FK,ty:'game',kd:'1x2',se:'home',od:2.0,p:.5,pr:.5}),                                // 2-1 home -> won +1
    bet({sp:'football',gk:FK,ty:'game',kd:'1x2',se:'draw',od:3.4,p:.25,pr:.25}),                              // lost -1
    bet({sp:'football',gk:FK,ty:'game',kd:'hcp',se:'home',ln:-1.5,od:2.6,p:.3,pr:.3}),                        // 1-1.5 -> lost
    bet({sp:'football',gk:FK,ty:'game',kd:'hcp',se:'away',ln:-1.5,od:1.5,p:.7,pr:.7}),                        // away +1.5 -> won +0.5
    bet({sp:'football',gk:FK,ty:'game',kd:'tot',se:'over',ln:2.5,od:1.8,p:.55,pr:.55}),                       // 3 goals -> won +0.8
    bet({sp:'football',gk:FK,ty:'game',kd:'btts',se:'yes',od:1.7,p:.58,pr:.58}),                              // won +0.7
    bet({sp:'football',gk:FK,pl:'Cara',st:'shots',sd:'over',ln:1.5,od:2.2,p:.4,pr:.4}),                       // 3 shots -> won +1.2
    bet({sp:'football',gk:FK,pl:'Cara',st:'goals',sd:'over',ln:0.5,od:3.0,p:.3,pr:.3}),                       // 0 goals -> lost
    bet({ty:'outright',od:4,p:.2,pr:.2}),                                                                       // open
    bet({gk:'2099-01-01|ZZZ',pl:'Z',st:'pts',sd:'over',ln:9.5,od:2.0,t:now-3600e3}),                          // game not in results yet -> waiting
    bet({gk:'2026-01-01|OLD',pl:'Z',st:'pts',sd:'over',ln:9.5,od:2.0,t:old}),                                  // too old to find a result
  ];
  const results = { generated_at: new Date().toISOString(), days: 21, nba_stats:['pts','reb','ast','fg3'], football_stats:['shots','sot','goals','assists'],
    nba:[{key:NK,home:'AAA',away:'BBB',home_pts:110,away_pts:100,players:{Alice:[25,8,5,3]}}],
    football:[{key:FK,home:'H',away:'A',home_goals:2,away_goals:1,players:{Cara:[3,1,0,0]}}] };
  const exp = { won:[0.9,0.5,0.9,0.9,0.9,1,0.5,0.8,0.7,1.2].length, lost:0 };
  // expected by hand
  const W=[1.9-1,1.5-1,1.9-1,1.9-1,1.9-1,2.0-1,1.5-1,1.8-1,1.7-1,2.2-1]; // won: Alice o24.5, ML home, spr -9.5, away +10.5, under 215.5, 1x2 home, hcp away, tot, btts, shots
  const nWon=W.length, nLost=6, nPush=3, nVoid=1; // lost: Alice u24.5, ML away, 1x2 draw, hcp home, goals o0.5 + ... (counted below)
  p = await open(b, { db: true, store: { [LEDGER_PATH]: { v:1, bets } }, results });
  await p.click('#recbtn'); await p.waitForTimeout(400);
  const items = await p.locator('.brow').evaluateAll(rs => rs.map(r => ({ lab: r.querySelector('.name').innerText, res: r.querySelector('.bres').innerText })));
  const count = k => items.filter(i => i.res.startsWith(k)).length;
  ok('won / lost / push / void / open / waiting / no-result counts are right', count('Won')===10 && count('Lost')===5 && count('Push')===3 && count('Void')===1 && count('Open')===1 && count('Waiting')===1 && count('No result')===1, JSON.stringify({won:count('Won'),lost:count('Lost'),push:count('Push'),void:count('Void'),open:count('Open'),wait:count('Waiting'),old:count('No result')}));
  const settledN = 10+5+3, profit = W.reduce((a,x)=>a+x,0) - 5;
  const tiles = await tile(p);
  ok(`tile: ${settledN} settled`, tiles[0]===String(settledN), tiles.join('|'));
  ok(`tile: profit ${profit.toFixed(2)} units`, tiles[1]===(profit>=0?'+':'−')+Math.abs(profit).toFixed(2), tiles[1]+' vs '+profit.toFixed(2));
  const roi = profit/15*100; ok(`tile: return per bet ${roi.toFixed(1)}%`, tiles[2]===(roi>=0?'+':'−')+Math.abs(roi).toFixed(1)+'%', tiles[2]);
  // expected by the model: sum over won/lost/push of p*od + pp - 1
  const settled = bets.filter((x,i)=>true);
  const outcome = ['won','lost','push','void','won','lost','push','won','won','push','won','won','lost','lost','won','won','won','won','lost','open','wait','old'];
  let E=0; bets.forEach((x,i)=>{ if (['won','lost','push'].includes(outcome[i])) E += x.p*x.od + x.pp - 1; });
  ok(`"model expected" figure is ${E.toFixed(2)} units`, new RegExp('What the model expected:</strong>|What the model expected:').test(await p.locator('#list').innerText()) && (await p.locator('#list').innerText()).includes('from these bets') && (await p.locator('#list').innerText()).includes((E>=0?'+':'−')+Math.abs(E).toFixed(2)+' units'), (await p.locator('.meta').allInnerTexts()).filter(t=>/expected/.test(t))[0]);
  ok('says a run of 18 bets is mostly luck', /only 18 settled bets/.test(await p.locator('#list').innerText()));
  const cal = await p.locator('.ctab').evaluate(e=>e.textContent); ok('calibration table is shown', /Model said/.test(cal));
  // recompute calibration buckets by hand
  const B=[[0,.3],[.3,.45],[.45,.6],[.6,.75],[.75,1.01]]; const lines=[];
  B.forEach(([lo,hi],k)=>{ const xs=bets.map((x,i)=>({x,o:outcome[i]})).filter(z=>['won','lost'].includes(z.o) && z.x.pr>=lo && z.x.pr<hi); if(xs.length) lines.push(`${xs.length}|${Math.round(xs.reduce((a,z)=>a+z.x.pr,0)/xs.length*100)}%|${Math.round(xs.filter(z=>z.o==='won').length/xs.length*100)}%`); });
  const calCells = await p.locator('.ctab span:not(.h)').allInnerTexts(); const got=[]; for (let i=0;i<calCells.length;i+=4) got.push(`${calCells[i+1]}|${calCells[i+2]}|${calCells[i+3]}`);
  ok('calibration buckets match a hand calculation', JSON.stringify(got)===JSON.stringify(lines), JSON.stringify(got)+' vs '+JSON.stringify(lines));
  ok('each settled bet shows what happened (final score / stat)', (await p.locator('#list').innerText()).includes('final 100 – 110') && (await p.locator('#list').innerText()).includes('finished with 25') && (await p.locator('#list').innerText()).includes('final 2 – 1') && (await p.locator('#list').innerText()).includes('did not play'));
  ok('no NaN / undefined on the Record page', !/NaN|undefined|Infinity/.test(await p.locator('#list').innerText()));
  ok('no page errors settling', p.errs.length===0, JSON.stringify(p.errs));

  // ================= storage fallbacks and failures =================
  p = await open(b, { claude: false, results });
  await p.click('button[data-tab=matches]'); await p.waitForSelector('.mrow[data-open]'); await p.locator('.mrow[data-open]').first().click(); await p.waitForSelector('.srow');
  const r2 = p.locator('.srow').first(); await r2.locator('[data-field=line]').fill('15.5'); await r2.locator('[data-field=odds]').fill('1.9'); await p.waitForTimeout(250); await r2.locator('.trk').click(); await p.waitForTimeout(300);
  ok('without a Claude account store, tracking still works on this device', (await p.evaluate(()=>JSON.parse(localStorage.getItem('propfinder-ledger')||'[]'))).length===1);
  await p.click('#recbtn'); await p.waitForTimeout(300); ok('...and says so', /Saved on this device only/.test(await p.locator('#list').innerText()));
  await p.reload(); await p.waitForSelector('#list > *'); await p.waitForTimeout(700); await p.click('#recbtn'); await p.waitForTimeout(300); ok('...and keeps it after a reload', (await p.locator('.brow').count())===1);
  p = await open(b, { db: true, failWrite: true, results });
  await p.click('button[data-tab=matches]'); await p.waitForSelector('.mrow[data-open]'); await p.locator('.mrow[data-open]').first().click(); await p.waitForSelector('.srow');
  const r3 = p.locator('.srow').first(); await r3.locator('[data-field=line]').fill('15.5'); await r3.locator('[data-field=odds]').fill('1.9'); await p.waitForTimeout(250); await r3.locator('.trk').click(); await p.waitForTimeout(500);
  await p.click('#recbtn'); await p.waitForTimeout(300);
  ok('if the account store refuses a write, the bet is kept on the device and the page says so', (await p.locator('.brow').count())===1 && /Saved on this device only/.test(await p.locator('#list').innerText()) && p.errs.length===0, JSON.stringify(p.errs));
  p = await open(b, { db: true, store: { [LEDGER_PATH]: { v:1, bets: bets.slice(0,3) } }, noResults: true });
  await p.click('#recbtn'); await p.waitForTimeout(400);
  ok('if results cannot be loaded, bets simply wait (no errors)', (await p.locator('.brow').count())===3 && /Waiting/.test(await p.locator('#list').innerText()) && p.errs.filter(e=>!/results\.json|ERR_FAILED|Failed to load resource/.test(e)).length===0, JSON.stringify(p.errs));
  for (const w of [360,390,768,1280]) { const q=await (await b.newContext({viewport:{width:w,height:844}})).newPage(); await q.addInitScript(FAKE({db:true,store:{[LEDGER_PATH]:{v:1,bets}}})); await q.route('**/results.json', r=>r.fulfill({json:results})); await q.goto(URL); await q.waitForSelector('.card'); await q.waitForTimeout(500); await q.click('#recbtn'); await q.waitForSelector('.brow'); ok(`no sideways scroll on the Record page at ${w}px`, !(await q.evaluate(()=>document.documentElement.scrollWidth>innerWidth))); if (w===390) await q.screenshot({path:process.argv[2]+'/record.png', fullPage:false}); await q.context().close(); }
  for (const [s,n,e] of R) console.log(s,'|',n,e?('| '+e):'');
  console.log('\n'+R.filter(r=>r[0]==='PASS').length+' passed, '+R.filter(r=>r[0]==='FAIL').length+' failed');
  await b.close();
})().catch(e=>{ for (const [s,n,x] of R) console.log(s,'|',n,x?('| '+x):''); console.log('CRASH:',String(e).split('\n')[0]); process.exit(1); });
