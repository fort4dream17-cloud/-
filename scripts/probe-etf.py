#!/usr/bin/env python3
"""Small authenticated capability probe. Publishes schema/counts, not quote/PDF rows."""
import json
import time
from collect import authenticated_stock, atomic, now, collection_end
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    report = {'checked_at': now().isoformat(), 'status': 'failed',
              'source': 'KRX authenticated endpoints via pykrx 1.2.9',
              'publication_rights': 'unverified', 'raw_rows_published': False}
    try:
        stock = authenticated_stock()
        from pykrx.website.krx.etx.core import ETF_전종목기본종목, 전종목시세_ETF, PDF
        from datetime import timedelta
        end = collection_end(now())
        bench = stock.get_index_ohlcv_by_date((now()-timedelta(days=45)).strftime('%Y%m%d'), end, '1001')
        dates = [d.strftime('%Y%m%d') for d in bench.index][-2:]
        master = ETF_전종목기본종목().fetch(); time.sleep(1)
        quote = 전종목시세_ETF().fetch(dates[-1]); time.sleep(1)
        report.update({'as_of': dates[-1], 'previous_session': dates[-2],
                       'etf_master_count': len(master), 'quote_count': len(quote),
                       'master_columns': list(master.columns), 'quote_columns': list(quote.columns)})
        results=[]
        for _, r in master.head(3).iterrows():
            for date in dates:
                try:
                    frame=PDF().fetch(date, r['ISU_CD']); time.sleep(1)
                    results.append({'date': date, 'rows': len(frame), 'columns': list(frame.columns), 'ok': not frame.empty})
                except Exception as e:
                    results.append({'date': date, 'ok': False, 'error_type': type(e).__name__})
        report.update({'pdf_probe': results, 'status': 'success'})
    except Exception as e:
        report['error_type']=type(e).__name__
    atomic(ROOT/'dist/data/etf-capabilities.json', report)
    print(json.dumps(report, ensure_ascii=False))
    return report['status']!='success'

if __name__=='__main__':raise SystemExit(main())
