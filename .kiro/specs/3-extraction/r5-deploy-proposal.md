# R5 — extractor runtime deploy: what's done, and the deploy decision that needs you

Status of the five conditions after this pass:

- **Design property (pre-condition): DONE.** design.md now records containment as a
  contract property — after R2 the extractor receives stored text, never a URL.
- **Condition 1 (text-not-URL contract): DONE.** `entrypoint.py invoke()` requires
  `payload['pages']: list[str]`; `document_id` is an opaque log label, never
  dereferenced; fails closed on a bad payload.
- **Condition 4 (migrations): DONE, live.** 002 → 003 → 004 applied to Aurora
  `porchlight-dev` in order, each run twice with no error (idempotency proven).
  Rollback note in each migration file. All additive/safe.
- **Condition 3 (narrow IAM): policy WRITTEN below, NOT attached** — it needs the
  deployed runtime ARN, which does not exist yet.
- **Condition 2 (prove containment live) + Condition 5 (run the meeting): BLOCKED
  on the deploy**, and the deploy has a decision only you should make (below).

## The deploy decision (why I stopped)

**No-egress is not a flag; it requires VPC network mode.** The AgentCore runtime
`networkMode` enum is only `PUBLIC | VPC`. PUBLIC has full internet egress (the
Security Hub control `BedrockAgentCore.1` explicitly fails a PUBLIC runtime).
Genuine no-egress — which condition 2 demands be PROVEN by a blocked call, not
asserted — requires **VPC network mode with a security group that has no outbound
route the extractor could use**. The Spike B scaffolding is PUBLIC with no VPC.
The decisions doc (§16b "Extractor egress question") flagged exactly this as a
"Spec 5 decision," and this is that decision.

So R5's deploy is not "run `agentcore deploy`." It is: stand up (or choose) a VPC +
private subnet(s) + a security group with no egress, point a new extractor runtime
at `agents/extractor/entrypoint.py` in VPC mode, and only then is condition 2
provable. That is billable, persistent external state with real blast radius, and
the VPC/subnet/SG choice is a genuine design fork. It is propose-and-wait, and I am
not improvising it inside this block.

### Options for the VPC/no-egress posture (pick one)

1. **VPC + private subnet, security group with NO egress rules at all.** The
   strongest and simplest: the runtime literally cannot open an outbound
   connection. But the extractor also needs Bedrock (the model) and the RDS Data
   API — both reachable via **VPC endpoints (PrivateLink)**, not the internet. So:
   private subnet, SG egress limited to the Bedrock + RDS-Data VPC endpoints only,
   no NAT, no internet route. This is the honest "no egress to the internet, only
   to the two AWS services it must reach, over PrivateLink" posture. Recommended.
2. **VPC + SG with zero egress, and pass model output in/out via the payload** so
   the runtime needs neither Bedrock nor RDS from inside. Purest no-egress, but it
   moves the model call and the DB writes OUT of the extractor runtime back to the
   pipeline — which changes the architecture (the extractor would only parse text
   handed to it and return items; the pipeline does the model call and the writes).
   Arguably cleaner given the contract property (the extractor's job is parsing
   handed text), but it is a design change, not just a deploy.
3. **Accept PUBLIC mode for the PoC and DOWNGRADE the claim** — document that
   no-egress is enforced only by the tool allowlist hook (one layer, not two) until
   VPC is wired. Honest, but it gives up the "two independent layers" guarantee that
   §19c/R8.3 rest on, and it cannot satisfy condition 2 as written (nothing to
   prove blocked at the network layer). Not recommended; recorded for completeness.

My lean: **option 1** for a faithful two-layer guarantee, or **option 2** if you
want the extractor's contract to be "parse handed text, return items, touch
nothing" — which actually matches the containment-is-a-contract property best. Both
are real work and a real cost; your call.

## DECISION: Option 1 (recorded)

**Chosen: Option 1** — VPC private subnet, security group egress restricted to the
Bedrock and RDS-Data PrivateLink endpoints only.

**Why NOT option 2 (recorded reasoning):** moving the model call out to the pipeline
stops the extractor being an AGENT — it becomes a parser. That collapses the
three-loops-two-agents architecture (§3) to one agent, in a hackathon track that is
specifically about agents. The containment would be purer and the architecture would
be gone. The ~$14/month is not the deciding factor; the ~$7 between now and judging
is noise. The architecture is worth more than the marginal purity.

**Timebox (firm):** two hours of actual VPC/subnet/endpoint/SG work. If it is not
deployed and reachable by then, STOP and take Option 3 (the pre-written fallback
below). Block Zero lost three days to exactly this "almost there" infrastructure;
shipping Option 3 honestly beats losing days to networking.

## Pre-written Option-3 fallback paragraph (use verbatim if the timebox blows)

For README, KNOWN-LIMITATIONS, and the Devpost writeup — drafted BEFORE starting so
the honest version exists under no pressure. Do not soften it.

> **Extractor network containment: one layer deployed, two designed.** The extractor
> reads untrusted PDF text, so its design calls for two independent containment
> layers: the Strands hook tool-allowlist (which blocks any tool call outside its
> four permitted tools) AND network-level egress control (the runtime cannot open an
> outbound connection at all). For v1, only the first layer is deployed. The
> AgentCore runtime runs in PUBLIC network mode, which permits outbound egress;
> network-level no-egress requires VPC network mode with a restricted security group
> and PrivateLink endpoints, which was designed and specified but not deployed within
> the hackathon window. The consequence, stated plainly: if a prompt injection
> defeated the hook allowlist, nothing at the network layer would stop an outbound
> call. The hook allowlist is real and tested; the second layer is designed and
> documented, not shipped. We chose to ship this honestly rather than claim a
> containment posture we had not deployed.

## Condition 3 — the narrow IAM policy (written, attach after deploy)

Attach to role **`porchlight-dev-hunter-role`** (the hunter Lambda's execution
role, `arn:aws:iam::<ACCOUNT>:role/porchlight-dev-hunter-role`). Invoke permission
on THAT extractor runtime ARN only — no wildcard, no service-wide invoke:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeExtractorRuntimeOnly",
      "Effect": "Allow",
      "Action": "bedrock-agentcore:InvokeAgentRuntime",
      "Resource": "arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT>:runtime/porchlight-dev-extractor-*"
    }
  ]
}
```

The `-*` suffix covers the runtime's version/endpoint sub-resources under the one
named runtime; it is NOT a wildcard across runtimes (the runtime name
`porchlight-dev-extractor` is fixed). No other `bedrock-agentcore:*` action, no
`Resource: "*"`. Exact ARN swapped in once the runtime is deployed and its id known.

## Condition — teardown accounting (what R5 leaves running, idle cost, command)

**What a deployed extractor runtime leaves running:**
- An AgentCore runtime (`porchlight-dev-extractor`). AgentCore Runtime bills per
  request/compute-second on invoke; **an idle runtime that is not being invoked has
  no per-request charge.** The standing cost is near-zero when idle — unlike a
  provisioned server, it is not paid by the hour just for existing.
- **If option 1/VPC:** the ongoing cost is the VPC endpoints (PrivateLink). Interface
  VPC endpoints bill ~$0.01/hour each ≈ **~$0.24/day per endpoint**, so Bedrock +
  RDS-Data endpoints ≈ **~$0.48/day (~$14/month) idle**, whether or not anything
  runs. This is the real standing cost of the no-egress posture, and it is the number
  to weigh. A NAT gateway is NOT used (that would be ~$32/month); PrivateLink is
  cheaper and is the no-internet path.
- **Aurora** (already running from Spec 2, min-cap 0): ~$0 idle when auto-paused;
  not new to R5.

**Idle cost of R5 specifically:** ~$0.48/day if option 1 (the two VPC endpoints);
~$0 if option 2 (no VPC endpoints — the runtime touches nothing); ~$0 if option 3.
The runtime itself and Aurora contribute ~$0 idle.

**Exact teardown command** (removes the extractor runtime; per the AGENTS.md CLI):
```
agentcore remove runtime porchlight-dev-extractor   # from the agentcore project dir
agentcore deploy                                     # applies the removal (tears down the runtime)
```
For the VPC endpoints (option 1), teardown is deleting the two interface endpoints:
```
aws ec2 delete-vpc-endpoint-connections ...   # or delete via the VPC console / the IaC that created them
```
The wind-down obligation (§13) is stopping the crawler, not saving money; the
teardown of the *hunter schedule* is the EventBridge disable already documented.
R5's extractor runtime and any VPC endpoints are the new things to remove, above.

## What I did NOT do (honest boundary)

- Did NOT deploy a runtime (the VPC/no-egress decision is yours).
- Did NOT attach the IAM policy (no runtime ARN yet).
- Did NOT fake condition 2. Containment is proven by a blocked attempt against a
  real deployed runtime, or it is not proven. There is no simulated stand-in in
  this doc, deliberately.
