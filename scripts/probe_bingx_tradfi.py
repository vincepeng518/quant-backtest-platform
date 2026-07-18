import urllib.request, json, concurrent.futures

SYMS = [
 "NCFXEUR2USD-USDT","NCFXGBP2USD-USDT","NCFXUSD2JPY-USDT","NCFXAUD2USD-USDT",
 "NCFXUSD2CAD-USDT","NCFXUSD2CHF-USDT",
 "NCFXGBP2JPY-USDT","NCFXEUR2JPY-USDT","NCFXNZD2USD-USDT","NCFXEUR2CAD-USDT",
 "NCFXEUR2GBP-USDT","NCFXEUR2CHF-USDT","NCFXGBP2CHF-USDT","NCFXAUD2JPY-USDT",
 "NCFXUSDSGD-USDT","NCFXEURSGD-USDT","NCFXGBPSGD-USDT","NCFXUSDBRL-USDT",
 "NCCOGOLD2USD-USDT","NCCOSILVER2USD-USDT","NCCOPALLADIUM2USD-USDT","NCCOPLATINUM2USD-USDT",
 "NCCOCOPPER2USD-USDT","NCCONICKEL2USD-USDT","NCCOZINC2USD-USDT","NCCOALUMINUM2USD-USDT","NCCOLEAD2USD-USDT",
 "NCCOOILBRENT2USD-USDT","NCCOOILWTI2USD-USDT","NCCONATURALGAS2USD-USDT","NCCOGASOLINE2USD-USDT","NCCOHEATINGOIL2USD-USDT",
 "NCSINASDAQ1002USD-USDT","NCSISP5002USD-USDT","NCSIDOWJONES2USD-USDT","NCSIRUSSELL20002USD-USDT",
 "NCSINIKKEI2252USD-USDT",
 "NCSKAAPL2USD-USDT","NCSKMSFT2USD-USDT","NCSKGOOGL2USD-USDT","NCSKAMZN2USD-USDT","NCSKTSLA2USD-USDT",
 "NCSKMETA2USD-USDT","NCSKNVDA2USD-USDT","NCSKARM2USD-USDT","NCSKCOIN2USD-USDT","NCSKMSTR2USD-USDT",
 "NCSKHOOD2USD-USDT","NCSKPLTR2USD-USDT","NCSKRDDT2USD-USDT","NCSKINTC2USD-USDT","NCSKCSCO2USD-USDT",
 "NCSKORCL2USD-USDT","NCSKIBM2USD-USDT","NCSKMCD2USD-USDT","NCSKGE2USD-USDT","NCSKGME2USD-USDT",
]

def probe(sym):
    url = "https://open-api.bingx.com/openApi/swap/v3/quote/klines?symbol=%s&interval=1d&limit=1" % sym
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        if d.get("code") == 0 and d.get("data"):
            return (sym, "OK")
        return (sym, "EMPTY code=%s msg=%s" % (d.get("code"), d.get("msg")))
    except Exception as e:
        return (sym, "ERR %s" % e)

ok = []; bad = []
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    for sym, res in ex.map(probe, SYMS):
        if res == "OK":
            ok.append(sym)
        else:
            bad.append((sym, res))

print("=== OK (%d) ===" % len(ok))
for s in ok:
    print(s)
print("\n=== BAD (%d) ===" % len(bad))
for s, r in bad:
    print(s, "->", r)
