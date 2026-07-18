import urllib.request, json, concurrent.futures

# 你提供的 BingX OpenAPI 權威符號表
SYMS = [
 "NCFXEUR2USD-USDT","NCFXUSD2JPY-USDT","NCFXAUD2USD-USDT","NCFXUSD2CAD-USDT",
 "NCFXUSD2CHF-USDT","NCFXGBP2USD-USDT","NCFXGBP2JPY-USDT","NCFXEUR2JPY-USDT",
 "NCFXNZD2USD-USDT","NCFXEUR2CAD-USDT","NCFXEUR2GBP-USDT","NCFXEUR2CHF-USDT",
 "NCFXGBP2CHF-USDT","NCFXAUD2JPY-USDT","NCFXUSDSGD2USD-USDT","NCFXEURSGD2USD-USDT",
 "NCFXGBPSGD2USD-USDT","NCFXUSDBRL2USD-USDT",
 "NCCOGOLD2USD-USDT","NCCOSILVER2USD-USDT","NCCOOILBRENT2USD-USDT","NCCOOILWTI2USD-USDT",
 "NCCONATURALGAS2USD-USDT","NCCOGASOLINE2USD-USDT","NCCOCOFFEE2USD-USDT","NCCOCOPPER2USD-USDT",
 "NCCOPALLADIUM2USD-USDT","NCCONICKEL2USD-USDT","NCCOZINC2USD-USDT","NCCOHEATINGOIL2USD-USDT",
 "NCCOALUMINIUM2USD-USDT","NCCOLEAD2USD-USDT","NCCOCOCOA2USD-USDT","NCCOSOYBEANS2USD-USDT",
 "NCSINASDAQ1002USD-USDT","NCSISP5002USD-USDT","NCSIDOWJONES2USD-USDT","NCSIRUSSELL20002USD-USDT",
 "NCSINIKKEI2252USD-USDT","NCSKMSFT2USD-USDT","NCSKGOOGL2USD-USDT","NCSKAMZN2USD-USDT",
 "NCSKTSLA2USD-USDT","NCSKARM2USD-USDT","NCSKINTC2USD-USDT","NCSKAAPL2USD-USDT",
 "NCSKCOIN2USD-USDT","NCSKNVDA2USD-USDT","NCSKMETA2USD-USDT","NCSKMSTR2USD-USDT",
 "NCSKHOOD2USD-USDT","NCSKPLTR2USD-USDT","NCSKCSCO2USD-USDT","NCSKACN2USD-USDT",
 "NCSKASML2USD-USDT","NCSKORCL2USD-USDT","NCSKRDDT2USD-USDT","NCSKMRVL2USD-USDT",
 "NCSKAPP2USD-USDT","NCSKIBM2USD-USDT","NCSKGME2USD-USDT","NCSKGE2USD-USDT",
 "NCSKCRCL2USD-USDT","NCSKMCD2USD-USDT",
]

def probe(sym):
    url = "https://open-api.bingx.com/openApi/swap/v3/quote/klines?symbol=%s&interval=1d&limit=1" % sym
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        if d.get("code") == 0 and d.get("data"):
            return (sym, "active")
        msg = (d.get("msg") or "").lower()
        if "offline" in msg: return (sym, "offline")
        if "pause" in msg: return (sym, "paused")
        return (sym, "not_exist")
    except Exception as e:
        return (sym, "not_exist")

ok=[]; bad=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    for sym, res in ex.map(probe, SYMS):
        if res=="active": ok.append(sym)
        else: bad.append((sym,res))

print("=== ACTIVE (%d) ===" % len(ok))
for s in ok: print(s)
print("\n=== NOT ACTIVE (%d) ===" % len(bad))
for s,r in bad: print(s, "->", r)
