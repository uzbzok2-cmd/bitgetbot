import hashlib
import hmac
import base64
import time
import requests
import json
from typing import Optional
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASSPHRASE, FUTURES_BASE_URL


class BitgetClient:
    def __init__(self):
        self.api_key = BITGET_API_KEY
        self.api_secret = BITGET_API_SECRET
        self.passphrase = BITGET_API_PASSPHRASE
        self.base_url = FUTURES_BASE_URL
        self.session = requests.Session()

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        message = timestamp + method.upper() + path + body
        mac = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            digestmod=hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode()

    def _headers(self, method: str, path: str, body: str = "") -> dict:
        timestamp = str(int(time.time() * 1000))
        sign = self._sign(timestamp, method, path, body)
        return {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": sign,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "locale": "en-US"
        }

    def _get(self, path: str, params: dict = None) -> dict:
        query = ""
        if params:
            query = "?" + "&".join(f"{k}={v}" for k, v in params.items())
        full_path = path + query
        headers = self._headers("GET", full_path)
        try:
            resp = self.session.get(self.base_url + full_path, headers=headers, timeout=10)
            return resp.json()
        except Exception as e:
            return {"code": "error", "msg": str(e), "data": None}

    def _post(self, path: str, body: dict) -> dict:
        body_str = json.dumps(body)
        headers = self._headers("POST", path, body_str)
        try:
            resp = self.session.post(self.base_url + path, headers=headers, data=body_str, timeout=10)
            return resp.json()
        except Exception as e:
            return {"code": "error", "msg": str(e), "data": None}

    # ═══════════════════════════════════════════════
    # FUTURES ENDPOINTS
    # ═══════════════════════════════════════════════

    def get_futures_account(self, product_type: str = "USDT-FUTURES", margin_coin: str = "USDT") -> dict:
        result = self._get("/api/v2/mix/account/accounts", {"productType": product_type})
        if result.get("code") == "00000":
            accounts = result.get("data", [])
            for acc in accounts:
                if acc.get("marginCoin") == margin_coin:
                    result["data"] = acc
                    return result
            if accounts:
                result["data"] = accounts[0]
        return result

    def get_futures_accounts_all(self, product_type: str = "USDT-FUTURES") -> dict:
        return self._get("/api/v2/mix/account/accounts", {"productType": product_type})

    def get_futures_positions(self, product_type: str = "USDT-FUTURES") -> dict:
        return self._get("/api/v2/mix/position/all-position", {
            "productType": product_type,
            "marginCoin": "USDT"
        })

    def get_futures_open_orders(self, product_type: str = "USDT-FUTURES") -> dict:
        return self._get("/api/v2/mix/order/orders-pending", {"productType": product_type})

    def get_futures_plan_orders(self, product_type: str = "USDT-FUTURES") -> dict:
        return self._get("/api/v2/mix/order/orders-plan-pending", {"productType": product_type})

    def get_futures_history(self, product_type: str = "USDT-FUTURES", start_time: str = "", end_time: str = "", limit: int = 100) -> dict:
        params = {"productType": product_type, "limit": str(limit)}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return self._get("/api/v2/mix/order/fill-history", params)

    def get_futures_order_history(self, product_type: str = "USDT-FUTURES", start_time: str = "", end_time: str = "", limit: int = 100) -> dict:
        params = {"productType": product_type, "limit": str(limit)}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return self._get("/api/v2/mix/order/orders-history", params)

    def get_futures_ticker(self, symbol: str) -> dict:
        return self._get("/api/v2/mix/market/ticker", {"symbol": symbol, "productType": "USDT-FUTURES"})

    def get_futures_tickers(self, product_type: str = "USDT-FUTURES") -> dict:
        return self._get("/api/v2/mix/market/tickers", {"productType": product_type})

    def get_futures_candles(self, symbol: str, granularity: str = "1H", limit: int = 100) -> dict:
        return self._get("/api/v2/mix/market/candles", {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "granularity": granularity,
            "limit": str(limit)
        })

    def get_futures_leverage_info(self, symbol: str, product_type: str = "USDT-FUTURES") -> dict:
        return self._get("/api/v2/mix/market/symbol-leverage", {
            "symbol": symbol,
            "productType": product_type
        })

    def get_futures_contract_info(self, symbol: str, product_type: str = "USDT-FUTURES") -> dict:
        return self._get("/api/v2/mix/market/contracts", {
            "symbol": symbol,
            "productType": product_type
        })

    def get_all_futures_contracts(self, product_type: str = "USDT-FUTURES") -> dict:
        return self._get("/api/v2/mix/market/contracts", {"productType": product_type})

    def set_leverage(self, symbol: str, leverage: int, margin_coin: str = "USDT", product_type: str = "USDT-FUTURES", hold_side: str = "long") -> dict:
        return self._post("/api/v2/mix/account/set-leverage", {
            "symbol": symbol,
            "productType": product_type,
            "marginCoin": margin_coin,
            "leverage": str(leverage),
            "holdSide": hold_side
        })

    def set_margin_mode(self, symbol: str, margin_mode: str = "crossed", product_type: str = "USDT-FUTURES", margin_coin: str = "USDT") -> dict:
        return self._post("/api/v2/mix/account/set-margin-mode", {
            "symbol": symbol,
            "productType": product_type,
            "marginCoin": margin_coin,
            "marginMode": margin_mode
        })

    def place_futures_order(self, symbol: str, side: str, trade_side: str, size: str,
                             price: str = "", order_type: str = "market",
                             product_type: str = "USDT-FUTURES", margin_coin: str = "USDT",
                             margin_mode: str = "crossed") -> dict:
        body = {
            "symbol": symbol,
            "productType": product_type,
            "marginMode": margin_mode,
            "marginCoin": margin_coin,
            "size": size,
            "side": side,
            "tradeSide": trade_side,
            "orderType": order_type,
        }
        if price:
            body["price"] = price
        return self._post("/api/v2/mix/order/place-order", body)

    def place_futures_tp_sl(self, symbol: str, plan_type: str, trigger_price: str,
                             side: str, size: str, product_type: str = "USDT-FUTURES",
                             margin_coin: str = "USDT") -> dict:
        return self._post("/api/v2/mix/order/place-tpsl-order", {
            "symbol": symbol,
            "productType": product_type,
            "marginCoin": margin_coin,
            "planType": plan_type,
            "triggerPrice": trigger_price,
            "triggerType": "mark_price",
            "executePrice": "0",
            "holdSide": side,
            "size": size
        })

    def close_futures_position(self, symbol: str, hold_side: str, product_type: str = "USDT-FUTURES", margin_coin: str = "USDT") -> dict:
        return self._post("/api/v2/mix/order/close-positions", {
            "symbol": symbol,
            "productType": product_type,
            "holdSide": hold_side,
            "marginCoin": margin_coin
        })

    def cancel_futures_order(self, symbol: str, order_id: str, product_type: str = "USDT-FUTURES") -> dict:
        return self._post("/api/v2/mix/order/cancel-order", {
            "symbol": symbol,
            "productType": product_type,
            "orderId": order_id
        })

    # ═══════════════════════════════════════════════
    # SPOT ENDPOINTS
    # ═══════════════════════════════════════════════

    def get_spot_account(self) -> dict:
        return self._get("/api/v2/spot/account/assets")

    def get_spot_tickers(self) -> dict:
        return self._get("/api/v2/spot/market/tickers")

    def get_spot_ticker(self, symbol: str) -> dict:
        return self._get("/api/v2/spot/market/tickers", {"symbol": symbol})

    def get_spot_candles(self, symbol: str, granularity: str = "1H", limit: int = 100) -> dict:
        return self._get("/api/v2/spot/market/candles", {
            "symbol": symbol,
            "granularity": granularity,
            "limit": str(limit)
        })

    def get_spot_open_orders(self) -> dict:
        return self._get("/api/v2/spot/trade/unfilled-orders")

    def get_spot_history(self, start_time: str = "", end_time: str = "", limit: int = 100) -> dict:
        params = {"limit": str(limit)}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return self._get("/api/v2/spot/trade/fills", params)

    def get_spot_order_history(self, start_time: str = "", end_time: str = "", limit: int = 100) -> dict:
        params = {"limit": str(limit)}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return self._get("/api/v2/spot/trade/history-orders", params)

    def place_spot_order(self, symbol: str, side: str, order_type: str,
                          size: str, price: str = "", force: str = "gtc") -> dict:
        body = {
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "size": size,
            "force": force
        }
        if price:
            body["price"] = price
        return self._post("/api/v2/spot/trade/place-order", body)

    def cancel_spot_order(self, symbol: str, order_id: str) -> dict:
        return self._post("/api/v2/spot/trade/cancel-order", {
            "symbol": symbol,
            "orderId": order_id
        })

    def get_spot_symbol_info(self, symbol: str = "") -> dict:
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._get("/api/v2/spot/public/symbols", params)

    # ═══════════════════════════════════════════════
    # FUNDING RATE
    # ═══════════════════════════════════════════════

    def get_funding_rate(self, symbol: str, product_type: str = "USDT-FUTURES") -> dict:
        return self._get("/api/v2/mix/market/current-fund-rate", {
            "symbol": symbol,
            "productType": product_type
        })

    def get_funding_history(self, symbol: str, product_type: str = "USDT-FUTURES", limit: int = 20) -> dict:
        return self._get("/api/v2/mix/market/history-fund-rate", {
            "symbol": symbol,
            "productType": product_type,
            "pageSize": str(limit)
        })
