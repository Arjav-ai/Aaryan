// Required first by every end-to-end test: each new browser context behaves like a returning user
// (intro already dismissed, "More filters" panel open, last visit ended on Most probable) so the tests can reach every control directly.
// A test that wants the first-visit experience passes { firstVisit: true } as a context option.
const { chromium } = require('playwright');
const launch = chromium.launch.bind(chromium);
chromium.launch = async (o) => {
  const b = await launch(o); const nc = b.newContext.bind(b);
  b.newContext = async (opts = {}) => {
    const { firstVisit, ...rest } = opts; const c = await nc(rest);
    if (!firstVisit) await c.addInitScript(() => { try { localStorage.setItem('propfinder-intro-seen', '1'); localStorage.setItem('propfinder-filters-open', '1'); if (!localStorage.getItem('propfinder-v1')) localStorage.setItem('propfinder-v1', JSON.stringify({ tab: 'probable' })); } catch (e) {} });
    return c;
  };
  return b;
};
