SELECT
    SK_ID_BUREAU,
    {select_list}
FROM bureau_balance
GROUP BY SK_ID_BUREAU
