-- Harborline's own mortgage applications in the HMDA layout. Demographic fields are
-- collected because the law requires it, and nothing downstream joins them to a model.
select hmda_application_id, month, action_taken, derived_race, derived_ethnicity, derived_sex, denial_reason_1
from {{ source('generated', 'hmda_style_applications') }}
