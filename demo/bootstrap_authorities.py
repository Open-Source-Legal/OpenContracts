"""Bootstrap authority corpora from the seed JSONs in demo/authority_seeds/.

Run inside the Django container:

    docker compose -f local.yml run --rm django \
        python manage.py shell -c "exec(open('/app/demo/bootstrap_authorities.py').read())"

Set CREATOR_ID to the user who should own the authority corpora (must also be
able to read the filing corpora you intend to link).
"""

import json
import pathlib

from opencontractserver.enrichment.authorities import (
    AuthorityCorpusBootstrapper,
    AuthoritySection,
)

CREATOR_ID = 1
SEED_DIR = pathlib.Path("/app/demo/authority_seeds")

bootstrapper = AuthorityCorpusBootstrapper()
for seed_path in sorted(SEED_DIR.glob("*.json")):
    spec = json.loads(seed_path.read_text())
    sections = [
        AuthoritySection(
            key=s["key"],
            heading=s["heading"],
            text=s["text"],
            source_url=s.get("source_url"),
        )
        for s in spec["sections"]
    ]
    out = bootstrapper.bootstrap(
        creator_id=CREATOR_ID,
        corpus_title=spec["corpus_title"],
        sections=sections,
        aliases=spec.get("aliases"),
    )
    print(
        f"{spec['corpus_title']}: corpus {out['corpus_id']} "
        f"(created={out['corpus_created']}) "
        f"+{out['documents_created']} ~{out['documents_updated']} "
        f"={out['documents_skipped']} skipped "
        f"^{out['documents_restamped']} restamped"
    )
