select * from {{ ref('mart_hmda_denial_by_group') }} where denial_rate < 0 or denial_rate > 1 or denials > applications
