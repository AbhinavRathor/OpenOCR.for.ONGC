import io
import json
import logging
import time
import urllib.parse
from functools import cached_property, wraps
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generator,
    Generic,
    Iterable,
    Type,
    TypeVar,
)

import grpc
import requests
from google.protobuf.message import Message

from . import beaker_pb2 as pb2
from . import beaker_pb2_grpc
from .config import Config
from .exceptions import *
from .exceptions import BeakerQueueNotFound
from .utils import pb2_to_dict

if TYPE_CHECKING:
    from .client import Beaker


T = TypeVar("T")


class RpcMethod(Generic[T]):
    def __init__(self, method: grpc.UnaryUnaryMultiCallable):
        self.method = method

    def __call__(
        self,
        request: Message,
        exceptions_for_status: dict[grpc.StatusCode, Exception] | None = None,
        **kwargs,
    ) -> T:
        try:
            return self.method(request, **kwargs)
        except RpcError as e:
            raise coerce_rpc_error(e, exceptions_for_status)

    @property
    def name(self) -> str:
        return self.method._method.decode()  # type: ignore


class RpcStreamingMethod(Generic[T]):
    def __init__(self, method: grpc.UnaryStreamMultiCallable):
        self.method = method

    def __call__(
        self,
        request: Message,
        exceptions_for_status: dict[grpc.StatusCode, Exception] | None = None,
        **kwargs,
    ) -> Generator[T, None, None]:
        try:
            yield from self.method(request, **kwargs)
        except RpcError as e:
            raise coerce_rpc_error(e, exceptions_for_status)

    @property
    def name(self) -> str:
        return self.method._method.decode()  # type: ignore


class RpcBidirectionalStreamingMethod(Generic[T]):
    def __init__(self, method: grpc.StreamStreamMultiCallable):
        self.method = method

    def __call__(
        self,
        request: Iterable[Message],
        exceptions_for_status: dict[grpc.StatusCode, Exception] | None = None,
        **kwargs,
    ) -> Generator[T, None, None]:
        try:
            yield from self.method(request, **kwargs)
        except RpcError as e:
            raise coerce_rpc_error(e, exceptions_for_status)

    @property
    def name(self) -> str:
        return self.method._method.decode()  # type: ignore


def coerce_rpc_error(
    e: RpcError, exceptions_for_status: dict[grpc.StatusCode, Exception] | None = None
):
    if isinstance(e, grpc.Call):
        status = e.code()
        if exceptions_for_status is not None and status in exceptions_for_status:
            return exceptions_for_status[status]
        elif status == grpc.StatusCode.UNIMPLEMENTED:
            return NotImplementedError(e.details())
        elif status == grpc.StatusCode.PERMISSION_DENIED:
            return BeakerPermissionsError(e.details())
        elif status == grpc.StatusCode.NOT_FOUND:
            return BeakerNotFoundError(e.details())
        elif status == grpc.StatusCode.INVALID_ARGUMENT:
            return BeakerClientError(e.details())
        elif status == grpc.StatusCode.INTERNAL:
            if "RST_STREAM" in e.details():
                return BeakerStreamConnectionClosedError(e.details())
            else:
                return BeakerServerError(e.details())
        elif status == grpc.StatusCode.UNAVAILABLE:
            return BeakerServerUnavailableError(e.details())
    return e


class ServiceClient:
    MAX_PAGE_SIZE = 50

    def __init__(self, beaker: "Beaker"):
        self.beaker = beaker
        self._base_url = f"{self.config.agent_address}/api/{self.beaker.API_VERSION}"

    @property
    def config(self) -> Config:
        return self.beaker.config

    @property
    def logger(self) -> logging.Logger:
        return self.beaker.logger

    @property
    def service(self) -> beaker_pb2_grpc.BeakerStub:
        return self.beaker.service

    def http_request(
        self,
        resource: str,
        method: str = "GET",
        query: dict[str, Any] | None = None,
        data: Any | None = None,
        exceptions_for_status: dict[int, Exception] | None = None,
        headers: dict[str, str] | None = None,
        token: str | None = None,
        base_url: str | None = None,
        stream: bool = False,
        timeout: float | tuple[float, float] | None = None,
    ) -> requests.Response:
        def make_request(session: requests.Session) -> requests.Response:
            # Build URL.
            url = f"{base_url or self._base_url}/{resource}"
            if query is not None:
                url = url + "?" + urllib.parse.urlencode(query)

            # Populate headers.
            default_headers = {
                "Authorization": f"Bearer {token or self.config.user_token}",
                "Content-Type": "application/json",
                "User-Agent": self.beaker.user_agent,
            }
            if headers is not None:
                default_headers.update(headers)

            # Validate request data.
            request_data: str | bytes | io.BufferedReader | io.BytesIO | None = None
            if isinstance(data, Message):
                request_data = json.dumps(pb2_to_dict(data))
            elif isinstance(data, dict):
                request_data = json.dumps(data)
            elif isinstance(data, (str, bytes, io.BufferedReader, io.BytesIO)):
                request_data = data
            elif data is not None:
                raise TypeError(f"Unexpected type for 'data', got {type(data)}")

            # Log request at DEBUG.
            if isinstance(request_data, str):
                self.logger.debug("SEND %s %s - %s", method, url, request_data)
            elif isinstance(request_data, bytes):
                self.logger.debug("SEND %s %s - %d bytes", method, url, len(request_data))
            elif request_data is not None:
                self.logger.debug("SEND %s %s - ? bytes", method, url)
            else:
                self.logger.debug("SEND %s %s", method, url)

            # Make request.
            response = getattr(session, method.lower())(
                url,
                headers=default_headers,
                data=request_data,
                stream=stream,
                timeout=timeout or self.beaker.TIMEOUT,
            )

            # Log response at DEBUG.
            if (
                not stream
                and self.logger.isEnabledFor(logging.DEBUG)
                and len(response.content) < 1024
                and response.text
            ):
                self.logger.debug("RECV %s %s %s - %s", method, url, response, response.text)
            else:
                self.logger.debug("RECV %s %s %s", method, url, response)

            status_code = response.status_code

            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                # Try parsing error message from the response
                msg: str | None = None
                if response.text:
                    try:
                        msg = json.loads(response.text)["message"]
                    except (TypeError, KeyError, json.JSONDecodeError):
                        pass

                # HACK: sometimes Beaker doesn't use the right error code, so we try to guess based
                # on the message.
                if status_code == 400 and msg is not None and "already in use" in msg:
                    status_code = 409

                if exceptions_for_status is not None and status_code in exceptions_for_status:
                    raise exceptions_for_status[status_code]

                if msg is not None and status_code is not None and 400 <= status_code < 500:
                    # Raise a BeakerError if we're misusing the API (4xx error code).
                    if status_code == 403:
                        raise BeakerPermissionsError(msg)
                    else:
                        raise BeakerError(f"[code={status_code}] {msg}")
                elif msg is not None:
                    raise HTTPError(msg, response=response)  # type: ignore
                elif status_code == 405:
                    raise BeakerClientError(f"[code={status_code}] method not allowed")
                else:
                    raise

            return response

        if method in {"HEAD", "GET"}:
            # We assume HEAD and GET calls won't modify state, so they're
            # safe to retry for any recoverable error.
            make_request = self._retriable()(make_request)

        with self.beaker.http_session() as session:
            return make_request(session)

    def rpc_request(
        self,
        method: RpcMethod[T],
        request: Message,
        exceptions_for_status: dict[grpc.StatusCode, Exception] | None = None,
        retriable: bool | None = None,
    ) -> T:
        self.logger.debug("Calling unary-unary RPC method '%s'", method.name)

        if retriable is None:
            request_name = request.__class__.__name__
            retriable = (
                request_name.startswith("Get")
                or request_name.startswith("List")
                or request_name.startswith("Resolve")
            )

        method_to_call = self._retriable()(method) if retriable else method
        return method_to_call(
            request,
            exceptions_for_status=exceptions_for_status,
            metadata=self._rpc_call_metadata,
        )

    def rpc_paged_request(
        self,
        method: RpcMethod[T],
        request: Message,
        exceptions_for_status: dict[grpc.StatusCode, Exception] | None = None,
        retriable: bool = True,
    ) -> Generator[T, None, None]:
        self.logger.debug("Calling paged unary-unary RPC method '%s'", method.name)

        method_to_call = self._retriable()(method) if retriable else method
        response = method_to_call(
            request, exceptions_for_status=exceptions_for_status, metadata=self._rpc_call_metadata
        )
        yield response

        next_page_token = response.next_page_token  # type: ignore
        while next_page_token:
            request.next_page_token = next_page_token  # type: ignore
            response = method_to_call(
                request,
                exceptions_for_status=exceptions_for_status,
                metadata=self._rpc_call_metadata,
            )
            next_page_token = response.next_page_token  # type: ignore
            yield response

    def rpc_streaming_request(
        self,
        method: RpcStreamingMethod[T],
        request: Message,
        exceptions_for_status: dict[grpc.StatusCode, Exception] | None = None,
    ) -> Generator[T, None, None]:
        self.logger.debug("Calling unary-streaming RPC method '%s'", method.name)
        yield from method(
            request,
            exceptions_for_status=exceptions_for_status,
            metadata=self._rpc_call_metadata,
        )

    def rpc_bidirectional_streaming_request(
        self,
        method: RpcBidirectionalStreamingMethod[T],
        request: Iterable[Message],
        exceptions_for_status: dict[grpc.StatusCode, Exception] | None = None,
    ) -> Generator[T, None, None]:
        self.logger.debug("Calling bidirectional-streaming RPC method '%s'", method.name)
        yield from method(
            request,
            exceptions_for_status=exceptions_for_status,
            metadata=self._rpc_call_metadata,
        )

    def resolve_org_id(self, org: str | pb2.Organization | None = None) -> str:
        if isinstance(org, pb2.Organization):
            return org.id

        if org is None:
            if self.config.default_org is not None:
                org = self.config.default_org
            elif self.config.default_workspace is not None and "/" in self.config.default_workspace:
                org = self.config.default_workspace.split("/", 1)[0]

        if org is None:
            raise BeakerOrganizationNotSet(
                "default organization not set, please specify the org name"
            )

        try:
            return self.rpc_request(
                RpcMethod[pb2.ResolveOrganizationNameResponse](
                    self.service.ResolveOrganizationName
                ),
                pb2.ResolveOrganizationNameRequest(organization_name=org),
                exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerOrganizationNotFound(org)},
            ).organization_id
        except BeakerOrganizationNotFound:
            return org  # this could be an org ID.

    def resolve_user_id(self, user: str | pb2.User | None = None) -> str:
        if isinstance(user, pb2.User):
            return user.id

        if user is None:
            return self.beaker.user.get().id

        try:
            return self.rpc_request(
                RpcMethod[pb2.ResolveUserNameResponse](self.service.ResolveUserName),
                pb2.ResolveUserNameRequest(user_name=user),
                exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerUserNotFound(user)},
            ).user_id
        except BeakerUserNotFound:
            return user  # this could be a user ID

    def resolve_workspace_id(self, workspace: str | pb2.Workspace | None = None) -> str:
        if isinstance(workspace, pb2.Workspace):
            return workspace.id

        if workspace is None:
            if self._default_workspace_id is not None:
                return self._default_workspace_id
            else:
                raise BeakerWorkspaceNotSet(
                    "'workspace' argument required since default workspace not set"
                )

        if "/" not in workspace:
            return workspace

        owner_name, workspace_name = workspace.split("/", 1)
        return self.rpc_request(
            RpcMethod[pb2.ResolveWorkspaceNameResponse](self.service.ResolveWorkspaceName),
            pb2.ResolveWorkspaceNameRequest(owner_name=owner_name, workspace_name=workspace_name),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerWorkspaceNotFound(workspace)},
        ).workspace_id

    def resolve_image_id(self, image: str | pb2.Image) -> str:
        if isinstance(image, pb2.Image):
            return image.id

        if "/" not in image:
            return image

        author_name, image_name = image.split("/", 1)
        return self.rpc_request(
            RpcMethod[pb2.ResolveImageNameResponse](self.service.ResolveImageName),
            pb2.ResolveImageNameRequest(author_name=author_name, image_name=image_name),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerImageNotFound(image)},
        ).image_id

    def resolve_experiment_id(self, experiment: str | pb2.Experiment | pb2.Workload) -> str:
        if isinstance(experiment, pb2.Experiment):
            return experiment.id

        if isinstance(experiment, pb2.Workload) and not self.beaker.workload.is_experiment(
            experiment
        ):
            raise ValueError(
                f"workload '{self.resolve_workload_id(experiment)}' is not an experiment"
            )

        return self.resolve_workload_id(experiment)

    def resolve_workload_id(self, workload: str | pb2.Workload) -> str:
        if isinstance(workload, pb2.Workload):
            if self.beaker.workload.is_experiment(workload):
                return workload.experiment.id
            elif self.beaker.workload.is_environment(workload):
                return workload.environment.id
            else:
                raise ValueError(f"workload is neither an experiment or an environment: {workload}")

        if "/" not in workload:
            return workload

        author_name, workload_name = workload.split("/", 1)
        return self.rpc_request(
            RpcMethod[pb2.ResolveWorkloadNameResponse](self.service.ResolveWorkloadName),
            pb2.ResolveWorkloadNameRequest(author_name=author_name, workload_name=workload_name),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerWorkloadNotFound(workload)},
        ).workload_id

    def resolve_dataset_id(self, dataset: str | pb2.Dataset) -> str:
        if isinstance(dataset, pb2.Dataset):
            return dataset.id

        if "/" not in dataset:
            return dataset

        author_name, dataset_name = dataset.split("/", 1)
        return self.rpc_request(
            RpcMethod[pb2.ResolveDatasetNameResponse](self.service.ResolveDatasetName),
            pb2.ResolveDatasetNameRequest(author_name=author_name, dataset_name=dataset_name),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerDatasetNotFound(dataset)},
        ).dataset_id

    def resolve_cluster_id(self, cluster: str | pb2.Cluster) -> str:
        if isinstance(cluster, pb2.Cluster):
            return cluster.id

        if "/" not in cluster:
            return cluster

        owner_name, cluster_name = cluster.split("/", 1)
        return self.rpc_request(
            RpcMethod[pb2.ResolveClusterNameResponse](self.service.ResolveClusterName),
            pb2.ResolveClusterNameRequest(owner_name=owner_name, cluster_name=cluster_name),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerClusterNotFound(cluster)},
        ).cluster_id

    def resolve_node_id(self, node: str | pb2.Node) -> str:
        if isinstance(node, pb2.Node):
            return node.id
        # TODO: currently there's no ResolveNodeName method.
        if "/" in node:
            raise ValueError("invalid node ID")
        return node

    def resolve_budget_id(self, budget: str) -> str:
        if "/" not in budget:
            return budget

        org_name, budget_name = budget.split("/", 1)
        return self.rpc_request(
            RpcMethod[pb2.ResolveBudgetNameResponse](self.service.ResolveBudgetName),
            pb2.ResolveBudgetNameRequest(organization_name=org_name, budget_name=budget_name),
            exceptions_for_status={
                grpc.StatusCode.NOT_FOUND: BeakerBudgetNotFound(budget),
            },
        ).budget_id

    def resolve_group_id(self, group: str | pb2.Group) -> str:
        if isinstance(group, pb2.Group):
            return group.id
        # TODO: currently there's no ResolveGroupName method.
        if "/" in group:
            raise ValueError("invalid group ID")
        return group

    def resolve_queue_id(self, queue: str | pb2.Queue) -> str:
        if isinstance(queue, pb2.Queue):
            return queue.id

        if "/" not in queue:
            return queue

        author_name, queue_name = queue.split("/", 1)
        return self.rpc_request(
            RpcMethod[pb2.ResolveQueueNameResponse](self.service.ResolveQueueName),
            pb2.ResolveQueueNameRequest(author_name=author_name, queue_name=queue_name),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerQueueNotFound(queue)},
        ).queue_id

    @cached_property
    def _default_workspace_id(self) -> str | None:
        if (workspace_name := self.config.default_workspace) is not None:
            return self.resolve_workspace_id(workspace_name)
        return None

    @property
    def _rpc_call_metadata(self) -> list[tuple[str, str]]:
        return [
            ("authorization", f"bearer {self.config.user_token}"),
            ("user-agent", self.beaker.user_agent),
        ]

    def _validate_beaker_name(self, name: str) -> str:
        if (
            not name
            or name.startswith("-")
            or not name.replace("-", "").replace("_", "").replace(".", "").isalnum()
        ):
            raise ValueError(
                f"Invalid name '{name}'. Beaker names can only contain letters, "
                f"digits, periods, dashes, and underscores, and cannot start with a dash."
            )
        return name

    def _url_quote(self, id: str) -> str:
        return urllib.parse.quote(id, safe="")

    def _log_and_wait(
        self, retries_so_far: int, err: Exception, log_level: int = logging.WARNING
    ) -> None:
        retry_in = min(self.beaker.BACKOFF_FACTOR * (2**retries_so_far), self.beaker.BACKOFF_MAX)
        self.logger.log(
            log_level,
            "Request failed with retriable error: %s: %s\nRetrying in %d second(s)...",
            err.__class__.__name__,
            err,
            retry_in,
        )
        time.sleep(retry_in)

    def _retriable(
        self,
        on_failure: Callable[..., None] | None = None,
        recoverable_errors: tuple[Type[Exception], ...] = (
            RequestException,
            BeakerServerError,
        ),
        expected_errors: tuple[Type[Exception], ...] = (
            BeakerStreamConnectionClosedError,
            BeakerServerUnavailableError,
        ),
    ):
        """
        Use to make a service client method more robust by allowing retries.
        """

        def parametrize_decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            def retriable_method(*args, **kwargs) -> T:
                retries = 0
                while True:
                    try:
                        return func(*args, **kwargs)
                    except expected_errors as err:
                        if on_failure is not None:
                            on_failure()
                        self._log_and_wait(1, err, log_level=logging.DEBUG)
                    except recoverable_errors as err:
                        if retries < self.beaker.MAX_RETRIES:
                            if on_failure is not None:
                                on_failure()
                            self._log_and_wait(retries, err)
                            retries += 1
                        else:
                            raise

            return retriable_method

        return parametrize_decorator
