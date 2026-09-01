"""The watcher (Spec 5): read-only relevance matcher over stored verified items.

Given a browser-supplied watchlist and the stored verified items, the watcher
decides relevance and emits each match with its plain-language reason in ONE
structured output (never.md #10), carrying a receipt copied from the record. It
reads; it writes nothing about the user (never.md #8).
"""
