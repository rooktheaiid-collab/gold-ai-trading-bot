import requests, io, zipfile, pandas as pd, os
base="https://data.binance.vision/data/futures/um/daily/klines/XAUUSDT"
days=["2026-06-01","2026-06-02","2026-06-03"]
for tf in ["1h","15m","1d"]:
    path=f"data/XAUUSDT_{tf}.csv"
    old=pd.read_csv(path)
    rows=[]
    for d in days:
        url=f"{base}/{tf}/XAUUSDT-{tf}-{d}.zip"
        r=requests.get(url,timeout=15)
        if r.status_code!=200: 
            print(tf,d,"skip",r.status_code); continue
        z=zipfile.ZipFile(io.BytesIO(r.content))
        name=z.namelist()[0]
        df=pd.read_csv(z.open(name), header=None)
        # cols: open_time,open,high,low,close,volume,...
        df=df.iloc[:,:6]
        df.columns=["open_time","open","high","low","close","volume"]
        # some archives have a header row of text; coerce
        df=df[pd.to_numeric(df["open_time"],errors="coerce").notna()]
        df["open_time"]=df["open_time"].astype("int64")
        rows.append(df)
    if not rows: 
        print(tf,"no new rows"); continue
    new=pd.concat(rows,ignore_index=True)
    comb=pd.concat([old,new],ignore_index=True).drop_duplicates(subset=["open_time"]).sort_values("open_time")
    comb.to_csv(path,index=False)
    import datetime
    last=datetime.datetime.utcfromtimestamp(int(comb["open_time"].iloc[-1])/1000)
    print(f"{tf}: {len(old)} -> {len(comb)} rows | last={last}")
