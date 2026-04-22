#!/usr/bin/env python3
"""
Pre-compress static files in site/ directory with gzip and brotli.

This script scans the site/ directory and creates .gz and .br versions
of all compressible files to improve serving performance.
"""

import gzip
import os
import sys
from pathlib import Path

try:
    import brotli
except ImportError:
    print("ERROR: brotli library not installed. Run: pip install brotli")
    sys.exit(1)


# File extensions that are already compressed or don't benefit from compression
SKIP_EXTENSIONS = {
    ".gz",
    ".br",
    ".zip",
    ".tar",
    ".tgz",
    ".7z",
    ".rar",
    ".xz",
    # Images
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".avif",
    ".ico",
    ".svg",
    # Fonts
    ".woff",
    ".woff2",
    ".eot",
    ".ttf",
    # Video/Audio
    ".mp4",
    ".webm",
    ".mp3",
    ".ogg",
}

# Compression quality settings
GZIP_LEVEL = 6  # Balance between speed and size (1-9)
BROTLI_QUALITY = 6  # Balance between speed and size (0-11)


def should_compress(file_path: Path) -> bool:
    """Check if a file should be compressed."""
    if file_path.suffix.lower() in SKIP_EXTENSIONS:
        return False
    # Skip files that already have compressed counterparts newer than source
    return True


def compress_file(file_path: Path, site_root: Path, dry_run: bool = False) -> dict:
    """Compress a single file with gzip and brotli."""
    result = {"gz": "skipped", "br": "skipped"}

    # Skip if already compressed versions exist and are newer
    gz_path = Path(str(file_path) + ".gz")
    br_path = Path(str(file_path) + ".br")

    if gz_path.exists() and gz_path.stat().st_mtime >= file_path.stat().st_mtime:
        result["gz"] = "exists"
    else:
        if dry_run:
            result["gz"] = "would_compress"
        else:
            content = file_path.read_bytes()
            with gzip.open(gz_path, "wb", compresslevel=GZIP_LEVEL) as f:
                f.write(content)
            result["gz"] = "compressed"

    if br_path.exists() and br_path.stat().st_mtime >= file_path.stat().st_mtime:
        result["br"] = "exists"
    else:
        if dry_run:
            result["br"] = "would_compress"
        else:
            content = file_path.read_bytes()
            compressed = brotli.compress(content, quality=BROTLI_QUALITY)
            br_path.write_bytes(compressed)
            result["br"] = "compressed"

    return result


def main():
    """Main entry point for precompression."""
    # Determine project root (parent of scripts/)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    site_dir = project_root / "site"

    if not site_dir.exists():
        print(f"ERROR: site/ directory not found at {site_dir}")
        sys.exit(1)

    # Parse arguments
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("[DRY RUN] Would compress files in:", site_dir)
    else:
        print("Pre-compressing files in:", site_dir)

    stats = {"total": 0, "compressed": 0, "skipped": 0, "exists": 0}
    results = {"gz_compressed": 0, "gz_exists": 0, "br_compressed": 0, "br_exists": 0}

    # Walk through site directory
    for root, _dirs, files in os.walk(site_dir):
        for filename in sorted(files):
            file_path = Path(root) / filename

            # Skip compressed files
            if not should_compress(file_path):
                stats["skipped"] += 1
                continue

            stats["total"] += 1

            result = compress_file(file_path, site_dir, dry_run)

            if result["gz"] == "compressed":
                results["gz_compressed"] += 1
                stats["compressed"] += 1
            elif result["gz"] == "exists":
                results["gz_exists"] += 1
                stats["exists"] += 1

            if result["br"] == "compressed":
                results["br_compressed"] += 1
            elif result["br"] == "exists":
                results["br_exists"] += 1

            # Print progress every 100 files
            if stats["total"] % 100 == 0:
                print(f"  Processed {stats['total']} files...")

    # Print summary
    print()
    print("=" * 50)
    print("Pre-compression summary:")
    print("=" * 50)
    print(f"  Files scanned:     {stats['total']}")
    print(f"  Newly compressed:  {stats['compressed']}")
    print(f"  Already existed:   {stats['exists']}")
    print(f"  Skipped (binary):  {stats['skipped']}")
    print()
    print(f"  .gz files: {results['gz_compressed']} new, {results['gz_exists']} existing")
    print(f"  .br files: {results['br_compressed']} new, {results['br_exists']} existing")
    print("=" * 50)

    if dry_run:
        print("\nRun without --dry-run to actually compress files.")


if __name__ == "__main__":
    main()
