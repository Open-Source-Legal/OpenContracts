- Vector embedding now batches relationship text alongside annotations, removes
  relationship/creator query fan-out, caches decrypted component settings per
  component instance, uses accelerator-sized inference batches, and coalesces
  simultaneous HTTP requests. The Intel Arc 140V reference gate measured a
  49.13x throughput improvement over the production CPU embedder while retaining
  a minimum CPU/GPU cosine similarity of 0.9999989.
