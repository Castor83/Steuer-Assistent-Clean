"""Erstellt eine Auswertung des Neulaufs ohne erfundene Fachpunktzahl."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT/'tests/ergebnisse/steuerex_neulauf_20260905.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    rows = report['ergebnisse']
    assert len(rows)==115 and {r['id'] for r in rows}==set(range(1001,1116))
    cases = json.loads((ROOT/'tests/steuerex_haertetest_115.json').read_text(encoding='utf-8'))
    assert {r['id']:r['frage'] for r in rows}=={c['id']:c['frage'] for c in cases}
    times = sorted(r['dauer_sekunden'] for r in rows)
    answer_groups = {}
    for r in rows:
        if r['status'] == 'ANTWORT_MIT_QUELLEN':
            answer_groups.setdefault(r['antwort'], []).append(r['id'])
    duplicates = [ids for ids in answer_groups.values() if len(ids) > 1]
    refusals_with_sources = [r['id'] for r in rows if r['quellen'] and
                            ('nicht sicher beantworten' in r['antwort'].lower() or
                             'nicht sicher ermitteln' in r['antwort'].lower())]
    warnings = []
    categories = {}
    for r in rows:
        categories.setdefault(r['kategorie'], []).append(r)
    for r in rows:
        hints=[]
        if r['zeitbezug_pruefen']:hints.append('Zeitbezug mehrdeutig/ohne Jahresangabe')
        years=r['jahre_im_text']
        if years and any(str(q.get('jahr','')).isdigit() and int(q['jahr'])>max(years) for q in r['quellen']):
            hints.append('Quelle mit späterer Jahreskennzeichnung: historische Gültigkeit prüfen')
        if r['status']!='ANTWORT_MIT_QUELLEN':hints.append(r['status'])
        if r['dauer_sekunden']>10:hints.append('Antwortzeit über 10 Sekunden')
        if hints:warnings.append({'id':r['id'],'hinweise':hints})
    summary={'anzahl':len(rows),'originalfragen_identisch':True,'status':dict(Counter(r['status'] for r in rows)),
             'median_sekunden':statistics.median(times),'mittel_sekunden':statistics.mean(times),
             'p95_nearest_rank_sekunden':times[109],'max_sekunden':max(times),
             'dauer_sekunden':report['dauer_sekunden'],
             'ablehnungsformulierung_trotz_quellen_ids':refusals_with_sources,
             'kategorien':{name:{'anzahl':len(items),
                                'status':dict(Counter(x['status'] for x in items)),
                                'median_sekunden':statistics.median(x['dauer_sekunden'] for x in items)}
                           for name,items in categories.items()},
             'identische_belegte_antworten_fallgruppen':duplicates,'pruefhinweise':warnings}
    (path.parent/'steuerex_neulauf_zusammenfassung.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# SteuerEx-Neulauf vom 05.09.2026','',
           '**Keine offizielle Benchmarkpunktzahl und keine fachliche Bestehensquote.**','',
           f"Getesteter App-Commit: `{report['commit']}`. Start: {report['erstellt']}. "
           f"SHA256 der Ergebnisdatei: `{hashlib.sha256(path.read_bytes()).hexdigest()}`.",'',
           f"Alle {len(rows)} Originalfragen wurden unverändert durch die laufende Web-App geschickt. "
           'Die UI-Jahresauswahl blieb leer; historische Daten stehen unverändert im Fragetext. '
           'Bei mehreren Jahren wählt die App derzeit das zuletzt genannte Jahr. Das ist kein verlässlicher fachlicher Zeitbezug. '
           'Das Prüfungssemester wurde nicht pauschal zum Steuerjahr gemacht.','',
           'Der Test nutzte das bestehende lokale Nutzerprofil mit leerem Gesprächsverlauf. '
           'Der Bestand wurde bereits früher für Fehlerkorrekturen verwendet; im Code sind sogar namentliche Fallpfade vorhanden. '
           'Dies ist daher ein Regressionstest des Gesamtsystems, kein unabhängiger Modellbenchmark.','',
           'Die HTTP-Anfrage hat ein Zeitlimit von 180 Sekunden. Ein Timeout garantiert nicht, '
           'dass die serverseitige Berechnung bereits beendet wurde. Nachfolgende Antwortzeiten können '
           'deshalb durch noch laufende Berechnungen beeinflusst sein. Fehlgeschlagene Fälle werden '
           'als technische Fehler gezählt, nicht als fachliche Ablehnungen.','',
           '## Technische Ergebnisse','',
           'Die Statusnamen stammen aus einer rein strukturellen Auswertung. '
           'ANTWORT_MIT_QUELLEN bedeutet nur: Antwort und Quellenliste vorhanden. '
           'RUECKFRAGE wird anhand eines Fragezeichens erkannt; ABLEHNUNG_OHNE_QUELLEN '
           'bezeichnet eine Antwort ohne Quellen und ohne Fragezeichen. Eine inhaltliche Bewertung ist damit nicht verbunden.','']
    for k,v in summary['status'].items():lines.append(f'- {k}: {v}')
    lines += ['', f'Zusätzlich enthalten {len(refusals_with_sources)} Antworten mit Quellen eine ausdrückliche '
              f'Unsicherheits-/Ablehnungsformulierung: {refusals_with_sources}. '
              'Die Erkennung verwendet nur die Formulierungen „nicht sicher beantworten“ und „nicht sicher ermitteln“; '
              'weitere inhaltliche Ablehnungen sind möglich.']
    lines += ['', '| Steuergebiet | Fälle | Mit Quellen (keine Fachwertung) | Median Sekunden |',
              '|---|---:|---:|---:|']
    for name, values in summary['kategorien'].items():
        lines.append(f"| {name} | {values['anzahl']} | {values['status'].get('ANTWORT_MIT_QUELLEN', 0)} | {values['median_sekunden']:.2f} |")
    lines += ['',f"Gesamtdauer: {report['dauer_sekunden']:.1f} s. Median: {summary['median_sekunden']:.2f} s. "
              f"95. Perzentil: {summary['p95_nearest_rank_sekunden']:.2f} s. Maximum: {summary['max_sekunden']:.2f} s.",'',
              'Der frühere Lauf vom 25.08. dauerte 681,4 Sekunden, verwendete aber eine feste Jahresvorgabe. '
              'Wegen unterschiedlicher Bedingungen ist daraus kein sauberer Beschleunigungsfaktor ableitbar.','',
              f'Fallgruppen mit exakt identischen Antworten trotz unterschiedlicher Fragen: {duplicates}. '
              'Dies ist ein Prüfhinweis, nicht automatisch ein Fehler.','',
              '## Prüfliste','', '| ID | Status | Sekunden | Frage |','|---|---|---:|---|']
    for r in rows:
        q=' '.join(r['frage'].split()).replace('|','/')
        lines.append(f"| {r['id']} | {r['status']} | {r['dauer_sekunden']:.2f} | {q[:130]}… |")
    lines += ['', 'Vollständige Antworten und Quellen: `tests/ergebnisse/steuerex_neulauf_20260905.json`. '
              'Zusätzliche Warnhinweise: `tests/ergebnisse/steuerex_neulauf_zusammenfassung.json`. '
              'Fachliche Stichprobe: `STEUEREX_FACHPROBE_20260905.md`.','']
    (ROOT/'STEUEREX_NEULAUF_20260905.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='pruefhinweise'},ensure_ascii=True))


if __name__=='__main__':main()
