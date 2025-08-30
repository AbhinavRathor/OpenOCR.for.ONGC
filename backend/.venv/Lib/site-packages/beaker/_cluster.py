from typing import Iterable, Literal

import grpc

from . import beaker_pb2 as pb2
from ._service_client import RpcMethod, ServiceClient
from .exceptions import *
from .types import *


class ClusterClient(ServiceClient):
    """
    Methods for interacting with Beaker `Clusters <https://beaker-docs.apps.allenai.org/concept/clusters.html>`_.
    Accessed via the :data:`Beaker.cluster <beaker.Beaker.cluster>` property.

    .. warning::
        Do not instantiate this class directly! The :class:`~beaker.Beaker` client will create
        one automatically which you can access through the corresponding property.
    """

    def get(self, cluster: str, *, include_cluster_occupancy: bool = False) -> pb2.Cluster:
        """
        :examples:

        >>> with Beaker.from_env() as beaker:
        ...     cluster = beaker.cluster.get(cluster_name)

        :returns: A :class:`~beaker.types.BeakerCluster`.

        :raises ~beaker.exceptions.BeakerClusterNotFound: If the cluster doesn't exist.
        """
        return self.rpc_request(
            RpcMethod[pb2.GetClusterResponse](self.service.GetCluster),
            pb2.GetClusterRequest(
                cluster_id=self.resolve_cluster_id(cluster),
                include_cluster_occupancy=include_cluster_occupancy,
            ),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerClusterNotFound(cluster)},
        ).cluster

    def list(
        self,
        *,
        org: pb2.Organization | None = None,
        sort_order: BeakerSortOrder | None = None,
        sort_field: Literal[
            "created", "name", "running_jobs", "total_nodes", "total_gpus", "free_gpus"
        ] = "name",
        include_cluster_occupancy: bool = False,
        limit: int | None = None,
    ) -> Iterable[pb2.Cluster]:
        """
        List clusters.

        :returns: An iterator over :class:`~beaker.types.BeakerCluster` protobuf objects.
        """
        if limit is not None and limit <= 0:
            raise ValueError("'limit' must be a positive integer")

        count = 0
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListClustersResponse](self.service.ListClusters),
            pb2.ListClustersRequest(
                options=pb2.ListClustersRequest.Opts(
                    sort_clause=pb2.ListClustersRequest.Opts.SortClause(
                        sort_order=None if sort_order is None else sort_order.as_pb2(),
                        created={} if sort_field == "created" else None,
                        name={} if sort_field == "name" else None,
                        running_jobs={} if sort_field == "running_jobs" else None,
                        total_nodes={} if sort_field == "total_nodes" else None,
                        total_gpus={} if sort_field == "total_gpus" else None,
                        free_gpus={} if sort_field == "free_gpus" else None,
                    ),
                    organization_id=self.resolve_org_id(org),
                    include_cluster_occupancy=include_cluster_occupancy,
                    page_size=self.MAX_PAGE_SIZE
                    if limit is None
                    else min(self.MAX_PAGE_SIZE, limit),
                )
            ),
        ):
            for cluster in response.clusters:
                count += 1
                yield cluster
                if limit is not None and count >= limit:
                    return

    def url(self, cluster: pb2.Cluster) -> str:
        """
        Get the URL to the cluster on the Beaker dashboard.
        """
        return f"{self.config.agent_address}/orgs/{self.beaker.org_name}/clusters/{cluster.name}"
