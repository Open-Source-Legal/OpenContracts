- Fixed Django image builds failing during spaCy model loading by pinning
  `preshed` to the working 3.0.13 release and excluding the broken 3.0.14 wheel
  from Dependabot updates. Added a tokenizer deserialization regression test.
- Pinned browser-test and screenshot CI jobs to Ubuntu 24.04, which supports
  the installed Playwright version; Ubuntu 26.04 runners fail before tests run.
- Pinned the Claude review action to the last verified working v1.0.259
  revision and excluded the failing v1.0.262 release from Dependabot updates.
