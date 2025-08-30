from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from functools import cached_property
from typing import ClassVar, Generator, TypeVar

import grpc
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import beaker_pb2_grpc
from ._cluster import ClusterClient
from ._dataset import DatasetClient
from ._experiment import ExperimentClient
from ._group import GroupClient
from ._image import ImageClient
from ._job import JobClient
from ._node import NodeClient
from ._organization import OrganizationClient
from ._queue import QueueClient
from ._secret import SecretClient
from ._user import UserClient
from ._workload import WorkloadClient
from ._workspace import WorkspaceClient
from .config import Config, InternalConfig
from .exceptions import *
from .version import VERSION

__all__ = ["Beaker"]


_LATEST_VERSION_CHECKED = False
T = TypeVar("T")


class Beaker:
    """
    A client for interacting with `Beaker <https://beaker.org>`_. This should be used as a context
    manager to ensure connections are properly closed on exit.

    .. tip::
        Use :meth:`from_env()` to create a client instance.

    :param config: The Beaker :class:`Config`.
    :param check_for_upgrades: Automatically check that beaker-py is up-to-date. You'll see
        a warning if it isn't.
    :param user_agent: Override the "User-Agent" header used in requests to the Beaker server.
    """

    API_VERSION: ClassVar[str] = "v3"
    CLIENT_VERSION: ClassVar[str] = VERSION
    VERSION_CHECK_INTERVAL: ClassVar[int] = 12 * 3600  # 12 hours

    RPC_MAX_SEND_MESSAGE_LENGTH: ClassVar[int] = 64 * 1024 * 1024  # 64MiB

    RECOVERABLE_SERVER_ERROR_CODES: ClassVar[tuple[int, ...]] = (429, 500, 502, 503, 504)
    MAX_RETRIES: ClassVar[int] = 5
    BACKOFF_FACTOR: ClassVar[int] = 1
    BACKOFF_MAX: ClassVar[int] = 120
    TIMEOUT: ClassVar[float] = 5.0
    POOL_MAXSIZE: ClassVar[int] = min(100, (os.cpu_count() or 16) * 6)

    logger = logging.getLogger("beaker")

    def __init__(
        self,
        config: Config,
        check_for_upgrades: bool = True,
        user_agent: str = f"beaker-py v{VERSION}",
    ):
        self.user_agent = user_agent
        self._config = config
        self._channel: grpc.Channel | None = None
        self._service: beaker_pb2_grpc.BeakerStub | None = None
        self._thread_local = threading.local()
        self._thread_local.http_session = None  # requests.Session not thread safe

        # See if there's a newer version, and if so, suggest that the user upgrades.
        if check_for_upgrades:
            self._check_for_upgrades()

    def _get_latest_version(self) -> str:
        response = requests.get(
            "https://pypi.org/simple/beaker-py",
            headers={"Accept": "application/vnd.pypi.simple.v1+json"},
            timeout=2,
        )
        response.raise_for_status()
        return response.json()["versions"][-1]

    def _check_for_upgrades(self, force: bool = False) -> Exception | bool | None:
        global _LATEST_VERSION_CHECKED

        if not force and _LATEST_VERSION_CHECKED:
            return None

        import warnings

        import packaging.version

        try:
            config = InternalConfig.load()
            if (
                not force
                and config is not None
                and config.version_checked is not None
                and (time.time() - config.version_checked <= self.VERSION_CHECK_INTERVAL)
            ):
                return None

            should_upgrade: bool | None = None
            latest_version = packaging.version.parse(self._get_latest_version())
            current_version = packaging.version.parse(self.CLIENT_VERSION)
            if latest_version > current_version and (
                not latest_version.is_prerelease or current_version.is_prerelease
            ):
                warnings.warn(
                    f"You're using beaker-py v{current_version}, "
                    f"but a newer version (v{latest_version}) is available.\n\n"
                    f"Please upgrade with `pip install --upgrade beaker-py`.",
                    UserWarning,
                )
                should_upgrade = True
            else:
                should_upgrade = False

            _LATEST_VERSION_CHECKED = True
            if config is not None:
                config.version_checked = time.time()
                config.save()

            return should_upgrade
        except Exception as e:
            return e

    @classmethod
    def from_env(
        cls,
        check_for_upgrades: bool = True,
        user_agent: str = f"beaker-py v{VERSION}",
        **overrides,
    ) -> Beaker:
        """
        Initialize client from a config file and/or environment variables.

        :examples:

        >>> with Beaker.from_env(default_workspace="ai2/my-workspace") as beaker:
        ...     print(beaker.user_name)

        :param check_for_upgrades: Automatically check that beaker-py is up-to-date. You'll see
            a warning if it isn't.
        :param user_agent: Override the "User-Agent" header used in requests to the Beaker server.
        :param overrides: Fields in the :class:`Config` to override.

        .. note::
            This will use the same config file that the Beaker command-line client
            creates and uses, which is usually located at ``$HOME/.beaker/config.yml``.

            If you haven't configured the command-line client, then you can alternately just
            set the environment variable ``BEAKER_TOKEN`` to your Beaker `user token <https://beaker.org/user>`_.

        """
        return cls(
            Config.from_env(**overrides),
            check_for_upgrades=check_for_upgrades,
            user_agent=user_agent,
        )

    @property
    def service(self) -> beaker_pb2_grpc.BeakerStub:
        if self._service is None:
            self._channel = grpc.secure_channel(
                self.config.rpc_address,
                grpc.ssl_channel_credentials(),
                options=[
                    ("grpc.max_send_message_length", self.RPC_MAX_SEND_MESSAGE_LENGTH),
                    #  ("grpc.keepalive_time_ms", 10_000),
                ],
            )
            self._service = beaker_pb2_grpc.BeakerStub(self._channel)
        return self._service

    @property
    def config(self) -> Config:
        """
        The client's :class:`Config`.
        """
        return self._config

    @cached_property
    def user_name(self) -> str:
        return self.user.get().name

    @cached_property
    def org_name(self) -> str:
        return self.organization.get().name

    @cached_property
    def organization(self) -> OrganizationClient:
        """
        Manage organizations.
        """
        return OrganizationClient(self)

    @cached_property
    def user(self) -> UserClient:
        """
        Manage users.
        """
        return UserClient(self)

    @cached_property
    def workspace(self) -> WorkspaceClient:
        """
        Manage workspaces.
        """
        return WorkspaceClient(self)

    @cached_property
    def cluster(self) -> ClusterClient:
        """
        Manage clusters.
        """
        return ClusterClient(self)

    @cached_property
    def node(self) -> NodeClient:
        """
        Manage nodes.
        """
        return NodeClient(self)

    @cached_property
    def dataset(self) -> DatasetClient:
        """
        Manage datasets.
        """
        return DatasetClient(self)

    @cached_property
    def image(self) -> ImageClient:
        """
        Manage images.
        """
        return ImageClient(self)

    @cached_property
    def job(self) -> JobClient:
        """
        Manage jobs.
        """
        return JobClient(self)

    @cached_property
    def experiment(self) -> ExperimentClient:
        """
        Manage experiments.
        """
        return ExperimentClient(self)

    @cached_property
    def workload(self) -> WorkloadClient:
        """
        Manage workloads.
        """
        return WorkloadClient(self)

    @cached_property
    def secret(self) -> SecretClient:
        """
        Manage secrets.
        """
        return SecretClient(self)

    @cached_property
    def group(self) -> GroupClient:
        """
        Manage groups.
        """
        return GroupClient(self)

    @cached_property
    def queue(self) -> QueueClient:
        """
        Manage queues.
        """
        return QueueClient(self)

    @contextmanager
    def http_session(self) -> Generator[requests.Session, None, None]:
        if (
            not hasattr(self._thread_local, "http_session")
            or self._thread_local.http_session is None
        ):
            self._thread_local.http_session = self._init_http_session()
            try:
                yield self._thread_local.http_session
            finally:
                self._thread_local.http_session.close()
                self._thread_local.http_session = None
        else:
            yield self._thread_local.http_session

    def _init_http_session(self):
        session = requests.Session()
        retries = Retry(
            total=self.MAX_RETRIES * 2,
            connect=self.MAX_RETRIES,
            status=self.MAX_RETRIES,
            backoff_factor=self.BACKOFF_FACTOR,
            status_forcelist=self.RECOVERABLE_SERVER_ERROR_CODES,
        )
        session.mount("https://", HTTPAdapter(max_retries=retries, pool_maxsize=self.POOL_MAXSIZE))
        return session

    def __enter__(self) -> "Beaker":
        if (
            not hasattr(self._thread_local, "http_session")
            or self._thread_local.http_session is None
        ):
            self._thread_local.http_session = self._init_http_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        del exc_type, exc_val, exc_tb
        self.close()
        return False

    def close(self):
        """
        Close down RPC channels and HTTP sessions. This will be called automatically when using
        the client as a context manager.
        """
        # Close RPC channel.
        if self._channel is not None:
            self._channel.close()
        self._channel = None
        self._service = None

        # Close HTTP session.
        if (
            hasattr(self._thread_local, "http_session")
            and self._thread_local.http_session is not None
        ):
            self._thread_local.http_session.close()
        self._thread_local.http_session = None

    def __del__(self):
        self.close()
