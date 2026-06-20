"""nlp — Layer A NLP enrichment (deterministic, pure, tested).

Per CLAUDE.md §4 / DESIGN.md §5 the enrichment pipeline is hybrid but the
*decisions* live here as pure functions over typed inputs: text cleaning,
language detection, topic classification, gazetteer-backed entity/region
extraction, actor alias resolution, and high-precision quote extraction. No
I/O, no clock, no network, no LLM — those belong to the worker (fetch) and
Layer B (narration). Every module ships a `test_<module>.py` gate.
"""
