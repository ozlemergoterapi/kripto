from datetime import date


def metrics(trades, max_drawdown=None):
    n = len(trades)
    wins = sum(t.net > 0 for t in trades)
    gross_win = sum(max(0, t.net) for t in trades)
    gross_loss = sum(max(0, -t.net) for t in trades)
    return {"trades": n, "win_rate": wins / n if n else None,
            "net_pnl": sum(t.net for t in trades),
            "profit_factor": gross_win / gross_loss if gross_loss else None,
            "profit_factor_note": "Zarar yok" if n and not gross_loss else None,
            "expectancy_r": sum(t.net / t.initial_risk for t in trades) / n if n else None,
            "max_drawdown": max_drawdown,
            "average_minutes": sum((t.closed_at - t.opened_at) / 60 for t in trades) / n if n else None,
            "tp1_rate": sum(t.tp1_hit for t in trades) / n if n else None,
            "tp2_rate": sum(t.tp2_hit for t in trades) / n if n else None,
            "sl_rate": sum(t.sl_hit for t in trades) / n if n else None,
            "by_side": {s: {"trades": len(ts := [t for t in trades if t.side == s]),
                               "net_pnl": sum(t.net for t in ts),
                               "win_rate": sum(t.net > 0 for t in ts) / len(ts) if ts else None}
                        for s in ("LONG", "SHORT")},
            "by_coin": {s: {"trades": len(ts := [t for t in trades if t.symbol == s]),
                               "net_pnl": sum(t.net for t in ts)} for s in sorted({t.symbol for t in trades})}}


def reports(book):
    daily = [{"day": day, **row, "net_pnl": row["end_equity"] - row["start_equity"]}
             for day, row in sorted(book.days.items(), reverse=True)]
    weekly = {}
    for row in reversed(daily):
        iso = date.fromisoformat(row["day"]).isocalendar()
        key = f"{iso.year}-W{iso.week:02}"
        w = weekly.setdefault(key, {"week": key, "net_pnl": 0.0, "costs": 0.0, "days": 0})
        for k in ("net_pnl", "costs"):
            w[k] += row[k]
        w["days"] += 1
    return {"daily": daily, "weekly": list(reversed(list(weekly.values())))}
