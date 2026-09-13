from datetime import datetime
from db import query_db
from models.parcel import STATUS_LIST

def format_report_date(dt_val):
    if not dt_val:
        return ""
    if isinstance(dt_val, str):
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                dt_val = datetime.strptime(dt_val.strip(), fmt)
                break
            except ValueError:
                pass
    if isinstance(dt_val, datetime):
        return dt_val.strftime("%b %d, %Y")
    return str(dt_val)

def get_report_data(date_from, date_to, status='all'):
    where_clauses = ["date(date_created) BETWEEN ? AND ?"]
    params = [date_from, date_to]

    if status != 'all' and status is not None and str(status).strip() != '':
        where_clauses.append("status = ?")
        params.append(int(status))

    sql = f"SELECT * FROM parcels WHERE {' AND '.join(where_clauses)} ORDER BY unix_timestamp(date_created) ASC"
    rows = query_db(sql, tuple(params))

    results = []
    for r in rows:
        st_idx = r['status']
        st_name = STATUS_LIST[st_idx] if 0 <= st_idx < len(STATUS_LIST) else str(st_idx)
        p_val = float(r['price']) if r['price'] is not None else 0.0
        results.append({
            'id': r['id'],
            'reference_number': r['reference_number'],
            'sender_name': (r['sender_name'] or '').title(),
            'recipient_name': (r['recipient_name'] or '').title(),
            'date_created': format_report_date(r['date_created']),
            'status': st_name,
            'price': f"{p_val:,.2f}"
        })
    return results
