import aiohttp
import datetime
from useragent_changer import UserAgent

ua = UserAgent('iphone')

PROXY_URL = None


# --- send login request ---
async def login(phoneNumber: str, password: str, uuid: str):
    headers = {
        'User-Agent': ua.set(),
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Origin': 'https://www.paypay.ne.jp',
        'Referer': 'https://www.paypay.ne.jp/app/account/sign-in',
    }
    payload = {
        "scope": "SIGN_IN",
        "client_uuid": f"{uuid}",
        "grant_type": "password",
        "username": phoneNumber,
        "password": password,
        "add_otp_prefix": True,
        "language": "ja"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://www.paypay.ne.jp/app/v1/oauth/token",
            headers=headers,
            json=payload,
            proxy=PROXY_URL
        ) as login_request_response:
            return await login_request_response.json()


# --- one-time-password authentication ---
async def login_otp(set_uuid, otp, otpid, otp_pre):
    otp_number = otp
    headers = {
        'User-Agent': ua.set(),
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Origin': 'https://www.paypay.ne.jp',
        'Referer': 'https://www.paypay.ne.jp/app/account/sign-in',
    }
    payload = {
        "scope": "SIGN_IN",
        "client_uuid": f"{set_uuid}",
        "grant_type": "otp",
        "otp_prefix": str(otp_pre),
        "otp": otp_number,
        "otp_reference_id": otpid,
        "username_type": "MOBILE",
        "language": "ja"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://www.paypay.ne.jp/app/v1/oauth/token",
            headers=headers,
            json=payload,
            proxy=PROXY_URL
        ) as response:
            login_response = await response.json()
            try:
                if login_response["response_type"] == "ErrorResponse":
                    return "ERR"
            except Exception:
                return "OK"


async def check_link(cd):
    if "https://" in cd:
        cd = cd.replace("https://pay.paypay.ne.jp/", "")

    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": ua.set(),
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                f"https://www.paypay.ne.jp/app/v2/p2p-api/getP2PLinkInfo?verificationCode={cd}",
                headers=headers,
                proxy=PROXY_URL
            ) as response:
                response.raise_for_status()
                link_info = await response.json()

        except aiohttp.ClientError as e:
            print(f"API_REQ_EXC: {e}")
            return False

    result_code = link_info.get("header", {}).get("resultCode")
    if result_code != "S0000":
        return False

    order_status = link_info.get("payload", {}).get("orderStatus")
    if order_status == "PENDING":
        return link_info
    else:
        return False


async def link_rev(cd: str, phoneNumber: str, password: str, uuid: str, link_password: str = None):
    if "https://" in cd:
        cd = cd.replace("https://pay.paypay.ne.jp/", "")

    async with aiohttp.ClientSession() as session:
        base_headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": ua.set(),
            "Content-Type": "application/json"
        }

        try:
            async with session.get(
                f"https://www.paypay.ne.jp/app/v2/p2p-api/getP2PLinkInfo?verificationCode={cd}",
                headers=base_headers,
                proxy=PROXY_URL
            ) as response:
                response.raise_for_status()
                link_info = await response.json()

            if link_info.get("payload", {}).get("orderStatus") != "PENDING":
                return False

            if link_info.get("payload", {}).get("pendingP2PInfo", {}).get("isSetPasscode") and link_password is None:
                return False

        except aiohttp.ClientError as e:
            print(f"LINK_REQ_EXC: {e}")
            return False

        login_payload = {
            "scope": "SIGN_IN",
            "client_uuid": f"{uuid}",
            "grant_type": "password",
            "username": phoneNumber,
            "password": password,
            "add_otp_prefix": True,
            "language": "ja"
        }

        login_headers = {
            'User-Agent': ua.set(),
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Origin': 'https://www.paypay.ne.jp',
            'Referer': 'https://pay.paypay.ne.jp/' + cd,
        }

        async with session.post(
            "https://www.paypay.ne.jp/app/v1/oauth/token",
            headers=login_headers,
            json=login_payload,
            proxy=PROXY_URL
        ) as response:
            login_response = await response.json()
            try:
                login_response = login_response["access_token"]
            except Exception:
                try:
                    login_response["otp_reference_id"]
                    return "LOGINERR"
                except Exception:
                    return "LOGINERR"

        receive_payload = {
            "verificationCode": cd,
            "client_uuid": uuid,
            "requestAt": str(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%Y-%m-%dT%H:%M:%S+0900')),
            "requestId": link_info["payload"]["message"]["data"]["requestId"],
            "orderId": link_info["payload"]["message"]["data"]["orderId"],
            "senderMessageId": link_info["payload"]["message"]["messageId"],
            "senderChannelUrl": link_info["payload"]["message"]["chatRoomId"],
            "iosMinimumVersion": "3.45.0",
            "androidMinimumVersion": "3.45.0"
        }

        if link_password:
            receive_payload["passcode"] = link_password

        try:
            async with session.post(
                "https://www.paypay.ne.jp/app/v2/p2p-api/acceptP2PSendMoneyLink",
                json=receive_payload,
                headers=base_headers,
                proxy=PROXY_URL
            ) as response:
                response.raise_for_status()
                receive_data = await response.json()

                if receive_data.get("header", {}).get("resultCode") == "S0000":
                    return True
                else:
                    return False

        except aiohttp.ClientError as e:
            print(f"REVERR: {e}")
            return False


# --- create p2p code (受け取りURL生成) ---
async def create_p2pcode(access_token: str):
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": ua.set(),
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://www.paypay.ne.jp/app/v1/p2p-api/createP2PCode",
                headers=headers,
                proxy=PROXY_URL
            ) as response:
                response.raise_for_status()
                data = await response.json()

        except aiohttp.ClientError as e:
            print(f"P2PCODE_REQ_EXC: {e}")
            return False

    if data.get("header", {}).get("resultCode") != "S0000":
        print(data)
        return False

    return data["payload"]["p2pCode"]