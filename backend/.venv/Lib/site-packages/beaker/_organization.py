from typing import Iterable

import grpc

from . import beaker_pb2 as pb2
from ._service_client import RpcMethod, ServiceClient
from .exceptions import *
from .types import *


class OrganizationClient(ServiceClient):
    def get(self, org: str | None = None) -> pb2.Organization:
        org_id = self.resolve_org_id(org)
        return self.rpc_request(
            RpcMethod[pb2.GetOrganizationResponse](self.service.GetOrganization),
            pb2.GetOrganizationRequest(organization_id=org_id),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerOrganizationNotFound(org)},
        ).organization

    def list(self, sort_order: BeakerSortOrder | None = None) -> Iterable[pb2.Organization]:
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListOrganizationsResponse](self.service.ListOrganizations),
            pb2.ListOrganizationsRequest(
                options=pb2.ListOrganizationsRequest.Opts(
                    sort_clause=pb2.ListOrganizationsRequest.Opts.SortClause(
                        sort_order=None if sort_order is None else sort_order.as_pb2(),
                        created={},
                    )
                )
            ),
        ):
            yield from response.organizations
