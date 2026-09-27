"""Financial crime typologies injected with known membership, and the legitimate lookalikes around them.

Four typologies a transaction monitoring program looks for, each written into the
deposit sub ledger as ordinary entries:

- structuring: cash deposits just under the ten thousand dollar reporting
  threshold, across days and often across branches;
- rapid movement: a large wire in and nearly all of it out again within hours;
- mule: many small payments in from unrelated counterparties, then one wire out;
- round tripping: money that moves around a ring of accounts and comes home.

Every injected entry carries the episode id in ``reference``, and the truth
table records the episode. Around them sit legitimate customers who look
similar to a rule (cash intensive businesses, roommates splitting rent, a home
purchase wire), because a detector with no false positives to find would prove
nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import polars as pl

from ledger_bankgen.accounts import DepositBook
from ledger_bankgen.deposits import TYPES, ScheduledEntries
from ledger_bankgen.params import GeneratorParams
from ledger_bankgen.timeline import Timeline

EXTERNAL_BASE = 500_000  # external counterparty ids for typologies sit above the ordinary range


@dataclass
class Injection:
    scheduled: ScheduledEntries
    truth: pl.DataFrame
    friends: np.ndarray
    cash_intensive: np.ndarray


def build_friend_circles(n_customers: int, rng: np.random.Generator, slots: int = 4) -> np.ndarray:
    """Each customer's usual payment counterparties: a small circle of other customers plus outsiders.

    Values of zero or more are customer indexes. Negative values encode an
    external counterparty id as ``-(id + 1)``.
    """
    friends = np.empty((n_customers, slots), dtype=np.int64)
    order = rng.permutation(n_customers)
    start = 0
    while start < n_customers:
        size = int(rng.integers(3, 9))
        group = order[start : start + size]
        for member in group:
            others = group[group != member]
            for s in range(slots):
                if len(others) and rng.random() < 0.6:
                    friends[member, s] = int(rng.choice(others))
                else:
                    friends[member, s] = -(int(rng.integers(0, 400_000)) + 1)
        start += size
    return friends


def _stamp(timeline: Timeline, moment: datetime) -> tuple[int, int] | None:
    for i, m in enumerate(timeline.months):
        nxt = timeline.months[i + 1] if i + 1 < len(timeline) else None
        start = datetime(m.year, m.month, 1)
        if nxt is None:
            end = start + timedelta(days=31)
            end = datetime(end.year, end.month, 1)
        else:
            end = datetime(nxt.year, nxt.month, 1)
        if start <= moment < end:
            seconds = int((moment - start).total_seconds())
            # The simulation spreads ordinary entries over the first 28 days; keep typologies inside too.
            if seconds >= 28 * 86400:
                return None
            return i, seconds
    return None


class _Writer:
    def __init__(self, timeline: Timeline) -> None:
        self.timeline = timeline
        self.cols: dict[str, list[int | float]] = {
            k: []
            for k in (
                "month",
                "account",
                "amount",
                "kind",
                "seconds",
                "cp_account",
                "cp_external",
                "branch",
                "group",
                "ref",
            )
        }
        self.truth: list[dict[str, object]] = []
        self.group_seq = 90_000_000

    def add(
        self,
        moment: datetime,
        account: int,
        amount: float,
        kind: str,
        *,
        ref: int,
        cp_account: int = -1,
        cp_external: int = -1,
        branch: int = -1,
        group: int = -1,
    ) -> bool:
        stamp = _stamp(self.timeline, moment)
        if stamp is None:
            return False
        month, seconds = stamp
        for key, value in (
            ("month", month),
            ("account", account),
            ("amount", round(amount, 2)),
            ("kind", TYPES[kind]),
            ("seconds", seconds),
            ("cp_account", cp_account),
            ("cp_external", cp_external),
            ("branch", branch),
            ("group", group),
            ("ref", ref),
        ):
            self.cols[key].append(value)
        return True

    def transfer(self, moment: datetime, src: int, dst: int, amount: float, ref: int) -> bool:
        self.group_seq += 1
        ok = self.add(
            moment, src, -amount, "INTERNAL_TRANSFER", ref=ref, cp_account=dst, group=self.group_seq
        )
        if ok:
            self.add(moment, dst, amount, "INTERNAL_TRANSFER", ref=ref, cp_account=src, group=self.group_seq)
        return ok

    def scheduled(self) -> ScheduledEntries:
        out = ScheduledEntries()
        if not self.cols["account"]:
            return out
        a = {k: np.array(v) for k, v in self.cols.items()}
        kinds = sorted(set(a["kind"].tolist()))
        for kind in kinds:
            m = a["kind"] == kind
            out.add(
                a["month"][m],
                a["account"][m],
                a["amount"][m],
                int(kind),
                a["seconds"][m],
                cp_account=a["cp_account"][m],
                cp_external=a["cp_external"][m],
                branch=a["branch"][m],
                group=a["group"][m],
                ref=a["ref"][m],
            )
        return out


def inject(
    customers: pl.DataFrame,
    book: DepositBook,
    params: GeneratorParams,
    timeline: Timeline,
    rng: np.random.Generator,
) -> Injection:
    n = customers.height
    t = params.typologies
    friends = build_friend_circles(n, rng)
    open_dates = customers["open_date"].to_list()
    branch_home = customers["home_branch"].to_numpy()
    checking = book.checking_of_customer
    window_start = datetime(timeline.months[0].year, timeline.months[0].month, 1)
    # Candidates: customers with a checking account open before the window, so episodes land on live accounts.
    candidates = np.flatnonzero((checking >= 0) & (np.array([d < timeline.months[0] for d in open_dates])))
    pool = rng.permutation(candidates)
    cursor = 0

    def take(k: int) -> np.ndarray:
        nonlocal cursor
        chosen = pool[cursor : cursor + k]
        cursor += k
        return chosen

    w = _Writer(timeline)
    episode = 0
    ext_seq = EXTERNAL_BASE

    def random_moment(lo_day: int = 0, hi_day: int | None = None) -> datetime:
        hi = hi_day if hi_day is not None else len(timeline) * 30 - 20
        day = int(rng.integers(lo_day, hi))
        return window_start + timedelta(
            days=day, hours=int(rng.integers(9, 16)), minutes=int(rng.integers(0, 60))
        )

    def record(
        kind: str, cust: int, start: datetime, end: datetime, n_txn: int, amount: float, ring: int = -1
    ) -> None:
        w.truth.append(
            {
                "episode_id": episode,
                "typology": kind,
                "customer_index": int(cust),
                "account_index": int(checking[cust]),
                "start_at": start,
                "end_at": end,
                "n_entries": n_txn,
                "amount": round(amount, 2),
                "ring_id": ring,
            }
        )

    # Structuring: two or three episodes each, cash in under the threshold across days and branches.
    for cust in take(t.structuring_customers):
        acc = int(checking[cust])
        for _ in range(int(rng.integers(2, 4))):
            episode += 1
            start = random_moment()
            k = int(rng.integers(3, 7))
            days = np.sort(rng.integers(0, 10, k))
            amounts = np.round(rng.uniform(7_600, 9_950, k), 0)
            branches = rng.choice(np.arange(1, params.branches + 1), size=k)
            branches[0] = branch_home[cust]
            posted = 0
            for d, amt, br in zip(days, amounts, branches, strict=True):
                moment = start + timedelta(days=int(d), hours=int(rng.integers(0, 6)))
                posted += w.add(moment, acc, float(amt), "CASH_DEPOSIT", ref=episode, branch=int(br))
            out_moment = start + timedelta(days=int(days[-1]) + int(rng.integers(1, 5)))
            ext_seq += 1
            posted += w.add(
                out_moment,
                acc,
                -float(amounts.sum()) * rng.uniform(0.82, 0.95),
                "WIRE_OUT",
                ref=episode,
                cp_external=ext_seq,
            )
            record("structuring", cust, start, out_moment, posted, float(amounts.sum()))

    # Rapid movement: a large wire in and most of it out within hours.
    for cust in take(t.rapid_movement_customers):
        acc = int(checking[cust])
        for _ in range(int(rng.integers(1, 4))):
            episode += 1
            start = random_moment()
            amount = float(np.round(rng.uniform(20_000, 150_000), 2))
            ext_seq += 1
            posted = w.add(start, acc, amount, "WIRE_IN", ref=episode, cp_external=ext_seq)
            out_moment = start + timedelta(hours=float(rng.uniform(1.5, 20)))
            ext_seq += 1
            posted += w.add(
                out_moment,
                acc,
                -amount * rng.uniform(0.90, 0.99),
                "WIRE_OUT",
                ref=episode,
                cp_external=ext_seq,
            )
            record("rapid_movement", cust, start, out_moment, posted, amount)

    # Mules: many small payments in from unrelated counterparties, then one wire out.
    for cust in take(t.mule_customers):
        acc = int(checking[cust])
        for _ in range(int(rng.integers(1, 3))):
            episode += 1
            start = random_moment()
            k = int(rng.integers(8, 26))
            offsets = np.sort(rng.uniform(0, 13.5, k))
            amounts = np.round(rng.uniform(200, 2_500, k), 2)
            posted = 0
            for off, amt in zip(offsets, amounts, strict=True):
                ext_seq += 1
                posted += w.add(
                    start + timedelta(days=float(off)),
                    acc,
                    float(amt),
                    "P2P_IN",
                    ref=episode,
                    cp_external=ext_seq,
                )
            out_moment = start + timedelta(days=float(offsets[-1]) + float(rng.uniform(0.5, 3.0)))
            ext_seq += 1
            posted += w.add(
                out_moment,
                acc,
                -float(amounts.sum()) * rng.uniform(0.85, 0.98),
                "WIRE_OUT",
                ref=episode,
                cp_external=ext_seq,
            )
            record("mule", cust, start, out_moment, posted, float(amounts.sum()))

    # Round tripping: rings of three to five accounts, money around the ring and home again.
    for ring in range(t.round_trip_rings):
        size = int(rng.integers(3, 6))
        members = take(size)
        if len(members) < 3:
            break
        for _ in range(int(rng.integers(2, 5))):
            episode += 1
            start = random_moment()
            amount = float(np.round(rng.uniform(15_000, 60_000), 2))
            moment = start
            posted = 0
            hops = [*members, members[0]]
            for a_cust, b_cust in zip(hops[:-1], hops[1:], strict=True):
                moment = moment + timedelta(hours=float(rng.uniform(6, 60)))
                posted += 2 * w.transfer(
                    moment, int(checking[a_cust]), int(checking[b_cust]), amount, episode
                )
                amount = round(amount * rng.uniform(0.985, 0.999), 2)
            for c in members:
                record("round_tripping", c, start, moment, posted, amount, ring)

    # Legitimate lookalikes. No episode id: these are not suspicious, and the truth table says so by omission.
    cash_intensive = np.zeros(n, dtype=bool)
    cash_intensive[take(t.cash_intensive_lookalikes)] = True
    for cust in take(t.p2p_heavy_lookalikes):
        acc = int(checking[cust])
        roommates = [int(rng.integers(0, 400_000)) for _ in range(int(rng.integers(2, 4)))]
        for m in range(0, len(timeline)):
            if rng.random() < 0.85:
                for r in roommates:
                    moment = datetime(timeline.months[m].year, timeline.months[m].month, 1) + timedelta(
                        days=int(rng.integers(0, 5)), hours=10
                    )
                    w.add(
                        moment,
                        acc,
                        float(np.round(rng.uniform(600, 1_400), 2)),
                        "P2P_IN",
                        ref=-1,
                        cp_external=r,
                    )
    for cust in take(t.large_wire_lookalikes):
        acc = int(checking[cust])
        start = random_moment()
        amount = float(np.round(rng.uniform(40_000, 180_000), 2))
        ext_seq += 1
        w.add(start, acc, amount, "WIRE_IN", ref=-1, cp_external=ext_seq)
        ext_seq += 1
        w.add(
            start + timedelta(days=float(rng.uniform(6, 30))),
            acc,
            -amount * rng.uniform(0.9, 1.0),
            "WIRE_OUT",
            ref=-1,
            cp_external=ext_seq,
        )

    truth = pl.DataFrame(w.truth) if w.truth else pl.DataFrame()
    return Injection(scheduled=w.scheduled(), truth=truth, friends=friends, cash_intensive=cash_intensive)
