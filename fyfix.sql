DROP FUNCTION IF EXISTS fn_fy_closing_report(integer, integer);

CREATE OR REPLACE FUNCTION fn_fy_closing_report(
    p_society_id             INT,
    p_fy                     INT
)
 RETURNS TABLE (
    account_id           INT,
    account_name         TEXT,
    tab_name             TEXT,
    parent_account_id    INT,
    drcr_account         TEXT,
    has_bf               BOOLEAN,
    own_bf               NUMERIC(15,2),
    own_movement         NUMERIC(15,2),
    depreciation_charge  NUMERIC(15,2),
    own_closing          NUMERIC(15,2),
    total_closing        NUMERIC(15,2),
    display_side         TEXT,
    display_amount       NUMERIC(15,2),
    depth                INT,
    sort_path            TEXT
) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_fy_start DATE := MAKE_DATE(p_fy, 4, 1);
    v_fy_end   DATE := MAKE_DATE(p_fy + 1, 3, 31);
    v_total_depreciation NUMERIC(15,2);
    v_depreciation_acc_id INT;
BEGIN
    v_depreciation_acc_id := fn_resolve_depreciation_account(p_society_id);

    SELECT COALESCE(SUM(fn_account_depreciation(p_society_id, a.id, p_fy)), 0)
    INTO v_total_depreciation
    FROM accounts a
    WHERE a.society_id = p_society_id;

    RETURN QUERY
    WITH RECURSIVE tree AS (
        SELECT a.id, a.parent_account_id, 0 AS depth,
               LPAD(a.id::TEXT, 10, '0') AS sort_path
        FROM accounts a
        WHERE a.society_id = p_society_id AND a.parent_account_id IS NULL
        UNION ALL
        SELECT c.id, c.parent_account_id, t.depth + 1,
               t.sort_path || '.' || LPAD(c.id::TEXT, 10, '0')
        FROM accounts c
        JOIN tree t ON c.parent_account_id = t.id
        WHERE c.society_id = p_society_id
    ),
    leaf_closing AS (
        SELECT
            a.id,
            a.name::TEXT,
            a.tab_name::TEXT,
            a.parent_account_id,
            a.drcr_account::TEXT,
            a.has_bf,
            CASE WHEN a.has_bf THEN -fn_resolve_bf_amount_fy(p_society_id, a.id, p_fy) ELSE 0 END AS own_bf,
            COALESCE((
                SELECT SUM(CASE WHEN t.entry_side = 'Cr' THEN t.amount
                                 WHEN t.entry_side = 'Dr' THEN -t.amount
                                 ELSE 0 END)
                FROM transactions t
                WHERE t.acc_id = a.id AND t.society_id = p_society_id
                  AND t.status = 'paid'
                  AND t.trx_date BETWEEN v_fy_start AND v_fy_end
            ), 0)
            - CASE WHEN a.id = v_depreciation_acc_id THEN v_total_depreciation ELSE 0 END
              AS own_movement_raw,
            fn_account_depreciation(p_society_id, a.id, p_fy) AS depreciation_charge,
            tree.depth,
            tree.sort_path
        FROM accounts a
        JOIN tree ON tree.id = a.id
        WHERE a.society_id = p_society_id
    ),
    leaf_final AS (
        SELECT
            lc.id, lc.name, lc.tab_name, lc.parent_account_id, lc.drcr_account, lc.has_bf,
            lc.depth, lc.sort_path,
            lc.own_bf, (lc.own_movement_raw + lc.depreciation_charge) AS own_movement,
            lc.depreciation_charge,
            (lc.own_bf + lc.own_movement_raw + lc.depreciation_charge) AS own_closing
        FROM leaf_closing lc
    ),
    ancestry AS (
        SELECT id AS acc_id, id AS ancestor_id
        FROM leaf_final
        UNION ALL
        SELECT anc.acc_id, lf.parent_account_id
        FROM ancestry anc
        JOIN leaf_final lf ON lf.id = anc.ancestor_id
        WHERE lf.parent_account_id IS NOT NULL
    ),
    rollup AS (
        SELECT anc.ancestor_id AS id, SUM(lf.own_closing) AS total_closing
        FROM ancestry anc
        JOIN leaf_final lf ON lf.id = anc.acc_id
        GROUP BY anc.ancestor_id
    )
    SELECT
        lf.id, lf.name, lf.tab_name, lf.parent_account_id, lf.drcr_account, lf.has_bf,
        lf.own_bf, lf.own_movement, lf.depreciation_charge, lf.own_closing,
        r.total_closing,
        CASE WHEN r.total_closing >= 0 THEN 'Cr' ELSE 'Dr' END,
        ABS(r.total_closing),
        lf.depth,
        lf.sort_path
    FROM leaf_final lf
    JOIN rollup r ON r.id = lf.id
    ORDER BY lf.sort_path;
END;
$$;