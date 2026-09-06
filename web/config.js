/* LOCAL config (committed; contains no secrets, no account id). See config.example.js.
 *
 * The page calls the same-origin Vercel proxy /api/watch, which invokes the watcher
 * Lambda server-side (routing around the account's block on public Function URLs).
 * Leave PORCHLIGHT_WATCHER_URL as "/api/watch" for the deployed site. Set "" to force
 * keyword-only mode (e.g. a purely static host with no proxy). The page always falls
 * back to the keyword filter if the proxy fails, times out, or returns degraded. */
window.PORCHLIGHT_CONFIG = {
  PORCHLIGHT_WATCHER_URL: "/api/watch"
};
