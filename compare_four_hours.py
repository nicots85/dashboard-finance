#!/usr/bin/env python3
"""Comparación antes/después a cierres de 4h: consulta datos, no modifica series ni fotos."""
import argparse
from pathlib import Path
import sqlite3
import numpy as np
import pandas as pd
import yaml
from src.data.backup import ROOT
from src.data.db_manager import DEFAULT_DB_PATH
from src.calc.regime import calculate_atr, calculate_adx, get_latest_market_regime
from src.data.four_hour import policy, market_results, prepare_stored


def load(conn, symbol):
    df = pd.read_sql_query("SELECT * FROM candles WHERE symbol=? AND timeframe='4h' ORDER BY timestamp", conn, params=(symbol,))
    df.timestamp = pd.to_datetime(df.timestamp, utc=True, format="mixed")
    return df


def history(df, cfg):
    if df.empty:
        return pd.DataFrame(columns=["end", "direction", "regime"])
    ema = df.close.ewm(span=cfg.get("ema_period",50),adjust=False).mean()
    slope = ema.diff()
    adx = calculate_adx(df,cfg.get("adx_period",14))
    atr = calculate_atr(df,cfg.get("atr_period",14))
    z = (df.close-ema)/atr.replace(0,np.nan)
    threshold=cfg.get("adx_threshold_lateral",20)
    direction=pd.Series(np.select([(adx>=threshold)&(slope>0),(adx>=threshold)&(slope<=0),
        (adx<threshold)&(z>cfg.get("weak_trend_z",2))&(slope>0),(adx<threshold)&(z<-cfg.get("weak_trend_z",2))&(slope<0)],
        ["alcista","bajista","alcista (débil)","bajista (débil)"],default="lateral"),index=df.index)
    pct=atr.rolling(cfg.get("atr_percentile_window",250),min_periods=250).rank(method="max",pct=True)*100
    vol=pd.Series(np.select([pct<cfg.get("volatility_low_pct",25),pct>cfg.get("volatility_high_pct",75)],
        ["baja vol","alta vol"],default="normal vol"),index=df.index)
    result=pd.DataFrame({"end":df.bar_end,"direction":direction,"regime":direction+" / "+vol})
    result["end"] = pd.to_datetime(result.end, utc=True).dt.as_unit("ns")
    return result[adx.notna() & pct.notna()].sort_values("end").drop_duplicates("end")


def comparison(before_path, current_path):
    cfg=yaml.safe_load((ROOT/"config/calc.yaml").read_text(encoding="utf-8"))
    assets=yaml.safe_load((ROOT/"config/assets.yaml").read_text(encoding="utf-8"))
    old=sqlite3.connect(Path(before_path).resolve().as_uri()+"?mode=ro",uri=True)
    new=sqlite3.connect(Path(current_path).resolve().as_uri()+"?mode=ro",uri=True)
    rows=[]
    try:
        for sec,data in assets.items():
            if sec=="referencias":continue
            for symbol in data["activos"]:
                a,b=load(old,symbol),load(new,symbol)
                # La hora de disponibilidad de los precios, no comparar una vela futura.
                a=prepare_stored(a,symbol)
                b=prepare_stored(b,symbol)
                a,b=a[a.closed],b[b.closed]
                before=get_latest_market_regime(a,cfg["regime"])["direction"]
                after=market_results(b,cfg)[0]["direction"]
                ha,hb=history(a,cfg["regime"]),history(b,cfg["regime"])
                last_common=min(ha.end.max(),hb.end.max()) if len(ha) and len(hb) else None
                sample=pd.merge_asof(hb[hb.end<=last_common],ha,on="end",direction="backward",suffixes=("_new","_old")).dropna() if last_common else pd.DataFrame()
                pct_dir=float((sample.direction_new!=sample.direction_old).mean()*100) if len(sample) else None
                pct_reg=float((sample.regime_new!=sample.regime_old).mean()*100) if len(sample) else None
                rows.append({"sección":sec,"símbolo":symbol,"antes_velas":len(a),"después_velas":len(b),"antes_dirección":before,
                    "después_dirección":after,"puntos_comparables":len(sample),"dirección_cambia_pct":pct_dir,"régimen_cambia_pct":pct_reg,
                    "inicio_comparación":str(sample.end.min()) if len(sample) else None,"fin_comparación":str(last_common),
                    "último_dato_antes":str(a.timestamp.max()),"último_dato_después":str(b.timestamp.max()),"modificado":bool(policy(symbol))})
    finally:
        old.close();new.close()
    return rows


def main():
    p=argparse.ArgumentParser(description="Comparar la base de respaldo anterior con la serie 4h activa; no genera fotos.")
    p.add_argument("--before",required=True,help="Base restaurada del respaldo anterior")
    p.add_argument("--db",default=DEFAULT_DB_PATH)
    args=p.parse_args()
    print(pd.DataFrame(comparison(args.before,args.db)).to_string(index=False))


if __name__=="__main__":main()
