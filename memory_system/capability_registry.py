import json
import os
import importlib
import inspect
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

class ModelTier(Enum):
    LOCAL_FREE = "local_free"
    FREE_API = "free_api"
    PAID_OPT_IN = "paid_opt_in"

class TaskComplexity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

@dataclass
class Capability:
    id: str
    name: str
    description: str
    model_tier: ModelTier
    complexity: TaskComplexity
    dependencies: List[str]
    enabled: bool = True
    version: str = "1.0.0"

class CapabilityRegistry:
    def __init__(self, registry_path: str = "capabilities.json"):
        self.registry_path = registry_path
        self.capabilities: Dict[str, Capability] = {}
        self._load_registry()
    
    def _load_registry(self):
        if os.path.exists(self.registry_path):
            with open(self.registry_path, 'r') as f:
                data = json.load(f)
                for cap_data in data.get("capabilities", []):
                    capability = Capability(**cap_data)
                    self.capabilities[capability.id] = capability
        else:
            self._create_default_registry()
    
    def _create_default_registry(self):
        default_caps = [
            Capability(
                id="shared_memory",
                name="Shared Memory System",
                description="Operational memory for storing facts about user, environment, and recent interactions",
                model_tier=ModelTier.LOCAL_FREE,
                complexity=TaskComplexity.LOW,
                dependencies=[]
            ),
            Capability(
                id="vigilance",
                name="Useful Vigilance System",
                description="Smart monitoring that triggers only on meaningful changes",
                model_tier=ModelTier.LOCAL_FREE,
                complexity=TaskComplexity.LOW,
                dependencies=[]
            ),
            Capability(
                id="skill_creator",
                name="Skill Creation System",
                description="Ability to create, update, and manage skills for extending functionality",
                model_tier=ModelTier.LOCAL_FREE,
                complexity=TaskComplexity.MEDIUM,
                dependencies=["shared_memory"]
            ),
            Capability(
                id="code_reviewer",
                name="Code Review Assistant",
                description="Reviews code for quality, bugs, and improvements",
                model_tier=ModelTier.FREE_API,
                complexity=TaskComplexity.HIGH,
                dependencies=["shared_memory"]
            ),
            Capability(
                id="task_planner",
                name="Task Planning System",
                description="Breaks down complex goals into actionable steps",
                model_tier=ModelTier.LOCAL_FREE,
                complexity=TaskComplexity.MEDIUM,
                dependencies=["shared_memory"]
            )
        ]
        
        self.capabilities = {cap.id: cap for cap in default_caps}
        self._save_registry()
    
    def _save_registry(self):
        data = {
            "capabilities": [asdict(cap) for cap in self.capabilities.values()]
        }
        with open(self.registry_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def get_capability(self, capability_id: str) -> Optional[Capability]:
        return self.capabilities.get(capability_id)
    
    def list_capabilities(self, model_tier: Optional[ModelTier] = None, 
                         complexity: Optional[TaskComplexity] = None) -> List[Capability]:
        results = list(self.capabilities.values())
        if model_tier:
            results = [cap for cap in results if cap.model_tier == model_tier]
        if complexity:
            results = [cap for cap in results if cap.complexity == complexity]
        return results
    
    def enable_capability(self, capability_id: str):
        if capability_id in self.capabilities:
            self.capabilities[capability_id].enabled = True
            self._save_registry()
    
    def disable_capability(self, capability_id: str):
        if capability_id in self.capabilities:
            self.capabilities[capability_id].enabled = False
            self._save_registry()
    
    def get_routing_suggestion(self, task_description: str) -> Dict[str, Any]:
        # Simple keyword-based routing for demonstration
        task_lower = task_description.lower()
        
        if any(word in task_lower for word in ["code", "program", "debug", "refactor", "fix"]):
            suggested_cap = self.get_capability("code_reviewer")
        elif any(word in task_lower for word in ["plan", "organize", "schedule", "break down"]):
            suggested_cap = self.get_capability("task_planner")
        elif any(word in task_lower for word in ["learn", "remember", "recall", "fact"]):
            suggested_cap = self.get_capability("shared_memory")
        elif any(word in task_lower for word in ["watch", "monitor", "alert", "change"]):
            suggested_cap = self.get_capability("vigilance")
        else:
            suggested_cap = self.get_capability("shared_memory")  # default
        
        if not suggested_cap:
            suggested_cap = list(self.capabilities.values())[0]
        
        return {
            "suggested_capability": suggested_cap.id,
            "model_tier": suggested_cap.model_tier.value,
            "complexity": suggested_cap.complexity.value,
            "reasoning": f"Selected based on task description keywords"
        }

# Global registry instance
registry = CapabilityRegistry()

def get_capability_registry():
    return registry

if __name__ == "__main__":
    # Example usage
    reg = CapabilityRegistry()
    print("Available capabilities:")
    for cap in reg.list_capabilities():
        status = "ENABLED" if cap.enabled else "DISABLED"
        print(f"- {cap.name} ({cap.id}): {status}")
    
    print("\nRouting suggestion for 'review this Python code':")
    suggestion = reg.get_routing_suggestion("review this Python code")
    print(f"Suggested capability: {suggestion['suggested_capability']}")
    print(f"Model tier: {suggestion['model_tier']}")
    print(f"Complexity: {suggestion['complexity']}")