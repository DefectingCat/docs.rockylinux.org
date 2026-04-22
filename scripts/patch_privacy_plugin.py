#!/usr/bin/env python3
"""
Monkey-patch the MkDocs Material privacy plugin to:
1. Increase timeout from 5s to 30s
2. Add retry logic (3 attempts with exponential backoff)
"""

import os
import sys
import re

def find_privacy_plugin_path(venv_path):
    """Find the privacy plugin file path."""
    return os.path.join(
        venv_path,
        "lib", "python3.12", "site-packages",
        "material", "plugins", "privacy", "plugin.py"
    )

def patch_file(file_path):
    """Apply the monkey-patch to the privacy plugin."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Increase timeout from 5s to 30s
    content = content.replace(
        "DEFAULT_TIMEOUT_IN_SECS = 5",
        "DEFAULT_TIMEOUT_IN_SECS = 30"
    )

    # 2. Add retry import at the top (after 'import requests')
    content = content.replace(
        "import requests",
        "import requests\nfrom urllib3.util.retry import Retry\nfrom requests.adapters import HTTPAdapter"
    )

    # 3. Modify the _fetch method to add retry logic
    # Find the requests.get block and add retry session setup
    old_fetch = '''            res = requests.get(
                    file.url,
                    headers = {
                        # Set user agent explicitly, so Google Fonts gives us
                        # *.woff2 files, which according to caniuse.com is the
                        # only format we need to download as it covers the range
                        # range of browsers we're officially supporting.
                        "User-Agent": " ".join(
                            [
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                                "AppleWebKit/537.36 (KHTML, like Gecko)",
                                "Chrome/98.0.4758.102 Safari/537.36",
                            ]
                        )
                    },
                    timeout=DEFAULT_TIMEOUT_IN_SECS,
                )'''

    new_fetch = '''            # Create session with retry logic
                session = requests.Session()
                retry_strategy = Retry(
                    total=3,
                    backoff_factor=2,
                    status_forcelist=[429, 500, 502, 503, 504],
                )
                session.mount("https://", HTTPAdapter(max_retries=retry_strategy))
                session.mount("http://", HTTPAdapter(max_retries=retry_strategy))

                res = session.get(
                    file.url,
                    headers = {
                        # Set user agent explicitly, so Google Fonts gives us
                        # *.woff2 files, which according to caniuse.com is the
                        # only format we need to download as it covers the range
                        # range of browsers we're officially supporting.
                        "User-Agent": " ".join(
                            [
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                                "AppleWebKit/537.36 (KHTML, like Gecko)",
                                "Chrome/98.0.4758.102 Safari/537.36",
                            ]
                        )
                    },
                    timeout=DEFAULT_TIMEOUT_IN_SECS,
                )'''

    content = content.replace(old_fetch, new_fetch)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Patched: {file_path}")
    print("  - Timeout: 5s → 30s")
    print("  - Retries: 0 → 3 (with exponential backoff)")

if __name__ == "__main__":
    venv_path = sys.argv[1] if len(sys.argv) > 1 else ".venv"
    plugin_path = find_privacy_plugin_path(venv_path)

    if not os.path.exists(plugin_path):
        print(f"ERROR: Privacy plugin not found at: {plugin_path}")
        sys.exit(1)

    patch_file(plugin_path)
    print("Privacy plugin patched successfully!")
