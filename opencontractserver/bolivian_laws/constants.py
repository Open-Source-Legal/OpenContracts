"""Constants for the Bolivian Laws RAG service.

Defines the legal areas (specialties), document sources, and per-area
profiles consumed by both the ingestion pipeline (corpus creation) and
the agent layer (specialist personas / instructions).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import models


class LegalArea(models.TextChoices):
    """Bolivian legal specialties.

    One Corpus is created per area on first ingestion.
    """

    CONSTITUCIONAL = "constitucional", "Derecho Constitucional"
    PENAL = "penal", "Derecho Penal"
    CIVIL = "civil", "Derecho Civil"
    ADMINISTRATIVO = "administrativo", "Derecho Administrativo"
    LABORAL = "laboral", "Derecho Laboral"
    TRIBUTARIO = "tributario", "Derecho Tributario"
    FAMILIA = "familia", "Derecho de Familia"
    COMERCIAL = "comercial", "Derecho Comercial"
    AGRARIO = "agrario", "Derecho Agrario"
    AMBIENTAL = "ambiental", "Derecho Ambiental"
    OTROS = "otros", "Otros"


class LegalSource(models.TextChoices):
    """Origin of an ingested legal document."""

    GACETA = "gaceta", "Gaceta Oficial de Bolivia"
    TSJ = "tsj", "Tribunal Supremo de Justicia"
    TCP = "tcp", "Tribunal Constitucional Plurinacional"
    MANUAL = "manual", "Carga manual"


@dataclass(frozen=True)
class AreaProfile:
    """Single source of truth for area-specific corpus + agent config."""

    title: str
    description: str
    agent_persona: str
    agent_instructions: str


_BASE_AGENT_RULES = (
    "Responde siempre en español. Cita la norma exacta (ley, código, "
    "artículo, número y fecha) cuando esté disponible. Cuando recuperes "
    "fragmentos del corpus, inclúyelos como soporte de tu respuesta. "
    "Si la pregunta sale de tu área de especialidad, indícalo y sugiere "
    "consultar al especialista correspondiente."
)


def _profile(
    area_label: str,
    short: str,
    persona_focus: str,
    extra_instruction: str = "",
) -> AreaProfile:
    title = f"Bolivia — {area_label}"
    description = (
        f"Corpus de fuentes jurídicas bolivianas en materia de {short}. "
        "Incluye legislación, jurisprudencia y doctrina recopilada de "
        "fuentes oficiales (Gaceta Oficial, TSJ, TCP) y cargas manuales."
    )
    persona = (
        f"Eres un experto en derecho {short} boliviano. {persona_focus} "
        "Te apoyas exclusivamente en el corpus indexado para responder."
    )
    instructions = _BASE_AGENT_RULES
    if extra_instruction:
        instructions = f"{instructions} {extra_instruction}"
    return AreaProfile(
        title=title,
        description=description,
        agent_persona=persona,
        agent_instructions=instructions,
    )


AREA_PROFILES: dict[str, AreaProfile] = {
    LegalArea.CONSTITUCIONAL: _profile(
        "Constitucional",
        "constitucional",
        "Dominas la Constitución Política del Estado (CPE) de 2009, "
        "la jurisprudencia del Tribunal Constitucional Plurinacional, "
        "garantías y derechos fundamentales.",
    ),
    LegalArea.PENAL: _profile(
        "Penal",
        "penal",
        "Conoces el Código Penal boliviano, el Código de Procedimiento "
        "Penal y la jurisprudencia penal del TSJ.",
    ),
    LegalArea.CIVIL: _profile(
        "Civil",
        "civil",
        "Dominas el Código Civil, obligaciones, contratos, sucesiones, "
        "derechos reales y la jurisprudencia civil del TSJ.",
    ),
    LegalArea.ADMINISTRATIVO: _profile(
        "Administrativo",
        "administrativo",
        "Conoces la Ley de Procedimiento Administrativo, la Ley SAFCO "
        "(Ley 1178), normativa de contrataciones estatales y la "
        "jurisprudencia contencioso-administrativa.",
    ),
    LegalArea.LABORAL: _profile(
        "Laboral",
        "laboral",
        "Dominas la Ley General del Trabajo, su reglamento y la "
        "jurisprudencia social del TSJ.",
    ),
    LegalArea.TRIBUTARIO: _profile(
        "Tributario",
        "tributario",
        "Conoces el Código Tributario boliviano, normativa del SIN y "
        "la jurisprudencia de la AIT.",
    ),
    LegalArea.FAMILIA: _profile(
        "Familia",
        "familia",
        "Dominas el Código de las Familias y del Proceso Familiar, "
        "y la jurisprudencia en materia familiar.",
    ),
    LegalArea.COMERCIAL: _profile(
        "Comercial",
        "comercial",
        "Conoces el Código de Comercio, sociedades comerciales y "
        "normativa empresarial boliviana.",
    ),
    LegalArea.AGRARIO: _profile(
        "Agrario",
        "agrario",
        "Dominas la Ley INRA, la Ley de Reconducción Comunitaria, "
        "y la jurisprudencia del Tribunal Agroambiental.",
    ),
    LegalArea.AMBIENTAL: _profile(
        "Ambiental",
        "ambiental",
        "Conoces la Ley del Medio Ambiente (Ley 1333), normativa "
        "sectorial ambiental y la jurisprudencia ambiental.",
    ),
    LegalArea.OTROS: _profile(
        "General",
        "general",
        "Cubres áreas residuales del derecho boliviano que no encajan "
        "en una especialidad específica.",
    ),
}


def get_profile(area: str) -> AreaProfile:
    """Return the AreaProfile for a given area key, raising if unknown."""
    profile = AREA_PROFILES.get(area)
    if profile is None:
        raise KeyError(f"Unknown legal area: {area!r}")
    return profile


# Slug used for the per-area corpus. Keep stable: changing it would
# orphan existing corpora.
def corpus_slug_for_area(area: str) -> str:
    return f"bolivia-{area}"


# Orchestrator persona — used when no area is forced and the orchestrator
# routes the question to one or more specialists.
ORCHESTRATOR_PERSONA = (
    "Eres un orquestador jurídico para derecho boliviano. Recibes "
    "preguntas de usuarios y decides qué especialista(s) consultar "
    "(constitucional, penal, civil, administrativo, laboral, tributario, "
    "familia, comercial, agrario, ambiental). Cuando una pregunta cruza "
    "áreas, consulta a varios especialistas y sintetiza una respuesta "
    "coherente. Cita siempre las fuentes que devuelven los especialistas "
    "y deja claro de qué área proviene cada cita. No inventes normas: "
    "si los especialistas no encuentran respuesta, dilo explícitamente."
)
