"""The deposit sub ledger: every entry on every deposit account, month by month.

Balances are never drawn directly. Each month's entries are generated first and
the closing balance is the opening balance plus the sum of the month's entries,
so balances roll by construction and the "balance does not roll" defect is a
deliberate, counted exception rather than an accident.

Spending responds to the balance (people spend less when they are short), income
stops for a share of customers in months of high unemployment, and each deposit
product's rate follows the policy rate through a stated beta, so the analysis in
function 6 has deposit betas and a macro link to recover.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl

from ledger_bankgen.accounts import DepositBook
from ledger_bankgen.params import GeneratorParams
from ledger_bankgen.timeline import Timeline

TYPES = {
    "PAYROLL_IN": 1,
    "BILL_PAY": 2,
    "CARD_SPEND": 3,
    "ATM_WITHDRAWAL": 4,
    "CASH_DEPOSIT": 5,
    "P2P_OUT": 6,
    "P2P_IN": 7,
    "INTERNAL_TRANSFER": 8,
    "WIRE_IN": 9,
    "WIRE_OUT": 10,
    "LOAN_PAYMENT": 11,
    "FEE_MAINTENANCE": 12,
    "FEE_OVERDRAFT": 13,
    "INTEREST_CREDIT": 14,
    "ACCOUNT_FUNDING": 15,
    "CD_PAYOUT": 16,
    "ACH_IN": 17,
    "LOAN_DISBURSEMENT": 18,
    "ACH_OUT": 19,
    "OVERDRAFT_CHARGE_OFF": 20,
}
TYPE_NAMES = {v: k for k, v in TYPES.items()}


@dataclass
class ScheduledEntries:
    """Entries decided outside the deposit simulation: loan flows and injected typologies."""

    month: list[np.ndarray] = field(default_factory=list)
    account: list[np.ndarray] = field(default_factory=list)
    amount: list[np.ndarray] = field(default_factory=list)
    kind: list[np.ndarray] = field(default_factory=list)
    seconds: list[np.ndarray] = field(default_factory=list)
    cp_account: list[np.ndarray] = field(default_factory=list)
    cp_external: list[np.ndarray] = field(default_factory=list)
    branch: list[np.ndarray] = field(default_factory=list)
    group: list[np.ndarray] = field(default_factory=list)
    ref: list[np.ndarray] = field(default_factory=list)

    def add(
        self,
        month: np.ndarray,
        account: np.ndarray,
        amount: np.ndarray,
        kind: int,
        seconds: np.ndarray,
        *,
        cp_account: np.ndarray | None = None,
        cp_external: np.ndarray | None = None,
        branch: np.ndarray | None = None,
        group: np.ndarray | None = None,
        ref: np.ndarray | None = None,
    ) -> None:
        n = len(account)
        self.month.append(month.astype(np.int16))
        self.account.append(account.astype(np.int32))
        self.amount.append(np.round(amount, 2))
        self.kind.append(np.full(n, kind, dtype=np.int8))
        self.seconds.append(seconds.astype(np.int32))
        self.cp_account.append(
            np.full(n, -1, np.int32) if cp_account is None else cp_account.astype(np.int32)
        )
        self.cp_external.append(
            np.full(n, -1, np.int32) if cp_external is None else cp_external.astype(np.int32)
        )
        self.branch.append(np.full(n, -1, np.int16) if branch is None else branch.astype(np.int16))
        # Two legs of one transfer share a group id; -1 means the entry is its own transaction.
        self.group.append(np.full(n, -1, np.int64) if group is None else group.astype(np.int64))
        self.ref.append(np.full(n, -1, np.int64) if ref is None else ref.astype(np.int64))

    def frame(self) -> dict[str, np.ndarray]:
        if not self.account:
            empty = np.array([], dtype=np.int32)
            return {
                k: empty
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
        return {
            "month": np.concatenate(self.month),
            "account": np.concatenate(self.account),
            "amount": np.concatenate(self.amount),
            "kind": np.concatenate(self.kind),
            "seconds": np.concatenate(self.seconds),
            "cp_account": np.concatenate(self.cp_account),
            "cp_external": np.concatenate(self.cp_external),
            "branch": np.concatenate(self.branch),
            "group": np.concatenate(self.group),
            "ref": np.concatenate(self.ref),
        }


@dataclass
class DepositResult:
    entries: pl.DataFrame
    balances: pl.DataFrame
    rates: pl.DataFrame
    closures: pl.DataFrame
    truth_attrition: pl.DataFrame


def product_rates(params: GeneratorParams, macro: pl.DataFrame) -> pl.DataFrame:
    """Each product's standard rate by month, from the policy rate through the stated betas."""
    b = params.betas
    policy = macro["policy_rate"].to_numpy()
    p0 = policy[0]
    checking = np.maximum(b.checking_floor, 0.10 + b.checking * (policy - p0))
    savings = np.maximum(b.savings_floor, b.savings_start + b.savings * (policy - p0))
    time = np.maximum(0.50, p0 + b.time_spread + b.time * (policy - p0))
    return pl.DataFrame(
        {
            "month": macro["month"],
            "policy_rate": policy,
            "checking_rate": np.round(checking, 3),
            "savings_rate": np.round(savings, 3),
            "time_rate": np.round(time, 3),
        }
    )


def simulate_deposits(
    customers: pl.DataFrame,
    book: DepositBook,
    params: GeneratorParams,
    timeline: Timeline,
    macro: pl.DataFrame,
    scheduled: ScheduledEntries,
    friends: np.ndarray,
    cash_intensive: np.ndarray,
    rng: np.random.Generator,
) -> DepositResult:
    n_acc = len(book.customer_index)
    n_cust = customers.height
    n_months = len(timeline)
    cust = book.customer_index
    product = book.product
    income = customers["annual_income"].to_numpy()
    segment = customers["segment"].to_numpy()
    digital = customers["digital_active"].to_numpy()
    complaint = customers["complaint_flag"].to_numpy()
    branch_home = customers["home_branch"].to_numpy()
    open_dates = customers["open_date"].to_list()
    unemployment = macro["unemployment_rate"].to_numpy()
    rates = product_rates(params, macro)
    rate_arr = {
        0: rates["checking_rate"].to_numpy(),
        1: rates["savings_rate"].to_numpy(),
        2: rates["time_rate"].to_numpy(),
    }
    a = params.attrition

    balance = np.round(np.where(book.open_month < 0, book.opening_balance, 0.0), 2)
    active = book.open_month < 0
    closed_month = np.full(n_acc, -1, dtype=np.int32)
    customer_closed = np.full(n_cust, -1, dtype=np.int32)
    checking_of = book.checking_of_customer
    savings_of = book.savings_of_customer
    # Account level promotional spread, fixed for life, so implied rates vary around the product rate.
    promo = np.where(
        product == 1, rng.normal(0, 0.12, n_acc), np.where(product == 2, rng.normal(0, 0.10, n_acc), 0.0)
    )
    cd_rate = np.zeros(n_acc)
    cd_maturity = np.full(n_acc, -1, dtype=np.int32)
    term = book.accounts["term_months"].to_numpy()
    for i in np.flatnonzero(product == 2):
        opened_m = book.open_month[i]
        cd_rate[i] = rate_arr[2][max(opened_m, 0)] + promo[i]
        cd_maturity[i] = (opened_m if opened_m >= 0 else -int(rng.integers(0, max(1, term[i])))) + term[i]
    target = np.where(segment == "affluent", 1.6, np.where(segment == "emerging", 0.5, 0.8)) * income / 12.0

    sched = scheduled.frame()
    sched_by_month = [np.flatnonzero(sched["month"] == m) for m in range(n_months)]

    out: dict[str, list[np.ndarray]] = {
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
    bal_rows: list[pl.DataFrame] = []
    group_seq = 10_000_000
    prev_balance = balance.copy()
    fee_last = np.zeros(n_acc, dtype=bool)
    rate_gap = np.zeros(n_cust)
    attr_rows: list[pl.DataFrame] = []

    def emit(
        month: int, acc: np.ndarray, amt: np.ndarray, kind: int, secs: np.ndarray, **kw: np.ndarray
    ) -> None:
        # An entry that rounds to zero cents moves nothing and is never posted.
        rounded = np.round(amt, 2)
        keep = np.abs(rounded) >= 0.01
        if not keep.all():
            acc, rounded, secs = acc[keep], rounded[keep], secs[keep]
            kw = {k: v[keep] for k, v in kw.items()}
        n = len(acc)
        if n == 0:
            return
        out["month"].append(np.full(n, month, np.int16))
        out["account"].append(acc.astype(np.int32))
        out["amount"].append(rounded)
        out["kind"].append(np.full(n, kind, np.int8))
        out["seconds"].append(secs.astype(np.int32))
        out["cp_account"].append(kw.get("cp_account", np.full(n, -1, np.int32)).astype(np.int32))
        out["cp_external"].append(kw.get("cp_external", np.full(n, -1, np.int32)).astype(np.int32))
        out["branch"].append(kw.get("branch", np.full(n, -1, np.int16)).astype(np.int16))
        out["group"].append(kw.get("group", np.full(n, -1, np.int64)).astype(np.int64))
        out["ref"].append(kw.get("ref", np.full(n, -1, np.int64)).astype(np.int64))

    def exact_balance(opening_: np.ndarray, first: int) -> np.ndarray:
        if len(out["account"]) <= first:
            return np.round(opening_, 2)
        acc_ = np.concatenate(out["account"][first:])
        amt_ = np.concatenate(out["amount"][first:])
        return np.round(opening_ + np.bincount(acc_, weights=amt_, minlength=n_acc), 2)

    for m in range(n_months):
        first_chunk = len(out["account"])
        month_start = timeline.months[m]
        days = 30
        opening = balance.copy()
        opening_new = book.open_month == m
        active = active | opening_new
        live = active & (closed_month < 0)
        net = np.zeros(n_acc)

        def secs(n: int, lo_h: int = 0, hi_h: int = 24, span: int = days) -> np.ndarray:
            out: np.ndarray = rng.integers(0, span - 2, n) * 86400 + rng.integers(lo_h * 3600, hi_h * 3600, n)
            return out

        # Account funding for accounts opened this month.
        fund = np.flatnonzero(opening_new)
        if len(fund):
            emit(m, fund, book.opening_balance[fund], TYPES["ACCOUNT_FUNDING"], secs(len(fund), 9, 17))
            np.add.at(net, fund, book.opening_balance[fund])

        chk = np.flatnonzero(live & (product == 0))
        c_of = cust[chk]
        u = unemployment[m]
        job_loss = rng.random(len(chk)) < 0.018 + 0.012 * max(0.0, u - 4.0)
        pay_total = income[c_of] / 12.0 * 0.74 * rng.lognormal(0, 0.06, len(chk)) * ~job_loss
        pay_total = np.where(opening_new[chk], pay_total * 0.5, pay_total)
        biweekly = rng.random(len(chk)) < 0.45
        # Payroll: one or two ACH credits.
        n_pay = np.where(pay_total > 0, 1 + biweekly, 0)
        idx = np.repeat(np.arange(len(chk)), n_pay)
        amt = pay_total[idx] / np.repeat(n_pay, n_pay)
        emit(m, chk[idx], amt, TYPES["PAYROLL_IN"], secs(len(idx), 5, 7))
        np.add.at(net, chk[idx], amt)

        ratio = np.clip(0.975 + 0.22 * (opening[chk] / np.maximum(target[c_of], 200) - 1.0), 0.55, 1.35)
        ratio = ratio * rng.lognormal(0, 0.06, len(chk))
        # Scheduled debits this month (loan payments) come out of the same paycheck.
        due = np.zeros(n_acc)
        sm_all = sched_by_month[m]
        if len(sm_all):
            neg = sched["amount"][sm_all] < 0
            np.add.at(due, sched["account"][sm_all][neg], -sched["amount"][sm_all][neg])
        budget = np.where(
            pay_total > 0,
            pay_total * ratio,
            np.minimum(np.maximum(opening[chk], 0), income[c_of] / 12.0 * 0.45),
        )
        spend = np.maximum(budget - due[chk], 0.08 * budget)
        bills = spend * 0.47
        card = spend * 0.41
        emit(m, chk, -bills, TYPES["BILL_PAY"], secs(len(chk), 6, 9))
        emit(m, chk, -card, TYPES["CARD_SPEND"], np.full(len(chk), (days - 1) * 86400 + 23 * 3600))
        np.add.at(net, chk, -(bills + card))

        n_atm = rng.poisson(0.45, len(chk))
        idx = np.repeat(np.arange(len(chk)), n_atm)
        amt = rng.choice(
            [40.0, 60.0, 80.0, 100.0, 200.0, 300.0], size=len(idx), p=[0.12, 0.22, 0.18, 0.28, 0.14, 0.06]
        )
        emit(m, chk[idx], -amt, TYPES["ATM_WITHDRAWAL"], secs(len(idx)))
        np.add.at(net, chk[idx], -amt)

        # Cash deposits at a branch. Cash intensive customers deposit often and just under round numbers.
        heavy = cash_intensive[c_of]
        n_cash = rng.poisson(np.where(heavy, 4.5, 0.07))
        idx = np.repeat(np.arange(len(chk)), n_cash)
        amt = np.where(
            heavy[idx], rng.uniform(900, 9_600, len(idx)), rng.lognormal(np.log(420), 0.8, len(idx))
        )
        amt = np.round(amt, 0)
        br = np.where(
            rng.random(len(idx)) < 0.8, branch_home[c_of[idx]], rng.integers(1, params.branches + 1, len(idx))
        )
        emit(m, chk[idx], amt, TYPES["CASH_DEPOSIT"], secs(len(idx), 9, 17), branch=br)
        np.add.at(net, chk[idx], amt)
        # Cash intensive depositors pay suppliers out of the same account.
        heavy_out = np.flatnonzero(heavy)
        if len(heavy_out):
            out_amt = n_cash[heavy_out] * 5_000.0 * rng.uniform(0.85, 1.0, len(heavy_out))
            emit(m, chk[heavy_out], -out_amt, TYPES["BILL_PAY"], secs(len(heavy_out), 6, 9))
            np.add.at(net, chk[heavy_out], -out_amt)

        # Person to person payments with each customer's circle, internal or external.
        n_p2p = rng.poisson(0.30, len(chk))
        idx = np.repeat(np.arange(len(chk)), n_p2p)
        if len(idx):
            pick = rng.integers(0, friends.shape[1], len(idx))
            peer = friends[c_of[idx], pick]
            amt = np.round(rng.lognormal(np.log(85), 0.85, len(idx)), 2)
            internal_peer = peer >= 0
            peer_acc = np.where(internal_peer, checking_of[np.maximum(peer, 0)], -1)
            peer_live = internal_peer & (peer_acc >= 0)
            peer_live[peer_live] = live[peer_acc[peer_live]]
            ext = ~peer_live
            s = secs(len(idx))
            ext_id = np.where(internal_peer, rng.integers(0, 400_000, len(idx)), -peer - 1)
            emit(m, chk[idx[ext]], -amt[ext], TYPES["P2P_OUT"], s[ext], cp_external=ext_id[ext])
            np.add.at(net, chk[idx[ext]], -amt[ext])
            ii = np.flatnonzero(peer_live)
            groups = np.arange(group_seq, group_seq + len(ii))
            group_seq += len(ii)
            emit(
                m,
                chk[idx[ii]],
                -amt[ii],
                TYPES["INTERNAL_TRANSFER"],
                s[ii],
                cp_account=peer_acc[ii],
                group=groups,
            )
            emit(
                m,
                peer_acc[ii],
                amt[ii],
                TYPES["INTERNAL_TRANSFER"],
                s[ii],
                cp_account=chk[idx[ii]],
                group=groups,
            )
            np.add.at(net, chk[idx[ii]], -amt[ii])
            np.add.at(net, peer_acc[ii], amt[ii])
        n_in = rng.poisson(0.22, len(chk))
        idx = np.repeat(np.arange(len(chk)), n_in)
        amt = np.round(rng.lognormal(np.log(95), 0.8, len(idx)), 2)
        emit(
            m, chk[idx], amt, TYPES["P2P_IN"], secs(len(idx)), cp_external=rng.integers(0, 400_000, len(idx))
        )
        np.add.at(net, chk[idx], amt)

        # Sweeps between a customer's own checking and savings.
        sav_of_chk = savings_of[c_of]
        has_sav = sav_of_chk >= 0
        has_sav[has_sav] = live[sav_of_chk[has_sav]]
        sweep = has_sav & (rng.random(len(chk)) < 0.34) & (pay_total > 0)
        k = np.flatnonzero(sweep)
        amt = np.round(pay_total[k] * rng.uniform(0.03, 0.10, len(k)), 2)
        groups = np.arange(group_seq, group_seq + len(k))
        group_seq += len(k)
        s = secs(len(k))
        emit(m, chk[k], -amt, TYPES["INTERNAL_TRANSFER"], s, cp_account=sav_of_chk[k], group=groups)
        emit(m, sav_of_chk[k], amt, TYPES["INTERNAL_TRANSFER"], s, cp_account=chk[k], group=groups)
        np.add.at(net, chk[k], -amt)
        np.add.at(net, sav_of_chk[k], amt)

        # Savings withdrawals and savings only deposits.
        sav = np.flatnonzero(live & (product == 1))
        wd = sav[rng.random(len(sav)) < 0.07]
        amt = np.round(np.maximum(opening[wd], 0) * rng.uniform(0.05, 0.30, len(wd)), 2)
        chk_of_sav = checking_of[cust[wd]]
        to_chk = chk_of_sav >= 0
        to_chk[to_chk] = live[chk_of_sav[to_chk]]
        k = np.flatnonzero(to_chk & (amt > 0))
        groups = np.arange(group_seq, group_seq + len(k))
        group_seq += len(k)
        s = secs(len(k))
        emit(m, wd[k], -amt[k], TYPES["INTERNAL_TRANSFER"], s, cp_account=chk_of_sav[k], group=groups)
        emit(m, chk_of_sav[k], amt[k], TYPES["INTERNAL_TRANSFER"], s, cp_account=wd[k], group=groups)
        np.add.at(net, wd[k], -amt[k])
        np.add.at(net, chk_of_sav[k], amt[k])
        k2 = np.flatnonzero(~to_chk & (amt > 0))
        emit(m, wd[k2], -amt[k2], TYPES["ACH_OUT"], secs(len(k2)))
        np.add.at(net, wd[k2], -amt[k2])
        sav_only = sav[checking_of[cust[sav]] < 0]
        dep = sav_only[rng.random(len(sav_only)) < 0.5]
        amt = np.round(income[cust[dep]] / 12.0 * rng.uniform(0.03, 0.12, len(dep)), 2)
        emit(m, dep, amt, TYPES["ACH_IN"], secs(len(dep), 5, 7))
        np.add.at(net, dep, amt)

        # Scheduled entries: loan payments and disbursements, and the injected typologies.
        sm = sched_by_month[m]
        if len(sm):
            acc = sched["account"][sm]
            ok = live[acc]
            # Both legs of a scheduled transfer post, or neither does.
            grp = sched["group"][sm]
            paired = grp >= 0
            if paired.any():
                bad_groups = np.unique(grp[paired & ~ok])
                ok = ok & ~np.isin(grp, bad_groups)
            sm = sm[ok]
            acc = acc[ok]
            out["month"].append(sched["month"][sm])
            out["account"].append(acc)
            out["amount"].append(sched["amount"][sm])
            out["kind"].append(sched["kind"][sm])
            out["seconds"].append(sched["seconds"][sm])
            out["cp_account"].append(sched["cp_account"][sm])
            out["cp_external"].append(sched["cp_external"][sm])
            out["branch"].append(sched["branch"][sm])
            out["group"].append(sched["group"][sm])
            out["ref"].append(sched["ref"][sm])
            np.add.at(net, acc, sched["amount"][sm])

        # Interest credits on interest bearing balances, at the account's own rate.
        earning = np.flatnonzero(live & ((product > 0) | book.interest_checking) & (opening > 0))
        acc_rate = np.where(
            product[earning] == 2,
            cd_rate[earning],
            np.maximum(0.01, rate_arr[1][m] + promo[earning]) * (product[earning] == 1)
            + rate_arr[0][m] * (product[earning] == 0),
        )
        interest = np.round(opening[earning] * acc_rate / 100.0 / 12.0, 2)
        pos = interest > 0
        emit(
            m,
            earning[pos],
            interest[pos],
            TYPES["INTEREST_CREDIT"],
            np.full(pos.sum(), (days - 1) * 86400 + 23 * 3600 + 1800),
        )
        np.add.at(net, earning[pos], interest[pos])

        # Certificates that mature this month renew at the current rate or pay out.
        mat = np.flatnonzero(live & (product == 2) & (cd_maturity == m))
        renew = rng.random(len(mat)) < 0.68
        cd_rate[mat[renew]] = rate_arr[2][m] + promo[mat[renew]]
        cd_maturity[mat[renew]] = m + term[mat[renew]]
        payout = mat[~renew]
        pay_amt = np.maximum(exact_balance(opening, first_chunk)[payout], 0)
        emit(m, payout, -pay_amt, TYPES["CD_PAYOUT"], secs(len(payout), 9, 17))
        np.add.at(net, payout, -pay_amt)
        closed_month[payout] = m

        closing = exact_balance(opening, first_chunk)
        # Fees: overdraft on a negative close, maintenance on low balance non digital checking.
        od = np.flatnonzero(live & (product == 0) & (closing < 0))
        emit(
            m,
            od,
            np.full(len(od), -30.0),
            TYPES["FEE_OVERDRAFT"],
            np.full(len(od), (days - 1) * 86400 + 23 * 3600 + 2700),
        )
        closing[od] -= 30.0
        low = live & (product == 0) & (closing < 1_500) & (closing >= 0)
        low &= ~digital[cust] & (segment[cust] != "affluent")
        mt = np.flatnonzero(low & (rng.random(n_acc) < 0.85))
        emit(
            m,
            mt,
            np.full(len(mt), -12.0),
            TYPES["FEE_MAINTENANCE"],
            np.full(len(mt), (days - 1) * 86400 + 23 * 3600 + 2760),
        )
        closing[mt] -= 12.0
        fee_now = np.zeros(n_acc, dtype=bool)
        fee_now[od] = True
        fee_now[mt] = True

        # Attrition of the primary checking relationship, with the stated drivers.
        chk_live = np.flatnonzero(live & (product == 0))
        cc = cust[chk_live]
        tenure_days = np.array([(month_start - open_dates[c]).days for c in cc])
        new_cust = tenure_days < 365
        decline = closing[chk_live] < 0.6 * np.maximum(prev_balance[chk_live], 1.0)
        has_sav_c = savings_of[cc] >= 0
        gap = np.where(
            has_sav_c, np.maximum(0.0, macro["policy_rate"].to_numpy()[m] - rate_arr[1][m] - 2.0), 0.0
        )
        logit = (
            a.intercept
            + a.new_customer * new_cust
            + a.balance_decline * decline
            + a.fee_last_month * fee_last[chk_live]
            + a.digital_active * digital[cc]
            + a.rate_gap_per_point * gap
            + a.complaint * complaint[cc]
        )
        hazard = 1.0 / (1.0 + np.exp(-logit))
        leave = chk_live[rng.random(len(chk_live)) < hazard]
        attr_rows.append(
            pl.DataFrame(
                {
                    "account_index": chk_live.astype(np.int32),
                    "month": [timeline.labels[m]] * len(chk_live),
                    "hazard": np.round(hazard, 6),
                }
            )
        )
        # A leaving customer moves the balance out and closes checking, and usually savings too.
        if len(leave):
            leave_c = cust[leave]
            customer_closed[leave_c] = m
            # An account that closes overdrawn has the overdraft charged off, so it closes at zero.
            owed = leave[closing[leave] < 0]
            if len(owed):
                emit(
                    m,
                    owed,
                    -closing[owed],
                    TYPES["OVERDRAFT_CHARGE_OFF"],
                    np.full(len(owed), (days - 1) * 86400 + 15 * 3600),
                )
                closing[owed] = 0.0
            out_amt = -np.maximum(closing[leave], 0)
            emit(
                m,
                leave,
                out_amt,
                TYPES["WIRE_OUT"],
                np.full(len(leave), (days - 1) * 86400 + 16 * 3600),
                cp_external=rng.integers(400_000, 500_000, len(leave)),
            )
            closing[leave] += out_amt
            closed_month[leave] = m
            sv = savings_of[leave_c]
            sv = sv[(sv >= 0)]
            sv = sv[live[sv] & (rng.random(len(sv)) < 0.7)]
            amt = -np.maximum(closing[sv], 0)
            emit(
                m,
                sv,
                amt,
                TYPES["WIRE_OUT"],
                np.full(len(sv), (days - 1) * 86400 + 16 * 3600 + 60),
                cp_external=rng.integers(400_000, 500_000, len(sv)),
            )
            closing[sv] += amt
            closed_month[sv] = m

        # The month's closing balance is the opening plus the rounded entries actually posted, to the cent.
        posted_acc = (
            np.concatenate(out["account"][first_chunk:])
            if len(out["account"]) > first_chunk
            else np.array([], dtype=np.int32)
        )
        posted_amt = (
            np.concatenate(out["amount"][first_chunk:]) if len(out["amount"]) > first_chunk else np.array([])
        )
        closing = np.round(opening + np.bincount(posted_acc, weights=posted_amt, minlength=n_acc), 2)
        live_idx = np.flatnonzero(live)
        bal_rows.append(
            pl.DataFrame(
                {
                    "account_index": live_idx.astype(np.int32),
                    "month": [timeline.labels[m]] * len(live_idx),
                    "opening_balance": opening[live_idx],
                    "closing_balance": closing[live_idx],
                    "closed_this_month": closed_month[live_idx] == m,
                }
            )
        )
        prev_balance = np.where(live, closing, prev_balance)
        balance = closing
        fee_last = fee_now
        rate_gap[:] = 0

    frame = {k: np.concatenate(v) if v else np.array([]) for k, v in out.items()}
    out.clear()
    order = np.lexsort((frame["seconds"], frame["month"]))
    frame = {k: v[order] for k, v in frame.items()}
    del order
    n_entries = len(frame["account"])
    # Transaction ids: two legs of one transfer share an id; every other entry is its own transaction.
    tx_id = np.arange(1, n_entries + 1, dtype=np.int64)
    gi = np.flatnonzero(frame["group"] >= 0)
    if len(gi):
        gvals = frame["group"][gi]
        g_order = np.argsort(gvals, kind="stable")
        sorted_g = gvals[g_order]
        first = np.r_[True, sorted_g[1:] != sorted_g[:-1]]
        first_pos = np.maximum.accumulate(np.where(first, np.arange(len(sorted_g)), 0))
        tx_sorted = tx_id[gi][g_order]
        tx_id[gi[g_order]] = tx_sorted[first_pos]
    labels = timeline.labels
    month_enum = pl.Enum(labels)
    type_enum = pl.Enum(sorted(TYPES, key=TYPES.__getitem__))
    month_start_us = np.array([np.datetime64(timeline.months[int(mm)], "us") for mm in range(n_months)])
    posted = month_start_us[frame["month"]] + frame["seconds"].astype("timedelta64[s]").astype(
        "timedelta64[us]"
    )
    id_map = pl.DataFrame(
        {"account_index": np.arange(n_acc, dtype=np.int32), "account_id": book.accounts["account_id"]}
    )
    entries = pl.DataFrame(
        {
            "entry_id": np.arange(1, n_entries + 1, dtype=np.int64),
            "transaction_id": tx_id,
            "account_index": frame["account"].astype(np.int32),
            "month": pl.Series(frame["month"].astype(np.int64)).replace_strict(
                dict(enumerate(labels)), return_dtype=month_enum
            ),
            "posted_at": posted,
            "txn_type": pl.Series(frame["kind"].astype(np.int64)).replace_strict(
                {k: v for k, v in TYPE_NAMES.items()}, return_dtype=type_enum
            ),
            "amount": frame["amount"],
            "cp_index": frame["cp_account"].astype(np.int32),
            "cp_external": frame["cp_external"].astype(np.int64),
            "branch_id": frame["branch"].astype(np.int16),
            "reference": frame["ref"].astype(np.int64),
        }
    )
    frame.clear()
    entries = (
        entries.join(id_map, on="account_index", how="left")
        .join(
            id_map.rename({"account_index": "cp_index", "account_id": "counterparty_account_id"}),
            on="cp_index",
            how="left",
        )
        .with_columns(
            counterparty_id=pl.when(pl.col("cp_external") >= 0)
            .then(pl.format("X{}", pl.col("cp_external").cast(pl.Utf8).str.zfill(6)))
            .otherwise(None),
            branch_id=pl.when(pl.col("branch_id") >= 0).then(pl.col("branch_id")).otherwise(None),
        )
        .drop("cp_index", "cp_external", "account_index")
    )

    balances = pl.concat(bal_rows).join(id_map, on="account_index", how="left").drop("account_index")
    balances = balances.with_columns(pl.col("month").cast(month_enum))
    closures = pl.DataFrame(
        {
            "account_id": book.accounts["account_id"],
            "closed_month": [labels[c] if c >= 0 else None for c in closed_month],
        }
    )
    attr = pl.concat(attr_rows).join(id_map, on="account_index", how="left").drop("account_index")
    return DepositResult(
        entries=entries, balances=balances, rates=rates, closures=closures, truth_attrition=attr
    )
