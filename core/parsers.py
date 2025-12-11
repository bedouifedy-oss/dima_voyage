"""Parsers for the dynamic document engine.

The engine is now fully manual-only, so we only expose a no-op parser
entry for compatibility. Any templates use parser_type="none" and rely
entirely on manual fields.
"""

PARSER_REGISTRY = {
    "none": lambda x: {},
}
