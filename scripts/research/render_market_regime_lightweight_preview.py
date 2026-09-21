import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    payload = json.loads((ROOT / 'runtime/reports/market_regime/lightweight.json').read_text())
    template = Path(__file__).with_name('market_regime_lightweight_preview.html').read_text()
    output = ROOT / 'runtime/research/market_regime/lightweight-preview.html'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace('__DATA__', json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c')))
    print(output)


if __name__ == '__main__':
    main()
