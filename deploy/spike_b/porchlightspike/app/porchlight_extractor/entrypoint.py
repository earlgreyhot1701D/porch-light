"""AgentCore entry file for the extractor runtime (Spec 3 R5, PUBLIC networkMode).

Thin re-export: the real entrypoint (the BedrockAgentCoreApp + @app.entrypoint
invoke) lives in the vendored porchlight.agents.extractor.entrypoint, so the same
code that is unit-tested in the repo is what deploys. This file exists only because
AgentCore CodeZip needs an entry file at the codeLocation root.

Containment posture (this deploy): PUBLIC networkMode (the network-egress layer is
designed but deferred post-submission — see KNOWN-LIMITATIONS). The layer that IS
live and proven here is the Strands hook tool-allowlist, and the structural fact
that the extractor's contract takes stored text and its tool registry has no
network-capable tool.
"""

from porchlight.agents.extractor.entrypoint import app

if __name__ == "__main__":
    app.run()
