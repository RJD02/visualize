"""Icon injector for diagram SVG outputs.

This module is intentionally minimal and deterministic for planning/execution.
It reads local SVG assets from `ui/icons/`, sanitizes them, creates a
document-level <defs id="icon-sprite"> with <symbol> children, and injects
<use> references into node groups identified by IDs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional
from xml.etree import ElementTree as ET

BASE_ICON_DIR = Path("ui/icons")

MAPPING = {
    "postgres": "postgres.svg",
    "kafka": "kafka.svg",
    "minio": "minio.svg",
    "database": "database.svg",
    "cache": "cache.svg",
    "redis": "redis.svg",
    "airflow": "airflow.svg",
    "kubernetes": "kubernetes.svg",
    "grafana": "grafana.svg",
    "prometheus": "prometheus.svg",
    "spark": "spark.svg",
    "mysql": "mysql.svg",
    "mongodb": "mongodb.svg",
    "elasticsearch": "elasticsearch.svg",
    "nginx": "nginx.svg",
    "rabbitmq": "rabbitmq.svg",
    "docker": "docker.svg",
    "aws": "aws.svg",
    "gcp": "gcp.svg",
    "azure": "azure.svg",
}

# Keyword → MAPPING key.  Checked in order; first substring match wins.
# Labels are lowercased before matching.
_KEYWORDS: list[tuple[str, str]] = [
    ("postgres", "postgres"),
    ("postgresql", "postgres"),
    ("kafka", "kafka"),
    ("kinesis", "kafka"),
    ("event hub", "kafka"),
    ("pubsub", "kafka"),
    ("streaming", "kafka"),
    ("redis", "redis"),
    ("valkey", "redis"),
    ("minio", "minio"),
    ("object stor", "minio"),
    ("airflow", "airflow"),
    ("superset", "airflow"),
    ("openmetadata", "airflow"),
    ("prefect", "airflow"),
    ("dagster", "airflow"),
    ("kubernetes", "kubernetes"),
    ("k8s", "kubernetes"),
    ("kube", "kubernetes"),
    ("eks", "kubernetes"),
    ("gke", "kubernetes"),
    ("aks", "kubernetes"),
    ("grafana", "grafana"),
    ("prometheus", "prometheus"),
    ("alertmanager", "prometheus"),
    ("spark", "spark"),
    ("databricks", "spark"),
    ("mysql", "mysql"),
    ("mariadb", "mysql"),
    ("aurora", "mysql"),
    ("mongo", "mongodb"),
    ("elasticsearch", "elasticsearch"),
    ("opensearch", "elasticsearch"),
    ("solr", "elasticsearch"),
    ("nginx", "nginx"),
    ("ingress", "nginx"),
    ("gateway", "nginx"),
    ("haproxy", "nginx"),
    ("envoy", "nginx"),
    ("rabbitmq", "rabbitmq"),
    ("celery", "rabbitmq"),
    ("docker", "docker"),
    ("container", "docker"),
    ("aws", "aws"),
    ("amazon", "aws"),
    ("lambda", "aws"),
    ("gcp", "gcp"),
    ("bigquery", "gcp"),
    ("cloud run", "gcp"),
    ("azure", "azure"),
    ("blob", "azure"),
    ("database", "database"),
    ("cache", "cache"),
    ("memcache", "cache"),
]


def resolve_icon_key(label: str) -> Optional[str]:
    """Return the MAPPING key for *label*, or None if not recognised.

    Performs a case-insensitive substring search against _KEYWORDS in order.
    """
    label_low = label.lower()
    for keyword, key in _KEYWORDS:
        if keyword in label_low:
            return key
    return None


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _sanitize_svg_element(el: ET.Element) -> None:
    # Remove script and foreignObject elements and any on* attributes
    for child in list(el.iter()):
        tag = _strip_ns(child.tag)
        if tag in ("script", "foreignObject"):
            parent = _find_parent(el, child)
            if parent is not None:
                parent.remove(child)
            continue
        # remove event handler attributes
        to_del = [k for k in child.attrib.keys() if k.startswith("on")]
        for k in to_del:
            child.attrib.pop(k, None)


def _find_parent(root: ET.Element, target: ET.Element) -> ET.Element | None:
    for parent in root.iter():
        for child in list(parent):
            if child is target:
                return parent
    return None


def _read_icon_svg(name: str) -> ET.Element:
    path = BASE_ICON_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Icon not found: {path}")
    tree = ET.parse(path)
    root = tree.getroot()
    return root


def _icon_position_from_group(target: ET.Element) -> tuple[float, float, float, float]:
    """Return (x, y, width, height) for the icon <use>, derived from the first
    <rect> found in *target*.  Falls back to (0, 0, 24, 24) if no rect found.
    """
    for child in target.iter():
        if _strip_ns(child.tag) == "rect":
            rx = float(child.attrib.get("x", 0))
            ry = float(child.attrib.get("y", 0))
            rh = float(child.attrib.get("height", 32))
            icon_size = min(rh * 0.65, 32)
            return rx, ry, icon_size, icon_size
    return 0.0, 0.0, 24.0, 24.0


def inject_icons(svg_text: str, node_service_map: Dict[str, str]) -> str:
    """Inject icons into `svg_text`.

    node_service_map: mapping from node element id in the SVG to a service token
    (e.g., {"node-1": "postgres"}). The injector will add a single <defs>
    sprite and then insert a <use> referencing the symbol into the node <g>.
    """
    root = ET.fromstring(svg_text)

    # find or create defs
    defs = None
    for child in root.findall("{http://www.w3.org/2000/svg}defs") + root.findall("defs"):
        if child.attrib.get("id") == "icon-sprite":
            defs = child
            break
    if defs is None:
        defs = ET.Element("defs", {"id": "icon-sprite"})
        root.insert(0, defs)

    # Pre-populate from symbols already present in the sprite (idempotence guard)
    used_symbol_ids: set[str] = set()
    for existing in list(defs):
        sid = existing.attrib.get("id")
        if sid:
            used_symbol_ids.add(sid)

    for node_id, token in node_service_map.items():
        # Resolve token → MAPPING key using keyword matching, then direct lookup
        resolved_key = resolve_icon_key(token) or token.lower().strip()
        mapped = MAPPING.get(resolved_key)
        if mapped:
            fname = mapped
            symbol_id = f"icon-{resolved_key}"
        else:
            fname = "service-generic.svg"
            symbol_id = "icon-service-generic"

        if symbol_id not in used_symbol_ids:
            try:
                icon_root = _read_icon_svg(fname)
            except FileNotFoundError:
                # If the requested icon file is missing, try the generic fallback.
                try:
                    icon_root = _read_icon_svg("service-generic.svg")
                except FileNotFoundError:
                    icon_root = ET.Element("svg")
            # sanitize icon
            _sanitize_svg_element(icon_root)

            # create symbol and copy children
            symbol = ET.Element("symbol", {"id": symbol_id})
            # copy viewBox if present
            if "viewBox" in icon_root.attrib:
                symbol.attrib["viewBox"] = icon_root.attrib["viewBox"]
            for c in list(icon_root):
                symbol.append(c)
            defs.append(symbol)
            used_symbol_ids.add(symbol_id)

        # find node element by id
        target = None
        for el in root.iter():
            if el.attrib.get("id") == node_id:
                target = el
                break
        if target is None:
            # try data-service attribute matching
            for el in root.iter():
                if el.attrib.get("data-service") == resolved_key:
                    target = el
                    break
        if target is None:
            continue

        # idempotence: check marker or existing <use> referencing this symbol
        already_injected = target.attrib.get("data-icon-injected") == "1"
        if not already_injected:
            for child in list(target):
                # check both href and xlink:href
                href = child.attrib.get("href") or child.attrib.get("{http://www.w3.org/1999/xlink}href") or child.attrib.get("xlink:href")
                if href == f"#{symbol_id}":
                    already_injected = True
                    break
        if already_injected:
            continue

        # Compute position from the bounding rect inside the node group
        ix, iy, iw, ih = _icon_position_from_group(target)

        # create <use> with both href and xlink:href for compatibility
        use = ET.Element("use", {
            "href": f"#{symbol_id}",
            "class": "node-icon",
            "x": str(ix),
            "y": str(iy),
            "width": str(iw),
            "height": str(ih),
        })
        # set xlink:href attribute in the proper namespace
        use.attrib["{http://www.w3.org/1999/xlink}href"] = f"#{symbol_id}"
        # place use as first child of target
        target.insert(0, use)
        target.attrib["data-icon-injected"] = "1"
        target.attrib["data-icon-symbol"] = symbol_id

    return ET.tostring(root, encoding="unicode")
