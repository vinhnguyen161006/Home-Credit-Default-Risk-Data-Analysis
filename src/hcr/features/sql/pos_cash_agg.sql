SELECT
    SK_ID_PREV,
    {select_list}
FROM pos_cash_balance
GROUP BY SK_ID_PREV
