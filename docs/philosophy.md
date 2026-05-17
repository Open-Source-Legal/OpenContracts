# Philosophy

## Knowledge is the substrate

Most knowledge lives in documents. Contracts, regulations, research papers, policies — the stuff that governs how organizations actually work. That knowledge is usually trapped: locked in PDFs, scattered across drives, understood fully by a handful of people who happened to read the right things at the right time.

OpenContracts started in 2019 with a simple conviction: that knowledge needed to be carefully curated, and that machine learning systems were only as good as the data underneath them. It was built as a platform for human collaborators — lawyers, researchers, analysts — to annotate documents together and produce gold-standard training data.

Those collaborators mostly never came. The platform was too early, the problem too niche, the value too invisible.

Then large language models arrived, and the world suddenly needed exactly what OpenContracts had been building all along: structured, annotated, version-controlled knowledge bases that AI could actually reason over. The collaborators the platform was designed for finally showed up — they just turned out to be AI agents.

Today, OpenContracts is a self-hosted platform where teams build knowledge bases from their documents and where AI agents work alongside humans to search, analyze, and extend that knowledge. The core conviction hasn't changed. The best AI systems still need carefully curated data. The difference is that now, the curation and the AI happen in the same place.

## DRY for institutional knowledge

The Don't-Repeat-Yourself principle is usually applied to code. We apply it to knowledge. A corpus you have carefully annotated should be sharable — to your team, to your organisation, or to the public. Anyone with read access can fork it to a private copy, refine the annotations, add documents, and share their improvements back.

This is `git` for knowledge: branch it, build on it, share it, restore any prior version, and never lose work.

## Humans first, agents second

OpenContracts is not a "chat with your PDFs" tool. It treats human annotation as the ground truth and builds AI on top — agents reason over real, curated data instead of hallucinating in a vacuum. The quality of an agent's answers is bounded by the quality of the knowledge base underneath, so the platform invests heavily in making annotation, discussion, and review first-class workflows.
