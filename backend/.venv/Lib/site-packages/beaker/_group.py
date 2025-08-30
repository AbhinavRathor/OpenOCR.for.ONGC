from typing import Iterable, Literal

import grpc

from . import beaker_pb2 as pb2
from ._service_client import RpcMethod, ServiceClient
from .exceptions import *
from .types import *


class GroupClient(ServiceClient):
    """
    Methods for interacting with Beaker `Groups <https://beaker-docs.apps.allenai.org/concept/groups.html>`_.
    Accessed via the :data:`Beaker.group <beaker.Beaker.group>` property.

    .. warning::
        Do not instantiate this class directly! The :class:`~beaker.Beaker` client will create
        one automatically which you can access through the corresponding property.
    """

    def get(self, group_id: str) -> pb2.Group:
        """
        :examples:

        >>> with Beaker.from_env() as beaker:
        ...     group = beaker.group.get(group_id)

        :returns: A :class:`~beaker.types.BeakerGroup` protobuf object.

        :raises ~beaker.exceptions.BeakerGroupNotFound: If the group doesn't exist.
        """
        return self.rpc_request(
            RpcMethod[pb2.GetGroupResponse](self.service.GetGroup),
            pb2.GetGroupRequest(group_id=group_id),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerGroupNotFound(group_id)},
        ).group

    def create(
        self,
        name: str,
        *,
        workspace: pb2.Workspace | None = None,
        description: str | None = None,
        experiment_ids: list[str] | None = None,
    ) -> pb2.Group:
        """
        Create a new group.

        :returns: The new :class:`~beaker.types.BeakerGroup` object.
        """
        return self.rpc_request(
            RpcMethod[pb2.CreateGroupResponse](self.service.CreateGroup),
            pb2.CreateGroupRequest(
                workspace_id=self.resolve_workspace_id(workspace),
                name=name,
                description=description,
                experiment_ids=experiment_ids,
            ),
        ).group

    def update(
        self,
        group: pb2.Group,
        *,
        name: str | None = None,
        description: str | None = None,
        add_experiment_ids: list[str] | None = None,
        archived: bool | None = None,
    ) -> pb2.Group:
        return self.rpc_request(
            RpcMethod[pb2.UpdateGroupResponse](self.service.UpdateGroup),
            pb2.UpdateGroupRequest(
                group_id=self.resolve_group_id(group),
                name=name,
                description=description,
                add_experiment_ids=add_experiment_ids,
                archived=archived,  # type: ignore
            ),
        ).group

    def delete(
        self,
        *groups: pb2.Group,
    ):
        self.rpc_request(
            RpcMethod[pb2.DeleteGroupsResponse](self.service.DeleteGroups),
            pb2.DeleteGroupsRequest(group_ids=[self.resolve_group_id(group) for group in groups]),
        )

    def export_metrics(self, group: pb2.Group) -> str:
        return self.rpc_request(
            RpcMethod[pb2.GetGroupMetricsExportResponse](self.service.GetGroupMetricsExport),
            pb2.GetGroupMetricsExportRequest(group_id=self.resolve_group_id(group)),
        ).csv_data

    def list_task_metrics(self, group: pb2.Group) -> Iterable[pb2.TaskMetrics]:
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListGroupTaskMetricsResponse](self.service.ListGroupTaskMetrics),
            pb2.ListGroupTaskMetricsRequest(
                options=pb2.ListGroupTaskMetricsRequest.Opts(
                    group_id=self.resolve_group_id(group), page_size=self.MAX_PAGE_SIZE
                )
            ),
        ):
            yield from response.task_metrics

    def list(
        self,
        *,
        org: pb2.Organization | None = None,
        workspace: pb2.Workspace | None = None,
        name_or_description: str | None = None,
        sort_order: BeakerSortOrder | None = None,
        sort_field: Literal["created", "name", "modified"] = "name",
        limit: int | None = None,
    ) -> Iterable[pb2.Group]:
        if limit is not None and limit <= 0:
            raise ValueError("'limit' must be a positive integer")

        count = 0
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListGroupsResponse](self.service.ListGroups),
            pb2.ListGroupsRequest(
                options=pb2.ListGroupsRequest.Opts(
                    sort_clause=pb2.ListGroupsRequest.Opts.SortClause(
                        sort_order=None if sort_order is None else sort_order.as_pb2(),
                        created={} if sort_field == "created" else None,
                        name={} if sort_field == "name" else None,
                        modified={} if sort_field == "modified" else None,
                    ),
                    organization_id=self.resolve_org_id(org),
                    workspace_id=None
                    if workspace is None
                    else self.resolve_workspace_id(workspace),
                    name_or_description_substring=name_or_description,
                    page_size=self.MAX_PAGE_SIZE
                    if limit is None
                    else min(self.MAX_PAGE_SIZE, limit),
                ),
            ),
        ):
            for group in response.groups:
                count += 1
                yield group
                if limit is not None and count >= limit:
                    return

    def url(self, group: pb2.Group) -> str:
        group_id = self.resolve_group_id(group)
        return f"{self.config.agent_address}/gr/{self._url_quote(group_id)}"
