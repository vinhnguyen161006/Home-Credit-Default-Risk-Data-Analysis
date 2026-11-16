SELECT
    SK_ID_CURR,
    {select_list}
FROM bureau
LEFT JOIN bureau_balance_stage_one USING (SK_ID_BUREAU)
GROUP BY SK_ID_CURR
