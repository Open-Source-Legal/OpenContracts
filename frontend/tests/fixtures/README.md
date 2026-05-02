# E2E test fixtures

These PDFs are committed copies of canonical fixtures from
`opencontractserver/tests/fixtures/`:

- `usc-title-1.pdf` — copy of `USC Title 1 - CHAPTER 1.pdf` (72 KB).
- `eton-agreement.pdf` — copy of `EtonPharmaceuticalsInc_20191114_10-Q_EX-10.1_11893941_EX-10.1_Development_Agreement_ZrZJLLv.pdf` (247 KB).

They live here (rather than being read from the backend tree) so the
Playwright E2E specs do not reach across the frontend / backend boundary
at test time. The two PDFs are deliberately distinct — the
`doc_*_pdf_file.pdf` fixtures in the backend tree are byte-identical
clones of `usc-title-1.pdf` and would not give us two extractable titles.
