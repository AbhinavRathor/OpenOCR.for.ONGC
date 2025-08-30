import logging
from datetime import datetime
from typing import Iterable, Literal

import grpc

from . import beaker_pb2 as pb2
from ._service_client import RpcMethod, RpcStreamingMethod, ServiceClient
from .exceptions import *
from .types import *


class JobClient(ServiceClient):
    """
    Methods for interacting with Beaker Jobs.
    Accessed via the :data:`Beaker.job <beaker.Beaker.job>` property.

    .. warning::
        Do not instantiate this class directly! The :class:`~beaker.Beaker` client will create
        one automatically which you can access through the corresponding property.
    """

    def get(self, job_id: str) -> pb2.Job:
        """
        :examples:

        >>> with Beaker.from_env() as beaker:
        ...     job = beaker.job.get(job_id)

        :returns: A :class:`~beaker.types.BeakerJob` protobuf object.

        :raises ~beaker.exceptions.BeakerJobNotFound: If the job doesn't exist.
        """
        return self.rpc_request(
            RpcMethod[pb2.GetJobResponse](self.service.GetJob),
            pb2.GetJobRequest(job_id=job_id),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerJobNotFound(job_id)},
        ).job

    def get_results(self, job: pb2.Job) -> pb2.Dataset | None:
        """
        :returns: A :class:`~beaker.types.BeakerDataset` protobuf object.
        """
        if job.assignment_details.HasField("result_dataset_id"):
            return self.beaker.dataset.get(job.assignment_details.result_dataset_id)
        else:
            return None

    def logs(
        self,
        job: pb2.Job,
        *,
        tail_lines: int | None = None,
        follow: bool | None = None,
        since: datetime | None = None,
    ) -> Iterable[pb2.JobLog]:
        """
        :returns: An iterator over :class:`~beaker.types.BeakerJobLog` protobuf objects.
        """
        request = pb2.StreamJobLogsRequest(
            job_id=job.id,
            tail_lines=tail_lines,
            follow=follow,  # type: ignore
            since=since,  # type: ignore
        )

        retries = 0
        last_log_timestamp = None

        def update_request():
            # Update request to restart streaming from the last log message received.
            if last_log_timestamp is not None:
                request.MergeFrom(pb2.StreamJobLogsRequest(since=last_log_timestamp))
                request.since.nanos += 1  # NOTE: 'since' timestamp is now a clone of 'last_log_timestamp', so modifying in-place is okay.
                request.ClearField("tail_lines")

        while True:
            try:
                for job_log in self.rpc_streaming_request(
                    RpcStreamingMethod[pb2.JobLog](self.service.StreamJobLogs),
                    request,
                    exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerJobNotFound(job)},
                ):
                    retries = 0  # reset because we've successfully received a new log
                    last_log_timestamp = job_log.timestamp
                    yield job_log

                # NOTE: Work-around for #6602
                # If we're following the job, continue making streaming requests until the job is officially finalized.
                if follow and not self.get(job.id).status.HasField("finalized"):
                    update_request()
                    continue

                return
            except (BeakerStreamConnectionClosedError, BeakerServerUnavailableError) as err:
                # These errors are expected, see https://github.com/allenai/beaker/issues/6532
                self._log_and_wait(1, err, log_level=logging.DEBUG)
                update_request()
            except BeakerServerError as err:
                if retries < self.beaker.MAX_RETRIES:
                    self._log_and_wait(retries, err)
                    retries += 1
                    update_request()
                else:
                    raise

    def list_summarized_events(
        self,
        job: pb2.Job,
        *,
        sort_order: BeakerSortOrder | None = None,
        sort_field: Literal["latest_occurrence"] = "latest_occurrence",
        limit: int | None = None,
    ) -> Iterable[pb2.SummarizedJobEvent]:
        """
        :returns: An iterator over :class:`~beaker.types.BeakerSummarizedJobEvent` protobuf objects.
        """
        if limit is not None and limit <= 0:
            raise ValueError("'limit' must be a positive integer")

        count = 0
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListSummarizedJobEventsResponse](self.service.ListSummarizedJobEvents),
            pb2.ListSummarizedJobEventsRequest(
                options=pb2.ListSummarizedJobEventsRequest.Opts(
                    sort_clause=pb2.ListSummarizedJobEventsRequest.Opts.SortClause(
                        sort_order=None if sort_order is None else sort_order.as_pb2(),
                        latest_occurrence={} if sort_field == "latest_occurrence" else None,
                    ),
                    job_id=job.id,
                    page_size=self.MAX_PAGE_SIZE
                    if limit is None
                    else min(self.MAX_PAGE_SIZE, limit),
                )
            ),
        ):
            for event in response.summarized_job_events:
                count += 1
                yield event
                if limit is not None and count >= limit:
                    return

    def list(
        self,
        *,
        org: pb2.Organization | None = None,
        task: pb2.Task | None = None,
        environment: pb2.Environment | None = None,
        finalized: bool | None = None,
        elegible_for_cluster: pb2.Cluster | None = None,
        scheduled_on_node: pb2.Node | None = None,
        scheduled_on_cluster: pb2.Cluster | None = None,
        scheduled: bool | None = None,
        sort_order: BeakerSortOrder = BeakerSortOrder.descending,
        sort_field: Literal["created", "cluster_job_queue"] = "created",
        limit: int | None = None,
    ) -> Iterable[pb2.Job]:
        """
        :returns: An iterator over :class:`~beaker.types.BeakerJob` protobuf objects.
        """
        if limit is not None and limit <= 0:
            raise ValueError("'limit' must be a positive integer")

        count = 0
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListJobsResponse](self.service.ListJobs),
            pb2.ListJobsRequest(
                options=pb2.ListJobsRequest.Opts(
                    sort_clause=pb2.ListJobsRequest.Opts.SortClause(
                        sort_order=None if sort_order is None else sort_order.as_pb2(),
                        created={} if sort_field == "created" else None,
                        cluster_job_queue={} if sort_field == "cluster_job_queue" else None,
                    ),
                    organization_id=self.resolve_org_id(org),
                    task_id=None if task is None else task.id,
                    environment_id=None if environment is None else environment.id,
                    finalized=finalized,  # type: ignore
                    eligible_for_cluster_id=None
                    if elegible_for_cluster is None
                    else elegible_for_cluster.id,
                    scheduled_on_node_id=None
                    if scheduled_on_node is None
                    else scheduled_on_node.id,
                    scheduled_on_cluster_id=None
                    if scheduled_on_cluster is None
                    else scheduled_on_cluster.id,
                    scheduled=scheduled,  # type: ignore
                    page_size=self.MAX_PAGE_SIZE
                    if limit is None
                    else min(self.MAX_PAGE_SIZE, limit),
                )
            ),
        ):
            for job in response.jobs:
                count += 1
                yield job
                if limit is not None and count >= limit:
                    return

    def url(self, job: pb2.Job) -> str:
        """
        Get the URL to the job on the Beaker dashboard.
        """
        job_id = job.id
        return f"{self.config.agent_address}/job/{self._url_quote(job_id)}"
