#!/usr/bin/env python3
"""Run one evaluation against the session-free Jaeger MCP server.

Connects to ``<JAEGER_ENDPOINT>/api/ai/mcp/`` (not the ACP sidecar), drives
gemini-3.7-flash at temperature 0 through ``llm.call_llm``, and writes a
trajectory JSON. High-level tool variant is composed client-side from the
real tools in server.go — Jaeger is not forked.

Usage:
  export GEMINI_API_KEY=...
  export JAEGER_ENDPOINT=http://localhost:16686
  python harness/run_eval.py --scenario cart_failure --variant granular
  CAPTURE_FIXTURE=true python harness/run_eval.py --scenario cart_failure
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_DIR = Path(__file__).resolve().parent
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))

from llm import LLMError, _coerce, call_llm, function_response_prompt  # noqa: E402

DEFAULT_JAEGER = os.environ.get("JAEGER_ENDPOINT", "http://localhost:16686")
MCP_PATH = "/api/ai/mcp/"
MAX_STEPS = 15
EVAL_PROMPT = (
    "A user reported errors adding items to their cart. "
    "Identify the root cause using the available tools."
)
VALID_MCP_TOOLS = {
    "get_services",
    "get_span_names",
    "search_traces",
    "get_span_details",
    "get_trace_errors",
    "get_trace_topology",
    "get_critical_path",
    "get_service_dependencies",
    "read_skill",
}
HIGHLEVEL_NAME = "analyze_trace_fault"
BROKEN_SCENARIOS = {"product_catalog_failure"}

# Span-level evidence: operation substring + discriminating status message.
# Operation name alone is not evidence — get_span_names lists it in a catalog.
EVIDENCE = {
    "cart_failure": {
        "span": "oteldemo.CartService/EmptyCart",
        "message": "can't access cart storage",
    },
    "product_catalog_failure": {
        "span": "oteldemo.ProductCatalogService/GetProduct",
        "message": "product catalog fail feature flag enabled",
    },
}

SCENARIO_PROMPTS = {
    "cart_failure": EVAL_PROMPT,
    "product_catalog_failure": (
        "A user reported errors loading a product (id OLJCESPC7Z). "
        "Identify the root cause using the available tools."
    ),
}


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def load_skill(variant: str) -> str | None:
    mapping = {
        "stepwise": HARNESS_DIR / "variants" / "skill_stepwise.md",
        "goaloriented": HARNESS_DIR / "variants" / "skill_goaloriented.md",
        "builtin": None,
    }
    path = mapping.get(variant)
    if path is None:
        return None
    return path.read_text(encoding="utf-8")


def load_highlevel_schema() -> dict[str, Any]:
    path = HARNESS_DIR / "variants" / "tool_highlevel.json"
    return json.loads(path.read_text(encoding="utf-8"))


def mcp_tools_as_llm(tools: list[Any]) -> list[dict[str, Any]]:
    out = []
    for tool in tools:
        out.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": getattr(tool, "inputSchema", None)
                or {"type": "object", "properties": {}},
            }
        )
    return out


def tool_result_text(result: Any) -> tuple[str, bool]:
    chunks: list[str] = []
    is_error = bool(getattr(result, "isError", False))
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        try:
            chunks.append(json.dumps(structured, default=str))
        except TypeError:
            chunks.append(str(structured))
    content = getattr(result, "content", None) or []
    for item in content:
        text = getattr(item, "text", None)
        if text:
            chunks.append(text)
    if not chunks:
        chunks.append(str(result))
    # Prefer structured JSON when both copies are present (go-sdk dual-encode).
    text = chunks[0] if chunks else ""
    return text, is_error


def record_step(
    steps: list[dict[str, Any]],
    tool_name: str,
    arguments: dict[str, Any],
    response_text: str,
    started_ms: int,
    is_error: bool = False,
) -> None:
    steps.append(
        {
            "step": len(steps) + 1,
            "tool_name": tool_name,
            "input": arguments,
            "response_length_tokens": estimate_tokens(response_text),
            "response_summary": response_text[:200],
            "response_excerpt": response_text[:4000],
            "is_error": is_error,
            "timestamp_ms": started_ms,
        }
    )


def deepest_error(errors: dict[str, Any], topology: dict[str, Any]) -> dict[str, Any] | None:
    spans = errors.get("spans") or []
    if not spans:
        return None
    error_ids = {s.get("span_id") for s in spans if s.get("span_id")}
    children_with_errors: set[str] = set()
    for node in topology.get("spans") or []:
        path = (node.get("path") or "").split("/")
        if len(path) >= 2 and path[-1] in error_ids and path[-2] in error_ids:
            children_with_errors.add(path[-2])
    for span in reversed(spans):
        if span.get("span_id") not in children_with_errors:
            return span
    return spans[-1]


def compose_analyze_trace_fault(
    errors: dict[str, Any],
    topology: dict[str, Any],
    critical: dict[str, Any],
) -> dict[str, Any]:
    origin = deepest_error(errors, topology) or {}
    origin_id = origin.get("span_id")
    origin_path = ""
    chain: list[dict[str, Any]] = []
    for node in topology.get("spans") or []:
        path = node.get("path") or ""
        if origin_id and path.endswith(origin_id):
            origin_path = path
            ids = path.split("/")
            by_id = {n.get("path", "").split("/")[-1]: n for n in topology.get("spans") or []}
            for span_id in ids:
                n = by_id.get(span_id)
                if n:
                    chain.append(
                        {
                            "service": n.get("service"),
                            "span_name": n.get("span_name"),
                            "status": n.get("status"),
                        }
                    )
            break
    segments = sorted(
        critical.get("segments") or [],
        key=lambda s: s.get("self_time_us") or 0,
        reverse=True,
    )[:5]
    total = errors.get("total_error_count") or 0
    returned = len(errors.get("spans") or [])
    status = origin.get("status") or {}
    return {
        "trace_id": errors.get("trace_id") or topology.get("trace_id") or critical.get("trace_id"),
        "originating_error": {
            "span_id": origin.get("span_id"),
            "service": origin.get("service"),
            "span_name": origin.get("span_name"),
            "status_code": status.get("code") if isinstance(status, dict) else status,
            "status_message": status.get("message") if isinstance(status, dict) else "",
            "path": origin_path,
        },
        "propagation_chain": chain,
        "critical_path_hotspots": [
            {
                "span_id": s.get("span_id"),
                "service": s.get("service"),
                "span_name": s.get("span_name"),
                "self_time_us": s.get("self_time_us"),
            }
            for s in segments
        ],
        "total_error_count": total,
        "truncated": bool(total and returned < total),
    }


async def call_mcp_tool(session: Any, name: str, arguments: dict[str, Any]) -> Any:
    return await session.call_tool(name, arguments or {})


async def run_highlevel_tool(session: Any, arguments: dict[str, Any]) -> tuple[str, bool]:
    trace_id = arguments.get("trace_id")
    if not trace_id:
        return json.dumps({"error": "trace_id is required"}), True
    payloads = {}
    for name in ("get_trace_errors", "get_trace_topology", "get_critical_path"):
        result = await call_mcp_tool(session, name, {"trace_id": trace_id})
        text, is_error = tool_result_text(result)
        if is_error:
            return text, True
        try:
            payloads[name] = json.loads(text)
        except json.JSONDecodeError:
            payloads[name] = {"raw": text}
    composed = compose_analyze_trace_fault(
        payloads.get("get_trace_errors") or {},
        payloads.get("get_trace_topology") or {},
        payloads.get("get_critical_path") or {},
    )
    return json.dumps(composed), False


async def connect_mcp(url: str) -> tuple[Any, Any]:
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as exc:
        raise ConnectionError(
            "The `mcp` package is not installed. "
            "Run: pip install -r harness/requirements.txt"
        ) from exc

    try:
        cm = streamablehttp_client(url)
        read, write, _ = await cm.__aenter__()
        session = ClientSession(read, write)
        await session.__aenter__()
        await session.initialize()
        return cm, session
    except Exception as exc:
        raise ConnectionError(
            f"Cannot reach Jaeger MCP at {url}. "
            "Start Jaeger with extensions.jaeger_query.ai.mcp: {{}} "
            f"(see docker-compose.yml / jaeger-config.yaml). Detail: {exc}"
        ) from exc


async def fetch_trace_json(jaeger: str, trace_id: str) -> dict[str, Any] | None:
    try:
        import httpx
    except ImportError:
        return None
    urls = [
        f"{jaeger.rstrip('/')}/api/v3/traces/{trace_id}",
        f"{jaeger.rstrip('/')}/api/traces/{trace_id}",
    ]
    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in urls:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.json()
            except Exception:
                continue
    return None


def first_trace_id(steps: list[dict[str, Any]], message: str = "") -> str | None:
    """Prefer a trace_id from a step that already contains the evidence message."""
    ordered = list(steps)
    if message:
        needle = message.lower()
        preferred = [
            step
            for step in steps
            if needle in ((step.get("response_excerpt") or "") + (step.get("response_summary") or "")).lower()
        ]
        ordered = preferred + [s for s in steps if s not in preferred]
    for step in ordered:
        args = step.get("input") or {}
        if args.get("trace_id"):
            return args["trace_id"]
        excerpt = step.get("response_excerpt") or step.get("response_summary") or ""
        if '"trace_id"' in excerpt:
            try:
                payload = json.loads(step.get("response_excerpt") or "")
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("trace_id"):
                return payload["trace_id"]
            traces = payload.get("traces") if isinstance(payload, dict) else None
            if traces:
                return traces[0].get("trace_id")
    return None


def evidence_appeared(steps: list[dict[str, Any]], marker: str, message: str = "") -> bool:
    for step in steps:
        hay = (step.get("response_excerpt") or "") + " " + (step.get("response_summary") or "")
        if marker and marker not in hay:
            continue
        if message and message.lower() not in hay.lower():
            continue
        if marker or message:
            return True
    return False


async def run(args: argparse.Namespace) -> int:
    if args.scenario in BROKEN_SCENARIOS and not args.allow_broken:
        print(
            f"ERROR: scenario {args.scenario!r} is status: broken "
            "(productCatalogFailure flagd targeting is a no-op; "
            "https://github.com/open-telemetry/opentelemetry-demo/issues/3816). "
            "Not a valid benchmark scenario. Pass --allow-broken only after "
            "applying the workaround in scenarios/product_catalog_failure/scenario.md.",
            file=sys.stderr,
        )
        return 2

    jaeger = args.jaeger_endpoint.rstrip("/")
    mcp_url = jaeger + MCP_PATH
    try:
        transport, session = await connect_mcp(mcp_url)
    except ConnectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"MCP: {mcp_url}")
    print(f"LLM: {os.environ.get('LLM_MODEL', 'gemini-3.7-flash')} temperature=0")
    print(f"variant={args.variant} skill={args.skill} scenario={args.scenario}")

    listed = await session.list_tools()
    server_tools = list(listed.tools)
    print(f"Server advertised {len(server_tools)} tools: " + ", ".join(t.name for t in server_tools))

    if args.variant == "highlevel":
        hidden = {
            "get_span_details",
            "get_trace_errors",
            "get_trace_topology",
            "get_critical_path",
        }
        exposed = [t for t in server_tools if t.name not in hidden]
        llm_tools = mcp_tools_as_llm(exposed)
        schema = load_highlevel_schema()
        llm_tools.append(
            {
                "name": schema["name"],
                "description": schema["description"],
                "parameters": schema["inputSchema"],
            }
        )
    else:
        llm_tools = mcp_tools_as_llm(server_tools)

    skill_text = load_skill(args.skill)
    system = (
        "You are evaluating Jaeger MCP tools against a seeded, trace-solvable fault. "
        "Use tools to inspect traces. Name the originating span (service + operation) "
        "and the status message. Do not guess mechanisms that are not on a span. "
        "Flagd / OpenFeature client spans (ResolveBoolean, ResolveFloat) can be Error "
        "and are not the user-visible cart failure — skip them unless the user asked "
        "about feature flags. Prefer traces whose root_span_name matches the reported "
        "operation (EmptyCart, GetProduct). "
        "As soon as a tool response includes an Error span whose status.message names "
        "the failure, stop calling tools and write the final answer."
    )
    if skill_text:
        system = system + "\n\n# Active Skill\n\n" + skill_text

    prompt = SCENARIO_PROMPTS.get(args.scenario, EVAL_PROMPT)
    steps: list[dict[str, Any]] = []
    final_answer = ""
    t0 = time.time()

    try:
        turn, chat = call_llm(prompt, llm_tools, system=system)
    except LLMError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        await _aclose(session, transport)
        return 1

    for _ in range(MAX_STEPS):
        if not turn.tool_calls:
            final_answer = turn.text
            break
        function_parts: list[dict[str, Any]] = []
        for call in turn.tool_calls:
            started = int((time.time() - t0) * 1000)
            name = call.name
            arguments = call.args or {}
            arguments = {k: _coerce(v) for k, v in arguments.items()}
            try:
                if name == HIGHLEVEL_NAME:
                    response_text, is_error = await run_highlevel_tool(session, arguments)
                elif name in {t.name for t in server_tools}:
                    result = await call_mcp_tool(session, name, arguments)
                    response_text, is_error = tool_result_text(result)
                else:
                    response_text = json.dumps({"error": f"unknown tool: {name}"})
                    is_error = True
            except Exception as exc:
                response_text = json.dumps({"error": str(exc)})
                is_error = True
            record_step(steps, name, arguments, response_text, started, is_error=is_error)
            function_parts.extend(function_response_prompt(name, response_text[:8000]))
            print(f"  step {steps[-1]['step']}: {name} tokens={steps[-1]['response_length_tokens']} error={is_error}")

        try:
            turn, chat = call_llm(function_parts, llm_tools, chat=chat)
        except LLMError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            final_answer = turn.text
            break
    else:
        final_answer = turn.text or "(hit MAX_STEPS without a final answer)"

    await _aclose(session, transport)

    payload = {
        "scenario": args.scenario,
        "llm": os.environ.get("LLM_MODEL", "gemini-3.7-flash"),
        "tool_variant": args.variant,
        "skill_variant": args.skill,
        "trajectory": steps,
        "final_answer": final_answer,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    out_path = (
        REPO_ROOT
        / "trajectories"
        / f"{args.scenario}_{args.variant}_{args.skill}.json"
    )
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    total_tokens = sum(s["response_length_tokens"] for s in steps)
    evidence = EVIDENCE.get(args.scenario) or {}
    marker = evidence.get("span", "")
    message = evidence.get("message", "")
    appeared = evidence_appeared(steps, marker, message) if marker else False

    print()
    print(f"Wrote {out_path}")
    print(f"Total tool calls made: {len(steps)}")
    print(f"Total response tokens across all calls: {total_tokens}")
    if marker:
        print(
            f"Whether the root cause appeared in any response "
            f"(marker {marker!r} + message {message!r}): "
            f"{'yes' if appeared else 'no — manual check the trajectory'}"
        )
    else:
        print("Whether the root cause appeared in any response: manual check the trajectory")
    if final_answer:
        print("Final answer (truncated):")
        print(final_answer[:500])

    if os.environ.get("CAPTURE_FIXTURE", "").lower() in {"1", "true", "yes"}:
        trace_id = first_trace_id(steps, message=message)
        fixture_dir = REPO_ROOT / "scenarios" / args.scenario
        fixture_path = fixture_dir / "fixture.otlp.json"
        if not trace_id:
            print("CAPTURE_FIXTURE: no trace_id in trajectory; fixture not updated.")
        else:
            trace = await fetch_trace_json(jaeger, trace_id)
            if trace is None:
                print(f"CAPTURE_FIXTURE: could not fetch {trace_id} from {jaeger}")
            else:
                fixture_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
                print(f"CAPTURE_FIXTURE: wrote {fixture_path}")

    return 0


async def _aclose(session: Any, transport: Any) -> None:
    for obj in (session, transport):
        if obj is None:
            continue
        try:
            await obj.__aexit__(None, None, None)
        except Exception:
            pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="cart_failure")
    parser.add_argument(
        "--variant",
        choices=("granular", "highlevel"),
        default="granular",
        help="granular = live get_span_details surface; highlevel = analyze_trace_fault wrapper",
    )
    parser.add_argument(
        "--skill",
        choices=("stepwise", "goaloriented", "builtin"),
        default="stepwise",
        help="Skill text injected as system instruction. builtin = none (agent may read_skill).",
    )
    parser.add_argument("--jaeger-endpoint", default=DEFAULT_JAEGER)
    parser.add_argument(
        "--allow-broken",
        action="store_true",
        help="Permit running a status: broken scenario after applying its workaround.",
    )
    return parser.parse_args(argv)


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    sys.exit(main())
