select * from {{ ref('mart_recoveries') }} where recovery_rate < 0 or recovery_rate > 1
