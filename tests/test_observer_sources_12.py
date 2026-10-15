"""Offline tests: no guessed publication timestamps or fake source successes."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.repair_observer_sources_12 import (
    official_url, safe_link, parse_date, entries_from_html, execute)
from scripts.merge_observer_sources_12 import merge
from datetime import date
import json
import pytest
import requests

S={'id':'CNR','name':'CNR','type':'publications','domain':'cnr.it','keywords':['ricerca','studio','rapporto']}


def test_url_allowlist_and_redirect():
    assert official_url('https://www.cnr.it/it/comunicati-stampa','cnr.it')
    assert not official_url('http://cnr.it/it/news','cnr.it')
    assert not official_url('https://cnr.it.evil.example/t','cnr.it')
    assert safe_link('https://www.cnr.it/it/comunicati-stampa','/it/ricerca-2026','cnr.it')=='https://www.cnr.it/it/ricerca-2026'
    assert safe_link('https://cnr.it/','javascript:alert(1)','cnr.it') is None
    assert safe_link('https://cnr.it/','https://other.test/report.pdf','cnr.it') is None


def test_dated_link():
    html='''<article><h3>Studio CNR sulle innovazioni industriali</h3>
    <time datetime="2026-10-15">15 ottobre 2026</time>
    <a href="/it/ricerca-industriale-2026">Studio CNR sulle innovazioni industriali</a></article>'''
    rows=entries_from_html(html,'https://www.cnr.it/it/comunicati-stampa',S,today=date(2026,10,15))
    assert len(rows)==1
    assert rows[0]['published_at']=='2026-10-15'
    assert rows[0]['public_source']['url']=='https://www.cnr.it/it/ricerca-industriale-2026'
    assert not rows[0]['key_figures']
    assert rows[0]['pulse_title']==''


def test_no_date_no_invention():
    html='<article><a href="/it/studio-statistico-2026">Studio CNR sui dati nazionali</a></article>'
    assert entries_from_html(html,'https://www.cnr.it/it/comunicati-stampa',S,today=date(2026,10,15))==[]
    assert parse_date('RAPPORTO 2026',today=date(2026,10,15)) is None
    assert parse_date('31/02/2026',today=date(2026,10,15)) is None
    assert parse_date('30 dicembre 2026',today=date(2026,10,15)) is None
    assert parse_date('15 ottobre 2026',today=date(2026,10,15))=='2026-10-15'


def test_no_mixing_dates_across_cards():
    html='''<article><time datetime="2026-10-13"></time><a href="/it/ricerca-a">Ricerca A CNR 2026</a></article>
    <article><a href="/it/ricerca-b">Ricerca B CNR 2026</a></article>'''
    rows=entries_from_html(html,'https://www.cnr.it/it/comunicati-stampa',S,today=date(2026,10,15))
    assert [r['headline'] for r in rows]==['Ricerca A CNR 2026']


def test_merge_keeps_archive():
    old={'generated_at':'2026-10-11','articles':[{'id':str(i)} for i in range(1000)]}
    row={'id':'PULSE-OBS12-ABC','published_at':'2026-10-14','headline':'Rapporto Ufficiale',
         'observer':'CNR','public_source':{'url':'https://www.cnr.it/it/ricerca','role':'primary_institutional_publication'}}
    new=merge(old,{'origin':'12_pending_official_sources','articles':[row,row]})
    assert len(new['articles'])==1001 and len(old['articles'])==1000
    assert new['observer_12_additions']==1
    assert new['generated_at']=='2026-10-11'
    with pytest.raises(ValueError): merge({'articles':[{}]}, {'origin':'12_pending_official_sources','articles':[row]})


def test_run_mocked_http(tmp_path):
    class Fake:
        status_code=200;url='https://www.cnr.it/it/comunicati-stampa';headers={'Content-Type':'text/html'}
        content=b'<article><time datetime="2026-01-05">5 gennaio 2026</time><a href="/it/studio-ricerca">Studio ricerca nazionale 2026</a></article>'
        text=content.decode()
        def raise_for_status(self):pass
    class Session:
        def __init__(self):self.headers={}
        def get(self,url,**kw):
            if 'cnr.it' in url:return Fake()
            raise requests.ConnectionError('offline fixture')
    # Make all 12 point to a controlled fixture domain, distinct IDs; the
    # first returns a valid fixture, others stay unavailable.
    rows=json.loads((Path(__file__).resolve().parents[1]/'data/observer_sources_12_registry.json').read_text())
    summary=execute(registry=Path(__file__).resolve().parents[1]/'data/observer_sources_12_registry.json',
                    status_file=tmp_path/'status.json',out_file=tmp_path/'article.json',session=Session())
    assert summary['total_sources']==12
    assert summary['dated_publications'] >= 1
    assert (tmp_path/'status.json').exists()

def test_timezone_windows_missing_tzdata_fails_closed(monkeypatch):
    """Regression: no ZoneInfoNotFoundError on Windows without IANA database."""
    import scripts.repair_observer_sources_12 as mod
    from zoneinfo import ZoneInfoNotFoundError
    def without_tzdata(_):
        raise ZoneInfoNotFoundError("Europe/Rome")
    monkeypatch.setattr(mod, 'ZoneInfo', without_tzdata)
    assert mod.parse_date('5 gennaio 2026') == '2026-01-05'
    assert mod.parse_date('31/02/2026') is None
