`install_domain_pack` installs a **domain pack**: a named set of base packs plus
the wiring that belongs to none of them — a corpus group, an orchestrator agent
bound to it, and cross-pack equivalences.

A pack spanning several bodies of law used to install its content correctly and
land inert, because three things could not be expressed in a pack manifest and
had to be created by hand afterwards: the corpus group (without which there is
no cross-corpus retrieval at all), an orchestrator carrying
`search_across_corpora`, and the group slug somewhere the agent would read it —
the tool takes it as a required argument. The install reported success either
way.

```
python manage.py install_domain_pack <name> --creator admin --public
python manage.py install_domain_pack <name> --check      # plan, writes nothing
python manage.py install_domain_pack --list
```

The install contract (C1–C7) is defined in the pack registry's
`DOMAIN_PACKS.md`, so both sides build to one spec. Everything decidable from
the files is decided before anything is written, on the `--check` path and the
install path alike, and all wiring runs in one transaction.
