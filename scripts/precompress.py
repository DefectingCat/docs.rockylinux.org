#!/usr/bin/env python3
"""
Pre-compress static files in site/ directory with gzip and brotli.

This script scans the site/ directory and creates .gz and .br versions
of all compressible files to improve serving performance.
"""

import gzip
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# Number of worker threads (default: CPU count * 2)
MAX_WORKERS = None  # None means ThreadPoolExecutor will auto-detect


def should_compress(file_path: Path) -> bool:
    """Check if a file should be compressed."""
    if file_path.suffix.lower() in SKIP_EXTENSIONS:
        return False
    return True


def compress_file(file_path: Path) -> dict:
    """Compress a single file with gzip and brotli."""
    result = {"gz": "skipped", "br": "skipped"}

    gz_path = Path(str(file_path) + ".gz")
    br_path = Path(str(file_path) + ".br")

    try:
        file_mtime = file_path.stat().st_mtime

        if gz_path.exists() and gz_path.stat().st_mtime >= file_mtime:
            result["gz"] = "exists"
        else:
            content = file_path.read_bytes()
            with gzip.open(gz_path, "wb", compresslevel=GZIP_LEVEL) as f:
                f.write(content)
            result["gz"] = "compressed"

        if br_path.exists() and br_path.stat().st_mtime >= file_mtime:
            result["br"] = "exists"
        else:
            content = file_path.read_bytes()
            compressed = brotli.compress(content, quality=BROTLI_QUALITY)
            br_path.write_bytes(compressed)
            result["br"] = "compressed"
    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    """Main entry point for precompression."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    site_dir = project_root / "site"

    if not site_dir.exists():
        print(f"ERROR: site/ directory not found at {site_dir}")
        sys.exit(1)

    # Parse arguments
    dry_run = "--dry-run" in sys.argv
    threads_arg = None
    for arg in sys.argv:
        if arg.startswith("--threads="):
            threads_arg = int(arg.split("=")[1])

    workers = threads_arg if threads_arg is not None else MAX_WORKERS

    if dry_run:
        print("[DRY RUN] Would compress files in:", site_dir)
    else:
        print(f"Pre-compressing files in: {site_dir} (workers: {workers or 'auto'})")

    # Collect all files to compress
    files_to_compress = []
    for root, _dirs, files in os.walk(site_dir):
        for filename in sorted(files):
            file_path = Path(root) / filename
            if should_compress(file_path):
                files_to_compress.append(file_path)

    total_files = len(files_to_compress)
    print(f"Found {total_files} files to process\n")

    stats = {"compressed": 0, "exists": 0, "errors": 0}
    results = {"gz_compressed": 0, "gz_exists": 0, "br_compressed": 0, "br_exists": 0}

    if dry_run:
        # Dry run: just count files
        print(f"Would compress {total_files} files with gzip and brotli")
        stats["compressed"] = total_files
    else:
        # Multi-threaded compression
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_path = {executor.submit(compress_file, fp): fp for fp in files_to_compress}

            completed = 0
            for future in as_completed(future_to_path):
                file_path = future_to_path[future]
                completed += 1

                try:
                    result = future.result()

                    if "error" in result:
                        stats["errors"] += 1
                        print(f"  ERROR: {file_path.relative_to(site_dir)}: {result['error']}")
                    else:
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
                    if completed % 100 == 0:
                        print(f"  Processed {completed}/{total_files} files...")
                except Exception as e:
                    stats["errors"] += 1
                    print(f"  ERROR: {file_path.relative_to(site_dir)}: {e}")

    # Print summary
    print()
    print("=" * 50)
    print("Pre-compression summary:")
    print("=" * 50)
    print(f"  Files scanned:     {total_files}")
    print(f"  Newly compressed:  {stats['compressed']}")
    print(f"  Already existed:   {stats['exists']}")
    if stats["errors"]:
        print(f"  Errors:            {stats['errors']}")
    print()
    print(f"  .gz files: {results['gz_compressed']} new, {results['gz_exists']} existing")
    print(f"  .br files: {results['br_compressed']} new, {results['br_exists']} existing")
    print("=" * 50)

    if dry_run:
        print("\nRun without --dry-run to actually compress files.")

    if stats["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
