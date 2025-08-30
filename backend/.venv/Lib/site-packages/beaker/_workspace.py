from typing import Iterable, Literal

import grpc

from . import beaker_pb2 as pb2
from ._service_client import RpcMethod, ServiceClient
from .exceptions import *
from .types import *


class WorkspaceClient(ServiceClient):
    """
    Methods for interacting with Beaker `Workspaces <https://beaker-docs.apps.allenai.org/concept/workspaces.html>`_.
    Accessed via the :data:`Beaker.workspace <beaker.Beaker.workspace>` property.

    .. warning::
        Do not instantiate this class directly! The :class:`~beaker.Beaker` client will create
        one automatically which you can access through the corresponding property.
    """

    def get(self, workspace: str | None = None) -> pb2.Workspace:
        """
        :examples:

        >>> with Beaker.from_env() as beaker:
        ...     workspace = beaker.workspace.get(workspace_name)

        :returns: A :class:`~beaker.types.BeakerWorkspace` protobuf object.

        :raises: :class:`~beaker.exceptions.BeakerWorkspaceNotFound` if the workspace doesn't exist.
        """
        return self.rpc_request(
            RpcMethod[pb2.GetWorkspaceResponse](self.service.GetWorkspace),
            pb2.GetWorkspaceRequest(workspace_id=self.resolve_workspace_id(workspace)),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerWorkspaceNotFound(workspace)},
        ).workspace

    def create(
        self,
        name: str,
        *,
        org: pb2.Organization | None = None,
        description: str | None = None,
    ) -> pb2.Workspace:
        org_id: str | None = None
        if "/" in name:
            org_name, name = name.split("/", 1)
            if org is None:
                org_id = self.resolve_org_id(org_name)
            elif org.name != org_name:
                raise ValueError("got conflicting options for organization")

        return self.rpc_request(
            RpcMethod[pb2.CreateWorkspaceResponse](self.service.CreateWorkspace),
            pb2.CreateWorkspaceRequest(
                name=self._validate_beaker_name(name),
                organization_id=org_id if org_id is not None else self.resolve_org_id(org),
                description=description,
            ),
        ).workspace

    def update(
        self,
        workspace: pb2.Workspace | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
        archived: bool | None = None,
        budget: str | None = None,
        maximum_workspace_priority: BeakerJobPriority | None = None,
    ) -> pb2.Workspace:
        return self.rpc_request(
            RpcMethod[pb2.UpdateWorkspaceResponse](self.service.UpdateWorkspace),
            pb2.UpdateWorkspaceRequest(
                workspace_id=self.resolve_workspace_id(workspace),
                name=None if name is None else self._validate_beaker_name(name),
                description=description,
                archived=archived,  # type: ignore
                maximum_workspace_priority=None
                if maximum_workspace_priority is None
                else maximum_workspace_priority.as_pb2(),
                budget_id=None if budget is None else self.resolve_budget_id(budget),
            ),
        ).workspace

    def transfer_into(
        self, *, entity_ids: list[str], workspace: pb2.Workspace | None = None
    ) -> pb2.Workspace:
        return self.rpc_request(
            RpcMethod[pb2.TransferIntoWorkspaceResponse](self.service.TransferIntoWorkspace),
            pb2.TransferIntoWorkspaceRequest(
                workspace_id=self.resolve_workspace_id(workspace), entity_ids=entity_ids
            ),
        ).workspace

    def list(
        self,
        *,
        org: pb2.Organization | None = None,
        author: pb2.User | None = None,
        workload_author: pb2.User | None = None,
        name_or_description: str | None = None,
        only_archived: bool = False,
        sort_order: BeakerSortOrder | None = None,
        sort_field: Literal[
            "created", "name", "recent_workload_activity", "maximum_workload_priority"
        ] = "name",
        include_workspace_size: bool = False,
        limit: int | None = None,
    ) -> Iterable[pb2.Workspace]:
        if limit is not None and limit <= 0:
            raise ValueError("'limit' must be a positive integer")

        count = 0
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListWorkspacesResponse](self.service.ListWorkspaces),
            pb2.ListWorkspacesRequest(
                options=pb2.ListWorkspacesRequest.Opts(
                    sort_clause=pb2.ListWorkspacesRequest.Opts.SortClause(
                        sort_order=None if sort_order is None else sort_order.as_pb2(),
                        created={} if sort_field == "created" else None,
                        name={} if sort_field == "name" else None,
                        recent_workload_activity={}
                        if sort_field == "recent_workload_activity"
                        else None,
                        maximum_workload_priority={}
                        if sort_field == "maximum_workload_priority"
                        else None,
                    ),
                    organization_id=self.resolve_org_id(org),
                    author_id=None if author is None else self.resolve_user_id(author),
                    only_archived=only_archived,
                    workload_author_id=None
                    if workload_author is None
                    else self.resolve_user_id(workload_author),
                    name_or_description_substring=name_or_description,
                    include_workspace_size=include_workspace_size,
                    page_size=self.MAX_PAGE_SIZE
                    if limit is None
                    else min(self.MAX_PAGE_SIZE, limit),
                )
            ),
        ):
            for workspace in response.workspaces:
                count += 1
                yield workspace
                if limit is not None and count >= limit:
                    return

    def url(self, workspace: pb2.Workspace | None = None) -> str:
        workspace = workspace or self.get()
        return f"{self.config.agent_address}/ws/{workspace.name}"
