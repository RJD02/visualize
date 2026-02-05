"""Sequence diagram agent that generates meaningful flows from architecture context."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from openai import OpenAI

from src.utils.config import settings


SEQUENCE_GEN_SYSTEM = """You are a sequence diagram generation agent for software architecture.
Your job is to generate meaningful sequence diagrams based on the architecture plan.

Given an architecture plan with systems, services, and relationships, generate a sequence diagram
that shows realistic user interactions and data flows.

Return a JSON object with this structure:
{
  "title": "Brief title for the sequence",
  "participants": [
    {"id": "user", "name": "User", "type": "actor"},
    {"id": "api", "name": "API Gateway", "type": "system"}
  ],
  "steps": [
    {"from": "user", "to": "api", "message": "Request data", "order": 1},
    {"from": "api", "to": "service", "message": "Process request", "order": 2}
  ]
}

Guidelines:
- Use realistic interaction patterns (user → api → service → database)
- Include authentication/authorization steps if relevant
- Show error handling paths when appropriate
- Make participant names match the architecture plan
- Order steps sequentially (1, 2, 3...)
- Limit to 8-12 steps for clarity
"""


class SequenceGenerationAgent:
    """LLM-powered agent for generating sequence diagrams from architecture context."""

    def generate(
        self,
        architecture_plan: Dict[str, Any],
        github_url: Optional[str] = None,
        user_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a sequence diagram from architecture plan.
        
        Args:
            architecture_plan: The architecture plan dict with systems, services, etc.
            github_url: Optional GitHub URL for additional context
            user_message: Optional user message requesting the sequence diagram
            
        Returns:
            Dict with title, participants, and steps for the sequence diagram
        """
        if not settings.openai_api_key:
            return {
                "title": "Default Sequence",
                "participants": [
                    {"id": "user", "name": "User", "type": "actor"},
                    {"id": "system", "name": "System", "type": "system"},
                ],
                "steps": [
                    {"from": "user", "to": "system", "message": "Request", "order": 1},
                    {"from": "system", "to": "user", "message": "Response", "order": 2},
                ],
            }

        client = OpenAI(api_key=settings.openai_api_key)

        # Extract key information from architecture plan
        systems = architecture_plan.get("systems", [])
        services = architecture_plan.get("services", [])
        relationships = architecture_plan.get("relationships", [])
        actors = architecture_plan.get("actors", [])

        prompt = {
            "architecture": {
                "systems": [{"id": s.get("id"), "name": s.get("name"), "type": s.get("type")} for s in systems],
                "services": [{"id": s.get("id"), "name": s.get("name"), "type": s.get("type")} for s in services],
                "actors": [{"id": a.get("id"), "name": a.get("name")} for a in actors],
                "relationships": relationships,
            },
            "github_url": github_url,
            "user_message": user_message,
            "task": "Generate a meaningful sequence diagram showing a typical user interaction flow",
        }

        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SEQUENCE_GEN_SYSTEM},
                {"role": "user", "content": json.dumps(prompt)},
            ],
            temperature=0.3,
        )

        raw = response.choices[0].message.content or "{}"
        
        # Extract JSON
        import re
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return self._default_sequence(architecture_plan)
        
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return self._default_sequence(architecture_plan)

    def _default_sequence(self, architecture_plan: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a simple default sequence from architecture plan."""
        systems = architecture_plan.get("systems", [])
        services = architecture_plan.get("services", [])
        actors = architecture_plan.get("actors", [])
        
        participants = []
        steps = []
        
        # Add first actor or default user
        if actors:
            participants.append({
                "id": actors[0].get("id", "user"),
                "name": actors[0].get("name", "User"),
                "type": "actor"
            })
        else:
            participants.append({"id": "user", "name": "User", "type": "actor"})
        
        # Add first few systems/services
        order = 1
        prev_id = participants[0]["id"]
        
        for system in systems[:2]:
            sys_id = system.get("id", f"sys_{order}")
            sys_name = system.get("name", f"System {order}")
            participants.append({"id": sys_id, "name": sys_name, "type": "system"})
            steps.append({
                "from": prev_id,
                "to": sys_id,
                "message": f"Request to {sys_name}",
                "order": order
            })
            order += 1
            prev_id = sys_id
        
        for service in services[:2]:
            svc_id = service.get("id", f"svc_{order}")
            svc_name = service.get("name", f"Service {order}")
            participants.append({"id": svc_id, "name": svc_name, "type": "service"})
            steps.append({
                "from": prev_id,
                "to": svc_id,
                "message": f"Process via {svc_name}",
                "order": order
            })
            order += 1
            prev_id = svc_id
        
        return {
            "title": "System Interaction Flow",
            "participants": participants,
            "steps": steps,
        }
