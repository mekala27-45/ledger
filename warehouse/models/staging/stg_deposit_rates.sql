select month, policy_rate, checking_rate, savings_rate, time_rate
from {{ source('generated', 'deposit_rates') }}
