require('./_setup');
const { chromium } = require('playwright'); const R=[]; const ok=(n,c,x='')=>R.push([c?'PASS':'FAIL',n,x]);
(async()=>{const b=await chromium.launch(); const ctx=await b.newContext({viewport:{width:393,height:852},deviceScaleFactor:2}); const p=await ctx.newPage();
 await p.goto('http://localhost:8765/ios.html'); await p.waitForSelector('.card');
 // stand-in for the Claude app's floating buttons, positions taken from the owner's screenshot (css px)
 await p.evaluate(()=>{ for (const [l,w] of [[14,44],[225,150]]) { const d=document.createElement('div'); d.className='fake-ui'; d.style.cssText=`position:fixed;left:${l}px;top:55px;width:${w}px;height:39px;border-radius:20px;background:rgba(60,60,60,.6);z-index:999;pointer-events:none`; document.body.appendChild(d); } });
 const hit = async sel => p.evaluate(s=>{ const ui=[...document.querySelectorAll('.fake-ui')].map(e=>e.getBoundingClientRect()); const els=[...document.querySelectorAll(s)]; return els.some(e=>{const r=e.getBoundingClientRect(); return r.width&&r.height&&ui.some(u=>!(r.right<=u.left||r.left>=u.right||r.bottom<=u.top||r.top>=u.bottom));}); }, sel);
 const clear = async () => { const bad=[]; for (const s of ['h1','.sports','.tab','.statusrow','.top']) if (await hit(s)) bad.push(s); return bad; };
 ok('at the top: title, sport chips and tabs are clear of the floating buttons', (await clear()).length===0, (await clear()).join(','));
 const g = await p.evaluate(()=>({card:document.querySelector('.card').getBoundingClientRect().left, right:innerWidth-document.querySelector('.card').getBoundingClientRect().right, h1:document.querySelector('h1').getBoundingClientRect().top, docW:document.documentElement.scrollWidth}));
 ok('side gutters are 16px on both sides', g.card===16 && Math.abs(g.right-16)<0.5 && g.docW<=393, JSON.stringify(g));
 await p.evaluate(()=>window.scrollTo(0,900)); await p.waitForTimeout(300);
 const top = await p.evaluate(()=>document.querySelector('.top').getBoundingClientRect().top);
 ok('after scrolling, the sticky header stops below the floating buttons', top>=94, 'header top = '+top);
 ok('after scrolling, nothing in the header sits under the buttons', (await clear()).length===0, (await clear()).join(','));
 const hh = await p.evaluate(()=>document.querySelector('.top').getBoundingClientRect().height);
 ok('sticky header is compact (under 120px)', hh<120, 'height = '+Math.round(hh));
 await p.screenshot({path:process.argv[2]+'/ios_scrolled.png'});
 await p.evaluate(()=>window.scrollTo(0,0)); await p.waitForTimeout(200); await p.screenshot({path:process.argv[2]+'/ios_top.png'});
 for (const w of [360,375,430]) { const q=await (await b.newContext({viewport:{width:w,height:800}})).newPage(); await q.goto('http://localhost:8765/ios.html'); await q.waitForSelector('.card'); ok(`no sideways scroll at ${w}px`, !(await q.evaluate(()=>document.documentElement.scrollWidth>innerWidth))); await q.context().close(); }
 for (const [s,n,e] of R) console.log(s,'|',n,e?('| '+e):''); await b.close();})();
