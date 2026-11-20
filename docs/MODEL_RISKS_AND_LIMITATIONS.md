# Model, safety and data limitations

These issues were read from the supplied code and docs, not discovered by a real model benchmark.

1. **The fact checker is not a semantics guarantee.** It chiefly detects supported string patterns (numbers, dates, times, email/links/Latin tokens, and user-listed names). It can miss numbers written as words, changed descriptions, swapped order, meaning reversals and unlisted names; it may also withhold valid paraphrases.
2. **Training distribution shift.** The candidate travel corpus has short synthetic/formal sentences. The team-reviewed golden set contains customer-service issues across several domains, informal spelling and many facts. Performance is unknown until controlled evaluation.
3. **Training source rights.** The Zenodo record and article label CC BY 4.0, while the corpus's embedded README reportedly describes non-commercial restrictions; treat as licence ambiguity. Credit the author, avoid redistribution of raw data, and confirm rights before publishing derived weights or extensive training examples.
4. **Review provenance and freeze.** All 100 team approvals and reciprocal peer reviews were directly confirmed by the leader as having occurred in his presence. The reviewed set still requires a separately verifiable GitHub freeze commit before model training.
5. **ML evaluation leakage.** AI-authored template examples, prompt exemplars and the originally AI-drafted golden set may share patterns. Keep independent human review, exact/near/fact overlaps, and a final held-out test.
6. **Deployment.** Real adapter training, GGUF export, inference through Ollama and local Streamlit with the model still require end-to-end testing. No notebook execution or live model metrics has been demonstrated.
7. **Safety cases.** Mock-run statuses don't establish real model behavior or high-level semantic correctness. The adversarial set must be tested with the trained model and reviewed by team members.
