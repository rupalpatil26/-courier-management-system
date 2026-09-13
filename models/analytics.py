import logging
from datetime import datetime, timedelta
from db import query_db
from models.parcel import STATUS_LIST

logger = logging.getLogger(__name__)

def get_analytics_dashboard_data(date_from=None, date_to=None, branch_id=None, staff_id=None, status=None):
    """
    Compute aggregated metrics and dataset series for the 6 Chart.js charts.
    """
    where_clauses = ["1=1"]
    params = []

    if date_from:
        where_clauses.append("date(date_created) >= ?")
        params.append(date_from)
    if date_to:
        where_clauses.append("date(date_created) <= ?")
        params.append(date_to)
    if branch_id and str(branch_id) != 'all' and str(branch_id).strip() != '':
        where_clauses.append("(from_branch_id = ? OR to_branch_id = ?)")
        params.extend([branch_id, branch_id])
    if staff_id and str(staff_id) != 'all' and str(staff_id).strip() != '':
        where_clauses.append("assigned_staff_id = ?")
        params.append(staff_id)
    if status is not None and str(status) != 'all' and str(status).strip() != '':
        where_clauses.append("status = ?")
        params.append(int(status))

    where_sql = " AND ".join(where_clauses)

    # 1. Summary Metrics
    total_parcels = query_db(f"SELECT COUNT(*) as cnt FROM parcels WHERE {where_sql}", tuple(params), one=True)['cnt']
    delivered_count = query_db(f"SELECT COUNT(*) as cnt FROM parcels WHERE {where_sql} AND status = 7", tuple(params), one=True)['cnt']
    failed_count = query_db(f"SELECT COUNT(*) as cnt FROM parcels WHERE {where_sql} AND status = 9", tuple(params), one=True)['cnt']
    in_transit_count = query_db(f"SELECT COUNT(*) as cnt FROM parcels WHERE {where_sql} AND status IN (1,2,3,4,5,6)", tuple(params), one=True)['cnt']

    rev_row = query_db(f"SELECT SUM(price) as total_rev FROM parcels WHERE {where_sql}", tuple(params), one=True)
    total_revenue = float(rev_row['total_rev'] or 0.0) if rev_row else 0.0

    success_rate = round((delivered_count / (delivered_count + failed_count) * 100), 1) if (delivered_count + failed_count) > 0 else 100.0

    avg_rating_row = query_db("SELECT AVG(rating) as avg_r FROM parcel_feedback", one=True)
    avg_rating = round(float(avg_rating_row['avg_r'] or 5.0), 1) if avg_rating_row else 5.0

    # 2. Chart 1: Shipment Trends (Group by Month or Date)
    trend_rows = query_db(
        f"""
        SELECT strftime('%Y-%m', date_created) as period, COUNT(*) as volume, SUM(price) as rev
        FROM parcels WHERE {where_sql}
        GROUP BY period ORDER BY period ASC LIMIT 12
        """,
        tuple(params)
    )
    trend_labels = [r['period'] for r in trend_rows] if trend_rows else ['Current']
    trend_volumes = [r['volume'] for r in trend_rows] if trend_rows else [total_parcels]
    trend_revenues = [float(r['rev'] or 0) for r in trend_rows] if trend_rows else [total_revenue]

    # 3. Chart 2: Status Breakdown
    status_rows = query_db(
        f"""
        SELECT status, COUNT(*) as cnt
        FROM parcels WHERE {where_sql}
        GROUP BY status
        """,
        tuple(params)
    )
    status_map = {r['status']: r['cnt'] for r in status_rows}
    status_labels = []
    status_data = []
    for idx, name in enumerate(STATUS_LIST):
        cnt = status_map.get(idx, 0)
        if cnt > 0 or idx in (0, 3, 5, 7, 9):
            status_labels.append(name)
            status_data.append(cnt)

    # 4. Chart 3: Branch Volumes
    branch_rows = query_db(
        """
        SELECT b.id, b.branch_code, b.city,
               COUNT(p.id) as outgoing_count
        FROM branches b
        LEFT JOIN parcels p ON p.from_branch_id = b.id
        GROUP BY b.id
        ORDER BY outgoing_count DESC
        """
    )
    branch_labels = [f"{b['branch_code']} ({b['city']})" for b in branch_rows]
    branch_data = [b['outgoing_count'] for b in branch_rows]

    # 5. Chart 4: Delivery Outcome / Success Rate (Delivered vs Failed vs In-Transit vs Accepted)
    outcome_labels = ['Delivered', 'In-Transit / Out for Delivery', 'Accepted / Pending', 'Unsuccessful']
    outcome_data = [
        delivered_count,
        in_transit_count,
        status_map.get(0, 0),
        failed_count
    ]

    # 6. Chart 5: Revenue Trends
    # We can reuse trend_labels and trend_revenues for Revenue Trends

    # 7. Chart 6: Staff Performance (Parcels delivered by assigned staff)
    staff_rows = query_db(
        """
        SELECT u.id, concat(u.firstname, ' ', u.lastname) as staff_name,
               SUM(CASE WHEN p.status = 7 THEN 1 ELSE 0 END) as delivered_cnt,
               COUNT(p.id) as total_assigned
        FROM users u
        LEFT JOIN parcels p ON p.assigned_staff_id = u.id
        WHERE u.type = 2
        GROUP BY u.id
        ORDER BY delivered_cnt DESC
        """
    )
    staff_labels = [s['staff_name'] for s in staff_rows] if staff_rows else ['No Staff']
    staff_delivered_data = [s['delivered_cnt'] for s in staff_rows] if staff_rows else [0]
    staff_assigned_data = [s['total_assigned'] for s in staff_rows] if staff_rows else [0]

    return {
        'summary': {
            'total_parcels': total_parcels,
            'delivered_count': delivered_count,
            'failed_count': failed_count,
            'in_transit_count': in_transit_count,
            'total_revenue': total_revenue,
            'success_rate': success_rate,
            'avg_rating': avg_rating
        },
        'charts': {
            'trend': {
                'labels': trend_labels,
                'volumes': trend_volumes,
                'revenues': trend_revenues
            },
            'status': {
                'labels': status_labels,
                'data': status_data
            },
            'branch': {
                'labels': branch_labels,
                'data': branch_data
            },
            'outcome': {
                'labels': outcome_labels,
                'data': outcome_data
            },
            'staff': {
                'labels': staff_labels,
                'delivered': staff_delivered_data,
                'assigned': staff_assigned_data
            }
        }
    }
