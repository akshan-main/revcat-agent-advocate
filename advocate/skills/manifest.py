"""Skill manifest schema — defines what a skill declares about itself.

Each skill lives in a directory with a manifest.yaml that declares:
- identity (name, version, description)
- input/output schemas (JSON Schema)
- required permissions/scopes
- tool dependencies (what knowledge/API access it needs)
- composability (what skills it can chain into)
"""

from dataclasses import dataclass, field
from enum import Enum


class PermissionScope(str, Enum):
    """What a skill is allowed to access."""
    READ_DOCS = "read_docs"           # Search/read ingested doc corpus
    READ_CODEBASE = "read_codebase"   # Read files in user's project
    READ_DB = "read_db"               # Query the advocate DB
    WRITE_DB = "write_db"             # Insert/update DB rows
    CALL_API = "call_api"             # Call external APIs (RC, GitHub, etc.)
    EXECUTE_CODE = "execute_code"     # Run code snippets (linting, syntax check)
    WEB_SEARCH = "web_search"         # Search the web
    GIT_READ = "git_read"             # Read git state (diff, log, status)
    GIT_WRITE = "git_write"           # Modify git state (commit, push)


@dataclass
class IOField:
    """A single input or output field with type and validation."""
    name: str
    type: str                          # "string", "json", "file_path", "code", "markdown"
    description: str = ""
    required: bool = True
    default: str | None = None
    enum: list[str] | None = None      # Allowed values


@dataclass
class SkillManifest:
    """Complete declaration of a skill's contract."""
    # Identity
    name: str
    version: str
    description: str
    # IO contract
    inputs: list[IOField] = field(default_factory=list)
    outputs: list[IOField] = field(default_factory=list)
    # Permissions
    scopes: list[PermissionScope] = field(default_factory=list)
    # Dependencies
    tools: list[str] = field(default_factory=list)     # e.g. ["search_docs", "read_file"]
    # Composability
    chains_from: list[str] = field(default_factory=list)  # Skills that can feed into this
    chains_to: list[str] = field(default_factory=list)    # Skills this can feed into
    # Source
    skill_dir: str = ""                # Absolute path to skill directory
    prompt_file: str = ""              # Path to SKILL.md prompt template


def parse_manifest(manifest_dict: dict, skill_dir: str = "") -> SkillManifest:
    """Parse a manifest dict (from YAML) into a SkillManifest."""
    inputs = [
        IOField(
            name=f["name"],
            type=f.get("type", "string"),
            description=f.get("description", ""),
            required=f.get("required", True),
            default=f.get("default"),
            enum=f.get("enum"),
        )
        for f in manifest_dict.get("inputs", [])
    ]
    outputs = [
        IOField(
            name=f["name"],
            type=f.get("type", "string"),
            description=f.get("description", ""),
            required=f.get("required", False),
        )
        for f in manifest_dict.get("outputs", [])
    ]
    scopes = [
        PermissionScope(s) for s in manifest_dict.get("scopes", [])
        if s in PermissionScope.__members__.values() or s in [e.value for e in PermissionScope]
    ]

    return SkillManifest(
        name=manifest_dict.get("name", ""),
        version=manifest_dict.get("version", "0.1.0"),
        description=manifest_dict.get("description", ""),
        inputs=inputs,
        outputs=outputs,
        scopes=scopes,
        tools=manifest_dict.get("tools", []),
        chains_from=manifest_dict.get("chains_from", []),
        chains_to=manifest_dict.get("chains_to", []),
        skill_dir=skill_dir,
        prompt_file=manifest_dict.get("prompt_file", "SKILL.md"),
    )
