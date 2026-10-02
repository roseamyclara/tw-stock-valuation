"""Backfill matching year-to-date net profit from official market-wide reports."""
import datetime as dt
from html.parser import HTMLParser
import re
import time
import requests
from util import DATA_DIR, read_json, write_json, log, num
URL='https://mopsov.twse.com.tw/mops/web/ajax_t163sb04'
MARKETS={'listed':'sii','otc':'otc','esb':'rotc'}
class Rows(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.row=[];self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        if tag in ('td','th'):self.cell=[]
    def handle_data(self,text):
        if self.cell is not None:self.cell.append(text)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(''.join(self.cell).strip());self.cell=None
        if tag=='tr' and self.row:self.rows.append(self.row);self.row=[]
def parse(html):
    if any(x in html for x in ('因為安全性考量','Access Denied','請稍後再試')):raise ValueError('Official source requested a pause')
    if '新台幣仟元' not in html and '新臺幣仟元' not in html:raise ValueError('Missing expected unit')
    p=Rows();p.feed(html);headers=[];result={}
    for row in p.rows:
        if row and re.sub(r'\s','',row[0])=='公司代號':headers=[re.sub(r'\s','',h) for h in row];continue
        if not headers or not row or not re.fullmatch(r'\d{4}',row[0]):continue
        if len(row)!=len(headers):raise ValueError('Unexpected table width')
        values=dict(zip(headers,row));rec={}
        for h,v in values.items():
            if h.startswith('淨利') and '歸屬於母公司業主' in h:rec['parent']=num(v)
            if re.fullmatch(r'本期(?:稅後)?淨利（淨損）',h):rec['total']=num(v)
        result[row[0]]=rec
    if not result:raise ValueError('No financial rows')
    return result

def compare(cur,prev):
    for basis in ('parent','total'):
        a=cur.get(basis);b=prev.get(basis)
        if a is not None and b is not None:break
    else:return {'status':'missing','yoy':None}
    status='normal';yoy=None
    if b==0:status='去年同期為零'
    elif b<0:
        status='轉盈' if a>0 else '損益兩平' if a==0 else '虧損縮小' if a>b else '虧損擴大' if a<b else '虧損持平'
    elif a<0:status='轉虧'
    else:yoy=round((a/b-1)*100,2)
    return {'basis':basis,'current':a,'previous':b,'status':status,'yoy':yoy}

def main():
    rows=read_json(DATA_DIR/'latest.json',[]) or []
    periods=[(r['fin']['y'],r['fin']['q']) for r in rows if r.get('fin')]
    if not periods:return 0
    target=max(set(periods),key=periods.count)
    cache=read_json(DATA_DIR/'profit_history.json',{}) or {}
    output=read_json(DATA_DIR/'profit_growth.json',{'stocks':{}}) or {'stocks':{}}
    now=dt.datetime.now(dt.timezone.utc);session=requests.Session()
    session.headers['User-Agent']='Mozilla/5.0'
    for market,kind in MARKETS.items():
        selected=[r for r in rows if r['m']==market]
        targets={(r.get('fin',{}).get('y',target[0]),r.get('fin',{}).get('q',target[1])) for r in selected}
        for year,quarter in sorted(targets):
            try:
                reports=[]
                for y in (year,year-1):
                    key=f'{kind}:{y}Q{quarter}';entry=cache.get(key)
                    if not entry or (now-dt.datetime.fromisoformat(entry['fetchedAt'])).total_seconds()>86400:
                        time.sleep(3)
                        resp=session.post(URL,data={'encodeURIComponent':'1','step':'1','firstin':'1','off':'1','isQuery':'Y','TYPEK':kind,'year':str(y-1911),'season':f'{quarter:02d}'},timeout=40)
                        resp.raise_for_status();resp.encoding='utf-8';records=parse(resp.text)
                        entry={'fetchedAt':now.isoformat(),'records':records};cache[key]=entry
                        write_json(DATA_DIR/'profit_history.json',cache)
                    reports.append(entry['records'])
                for row in selected:
                    if (row.get('fin',{}).get('y',target[0]),row.get('fin',{}).get('q',target[1]))!=(year,quarter):continue
                    code=row['c'];record=compare(reports[0].get(code,{}),reports[1].get(code,{}))
                    record.update(year=year,quarter=quarter,source='https://mopsov.twse.com.tw/mops/web/t163sb04',market=kind)
                    output['stocks'][code]=record
                log(f'Profit growth {market} {year}Q{quarter}: {len(reports[0])}/{len(reports[1])} financial rows')
            except (requests.RequestException,ValueError) as e:
                log(f'Profit growth deferred: {e}');break
    output.update(updatedAt=now.isoformat(),unit='TWD thousands',periodType='YTD')
    write_json(DATA_DIR/'profit_growth.json',output)
    return 0
if __name__=='__main__':main()
