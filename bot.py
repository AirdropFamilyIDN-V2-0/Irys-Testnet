import time
import json
import requests
import secrets
import random
from pathlib import Path
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import to_checksum_address

RPC_URL = "https://testnet-rpc.irys.xyz/v1/execution-rpc"
API_BASE = "https://play.irys.xyz/api"
PKEVM_FILE = "pkevm.txt"

GAME_CONFIG = {
    "snake": (300, 500),
    "hex-shooter": (300, 500),
    "asteroids": (20000, 40000),    
    "missile-command": (80000, 120000) 
}
GAME_COST = 0.001

DELAY_BETWEEN_ACCOUNTS = 1.5
DELAY_BETWEEN_ACTIONS = 1.0
RANDOM_DELAY_MIN = 2.0   
RANDOM_DELAY_MAX = 6.0  

OUT_FILE = "irys_results.json"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://play.irys.xyz",
    "Referer": "https://play.irys.xyz/",
    "User-Agent": "Mozilla/5.0 (AutoLoginIrys/1.0)"
}

w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"headers": HEADERS}))

def banner():
    print("--------------------------------------------------")
    print("🚀 Irys Testnet")
    print("💎 ADFMIDN Team")
    print("🎮 Snake + HexShooter + Asteroids + Missile-Command")
    print("--------------------------------------------------")


def read_private_keys(path):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"{path} tidak ditemukan.")
    keys = []
    with p.open("r", encoding="utf-8") as f:
        for ln in f:
            s = ln.strip()
            if not s:
                continue
            keys.append(s)
    return keys


from eth_utils import to_checksum_address

def eth_get_balance(address):
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "eth_getBalance",
        "params": [to_checksum_address(address), "latest"]
    }
    try:
        r = requests.post(RPC_URL, json=payload, headers=HEADERS, timeout=20)
        r.raise_for_status()
        resp = r.json()
        if "result" in resp:
            return int(resp["result"], 16)
        return None
    except Exception as e:
        return f"balance_error:{e}"



def make_session_id(ts_ms=None):
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)
    suffix = secrets.token_hex(5)
    return f"game_{ts_ms}_{suffix}"


def sign_message_text(pk, text):
    acct = Account.from_key(pk)
    msg = encode_defunct(text=text)
    signed = acct.sign_message(msg)
    return signed.signature.hex()


def is_success_response(resp):
    if not resp or not isinstance(resp, dict):
        return False
    if resp.get("success") is True:
        return True
    data = resp.get("data", {})
    if isinstance(data, dict) and data.get("success") is True:
        return True
    msg = (resp.get("message") or "").lower()
    if any(k in msg for k in ("success", "ok", "played", "completed", "accepted")):
        return True
    if resp.get("status") in ("ok", "success", 200):
        return True
    return False


def pay_game(pk, address, game_type, game_cost=GAME_COST):
    ts = int(time.time() * 1000)
    session_id = make_session_id(ts)
    message_text = (
        f"I authorize payment of {game_cost} IRYS to play a game on Irys Arcade.\n\n"
        f"Player: {address}\n"
        f"Amount: {game_cost} IRYS\n"
        f"Timestamp: {ts}\n\n"
        f"This signature confirms I own this wallet and authorize the payment."
    )
    signature = sign_message_text(pk, message_text)

    body = {
        "playerAddress": address,
        "gameCost": game_cost,
        "signature": signature,
        "message": message_text,
        "timestamp": ts,
        "sessionId": session_id,
        "gameType": game_type
    }


    r = requests.post(f"{API_BASE}/game/start", json=body, headers=HEADERS, timeout=20)
    r.raise_for_status()
    resp = r.json()
    return resp, session_id


def claim_game(pk, address, session_id, game_type, score=None):
    if score is None:
        low, high = GAME_CONFIG.get(game_type, (300, 500))
        score = secrets.randbelow(high - low + 1) + low

    ts = int(time.time() * 1000)
    message_text = (
        f"I completed a {game_type} game on Irys Arcade.\n\n"
        f"Player: {address}\n"
        f"Game: {game_type}\n"
        f"Score: {score}\n"
        f"Session: {session_id}\n"
        f"Timestamp: {ts}\n\n"
        f"This signature confirms I own this wallet and completed this game."
    )
    signature = sign_message_text(pk, message_text)

    body = {
        "playerAddress": address,
        "gameType": game_type,
        "score": score,
        "signature": signature,
        "message": message_text,
        "timestamp": ts,
        "sessionId": session_id
    }

    r = requests.post(f"{API_BASE}/game/complete", json=body, headers=HEADERS, timeout=20)
    r.raise_for_status()
    resp = r.json()
    return resp, score

def process_account(raw_pk, idx):
    result = {
        "index": idx,
        "raw_pk": raw_pk,
        "address": None,
        "balance_wei": None,
        "balance_eth": None,
        "games": {},
        "errors": []
    }

    pk = raw_pk if raw_pk.startswith("0x") else "0x" + raw_pk
    try:
        acct = Account.from_key(pk)
        address = acct.address
        result["address"] = address
    except Exception as e:
        result["errors"].append(f"invalid_key:{e}")
        return result

    try:
        bal = eth_get_balance(address)
        result["balance_wei"] = bal
        result["balance_eth"] = float(Web3.from_wei(bal or 0, "ether"))
    except Exception as e:
        result["errors"].append(f"balance_error:{e}")


    for game_type in GAME_CONFIG.keys():

        rand_delay = random.uniform(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)
        time.sleep(rand_delay)

        try:
            pay_resp, session_id = pay_game(pk, address, game_type)
        except Exception as e:
            result["errors"].append(f"{game_type}_pay_exception:{e}")
            pay_resp = None
            session_id = make_session_id()
            print(f"    {game_type:15s} | start failed, using fallback session {session_id[-8:]}")


        rand_delay = random.uniform(RANDOM_DELAY_MIN + 1.0, RANDOM_DELAY_MAX + 4.0)
        time.sleep(rand_delay)

        low, high = GAME_CONFIG.get(game_type, (300, 500))
        score = secrets.randbelow(high - low + 1) + low

        try:
            claim_resp, actual_score = claim_game(pk, address, session_id, game_type, score=score)
        except Exception as e:
            result["errors"].append(f"{game_type}_claim_exception:{e}")
            claim_resp = None
            actual_score = score
            print(f"    {game_type:15s} | claim failed: {e}")

        pay_ok = is_success_response(pay_resp)
        claim_ok = is_success_response(claim_resp)

        result["games"][game_type] = {
            "pay_resp": pay_resp,
            "claim_resp": claim_resp,
            "pay_ok": pay_ok,
            "claim_ok": claim_ok,
            "score": actual_score,
            "session_id": session_id
        }

        status_text = "OK" if pay_ok and claim_ok else "FAILED"
        msg_preview = ""
        if isinstance(claim_resp, dict):
            msg_preview = claim_resp.get("message") or claim_resp.get("msg") or ""
        print(f"    {game_type:15s} | score: {actual_score:7d} | session: {session_id[-8:]:8s} | status: {status_text} | msg: {msg_preview}")

    return result

def main():
    banner()
    print("[*] Mulai Irys auto-game script (multi-game per akun)")
    keys = read_private_keys(PKEVM_FILE)
    print(f"[*] Ditemukan {len(keys)} private key")
    results = []
    for i, pk in enumerate(keys, 1):
        print("\n--------------------------------------------------")
        print(f">>> Proses akun #{i}")
        try:
            res = process_account(pk, i)
            results.append(res)
            addr = res.get("address")
            be = res.get("balance_eth")
            print(f"    Address : {addr}")
            print(f"    Balance : {be} IRYS")
            if res.get("errors"):
                print("    Errors :", res["errors"])
        except Exception as e:
            print("    Exception utama:", e)
            results.append({"index": i, "raw_pk": pk, "errors": [str(e)]})

        time.sleep(DELAY_BETWEEN_ACCOUNTS)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\n--------------------------------------------------")
    print(f"[*] Selesai. Hasil disimpan di {OUT_FILE}")


if __name__ == "__main__":
    main()
