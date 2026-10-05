"""JURIS-UQ: legal-aware uncertainty quantification for LLM legal question answering.

Phase A instrument: sampling harness, sample-only uncertainty baselines,
correctness resolution, and the E1 common-mode diagnostic.

Nothing in this package touches the network except ``jurisuq.generators``
(your local model endpoint) and, optionally, ``jurisuq.cluster`` (a Hugging
Face NLI checkpoint downloaded on first use).
"""

__version__ = "0.1.0-phaseA"
