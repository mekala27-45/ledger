-- Every posting ties to a transaction in a sub ledger: a deposit entry, a loan event or a journal line.
select p.posting_id, p.source_type
from {{ ref('stg_gl_postings') }} as p
anti join {{ ref('stg_deposit_entries') }} as e on e.entry_id = p.source_id
where p.source_type = 'deposit_entry'
union all
select p.posting_id, p.source_type
from {{ ref('stg_gl_postings') }} as p
anti join {{ ref('stg_loan_events') }} as l on l.event_id = p.source_id
where p.source_type = 'loan_event'
union all
select p.posting_id, p.source_type
from {{ ref('stg_gl_postings') }} as p
anti join {{ ref('stg_gl_journals') }} as j on j.journal_id = p.source_id
where p.source_type = 'gl_journal'
