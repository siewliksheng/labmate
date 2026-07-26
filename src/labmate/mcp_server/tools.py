"""M1/M2: real tool implementations, traced via labmate.observability.

Design notes worth keeping as this evolves further:
- lookup_sds / lookup_biosafety_level / get_environmental_state /
  search_sop_handbook all return found: false rather than guessing when
  there's no match -- see docs/architecture.md, "absence of a match is
  not the same as clearance." A caller (or the M3 gate, later) must treat
  found: false as unresolved.
- analyze_image never returns a safe/unsafe verdict, only two independent
  passes' raw findings -- that framing decision belongs to the safety
  gate (M3), not to this tool or the vision specialist. It records what it
  found to memory (M2) so a future analysis of a similar sample can be
  compared against labeled history, not just judged in isolation.
- escalate_to_safety_officer logs to a local file for now (var/, never
  committed); M4 replaces the storage layer with a real review-queue DB
  and builds a UI on top, but the tool's interface doesn't need to change.
"""

import json
import os
from pathlib import Path
from typing import Any

import httpx

from labmate.memory.sop_handbook import search_sop_handbook as _search_sop_handbook
from labmate.memory.store import get_environmental_state as _get_environmental_state
from labmate.memory.store import log_environmental_state as _log_environmental_state
from labmate.memory.store import record_image_analysis
from labmate.memory.store import search_past_image_analyses as _search_past_image_analyses
from labmate.memory.store import search_past_qa as _search_past_qa
from labmate.observability import traced_tool_call
from labmate.paths import VAR_DIR

_BIOSAFETY_DATA_PATH = Path(__file__).parent / "data" / "biosafety_levels.json"
_HTTP_TIMEOUT = 10.0

TOOL_SCHEMAS = [
    {
        "name": "search_pubmed",
        "description": "Search PubMed for recent papers on a topic. Returns titles, PMIDs, journal, and date -- call fetch_abstract for the full abstract text of a specific result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_abstract",
        "description": "Fetch the full abstract text for a PubMed ID. Use this before citing a specific paper's findings -- a title alone is not enough to ground a claim.",
        "input_schema": {
            "type": "object",
            "properties": {"pmid": {"type": "string"}},
            "required": ["pmid"],
        },
    },
    {
        "name": "search_biorxiv",
        "description": "Search preprints (bioRxiv, medRxiv, and other servers indexed by Europe PMC) for a topic. Returns title, source server, date, and abstract text directly.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "analyze_image",
        "description": (
            "Analyze a lab sample image (microscopy, culture plate, blot) in two independent passes: "
            "a descriptive pass and a hazard-scan pass covering edges/background. "
            "Never returns a safe/unsafe verdict, which is not this tool's job."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"image_path": {"type": "string"}},
            "required": ["image_path"],
        },
    },
    {
        "name": "lookup_sds",
        "description": "Retrieve GHS hazard classification (pictograms, hazard statements) for a named substance from PubChem. Returns found: false if there's no matching entry -- treat that as unresolved, not as non-hazardous.",
        "input_schema": {
            "type": "object",
            "properties": {"substance": {"type": "string"}},
            "required": ["substance"],
        },
    },
    {
        "name": "lookup_biosafety_level",
        "description": "Look up the required biosafety level for a named organism or sample type from a curated reference table. Returns found: false if there's no matching entry -- treat that as unresolved, not as low-risk.",
        "input_schema": {
            "type": "object",
            "properties": {"organism_or_sample": {"type": "string"}},
            "required": ["organism_or_sample"],
        },
    },
    {
        "name": "search_sop_handbook",
        "description": "Search the lab's SOP handbook for guidance relevant to a query. Returns matching excerpts with their source file, not the whole handbook. Returns no results if nothing matches -- treat that as unresolved, not as 'no restrictions apply.'",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        },
    },
    {
        "name": "log_environmental_state",
        "description": "Record a current environmental condition at a bench/location (e.g. an active heat source, an in-progress procedure). Entries expire after ttl_hours -- log real conditions, not permanent facts about the bench.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bench": {"type": "string"},
                "description": {"type": "string"},
                "logged_by": {"type": "string"},
                "ttl_hours": {"type": "number", "default": 2.0},
            },
            "required": ["bench", "description", "logged_by"],
        },
    },
    {
        "name": "get_environmental_state",
        "description": "Look up the current logged environmental state for a bench/location. Returns found: false if nothing is logged, or if the last entry expired -- an expired entry means unknown, never 'still safe.'",
        "input_schema": {
            "type": "object",
            "properties": {"bench": {"type": "string"}},
            "required": ["bench"],
        },
    },
    {
        "name": "search_past_qa",
        "description": "Search this lab's history of past questions and answers for anything relevant to the current one -- useful for noticing 'we saw something like this before.'",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_past_image_analyses",
        "description": "Search past sample-image analyses (and any human-confirmed labels attached to them) for comparison against the current one -- grounds a new analysis against labeled history instead of judging it in isolation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "escalate_to_safety_officer",
        "description": (
            "Hand off a safety question to a human safety officer instead of answering it directly. "
            "Use whenever no retrieved SDS/protocol unambiguously covers the situation, a lookup "
            "returned found: false, or the query implies physical risk you are not certain about."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "urgency": {"enum": ["routine", "urgent"]},
            },
            "required": ["summary", "urgency"],
        },
    },
]


def dispatch_tool(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool '{name}'. Available: {list(_HANDLERS)}"}

    attrs = {f"input.{k}": v for k, v in tool_input.items()}
    with traced_tool_call(name, **attrs) as span:
        try:
            result = handler(**tool_input)
        except Exception as exc:
            span.set_attribute("error", str(exc))
            return {"error": f"{name} failed: {exc}"}
        if isinstance(result, dict):
            span.set_attribute("output.keys", ",".join(result.keys()))
        return result


def _ncbi_params(**params):
    # NCBI allows 3 req/sec unauthenticated, 10 req/sec with a free API
    # key -- .env.example has a slot for it (NCBI_API_KEY) that previously
    # went unused. This is the one place that matters.
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return params


def _search_pubmed(query: str, max_results: int = 10):
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        search_resp = client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params=_ncbi_params(db="pubmed", term=query, retmax=max_results, retmode="json"),
        )
        search_resp.raise_for_status()
        ids = search_resp.json()["esearchresult"]["idlist"]
        if not ids:
            return {"results": [], "note": "No PubMed results for this query."}

        summary_resp = client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params=_ncbi_params(db="pubmed", id=",".join(ids), retmode="json"),
        )
        summary_resp.raise_for_status()
        summary = summary_resp.json()["result"]

    results = [
        {
            "pmid": pmid,
            "title": summary.get(pmid, {}).get("title", ""),
            "journal": summary.get(pmid, {}).get("fulljournalname", ""),
            "pubdate": summary.get(pmid, {}).get("pubdate", ""),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        }
        for pmid in ids
    ]
    return {"results": results}


def _fetch_abstract(pmid: str):
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params=_ncbi_params(db="pubmed", id=pmid, rettype="abstract", retmode="text"),
        )
        resp.raise_for_status()

    text = resp.text.strip()
    if not text:
        return {"pmid": pmid, "found": False, "note": "No abstract text returned for this PMID."}
    return {
        "pmid": pmid,
        "found": True,
        "abstract_text": text,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


def _search_biorxiv(query: str, max_results: int = 10):
    # Europe PMC's SRC:PPR covers all preprint servers it indexes (bioRxiv,
    # medRxiv, and others) -- there is no bioRxiv-only public search API, so
    # this is the honest scope of what this tool actually searches.
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={
                "query": f"({query}) AND SRC:PPR",
                "format": "json",
                "pageSize": max_results,
                "resultType": "core",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    results = [
        {
            "id": entry.get("id"),
            "title": entry.get("title", ""),
            "source": entry.get("source", ""),
            "first_publication_date": entry.get("firstPublicationDate", ""),
            "abstract_text": entry.get("abstractText", ""),
            "doi": entry.get("doi", ""),
        }
        for entry in data.get("resultList", {}).get("result", [])
    ]
    if not results:
        return {"results": [], "note": "No preprint results for this query."}
    return {"results": results}


def _analyze_image(image_path: str):
    import base64

    from anthropic import Anthropic

    from labmate.specialists.vision import VISION_DESCRIPTIVE_PROMPT, VISION_HAZARD_SCAN_PROMPT

    path = Path(image_path)
    if not path.exists():
        return {"found": False, "note": f"Image file not found at {image_path}"}

    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "image/jpeg")
    image_b64 = base64.standard_b64encode(path.read_bytes()).decode()

    client = Anthropic()

    def _pass(prompt_text: str) -> str:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                        },
                        {"type": "text", "text": prompt_text},
                    ],
                }
            ],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    description = _pass(VISION_DESCRIPTIVE_PROMPT)
    hazard_scan_findings = _pass(VISION_HAZARD_SCAN_PROMPT)
    record_image_analysis(image_path, description, hazard_scan_findings)

    return {
        "found": True,
        "description": description,
        "hazard_scan_findings": hazard_scan_findings,
    }


def _load_biosafety_entries():
    return json.loads(_BIOSAFETY_DATA_PATH.read_text(encoding="utf-8"))["entries"]


def _lookup_biosafety_level(organism_or_sample: str):
    query = organism_or_sample.strip().lower()
    for entry in _load_biosafety_entries():
        if any(alias in query or query in alias for alias in entry["aliases"]):
            return {
                "found": True,
                "matched_alias": entry["aliases"][0],
                "level": entry["level"],
                "notes": entry["notes"],
                "source": entry["source"],
            }
    return {
        "found": False,
        "organism_or_sample": organism_or_sample,
        "note": "No entry in the local biosafety reference table -- treat as unresolved, not as low-risk.",
    }


def _lookup_sds(substance: str):
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        cid_resp = client.get(
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{substance}/cids/JSON"
        )
        if cid_resp.status_code == 404:
            return {
                "found": False,
                "substance": substance,
                "note": "No PubChem entry for this name -- treat as unresolved, not as non-hazardous.",
            }
        cid_resp.raise_for_status()
        cid = cid_resp.json()["IdentifierList"]["CID"][0]

        view_resp = client.get(
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON",
            params={"heading": "GHS Classification"},
        )
        if view_resp.status_code == 404:
            return {
                "found": False,
                "substance": substance,
                "cid": cid,
                "note": "No GHS Classification section for this compound -- treat as unresolved.",
            }
        view_resp.raise_for_status()
        data = view_resp.json()

    statements: list[str] = []
    pictograms: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            name = node.get("Name", "")
            value = node.get("Value", {})
            if "StringWithMarkup" in value:
                text_items = [s.get("String", "") for s in value["StringWithMarkup"]]
                if "Pictogram" in name:
                    pictograms.extend(text_items)
                elif "Hazard Statements" in name:
                    statements.extend(text_items)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)

    return {
        "found": True,
        "substance": substance,
        "cid": cid,
        "hazard_statements": statements,
        "pictograms": pictograms,
        "source_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
    }


def _escalate_to_safety_officer(summary: str, urgency: str):
    from datetime import datetime, timezone

    VAR_DIR.mkdir(exist_ok=True, parents=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "urgency": urgency,
        "status": "pending",
    }
    with (VAR_DIR / "escalations.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return {
        "escalated": True,
        "queued_at": entry["timestamp"],
        "note": "Logged to the local review queue (var/escalations.jsonl). M4 builds the real review UI on top of this store.",
    }


_HANDLERS = {
    "search_pubmed": _search_pubmed,
    "fetch_abstract": _fetch_abstract,
    "search_biorxiv": _search_biorxiv,
    "analyze_image": _analyze_image,
    "lookup_sds": _lookup_sds,
    "lookup_biosafety_level": _lookup_biosafety_level,
    "search_sop_handbook": _search_sop_handbook,
    "log_environmental_state": _log_environmental_state,
    "get_environmental_state": _get_environmental_state,
    "search_past_qa": _search_past_qa,
    "search_past_image_analyses": _search_past_image_analyses,
    "escalate_to_safety_officer": _escalate_to_safety_officer,
}
