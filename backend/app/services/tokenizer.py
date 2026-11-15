import os

import tiktoken

# The vocabulary file ships in tiktoken_cache/ so no network is needed at startup.
# Assigned, not setdefault: an inherited TIKTOKEN_CACHE_DIR (or "" which disables the
# cache) would point tiktoken away from the shipped file and bring back the download.
os.environ["TIKTOKEN_CACHE_DIR"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tiktoken_cache"
)

# An approximation: no provider's tokenizer is exactly cl100k_base. The budget in
# context_budget.py keeps a safety margin (SUMMARIZE_THRESHOLD) to absorb the error.
ENCODING = tiktoken.get_encoding("cl100k_base")
