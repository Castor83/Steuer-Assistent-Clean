"""Speichert Laufzeit und vollständige Trefferranglisten für einen Vergleich."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import rag_assistent as r


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ausgabe', required=True)
    parser.add_argument('--vergleich')
    args = parser.parse_args()
    cases = json.loads((ROOT/'tests/praxischarge_50.json').read_text(encoding='utf-8'))
    cases += json.loads((ROOT/'tests/steuerllm_testfragen_50.json').read_text(encoding='utf-8'))
    results = []
    for repeat in range(2):
        start = time.perf_counter()
        rankings = []
        for case in cases:
            hits = r.suche_quellenkarten_lexikalisch(case['frage'],limit=24,steuerjahr=2025)
            rankings.append({'id':case['id'], 'hits':[(q.payload.get('datei'),q.score,q.rohscore) for q in hits]})
        results.append({'seconds':time.perf_counter()-start,'rankings':rankings})
        print(f"Durchlauf {repeat+1}: {results[-1]['seconds']:.3f} Sekunden",flush=True)
    path = ROOT/'tests/ergebnisse'/args.ausgabe
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if args.vergleich:
        previous = json.loads((ROOT/'tests/ergebnisse'/args.vergleich).read_text(encoding='utf-8'))
        actual = json.loads(path.read_text(encoding='utf-8'))
        assert all(a['rankings']==b['rankings'] for a,b in zip(previous,actual))
        print('Alle Treffer, Reihenfolgen und Scores identisch.',flush=True)


if __name__ == '__main__':
    main()
