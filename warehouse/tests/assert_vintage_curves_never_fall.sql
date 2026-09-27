-- A cumulative default rate cannot decrease with months on book.
select vintage, months_on_book
from (
    select vintage, months_on_book, cumulative_default_rate,
        lag(cumulative_default_rate) over (partition by vintage order by months_on_book) as previous
    from {{ ref('mart_vintage_curves') }}
)
where cumulative_default_rate < previous
