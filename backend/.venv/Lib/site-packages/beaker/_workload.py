from datetime import datetime
from typing import Iterable, Literal

import grpc

from . import beaker_pb2 as pb2
from ._service_client import RpcMethod, ServiceClient
from .exceptions import *
from .types import *


class WorkloadClient(ServiceClient):
    """
    Methods for interacting with Beaker Workloads.
    Accessed via the :data:`Beaker.workload <beaker.Beaker.workload>` property.

    .. warning::
        Do not instantiate this class directly! The :class:`~beaker.Beaker` client will create
        one automatically which you can access through the corresponding property.
    """

    def get(self, workload: str) -> pb2.Workload:
        """
        :examples:

        >>> with Beaker.from_env() as beaker:
        ...     workload = beaker.workload.get(workload_id)

        :returns: A :class:`~beaker.types.BeakerWorkload` protobuf object.

        :raises ~beaker.exceptions.BeakerWorkloadNotFound: If the workload doesn't exist.
        """
        return self.rpc_request(
            RpcMethod[pb2.GetWorkloadResponse](self.service.GetWorkload),
            pb2.GetWorkloadRequest(workload_id=self.resolve_workload_id(workload)),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerWorkloadNotFound(workload)},
        ).workload

    def is_experiment(self, workload: pb2.Workload) -> bool:
        """
        Returns ``True`` if an workload is an experiment-type workload.
        """
        return workload.HasField("experiment")

    def is_environment(self, workload: pb2.Workload) -> bool:
        """
        Returns ``True`` if an workload is an environment-type (session) workload.
        """
        return workload.HasField("environment")

    def update(
        self, workload: pb2.Workload, *, name: str | None = None, description: str | None = None
    ) -> pb2.Workload:
        """
        Update fields of a workload.

        :returns: The updated :class:`~beaker.types.BeakerWorkload` object.
        """
        return self.rpc_request(
            RpcMethod[pb2.UpdateWorkloadResponse](self.service.UpdateWorkload),
            pb2.UpdateWorkloadRequest(
                workload_id=self.resolve_workload_id(workload), name=name, description=description
            ),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerWorkloadNotFound(workload)},
        ).workload

    def cancel(self, *workloads: pb2.Workload) -> Iterable[str]:
        """
        Cancel a running workload.
        """
        return self.rpc_request(
            RpcMethod[pb2.CancelWorkloadsResponse](self.service.CancelWorkloads),
            pb2.CancelWorkloadsRequest(
                workload_ids=[self.resolve_workload_id(workload) for workload in workloads]
            ),
        ).workload_ids

    def delete(self, *workloads: pb2.Workload):
        """
        Delete workloads.
        """
        self.rpc_request(
            RpcMethod[pb2.DeleteWorkloadsResponse](self.service.DeleteWorkloads),
            pb2.DeleteWorkloadsRequest(
                workload_ids=[self.resolve_workload_id(workload) for workload in workloads]
            ),
        )

    def _resolve_task(
        self, workload: pb2.Workload, task: pb2.Task | None = None
    ) -> pb2.Task | None:
        if task is None:
            if len(workload.experiment.tasks) == 0:
                return None
            else:
                return workload.experiment.tasks[0]

        # Make sure task is actually part of workload.
        all_tasks = [t.id for t in workload.experiment.tasks]
        if task.id not in all_tasks:
            raise ValueError(
                f"invalid task '{task.id}', task is not part of workload '{workload.experiment.id}' "
                f"with tasks {all_tasks}"
            )
        return task

    def get_latest_job(
        self, workload: pb2.Workload, *, task: pb2.Task | None = None, finalized: bool | None = None
    ) -> pb2.Job | None:
        """
        Get the latest job of an experiment-type workload.

        :param task: Filter by a specific task.
        :param finalized: Filter by finalized status.

        :returns: The latest :class:`~beaker.types.BeakerJob` object or ``None``, if one hasn't
            been created yet.

        :raises ValueError: If the workload is not an experiment.
        """
        env: pb2.Environment | None = None
        if self.is_experiment(workload):
            task = self._resolve_task(workload, task=task)
            if task is None:
                raise ValueError(f"Workload does not have any tasks, so no jobs: {workload}")
        elif self.is_environment(workload):
            if task is not None:
                raise ValueError(f"'task' option is invalid for environment workload: {workload}")
            env = workload.environment
        else:
            raise ValueError(f"Could not determine workload type: {workload}")

        jobs = list(
            self.beaker.job.list(
                task=task,
                environment=env,
                sort_field="created",
                sort_order=BeakerSortOrder.descending,
                limit=1,
                finalized=finalized,
            )
        )
        if not jobs:
            return None

        return jobs[0]

    def get_results(
        self, workload: pb2.Workload, *, task: pb2.Task | None = None
    ) -> pb2.Dataset | None:
        """
        Get the results :class:`~beaker.types.BeakerDataset` from a workload.
        """
        job = self.get_latest_job(workload, task=task)
        if job is None:
            return None
        else:
            return self.beaker.job.get_results(job)

    def list(
        self,
        *,
        org: pb2.Organization | None = None,
        author: pb2.User | None = None,
        workspace: pb2.Workspace | None = None,
        created_before: datetime | None = None,
        created_after: datetime | None = None,
        finalized: bool | None = None,
        workload_type: BeakerWorkloadType | None = None,
        statuses: Iterable[BeakerWorkloadStatus] | None = None,
        name_or_description: str | None = None,
        sort_order: BeakerSortOrder | None = None,
        sort_field: Literal["created"] = "created",
        limit: int | None = None,
    ) -> Iterable[pb2.Workload]:
        """
        List workloads.

        :returns: An iterator over :class:`~beaker.types.BeakerWorkload` objects.
        """
        Opts = pb2.ListWorkloadsRequest.Opts

        if limit is not None and limit <= 0:
            raise ValueError("'limit' must be a positive integer")

        count = 0
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListWorkloadsResponse](self.service.ListWorkloads),
            pb2.ListWorkloadsRequest(
                options=Opts(
                    sort_clause=Opts.SortClause(
                        sort_order=None if sort_order is None else sort_order.as_pb2(),
                        created={} if sort_field == "created" else None,
                    ),
                    created_before=created_before,  # type: ignore[arg-type]
                    created_after=created_after,  # type: ignore[arg-type]
                    job_finalized=finalized,  # type: ignore[arg-type]
                    workload_type=None if workload_type is None else workload_type.as_pb2(),
                    statuses=None if statuses is None else [status.as_pb2() for status in statuses],
                    name_or_description_substring=name_or_description,
                    organization_id=self.resolve_org_id(org),
                    author_id=None if author is None else self.resolve_user_id(author),
                    workspace_id=None
                    if workspace is None
                    else self.resolve_workspace_id(workspace),
                    page_size=self.MAX_PAGE_SIZE
                    if limit is None
                    else min(self.MAX_PAGE_SIZE, limit),
                )
            ),
        ):
            for workload in response.workloads:
                count += 1
                yield workload
                if limit is not None and count >= limit:
                    return

    def url(self, workload: pb2.Workload) -> str:
        """
        Get the URL to a workload on the Beaker dashboard.
        """
        return (
            f"{self.config.agent_address}/ex/{self._url_quote(self.resolve_workload_id(workload))}"
        )
