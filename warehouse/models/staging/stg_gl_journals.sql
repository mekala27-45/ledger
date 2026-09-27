select journal_id, description, gl_account, {{ money('amount') }} as amount, posted_at, month
from {{ source('generated', 'gl_journals') }}
