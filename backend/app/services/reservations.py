from decimal import Decimal
from typing import Dict, Any, List

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    """
    Calculates revenue for a specific month.

    Month boundaries are in the property's local timezone, not UTC
    (e.g. 2024-02-29 23:30 UTC is already March in Paris).
    """
    from sqlalchemy import text
    from app.core.database_pool import db_pool

    await db_pool.initialize()

    query = text("""
        SELECT COALESCE(SUM(r.total_amount), 0) AS total
        FROM reservations r
        JOIN properties p
          ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
          AND r.tenant_id = :tenant_id
          AND (r.check_in_date AT TIME ZONE p.timezone) >= make_timestamp(:year, :month, 1, 0, 0, 0)
          AND (r.check_in_date AT TIME ZONE p.timezone) <  make_timestamp(:year, :month, 1, 0, 0, 0) + INTERVAL '1 month'
    """)

    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "year": year,
            "month": month,
        })
        total = result.scalar()

    return Decimal(str(total or 0))

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        # Reuse the shared pool rather than building a new engine per request
        from app.core.database_pool import db_pool

        await db_pool.initialize()
        
        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                # Use SQLAlchemy text for raw SQL
                from sqlalchemy import text
                
                query = text("""
                    SELECT 
                        property_id,
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count
                    FROM reservations 
                    WHERE property_id = :property_id AND tenant_id = :tenant_id
                    GROUP BY property_id
                """)
                
                result = await session.execute(query, {
                    "property_id": property_id, 
                    "tenant_id": tenant_id
                })
                row = result.fetchone()
                
                if row:
                    total_revenue = Decimal(str(row.total_revenue))
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": str(total_revenue),
                        "currency": "USD", 
                        "count": row.reservation_count
                    }
                else:
                    # No reservations found for this property
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": "0.00",
                        "currency": "USD",
                        "count": 0
                    }
        else:
            raise Exception("Database pool not available")
            
    except Exception as e:
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        
        # No mock fallback - it was keyed by property only and leaked
        # numbers across tenants.
        raise
