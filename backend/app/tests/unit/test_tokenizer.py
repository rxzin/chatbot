"""The cl100k_base vocabulary ships with the app and loads with no network."""

import hashlib
import inspect
import os
import re
import subprocess
import sys
from pathlib import Path

from tiktoken_ext.openai_public import cl100k_base

APP_DIR = Path(__file__).resolve().parents[2]
CACHE_DIR = APP_DIR / "services" / "tiktoken_cache"
# tiktoken names cache files by the sha1 of the blob URL.
CACHE_FILE = CACHE_DIR / hashlib.sha1(
    b"https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
).hexdigest()

# Any network attempt raises, so a download would fail the script.
NO_NETWORK_SCRIPT = """
import socket

def refuse(*args, **kwargs):
    raise OSError("network disabled")

socket.getaddrinfo = refuse
socket.create_connection = refuse

from services.tokenizer import ENCODING

assert ENCODING.encode("hello world") == [15339, 1917]
print("ok")
"""


def expected_hash() -> str:
    # The hash is an argument to load_tiktoken_bpe inside cl100k_base(), so read it
    # from the source rather than duplicating it here.
    return re.search(r'expected_hash="([0-9a-f]{64})"', inspect.getsource(cl100k_base)).group(1)


def test_vendored_file_matches_tiktoken_hash():
    assert hashlib.sha256(CACHE_FILE.read_bytes()).hexdigest() == expected_hash()


def test_encoding_loads_without_network(tmp_path):
    # An empty temp dir so tiktoken's default temp cache cannot hide a missing file.
    env = {
        **os.environ,
        "TEMP": str(tmp_path),
        "TMP": str(tmp_path),
        "TMPDIR": str(tmp_path),
    }
    env.pop("TIKTOKEN_CACHE_DIR", None)
    env.pop("DATA_GYM_CACHE_DIR", None)

    result = subprocess.run(
        [sys.executable, "-c", NO_NETWORK_SCRIPT],
        cwd=APP_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
