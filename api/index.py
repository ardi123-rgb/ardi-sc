from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
import random
import string
import json
import hmac
import hashlib
import codecs
import base64
import re
import urllib3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEX_KEY = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
AES_KEY = bytes([89,103,38,116,99,37,68,69,117,104,54,37,90,99,94,56])
AES_IV  = bytes([54,111,121,90,68,114,50,50,69,51,121,99,104,106,77,37])

REGION_LANG = {"ME":"ar","IND":"hi","ID":"id","VN":"vi","TH":"th","BD":"bn",
               "PK":"ur","TW":"zh","CIS":"ru","SAC":"es","BR":"pt"}

UA = [
 "GarenaMSDK/4.0.42(SM-A525F ;Android)",
 "GarenaMSDK/4.0.39(SM-A325M;Android 13;en;HK;)",
 "GarenaMSDK/4.0.38(Redmi Note 10;Android 12;en;ID;)",
]

# --- PROTOBUF & CRYPTO ---
def vi(n):
    if n < 0: return b""
    o = bytearray()
    while True:
        b = n & 0x7F; n >>= 7
        if n: b |= 0x80
        o.append(b)
        if not n: return bytes(o)

def pf(k, v):
    if isinstance(v, dict):
        n = b"".join(pf(a,b) for a,b in v.items())
        return vi((k<<3)|2) + vi(len(n)) + n
    if isinstance(v, int):
        return vi((k<<3)|0) + vi(v)
    if isinstance(v, (str, bytes)):
        raw = v.encode() if isinstance(v, str) else v
        return vi((k<<3)|2) + vi(len(raw)) + raw
    return b""

def proto(d): return b"".join(pf(k,v) for k,v in d.items())

def aes_hex(h):
    return AES.new(AES_KEY, AES.MODE_CBC, AES_IV).encrypt(pad(bytes.fromhex(h), 16))

def enc_api(h): return aes_hex(h).hex()

def rpass():
    return "LONGS" + "".join(random.choices(string.ascii_letters + string.digits, k=12))

# --- GARENA LOGIC ---
def generate_acc(region="ID"):
    ip = f"{random.randint(1,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
    ua = random.choice(UA)
    pw = rpass()

    # 1. Guest Register
    body = json.dumps({"app_id":100067,"client_type":2,"password":pw,"source":2}, separators=(",",":"))
    sig = hmac.new(HEX_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
    h1 = {
        "User-Agent":ua, "Connection":"Keep-Alive", "Accept":"application/json",
        "Accept-Encoding":"gzip", "Authorization":f"Signature {sig}",
        "Content-Type":"application/json; charset=utf-8",
        "Host":"100067.connect.garena.com", "X-Forwarded-For":ip, "X-Real-IP":ip
    }
    
    try:
        r1 = requests.post("https://100067.connect.garena.com/api/v2/oauth/guest:register", headers=h1, data=body, timeout=8, verify=False)
        if r1.status_code != 200: return None
        uid = (r1.json().get("data") or {}).get("uid")
        if not uid: return None
    except Exception: return None

    # 2. Grant
    h2 = {
        "Accept-Encoding":"gzip","Connection":"Keep-Alive",
        "Content-Type":"application/x-www-form-urlencoded",
        "Host":"100067.connect.garena.com","User-Agent":ua,
        "X-Forwarded-For":ip,"X-Real-IP":ip
    }
    b2 = {"uid":uid,"password":pw,"response_type":"token","client_type":"2","client_secret":HEX_KEY,"client_id":"100067"}
    
    try:
        r2 = requests.post("https://100067.connect.garena.com/oauth/guest/token/grant", headers=h2, data=b2, timeout=8, verify=False)
        if r2.status_code != 200: return None
        inner = r2.json().get("data", r2.json())
        at, oid = inner.get("access_token"), inner.get("open_id")
        if not at or not oid: return None
    except Exception: return None

    # 3. Major Register & Login
    ks = [0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30,
          0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,
          0x30,0x30,0x32,0x30]
    enc = "".join(chr(ord(oid[i]) ^ ks[i % len(ks)]) for i in range(len(oid)))
    field = codecs.decode("".join(c if 32 <= ord(c) <= 126 else f"\\u{ord(c):04x}" for c in enc), "unicode_escape").encode("latin1")
    
    name = "LONGS" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    lang = REGION_LANG.get(region.upper(), "en")
    
    h3 = {
         "User-Agent":"UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
         "Accept-Encoding":"deflate, gzip","X-GA-SV":"1789535859",
         "Authorization":"Bearer","X-GA":"v1 1","ReleaseVersion":"OB55",
         "Content-Type":"application/x-www-form-urlencoded",
         "X-Unity-Version":"2018.4.12f1","Host":"loginbp.ppmainecoonghj.com",
         "X-Forwarded-For":ip,"X-Real-IP":ip
    }
    payload = {1:name,2:at,3:oid,5:102000007,6:4,7:1,13:1,14:field,15:lang,16:1,17:1}
    
    try:
        requests.post("https://loginbp.ppmainecoonghj.com/MajorRegister", headers=h3, data=aes_hex(proto(payload).hex()), timeout=8, verify=False)
    except Exception: pass

    p1 = b'\x1a\x132025-08-30 05:19:21"\tfree fire(\x01:\x081.114.13B2Android OS 9 / API-28 (PI/rel.cjw.20220518.114133)J\x08HandheldR\nATM MobilsZ\x04WIFI`\xb6\nh\xee\x05r\x03300z\x1fARMv7 VFPv3 NEON VMH | 2400 | 2\x80\x01\xc9\x0f\x8a\x01\x0fAdreno (TM) 640\x92\x01\rOpenGL ES 3.2\x9a\x01+Google|dfa4ab4b-9dc4-454e-8065-e70c733fa53f\xa2\x01\x0e105.235.139.91\xaa\x01\x02'
    p2 = lang.encode("ascii")
    p3 = b'\xb2\x01 1d8ec0240ede109973f3321b9354b44d\xba\x01\x014\xc2\x01\x08Handheld\xca\x01\x10Asus ASUS_I005DA\xea\x01@afcfbf13334be42036e4f742c80b956344bed760ac91b3aff9b607a610ab4390\xf0\x01\x01\xca\x02\nATM Mobils\xd2\x02\x04WIFI\xca\x03 7428b253defc164018c604a1ebbfebdf\xe0\x03\xa8\x81\x02\xe8\x03\xf6\xe5\x01\xf0\x03\xaf\x13\xf8\x03\x84\x07\x80\x04\xe7\xf0\x01\x88\x04\xa8\x81\x02\x90\x04\xe7\xf0\x01\x98\x04\xa8\x81\x02\xc8\x04\x01\xd2\x04=/data/app/com.dts.freefireth-PdeDnOilCSFn37p1AH_FLg==/lib/arm\xe0\x04\x01\xea\x04_2087f61c19f57f2af4e7feff0b24d9d9|/data/app/com.dts.freefireth-PdeDnOilCSFn37p1AH_FLg==/base.apk\xf0\x04\x03\xf8\x04\x01\x8a\x05\x0232\x9a\x05\n2019118693\xb2\x05\tOpenGLES2\xb8\x05\xff\x7f\xc0\x05\x04\xe0\x05\xf3F\xea\x05\x07android\xf2\x05pKqsHT5ZLWrYljNb5Vqh//yFRlaPHSO9NWSQsVvOmdhEEn7W+VHNUK+Q+fduA3ptNrGB0Ll0LRz3WW0jOwesLj6aiU7sZ40p8BfUE/FI/jzSTwRe2\xf8\x05\xfb\xe4\x06\x88\x06\x01\x90\x06\x01\x9a\x06\x014\xa2\x06\x014\xb2\x06"GQ@O\x00\x0e^\x00D\x06UA\x0ePM\r\x13hZ\x07T\x06\x0cm\\V\x0ejYV;\x0bU5'
    
    d = p1 + p2 + p3
    d = d.replace(b'afcfbf13334be42036e4f742c80b956344bed760ac91b3aff9b607a610ab4390', at.encode())
    d = d.replace(b'1d8ec0240ede109973f3321b9354b44d', oid.encode())
    
    try:
        r3 = requests.post("https://loginbp.ppmainecoonghj.com/MajorLogin", headers=h3, data=bytes.fromhex(enc_api(d.hex())), timeout=8, verify=False)
        if r3.status_code == 200:
            t = r3.text
            jwt, aid = "", "N/A"
            
            i = t.find("eyJ")
            if i != -1:
                j = t[i:]
                s = j.find(".", j.find(".")+1)
                if s != -1:
                    jwt = j[:s+44]
                    try:
                        p = jwt.split(".")[1]; p += "=" * (-len(p) % 4)
                        dec = json.loads(base64.urlsafe_b64decode(p))
                        a = dec.get("account_id") or dec.get("external_id")
                        if a: aid = str(a)
                    except Exception: pass
            
            if aid == "N/A":
                matches = re.findall(r"\b\d{10,12}\b", t)
                if matches: aid = matches[0]
                
            return {
                "uid": uid,
                "password": pw,
                "account_id": aid,
                "jwt_token": jwt,
                "region": region,
                "name": name
            }
    except Exception:
        pass
        
    return None

@app.get("/api/gen")
@app.get("/gen")
def api_generate(region: str = "ID"):
    try:
        acc = generate_acc(region=region)
        if acc:
            return {"status": "success", "accounts": [acc]}
        else:
            return {"status": "error", "message": "Garena nolak (IP Vercel diblokir)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
