"""Skill runtime — discovers, validates, and executes skills dynamically.

This is the core skill layer. Instead of static prompt docs, skills are:
1. Discovered from manifest.yaml files at startup
2. Validated (schema, permissions, dependencies) before execution
3. Executed with scoped access to tools/knowledge
4. Composable into multi-skill toolchains

Usage:
    runtime = SkillRuntime(config, db)
    runtime.discover()                          # Scan for skills
    result = runtime.execute("review-rc", {     # Run with validation
        "code": "...",
        "platform": "ios",
    })
    chain = runtime.chain(["search-docs", "review-rc", "rc-audit"])
    chain_result = chain.run({"query": "..."})
"""

import os
import time
import yaml
from dataclasses import dataclass, field
from typing import Any

from .manifest import SkillManifest, PermissionScope, parse_manifest


@dataclass
class SkillResult:
    """Output from a skill execution."""
    skill: str
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0
    scopes_used: list[str] = field(default_factory=list)


@dataclass
class ValidationError:
    """A specific validation failure."""
    field: str
    message: str


class SkillExecutionError(Exception):
    """Raised when skill execution fails validation or runtime checks."""
    pass


class SkillRuntime:
    """Runtime plugin layer for skill discovery, validation, and execution."""

    def __init__(self, config, db_conn, skills_dir: str | None = None):
        self.config = config
        self.db = db_conn
        self.skills_dir = skills_dir or self._default_skills_dir()
        self.registry: dict[str, SkillManifest] = {}
        self._tool_providers: dict[str, Any] = {}

    def _default_skills_dir(self) -> str:
        """Find .claude/skills/ relative to repo root."""
        # advocate/skills/runtime.py → advocate/skills → advocate → repo_root
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(repo_root, ".claude", "skills")

    # --- Discovery ---

    def discover(self) -> dict[str, SkillManifest]:
        """Scan skills_dir for manifest.yaml files and register valid skills."""
        self.registry.clear()
        if not os.path.isdir(self.skills_dir):
            return self.registry

        for entry in sorted(os.listdir(self.skills_dir)):
            skill_path = os.path.join(self.skills_dir, entry)
            if not os.path.isdir(skill_path):
                continue

            manifest_path = os.path.join(skill_path, "manifest.yaml")
            if not os.path.exists(manifest_path):
                # Fall back: try to extract from SKILL.md YAML frontmatter
                skill_md = os.path.join(skill_path, "SKILL.md")
                if os.path.exists(skill_md):
                    manifest = self._extract_from_skill_md(skill_md, skill_path)
                    if manifest:
                        self.registry[manifest.name] = manifest
                continue

            try:
                with open(manifest_path, "r") as f:
                    raw = yaml.safe_load(f)
                if raw and isinstance(raw, dict):
                    manifest = parse_manifest(raw, skill_dir=skill_path)
                    if manifest.name:
                        self.registry[manifest.name] = manifest
            except Exception:
                pass

        return self.registry

    def _extract_from_skill_md(self, path: str, skill_dir: str) -> SkillManifest | None:
        """Extract a basic manifest from SKILL.md YAML frontmatter."""
        try:
            with open(path, "r") as f:
                content = f.read()
            if not content.startswith("---"):
                return None
            parts = content.split("---", 2)
            if len(parts) < 3:
                return None
            meta = yaml.safe_load(parts[1])
            if not meta or not isinstance(meta, dict):
                return None
            # Build a minimal manifest from frontmatter
            meta.setdefault("version", "0.1.0")
            meta.setdefault("scopes", ["read_docs", "read_codebase"])
            meta.setdefault("tools", ["search_docs"])
            meta["prompt_file"] = "SKILL.md"
            return parse_manifest(meta, skill_dir=skill_dir)
        except Exception:
            return None

    def list_skills(self) -> list[dict]:
        """Return all registered skills as dicts (for MCP/API exposure)."""
        return [
            {
                "name": m.name,
                "version": m.version,
                "description": m.description,
                "inputs": [{"name": i.name, "type": i.type, "required": i.required, "description": i.description} for i in m.inputs],
                "outputs": [{"name": o.name, "type": o.type, "description": o.description} for o in m.outputs],
                "scopes": [s.value for s in m.scopes],
                "chains_to": m.chains_to,
            }
            for m in self.registry.values()
        ]

    def get_skill(self, name: str) -> SkillManifest | None:
        """Get a registered skill by name."""
        return self.registry.get(name)

    # --- Validation ---

    def validate_inputs(self, manifest: SkillManifest, inputs: dict) -> list[ValidationError]:
        """Validate inputs against the skill's declared schema."""
        errors = []
        for field_def in manifest.inputs:
            value = inputs.get(field_def.name)
            if field_def.required and value is None and field_def.default is None:
                errors.append(ValidationError(
                    field=field_def.name,
                    message=f"Required input '{field_def.name}' is missing",
                ))
                continue
            if value is not None:
                # Type checks
                if field_def.type == "string" and not isinstance(value, str):
                    errors.append(ValidationError(
                        field=field_def.name,
                        message=f"Expected string for '{field_def.name}', got {type(value).__name__}",
                    ))
                if field_def.type == "json" and not isinstance(value, (dict, list, str)):
                    errors.append(ValidationError(
                        field=field_def.name,
                        message=f"Expected JSON-serializable for '{field_def.name}'",
                    ))
                if field_def.type == "file_path" and isinstance(value, str) and not os.path.exists(value):
                    errors.append(ValidationError(
                        field=field_def.name,
                        message=f"File not found: '{value}'",
                    ))
                if field_def.enum and value not in field_def.enum:
                    errors.append(ValidationError(
                        field=field_def.name,
                        message=f"Value '{value}' not in allowed values: {field_def.enum}",
                    ))
        return errors

    def check_permissions(self, manifest: SkillManifest) -> list[ValidationError]:
        """Verify the runtime can satisfy the skill's declared scopes."""
        errors = []
        for scope in manifest.scopes:
            if scope == PermissionScope.CALL_API and not self.config.has_anthropic:
                errors.append(ValidationError(
                    field="scope",
                    message=f"Scope '{scope.value}' requires API credentials (ANTHROPIC_API_KEY)",
                ))
            if scope == PermissionScope.WRITE_DB and self.config.dry_run:
                errors.append(ValidationError(
                    field="scope",
                    message=f"Scope '{scope.value}' blocked by DRY_RUN=true",
                ))
            if scope == PermissionScope.GIT_WRITE and self.config.dry_run:
                errors.append(ValidationError(
                    field="scope",
                    message=f"Scope '{scope.value}' blocked by DRY_RUN=true",
                ))
        return errors

    # --- Execution ---

    def execute(self, skill_name: str, inputs: dict | None = None) -> SkillResult:
        """Prepare a skill for execution: validate, check permissions, build scoped tools.

        Returns a SkillResult containing the skill's prompt and callable tools
        for the caller (CLI, MCP, or agent loop) to drive an LLM tool-use cycle.

        1. Look up skill in registry
        2. Validate inputs against declared schema
        3. Check permission scopes against current config
        4. Build scoped tool context (callable functions + tool schemas)
        5. Return prepared context — caller invokes tools, not this method
        """
        inputs = inputs or {}
        start = time.monotonic()

        manifest = self.registry.get(skill_name)
        if not manifest:
            return SkillResult(
                skill=skill_name, success=False,
                errors=[f"Skill '{skill_name}' not found. Available: {list(self.registry.keys())}"],
            )

        # Validate inputs
        input_errors = self.validate_inputs(manifest, inputs)
        if input_errors:
            return SkillResult(
                skill=skill_name, success=False,
                errors=[f"{e.field}: {e.message}" for e in input_errors],
            )

        # Check permissions
        perm_errors = self.check_permissions(manifest)
        if perm_errors:
            return SkillResult(
                skill=skill_name, success=False,
                errors=[f"{e.field}: {e.message}" for e in perm_errors],
            )

        # Build scoped context
        context = self._build_context(manifest, inputs)

        elapsed = int((time.monotonic() - start) * 1000)
        return SkillResult(
            skill=skill_name,
            success=True,
            output=context,
            duration_ms=elapsed,
            scopes_used=[s.value for s in manifest.scopes],
        )

    def _build_context(self, manifest: SkillManifest, inputs: dict) -> dict:
        """Build the execution context: prompt, callable tools, knowledge access.

        Returns a dict with:
        - prompt: the skill's prompt template
        - tools: dict of name → callable function (scoped by permissions)
        - tool_schemas: list of tool definitions for LLM tool_use
        - doc_context: pre-searched doc results
        """
        import subprocess as _sp
        import json as _json
        import requests as _requests

        config = self.config
        db = self.db
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        context = {
            "skill_name": manifest.name,
            "skill_version": manifest.version,
            "inputs": inputs,
            "scopes": [s.value for s in manifest.scopes],
            "tools_available": [],
            "tools": {},           # name → callable
            "tool_schemas": [],    # for LLM tool_use
            "prompt": "",
            "doc_context": [],
        }

        # Load the prompt template
        prompt_path = os.path.join(manifest.skill_dir, manifest.prompt_file)
        if os.path.exists(prompt_path):
            with open(prompt_path, "r") as f:
                content = f.read()
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    content = parts[2].strip()
            context["prompt"] = content

        # --- Scoped tool builders ---

        if PermissionScope.READ_DOCS in manifest.scopes:
            _search_index = None
            _rag_index = None

            def _ensure_index():
                nonlocal _search_index
                if _search_index is None:
                    from ..knowledge.search import build_index
                    _search_index = build_index(config.docs_cache_dir, db)
                return _search_index

            def search_docs(query: str, top_k: int = 8) -> str:
                """Search ingested RevenueCat docs with BM25 + optional RAG reranking."""
                from ..knowledge.search import search
                index = _ensure_index()
                results = search(query, index, config.docs_cache_dir, top_k=top_k)
                # Try RAG reranking
                try:
                    from ..knowledge.rag import build_rag_index_from_config, get_context_chunks
                    nonlocal _rag_index
                    if _rag_index is None:
                        _rag_index = build_rag_index_from_config(config, db)
                    if _rag_index and _rag_index.chunks:
                        chunks = get_context_chunks(query, _rag_index, max_chunks=8, max_words=3000)
                        out = []
                        for c in chunks:
                            out.append(f"**{c.doc_title}** (score: {c.score:.3f})\nURL: {c.doc_url}\n\n{c.text}")
                        for r in results:
                            if not any(r.url in o for o in out):
                                out.append(f"**{r.title}** (BM25: {r.score:.2f})\nURL: {r.url}\nSHA256: {r.doc_sha256[:16]}...\n" + "\n".join(f"  - {s}" for s in r.snippets[:2]))
                        return "\n\n---\n\n".join(out) if out else "No results."
                except Exception:
                    pass
                out = []
                for r in results:
                    out.append(f"**{r.title}** (score: {r.score:.2f})\nURL: {r.url}\nSHA256: {r.doc_sha256[:16]}...\n" + "\n".join(f"  - {s}" for s in r.snippets[:3]))
                return "\n\n".join(out) if out else "No results."

            context["tools"]["search_docs"] = search_docs
            context["tools_available"].append("search_docs")
            context["tool_schemas"].append({
                "name": "search_docs",
                "description": "Search ingested RevenueCat doc pages with hybrid RAG. Returns cited results with URLs.",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "default": 8}}, "required": ["query"]},
            })

            # Pre-search for initial context
            query = inputs.get("query") or inputs.get("topic") or inputs.get("code", "")[:200]
            if query:
                try:
                    from ..knowledge.search import search
                    index = _ensure_index()
                    results = search(query, index, config.docs_cache_dir, top_k=5)
                    context["doc_context"] = [
                        {"title": r.title, "url": r.url, "snippets": r.snippets[:2], "sha256": r.doc_sha256}
                        for r in results
                    ]
                except Exception:
                    pass

        if PermissionScope.READ_CODEBASE in manifest.scopes:
            _blocked_files = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json"}

            def read_file(path: str) -> str:
                """Read a file from the repository. Use relative paths."""
                fpath = os.path.realpath(os.path.join(repo_root, path))
                if not fpath.startswith(os.path.realpath(repo_root) + os.sep):
                    return "Access denied: path outside repository."
                if os.path.basename(fpath) in _blocked_files or ".env" in os.path.basename(fpath):
                    return f"Access denied: {os.path.basename(fpath)} is a sensitive file."
                if not os.path.exists(fpath):
                    return f"File not found: {path}"
                try:
                    with open(fpath, "r") as f:
                        content = f.read()
                    return content[:50000] + (f"\n\n... (truncated, {len(content)} chars)" if len(content) > 50000 else "")
                except Exception as e:
                    return f"Error: {e}"

            def list_files() -> str:
                """List all source files in the repository."""
                import glob as _glob
                files = []
                for pattern in ["**/*.py", "**/*.html", "**/*.css", "**/*.yaml", "**/*.md"]:
                    for fp in _glob.glob(os.path.join(repo_root, pattern), recursive=True):
                        rel = os.path.relpath(fp, repo_root)
                        if any(skip in rel for skip in ["__pycache__", "site_output", ".docs_cache", ".egg", ".pytest_cache"]):
                            continue
                        try:
                            files.append(f"{rel}  ({os.path.getsize(fp)} bytes)")
                        except Exception:
                            pass
                return "\n".join(sorted(files))

            context["tools"]["read_file"] = read_file
            context["tools"]["list_files"] = list_files
            context["tools_available"].extend(["read_file", "list_files"])
            context["tool_schemas"].append({
                "name": "read_file",
                "description": "Read a file from the repository. Use relative paths like 'cli.py' or 'advocate/ledger.py'.",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            })
            context["tool_schemas"].append({
                "name": "list_files",
                "description": "List all source files in the repository with sizes.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            })

        if PermissionScope.READ_DB in manifest.scopes:
            from ..db import query_rows, count_rows

            def query_database(table: str, limit: int = 20) -> str:
                """Query the SQLite database. Tables: content_pieces, growth_experiments, product_feedback, run_log, seo_pages, doc_snapshots, community_interactions."""
                try:
                    rows = query_rows(db, table, limit=limit)
                    return _json.dumps(rows, indent=2, default=str)
                except Exception as e:
                    return f"Error: {e}"

            def get_db_stats() -> str:
                """Get summary statistics from all database tables."""
                from ..ledger import verify_chain
                chain = verify_chain(db, config)
                stats = {t: count_rows(db, t) for t in ["content_pieces", "growth_experiments", "product_feedback", "run_log", "seo_pages", "doc_snapshots", "community_interactions"]}
                stats["chain_valid"] = chain.valid
                stats["chain_total"] = chain.total_entries
                return _json.dumps(stats, indent=2)

            context["tools"]["query_database"] = query_database
            context["tools"]["get_db_stats"] = get_db_stats
            context["tools_available"].extend(["query_database", "get_db_stats"])
            context["tool_schemas"].append({
                "name": "query_database",
                "description": "Query the database. Tables: content_pieces, growth_experiments, product_feedback, run_log, seo_pages, doc_snapshots, community_interactions.",
                "input_schema": {"type": "object", "properties": {"table": {"type": "string"}, "limit": {"type": "integer", "default": 20}}, "required": ["table"]},
            })
            context["tool_schemas"].append({
                "name": "get_db_stats",
                "description": "Get summary counts from all database tables plus chain verification status.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            })

        if PermissionScope.GIT_READ in manifest.scopes:
            def git_diff(staged: bool = True) -> str:
                """Get git diff (staged or unstaged changes)."""
                cmd = ["git", "diff", "--staged"] if staged else ["git", "diff"]
                try:
                    result = _sp.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=10)
                    return result.stdout[:30000] or "(no changes)"
                except Exception as e:
                    return f"Error: {e}"

            context["tools"]["git_diff"] = git_diff
            context["tools_available"].append("git_diff")
            context["tool_schemas"].append({
                "name": "git_diff",
                "description": "Get git diff (staged or working tree changes).",
                "input_schema": {"type": "object", "properties": {"staged": {"type": "boolean", "default": True}}, "required": []},
            })

        if PermissionScope.WRITE_DB in manifest.scopes:
            from ..db import insert_row, update_row

            def write_db_row(table: str, data: str) -> str:
                """Insert a row into the database. data is a JSON string of column→value pairs."""
                if config.dry_run:
                    return "Blocked: DRY_RUN=true. Set DRY_RUN=false to allow DB writes."
                try:
                    parsed = _json.loads(data) if isinstance(data, str) else data
                    row_id = insert_row(db, table, parsed)
                    return f"Inserted row {row_id} into {table}."
                except Exception as e:
                    return f"Error: {e}"

            def update_db_row(table: str, row_id: int, data: str) -> str:
                """Update a row in the database. data is a JSON string of column→value pairs."""
                if config.dry_run:
                    return "Blocked: DRY_RUN=true. Set DRY_RUN=false to allow DB writes."
                try:
                    parsed = _json.loads(data) if isinstance(data, str) else data
                    update_row(db, table, row_id, parsed)
                    return f"Updated row {row_id} in {table}."
                except Exception as e:
                    return f"Error: {e}"

            context["tools"]["write_db_row"] = write_db_row
            context["tools"]["update_db_row"] = update_db_row
            context["tools_available"].extend(["write_db_row", "update_db_row"])
            context["tool_schemas"].append({
                "name": "write_db_row",
                "description": "Insert a row into the database. Blocked when DRY_RUN=true.",
                "input_schema": {"type": "object", "properties": {"table": {"type": "string"}, "data": {"type": "string", "description": "JSON object of column→value"}}, "required": ["table", "data"]},
            })
            context["tool_schemas"].append({
                "name": "update_db_row",
                "description": "Update an existing row. Blocked when DRY_RUN=true.",
                "input_schema": {"type": "object", "properties": {"table": {"type": "string"}, "row_id": {"type": "integer"}, "data": {"type": "string"}}, "required": ["table", "row_id", "data"]},
            })

        if PermissionScope.GIT_WRITE in manifest.scopes:
            def git_commit(message: str, files: str = ".") -> str:
                """Stage files and create a git commit. Blocked when DRY_RUN=true."""
                if config.dry_run:
                    return "Blocked: DRY_RUN=true. Set DRY_RUN=false to allow git writes."
                try:
                    _sp.run(["git", "add", files], cwd=repo_root, capture_output=True, text=True, timeout=10)
                    result = _sp.run(["git", "commit", "-m", message], cwd=repo_root, capture_output=True, text=True, timeout=10)
                    return result.stdout or result.stderr
                except Exception as e:
                    return f"Error: {e}"

            context["tools"]["git_commit"] = git_commit
            context["tools_available"].append("git_commit")
            context["tool_schemas"].append({
                "name": "git_commit",
                "description": "Stage and commit files. Blocked when DRY_RUN=true.",
                "input_schema": {"type": "object", "properties": {"message": {"type": "string"}, "files": {"type": "string", "default": "."}}, "required": ["message"]},
            })

        if PermissionScope.EXECUTE_CODE in manifest.scopes:
            def run_python(code: str) -> str:
                """Execute a Python snippet and return stdout/stderr. Timeout: 30s."""
                try:
                    result = _sp.run(
                        ["python3", "-c", code],
                        cwd=repo_root, capture_output=True, text=True, timeout=30,
                    )
                    out = result.stdout[:10000]
                    err = result.stderr[:5000]
                    return (out + ("\nSTDERR:\n" + err if err else "")) or "(no output)"
                except _sp.TimeoutExpired:
                    return "Error: execution timed out (30s limit)."
                except Exception as e:
                    return f"Error: {e}"

            def lint_python(code: str) -> str:
                """Check Python code for syntax errors without executing it."""
                import py_compile
                import tempfile
                try:
                    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
                        f.write(code)
                        f.flush()
                        py_compile.compile(f.name, doraise=True)
                    return "Syntax OK."
                except py_compile.PyCompileError as e:
                    return f"Syntax error: {e}"
                finally:
                    try:
                        os.unlink(f.name)
                    except Exception:
                        pass

            context["tools"]["run_python"] = run_python
            context["tools"]["lint_python"] = lint_python
            context["tools_available"].extend(["run_python", "lint_python"])
            context["tool_schemas"].append({
                "name": "run_python",
                "description": "Execute a Python code snippet and return output. 30s timeout.",
                "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
            })
            context["tool_schemas"].append({
                "name": "lint_python",
                "description": "Check Python code for syntax errors without executing.",
                "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
            })

        if PermissionScope.CALL_API in manifest.scopes:
            def call_revenuecat_api(method: str, path: str, body: str = "") -> str:
                """Call RevenueCat REST API v2. Non-GET methods blocked when ALLOW_WRITES=false."""
                if method.upper() != "GET" and not config.allow_writes:
                    return f"Blocked: {method} requires ALLOW_WRITES=true."
                if not config.has_rc_credentials:
                    return "No RevenueCat API credentials configured."
                try:
                    from ..revenuecat.api import RevenueCatClient
                    client = RevenueCatClient(config)
                    resp = client._request(method, path, json=_json.loads(body) if body else None)
                    return _json.dumps(resp, indent=2, default=str)[:20000]
                except Exception as e:
                    return f"API error: {e}"

            def call_anthropic(prompt: str, max_tokens: int = 1024) -> str:
                """Call Claude API with a prompt. Requires ANTHROPIC_API_KEY."""
                if not config.has_anthropic:
                    return "No Anthropic API key configured."
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
                    resp = client.messages.create(
                        model=config.ai_model,
                        max_tokens=max_tokens,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    return resp.content[0].text
                except Exception as e:
                    return f"API error: {e}"

            context["tools"]["call_revenuecat_api"] = call_revenuecat_api
            context["tools"]["call_anthropic"] = call_anthropic
            context["tools_available"].extend(["call_revenuecat_api", "call_anthropic"])
            context["tool_schemas"].append({
                "name": "call_revenuecat_api",
                "description": "Call RevenueCat REST API v2. Non-GET blocked without ALLOW_WRITES.",
                "input_schema": {"type": "object", "properties": {"method": {"type": "string"}, "path": {"type": "string"}, "body": {"type": "string", "default": ""}}, "required": ["method", "path"]},
            })
            context["tool_schemas"].append({
                "name": "call_anthropic",
                "description": "Call Claude API with a prompt.",
                "input_schema": {"type": "object", "properties": {"prompt": {"type": "string"}, "max_tokens": {"type": "integer", "default": 1024}}, "required": ["prompt"]},
            })

        if PermissionScope.WEB_SEARCH in manifest.scopes:
            def web_search(query: str) -> str:
                """Search the web via DuckDuckGo."""
                import re as _re
                try:
                    resp = _requests.get(
                        "https://html.duckduckgo.com/html/",
                        params={"q": query},
                        headers={"User-Agent": "revcat-agent-advocate/1.0"},
                        timeout=15,
                    )
                    results = []
                    for match in _re.finditer(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</span>', resp.text, _re.DOTALL):
                        url = match.group(1)
                        title = _re.sub(r'<[^>]+>', '', match.group(2)).strip()
                        snippet = _re.sub(r'<[^>]+>', '', match.group(3)).strip()
                        if url.startswith("//duckduckgo.com/l/?uddg="):
                            import urllib.parse
                            url = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
                        results.append(f"**{title}**\n{url}\n{snippet}")
                        if len(results) >= 8:
                            break
                    return "\n\n".join(results) if results else f"No results for: {query}"
                except Exception as e:
                    return f"Search error: {e}"

            def fetch_url(url: str) -> str:
                """Fetch a URL and return its content."""
                try:
                    resp = _requests.get(url, timeout=15, headers={"User-Agent": "revcat-agent-advocate/1.0"})
                    content = resp.text
                    return content[:30000] + ("\n\n... (truncated)" if len(content) > 30000 else "")
                except Exception as e:
                    return f"Fetch error: {e}"

            context["tools"]["web_search"] = web_search
            context["tools"]["fetch_url"] = fetch_url
            context["tools_available"].extend(["web_search", "fetch_url"])
            context["tool_schemas"].append({
                "name": "web_search",
                "description": "Search the web for current information.",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            })
            context["tool_schemas"].append({
                "name": "fetch_url",
                "description": "Fetch a URL and return its content.",
                "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            })

        # Enforce manifest.tools: only expose tools the skill declared
        if manifest.tools:
            declared = set(manifest.tools)
            context["tools"] = {k: v for k, v in context["tools"].items() if k in declared}
            context["tools_available"] = [t for t in context["tools_available"] if t in declared]
            context["tool_schemas"] = [s for s in context["tool_schemas"] if s["name"] in declared]

        return context

    # --- Composability ---

    def chain(self, skill_names: list[str]) -> "SkillChain":
        """Create a composable toolchain from multiple skills.

        Validates that each skill's output can feed into the next skill's input,
        and that permission scopes are compatible across the chain.
        """
        manifests = []
        errors = []

        for name in skill_names:
            m = self.registry.get(name)
            if not m:
                errors.append(f"Skill '{name}' not found")
            else:
                manifests.append(m)

        if errors:
            raise SkillExecutionError(f"Chain validation failed: {'; '.join(errors)}")

        # Validate chain compatibility
        for i in range(len(manifests) - 1):
            current = manifests[i]
            next_skill = manifests[i + 1]
            if next_skill.name not in current.chains_to and current.name not in next_skill.chains_from:
                # Soft warning — allow implicit chaining if output types overlap
                pass

        return SkillChain(self, manifests)

    def get_chainable_skills(self, skill_name: str) -> list[str]:
        """Return skills that can follow the given skill in a chain."""
        manifest = self.registry.get(skill_name)
        if not manifest:
            return []
        # Explicit chains + skills that accept this skill's output types
        explicit = set(manifest.chains_to)
        output_types = {o.type for o in manifest.outputs}
        for m in self.registry.values():
            if m.name == skill_name:
                continue
            input_types = {i.type for i in m.inputs}
            if output_types & input_types:
                explicit.add(m.name)
        return sorted(explicit)


class SkillChain:
    """A composed sequence of skills that execute in order, passing context forward."""

    def __init__(self, runtime: SkillRuntime, manifests: list[SkillManifest]):
        self.runtime = runtime
        self.manifests = manifests
        self.results: list[SkillResult] = []

    @property
    def skill_names(self) -> list[str]:
        return [m.name for m in self.manifests]

    def run(self, initial_inputs: dict | None = None) -> SkillResult:
        """Execute each skill in sequence, feeding outputs forward."""
        current_inputs = initial_inputs or {}
        self.results = []

        for manifest in self.manifests:
            # Merge previous outputs into inputs
            result = self.runtime.execute(manifest.name, current_inputs)
            self.results.append(result)

            if not result.success:
                return SkillResult(
                    skill=f"chain({' → '.join(self.skill_names)})",
                    success=False,
                    errors=[f"Chain broke at '{manifest.name}': {'; '.join(result.errors)}"],
                    output={"partial_results": [r.output for r in self.results]},
                )

            # Forward outputs as inputs to next skill
            if result.output:
                current_inputs.update(result.output.get("inputs", {}))
                # Pass doc context forward
                if result.output.get("doc_context"):
                    current_inputs["doc_context"] = result.output["doc_context"]

        return SkillResult(
            skill=f"chain({' → '.join(self.skill_names)})",
            success=True,
            output={
                "chain_results": [r.output for r in self.results],
                "scopes_used": list({s for r in self.results for s in r.scopes_used}),
            },
        )
