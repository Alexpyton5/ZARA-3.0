"""Backend-owned allowlist; model output can request actions, never grant access."""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path


class ScopeViolation(ValueError):
    pass


def canonical_resource(value: str) -> str:
    if not isinstance(value, str) or not value or '*' in value:
        raise ScopeViolation('An explicit resource is required')
    if value.startswith('provider:'):
        return value
    path = Path(value)
    if not path.is_absolute():
        raise ScopeViolation('Filesystem resources must be absolute')
    if os.name == 'nt' and (path.is_reserved() or ':' in str(path)[len(path.drive):]
                            or str(path).startswith(('\\\\', '//'))):
        raise ScopeViolation('Device paths, network shares and alternate streams are forbidden')
    # Reject links/junctions rather than granting their targets implicitly.
    for part in (path, *path.parents):
        attrs = getattr(part.lstat(), 'st_file_attributes', 0) if part.exists() else 0
        if part.is_symlink() or attrs & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
            raise ScopeViolation('Linked resources are outside the execution boundary')
    return os.path.normcase(str(path.resolve()))


@dataclass(frozen=True)
class ExecutionScope:
    allowed_resources: tuple[str, ...] = ()
    allowed_capabilities: tuple[str, ...] = ()
    forbidden_capabilities: tuple[str, ...] = ('shell.unrestricted', 'credentials.write')
    risk: str = 'LOW'
    authorization_state: str = 'DENIED'
    authorization_ref: str = ''

    def validate(self):
        if self.risk not in ('LOW', 'MEDIUM', 'HIGH'):
            raise ScopeViolation('Unknown risk')
        if self.authorization_state not in ('DENIED', 'POLICY_AUTHORIZED', 'OWNER_AUTHORIZED'):
            raise ScopeViolation('Unknown authorization state')
        if any(not isinstance(c, str) or not c or '*' in c
               for c in (*self.allowed_capabilities, *self.forbidden_capabilities)):
            raise ScopeViolation('Capabilities must be explicit')
        for resource in self.allowed_resources:
            canonical_resource(resource)

    def require(self, capability: str, resources: tuple[str, ...], risk: str):
        self.validate()
        if self.authorization_state == 'DENIED' or not self.authorization_ref:
            raise ScopeViolation('Authorization is required')
        levels = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
        if risk not in levels or levels[risk] > levels[self.risk]:
            raise ScopeViolation('Requested risk exceeds mission policy')
        if risk == 'HIGH' and self.authorization_state != 'OWNER_AUTHORIZED':
            raise ScopeViolation('High risk requires owner authorization')
        if capability not in self.allowed_capabilities or capability in self.forbidden_capabilities:
            raise ScopeViolation('Capability is outside mission scope')
        if not resources:
            raise ScopeViolation('Requested resources are required')
        allowed = [canonical_resource(r) for r in self.allowed_resources]
        for resource in resources:
            target = canonical_resource(resource)
            if not any(target == root or (not root.startswith('provider:') and
                       not target.startswith('provider:') and Path(root) in Path(target).parents)
                       for root in allowed):
                raise ScopeViolation('Resource is outside mission scope')
