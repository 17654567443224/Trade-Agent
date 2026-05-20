import json
import logging
import time
import warnings
from datetime import datetime, timezone

import httpx
from httpx import Client

from . import consts as c, utils, exceptions


class OkxClient(Client):

    def __init__(self, api_key='-1', api_secret_key='-1', passphrase='-1', use_server_time=None,
                 flag='1', base_api=c.API_URL, proxy=None, logger=None, retry_time=60, **kwargs):
        try:
            super().__init__(base_url=base_api, http2=True, proxy=proxy)
        except TypeError:
            if proxy:
                super().__init__(base_url=base_api, http2=True, proxies={'http://': proxy, 'https://': proxy})
            else:
                super().__init__(base_url=base_api, http2=True)

        self.API_KEY = api_key
        self.API_SECRET_KEY = api_secret_key
        self.PASSPHRASE = passphrase
        self.use_server_time = False
        self.flag = flag
        self.domain = base_api
        self.retry_time = retry_time
        self.logger = logger if logger is not None else logging.getLogger(__name__)

        if use_server_time is not None:
            warnings.warn("use_server_time parameter is deprecated.", DeprecationWarning)

    def _request(self, method, request_path, params):
        if method == c.GET:
            request_path = request_path + utils.parse_params_to_str(params)

        timestamp = utils.get_timestamp()
        body = json.dumps(params) if method == c.POST else ""

        if self.API_KEY != '-1':
            sign = utils.sign(
                utils.pre_hash(timestamp, method, request_path, str(body)),
                self.API_SECRET_KEY
            )
            header = utils.get_header(self.API_KEY, sign, timestamp, self.PASSPHRASE, self.flag)
        else:
            header = utils.get_header_no_sign(self.flag)

        start_time = time.time()
        first_error = True
        while True:
            try:
                if method == c.GET:
                    response = self.get(request_path, headers=header)
                elif method == c.POST:
                    response = self.post(request_path, data=body, headers=header)
                else:
                    raise ValueError(f'Unsupported HTTP method: {method}')
                return response.json()
            except httpx.RequestError as e:
                if first_error:
                    self.logger.error(f'[okx] request error: {e}')
                    first_error = False
                if time.time() - start_time >= self.retry_time:
                    raise exceptions.OkxRequestException(str(e))
                time.sleep(0.5)

    def _request_without_params(self, method, request_path):
        return self._request(method, request_path, {})

    def _request_with_params(self, method, request_path, params):
        return self._request(method, request_path, params)

    def _get_timestamp(self):
        try:
            response = self.get(c.SERVER_TIMESTAMP_URL)
            if response.status_code == 200:
                ts = datetime.fromtimestamp(
                    int(response.json()['data'][0]['ts']) / 1000.0, tz=timezone.utc
                )
                return ts.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        except Exception:
            pass
        return utils.get_timestamp()
