from typing import Iterable, Literal

import grpc

from . import beaker_pb2 as pb2
from ._service_client import RpcMethod, ServiceClient
from .exceptions import *
from .types import *


class UserClient(ServiceClient):
    def get(
        self,
        user: str | None = None,
        *,
        include_user_details: bool = False,
        include_orgs: bool = False,
    ) -> pb2.User:
        user_id = None if user is None else self.resolve_user_id(user)
        return self.rpc_request(
            RpcMethod[pb2.GetUserResponse](self.service.GetUser),
            pb2.GetUserRequest(
                user_id=user_id,
                include_user_details=include_user_details,
                include_orgs=include_orgs,
            ),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerUserNotFound(user)},
        ).user

    def create(self, *, name: str, email: str | None = None) -> pb2.User:
        return self.rpc_request(
            RpcMethod[pb2.CreateUserResponse](self.service.CreateUser),
            pb2.CreateUserRequest(name=name, email=email),
        ).user

    def update(
        self,
        user: pb2.User | None = None,
        *,
        name: str | None = None,
        display_name: str | None = None,
        email: str | None = None,
        pronouns: str | None = None,
        role: BeakerAuthRole | None = None,
    ) -> pb2.User:
        return self.rpc_request(
            RpcMethod[pb2.UpdateUserResponse](self.service.UpdateUser),
            pb2.UpdateUserRequest(
                user_id=self.resolve_user_id(user),
                name=name,
                display_name=display_name,
                pronouns=pronouns,
                email=email,
                role=None if role is None else role.as_pb2(),
            ),
        ).user

    def regenerate_auth_token(self) -> str:
        return self.rpc_request(
            RpcMethod[pb2.RegenerateUserAuthTokenResponse](self.service.RegenerateUserAuthToken),
            pb2.RegenerateUserAuthTokenRequest(),
        ).token

    def list(
        self,
        *,
        org: pb2.Organization | None = None,
        sort_order: BeakerSortOrder | None = None,
        sort_field: Literal["created", "name"] = "name",
        include_user_details: bool = False,
        limit: int | None = None,
    ) -> Iterable[pb2.User]:
        if limit is not None and limit <= 0:
            raise ValueError("'limit' must be a positive integer")

        count = 0
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListUsersResponse](self.service.ListUsers),
            pb2.ListUsersRequest(
                options=pb2.ListUsersRequest.Opts(
                    sort_clause=pb2.ListUsersRequest.Opts.SortClause(
                        sort_order=None if sort_order is None else sort_order.as_pb2(),
                        created={} if sort_field == "created" else None,
                        name={} if sort_field == "name" else None,
                    ),
                    organization_id=self.resolve_org_id(org),
                    include_user_details=include_user_details,
                    page_size=self.MAX_PAGE_SIZE
                    if limit is None
                    else min(self.MAX_PAGE_SIZE, limit),
                ),
            ),
        ):
            for user in response.users:
                count += 1
                yield user
                if limit is not None and count >= limit:
                    return
