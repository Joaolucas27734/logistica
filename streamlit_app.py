# kpi.py
import pandas as pd
import numpy as np
from datetime import timedelta

def load_data(path_or_df, parse_dates=None):
    """
    Carrega CSV ou DataFrame e normaliza tipos.
    parse_dates: lista de colunas para converter em datetime
    """
    if isinstance(path_or_df, pd.DataFrame):
        df = path_or_df.copy()
    else:
        df = pd.read_csv(path_or_df)
    if parse_dates is None:
        parse_dates = ['order_date','supplier_post_date','tracking_first_update','delivery_date']
    for c in parse_dates:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors='coerce')
    # Normalize boolean-like columns
    for col in ['is_returned','is_lost','customs_retained']:
        if col in df.columns:
            df[col] = df[col].astype('boolean')
    # numeric
    for ncol in ['product_cost','shipping_cost','refund_amount','carrier_attempts','packaging_quality_score']:
        if ncol in df.columns:
            df[ncol] = pd.to_numeric(df[ncol], errors='coerce')
    return df

# ========== KPI functions ==========
def transit_time_international(df):
    """Transit Time International: supplier_post_date -> tracking_first_update or arrival to Brazil proxy"""
    mask = df['supplier_post_date'].notna() & df['tracking_first_update'].notna()
    s = (df.loc[mask,'tracking_first_update'] - df.loc[mask,'supplier_post_date']).dt.days
    return {'count': int(mask.sum()), 'median_days': float(s.median()) if len(s)>0 else None, 'mean_days': float(s.mean()) if len(s)>0 else None}

def time_to_delivery(df):
    """order_date -> delivery_date"""
    mask = df['order_date'].notna() & df['delivery_date'].notna()
    s = (df.loc[mask,'delivery_date'] - df.loc[mask,'order_date']).dt.days
    return {'count': int(mask.sum()), 'median_days': float(s.median()) if len(s)>0 else None, 'mean_days': float(s.mean()) if len(s)>0 else None}

def supplier_processing_time(df):
    """supplier_post_date - order_date"""
    mask = df['order_date'].notna() & df['supplier_post_date'].notna()
    s = (df.loc[mask,'supplier_post_date'] - df.loc[mask,'order_date']).dt.days
    return {'count': int(mask.sum()), 'median_days': float(s.median()) if len(s)>0 else None, 'mean_days': float(s.mean()) if len(s)>0 else None}

def percent_retained_customs(df):
    if 'customs_retained' not in df.columns:
        return None
    total = len(df)
    retained = df['customs_retained'].sum()
    return {'rate_percent': float(retained*100/total) if total>0 else None, 'retained': int(retained), 'total': int(total)}

def percent_lost(df):
    if 'is_lost' not in df.columns:
        return None
    total = len(df)
    lost = df['is_lost'].sum()
    return {'rate_percent': float(lost*100/total) if total>0 else None, 'lost': int(lost), 'total': int(total)}

def percent_returned(df):
    if 'is_returned' not in df.columns:
        return None
    total = len(df)
    returned = df['is_returned'].sum()
    return {'rate_percent': float(returned*100/total) if total>0 else None, 'returned': int(returned), 'total': int(total)}

def avg_carrier_attempts(df):
    if 'carrier_attempts' not in df.columns:
        return None
    return float(df['carrier_attempts'].dropna().mean())

def average_costs(df):
    cols = {}
    if 'shipping_cost' in df.columns:
        cols['shipping_cost_per_order'] = float(df['shipping_cost'].dropna().mean())
    if 'product_cost' in df.columns:
        cols['product_cost_per_order'] = float(df['product_cost'].dropna().mean())
    if 'refund_amount' in df.columns:
        cols['refund_amount_per_order'] = float(df['refund_amount'].dropna().mean())
    if 'shipping_cost' in df.columns and 'product_cost' in df.columns:
        cols['total_cost_per_order'] = float((df[['shipping_cost','product_cost']].sum(axis=1)).dropna().mean())
    return cols

def sla_on_time_rate(df, promised_days=30):
    """
    Consider delivery within order_date + promised_days as SLA met.
    """
    mask = df['order_date'].notna() & df['delivery_date'].notna()
    if mask.sum()==0:
        return None
    ontime = ((df.loc[mask,'delivery_date'] - df.loc[mask,'order_date']).dt.days <= promised_days).sum()
    return {'promised_days': promised_days, 'ontime_percent': float(ontime*100/mask.sum()), 'checked_orders': int(mask.sum())}

def contact_rate_per_order(df, contacts_column='contacts_count'):
    """
    If you have a column contacts_count per order (how many times the customer contacted support).
    """
    if contacts_column not in df.columns:
        return None
    total = len(df)
    return float(df[contacts_column].sum()/total)

def packaging_quality(df):
    if 'packaging_quality_score' not in df.columns:
        return None
    s = df['packaging_quality_score'].dropna()
    return {'mean_packaging_score': float(s.mean()), 'n': int(len(s))}

def kpi_report(df, promised_days=30):
    """
    Aggregates all KPIs into a dict (ready to transform to DataFrame/JSON).
    """
    report = {}
    report['transit_time_international'] = transit_time_international(df)
    report['time_to_delivery'] = time_to_delivery(df)
    report['supplier_processing_time'] = supplier_processing_time(df)
    report['percent_retained_customs'] = percent_retained_customs(df)
    report['percent_lost'] = percent_lost(df)
    report['percent_returned'] = percent_returned(df)
    report['avg_carrier_attempts'] = avg_carrier_attempts(df)
    report['average_costs'] = average_costs(df)
    report['sla_on_time_rate'] = sla_on_time_rate(df, promised_days=promised_days)
    report['packaging_quality'] = packaging_quality(df)
    return report

# helpers to export KPIs to a table
def kpis_to_dataframe(report):
    """
    Flatten the dict report into a one-row DataFrame for easy export.
    """
    flat = {}
    def _flatten(prefix, val):
        if isinstance(val, dict):
            for k,v in val.items():
                _flatten(f"{prefix}_{k}" if prefix else k, v)
        else:
            flat[prefix] = val
    _flatten("", report)
    df = pd.DataFrame([flat])
    return df
