from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection
import numpy as np
import pandas as pd


ROLE_ALPHA = {
    "buildings": 0.90,
    "roads": 0.86,
    "water": 0.55,
    "trees": 0.62,
    "grass": 0.24,
    "terrain": 0.38,
}


def configure_fonts() -> None:
    for font_path in [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]:
        if font_path.exists():
            font_manager.fontManager.addfont(str(font_path))
            font_name = font_manager.FontProperties(fname=str(font_path)).get_name()
            plt.rcParams["font.family"] = font_name
            break
    plt.rcParams["axes.unicode_minus"] = False


def read_layer_colors(path: Path) -> dict[str, tuple[float, float, float, float]]:
    colors: dict[str, tuple[float, float, float, float]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            colors[row["layer"]] = (
                int(row["r"]) / 255,
                int(row["g"]) / 255,
                int(row["b"]) / 255,
                int(row["a"]) / 255,
            )
    return colors


def find_layer(layer_names: list[str], token: str) -> str:
    matches = [layer for layer in layer_names if token in layer]
    if not matches:
        raise KeyError(f"No layer containing {token!r} found in Rhino layer table")
    return matches[0]


def optional_layer(layer_names: list[str], token: str) -> str | None:
    matches = [layer for layer in layer_names if token in layer]
    return matches[0] if matches else None


def sample_frame(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    if len(df) <= limit:
        return df
    return df.iloc[np.linspace(0, len(df) - 1, limit, dtype=int)].copy()


def top_faces(df: pd.DataFrame) -> list[list[tuple[float, float, float]]]:
    faces = []
    for row in df.itertuples(index=False):
        z = float(row.z_max)
        faces.append(
            [
                (float(row.x_min), float(row.y_min), z),
                (float(row.x_max), float(row.y_min), z),
                (float(row.x_max), float(row.y_max), z),
                (float(row.x_min), float(row.y_max), z),
            ]
        )
    return faces


def cuboid_faces(df: pd.DataFrame) -> list[list[tuple[float, float, float]]]:
    faces = []
    for row in df.itertuples(index=False):
        x0, x1 = float(row.x_min), float(row.x_max)
        y0, y1 = float(row.y_min), float(row.y_max)
        z0, z1 = float(row.z_min), float(row.z_max)
        faces.extend(
            [
                [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
                [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
                [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
                [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)],
                [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)],
            ]
        )
    return faces


def add_faces(ax, faces, color, alpha, edge_alpha=0.08, linewidth=0.03):
    if not faces:
        return
    r, g, b, _ = color
    collection = Poly3DCollection(
        faces,
        facecolors=(r, g, b, alpha),
        edgecolors=(r * 0.70, g * 0.70, b * 0.70, edge_alpha),
        linewidths=linewidth,
        zsort="average",
    )
    ax.add_collection3d(collection)


def render(args) -> None:
    configure_fonts()
    colors = read_layer_colors(args.layers)
    terrain = pd.read_csv(args.terrain)
    runs = pd.read_csv(
        args.voxels,
        usecols=["layer", "x_min", "x_max", "y_min", "y_max", "z_min", "z_max", "voxel_count"],
    )
    layer_names = sorted(set(colors).union(set(runs["layer"].astype(str))))
    role_layers = {
        "buildings": find_layer(layer_names, "Buildings_"),
        "building_bases": optional_layer(layer_names, "Building_Bases_"),
        "roads": find_layer(layer_names, "Roads_Hardscape_"),
        "water": find_layer(layer_names, "Water_"),
        "trees": find_layer(layer_names, "Green_Trees_"),
        "grass": find_layer(layer_names, "Green_Grass_"),
        "terrain": find_layer(layer_names, "Terrain_DEM_"),
    }

    xvals = np.sort(terrain["x_m"].unique())
    yvals = np.sort(terrain["y_m"].unique())
    zgrid = terrain.pivot(index="y_m", columns="x_m", values="z_m").loc[yvals, xvals].to_numpy()
    xgrid, ygrid = np.meshgrid(xvals, yvals)

    fig = plt.figure(figsize=(13.5, 10), dpi=180)
    ax = fig.add_subplot(111, projection="3d")

    terrain_color = colors[role_layers["terrain"]]
    ax.plot_surface(
        xgrid,
        ygrid,
        zgrid,
        rstride=2,
        cstride=2,
        color=terrain_color[:3],
        alpha=ROLE_ALPHA["terrain"],
        linewidth=0,
        antialiased=True,
        shade=True,
    )

    grass = sample_frame(runs[runs["layer"] == role_layers["grass"]], 7000)
    water = sample_frame(runs[runs["layer"] == role_layers["water"]], 5000)
    roads = sample_frame(runs[runs["layer"] == role_layers["roads"]], 9000)
    trees = sample_frame(runs[runs["layer"] == role_layers["trees"]], 500)
    buildings = sample_frame(runs[runs["layer"] == role_layers["buildings"]], 6500)
    bases = (
        sample_frame(runs[runs["layer"] == role_layers["building_bases"]], 3500)
        if role_layers["building_bases"]
        else pd.DataFrame(columns=runs.columns)
    )

    add_faces(ax, top_faces(grass), colors[role_layers["grass"]], ROLE_ALPHA["grass"], 0.02)
    add_faces(ax, top_faces(water), colors[role_layers["water"]], ROLE_ALPHA["water"], 0.04)
    add_faces(ax, top_faces(roads), colors[role_layers["roads"]], ROLE_ALPHA["roads"], 0.10, 0.05)
    if role_layers["building_bases"]:
        add_faces(ax, cuboid_faces(bases), colors[role_layers["building_bases"]], 0.32, 0.06, 0.03)
    add_faces(ax, cuboid_faces(trees), colors[role_layers["trees"]], ROLE_ALPHA["trees"], 0.07)
    add_faces(ax, cuboid_faces(buildings), colors[role_layers["buildings"]], ROLE_ALPHA["buildings"], 0.14, 0.05)

    half = float(max(abs(terrain["x_m"]).max(), abs(terrain["y_m"]).max()))
    boundary = [
        [(-half, -half, 0), (half, -half, 0)],
        [(half, -half, 0), (half, half, 0)],
        [(half, half, 0), (-half, half, 0)],
        [(-half, half, 0), (-half, -half, 0)],
    ]
    ax.add_collection3d(Line3DCollection(boundary, colors=[(1.0, 0.82, 0.05, 1.0)], linewidths=2.2))

    z_min = float(runs["z_min"].min())
    z_max = float(runs["z_max"].max())
    ax.set_xlim(-half, half)
    ax.set_ylim(-half, half)
    ax.set_zlim(0, max(70.0, z_max + 3.0))
    ax.set_box_aspect((1, 1, 0.32))
    ax.view_init(elev=34, azim=-50)
    ax.set_xlabel("X local meters")
    ax.set_ylabel("Y local meters")
    ax.set_zlabel("Z meters")
    ax.set_title(args.title, pad=18)

    legend = [
        ("Buildings", "buildings", len(buildings)),
        ("Building bases", "building_bases", len(bases)),
        ("Roads / hardscape", "roads", len(roads)),
        ("Water", "water", len(water)),
        ("Trees", "trees", len(trees)),
        ("Grass / ground cover", "grass", len(grass)),
        ("DEM terrain", "terrain", len(terrain)),
    ]
    handles = []
    labels = []
    for label, role, count in legend:
        if role_layers.get(role) is None:
            continue
        r, g, b, _ = colors[role_layers[role]]
        alpha = 0.45 if role == "building_bases" else max(0.45, ROLE_ALPHA[role])
        handles.append(plt.Rectangle((0, 0), 1, 1, color=(r, g, b, alpha)))
        labels.append(f"{label}: {count} plotted records")
    ax.legend(handles, labels, loc="upper left", framealpha=0.92)

    caption = (
        f"Voxel table records: {len(runs):,} | Rhino layers preserved: {len(colors)} | "
        f"Extent: {half * 2:.0f} m x {half * 2:.0f} m | Z range: {z_max - z_min:.1f} m\n"
        "DEM is shown as a continuous terrain surface; buildings, roads, grass, and trees are drawn from sparse voxel runs."
    )
    fig.text(0.02, 0.035, caption, fontsize=10, color="#333333")
    fig.tight_layout(rect=(0, 0.05, 1, 0.98))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terrain", type=Path, required=True)
    parser.add_argument("--voxels", type=Path, required=True)
    parser.add_argument("--layers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="Voxel Model Review")
    render(parser.parse_args())


if __name__ == "__main__":
    main()
