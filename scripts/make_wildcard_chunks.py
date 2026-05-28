#!/usr/bin/env python3
"""Create balanced chunk files and aws --include wildcard manifests."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Chunk:
    idx: int
    prefixes: list[str] = field(default_factory=list)
    genomes: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.genomes)


def read_genomes(path: Path) -> list[str]:
    genomes = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    if not genomes:
        raise ValueError(f"No genomes found in {path}")
    return genomes


def assign_prefixes(genomes: list[str], num_chunks: int, prefix_len: int) -> tuple[list[Chunk], float]:
    if num_chunks <= 0:
        raise ValueError("num_chunks must be greater than zero")

    by_prefix: dict[str, list[str]] = defaultdict(list)
    for genome in genomes:
        by_prefix[genome[:prefix_len]].append(genome)

    chunks = [Chunk(idx=i) for i in range(num_chunks)]
    bucket_items = sorted(by_prefix.items(), key=lambda kv: len(kv[1]), reverse=True)
    for prefix, items in bucket_items:
        target = min(chunks, key=lambda chunk: (chunk.count, chunk.idx))
        target.prefixes.append(prefix)
        target.genomes.extend(items)

    expected = len(genomes) / num_chunks
    max_dev = max((abs(chunk.count - expected) / expected) * 100 for chunk in chunks)
    return chunks, max_dev


def verify_coverage(genomes: list[str], chunks: list[Chunk]) -> None:
    assigned = [g for chunk in chunks for g in chunk.genomes]
    if len(assigned) != len(genomes):
        raise ValueError("Chunk assignment count does not match input genomes")
    if len(set(assigned)) != len(genomes):
        raise ValueError("Chunk assignment produced duplicate genome entries")
    if set(assigned) != set(genomes):
        raise ValueError("Chunk assignment missed one or more genomes")


def choose_layout(genomes: list[str], num_chunks: int, max_imbalance_pct: float) -> tuple[list[Chunk], int, float]:
    max_len = max(len(g) for g in genomes)
    best: tuple[list[Chunk], int, float] | None = None

    for prefix_len in range(1, max_len + 1):
        bucket_count = len(Counter(g[:prefix_len] for g in genomes))
        if bucket_count < num_chunks:
            continue

        chunks, max_dev = assign_prefixes(genomes, num_chunks, prefix_len)
        verify_coverage(genomes, chunks)
        if best is None or max_dev < best[2]:
            best = (chunks, prefix_len, max_dev)
        if max_dev <= max_imbalance_pct:
            return chunks, prefix_len, max_dev

    if best is None:
        raise ValueError("Could not generate wildcard buckets for requested chunk count")
    raise ValueError(
        f"Best wildcard balance was {best[2]:.2f}% (target <= {max_imbalance_pct:.2f}%). "
        f"Try fewer chunks or a larger subset."
    )


def write_outputs(chunks: list[Chunk], out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    chunk_ids: list[str] = []
    for chunk in chunks:
        chunk_id = f"{chunk.idx:04d}"
        chunk_ids.append(chunk_id)

        genomes_path = out_dir / f"chunk_{chunk_id}.txt"
        includes_path = out_dir / f"chunk_{chunk_id}.includes.txt"

        genomes_path.write_text("".join(f"{g}\n" for g in sorted(chunk.genomes)))
        includes_path.write_text("".join(f"{prefix}*\n" for prefix in sorted(chunk.prefixes)))
    return chunk_ids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--num-chunks", required=True, type=int)
    parser.add_argument("--max-imbalance-pct", type=float, default=10.0)
    parser.add_argument("--summary-json", required=True, type=Path)
    args = parser.parse_args()

    genomes = read_genomes(args.input)
    num_chunks = max(1, min(args.num_chunks, len(genomes)))
    chunks, prefix_len, max_dev = choose_layout(genomes, num_chunks, args.max_imbalance_pct)
    chunk_ids = write_outputs(chunks, args.out_dir)

    summary = {
        "chunk_ids": chunk_ids,
        "prefix_len": prefix_len,
        "max_imbalance_pct": round(max_dev, 4),
        "total_genomes": len(genomes),
        "target_chunks": num_chunks,
        "chunk_sizes": {f"{chunk.idx:04d}": chunk.count for chunk in chunks},
    }
    args.summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    expected = len(genomes) / num_chunks
    upper = math.ceil(expected * (1 + (args.max_imbalance_pct / 100.0)))
    lower = math.floor(expected * (1 - (args.max_imbalance_pct / 100.0)))
    print(f"Wildcard type: aws --include uses shell-style globs (*, ?, [seq], [!seq])")
    print(f"Prefix length used: {prefix_len}")
    print(f"Expected genomes/chunk: {expected:.2f} (allowed integer range: {lower}..{upper})")
    print(f"Observed max imbalance: {max_dev:.2f}%")
    for chunk in chunks:
        print(f"chunk_{chunk.idx:04d}: {chunk.count} genomes, {len(chunk.prefixes)} include pattern(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
