/* Porch Light web config — copy to config.js and fill in.
 *
 * PORCHLIGHT_WATCHER_URL: the deployed watcher Function URL. When set, the page
 * calls the REAL Nova Lite matcher at request time. When empty (""), the page uses
 * the transparent client-side keyword filter and says so. The page ALWAYS falls
 * back to the keyword filter if the endpoint fails, times out, is CORS-blocked, or
 * returns a degraded/paused state — never a blank list, never a hanging spinner.
 *
 * config.js is gitignored (the URL is environment-specific; keeping it untracked
 * also keeps any account-identifying host out of the repo). Commit config.example.js.
 */
window.PORCHLIGHT_CONFIG = {
  // "/api/watch" = the same-origin Vercel proxy (default). "" = keyword-only.
  PORCHLIGHT_WATCHER_URL: "/api/watch"
};
