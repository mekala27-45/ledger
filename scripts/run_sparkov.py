"""Generate the card transaction stream with Sparkov, seeded, and strip it to what the desk may see.

Sparkov (github.com/namebrandon/Sparkov_Data_Generation, MIT) seeds Faker but
not Python's random module or numpy, and it farms chunks out to a process pool,
so two runs with the same seed differ. This wrapper seeds every chunk from the
base seed, the profile and the chunk offset before it runs, which makes the
output independent of pool scheduling. Nothing in Sparkov is modified.

Ingestion drops every field that identifies a generated person (names, street,
card number, account number, SSN, date of birth to the day, job) and keeps a
salted card key, age, gender, city population and coordinates. The generated
names are written to data/staged for the identifier scan, and nowhere else.

    uv run python scripts/run_sparkov.py --customers 1100 --start 2025-09-01 --end 2026-08-31
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPARKOV_URL = "https://github.com/namebrandon/Sparkov_Data_Generation.git"
SPARKOV_COMMIT = "b5eb45c89d36f2aa4ef16044a42945bed8b96d93"
CACHE = ROOT / ".cache" / "sparkov"


def _seed_for(base: int, *parts: object) -> int:
    digest = hashlib.sha256(("|".join(str(p) for p in (base, *parts))).encode()).hexdigest()
    return int(digest[:8], 16)


def ensure_checkout() -> Path:
    if not (CACHE / "datagen.py").exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", SPARKOV_URL, str(CACHE)], check=True)
    subprocess.run(["git", "-C", str(CACHE), "checkout", "-q", SPARKOV_COMMIT], check=True)
    return CACHE


def _run_chunk(args: tuple[str, str, str, str, str, int, int, int]) -> str:
    customer_file, profile, start, end, out_path, lo, hi, seed = args
    os.chdir(CACHE)
    sys.path.insert(0, str(CACHE))
    import random

    import datagen_transaction
    import numpy as np
    from faker import Faker

    s = _seed_for(seed, profile, lo)
    random.seed(s)
    np.random.seed(s % (2**32))
    Faker.seed(s)
    datagen_transaction.fake.seed_instance(s)
    datagen_transaction.main(
        Path(customer_file),
        Path("profiles") / profile,
        datetime.strptime(start, "%Y-%m-%d"),
        datetime.strptime(end, "%Y-%m-%d"),
        out_path,
        lo,
        hi,
    )
    return out_path


def generate(customers: int, start: str, end: str, seed: int, work: Path) -> list[Path]:
    ensure_checkout()
    work.mkdir(parents=True, exist_ok=True)
    os.chdir(CACHE)
    sys.path.insert(0, str(CACHE))
    import random

    import datagen_customer
    import numpy as np

    random.seed(seed)
    np.random.seed(seed % (2**32))
    customer_file = work / "customers.csv"
    datagen_customer.main(customers, seed, Path("profiles/main_config.json"), customer_file)
    profiles = [p for p in json.loads(Path("profiles/main_config.json").read_text())]
    chunk = 250
    jobs = []
    for profile in profiles:
        for lo in range(0, customers, chunk):
            hi = min(customers - 1, lo + chunk - 1)
            out = work / f"{profile.replace('.json', '')}_{lo:05d}.csv"
            jobs.append((str(customer_file), profile, start, end, str(out), lo, hi, seed))
    with Pool() as pool:
        outputs = pool.map(_run_chunk, jobs)
    return [Path(o) for o in outputs]


def ingest(work: Path, raw_dir: Path, staged_dir: Path, salt: str) -> dict[str, int]:
    import polars as pl

    frames = []
    names: set[str] = set()
    for path in sorted(work.glob("*_*.csv")):
        if path.name == "customers.csv" or path.stat().st_size == 0:
            continue
        text = path.read_text(encoding="utf-8")
        if text.count("\n") < 2:
            continue
        frame = pl.read_csv(io.StringIO(text), separator="|", infer_schema_length=0)
        frames.append(frame)
    tx = pl.concat(frames)
    for row in tx.select("first", "last").unique().iter_rows():
        names.add(f"{row[0]} {row[1]}".lower())
    key = pl.col("cc_num").map_elements(
        lambda v: "K" + hashlib.sha256(f"{salt}:{v}".encode()).hexdigest()[:10], return_dtype=pl.Utf8
    )
    merchant = pl.col("merchant").str.replace(r"^fraud_", "")
    out = (
        tx.with_columns(
            card_key=key,
            merchant_name=merchant,
            merchant_key=merchant.map_elements(
                lambda v: "M" + hashlib.sha256(f"{salt}:{v}".encode()).hexdigest()[:8], return_dtype=pl.Utf8
            ),
            transaction_time=(pl.col("trans_date") + " " + pl.col("trans_time")).str.to_datetime(
                "%Y-%m-%d %H:%M:%S", time_unit="us"
            ),
            amount=pl.col("amt").cast(pl.Float64),
            is_fraud=pl.col("is_fraud").cast(pl.Int8),
            customer_lat=pl.col("lat").cast(pl.Float64),
            customer_long=pl.col("long").cast(pl.Float64),
            merchant_lat=pl.col("merch_lat").cast(pl.Float64),
            merchant_long=pl.col("merch_long").cast(pl.Float64),
            city_pop=pl.col("city_pop").cast(pl.Int64),
            birth_year=pl.col("dob").str.slice(0, 4).cast(pl.Int32),
        )
        .select(
            "card_key",
            "transaction_time",
            "category",
            "amount",
            "merchant_key",
            "merchant_name",
            "merchant_lat",
            "merchant_long",
            "customer_lat",
            "customer_long",
            "city_pop",
            "state",
            "gender",
            "birth_year",
            "is_fraud",
        )
        .filter(pl.col("transaction_time") < pl.lit(datetime(2026, 9, 1)))
        .sort("transaction_time", "card_key")
        .with_row_index("txn_id", offset=1)
        .with_columns(pl.col("txn_id").cast(pl.Int64))
    )
    raw_dir.mkdir(parents=True, exist_ok=True)
    staged_dir.mkdir(parents=True, exist_ok=True)
    out.write_parquet(raw_dir / "card_transactions.parquet", compression="zstd")
    with gzip.open(staged_dir / "person_names.txt.gz", "wt", encoding="utf-8") as handle:
        for name in sorted(names):
            handle.write(name + "\n")
    return {
        "transactions": out.height,
        "cards": out["card_key"].n_unique(),
        "fraud": int(out["is_fraud"].sum()),
        "names": len(names),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--customers", type=int, default=1100)
    parser.add_argument("--start", default="2025-09-01")
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--seed", type=int, default=20260831)
    args = parser.parse_args()
    work = ROOT / ".cache" / "sparkov_out"
    generate(args.customers, args.start, args.end, args.seed, work)
    stats = ingest(
        work,
        ROOT / "data" / "raw" / "sparkov",
        ROOT / "data" / "staged" / "sparkov",
        salt=f"sparkov-{args.seed}",
    )
    record = {
        "sparkov_commit": SPARKOV_COMMIT,
        "customers": args.customers,
        "start": args.start,
        "end": args.end,
        "seed": args.seed,
        **stats,
    }
    (ROOT / "data" / "raw" / "sparkov" / "run.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))
    return 0


if __name__ == "__main__":
    csv.field_size_limit(sys.maxsize)
    sys.exit(main())
