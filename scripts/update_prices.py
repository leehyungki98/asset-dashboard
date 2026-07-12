#!/usr/bin/env python3
"""
tickers.json 의 티커에 대해
  data/prices.json    현재가 / 등락률 / 배당 / 환율
  data/history.json   일별 종가 + 일별 환율 (400일)
을 생성한다.  전부 '시장 데이터'일 뿐, 보유수량·금액은 여기 없다.

보유 데이터는 노션 embed URL 의 #c= 해시에만 있고,
브라우저는 해시를 서버로 보내지 않으므로 GitHub 은 그것을 볼 수 없다.
"""
import json
import pathlib
from datetime import datetime, timezone, timedelta

import yfinance as yf

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
KST = timezone(timedelta(hours=9))
FX = "KRW=X"


def quote(t: str) -> dict:
    i = yf.Ticker(t).info
    price = i.get("regularMarketPrice")
    if price is None:
        raise RuntimeError(f"{t}: regularMarketPrice 없음 — 티커 확인 필요")
    prev = i.get("regularMarketPreviousClose") or price
    return {
        "price": price,
        "prevClose": prev,
        "changePct": (price / prev - 1) * 100 if prev else 0.0,
        "currency": i.get("currency", "USD"),
    }


def dividends(t: str, price: float) -> dict:
    try:
        d = yf.Ticker(t).dividends
        if d is None or len(d) == 0:
            raise ValueError
        last = d[d.index >= d.index.max() - timedelta(days=365)]
        annual = float(last.sum())
        return {
            "dividendMonths": sorted({int(x.month) for x in last.index}),
            "annualDividend": annual,
            "dividendYield": annual / price * 100 if price else 0.0,
        }
    except Exception:
        return {"dividendMonths": [], "annualDividend": 0.0, "dividendYield": 0.0}


def main() -> None:
    cfg = json.loads((ROOT / "tickers.json").read_text(encoding="utf-8"))
    tickers, days = cfg["tickers"], cfg.get("historyDays", 400)

    fx = quote(FX)["price"]
    quotes = {}
    for t in tickers:
        q = quote(t)
        q.update(dividends(t, q["price"]))
        quotes[t] = q

    now = datetime.now(KST)
    (DATA / "prices.json").write_text(json.dumps(
        {"updated": now.isoformat(timespec="minutes"), "fx": fx, "quotes": quotes},
        ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 일별 종가 + 일별 환율 ----
    period = f"{days}d"
    closes = {}
    for t in tickers + [FX]:
        h = yf.Ticker(t).history(period=period, auto_adjust=False)
        closes[t] = {d.strftime("%Y-%m-%d"): round(float(c), 4)
                     for d, c in h["Close"].items() if c == c}   # NaN 제거

    dates = sorted(set().union(*[set(v) for v in closes.values()]))

    def ffill(series: dict) -> list:
        out, last = [], None
        for d in dates:
            last = series.get(d, last)
            out.append(last)
        return out

    fx_series = ffill(closes[FX])
    series = {t: ffill(closes[t]) for t in tickers}

    # 앞부분에 값이 없는(None) 날짜는 통째로 버린다
    start = max((next((i for i, v in enumerate(s) if v is not None), 0)
                 for s in [fx_series, *series.values()]), default=0)

    (DATA / "history.json").write_text(json.dumps({
        "dates": dates[start:],
        "fx": fx_series[start:],
        "close": {t: s[start:] for t, s in series.items()},
    }, ensure_ascii=False), encoding="utf-8")

    print(f"현재 환율 {fx:,.2f} / 종목 {len(tickers)}개 / 일별 {len(dates[start:])}일치")
    for t, q in quotes.items():
        print(f"  {t:<12} {q['price']:>10,.2f} {q['currency']}  {q['changePct']:+.2f}%")


if __name__ == "__main__":
    main()
