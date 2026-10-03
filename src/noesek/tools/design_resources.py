"""Verified design-resource registry for the agent (owner-requested VIBE-video sites).

Each entry records only facts read from the site, docs or on-disk LICENSE
during research (source URLs below); anything not verified says so. The agent
uses this to choose a resource when building UI, and gets the exact install
step or the honest "hosted tool, no verified API" limit. Manus is excluded by
the owner's order; the video's "Manifold" builder is left unconnected because
its identity was never confirmed.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

RESOURCES: dict[str, dict] = {
    "shadcn": {
        "name": "shadcn/ui", "url": "https://ui.shadcn.com/docs", "kind": "component_registry",
        "license": "unverified here (docs page read; repo LICENSE not checked)",
        "install": "npx shadcn@latest init",
        "agent_use": "Default component source for React/Tailwind builds; also the registry format Bklit and Kokonut publish into. Open code: copy and edit the files.",
        "limits": "Needs a Node project with Tailwind; the agent cannot run npx without a code workspace.",
        "source": "https://ui.shadcn.com/docs",
    },
    "motion": {
        "name": "Motion (formerly Framer Motion)", "url": "https://motion.dev", "kind": "animation_library",
        "license": "MIT per motion.dev homepage",
        "install": "npm install motion",
        "agent_use": "Animations in React: import { motion } from \"motion/react\". Animate transform and opacity; pair with prefers-reduced-motion (taste_check flags missing fallbacks).",
        "limits": "Client-side JS dependency.",
        "source": "https://motion.dev, https://motion.dev/docs/react-quick-start",
    },
    "bklit_ui": {
        "name": "Bklit UI", "url": "https://bklit.com", "kind": "component_registry",
        "license": "MIT for chart components (packages/ui, on-disk LICENSE); Bklit Studio is proprietary (LICENSE-STUDIO.md): do not copy or redistribute it",
        "install": "npx shadcn@latest add @bklit/line-chart",
        "agent_use": "Chart components for dashboards via the shadcn registry.",
        "limits": "Studio (ui.bklit.com/studio) is off-limits for reuse; registry path only.",
        "source": "https://github.com/bklit/bklit-ui, https://bklit.com/docs/installation",
    },
    "kokonut_ui": {
        "name": "Kokonut UI", "url": "https://kokonutui.com", "kind": "component_registry",
        "license": "MIT (on-disk LICENSE)",
        "install": "npx shadcn@latest add @kokonutui/toolbar",
        "agent_use": "Tailwind + shadcn + Motion components (navigation, UI blocks). Swap the component name in the install command.",
        "limits": "Check each component's page before use.",
        "source": "https://github.com/kokonut-labs/kokonutui, https://kokonutui.com/docs/navigation/toolbar",
    },
    "haikei": {
        "name": "Haikei", "url": "https://haikei.app", "kind": "hosted_tool",
        "license": "terms not verified; site says free, no signup",
        "install": None,
        "agent_use": "Generates SVG/PNG backgrounds (waves, blobs, low-poly grids, gradients) in a web UI. The agent can recommend a generator and settings; the user exports the SVG, then the agent embeds it.",
        "limits": "No verified API; generating needs a browser session, not a tool call.",
        "source": "https://haikei.app",
    },
    "spline": {
        "name": "Spline", "url": "https://spline.design", "kind": "hosted_tool",
        "license": "terms not verified",
        "install": None,
        "agent_use": "Browser 3D design tool for interactive scenes and templates. The agent can plan a scene and the embed point; the user builds or remixes it in Spline.",
        "limits": "No verified API or export format read; do not promise automation.",
        "source": "https://spline.design",
    },
}
EXCLUDED = {"manus": "excluded by the owner's instruction",
            "manifold": "name heard in a transcript; identity unconfirmed, intentionally not connected"}


class DesignResourcesInput(BaseModel):
    action: str = Field(description="list | get | recommend")
    resource: str = Field(default="", description="get: resource id")
    need: str = Field(default="", max_length=300, description="recommend: what is being built")


_KEYS = {"chart": ["bklit_ui", "shadcn"], "dashboard": ["bklit_ui", "shadcn"],
         "animation": ["motion"], "animate": ["motion"], "background": ["haikei"],
         "wave": ["haikei"], "3d": ["spline"], "navigation": ["kokonut_ui", "shadcn"],
         "component": ["shadcn", "kokonut_ui"], "button": ["shadcn", "kokonut_ui"],
         "form": ["shadcn"], "landing": ["shadcn", "kokonut_ui", "motion", "haikei"]}


def design_resources(inp: DesignResourcesInput) -> dict:
    a = inp.action.strip().lower()
    if a == "list":
        return {"resources": {k: {"name": v["name"], "kind": v["kind"], "license": v["license"]}
                              for k, v in RESOURCES.items()}, "excluded": EXCLUDED}
    if a == "get":
        r = RESOURCES.get(inp.resource.strip().lower())
        if r:
            return {"id": inp.resource.strip().lower(), **r}
        if inp.resource.strip().lower() in EXCLUDED:
            return {"excluded": EXCLUDED[inp.resource.strip().lower()]}
        return {"error": f"unknown resource '{inp.resource}'", "resources": sorted(RESOURCES)}
    if a == "recommend":
        need = inp.need.lower()
        picks: list[str] = []
        for key, ids in _KEYS.items():
            if key in need:
                picks += [i for i in ids if i not in picks]
        return {"recommended": [{"id": i, "install": RESOURCES[i]["install"], "why": RESOURCES[i]["agent_use"]}
                                for i in picks] or [],
                "note": "" if picks else "no keyword match; use list"}
    return {"error": f"unknown action '{inp.action}'", "actions": ["list", "get", "recommend"]}
