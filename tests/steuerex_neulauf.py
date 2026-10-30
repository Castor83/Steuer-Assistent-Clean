"""Unveränderte SteuerEx-Fragen über die laufende Web-App; keine Fachpunktzahl."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import time

import strenger_katalogtest as web

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ausgabe', default='steuerex_neulauf_20260905.json')
    parser.add_argument('--nutzer', default='Alex Beispiel')
    args = parser.parse_args()
    source = ROOT/'tests/steuerex_haertetest_115.json'
    cases = json.loads(source.read_text(encoding='utf-8'))
    assert len(cases) == 115 and len({c['id'] for c in cases}) == 115
    path = ROOT/'tests/ergebnisse'/args.ausgabe
    if path.exists():
        raise FileExistsError(f'Vorhandenen Lauf nicht überschreiben: {path}')
    web.nutzer_waehlen(web.ENDPUNKT, args.nutzer)
    report = {'erstellt':datetime.now().astimezone().isoformat(),
              'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'katalog_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
              'modus':'Web-App, Originalfrage, leerer Gesprächsverlauf, keine UI-Jahresvorgabe',
              'einschraenkung':'Bestehendes Nutzerprofil der Web-App. Prüfungssemester ist kein automatisch gesetztes Steuerjahr. Keine Goldantworten, keine offizielle Punktzahl.',
              'ergebnisse':[]}
    start = time.perf_counter()
    for case in cases:
        years = [int(y) for y in re.findall(r'(?<!\d)(20\d{2})(?!\d)',case['frage'])]
        result = {'id':case['id'],'kategorie':case['kategorie'],'frage':case['frage'],
                  'steuerex_semester':case['steuerex_semester'],'max_punkte':case['max_punkte'],
                  'jahre_im_text':sorted(set(years)),
                  'jahr_nach_aktueller_appheuristik':years[-1] if years else None,
                  'zeitbezug_pruefen':len(set(years)) != 1,
                  'fachlich_bewertet':False}
        before = time.perf_counter()
        try:
            data = web.frage_stellen(case['frage'],steuerjahr='')
            answer = data.get('antwort','').strip()
            sources = data.get('quellen',[])
            status = ('ANTWORT_MIT_QUELLEN' if sources else
                      'RUECKFRAGE' if '?' in answer else 'ABLEHNUNG_OHNE_QUELLEN') if answer else 'LEERE_ANTWORT'
            result.update(antwort=answer,quellen=sources,status=status)
        except Exception as exc:
            result.update(status='TECHNISCHER_FEHLER',fehler=str(exc),antwort='',quellen=[])
        result['dauer_sekunden'] = round(time.perf_counter()-before,3)
        report['ergebnisse'].append(result)
        report['abgeschlossen'] = len(report['ergebnisse'])
        report['dauer_sekunden'] = round(time.perf_counter()-start,3)
        report['status'] = dict(Counter(r['status'] for r in report['ergebnisse']))
        report['median_sekunden'] = statistics.median(r['dauer_sekunden'] for r in report['ergebnisse'])
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(f"{report['abgeschlossen']}/115 #{case['id']} {result['status']} {result['dauer_sekunden']}s",flush=True)
    print(json.dumps({k:v for k,v in report.items() if k!='ergebnisse'},ensure_ascii=True),flush=True)


if __name__ == '__main__':
    main()
