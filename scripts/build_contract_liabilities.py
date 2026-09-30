"""Collect separately disclosed contract liabilities from official MOPS balance sheets.

Sequential, resumable collection. Missing lines are unknown, never zero. This does
not extract unstructured financial-statement notes or insurance liabilities.
"""
from __future__ import annotations
import argparse
import datetime as dt
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import requests
from util import DATA_DIR, read_json, write_json, log

URL = 'https://mopsov.twse.com.tw/mops/web/ajax_t164sb03'
SOURCE = 'https://mopsov.twse.com.tw/mops/web/t164sb03'

class Rows(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=[]; self.cell=None
    def handle_starttag(self, tag, attrs):
        if tag == 'tr': self.row=[]
        if tag in ('td','th'): self.cell=[]
    def handle_data(self, value):
        if self.cell is not None: self.cell.append(value)
    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(''.join(self.cell).strip()); self.cell=None
        if tag == 'tr' and self.row: self.rows.append(self.row); self.row=[]

def parse_report(html, year, quarter):
    if any(x in html for x in ('因為安全性考量','Access Denied','請稍後再試')):
        raise RuntimeError('Official site requested a pause')
    period = re.search(r'民國\s*(\d+)\s*年第\s*(\d+)\s*季', html)
    if not period: return None
    if (int(period[1])+1911,int(period[2])) != (year,quarter):
        raise ValueError('Report period does not match request')
    if '新台幣仟元' not in html and '新臺幣仟元' not in html:
        raise ValueError('Unrecognized currency or unit')
    parser=Rows(); parser.feed(html)
    amounts={'current':None,'noncurrent':None,'total':None}
    names={'合約負債流動':'current','合約負債非流動':'noncurrent','合約負債':'total','合約負債合計':'total'}
    for row in parser.rows:
        name=re.sub(r'[\s\-－—–─]','',row[0])
        if name not in names or len(row)<2: continue
        raw=row[1].replace(',','').strip()
        if re.fullmatch(r'-?\d+(?:\.\d+)?',raw): amounts[names[name]]=round(float(raw)*1000)
    if amounts['total'] is None and all(amounts[k] is not None for k in ('current','noncurrent')):
        amounts['total']=amounts['current']+amounts['noncurrent']
    return dict(amounts,year=year,quarter=quarter,
                basis='合併' if '合併資產負債表' in html else '個別',
                status='disclosed' if any(v is not None for v in amounts.values()) else 'not_separately_disclosed')

def main(max_requests=80, delay=5.0, refresh_days=7):
    path=DATA_DIR/'contract_liabilities.json'
    data=read_json(path,{}) or {}; records=data.setdefault('stocks',{})
    if data.get('retryAfter') and dt.datetime.fromisoformat(data['retryAfter']) > dt.datetime.now(dt.timezone.utc):
        log('Contract liabilities cooling down after official source failure'); return 0
    rows=read_json(DATA_DIR/'latest.json',[]) or []
    today=dt.date.today(); periods=[(r['fin']['y'],r['fin']['q']) for r in rows if r.get('fin')]
    default=max(set(periods),key=periods.count) if periods else (today.year-1,4)
    def priority(r):
        old=records.get(r['c'],{}); target=(r.get('fin',{}).get('y',default[0]),r.get('fin',{}).get('q',default[1]))
        return (bool(old), (old.get('year'),old.get('quarter'))==target, old.get('checkedAt',''),r['c'])
    session=requests.Session(); session.headers['User-Agent']='Mozilla/5.0 (compatible; PublicFinancialDataReader/1.0)'
    count=0
    for r in sorted(rows,key=priority):
        if count>=max_requests: break
        code=r['c']; old=records.get(code,{})
        year=r.get('fin',{}).get('y',default[0]); quarter=r.get('fin',{}).get('q',default[1])
        if old.get('checkedAt') and (old.get('year'),old.get('quarter'))==(year,quarter):
            if (today-dt.date.fromisoformat(old['checkedAt'])).days<refresh_days: continue
        count+=1
        try:
            response=session.post(URL,data={'encodeURIComponent':'1','step':'1','firstin':'1','off':'1','isQuery':'Y','co_id':code,'year':str(year-1911),'season':f'{quarter:02d}'},timeout=25)
            response.raise_for_status(); response.encoding='utf-8'
            rec=parse_report(response.text,year,quarter)
            if rec is None:
                if old.get('status')=='disclosed': continue
                rec={'year':year,'quarter':quarter,'status':'unavailable','current':None,'noncurrent':None,'total':None}
            rec['checkedAt']=today.isoformat();rec['source']=SOURCE+'?co_id='+code+'&year='+str(year-1911)+'&season='+f'{quarter:02d}'
            records[code]=rec
            data['updatedAt']=dt.datetime.now(dt.timezone.utc).isoformat();data['unit']='TWD';data['scope']='資產負債表單獨列示項目；未列示不代表零，附註未涵蓋'
            write_json(path,data)
        except (requests.RequestException,RuntimeError) as exc:
            log(f'Contract liabilities paused at {code}: {type(exc).__name__} {exc}')
            data['retryAfter']=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=6)).isoformat()
            write_json(path,data);break
        except ValueError as exc:
            log(f'Contract liabilities skipped {code}: {exc}')
        if count%50==0: log(f'Contract liabilities: {count} requests; {len(records)}/{len(rows)} checked')
        time.sleep(delay)
    log(f'Contract liabilities completed: {len(records)}/{len(rows)} checked; '+str(sum(x.get('status')=='disclosed' for x in records.values()))+' disclosed')
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--max-requests',type=int,default=80);p.add_argument('--delay',type=float,default=5)
    a=p.parse_args();main(a.max_requests,max(.5,a.delay))
