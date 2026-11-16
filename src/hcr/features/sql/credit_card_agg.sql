SELECT
    SK_ID_PREV,
    {select_list}
FROM credit_card_balance
GROUP BY SK_ID_PREV
