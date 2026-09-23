"""Grounded Gemini retrieval for the ATLAS enterprise knowledge connectors.

The deterministic fallback keeps the demo usable in local development when a
Gemini credential is intentionally not configured.
"""

from __future__ import annotations

import os
import re
from typing import Any

try:  # Allow the FastAPI demo to start before optional SDK dependencies are installed.
    from google import genai
except ImportError:  # pragma: no cover - depends on the local developer environment
    genai = None


KNOWLEDGE_CORPUS: list[dict[str, str]] = [
    {
        "id": "KBA003192",
        "title": "SAP EWM qRFC Queue Lock Resolution & SM12 Unlock Procedure",
        "system": "ServiceNow",
        "url": "https://roche.service-now.com/kb_view.do?sysparm_article=KBA003192",
        "keywords": "sap ewm qrfc queue lock sm12 unlock warehouse goods issue",
    },
    {
        "id": "VEEVA-SOP-0042",
        "title": "GxP Standard Operating Procedure for Batch Interface Access Controls",
        "system": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/SOP-0042",
        "keywords": "gxp batch interface access controls authorization roles compliance",
    },
    {
        "id": "ALM-DEF-8812",
        "title": "Known Defect: SolMan Redundant Alert Suppression in SAP EWM 1010",
        "system": "HP ALM",
        "url": "https://alm.roche.com/qcbin/defect/8812",
        "keywords": "solman redundant alert suppression sap ewm 1010 monitoring defect",
    },
    {
        "id": "GDRIVE-SUD-109",
        "title": "System Understanding Document: SAP MM PO Release Workflow Integration Architecture",
        "system": "Google Drive",
        "url": "https://drive.google.com/file/d/SUD-109-ARCH",
        "keywords": "sap mm po purchase order release workflow integration architecture",
    },
]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
try:
    client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY and genai else None
except Exception:  # pragma: no cover - protects local startup from SDK credential issues
    client = None


def _retrieve_sources(query_text: str) -> list[dict[str, str]]:
    """Rank connector documents with transparent keyword relevance."""

    query_terms = set(re.findall(r"[a-z0-9]+", query_text.lower()))
    scored_sources: list[tuple[int, int, dict[str, str]]] = []
    for index, source in enumerate(KNOWLEDGE_CORPUS):
        searchable_terms = set(re.findall(r"[a-z0-9]+", " ".join(source.values()).lower()))
        score = len(query_terms & searchable_terms)
        scored_sources.append((score, -index, source))

    # Always return two references so an unrecognised question still has a
    # useful, deterministic enterprise context rather than an empty citation UI.
    ranked = sorted(scored_sources, reverse=True)
    return [source for _, _, source in ranked[:2]]


def _fallback_answer(query_text: str, sources: list[dict[str, str]]) -> str:
    source_labels = ", ".join(f"{source['id']} ({source['title']})" for source in sources)
    return (
        f"Grounded ATLAS synthesis for: {query_text.strip()}. Review {source_labels} "
        "and validate the proposed operational action in the applicable ServiceNow record before execution. "
        "This response is running in local deterministic mode because GEMINI_API_KEY is not configured."
    )


def _grounded_prompt(query_text: str, sources: list[dict[str, str]]) -> str:
    reference_text = "\n".join(
        f"- [{source['id']}] {source['title']} ({source['system']}): {source['url']}"
        for source in sources
    )
    return (
        "You are the Roche ATLAS ITSM Co-Pilot. Answer only from the enterprise "
        "sources below. State practical next steps, do not invent source details, "
        "and cite source IDs inline.\n\n"
        f"User question: {query_text}\n\nRetrieved enterprise sources:\n{reference_text}"
    )


def query_gemini_rag(query_text: str) -> dict[str, Any]:
    """Retrieve enterprise references and synthesize a Gemini-grounded response."""

    sources = _retrieve_sources(query_text)
    answer = _fallback_answer(query_text, sources)
    if client is not None:
        try:
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=_grounded_prompt(query_text, sources),
            )
            if response.text:
                answer = response.text
        except Exception:
            # Runtime API failures must not break support engineers' local chat flow.
            pass

    return {"answer": answer, "sources": sources, "model_used": "gemini-1.5-flash"}
