"""Downscale oversized source PNGs in a staged Pygbag build.

The source artwork remains untouched. Runtime sprites are kept at twice their
logical display size so they stay crisp without making browsers unpack tens of
megabytes of pixels that the game never displays.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pygame


def resize(path: Path, size: tuple[int, int]) -> None:
    image = pygame.image.load(path)
    if image.get_size() == size:
        return
    pygame.image.save(pygame.transform.smoothscale(image, size), path)


def main(asset_dir: Path) -> None:
    for path in (asset_dir / "pieces").glob("*.png"):
        resize(path, (136, 136))

    for path in (asset_dir / "monsters").glob("*.png"):
        size = (360, 360) if path.stem == "boss" else (252, 252)
        resize(path, size)

    defeat_dir = asset_dir / "monsters" / "defeat"
    for path in defeat_dir.glob("*.png"):
        # Six frames arranged as a 3x2 sprite sheet.
        size = (1200, 800) if path.stem == "boss" else (888, 592)
        resize(path, size)

    effect_dir = asset_dir / "effects" / "royal_star_comet"
    effect_sizes = {
        "crown_flash.png": (212, 176),
        "impact_starburst.png": (236, 236),
        "particles_atlas.png": (404, 352),
        "projectile_blue.png": (88, 88),
        "projectile_green.png": (88, 88),
        "projectile_red.png": (88, 88),
        "trail_blue.png": (244, 56),
        "trail_green.png": (244, 56),
        "trail_red.png": (244, 56),
    }
    for filename, size in effect_sizes.items():
        resize(effect_dir / filename, size)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare_web_assets.py ASSET_DIR")
    main(Path(sys.argv[1]))
