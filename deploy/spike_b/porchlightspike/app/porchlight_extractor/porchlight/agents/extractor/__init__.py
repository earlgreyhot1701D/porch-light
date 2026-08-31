# Extractor — the agent that reads ONE document and emits items with page ranges
# (Spec 3, R1, §3, §30d, §38). Runs in its own AgentCore runtime with NO network
# egress; tools are allowlisted at the Strands hook layer. Two independent
# containment layers (runtime + hook). Packet text is untrusted data (never.md #9).
