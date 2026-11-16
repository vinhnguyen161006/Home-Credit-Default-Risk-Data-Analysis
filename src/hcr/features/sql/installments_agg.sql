SELECT
    SK_ID_PREV,
    {select_list}
FROM installments_payments
GROUP BY SK_ID_PREV
