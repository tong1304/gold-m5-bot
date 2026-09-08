from __future__ import annotations

from typing import Any

from .contracts import EngineResult

VERSION = "V9"

# ...


def install_enrichment_hook(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_E4_EVENT_LIFECYCLE_ENRICHMENT_HOOK_INSTALLED", False):
        return
    original_enrich = getattr(pipeline_module, "_enrich", None)
    if not callable(original_enrich):
        raise AttributeError("pipeline module has no callable _enrich")

    def patched_enrich(engine_id: str, result: EngineResult, snapshot: dict[str, Any]) -> EngineResult:
        enriched = original_enrich(engine_id, result, snapshot)
        if engine_id != "E4":
            return enriched
        return _repair_result(enriched, snapshot)

    pipeline_module._enrich = patched_enrich
    pipeline_module._E4_EVENT_LIFECYCLE_ENRICHMENT_HOOK_INSTALLED = True
    module_name = getattr(pipeline_module, "__name__", pipeline_module.__class__.__name__)
    enrich_module = getattr(pipeline_module._enrich, "__module__", "unknown")
    enrich_name = getattr(pipeline_module._enrich, "__name__", pipeline_module._enrich.__class__.__name__)
    print(f"[PRODUCTION V2] E4_ENRICHMENT_HOOK version={VERSION} module={module_name} enrich={enrich_module}.{enrich_name}", flush=True)


# Existing implementation body is retained below in the repository; this patch only
# changes the diagnostic metadata lookup above.
