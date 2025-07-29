import requests
import aiohttp
from . import config
from aiohttp.client_exceptions import ClientOSError, ClientConnectionError, ServerDisconnectedError
from .utils import Validate, privUtils
from typing import Union
import json
import asyncio
import ssl

class _Profile:
    def __init__(self, otp, ck, i_d) -> None:
        self.OTP_SECRET = otp
        self.RBLX_COOKIE = ck
        self.USER_ID = i_d

class AuthenticatorAsync:
    def __init__(self) -> None:
        self._accs: dict[str, dict[str,int]] = dict()
        self.__current_account = str()
        self.__current_session: aiohttp.ClientSession()

    async def __ExecuteSequence(self, **kwargs):
        METHOD = kwargs['METHOD']
        INIT_DATA: dict = kwargs['INIT_DATA']
        varDict = {'Content-Type': 'application/json', 'actionType': 7}
        varDict['.ROBLOSECURITY'] = self._accs[self.__current_account]['RBLX_COOKIE']

        SEQUENCE = config.Config._Sequence(METHOD)
        resp = None

        try:
            for httpMethod in SEQUENCE:
                methodInfo = config.Config.HTTPCONFIG[httpMethod]
                methodHeaders = methodInfo['HEADERS']
                headersSubmit = {h: varDict[h] for h in methodHeaders}
                methodData = methodInfo['DATA']
                if not isinstance(methodData, str):
                    varDict['OTP_SECRET'] = privUtils._secrTo6Digi(self._accs[self.__current_account]['OTP_SECRET'])
                    dataSubmit = {d: varDict[methodData[d]] for d in methodData}
                else:
                    dataSubmit = kwargs['INIT_DATA']['POSTDATA']
                methodCookies = methodInfo['COOKIES']
                cookiesSubmit = {c: varDict[c] for c in methodCookies}
                url = methodInfo['URL'] if methodInfo['URL'] is not None else config.Config.URLCONFIG[httpMethod][METHOD]
                url = privUtils._urlProcessing(INIT_DATA, url)
                for key, value in dataSubmit.items():
                    if asyncio.iscoroutine(value):
                        dataSubmit[key] = await value
                for key, value in headersSubmit.items():
                    if asyncio.iscoroutine(value):
                        headersSubmit[key] = await value
                for attempt in range(3):
                    try:
                        if self.__current_session.closed:
                            self.__current_session = aiohttp.ClientSession()
                        if methodInfo['METHOD'] == 'POST':
                            resp = await self.__current_session.post(
                                url,
                                data=json.dumps(dataSubmit),
                                headers={str(k): str(v) for k, v in headersSubmit.items()},
                                cookies=cookiesSubmit
                            )
                            if "rblx-challenge-metadata" not in headersSubmit:
                                break
                            headersSubmit = {"x-csrf-token": headersSubmit["x-csrf-token"]}
                        elif methodInfo['METHOD'] == 'GET':
                            resp = await self.__current_session.get(
                                url,
                                headers={str(k): str(v) for k, v in headersSubmit.items()},
                                cookies=cookiesSubmit
                            )
                        break
                    except (ClientOSError, ServerDisconnectedError, ssl.SSLError, ClientConnectionError) as e:
                        if not self.__current_session.closed:
                            await self.__current_session.close()
                        self.__current_session = aiohttp.ClientSession()
                        await asyncio.sleep(2)
                    except Exception as e:
                        raise
                if resp is None:
                    raise RuntimeError("Failed to get response after retries")
                if resp.status in methodInfo['STATUS']:
                    for respHeader in methodInfo['RETURN_HEADERS']:
                        varDict[respHeader] = resp.headers.get(respHeader)
                    if methodInfo['PROCESSING']:
                        for i, funcName in enumerate(methodInfo['PROCESSING'][0]):
                            varDict[methodInfo['PROCESSING'][1][i]] = getattr(privUtils, funcName)(resp, varDict)
                else:
                    return resp
            return resp
        finally:
            if not self.__current_session.closed:
                await self.__current_session.close()

    @Validate.validate_types
    def add(self, USER_ID: Union[str, int], OTP_SECRET: str, RBLX_COOKIE: str, TAG: str = None) -> dict:
        if not TAG:
            TAG = USER_ID

        accountData: dict = _Profile(OTP_SECRET, RBLX_COOKIE, int(USER_ID)).__dict__
        self._accs[TAG] = accountData
        return accountData

    @Validate.validate_tag   
    @Validate.validate_types
    def config(self, TAG: str, UPDATED_INFO: dict[str, str]) -> dict:
        for _k in UPDATED_INFO:
            self._accs[TAG][_k] = UPDATED_INFO[_k]

        return self._accs[TAG]

    @Validate.validate_tag   
    @Validate.validate_types
    def remove(self, TAG: str) -> bool:
        if self._accs.get(TAG):
            self._accs.pop(TAG)
            return True
        raise KeyError(f'{TAG} does not exist in account cache.')    

    @Validate.validate_tag   
    @Validate.validate_types
    async def accept_trade(self, TAG: str, TRADE_ID: int) -> aiohttp.ClientResponse:
        self.__current_account = TAG
        self.__current_session = aiohttp.ClientSession()

        return await self.__ExecuteSequence(METHOD='ACCEPT', INIT_DATA={'USER_ID': self._accs[self.__current_account]['USER_ID'],'TRADE_ID': TRADE_ID, 'POSTDATA': {}})

    @Validate.validate_tag   
    @Validate.validate_types
    async def send_trade(self, TAG: str, TRADE_DATA: dict) -> aiohttp.ClientResponse:
        self.__current_account = TAG
        self.__current_session = aiohttp.ClientSession()

        return await self.__ExecuteSequence(METHOD='SEND', INIT_DATA={'USER_ID': self._accs[self.__current_account]['USER_ID'], 'POSTDATA': TRADE_DATA})

    @Validate.validate_tag   
    @Validate.validate_types
    async def counter_trade(self, TAG: str, TRADE_DATA: dict, TRADE_ID: int) -> requests.Response:
        self.__current_account = TAG
        self.__current_session = aiohttp.ClientSession()
        return await self.__ExecuteSequence(METHOD='COUNTER', INIT_DATA={'USER_ID': self._accs[self.__current_account]['USER_ID'],'TRADE_ID': TRADE_ID, 'POSTDATA': TRADE_DATA})

    @Validate.validate_tag   
    @Validate.validate_types
    async def decline_trade(self, TAG: str, TRADE_ID: int) -> requests.Response:
        self.__current_account = TAG
        self.__current_session = aiohttp.ClientSession()

        return await self.__ExecuteSequence(METHOD='DECLINE', INIT_DATA={'USER_ID': self._accs[self.__current_account]['USER_ID'],'TRADE_ID': TRADE_ID, 'POSTDATA': {}})

    @Validate.validate_tag   
    @Validate.validate_types
    async def one_time_payout(self, TAG: str, GROUP_ID: int, PAYOUT_DATA: dict) -> aiohttp.ClientResponse:
        self.__current_account = TAG
        self.__current_session = aiohttp.ClientSession()

        return await self.__ExecuteSequence(METHOD='GROUP_ONE_TIME_PAYOUT', INIT_DATA={'USER_ID': self._accs[self.__current_account]['USER_ID'],'GROUP_ID': GROUP_ID, 'POSTDATA': PAYOUT_DATA})

    @Validate.validate_tag   
    @Validate.validate_types
    async def recurring_payout(self, TAG: str, GROUP_ID: int, PAYOUT_DATA: dict) -> aiohttp.ClientResponse:
        self.__current_account = TAG
        self.__current_session = aiohttp.ClientSession()

        return await self.__ExecuteSequence(METHOD='GROUP_RECURRING_PAYOUT', INIT_DATA={'USER_ID': self._accs[self.__current_account]['USER_ID'],'GROUP_ID': GROUP_ID, 'POSTDATA': PAYOUT_DATA})

    @Validate.validate_tag    
    @Validate.validate_types
    async def accessory_purchase(self, TAG: str, ACCESSORY_ID: int, PURCHASE_DATA: dict) -> requests.Response:
        self.__current_account = TAG
        self.__current_session = aiohttp.ClientSession()

        return await self.__ExecuteSequence(METHOD='ACCESSORY_PURCHASE', INIT_DATA={'USER_ID': self._accs[self.__current_account]['USER_ID'],'ACCESSORY_ID': ACCESSORY_ID, 'POSTDATA': PURCHASE_DATA})

    @Validate.validate_tag   
    @Validate.validate_types
    def info(self, TAG: str) -> dict:
        if self._accs.get(TAG):
            return self._accs[TAG]
        raise KeyError(f'{TAG} does not exist in account cache.')

    def __repr__(self) -> str:
        return f'CLASS REPR: {self._accs}'

    async def close(self):
        if self.__current_session is not None:
            await self.__current_session.close()