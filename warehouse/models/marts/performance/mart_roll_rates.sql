-- Month to month transitions between delinquency buckets for installment loans open at
-- the start of the month. Rows are the bucket at the start of the month; each row sums to one.
with t as (
    select month, bucket_open as from_bucket, bucket as to_bucket, count(*) as loans, sum(opening_balance) as balance
    from {{ ref('fct_loan_month') }}
    where product = 'installment' and bucket_open in ('current', '30', '60', '90+')
    group by 1, 2, 3
)
select
    month,
    from_bucket,
    to_bucket,
    loans,
    balance,
    loans / sum(loans) over (partition by month, from_bucket) as rate
from t
