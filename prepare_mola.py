import argparse
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image


GLOBAL_PATTERN = re.compile(r"megt(?P<lat>\d{2})(?P<hem>[ns])(?P<lon>\d{3})hb", re.I)
POLAR_PATTERN = re.compile(r"megt_(?P<hem>[ns])_512_1", re.I)
HEIGHT_OFFSET = -10000.0
HEIGHT_SCALE = 10.0
GLOBAL_TILE_SIZE = (512, 256)
POLAR_TILE_SIZE = (256, 256)


def label_value(label: str, key: str, default: str | None = None) -> str:
    match = re.search(rf"^\s*{re.escape(key)}\s*=\s*([^,\r\n]+)", label, re.I | re.M)
    if not match:
        if default is None:
            raise ValueError(f"Falta {key} en la etiqueta PDS.")
        return default
    return match.group(1).strip().strip('"\'')


def number(label: str, key: str, default: float | None = None) -> float:
    value = label_value(label, key, None if default is None else str(default))
    match = re.search(r"[-+]?\d+(?:\.\d+)?", value)
    if not match:
        raise ValueError(f"Valor no numérico para {key}: {value}")
    return float(match.group(0))


def read_label(image_path: Path) -> tuple[np.ndarray, dict[str, float | int | str]]:
    label_path = image_path.with_suffix(".lbl")
    if not label_path.is_file():
        raise FileNotFoundError(f"No se encontró la etiqueta PDS: {label_path}")
    label = label_path.read_text(encoding="ascii", errors="replace")
    lines = int(number(label, "LINES"))
    samples = int(number(label, "LINE_SAMPLES"))
    sample_type = label_value(label, "SAMPLE_TYPE").upper()
    if sample_type == "MSB_INTEGER":
        dtype = ">i2"
    elif sample_type == "MSB_UNSIGNED_INTEGER":
        dtype = ">u2"
    else:
        raise ValueError(f"Tipo de muestra PDS no admitido: {sample_type}")

    expected_size = lines * samples * 2
    actual_size = image_path.stat().st_size
    if actual_size != expected_size:
        raise ValueError(
            f"Tamaño inválido para {image_path.name}: "
            f"{actual_size} bytes; se esperaban {expected_size}."
        )

    data = np.memmap(image_path, dtype=dtype, mode="r", shape=(lines, samples))
    metadata: dict[str, float | int | str] = {
        "lines": lines,
        "samples": samples,
        "scale": number(label, "SCALING_FACTOR", 1.0),
        "offset": number(label, "OFFSET", 0.0),
        "sample_type": sample_type,
    }
    return data, metadata


def height_rgb(values: np.ndarray) -> np.ndarray:
    encoded = np.rint((values.astype(np.float64) - HEIGHT_OFFSET) * HEIGHT_SCALE)
    if not np.isfinite(encoded).all() or np.any(encoded < 0) or np.any(encoded > 0xFFFFFF):
        raise ValueError("Hay alturas fuera del rango representable por RGB24; se cancela para evitar recortes.")
    encoded = encoded.astype(np.uint32)
    rgb = np.empty((*encoded.shape, 3), dtype=np.uint8)
    rgb[..., 0] = (encoded >> 16).astype(np.uint8)
    rgb[..., 1] = (encoded >> 8).astype(np.uint8)
    rgb[..., 2] = encoded.astype(np.uint8)
    return rgb


def save_tile(
    source: np.ndarray,
    scale: float,
    offset: float,
    source_bounds: tuple[float, float, float, float],
    output_size: tuple[int, int],
    destination: Path,
) -> None:
    x0, y0, x1, y1 = source_bounds
    width, height = output_size
    cols = np.minimum(
        source.shape[1] - 1,
        np.floor(x0 + (np.arange(width) + 0.5) * (x1 - x0) / width).astype(np.int32),
    )
    rows = np.minimum(
        source.shape[0] - 1,
        np.floor(y0 + (np.arange(height) + 0.5) * (y1 - y0) / height).astype(np.int32),
    )
    values = source[np.ix_(rows, cols)].astype(np.float32) * scale + offset
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".png.tmp")
    Image.fromarray(height_rgb(values)).save(temporary, format="PNG", compress_level=3)
    os.replace(temporary, destination)


def global_extent(stem: str, label: str) -> tuple[float, float, float, float, str]:
    match = GLOBAL_PATTERN.fullmatch(stem)
    if not match:
        raise ValueError(f"Nombre de tesela global MOLA inválido: {stem}")
    west = number(label, "WESTERNMOST_LONGITUDE")
    east = number(label, "EASTERNMOST_LONGITUDE")
    north = number(label, "MAXIMUM_LATITUDE")
    south = number(label, "MINIMUM_LATITUDE")
    root = f"{match.group('lat')}{match.group('hem').lower()}{match.group('lon')}"
    return west, south, east, north, root


def build_global(image_path: Path, output: Path, max_level: int) -> dict[str, object]:
    label_path = image_path.with_suffix(".lbl")
    label = label_path.read_text(encoding="ascii", errors="replace")
    source, metadata = read_label(image_path)
    west, south, east, north, root = global_extent(image_path.stem, label)
    width, height = GLOBAL_TILE_SIZE
    for level in range(max_level + 1):
        divisions = 1 << level
        for tile_y in range(divisions):
            y0 = tile_y * metadata["lines"] / divisions
            y1 = (tile_y + 1) * metadata["lines"] / divisions
            for tile_x in range(divisions):
                destination = output / "global" / root / str(level) / str(tile_x) / f"{tile_y}.png"
                x0 = tile_x * metadata["samples"] / divisions
                x1 = (tile_x + 1) * metadata["samples"] / divisions
                save_tile(
                    source,
                    float(metadata["scale"]),
                    float(metadata["offset"]),
                    (x0, y0, x1, y1),
                    (width, height),
                    destination,
                )
    del source
    return {
        "id": root,
        "west": west,
        "east": east,
        "north": north,
        "south": south,
        "maxLevel": max_level,
        "tileWidth": width,
        "tileHeight": height,
    }


def build_polar(image_path: Path, output: Path, max_level: int) -> dict[str, object]:
    match = POLAR_PATTERN.fullmatch(image_path.stem)
    if not match:
        raise ValueError(f"Nombre de tesela polar MOLA inválido: {image_path.stem}")
    hemisphere = match.group("hem").lower()
    source, metadata = read_label(image_path)
    width, height = POLAR_TILE_SIZE
    for level in range(max_level + 1):
        divisions = 1 << level
        for tile_y in range(divisions):
            y0 = tile_y * metadata["lines"] / divisions
            y1 = (tile_y + 1) * metadata["lines"] / divisions
            for tile_x in range(divisions):
                destination = (
                    output
                    / "polar"
                    / hemisphere
                    / str(level)
                    / str(tile_x)
                    / f"{tile_y}.png"
                )
                x0 = tile_x * metadata["samples"] / divisions
                x1 = (tile_x + 1) * metadata["samples"] / divisions
                save_tile(
                    source,
                    float(metadata["scale"]),
                    float(metadata["offset"]),
                    (x0, y0, x1, y1),
                    (width, height),
                    destination,
                )
    del source
    return {
        "hemisphere": hemisphere,
        "maxLevel": max_level,
        "tileWidth": width,
        "tileHeight": height,
        "sourceSamples": int(metadata["samples"]),
        "mapScaleKmPerPixel": 0.115,
        "sourceUnits": "m",
        "sourceSampleType": str(metadata["sample_type"]),
        "sourceScale": float(metadata["scale"]),
        "sourceOffset": float(metadata["offset"]),
        "bodyRadiusKm": 3376.2,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convierte productos MOLA MEGT en teselas PNG RGB de altura para Three.js."
    )
    parser.add_argument("--input", type=Path, default=Path("MOLA-raw"))
    parser.add_argument("--output", type=Path, default=Path("MOLA-tiles"))
    parser.add_argument("--global-level", type=int, default=5)
    parser.add_argument("--polar-level", type=int, default=6)
    args = parser.parse_args()
    if args.global_level < 0 or args.polar_level < 0:
        parser.error("Los niveles deben ser cero o positivos.")

    global_files = sorted(args.input.glob("megt*hb.img"))
    polar_files = sorted(args.input.glob("megt_*_512_1.img"))
    if len(global_files) != 16 or len(polar_files) != 2:
        raise FileNotFoundError(
            f"Se requieren 16 MEGT globales a 128 ppd y 2 MEGT polares a 512 ppd; "
            f"se encontraron {len(global_files)} y {len(polar_files)} en {args.input}."
        )

    args.output.mkdir(parents=True, exist_ok=True)
    global_manifest = []
    for index, image_path in enumerate(global_files, start=1):
        print(f"[{index}/18] Procesando {image_path.name}", flush=True)
        global_manifest.append(build_global(image_path, args.output, args.global_level))
    polar_manifest = []
    for index, image_path in enumerate(polar_files, start=17):
        print(f"[{index}/18] Procesando {image_path.name}", flush=True)
        polar_manifest.append(build_polar(image_path, args.output, args.polar_level))

    manifest = {
        "source": "NASA PDS Geosciences Node, MGS MOLA MEGDR topography (MEGT)",
        "heightEncoding": {
            "format": "RGB24",
            "metres": "((R*65536 + G*256 + B) / 10) - 10000",
            "minimumMetres": -10000,
            "maximumMetres": 1667721.5,
        },
        "sourceConversions": {
            "global": {
                "units": "m",
                "sampleType": "MSB_INTEGER",
                "scale": 1.0,
                "offset": 0.0,
            },
            "polar": {
                "units": "m",
                "sampleType": "MSB_UNSIGNED_INTEGER",
                "scale": 0.25,
                "offset": -8000.0,
            },
        },
        "bodyShape": {
            "equatorialRadiusKm": 3396.0,
            "polarRadiusKm": 3376.2,
        },
        "polarProjection": {
            "type": "PDS polar stereographic",
            "pixelsPerDegree": 512,
            "mapScaleKmPerPixel": 0.115,
            "radiusKm": 3376.2,
        },
        "global": global_manifest,
        "polar": polar_manifest,
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Teselas listas: {manifest_path}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error al preparar MOLA: {exc}", file=sys.stderr)
        raise SystemExit(1)
