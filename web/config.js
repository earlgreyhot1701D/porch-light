/* LOCAL config (gitignored). See config.example.js.
 * The deployed watcher Function URL. Empty string = keyword-only mode.
 * NOTE: this account blocks public (AuthType=NONE) Function URLs, so the live URL
 * currently returns 403 from a browser and the page will fall back to keyword mode
 * and say so. Set this when an account/proxy serves the endpoint publicly. */
window.PORCHLIGHT_CONFIG = {
  PORCHLIGHT_WATCHER_URL: "https://mgor4eoxo4juxanyaacto4fknu0otsgn.lambda-url.us-east-1.on.aws/"
};
