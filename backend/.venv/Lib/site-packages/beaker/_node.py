from typing import Iterable, Literal

import grpc

from . import beaker_pb2 as pb2
from ._service_client import RpcMethod, ServiceClient
from .exceptions import *
from .types import *


class NodeClient(ServiceClient):
    def get(self, node_id: str) -> pb2.Node:
        return self.rpc_request(
            RpcMethod[pb2.GetNodeResponse](self.service.GetNode),
            pb2.GetNodeRequest(node_id=node_id),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerNodeNotFound(node_id)},
        ).node

    def cordon(self, node: pb2.Node, *, reason: str) -> pb2.Node:
        return self.rpc_request(
            RpcMethod[pb2.CordonNodeResponse](self.service.CordonNode),
            pb2.CordonNodeRequest(
                node_id=self.resolve_node_id(node),
                cordon_reason=reason,
                desired_state=pb2.CordonNodeRequest.DesiredState.DESIRED_STATE_CORDONED,
            ),
        ).node

    def list(
        self,
        *,
        org: pb2.Organization | None = None,
        cluster: pb2.Cluster | None = None,
        sort_order: BeakerSortOrder | None = None,
        sort_field: Literal["created", "name", "recent_activity_for_user", "utilization"] = "name",
        user: pb2.User | None = None,
        limit: int | None = None,
    ) -> Iterable[pb2.Node]:
        if limit is not None and limit <= 0:
            raise ValueError("'limit' must be a positive integer")

        count = 0
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListNodesResponse](self.service.ListNodes),
            pb2.ListNodesRequest(
                options=pb2.ListNodesRequest.Opts(
                    sort_clause=pb2.ListNodesRequest.Opts.SortClause(
                        sort_order=None if sort_order is None else sort_order.as_pb2(),
                        created={} if sort_field == "created" else None,
                        name={} if sort_field == "name" else None,
                        recent_activity_for_user_id=self.resolve_user_id(user)
                        if sort_field == "recent_activity_for_user"
                        else None,
                        utilization={} if sort_field == "utilization" else None,
                    ),
                    organization_id=self.resolve_org_id(org),
                    cluster_id=None if cluster is None else self.resolve_cluster_id(cluster),
                    page_size=self.MAX_PAGE_SIZE
                    if limit is None
                    else min(self.MAX_PAGE_SIZE, limit),
                )
            ),
        ):
            for node in response.nodes:
                count += 1
                yield node
                if limit is not None and count >= limit:
                    return
