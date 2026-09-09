"""Build-only vector preparation; never modifies the saved geography."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

# The symbol's viewBox maps to a square viewport with xMidYMid meet.
ART = {
    "mountain": (
        24,
        28,
        23,
        -14,
        -18,
        0.7,
        [
            ("#183e47", [(-14, 5), (-2, -18), (14, 5)], True),
            ("#0d303a", [(-2, -18), (1, 5), (14, 5)], True),
            ("#a1b3b3", [(-2, -18), (-7, -9), (-2, -11), (2, -7)], True),
        ],
    ),
    "forest": (
        18,
        30,
        28,
        -16,
        -16,
        0.48,
        [
            (
                "#153c43",
                [(-8, -16), (-14, -4), (-10, -4), (-16, 5), (0, 5), (-6, -4), (-2, -4)],
                True,
            ),
            ("#0a2e36", [(3, -12), (-3, 0), (1, 0), (-5, 9), (13, 9), (7, 0), (11, 0)], True),
            ("#759092", [(-8, 4), (-8, 8)], False),
            ("#759092", [(4, 7), (4, 11)], False),
        ],
    ),
}


def sparse_decor(world: dict[str, Any]) -> list:
    if world.get("decor_density") == 0.5:
        return world["decor"]
    counts: dict[str, int] = defaultdict(int)
    result = []
    for item in world["decor"]:
        counts[item[0]] += 1
        if counts[item[0]] % 2:
            result.append(item)
    return result


def scenery(world: dict[str, Any]) -> list[dict[str, Any]]:
    """Batch non-overlapping symbols so group opacity preserves compositing.

    Clip primitives to the symbol viewport, matching SVG symbol overflow behavior.
    """
    batches: list[dict[str, Any]] = []
    for kind, x, y, size in sparse_decor(world):
        dim, vw, vh, vx, vy, opacity, shapes = ART[kind]
        span = dim * size
        bounds = (x - span / 2, y - span / 2, x + span / 2, y + span / 2)
        # Preserve painter order for any overlapping symbols, including other kinds.
        last = max(
            (
                i
                for i, b in enumerate(batches)
                if any(
                    bounds[0] < r[2] and bounds[2] > r[0] and bounds[1] < r[3] and bounds[3] > r[1]
                    for r in b["boxes"]
                )
            ),
            default=-1,
        )
        batch: Any = next((b for b in batches[last + 1 :] if b["opacity"] == opacity), None)
        if batch is None:
            new_batch: dict[str, Any] = {"opacity": opacity, "boxes": [], "paths": defaultdict(str)}
            batch = new_batch
            batches.append(batch)
        batch["boxes"].append(bounds)
        scale = span / max(vw, vh)
        ox, oy = x - vw * scale / 2 - vx * scale, y - vh * scale / 2 - vy * scale
        for fill, points, closed in shapes:
            transformed = [(ox + a * scale, oy + b * scale) for a, b in points]
            if closed:
                transformed = clip_polygon(transformed, bounds)
            # Trunks extend beyond the viewBox and are clipped too.
            else:
                transformed = [(a, min(b, bounds[3])) for a, b in transformed]
            if not transformed:
                continue
            path = "M" + "L".join(f"{a:.2f},{b:.2f}" for a, b in transformed)
            if closed:
                path += "Z"
            key = (fill, 0 if closed else round(1.2 * scale, 4))
            batch["paths"][key] += path
    return [
        {
            "opacity": b["opacity"],
            "paths": [
                {"color": color, "stroke": stroke, "d": d}
                for (color, stroke), d in b["paths"].items()
            ],
        }
        for b in batches
    ]


def clip_polygon(points: list, bounds: tuple) -> list:
    for axis, edge, sign in (
        (0, bounds[0], 1),
        (0, bounds[2], -1),
        (1, bounds[1], 1),
        (1, bounds[3], -1),
    ):
        result = []
        for a, b in zip(points, points[1:] + points[:1]):
            inside_a, inside_b = (a[axis] - edge) * sign >= 0, (b[axis] - edge) * sign >= 0
            if inside_a:
                result.append(a)
            if inside_a != inside_b:
                t = (edge - a[axis]) / (b[axis] - a[axis])
                result.append(tuple(a[k] + t * (b[k] - a[k]) for k in (0, 1)))
        points = result
    return points


def prepare_world(world: dict[str, Any]) -> dict[str, Any]:
    result = dict(world)
    result["scenery"] = scenery(world)
    result["decor_count"] = len(sparse_decor(world))
    result.pop("decor")
    result["overview"] = {
        k: [overview_curve(p) for p in world[k]] for k in ("land", "lakes", "rivers")
    }
    return result


def distance(point: tuple, a: tuple, b: tuple) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = (
        max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy)))
        if dx or dy
        else 0
    )
    return ((point[0] - a[0] - t * dx) ** 2 + (point[1] - a[1] - t * dy) ** 2) ** 0.5


def simplify(points: list, tolerance: float) -> list:
    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        error, index = max((distance(points[i], points[a], points[b]), i) for i in range(a + 1, b))
        if error > tolerance:
            keep.add(index)
            stack.extend(((a, index), (index, b)))
    return [points[i] for i in sorted(keep)]


def overview_curve(path: str) -> str:
    """Flatten cubic curves within .15 world units, then simplify within .35.

    Countries are intentionally untouched. At overview zoom the combined error is
    subpixel on the measured viewport; small rings and unsupported paths stay exact.
    """
    if set(re.findall(r"[A-Za-z]", path)) - {"M", "C", "Z"}:
        return path
    tokens = re.findall(r"[MCZ]|-?\d+(?:\.\d+)?", path)
    rings, points = [], []
    i = 0
    while i < len(tokens):
        command = tokens[i]
        i += 1
        if command == "M":
            if points:
                return path
            points = [(float(tokens[i]), float(tokens[i + 1]))]
            i += 2
        elif command == "C" and points:
            control = [(float(tokens[j]), float(tokens[j + 1])) for j in range(i, i + 6, 2)]
            i += 6
            stack = [(points[-1], *control, 0)]
            while stack:
                a, b, c, d, depth = stack.pop()
                if depth >= 12 or max(distance(b, a, d), distance(c, a, d)) <= 0.15:
                    points.append(d)
                else:

                    def mid(u: tuple, v: tuple) -> tuple:
                        return ((u[0] + v[0]) / 2, (u[1] + v[1]) / 2)

                    ab, bc, cd = mid(a, b), mid(b, c), mid(c, d)
                    abc, bcd = mid(ab, bc), mid(bc, cd)
                    center = mid(abc, bcd)
                    stack.extend(((center, bcd, cd, d, depth + 1), (a, ab, abc, center, depth + 1)))
        elif command == "Z" and points:
            if len(points) < 8:
                return path
            if points[-1] != points[0]:
                points.append(points[0])
            half = len(points) // 2
            reduced = simplify(points[: half + 1], 0.35)[:-1] + simplify(points[half:], 0.35)
            if len(set(reduced)) < 3:
                return path
            rings.append("M" + "L".join(f"{x:.2f},{y:.2f}" for x, y in reduced) + "Z")
            points = []
        else:
            return path
    if points:
        reduced = simplify(points, 0.35)
        if len(reduced) < 3:
            return path
        rings.append("M" + "L".join(f"{x:.2f},{y:.2f}" for x, y in reduced))
    return "".join(rings) if rings else path
