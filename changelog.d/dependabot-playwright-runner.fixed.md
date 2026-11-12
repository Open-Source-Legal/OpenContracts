- Pinned the frontend component and integration CI jobs to Ubuntu 24.04 so
  the installed Playwright release can install its browser dependencies.
- Pinned `preshed` to 3.0.13 so fresh frontend integration images can load
  spaCy models without the 3.0.14 tokenizer regression.
