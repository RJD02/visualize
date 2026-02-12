"""Conversation planner agent to produce execution plans."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from uuid import uuid4


from src.utils.config import settings
from src.utils.openai_client import get_openai_client


_BASE_STYLE_KEYWORDS = [
    "color",
    "colour",
    "palette",
    "theme",
    "style",
    "aesthetic",
    "vibrant",
    "contrast",
    "highlight",
    "emphasis",
    "visual",
    "look",
]

_COLOR_KEYWORDS = [
    "red",
    "orange",
    "yellow",
    "gold",
    "amber",
    "green",
    "teal",
    "cyan",
    "blue",
    "navy",
    "indigo",
    "violet",
    "purple",
    "magenta",
    "pink",
    "fuchsia",
    "maroon",
    "brown",
    "black",
    "white",
    "grey",
    "gray",
    "silver",
    "bronze",
    "turquoise",
    "lavender",
    "peach",
]

_STYLE_KEYWORDS = _BASE_STYLE_KEYWORDS + _COLOR_KEYWORDS


_VISUAL_KEYWORDS = _STYLE_KEYWORDS + [
    "calm",
    "minimal",
    "energetic",
    "noisy",
    "busy",
    "balanced",
]


_DIAGRAM_REQUEST_KEYWORDS = [
    "diagram",
    "diagrams",
    "generate",
    "create",
    "flow",
    "sequence",
    "plantuml",
    "plant uml",
    "architecture",
    "visualize",
]

_DIAGRAM_TYPE_HINTS = {
    "system_context": ["system context", "context diagram", "system diagram"],
    "container": ["container diagram", "containers"],
    "component": ["component diagram", "components"],
    "sequence": ["sequence diagram", "sequence", "flow", "interaction"],
}

_MULTIPLE_DIAGRAM_HINTS = [
    "multiple diagram",
    "multiple diagrams",
    "several diagram",
    "several diagrams",
    "various diagram",
    "various diagrams",
    "different diagrams",
    "all diagrams",
]

_DEFAULT_DIAGRAM_TYPE = "system_context"

_RENDERING_SERVICES = {
    "programmatic",
    "llm_plantuml",
    "llm_mermaid",
    "external_service",
    "auto",
    "plantuml",
    "mermaid",
    "structurizr",
}
_EXTERNAL_SERVICE_TOOLS = {
    "render_image_from_plan",
    "edit_existing_image",
    "run_sdxl",
    "run_sdxl_edit",
}


LATEST_IMAGE_PLACEHOLDER = "__LATEST_IMAGE__"

_GENERATION_TOOLS = {
    "generate_architecture_plan",
    "generate_multiple_diagrams",
    "generate_diagram",
    "generate_plantuml",
    "generate_sequence_from_architecture",
    "generate_plantuml_sequence",
    "edit_diagram_via_semantic_understanding",
    "edit_diagram_ir",
    "render_image_from_plan",
}


def _extract_inline_llm_diagram(message: str) -> dict | None:
    if not message:
        return None
    code_match = re.search(r"```(plantuml|mermaid)?\s*([\s\S]+?)```", message, re.IGNORECASE)
    if code_match:
        lang = (code_match.group(1) or "plantuml").strip().lower()
        diagram_text = (code_match.group(2) or "").strip()
        if not diagram_text:
            return None
        fmt = "mermaid" if lang.startswith("mermaid") else "plantuml"
        return {"format": fmt, "diagram": diagram_text}
    uml_match = re.search(r"(@startuml[\s\S]+?@enduml)", message, re.IGNORECASE)
    if uml_match:
        return {"format": "plantuml", "diagram": uml_match.group(1).strip()}
    mermaid_match = re.search(r"(graph\s+(?:td|lr)[\s\S]+)", message, re.IGNORECASE)
    if mermaid_match:
        return {"format": "mermaid", "diagram": mermaid_match.group(1).strip()}
    return None


def _normalize_rendering_service(tool_name: str, service: str | None, llm_format: str | None) -> str:
    if service:
        token = str(service).lower()
        if token in _RENDERING_SERVICES:
            return token
    if llm_format == "mermaid":
        return "llm_mermaid"
    if llm_format == "plantuml":
        return "llm_plantuml"
    if tool_name in _EXTERNAL_SERVICE_TOOLS:
        return "external_service"
    return "programmatic"


def _normalize_llm_diagram_payload(value: Any) -> dict | None:
    if not value:
        return None
    payload = value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    diagram_text = str(payload.get("diagram") or payload.get("text") or "").strip()
    if not diagram_text:
        return None
    fmt = str(payload.get("format") or payload.get("type") or "plantuml").lower()
    if fmt.startswith("mermaid"):
        fmt = "mermaid"
    else:
        fmt = "plantuml"
    schema_version = payload.get("schema_version") or payload.get("version") or 1
    try:
        schema_version = int(schema_version)
    except (TypeError, ValueError):
        schema_version = 1
    return {"format": fmt, "diagram": diagram_text, "schema_version": schema_version}


def _normalize_diagram_count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        parsed = int(value)
        return parsed
    except (TypeError, ValueError):
        return None


def _unique_diagram_types(types: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for entry in types:
        if not entry:
            continue
        normalized = entry.strip().lower()
        if not normalized or normalized in {"other", "none"}:
            continue
        if normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _collect_requested_diagram_types(message: str, plan_diagrams: List[Dict[str, Any]] | None) -> List[str]:
    collected: List[str] = []
    if plan_diagrams:
        for entry in plan_diagrams:
            diagram_type = (entry or {}).get("type")
            if diagram_type:
                collected.append(str(diagram_type))
    lowered = (message or "").lower()
    for diagram_type, tokens in _DIAGRAM_TYPE_HINTS.items():
        if any(token in lowered for token in tokens):
            collected.append(diagram_type)
    return _unique_diagram_types(collected)


def _prefers_multiple_generation(diagram_count: int | None, message: str, requested_types: List[str]) -> bool:
    if diagram_count and diagram_count > 1:
        return True
    lowered = (message or "").lower()
    if any(token in lowered for token in _MULTIPLE_DIAGRAM_HINTS):
        return True
    return len(_unique_diagram_types(requested_types)) > 1


def _infer_rendering_service_from_message(message: str) -> str | None:
    lowered = (message or "").lower()
    if "mermaid" in lowered:
        return "mermaid"
    if "plantuml" in lowered or "plant uml" in lowered:
        return "plantuml"
    if "structurizr" in lowered:
        return "structurizr"
    if any(tok in lowered for tok in ["sequence", "flow", "interaction", "story"]):
        return "mermaid"
    return None


def _build_generation_step(requested_types: List[str], prefer_multiple: bool, rendering_service: str | None = None) -> Dict[str, Any]:
    types = _unique_diagram_types(requested_types)
    if not types:
        types = [_DEFAULT_DIAGRAM_TYPE]
    if prefer_multiple:
        arguments = {"diagram_types": types} if types else {}
        if rendering_service:
            arguments["rendering_service"] = rendering_service
        return {"tool": "generate_multiple_diagrams", "arguments": arguments}
    arguments = {"diagram_type": types[0]}
    if rendering_service:
        arguments["rendering_service"] = rendering_service
    return {"tool": "generate_diagram", "arguments": arguments}


def _text_contains(text: str, keywords: List[str]) -> bool:
    lowered = (text or "").lower()
    return any(token in lowered for token in keywords)


def _select_target_image(state: Dict[str, Any], message: str) -> str | None:
    images = state.get("images") or []
    if not images:
        return None
    lowered = (message or "").lower()
    # Prefer diagrams that match explicit hints in the prompt.
    hint_map = [
        ("system", "system"),
        ("container", "container"),
        ("component", "component"),
        ("sequence", "sequence"),
    ]
    for hint, token in hint_map:
        if hint in lowered:
            for item in reversed(images):
                reason = (item.get("reason") or "").lower()
                if token in reason:
                    return item.get("id")
    # Fall back to the most recent diagram.
    return images[-1].get("id")


PLANNER_SYSTEM = (
    "You are a conversation planning agent for an architecture assistant. "
    "Your job is to convert a user message into a structured execution plan. "
    "You MUST choose from the provided MCP tools. "
    "Use ONLY JSON and match this schema:\n"
    "{\n"
    "  \"intent\": \"explain|edit_image|diagram_change|regenerate|clarify|generate_sequence\",\n"
    "  \"diagram_count\": number or null,\n"
    "  \"diagrams\": [\n"
    "    {\"type\": \"system_context|container|component|sequence|flow|other\", \"reason\": \"string\"}\n"
    "  ],\n"
    "  \"target_image_id\": \"uuid or null\",\n"
    "  \"target_diagram_type\": \"system_context|container|component|sequence|other|none\",\n"
    "  \"instructions\": \"string\",\n"
    "  \"requires_regeneration\": true|false,\n"
    "  \"plan\": [\n"
    "    {\"tool\": \"tool_name\", \"arguments\": {}}\n"
    "  ]\n"
    "}\n"
    "Rules:\n"
    "- If explain: intent=explain and plan should call explain_architecture.\n"
    "- If the user provides a GitHub URL: intent=regenerate and plan should call ingest_github_repo, then generate_architecture_plan, followed by whichever of generate_multiple_diagrams or generate_diagram best suits the request.\n"
    "- If the user asks to generate/create a SEQUENCE diagram or PLANTUML diagram or flow diagram, AND state.has_architecture_plan is true: intent=generate_sequence and plan=[{tool: 'generate_sequence_from_architecture', arguments: {}}].\n"
    "- If multiple diagrams are needed: use generate_multiple_diagrams and include diagram_types in tool arguments.\n"
    "- If a single diagram type is requested: use generate_diagram.\n"
    "- When choosing a renderer, set rendering_service in tool arguments (auto|plantuml|mermaid|structurizr).\n"
    "- If diagram type change: intent=diagram_change and plan should call generate_diagram when needed.\n"
    "- If edit image/diagram: intent=edit_image and plan should call edit_diagram_ir when possible.\n"
    "- If regenerate: intent=regenerate and plan should call generate_architecture_plan then generate_multiple_diagrams.\n"
    "- If regenerate: intent=regenerate and plan should call generate_architecture_plan, then select generate_multiple_diagrams or generate_diagram based on how many diagrams are needed.\n"
    "- If unclear: intent=clarify and plan should be empty.\n"
    "- If diagram_count is provided, do not exceed it.\n"
    "- Choose target_image_id as the most recent image unless the user references a specific version.\n"
    "- CRITICAL: When user says 'generate sequence diagram' or 'create plantuml' or similar, and has_architecture_plan=true, you MUST use generate_sequence_from_architecture tool!"
)


def _extract_json(text: str) -> Dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {}
    raw = match.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.replace("“", "\"").replace("”", "\"").replace("’", "'")
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}


def _extract_diagram_count(message: str) -> int | None:
    match = re.search(r"\b(\d+)\s*(diagram|diagrams|diagram(s))\b", message.lower())
    if match:
        try:
            value = int(match.group(1))
            return value if value > 0 else None
        except ValueError:
            return None
    return None


def _safe_list(items: List[Dict[str, Any]], keys: List[str]) -> List[Dict[str, Any]]:
    cleaned = []
    for item in items:
        cleaned.append({k: item.get(k) for k in keys})
    return cleaned


def _has_style_step(plan_steps: List[Dict[str, Any]]) -> bool:
    return any((step.get("tool") or "").startswith("styling.apply_") for step in plan_steps)


class ConversationPlannerAgent:
    """LLM-powered planner for conversation routing."""

    def _maybe_apply_style_followup(self, plan_dict: Dict[str, Any], message: str, state: Dict[str, Any]) -> Dict[str, Any]:
        if not plan_dict:
            return plan_dict
        if not _text_contains(message, _STYLE_KEYWORDS):
            return plan_dict
        plan_steps = list(plan_dict.get("plan", []) or [])
        if _has_style_step(plan_steps):
            return plan_dict
        state_images = state.get("images", []) or []
        has_existing_images = bool(state_images)
        has_generation_step = any(step.get("tool") in _GENERATION_TOOLS for step in plan_steps)
        if not has_generation_step and not has_existing_images:
            return plan_dict
        target_diagram_id: str | None = None
        if has_generation_step:
            target_diagram_id = LATEST_IMAGE_PLACEHOLDER
        elif has_existing_images:
            target_diagram_id = state_images[-1].get("id")
        if not target_diagram_id:
            return plan_dict
        style_step = {
            "tool": "styling.apply_post_svg",
            "arguments": {
                "diagramId": target_diagram_id,
                "userPrompt": message,
                "stylingIntent": message,
                "mode": "post-svg",
            },
        }
        plan_steps.append(style_step)
        plan_dict["plan"] = plan_steps
        metadata = plan_dict.setdefault("metadata", {}) or {}
        metadata.setdefault("style_prompt", message)
        plan_dict["metadata"] = metadata
        plan_dict.setdefault("intent", plan_dict.get("intent", "diagram_change"))
        return plan_dict

    def _normalize_plan_steps(self, plan_steps: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for step in plan_steps or []:
            if not isinstance(step, dict):
                normalized.append(step)
                continue
            entry = dict(step)
            entry["arguments"] = dict(entry.get("arguments") or {})
            llm_payload = _normalize_llm_diagram_payload(entry.get("llm_diagram"))
            if llm_payload:
                entry["llm_diagram"] = llm_payload
                entry["format"] = llm_payload["format"]
            else:
                entry.pop("llm_diagram", None)
            tool_name = str(entry.get("tool") or "")
            entry["rendering_service"] = _normalize_rendering_service(tool_name, entry.get("rendering_service"), (llm_payload or {}).get("format"))
            normalized.append(entry)
        return normalized

    def plan(self, message: str, state: Dict[str, Any], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        plan_id_value = str(uuid4())
        heuristic_plan = self._apply_local_heuristics(plan_id_value, message, state)
        if heuristic_plan:
            plan_with_style = self._maybe_apply_style_followup(heuristic_plan, message, state)
            plan_with_style["plan"] = self._normalize_plan_steps(plan_with_style.get("plan"))
            return plan_with_style

        diagram_count_hint = _extract_diagram_count(message)
        if not settings.openai_api_key:
            # Deterministic fallback when no OpenAI key is available.
            # If the user provided a GitHub URL, return a regenerate plan
            # that ingests the repo and generates diagrams.
            lowered = (message or "").lower()
            requested_types = _collect_requested_diagram_types(message, [])
            prefer_multiple = _prefers_multiple_generation(diagram_count_hint, message, requested_types)
            rendering_service = _infer_rendering_service_from_message(message)
            generation_step = _build_generation_step(requested_types, prefer_multiple, rendering_service)
            diagram_pref_meta = {
                "requested_types": _unique_diagram_types(requested_types) or [_DEFAULT_DIAGRAM_TYPE],
                "prefer_multiple": prefer_multiple,
            }
            if "github.com" in lowered:
                deterministic = {
                    "plan_id": plan_id_value,
                    "intent": "regenerate",
                    "diagram_count": diagram_count_hint,
                    "diagrams": [{"type": diagram_pref_meta["requested_types"][0], "reason": "github regenerate"}],
                    "target_image_id": None,
                    "target_diagram_type": diagram_pref_meta["requested_types"][0],
                    "instructions": message,
                    "requires_regeneration": True,
                    "plan": [
                        {"tool": "ingest_github_repo", "arguments": {"repo_url": message}},
                        {"tool": "generate_architecture_plan", "arguments": {}},
                        generation_step,
                    ],
                    "metadata": {"source": "deterministic", "reason": "missing_openai_key", "diagram_preferences": diagram_pref_meta},
                }
            else:
                deterministic = {
                "plan_id": plan_id_value,
                "intent": "clarify",
                "diagram_count": diagram_count_hint,
                "diagrams": [],
                "target_image_id": None,
                "target_diagram_type": "none",
                "instructions": "Missing OPENAI_API_KEY.",
                "requires_regeneration": False,
                "plan": [],
                "metadata": {"source": "deterministic", "reason": "missing_openai_key"},
                }
            plan_with_style = self._maybe_apply_style_followup(deterministic, message, state)
            plan_with_style["plan"] = self._normalize_plan_steps(plan_with_style.get("plan"))
            return plan_with_style
        client = get_openai_client()

        plan_summary = None
        if isinstance(state.get("architecture_plan"), dict):
            plan_data = state.get("architecture_plan") or {}
            plan_summary = {
                "system_name": plan_data.get("system_name"),
                "diagram_views": plan_data.get("diagram_views"),
                "diagram_kind": plan_data.get("diagram_kind"),
            }
        prompt = {
            "message": message,
            "tools": tools,
            "state": {
                "active_image_id": state.get("active_image_id"),
                "diagram_types": state.get("diagram_types", []),
                "images": _safe_list(state.get("images", []), ["id", "version", "reason", "file_path"]),
                "history": state.get("history", []),
                "github_url": state.get("github_url"),
                "has_architecture_plan": bool(state.get("architecture_plan")),
                "input_text": state.get("input_text"),
                "architecture_plan_summary": plan_summary,
            },
            "requested_diagram_count": diagram_count_hint,
        }

        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            temperature=0.2,
        )

        raw = response.choices[0].message.content or "{}"
        data = _extract_json(raw)
        # Post-process LLM output and add safeguards.
        plan_steps = data.get("plan", []) or []
        lowered = (message or "").lower()

        diagram_count_value = _normalize_diagram_count(data.get("diagram_count"))
        if diagram_count_value is None:
            diagram_count_value = diagram_count_hint
        requested_types = _collect_requested_diagram_types(message, data.get("diagrams"))
        prefer_multiple_generation = _prefers_multiple_generation(diagram_count_value, message, requested_types)
        rendering_service_hint = _infer_rendering_service_from_message(message)
        generation_step_template = _build_generation_step(requested_types, prefer_multiple_generation, rendering_service_hint)

        # Utility: extract a GitHub URL if present
        gh_match = re.search(r"https?://github\.com/[^\s]+", message or "", re.IGNORECASE)
        github_url = gh_match.group(0) if gh_match else None

        # Detect intent-like tokens beyond just 'github.com' and 'generate'
        intent_tokens = ["generate", "diagram", "diagrams", "sequence", "mermaid", "plantuml", "plant uml", "flow", "create", "render"]
        mentions_intent = any(tok in lowered for tok in intent_tokens)

        has_ingest = any(p.get("tool") == "ingest_github_repo" for p in plan_steps)
        has_gen_plan = any(p.get("tool") in {"generate_architecture_plan", "generate_multiple_diagrams", "generate_diagram", "generate_sequence_from_architecture", "generate_plantuml_sequence"} for p in plan_steps)

        # If a GitHub URL is present and ingestion is planned but generation is missing,
        # append generation steps to make the plan actionable.
        if (github_url or state.get("github_url")) and has_ingest and not has_gen_plan:
            # Avoid duplicates: only add if not already present
            if not any(p.get("tool") == "generate_architecture_plan" for p in plan_steps):
                plan_steps.append({"tool": "generate_architecture_plan", "arguments": {}})
            if not any(p.get("tool") == generation_step_template["tool"] for p in plan_steps):
                plan_steps.append(generation_step_template)

        # If user explicitly requested sequence/mermaid/plantuml and we have an architecture plan
        # prefer a direct sequence generation tool when missing.
        has_arch_plan = bool(state.get("has_architecture_plan") or state.get("architecture_plan"))
        wants_sequence = any(tok in lowered for tok in ["sequence", "mermaid", "plantuml", "plant uml", "flow", "interaction"]) or (mentions_intent and "sequence" in (data.get("diagrams") or []))
        if wants_sequence and has_arch_plan and not any(p.get("tool") == "generate_sequence_from_architecture" for p in plan_steps):
            # place sequence generator near the front if no generation steps exist
            plan_steps.append({"tool": "generate_sequence_from_architecture", "arguments": {}})

        # If no plan steps were produced but the message clearly requests diagrams, create a safe default plan.
        if not plan_steps and (mentions_intent or github_url):
            if github_url:
                plan_steps = [
                    {"tool": "ingest_github_repo", "arguments": {"repo_url": github_url}},
                    {"tool": "generate_architecture_plan", "arguments": {}},
                    generation_step_template,
                ]
            elif wants_sequence and has_arch_plan:
                plan_steps = [{"tool": "generate_sequence_from_architecture", "arguments": {}}]
            else:
                plan_steps = [generation_step_template]

        # Ensure repo_url is an argument for ingest if we added ingest step without proper args
        for step in plan_steps:
            if step.get("tool") == "ingest_github_repo" and not step.get("arguments", {}).get("repo_url"):
                if github_url:
                    step.setdefault("arguments", {})["repo_url"] = github_url
                else:
                    step.setdefault("arguments", {})["repo_url"] = message

        diagram_pref_meta = {
            "requested_types": _unique_diagram_types(requested_types) or [_DEFAULT_DIAGRAM_TYPE],
            "prefer_multiple": prefer_multiple_generation,
            "diagram_count": diagram_count_value,
        }

        plan_output = {
            "plan_id": plan_id_value,
            "intent": data.get("intent", "clarify"),
            "diagram_count": data.get("diagram_count"),
            "diagrams": data.get("diagrams", []),
            "target_image_id": data.get("target_image_id"),
            "target_diagram_type": data.get("target_diagram_type", "none"),
            "instructions": data.get("instructions", message),
            "requires_regeneration": bool(data.get("requires_regeneration", False)),
            "plan": plan_steps,
            "metadata": {
                "source": "llm",
                "model": settings.openai_model,
                "raw_response": raw,
                "diagram_preferences": diagram_pref_meta,
            },
        }
        plan_with_style = self._maybe_apply_style_followup(plan_output, message, state)
        plan_with_style["plan"] = self._normalize_plan_steps(plan_with_style.get("plan"))
        return plan_with_style

    def _apply_local_heuristics(self, plan_id: str, message: str, state: Dict[str, Any]) -> Dict[str, Any] | None:
        diagram_count = _extract_diagram_count(message)
        has_plan = bool(state.get("architecture_plan"))
        has_images = bool(state.get("images"))

        inline_diagram = _extract_inline_llm_diagram(message)
        if inline_diagram:
            requested_types = _collect_requested_diagram_types(message, [])
            diagram_type = requested_types[0] if requested_types else _DEFAULT_DIAGRAM_TYPE
            plan_steps = [
                {
                    "tool": "generate_plantuml",
                    "arguments": {
                        "diagram_type": diagram_type,
                        "format": inline_diagram["format"],
                    },
                    "rendering_service": "llm_mermaid" if inline_diagram["format"] == "mermaid" else "llm_plantuml",
                    "llm_diagram": {
                        "format": inline_diagram["format"],
                        "diagram": inline_diagram["diagram"],
                        "schema_version": 1,
                    },
                }
            ]
            return {
                "plan_id": plan_id,
                "intent": "user_supplied_diagram",
                "diagram_count": 1,
                "diagrams": [{"type": diagram_type, "reason": "inline diagram"}],
                "target_image_id": None,
                "target_diagram_type": diagram_type,
                "instructions": message,
                "requires_regeneration": False,
                "plan": plan_steps,
                "metadata": {"source": "heuristic", "heuristic": "inline_llm_diagram"},
            }

        if has_images and _text_contains(message, _VISUAL_KEYWORDS):
            target_image_id = _select_target_image(state, message)
            if target_image_id:
                return {
                    "plan_id": plan_id,
                    "intent": "style_diagram",
                    "diagram_count": diagram_count or 1,
                    "diagrams": [{"type": "existing", "reason": "visual styling"}],
                    "target_image_id": target_image_id,
                    "target_diagram_type": "existing",
                    "instructions": message,
                    "requires_regeneration": False,
                    "plan": [
                        {
                            "tool": "styling.apply_post_svg",
                            "arguments": {
                                "diagramId": target_image_id,
                                "userPrompt": message,
                                "stylingIntent": message,
                                "mode": "post",
                            },
                        }
                    ],
                    "metadata": {"source": "heuristic", "heuristic": "styling"},
                }

        if (not has_plan and not state.get("diagram_types")) and _text_contains(message, _DIAGRAM_REQUEST_KEYWORDS):
            content_value = state.get("input_text") or message
            requested_types = _collect_requested_diagram_types(message, [])
            prefer_multiple = _prefers_multiple_generation(diagram_count, message, requested_types)
            rendering_service = _infer_rendering_service_from_message(message)
            generation_step = _build_generation_step(requested_types, prefer_multiple, rendering_service)
            plan_steps = [
                {"tool": "generate_architecture_plan", "arguments": {"content": content_value}},
                generation_step,
            ]
            return {
                "plan_id": plan_id,
                "intent": "regenerate",
                "diagram_count": diagram_count,
                "diagrams": [],
                "target_image_id": None,
                "target_diagram_type": "none",
                "instructions": message,
                "requires_regeneration": True,
                "plan": plan_steps,
                "metadata": {
                    "source": "heuristic",
                    "heuristic": "bootstrap",
                    "diagram_preferences": {
                        "requested_types": _unique_diagram_types(requested_types) or [_DEFAULT_DIAGRAM_TYPE],
                        "prefer_multiple": prefer_multiple,
                    },
                },
            }

        return None
