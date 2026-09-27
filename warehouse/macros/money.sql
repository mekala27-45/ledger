{#- Money is carried as DECIMAL(18, 2) from staging onward, so every sum is exact to the cent. -#}
{% macro money(expr) -%}
    cast({{ expr }} as decimal(18, 2))
{%- endmacro %}

{% macro month_index(month_expr) -%}
    (cast(substr({{ month_expr }}, 1, 4) as integer) * 12 + cast(substr({{ month_expr }}, 6, 2) as integer)
     - (2023 * 12 + 9))
{%- endmacro %}

{% macro dpd_bucket(state_expr) -%}
    case {{ state_expr }}
        when 'current' then 'current'
        when 'dpd30' then '30'
        when 'dpd60' then '60'
        when 'dpd90' then '90+'
        when 'dpd120' then '90+'
        when 'dpd150' then '90+'
        when 'charged_off' then 'charged_off'
        when 'paid_off' then 'paid_off'
        when 'matured' then 'paid_off'
    end
{%- endmacro %}
