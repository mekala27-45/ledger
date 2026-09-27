-- Cash deposits by account and day, with the branches used. The structuring rule reads this.
select
    account_id,
    customer_id,
    posted_date,
    count(*) as cash_deposits,
    sum(amount) as cash_amount,
    max(amount) as largest_deposit,
    count(distinct branch_id) as branches
from {{ ref('fct_deposit_entry') }}
where txn_type = 'CASH_DEPOSIT'
group by 1, 2, 3
