from .okxclient import OkxClient
from .consts import *


class StatusAPI(OkxClient):
    def __init__(self, api_key='-1', api_secret_key='-1', passphrase='-1', use_server_time=None, flag='1', domain='https://www.okx.com', proxy=None, logger=None, retry_time=60, **kwargs):
        OkxClient.__init__(self, api_key, api_secret_key, passphrase, use_server_time, flag, domain, proxy, logger, retry_time)

    def status(self, state=''):
        params = {'state': state}
        return self._request_with_params(GET, STATUS, params)
