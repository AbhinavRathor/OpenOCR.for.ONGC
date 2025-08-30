from __future__ import annotations

import logging
import threading
import time
from contextlib import AbstractContextManager as ContextManager
from contextlib import contextmanager
from dataclasses import dataclass
from queue import Empty as QueueEmpty
from queue import SimpleQueue
from typing import Generator, Iterable, Literal, overload

import grpc
from google.protobuf.duration_pb2 import Duration
from google.protobuf.empty_pb2 import Empty
from google.protobuf.struct_pb2 import Struct
from google.protobuf.timestamp_pb2 import Timestamp

from . import beaker_pb2 as pb2
from ._service_client import (
    RpcBidirectionalStreamingMethod,
    RpcMethod,
    RpcStreamingMethod,
    ServiceClient,
)
from .exceptions import *
from .types import *
from .utils import pb2_to_dict


class QueueClient(ServiceClient):
    """
    Methods for interacting with Beaker `Queues <https://beaker-docs.apps.allenai.org/concept/queues.html>`_.
    Accessed via the :data:`Beaker.queue <beaker.Beaker.queue>` property.

    .. warning::
        Do not instantiate this class directly! The :class:`~beaker.Beaker` client will create
        one automatically which you can access through the corresponding property.
    """

    def get(self, queue: str) -> pb2.Queue:
        """
        :examples:

        >>> with Beaker.from_env() as beaker:
        ...     queue = beaker.queue.get(queue_id)

        :returns: A :class:`~beaker.types.BeakerQueue` protobuf object.

        :raises ~beaker.exceptions.BeakerQueueNotFound: If the queue doesn't exist.
        """
        return self.rpc_request(
            RpcMethod[pb2.GetQueueResponse](self.service.GetQueue),
            pb2.GetQueueRequest(queue_id=self.resolve_queue_id(queue)),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerQueueNotFound(queue)},
        ).queue

    def create(
        self,
        name: str | None = None,
        workspace: pb2.Workspace | None = None,
        input_schema: dict | None = {},
        output_schema: dict | None = {},
        batch_size: int | None = 1,
        max_claimed_entries: int | None = None,
        wait_timeout_ms: int | None = 0,
    ) -> pb2.Queue:
        """
        Create a new queue.

        :returns: A new :class:`~beaker.types.BeakerQueue` object.
        """
        wait_timeout = None
        if wait_timeout_ms is not None:
            wait_timeout = Duration()
            wait_timeout.FromMilliseconds(wait_timeout_ms)
        input_schema_struct = Struct()
        if input_schema is not None:
            input_schema_struct.update(input_schema)
        output_schema_struct = Struct()
        if output_schema is not None:
            output_schema_struct.update(output_schema)
        return self.rpc_request(
            RpcMethod[pb2.CreateQueueResponse](self.service.CreateQueue),
            pb2.CreateQueueRequest(
                workspace_id=self.resolve_workspace_id(workspace),
                name=name,
                input_schema=input_schema_struct,
                output_schema=output_schema_struct,
                batch_size=batch_size,
                max_claimed_entries=max_claimed_entries
                if max_claimed_entries is not None
                else batch_size,
                wait_timeout=wait_timeout,
            ),
        ).queue

    def delete(
        self,
        *queues: pb2.Queue,
    ):
        """
        Delete queues.
        """
        self.rpc_request(
            RpcMethod[pb2.DeleteQueuesResponse](self.service.DeleteQueues),
            pb2.DeleteQueuesRequest(queue_ids=[self.resolve_queue_id(q) for q in queues]),
        )

    def create_worker(self, queue: pb2.Queue) -> pb2.QueueWorker:
        """
        Create a new queue worker.

        :returns: A new :class:`~beaker.types.BeakerQueueWorker` object.
        """
        return self.rpc_request(
            RpcMethod[pb2.CreateQueueWorkerResponse](self.service.CreateQueueWorker),
            pb2.CreateQueueWorkerRequest(queue_id=queue.id),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerQueueNotFound(queue.id)},
        ).queue_worker

    def list_workers(self, queue: pb2.Queue, limit: int | None = None) -> Iterable[pb2.QueueWorker]:
        """
        List queue workers.

        :returns: An iterator over :class:`~beaker.types.BeakerQueueWorker` objects.
        """
        if limit is not None and limit <= 0:
            raise ValueError("'limit' must be a positive integer")

        count = 0
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListQueueWorkersResponse](self.service.ListQueueWorkers),
            pb2.ListQueueWorkersRequest(
                options=pb2.ListQueueWorkersRequest.Opts(
                    queue_id=queue.id,
                    page_size=self.MAX_PAGE_SIZE
                    if limit is None
                    else min(self.MAX_PAGE_SIZE, limit),
                )
            ),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerQueueNotFound(queue.id)},
        ):
            for worker in response.queue_workers:
                count += 1
                yield worker
                if limit is not None and count >= limit:
                    return

    def get_entry(self, entry_id: str) -> pb2.QueueEntry:
        """
        Get a queue entry object.

        :returns: A :class:`~beaker.types.BeakerQueueEntry` object.

        :raises ~beaker.exceptions.BeakerQueueEntryNotFound: If the entry doesn't exist or has expired.
        """
        return self.rpc_request(
            RpcMethod[pb2.GetQueueEntryResponse](self.service.GetQueueEntry),
            pb2.GetQueueEntryRequest(queue_entry_id=entry_id),
            exceptions_for_status={
                grpc.StatusCode.NOT_FOUND: BeakerQueueEntryNotFound(
                    f"queue entry '{entry_id}' not found or expired"
                )
            },
        ).queue_entry

    def create_entry(
        self,
        queue: pb2.Queue,
        *,
        input: dict | None = {},
        expires_in_sec: int = 3600 * 24,
        block: bool = True,
    ) -> Iterable[pb2.CreateQueueEntryResponse]:
        """
        Submit an entry to a queue and stream response events as they happen.

        .. important::
            This method will block until the entry has been finalized. If you expect the entry
            will take a while to process, you should use :meth:`create_entry_async()` instead
            and periodically poll the entry status with :meth:`get_entry()`.

        :param input: The input data.
        :param expires_in_sec: Time until the entry expires (in seconds). Defaults to 24 hours.
        :param block: If ``True`` (the default), this method will block until new responses become
            available and continue streaming until the entry is finalized. If ``False`` this
            method will only yield the ``pending_entry`` response and then return.
        """
        expiry = Timestamp()
        expiry.GetCurrentTime()
        expiry.FromSeconds(expiry.seconds + expires_in_sec)

        input_struct = Struct()
        if input is not None:
            input_struct.update(input)

        request = pb2.CreateQueueEntryRequest(
            queue_id=self.resolve_queue_id(queue),
            input=input_struct,
            expiry=expiry,
            # NOTE: 'async' is a reserved keyword in Python so we have to do this.
            **({} if block else {"async": True}),
        )

        yield from self.rpc_streaming_request(
            RpcStreamingMethod[pb2.CreateQueueEntryResponse](self.service.CreateQueueEntry),
            request,
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerQueueNotFound(queue.id)},
        )

    def create_entry_async(
        self,
        queue: pb2.Queue,
        *,
        input: dict | None = {},
        expires_in_sec: int = 3600 * 24,
    ) -> pb2.QueueEntry:
        """
        A convenience wrapper for :meth:`create_entry()` with ``block=False``. Returns the created
        entry right away.

        :returns: A new :class:`~beaker.types.BeakerQueueEntry` object.
        """
        status_count = 0
        for status in self.create_entry(
            queue, input=input, expires_in_sec=expires_in_sec, block=False
        ):
            status_count += 1
            if status.HasField("pending_entry"):
                return status.pending_entry
        raise BeakerCreateQueueEntryFailedError(
            f"Failed to create queue entry (no 'pending_entry' status was produced out of {status_count} statuses)"
        )

    def list_entries(self, queue: pb2.Queue, limit: int | None = None) -> Iterable[pb2.QueueEntry]:
        """
        List entries within a queue.

        :returns: An iterator over :class:`~beaker.types.BeakerQueueEntry` objects.
        """
        if limit is not None and limit <= 0:
            raise ValueError("'limit' must be a positive integer")

        count = 0
        Opts = pb2.ListQueueEntriesRequest.Opts
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListQueueEntriesResponse](self.service.ListQueueEntries),
            pb2.ListQueueEntriesRequest(
                options=Opts(
                    queue_id=queue.id,
                    page_size=self.MAX_PAGE_SIZE
                    if limit is None
                    else min(self.MAX_PAGE_SIZE, limit),
                )
            ),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerQueueNotFound(queue.id)},
        ):
            for entry in response.entries:
                count += 1
                yield entry
                if limit is not None and count >= limit:
                    return

    def worker_channel(
        self,
        queue: pb2.Queue,
        worker: pb2.QueueWorker,
    ) -> ContextManager[tuple[BeakerEntrySender, BeakerEntryReceiver]]:
        """
        A context manager for opening a bidirectional worker channel for consuming and responding to entries.
        The channel returned is a tuple of a :class:`BeakerEntrySender` and a :class:`BeakerEntryReceiver`,
        respectively.

        Example:

        >>> with beaker.queue.worker_channel(queue, worker) as (tx, rx):
        ...     for batch in rx.recv(max_batches=2, time_limit=10.0):
        ...         for entry_id, entry_input in batch:
        ...             tx.send(entry_id, output=entry_input)
        ...             tx.send(entry_id, done=True)

        """
        # NOTE: the extra indirection here is just to make the type hints on the public method
        # more concrete/clear.
        return self._worker_channel(queue, worker)

    @contextmanager
    def _worker_channel(
        self,
        queue: pb2.Queue,
        worker: pb2.QueueWorker,
    ) -> Generator[tuple[BeakerEntrySender, BeakerEntryReceiver], None, None]:
        tx: SimpleQueue[pb2.ProcessQueueEntriesRequest | None] = SimpleQueue()
        rx: SimpleQueue[list[pb2.QueueWorkerInput] | None] = SimpleQueue()
        done_event = threading.Event()
        error_event = threading.Event()
        thread = threading.Thread(
            target=self._process_queue_entries,
            args=(worker, tx, rx, done_event, error_event),
            name=f"beaker-queue-worker-{worker.id}",
        )
        thread.start()

        try:
            yield BeakerEntrySender(
                queue=queue,
                worker=worker,
                tx=tx,
            ), BeakerEntryReceiver(
                queue=queue,
                worker=worker,
                rx=rx,
                error=error_event,
                logger=self.logger,
            )
            if error_event.is_set():
                raise BeakerWorkerThreadError("channel thread died unexpectedly")
        finally:
            self.logger.debug(
                f"Closing down {self.__class__.__name__} queues and worker threads..."
            )
            tx.put(None)
            done_event.set()
            thread.join()

    def _process_queue_entries(
        self,
        worker: pb2.QueueWorker,
        tx: SimpleQueue[pb2.ProcessQueueEntriesRequest | None],
        rx: SimpleQueue[list[pb2.QueueWorkerInput] | None],
        done: threading.Event,
        error: threading.Event,
    ):
        # NOTE (epwalsh): For reasons I don't fully understand we need to be very careful
        # when retrying these streaming requests to ensure that the `request_iter`
        # generator function (defined below) from the failed request (that we're about to retry)
        # gets exhausted before we restart the request with another `request_iter`.
        # Otherwise we end up in a bad state where we stop sending or receiving new streaming messages.
        #
        # Hence these extra bookkeeping flags:
        #
        # We set `iter_done` to `True` within the `request_iter` function when it gets exhausted
        # in order to signal to the output while-loop that we can safely recreate a new `request_iter` function.
        iter_done = True
        # We set `iter_canceled` to `True` in the outer while-loop below each time we intercept a retriable
        # error in order to signal to the `request_iter` function that it should complete early.
        iter_canceled = False

        retries = 0
        while not done.is_set():
            try:
                if not iter_done:
                    self.logger.debug("Waiting for previous entry requests iterator to exit...")
                    while not iter_done:
                        time.sleep(0.5)

                iter_canceled = False
                iter_done = False

                def request_iter() -> Generator[pb2.ProcessQueueEntriesRequest, None, None]:
                    nonlocal iter_done

                    yield pb2.ProcessQueueEntriesRequest(
                        init=pb2.ProcessQueueEntriesRequest.Init(worker_id=worker.id)
                    )
                    self.logger.debug("Waiting for new entry process requests from thread")

                    while not iter_canceled:
                        try:
                            request = tx.get(
                                block=True,
                                timeout=0.5,
                            )
                        except QueueEmpty:
                            continue

                        if request is None:
                            break

                        self.logger.debug("Sending new entry process request from thread")
                        yield request

                    self.logger.debug("Exhausted entry process requests from thread")
                    iter_done = True

                for response in self.rpc_bidirectional_streaming_request(
                    RpcBidirectionalStreamingMethod[pb2.ProcessQueueEntriesResponse](
                        self.service.ProcessQueueEntries
                    ),
                    request_iter(),
                    exceptions_for_status={
                        grpc.StatusCode.NOT_FOUND: BeakerQueueWorkerNotFound(worker.id)
                    },
                ):
                    batch_inputs = list(response.batch.worker_input)
                    self.logger.debug("Received new entry batch from thread")
                    rx.put(batch_inputs)

                    if done.is_set():
                        break

                rx.put(None)
                return
            except (BeakerStreamConnectionClosedError, BeakerServerUnavailableError) as err:
                # These errors are expected, see https://github.com/allenai/beaker/issues/6532
                iter_canceled = True
                self._log_and_wait(1, err, log_level=logging.DEBUG)
            except BeakerServerError as err:
                iter_canceled = True
                if retries < self.beaker.MAX_RETRIES:
                    self._log_and_wait(retries, err)
                    retries += 1
                else:
                    error.set()
                    rx.put(None)
                    raise
            except BaseException:
                iter_canceled = True
                error.set()
                rx.put(None)
                raise

    def list(
        self,
        *,
        org: pb2.Organization | None = None,
        workspace: pb2.Workspace | None = None,
        sort_order: BeakerSortOrder | None = BeakerSortOrder.descending,
        sort_field: Literal["created"] = "created",
        limit: int | None = None,
    ) -> Iterable[pb2.Queue]:
        """
        List queues.

        :returns: An iterator over :class:`~beaker.types.BeakerQueue` objects.
        """
        if limit is not None and limit <= 0:
            raise ValueError("'limit' must be a positive integer")

        count = 0
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListQueuesResponse](self.service.ListQueues),
            pb2.ListQueuesRequest(
                options=pb2.ListQueuesRequest.Opts(
                    sort_clause=pb2.ListQueuesRequest.Opts.SortClause(
                        sort_order=None if sort_order is None else sort_order.as_pb2(),
                        created={} if sort_field == "created" else None,
                    ),
                    organization_id=self.resolve_org_id(org),
                    workspace_id=None
                    if workspace is None
                    else self.resolve_workspace_id(workspace),
                    page_size=self.MAX_PAGE_SIZE
                    if limit is None
                    else min(self.MAX_PAGE_SIZE, limit),
                ),
            ),
        ):
            for queue in response.queues:
                count += 1
                yield queue
                if limit is not None and count >= limit:
                    return


@dataclass
class BeakerEntrySender:
    """
    Queue entry sender. Use this to respond to queue entries consumed by a worker.

    .. warning::
        Do not instantiated this class directly! Use :meth:`~QueueClient.worker_channel()` to create one.
    """

    queue: pb2.Queue
    worker: pb2.QueueWorker
    tx: SimpleQueue[pb2.ProcessQueueEntriesRequest | None]

    @overload
    def send(
        self,
        entry_id: str,
        *,
        output: dict,
    ):
        ...

    @overload
    def send(
        self,
        entry_id: str,
        *,
        rejection: str,
    ):
        ...

    @overload
    def send(
        self,
        entry_id: str,
        *,
        done: Literal[True],
    ):
        ...

    def send(
        self,
        entry_id: str,
        *,
        output: dict | None = None,
        rejection: str | None = None,
        done: bool = False,
    ):
        """
        Send output to an entry, reject, or mark the entry as done.

        .. important::
            Only one of ``output``, ``rejection``, or ``done`` can be specified at a time, and you
            should eventually set ``done=True`` (or ``rejection=...``) on every entry.

        :param entry_id: The ID of the entry.
        :param output: Worker response data for the entry. Mutually exclusive with the other keyword args.
        :param rejection: Marks the entry as rejected. This should be a human-readable reason for rejecting the entry.
            Mutually exclusive with the other keyword args.
        :param done: Mark the entry as done. Mutually exclusive with the other keyword args.
        """
        if sum([(done is True), (output is not None), (rejection is not None)]) != 1:
            raise ValueError("exactly one of `output`, `rejection`, or `done` can be specified")

        request = pb2.ProcessQueueEntriesRequest(
            worker_output=pb2.QueueWorkerOutput(
                metadata=pb2.QueueEntryMetadata(
                    queue_id=self.queue.id, entry_id=entry_id, worker_id=self.worker.id
                ),
                output=output,
                rejection=rejection,
                done=Empty() if done else None,
            ),
        )

        if output is not None:
            self.tx.put(request)
        elif rejection is not None:
            self.tx.put(request)
        elif done:
            self.tx.put(request)


@dataclass
class BeakerEntryReceiver:
    """
    Queue entry receiver. Use this to consume queue entries as a worker.

    .. warning::
        Do not instantiated this class directly! Use :meth:`~QueueClient.worker_channel()` to create one.
    """

    queue: pb2.Queue
    worker: pb2.QueueWorker
    rx: SimpleQueue[list[pb2.QueueWorkerInput] | None]
    error: threading.Event
    logger: logging.Logger

    def recv(
        self,
        *,
        max_batches: int | None = None,
        time_limit: float | None = None,
    ) -> Generator[list[tuple[str, dict | None]], None, None]:
        """
        Receive batches of queue entries as they become available. Returns a generator of lists of
        tuples in the form ``(entry_id: str, input_data: dict | None)``.

        This will wait indefinitely on more batches unless ``max_batches`` or ``time_limit`` is set.

        :param max_batches: Stop receiving after this many batches.
        :param time_limit: Stop receiving after this many seconds.
        """
        batches_received = 0
        start_time = time.monotonic()

        def elapsed_time() -> float:
            return time.monotonic() - start_time

        def time_left() -> float | None:
            return None if time_limit is None else max(time_limit - elapsed_time(), 0.0)

        def wait_timeout() -> float:
            if (seconds_remaining := time_left()) is not None:
                return min(seconds_remaining, 1.0)
            else:
                return 1.0

        def should_wait() -> bool:
            if self.error.is_set():
                return False
            elif max_batches is not None and batches_received >= max_batches:
                self.logger.debug(
                    f"{self.__class__.__name__}.receive() finished due to max batches"
                )
                return False
            elif (seconds_remaining := time_left()) is not None and seconds_remaining <= 0:
                self.logger.debug(f"{self.__class__.__name__}.receive() finished due to time limit")
                return False
            else:
                return True

        while should_wait():
            try:
                batch = self.rx.get(
                    block=True,
                    timeout=wait_timeout(),
                )
            except QueueEmpty:
                continue

            if batch is not None:
                batches_received += 1
                entries = []
                for worker_input in batch:
                    entry_id = worker_input.metadata.entry_id
                    entry_input = (
                        None
                        if not worker_input.HasField("input")
                        else pb2_to_dict(worker_input.input)
                    )
                    entries.append((entry_id, entry_input))
                yield entries
            else:
                break

        if self.error.is_set():
            raise BeakerWorkerThreadError("channel thread died unexpectedly")
