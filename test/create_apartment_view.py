#!/usr/bin/env python3
"""
Create PostgreSQL View: v_apartments_list
Using direct psycopg2 connection (same pattern as create_test_society_direct.py)

Usage:
    python3 create_apartment_view_direct.py
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

VIEW_SQL = """
CREATE OR REPLACE VIEW v_apartments_list AS

WITH apartment_data AS (
    SELECT
        a.*,
        s.arrear_start_date,

        (
            EXTRACT(YEAR FROM AGE(CURRENT_DATE, s.arrear_start_date)) * 12
            +
            EXTRACT(MONTH FROM AGE(CURRENT_DATE, s.arrear_start_date))
        )::INTEGER AS months_due,

        3.0::NUMERIC AS rate_per_sqft

    FROM apartments a
    JOIN societies s
        ON a.society_id = s.id
),

payment_summary AS (
    SELECT
        apartment_id,

        COALESCE(
            SUM(amount) FILTER (WHERE status = 'verified'),
            0
        ) AS paid_amount,

        COALESCE(
            SUM(amount) FILTER (WHERE status = 'pending'),
            0
        ) AS pending_amount

    FROM payments
    GROUP BY apartment_id
),

late_fee_calc AS (
    SELECT
        apartment_id,

        COALESCE(
            SUM(
                CASE
                    WHEN due_date < CURRENT_DATE THEN
                        amount
                        * 0.02
                        * EXTRACT(DAY FROM AGE(CURRENT_DATE, due_date))
                        / 30
                    ELSE 0
                END
            ),
            0
        ) AS late_fee

    FROM payments
    WHERE status = 'pending'
    GROUP BY apartment_id
)

SELECT
    ad.*,

    COALESCE(ps.paid_amount, 0) AS paid_amount,
    COALESCE(ps.pending_amount, 0) AS pending_amount,

    COALESCE(lf.late_fee, 0) AS late_fee,

    (
        ad.apartment_size
        * ad.rate_per_sqft
        * GREATEST(ad.months_due, 0)
    ) AS total_maintenance_due,

    (
        (
            ad.apartment_size
            * ad.rate_per_sqft
            * GREATEST(ad.months_due, 0)
        )
        - COALESCE(ps.paid_amount, 0)
        + COALESCE(lf.late_fee, 0)
    ) AS pending_dues

FROM apartment_data ad

LEFT JOIN payment_summary ps
    ON ad.id = ps.apartment_id

LEFT JOIN late_fee_calc lf
    ON ad.id = lf.apartment_id;
"""


def create_view():
    """Create or replace apartment view"""

    print("=" * 60)
    print("CREATE VIEW: v_apartments_list")
    print("=" * 60)

    # Connection parameters
    pg_host = os.getenv('PGHOST', '').strip("'\"")
    pg_database = os.getenv('PGDATABASE', '').strip("'\"")
    pg_user = os.getenv('PGUSER', '').strip("'\"")
    pg_password = os.getenv('PGPASSWORD', '').strip("'\"")
    pg_sslmode = os.getenv('PGSSLMODE', 'require').strip("'\"")

    print(f"\nConnecting to: {pg_host}/{pg_database}")

    try:
        # Direct PostgreSQL connection
        conn = psycopg2.connect(
            host=pg_host,
            database=pg_database,
            user=pg_user,
            password=pg_password,
            sslmode=pg_sslmode
        )

        conn.autocommit = True
        cur = conn.cursor()

        print("\n1. Creating/Replacing View...")
        cur.execute(VIEW_SQL)

        print("   ✅ View created successfully")

        # Verify view exists
        print("\n2. Verifying view...")

        cur.execute("""
            SELECT table_name
            FROM information_schema.views
            WHERE table_name = 'v_apartments_list'
        """)

        exists = cur.fetchone()

        if exists:
            print("   ✅ View exists in database")
        else:
            print("   ❌ View verification failed")
            return False

        # Test query
        print("\n3. Testing view query...")

        cur.execute("""
            SELECT COUNT(*) 
            FROM v_apartments_list
        """)

        result = cur.fetchone()

        if result:
            print(f"   ✅ View query successful")
            print(f"   Total rows: {result[0]}")

        # Sample columns
        print("\n4. Fetching columns...")

        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'v_apartments_list'
            ORDER BY ordinal_position
        """)

        columns = cur.fetchall()

        print(f"   ✅ Total columns: {len(columns)}")

        for col in columns[:10]:
            print(f"      - {col[0]}")

        if len(columns) > 10:
            print(f"      ... and {len(columns)-10} more")

        cur.close()
        conn.close()

        print("\n" + "=" * 60)
        print("VIEW CREATED SUCCESSFULLY")
        print("=" * 60)

        return True

    except psycopg2.errors.UndefinedTable as e:
        print(f"\n❌ Table missing: {e}")
        print("\nRun migrations first.")
        return False

    except Exception as e:
        print(f"\n❌ Error: {e}")

        import traceback
        traceback.print_exc()

        return False


if __name__ == "__main__":
    create_view()

"""
    WITH 
    apartment_data AS 
        ( 
        SELECT a.id, a.society_id, a.flat_number, a.owner_name, a.mobile, a.apartment_size, a.active, a.created_at, s.arrear_start_date,
        (((EXTRACT(year FROM age((CURRENT_DATE)::timestamp with time zone, (s.arrear_start_date)::timestamp with time zone)) * (12)::numeric) +
            EXTRACT(month   FROM age((CURRENT_DATE)::timestamp with time zone, (s.arrear_start_date)::timestamp with time zone))))::integer AS months_due,
        3.0 AS rate_per_sqft
    FROM 
        (apartments a JOIN societies s ON ((a.society_id = s.id))) ),
    payment_summary AS 
        ( SELECT payments.apartment_id, COALESCE(sum(payments.amount) FILTER (WHERE ((payments.status)::text = 'verified'::text)), (0)::numeric) AS paid_amount,
        COALESCE(sum(payments.amount) FILTER (WHERE ((payments.status)::text = 'pending'::text)), (0)::numeric) AS pending_amount 
        FROM 
            payments 
        GROUP BY 
            payments.apartment_id ) 
    late_fee_calc AS 
        ( SELECT payments.apartment_id, COALESCE(sum( CASE WHEN (payments.due_date < CURRENT_DATE) THEN 
            (((payments.amount * 0.02) * EXTRACT(day FROM age((CURRENT_DATE)::timestamp with time zone, (payments.due_date)::timestamp with time zone))) / (30)::numeric) 
        ELSE (0)::numeric END), (0)::numeric) AS late_fee 
        FROM 
            payments WHERE ((payments.status)::text = 'pending'::text) 
        GROUP BY 
            payments.apartment_id ) 
        SELECT ad.id, ad.society_id, ad.flat_number, ad.owner_name, ad.mobile, ad.apartment_size, ad.active, ad.created_at, ad.arrear_start_date, ad.months_due, ad.rate_per_sqft, 
        COALESCE(ps.paid_amount, (0)::numeric) AS paid_amount,
        COALESCE(ps.pending_amount, (0)::numeric) AS pending_amount,
        COALESCE(lf.late_fee, (0)::numeric) AS late_fee, 
        (((ad.apartment_size)::numeric * ad.rate_per_sqft) * (GREATEST(ad.months_due, 0))::numeric) AS total_maintenance_due, 
        (((((ad.apartment_size)::numeric * ad.rate_per_sqft) * (GREATEST(ad.months_due, 0))::numeric) - COALESCE(ps.paid_amount, (0)::numeric)) + COALESCE(lf.late_fee, (0)::numeric)) AS pending_dues 
        FROM 
            ((apartment_data ad LEFT JOIN payment_summary ps ON ((ad.id = ps.apartment_id))) LEFT JOIN late_fee_calc lf ON ((ad.id = lf.apartment_id)));
"""