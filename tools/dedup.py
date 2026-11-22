"""Near-duplicate detection with word shingles and MinHash-style banding (no dependencies)."""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict


def normalise(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\$[^$]*\$", " <math> ", text)
    text = re.sub(r"[^a-z0-9<> ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def shingles(text: str, n: int = 5) -> set[str]:
    words = normalise(text).split()
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / max(1, len(a | b))


def _minhash(sh: set[str], k: int = 64) -> list[int]:
    sig = []
    for seed in range(k):
        best = min(
            (int.from_bytes(hashlib.blake2b(f"{seed}:{s}".encode(), digest_size=8).digest(), "big") for s in sh),
            default=0,
        )
        sig.append(best)
    return sig


def find_duplicates(texts: list[str], threshold: float = 0.7, bands: int = 16) -> dict[int, int]:
    """Return {index: index_of_earlier_original} for every near-duplicate.

    Candidates come from LSH banding over MinHash signatures, then are confirmed
    with exact Jaccard similarity on shingles.
    """
    sh = [shingles(t) for t in texts]
    sigs = [_minhash(s) for s in sh]
    rows = len(sigs[0]) // bands if sigs else 0
    buckets: dict[tuple[int, tuple[int, ...]], list[int]] = defaultdict(list)
    dup: dict[int, int] = {}
    for i, sig in enumerate(sigs):
        cands: set[int] = set()
        for b in range(bands):
            key = (b, tuple(sig[b * rows : (b + 1) * rows]))
            cands.update(buckets[key])
            buckets[key].append(i)
        for j in sorted(cands):
            if j in dup:
                continue
            if jaccard(sh[i], sh[j]) >= threshold:
                dup[i] = j
                break
    return dup
