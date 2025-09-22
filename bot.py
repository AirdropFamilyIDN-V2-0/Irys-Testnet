import time
import json
import requests
import secrets
from pathlib import Path
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()

RPC_URL = "https://testnet-rpc.irys.xyz/v1/execution-rpc"
API_BASE = "https://play.irys.xyz/api"
PKEVM_FILE = "pkevm.txt"

GAME_TYPE = "hex-shooter"
GAME_COST = 0.001            
SCORE_MIN = 15000          
SCORE_MAX = 30000

DELAY_BETWEEN_ACCOUNTS = 1.2   
DELAY_BETWEEN_ACTIONS = 0.8    

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
    text = Text()
    text.append("🚀 Irys Testnet\n", style="bold cyan")
    text.append("💎 ADFMIDN Team\n", style="bold magenta")
    text.append("🎯 Join Membership For BOT AirDrop\n", style="bold green")

    console.print(
        Panel(
            text,
            title="AUTO BOT AIRDROP",
            title_align="center",
            border_style="bright_yellow",
            box=box.DOUBLE,
        )
    )

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

def eth_get_balance(address):
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "eth_getBalance",
        "params": [Web3.toChecksumAddress(address), "latest"]
    }
    r = requests.post(RPC_URL, json=payload, headers=HEADERS, timeout=20)
    r.raise_for_status()
    resp = r.json()
    if "result" in resp:
        try:
            return int(resp["result"], 16)
        except Exception:
            return None
    return None

def make_session_id(ts_ms=None):
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)
    suffix = secrets.token_hex(4)
    return f"game_{ts_ms}_{suffix}"

def sign_message_text(pk, text):
    acct = Account.from_key(pk)
    msg = encode_defunct(text=text)
    signed = acct.sign_message(msg)
    return signed.signature.hex()

def pay_game(pk, address, game_type=GAME_TYPE, game_cost=GAME_COST):
    ts = int(time.time() * 1000)
    session_id = make_session_id(ts)
    message_text = (
        f"I authorize payment of {game_cost} IRYS to play a game on Irys Arcade.\n    \n"
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
    return r.json()

def claim_game(pk, address, session_id, game_type=GAME_TYPE, score=None):
    if score is None:
        score = secrets.randbelow(max(1, SCORE_MAX - SCORE_MIN + 1)) + SCORE_MIN

    ts = int(time.time() * 1000)
    message_text = (
        f"I completed a {game_type} game on Irys Arcade.\n    \n"
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
    return r.json()

def process_account(raw_pk, idx):
    result = {
        "index": idx,
        "raw_pk": raw_pk,
        "address": None,
        "balance_wei": None,
        "balance_eth": None,
        "pay_resp": None,
        "claim_resp": None,
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
        result["balance_eth"] = float(w3.fromWei(bal or 0, "ether"))
    except Exception as e:
        result["errors"].append(f"balance_error:{e}")

    time.sleep(DELAY_BETWEEN_ACTIONS)

    try:
        pay_resp = pay_game(pk, address, game_type=GAME_TYPE, game_cost=GAME_COST)
        result["pay_resp"] = pay_resp
        if isinstance(pay_resp, dict) and not pay_resp.get("success", True):
            result["errors"].append(f"pay_failed:{pay_resp.get('message')}")
    except Exception as e:
        result["errors"].append(f"pay_exception:{e}")
        pay_resp = None

    time.sleep(DELAY_BETWEEN_ACTIONS)

    session_id = None
    try:
        if pay_resp and isinstance(pay_resp, dict):
            sid = None
            if pay_resp.get("data") and isinstance(pay_resp.get("data"), dict):
                sid = pay_resp["data"].get("sessionId")
            if not sid and pay_resp.get("sessionId"):
                sid = pay_resp.get("sessionId")
            session_id = sid

        if not session_id:
            session_id = make_session_id()

        score = secrets.randbelow(max(1, SCORE_MAX - SCORE_MIN + 1)) + SCORE_MIN

        claim_resp = claim_game(pk, address, session_id, game_type=GAME_TYPE, score=score)
        result["claim_resp"] = claim_resp
        if isinstance(claim_resp, dict) and not claim_resp.get("success", True):
            result["errors"].append(f"claim_failed:{claim_resp.get('message')}")
    except Exception as e:
        result["errors"].append(f"claim_exception:{e}")

    return result

def main():
    banner()  
    print("[*] Mulai Irys auto-game script")
    keys = read_private_keys(PKEVM_FILE)
    print(f"[*] Ditemukan {len(keys)} private key")
    results = []
    for i, pk in enumerate(keys, 1):
        print(f"\n>>> Proses akun #{i}")
        try:
            res = process_account(pk, i)
            results.append(res)
            addr = res.get("address")
            be = res.get("balance_eth")
            print(f"    address: {addr} | balance (IRYS): {be}")
            if res.get("pay_resp"):
                print("    pay_resp success:", res["pay_resp"].get("success"), "| message:", res["pay_resp"].get("message"))
            if res.get("claim_resp"):
                print("    claim_resp success:", res["claim_resp"].get("success"), "| message:", res["claim_resp"].get("message"))
            if res.get("errors"):
                print("    errors:", res["errors"])
        except Exception as e:
            print("    Exception utama:", e)
            results.append({"index": i, "raw_pk": pk, "errors": [str(e)]})

        time.sleep(DELAY_BETWEEN_ACCOUNTS)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n[*] Selesai. Hasil disimpan di {OUT_FILE}")

if __name__ == "__main__":
    main()
