"""
Hermes Integration — Complete integration with Hermes Gateway.
Loads all skills, configures agent teams, extends tool registry.
"""
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from core.model_router import route_message, router
from core.paths import project_root


@dataclass
class HermesSkill:
    """Hermes skill definition."""
    name: str
    description: str
    tools: list[str]
    enabled: bool = True
    config: dict = field(default_factory=dict)


@dataclass
class AgentTeam:
    """Agent team configuration."""
    name: str
    description: str
    agents: list[str]  # Agent names
    coordinator: str   # Coordinator agent
    tools: list[str]   # Available tools
    max_turns: int = 10


class HermesIntegration:
    """Complete Hermes Gateway integration for ZARA 3.0."""

    def __init__(self, gateway_url: str = "http://127.0.0.1:8642"):
        self.gateway_url = gateway_url.rstrip("/")
        self.api_key = os.environ.get("HERMES_API_KEY", "zara-hermes-bridge-key-2026")
        self.client: httpx.AsyncClient | None = None

        # Loaded components
        self.skills: dict[str, HermesSkill] = {}
        self.agent_teams: dict[str, AgentTeam] = {}
        self.tools_registry: dict[str, dict] = {}
        self.custom_tools: dict[str, Callable] = {}

        # State
        self.is_connected = False
        self.enabled = False
        self.last_health_check = 0

    async def initialize(self):
        """Initialize Hermes integration."""
        self.client = httpx.AsyncClient(
            base_url=self.gateway_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30.0,
        )

        # Check connection
        await self.health_check()

        if self.is_connected:
            # Load all skills
            await self.load_skills()
            # Configure agent teams
            await self.configure_agent_teams()
            # Extend tool registry
            await self.extend_tool_registry()
            # Register ZARA custom tools
            self.register_zara_tools()

            print(f"[Hermes] Integration initialized: {len(self.skills)} skills, {len(self.agent_teams)} teams, {len(self.tools_registry)} tools")
        else:
            print("[Hermes] Gateway not available, running in standalone mode")

    async def health_check(self) -> bool:
        """Check if Hermes gateway is healthy."""
        try:
            resp = await self.client.get("/health", timeout=5.0)
            self.is_connected = resp.status_code == 200
            return self.is_connected
        except Exception:
            self.is_connected = False
            return False


    async def enable_supercerebro(self) -> bool:
        """Enable ZARA -> Hermes routing and ensure the local gateway is reachable.

        This never terminates or takes ownership of Hermes Desktop; it only
        controls whether ZARA is allowed to route requests through the gateway.
        """
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.gateway_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30.0,
            )

        if not await self.health_check():
            try:
                from integrations.hermes.ensure_gateway import start_gateway
                started = await asyncio.to_thread(start_gateway, self.gateway_url)
            except Exception as exc:
                print(f"[Hermes] Could not start gateway: {exc}")
                started = False
            if not started or not await self.health_check():
                self.enabled = False
                return False

        # Refresh capabilities when the gateway becomes available.
        await self.load_skills()
        await self.configure_agent_teams()
        await self.extend_tool_registry()
        self.register_zara_tools()
        self.enabled = True
        print("[Hermes] Supercerebro enabled")
        return True

    async def disable_supercerebro(self) -> bool:
        """Disable ZARA -> Hermes routing without shutting down Hermes Desktop."""
        self.enabled = False
        print("[Hermes] Supercerebro disabled")
        return True

    async def load_skills(self):
        """Load all available skills from Hermes."""
        try:
            resp = await self.client.get("/v1/skills", timeout=10.0)
            if resp.status_code == 200:
                skills_data = resp.json()
                for skill_data in skills_data.get("skills", []):
                    skill = HermesSkill(
                        name=skill_data.get("name", ""),
                        description=skill_data.get("description", ""),
                        tools=skill_data.get("tools", []),
                        enabled=skill_data.get("enabled", True),
                        config=skill_data.get("config", {}),
                    )
                    self.skills[skill.name] = skill

                # Also load from local skills directory
                await self._load_local_skills()
        except Exception as e:
            print(f"[Hermes] Failed to load skills: {e}")

    async def _load_local_skills(self):
        """Load skills from local Hermes skills directory."""
        skills_dir = project_root() / "integrations" / "hermes" / "skills"
        if not skills_dir.exists():
            return

        for skill_file in skills_dir.glob("*.json"):
            try:
                with open(skill_file, encoding="utf-8") as f:
                    skill_data = json.load(f)
                skill = HermesSkill(
                    name=skill_data.get("name", skill_file.stem),
                    description=skill_data.get("description", ""),
                    tools=skill_data.get("tools", []),
                    enabled=skill_data.get("enabled", True),
                    config=skill_data.get("config", {}),
                )
                self.skills[skill.name] = skill
            except Exception as e:
                print(f"[Hermes] Failed to load local skill {skill_file}: {e}")

    async def configure_agent_teams(self):
        """Configure agent teams for different task types."""
        self.agent_teams = {
            "research": AgentTeam(
                name="research",
                description="Deep research and analysis team",
                agents=["researcher", "analyst", "fact_checker"],
                coordinator="researcher",
                tools=["web_search", "web_fetch", "browser_navigate", "browser_extract"],
                max_turns=15,
            ),
            "coding": AgentTeam(
                name="coding",
                description="Code generation, review, and debugging team",
                agents=["coder", "reviewer", "tester"],
                coordinator="coder",
                tools=["terminal", "files_read", "files_write", "code_analyze", "code_lint", "code_test"],
                max_turns=20,
            ),
            "automation": AgentTeam(
                name="automation",
                description="System automation and administration team",
                agents=["sysadmin", "automator"],
                coordinator="sysadmin",
                tools=["terminal", "os_ops", "system_metrics", "system_processes", "scheduler"],
                max_turns=10,
            ),
            "creative": AgentTeam(
                name="creative",
                description="Creative writing and content generation team",
                agents=["writer", "editor", "designer"],
                coordinator="writer",
                tools=["web_search", "files_write", "code_generate"],
                max_turns=10,
            ),
            "general": AgentTeam(
                name="general",
                description="General purpose assistant team",
                agents=["assistant", "planner"],
                coordinator="assistant",
                tools=["web_search", "terminal", "files_read", "files_write", "system_info"],
                max_turns=8,
            ),
        }

    async def extend_tool_registry(self):
        """Extend tool registry with Hermes tools."""
        try:
            resp = await self.client.get("/v1/tools", timeout=10.0)
            if resp.status_code == 200:
                tools_data = resp.json()
                for tool in tools_data.get("tools", []):
                    self.tools_registry[tool["name"]] = tool
        except Exception as e:
            print(f"[Hermes] Failed to load tool registry: {e}")

    def register_zara_tools(self):
        """Register ZARA's custom actions as Hermes tools."""
        from core.actions import get_registry

        action_registry = get_registry()
        for name, spec in action_registry.get_all_specs().items():
            self.tools_registry[f"zara_{name}"] = {
                "name": f"zara_{name}",
                "description": spec.description,
                "parameters": spec.parameters,
                "category": spec.category,
                "source": "zara",
            }

        # Add model router as a tool
        self.tools_registry["zara_route_model"] = {
            "name": "zara_route_model",
            "description": "Automatically route request to best free model based on intent",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "User message to classify"},
                    "context": {"type": "object", "description": "Additional context"},
                    "require_tools": {"type": "boolean", "default": False},
                },
                "required": ["message"],
            },
            "category": "routing",
            "source": "zara",
        }

    async def execute_tool(self, tool_name: str, params: dict) -> dict:
        """Execute a tool via Hermes or locally."""
        # Check if it's a ZARA local tool
        if tool_name.startswith("zara_") and tool_name in self.tools_registry:
            from core.actions import get_registry
            action_registry = get_registry()
            local_name = tool_name[5:]  # Remove "zara_" prefix
            result = action_registry.execute(local_name, **params)
            return {"success": result.success, "output": result.output, "error": result.error}

        # Check if it's the model router tool
        if tool_name == "zara_route_model":
            message = params.get("message", "")
            context = params.get("context", {})
            require_tools = params.get("require_tools", False)

            primary, fallbacks = route_message(message, context, require_tools)
            return {
                "primary": primary.id if primary else None,
                "fallbacks": [f.id for f in fallbacks],
                "task_types": [t.value for t in router.classify_intent(message, context)],
            }

        # Execute via Hermes
        try:
            resp = await self.client.post(
                "/v1/tools/execute",
                json={"tool": tool_name, "parameters": params},
                timeout=60.0,
            )
            return resp.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def send_message(
        self,
        message: str,
        history: list[dict] = None,
        team: str = "general",
        model: str = None,
        stream: bool = False,
    ) -> str | asyncio.AsyncGenerator[str, None]:
        """Send message to Hermes with optional team and model selection."""
        # Auto-select model if not specified
        if not model:
            primary, _ = route_message(message, {"require_tools": team != "general"})
            model = primary.id if primary else "hermes_gateway"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self._get_system_prompt(team)},
                *(history or []),
                {"role": "user", "content": message},
            ],
            "stream": stream,
            "tools": self._get_team_tools(team) if team != "general" else None,
        }

        if stream:
            return self._stream_response(payload)
        else:
            resp = await self.client.post("/v1/chat/completions", json=payload, timeout=120.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return f"Error: {resp.status_code}"

    def _get_system_prompt(self, team: str) -> str:
        """Get system prompt for agent team."""
        prompts = {
            "research": "You are a research specialist. Use web search, browsing, and extraction tools to find accurate, up-to-date information. Cite sources.",
            "coding": "You are a senior software engineer. Write clean, tested, documented code. Use terminal, file operations, and code analysis tools.",
            "automation": "You are a system administrator. Automate tasks safely. Use terminal, OS operations, and scheduling tools.",
            "creative": "You are a creative writer. Generate engaging, original content. Use web research for inspiration.",
            "general": "You are ZARA, a helpful AI assistant. Be concise, accurate, and use tools when needed.",
        }
        return prompts.get(team, prompts["general"])

    def _get_team_tools(self, team: str) -> list[str]:
        """Get tool list for agent team."""
        team_config = self.agent_teams.get(team)
        if team_config:
            return team_config.tools
        return []

    async def _stream_response(self, payload: dict) -> asyncio.AsyncGenerator[str, None]:
        """Stream response from Hermes."""
        async with self.client.stream("POST", "/v1/chat/completions", json=payload, timeout=120.0) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            yield content
                    except Exception:
                        pass

    async def get_agent_status(self) -> dict:
        """Get status of all agent teams."""
        return {
            "connected": self.is_connected,
            "enabled": self.enabled,
            "skills_loaded": len(self.skills),
            "teams_configured": len(self.agent_teams),
            "tools_available": len(self.tools_registry),
            "teams": {
                name: {
                    "description": team.description,
                    "agents": team.agents,
                    "coordinator": team.coordinator,
                    "tools_count": len(team.tools),
                }
                for name, team in self.agent_teams.items()
            },
        }

    async def shutdown(self):
        """Shutdown Hermes integration."""
        if self.client:
            await self.client.aclose()
            self.client = None
        self.is_connected = False


# Global instance
hermes_integration: HermesIntegration | None = None


async def init_hermes(gateway_url: str = "http://127.0.0.1:8642") -> HermesIntegration:
    """Initialize global Hermes integration."""
    global hermes_integration
    hermes_integration = HermesIntegration(gateway_url)
    await hermes_integration.initialize()
    return hermes_integration


def get_hermes() -> HermesIntegration | None:
    """Get global Hermes integration instance."""
    return hermes_integration
