from typing import Iterable, Literal, cast

import grpc

from . import beaker_pb2 as pb2
from ._service_client import RpcMethod, ServiceClient
from .exceptions import *
from .types import *


class ImageClient(ServiceClient):
    """
    Methods for interacting with Beaker `Images <https://beaker-docs.apps.allenai.org/concept/images.html>`_.
    Accessed via the :data:`Beaker.image <beaker.Beaker.image>` property.

    .. warning::
        Do not instantiate this class directly! The :class:`~beaker.Beaker` client will create
        one automatically which you can access through the corresponding property.
    """

    def get(self, image: str) -> pb2.Image:
        """
        :examples:

        >>> with Beaker.from_env() as beaker:
        ...     image = beaker.image.get(image_id)

        :returns: A :class:`~beaker.types.BeakerImage` protobuf object.

        :raises ~beaker.exceptions.BeakerImageNotFound: If the image doesn't exist.
        """
        return self.rpc_request(
            RpcMethod[pb2.GetImageResponse](self.service.GetImage),
            pb2.GetImageRequest(image_id=self.resolve_image_id(image)),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerImageNotFound(image)},
        ).image

    def create(
        self,
        name: str,
        image_tag: str,
        *,
        workspace: pb2.Workspace | None = None,
        description: str | None = None,
        commit: bool = True,
    ) -> pb2.Image:
        """
        Upload a local Docker image to Beaker.

        :param name: The name to assign to the image on Beaker.
        :param image_tag: The tag of the local image you're uploading.
        :param workspace: The workspace to upload the image to. If not specified, your default workspace is used.
        :param description: Text description of the image.
        :param quiet: If ``True``, progress won't be displayed.
        :param commit: Whether to commit the image after successful upload.
        """
        import docker
        from docker.models.images import Image

        docker_client = docker.from_env()

        # Validate name and resolve workspace.
        self._validate_beaker_name(name)
        workspace_id = self.resolve_workspace_id(workspace)

        # Get local Docker image object.
        image = cast(Image, docker_client.images.get(image_tag))

        with self.beaker.http_session():
            # Create new image on Beaker.
            image_id = self.http_request(
                "images",
                method="POST",
                data={
                    "workspace": workspace_id,
                    "imageId": image.id,
                    "imageTag": image_tag,
                    "description": description,
                },
                query={"name": name},
                exceptions_for_status={409: BeakerImageConflict(name)},
            ).json()["id"]

            # Get the repo data for the Beaker image.
            repo = self.http_request(f"images/{image_id}/repository", query={"upload": True}).json()

        # Tag the local image with the new tag for the Beaker image.
        image.tag(repo["imageTag"])

        # Upload the image.
        for layer_state_data in docker_client.api.push(
            repo["imageTag"],
            stream=True,
            decode=True,
            auth_config={
                "username": repo["auth"]["user"],
                "password": repo["auth"]["password"],
                "server_address": repo["auth"]["server_address"],
            },
        ):
            if "id" in layer_state_data and "status" in layer_state_data:
                status = layer_state_data["status"].lower()
                if status.startswith("layer "):
                    status = status.replace("layer ", "", 1)
                self.logger.info(f"Layer '{layer_state_data['id']}' {status}...")
            elif "error" in layer_state_data:
                raise BeakerDockerError(layer_state_data["error"])

        beaker_image = self.get(image_id)
        if commit:
            beaker_image = self.commit(beaker_image)

        return beaker_image

    def commit(self, image: pb2.Image) -> pb2.Image:
        if image.HasField("committed"):
            return image

        image_id = self.resolve_image_id(image)

        @self._retriable()
        def commit():
            # It's okay to retry this because committing an image  multiple
            # times does nothing.
            self.http_request(
                f"images/{image_id}",
                method="PATCH",
                data={"commit": True},
                exceptions_for_status={404: BeakerImageNotFound(image_id)},
            )

        commit()

        return self.get(image_id)

    def update(
        self, image: pb2.Image, name: str | None = None, description: str | None = None
    ) -> pb2.Image:
        return self.rpc_request(
            RpcMethod[pb2.UpdateImageResponse](self.service.UpdateImage),
            pb2.UpdateImageRequest(
                image_id=self.resolve_image_id(image), name=name, description=description
            ),
        ).image

    def delete(self, *images: pb2.Image):
        self.rpc_request(
            RpcMethod[pb2.DeleteImagesResponse](self.service.DeleteImages),
            pb2.DeleteImagesRequest(image_ids=[self.resolve_image_id(image) for image in images]),
        )

    def list(
        self,
        *,
        org: pb2.Organization | None = None,
        author: pb2.User | None = None,
        workspace: pb2.Workspace | None = None,
        name_or_description: str | None = None,
        sort_order: BeakerSortOrder | None = None,
        sort_field: Literal["created", "name"] = "name",
        limit: int | None = None,
    ) -> Iterable[pb2.Image]:
        if limit is not None and limit <= 0:
            raise ValueError("'limit' must be a positive integer")

        count = 0
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListImagesResponse](self.service.ListImages),
            pb2.ListImagesRequest(
                options=pb2.ListImagesRequest.Opts(
                    sort_clause=pb2.ListImagesRequest.Opts.SortClause(
                        sort_order=None if sort_order is None else sort_order.as_pb2(),
                        created={} if sort_field == "created" else None,
                        name={} if sort_field == "name" else None,
                    ),
                    image_name_or_description=name_or_description,
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
            for image in response.images:
                count += 1
                yield image
                if limit is not None and count >= limit:
                    return

    def url(self, image: pb2.Image) -> str:
        image_id = self.resolve_image_id(image)
        return f"{self.config.agent_address}/im/{self._url_quote(image_id)}"
