import logging
import typing as tp

import httpcore
import httpx

from hishel._utils import generate_key, to_httpcore_request, to_httpcore_response, to_httpx_request, to_httpx_response

from .._controller import Controller
from .._serializers import DictSerializer
from ._storages import BaseStorage, FileStorage

logger = logging.getLogger('hishel.transports')

class CacheTransport(httpx.BaseTransport):

    def __init__(self,
                 transport: httpx.BaseTransport,
                 storage: tp.Optional[BaseStorage] = None,
                 cache_controller: tp.Optional[Controller] = None) -> None:
        self._transport = transport

        if storage is not None:
            self._storage = storage
        else:
            self._storage = FileStorage(serializer=DictSerializer())

        if cache_controller is not None:
            self._controller = cache_controller
        else:
            self._controller = Controller()

    def handle_request(self, request: httpx.Request) -> httpx.Response:

        httpcore_request = to_httpcore_request(httpx_request=request)
        key = generate_key(
            httpcore_request.method,
            httpcore_request.url,
            httpcore_request.headers
        )

        stored_resposne = self._storage.retreive(key)

        if stored_resposne:
            stored_resposne.read()
            logger.debug("A response to this request was found.")
            res = self._controller.construct_response_from_cache(request=httpcore_request, response=stored_resposne)

            if isinstance(res, httpcore.Response):
                logger.debug(f"Using cached response for the {request.url}")
                return to_httpx_response(res)
            elif isinstance(res, httpcore.Request):
                response = self._transport.handle_request(to_httpx_request(res))
                response.read()
                updated_response = self._controller.handle_validation_response(
                    old_response=stored_resposne, new_response=to_httpcore_response(response)
                )
                self._storage.store(key, updated_response)
                return to_httpx_response(updated_response)

            assert False, "invalid return value for `construct_response_from_cache`"
        logger.debug("A response to this request was not found.")
        response = self._transport.handle_request(request)
        response.read()

        httpcore_response = to_httpcore_response(response)
        if self._controller.is_cachable(request=httpcore_request, response=httpcore_response):
            self._storage.store(key, httpcore_response)
        else:
            logger.debug("ignoring the response because it cannot be cached")

        return response