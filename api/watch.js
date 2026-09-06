// Porch Light — Vercel serverless proxy to the watcher Lambda.
//
// Routes around the account's block on public (AuthType=NONE) Function URLs: the
// browser calls this SAME-ORIGIN endpoint (no CORS), and this function invokes the
// watcher Lambda directly with a dedicated, least-privilege IAM user
// (lambda:InvokeFunction on the one function ARN). Credentials come from Vercel env
// vars only — never the repo, never the client bundle.
//
// NO-STORE (never.md #8) — the watch terms pass through Vercel now, so every logging
// path here is closed by construction:
//   - We NEVER console.log the request body, the terms, or the Lambda payload.
//   - The only logs are STATIC strings + non-term fields (status, a class name).
//   - Errors are caught and returned generically; no error path echoes the body.
//   - Vercel captures stdout/stderr, so silence here is the containment.
//
// Rate limit lives HERE (per-IP), not in the Lambda: the proxy sees the true client
// IP and is a better single choke point than the Lambda's per-instance counter.

import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";

const REGION = process.env.PORCHLIGHT_AWS_REGION || "us-east-1";
const FUNCTION_NAME = process.env.PORCHLIGHT_WATCHER_FUNCTION || "porchlight-dev-watcher";

// The SDK reads PORCHLIGHT_AWS_* explicitly so we don't collide with Vercel's
// reserved AWS_* names. Credentials are the dedicated invoke-only IAM user.
const lambda = new LambdaClient({
  region: REGION,
  credentials: {
    accessKeyId: process.env.PORCHLIGHT_AWS_ACCESS_KEY_ID,
    secretAccessKey: process.env.PORCHLIGHT_AWS_SECRET_ACCESS_KEY,
  },
});

// Per-IP rate limit: 10 requests / 60s. In-memory per proxy instance (Vercel may run
// several), so it is a courtesy throttle, not a hard guarantee — documented in
// KNOWN-LIMITATIONS. A durable limit (KV/usage plan) is the v2 fix.
const RATE_MAX = 10;
const RATE_WINDOW_MS = 60_000;
const hits = new Map();

function rateLimited(ip) {
  const now = Date.now();
  const arr = (hits.get(ip) || []).filter((t) => now - t < RATE_WINDOW_MS);
  if (arr.length >= RATE_MAX) {
    hits.set(ip, arr);
    return true;
  }
  arr.push(now);
  hits.set(ip, arr);
  return false;
}

function clientIp(req) {
  const xff = req.headers["x-forwarded-for"];
  if (typeof xff === "string" && xff.length) return xff.split(",")[0].trim();
  return "unknown";
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ degraded: true, reason: "method_not_allowed" });
    return;
  }

  if (rateLimited(clientIp(req))) {
    // No IP in the log.
    console.warn("watch_proxy_rate_limited");
    res.status(429).json({ degraded: true, reason: "rate_limited",
      note: "Too many requests. Please wait a moment." });
    return;
  }

  // Read the body. Vercel parses JSON bodies for us; fall back to raw parse.
  let terms;
  try {
    const body = typeof req.body === "object" && req.body ? req.body : JSON.parse(req.body || "{}");
    terms = Array.isArray(body.terms) ? body.terms : [];
  } catch {
    res.status(400).json({ degraded: true, reason: "bad_request" });
    return;
  }
  if (!terms.length) {
    res.status(200).json({ matches: [], is_quiet: true, source: "none" });
    return;
  }

  try {
    // Invoke the Lambda with the SAME event shape the handler already accepts
    // (Function URL style), so the Lambda code is unchanged.
    const event = {
      requestContext: { http: { method: "POST", sourceIp: clientIp(req) } },
      body: JSON.stringify({ terms }),
    };
    const out = await lambda.send(new InvokeCommand({
      FunctionName: FUNCTION_NAME,
      Payload: Buffer.from(JSON.stringify(event)),
    }));

    const raw = out.Payload ? Buffer.from(out.Payload).toString("utf-8") : "{}";
    const envelope = JSON.parse(raw); // { statusCode, headers, body }
    const status = envelope.statusCode || 200;
    // Pass the Lambda's own JSON body straight through, unchanged.
    res.status(status);
    res.setHeader("content-type", "application/json");
    res.send(envelope.body || JSON.stringify({ degraded: true, reason: "empty" }));
  } catch (err) {
    // STATIC error only — never the body, never the terms, never the message.
    console.error("watch_proxy_error", { error_type: err && err.name ? err.name : "Error" });
    res.status(200).json({ degraded: true, reason: "proxy_error",
      note: "The live watcher could not answer right now." });
  }
}
