import io
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Generator, Iterable, Literal
from urllib.parse import urlparse

import grpc
from requests import Response

from . import beaker_pb2 as pb2
from ._service_client import RpcMethod, ServiceClient
from .exceptions import *
from .types import *


@dataclass
class _DatasetStorage:
    id: str
    token: str
    tokenExpires: datetime
    address: str | None = None
    url: str | None = None
    urlv2: str | None = None
    totalSize: int | None = None
    numFiles: int | None = None

    def __post_init__(self):
        if self.address is not None and self.address.startswith("fh://"):
            # HACK: fix prior to https://github.com/allenai/beaker/pull/2962
            self.address = self.address.replace("fh://", "https://", 1)

    @property
    def scheme(self) -> str | None:
        return "fh" if self.urlv2 is None else urlparse(self.urlv2).scheme

    @property
    def base_url(self) -> str:
        if self.address is not None:
            return self.address
        elif self.urlv2 is not None:
            return f"https://{urlparse(self.urlv2).netloc}"
        else:
            raise ValueError("Missing field 'urlv2' or 'address'")


class DatasetClient(ServiceClient):
    """
    Methods for interacting with Beaker `Datasets <https://beaker-docs.apps.allenai.org/concept/datasets.html>`_.
    Accessed via the :data:`Beaker.dataset <beaker.Beaker.dataset>` property.

    .. warning::
        Do not instantiate this class directly! The :class:`~beaker.Beaker` client will create
        one automatically which you can access through the corresponding property.
    """

    HEADER_UPLOAD_ID = "Upload-ID"
    HEADER_UPLOAD_LENGTH = "Upload-Length"
    HEADER_UPLOAD_OFFSET = "Upload-Offset"
    HEADER_DIGEST = "Digest"
    HEADER_LAST_MODIFIED = "Last-Modified"
    HEADER_CONTENT_LENGTH = "Content-Length"
    REQUEST_SIZE_LIMIT = 32 * 1024 * 1024
    DOWNLOAD_CHUNK_SIZE = 10 * 1024

    def get(self, dataset: str) -> pb2.Dataset:
        """
        :examples:

        >>> with Beaker.from_env() as beaker:
        ...     dataset = beaker.dataset.get(dataset_name)

        :returns: A :class:`~beaker.types.BeakerDataset`.

        :raises ~beaker.exceptions.BeakerDatasetNotFound: If the cluster doesn't exist.
        """
        return self.rpc_request(
            RpcMethod[pb2.GetDatasetResponse](self.service.GetDataset),
            pb2.GetDatasetRequest(dataset_id=self.resolve_dataset_id(dataset)),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerDatasetNotFound(dataset)},
        ).dataset

    def _get_storage(self, dataset: pb2.Dataset) -> _DatasetStorage:
        dataset_info = self.http_request(
            f"datasets/{self._url_quote(dataset.id)}",
            exceptions_for_status={404: BeakerDatasetNotFound(dataset.id)},
        ).json()
        return _DatasetStorage(**dataset_info["storage"])

    def create(
        self,
        name: str,
        *sources: PathOrStr,
        target: PathOrStr | None = None,
        workspace: pb2.Workspace | None = None,
        description: str | None = None,
        force: bool = False,
        max_workers: int | None = None,
        commit: bool = True,
        strip_paths: bool = False,
    ) -> pb2.Dataset:
        """
        Create a dataset from local source files.

        :param name: The name to assign to the new dataset.
        :param sources: Local source files or directories to upload to the dataset.
        :param target: If specified, all source files/directories will be uploaded under
            a directory of this name.
        :param workspace: The workspace to upload the dataset to. If not specified your default workspace is used.
        :param description: Text description for the dataset.
        :param force: If ``True`` and a dataset by the given name already exists, it will be overwritten.
        :param max_workers: The maximum number of thread pool workers to use to upload files concurrently.
        :param commit: Whether to commit the dataset after successfully uploading source files.
        :param strip_paths: If ``True``, all source files and directories will be uploaded under their name,
            not their path. E.g. the file "docs/source/index.rst" would be uploaded as just "index.rst",
            instead of "docs/source/index.rst".

            .. note::
                This only applies to source paths that are children of the current working directory.
                If a source path is outside of the current working directory, it will always
                be uploaded under its name only.

        :returns: A new :class:`beaker.types.BeakerDataset` object.

        :raises ~beaker.exceptions.BeakerDatasetConflict: If a dataset with the given name already exists.
        """
        self._validate_beaker_name(name)
        workspace_id = self.resolve_workspace_id(workspace)

        # Create the dataset.
        def make_dataset() -> tuple[pb2.Dataset, _DatasetStorage]:
            dataset_info = self.http_request(
                "datasets",
                method="POST",
                query={"name": name},
                data=dict(workspace=workspace_id, description=description),
                exceptions_for_status={409: BeakerDatasetConflict(name)},
            ).json()
            return self.get(dataset_info["id"]), _DatasetStorage(**dataset_info["storage"])

        with self.beaker.http_session():
            try:
                dataset, storage = make_dataset()
            except BeakerDatasetConflict:
                if force:
                    self.delete(self.get(f"{self.beaker.user_name}/{name}"))
                    dataset, storage = make_dataset()
                else:
                    raise

        # Upload the file(s).
        if sources:
            self._sync(
                dataset,
                storage=storage,
                source_paths=sources,
                target=target,
                max_workers=max_workers,
                strip_paths=strip_paths,
            )

        if commit:
            return self.commit(dataset)
        else:
            return dataset

    def commit(self, dataset: pb2.Dataset) -> pb2.Dataset:
        """
        Commit a dataset.

        :returns: The updated :class:`~beaker.types.BeakerDataset` object.
        """
        if dataset.HasField("committed"):
            return dataset

        @self._retriable()
        def commit():
            # It's okay to retry this because committing a dataset multiple
            # times does nothing.
            self.http_request(
                f"datasets/{self._url_quote(self.resolve_dataset_id(dataset))}",
                method="PATCH",
                data={"commit": True},
                exceptions_for_status={404: BeakerDatasetNotFound(dataset.id)},
            )

        commit()

        return self.get(self.resolve_dataset_id(dataset))

    def _sync(
        self,
        dataset: pb2.Dataset,
        *,
        storage: _DatasetStorage,
        source_paths: Iterable[PathOrStr],
        target: PathOrStr | None = None,
        max_workers: int | None = None,
        strip_paths: bool = False,
    ) -> int:
        if dataset.HasField("committed"):
            raise BeakerDatasetWriteError(f"Dataset '{dataset.id}' has already been committed")

        total_bytes = 0
        # map source path to (target_path, size)
        path_info: dict[Path, tuple[Path, int]] = {}
        for source in source_paths:
            source = Path(source)
            strip_path = strip_paths or not source.is_relative_to(".")
            if source.is_file():
                target_path = Path(source.name) if strip_path else source
                if target is not None:
                    target_path = Path(str(target)) / target_path
                size = source.lstat().st_size
                path_info[source] = (target_path, size)
                total_bytes += size
            elif source.is_dir():
                for path in source.glob("**/*"):
                    if path.is_dir():
                        continue
                    target_path = path.relative_to(source) if strip_path else path
                    if target is not None:
                        target_path = Path(str(target)) / target_path
                    size = path.lstat().st_size
                    if size == 0:
                        continue
                    path_info[path] = (target_path, size)
                    total_bytes += size
            else:
                raise FileNotFoundError(source)

        import concurrent.futures

        # Now upload.
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Dispatch tasks to thread pool executor.
            future_to_path = {}
            for path, (target_path, size) in path_info.items():
                future = executor.submit(
                    self._upload_file,
                    dataset,
                    storage=storage,
                    size=size,
                    source=path,
                    target=target_path,
                    ignore_errors=True,
                )
                future_to_path[future] = path

            # Collect completed tasks.
            for future in concurrent.futures.as_completed(future_to_path):
                path = future_to_path[future]
                original_size = path_info[path][1]
                actual_size = future.result()
                if actual_size != original_size:
                    # If the size of the file has changed since we started, adjust total.
                    total_bytes += actual_size - original_size

        return total_bytes

    def upload(self, dataset: pb2.Dataset, source: PathOrStr | bytes, target: PathOrStr) -> int:
        """
        Upload a file to a dataset.

        :param dataset: The dataset to upload to (must be uncommitted).
        :param source: Path to the local source file or the contents as bytes.
        :param target: The path within the dataset to upload the file to.

        :returns: The number of bytes uploaded.

        :raises ~beaker.exceptions.BeakerDatasetWriteError: If the dataset is already committed.
        """
        if dataset.HasField("committed"):
            raise BeakerDatasetWriteError(f"Dataset '{dataset.id}' has already been committed")

        size = len(source) if isinstance(source, bytes) else Path(source).stat().st_size
        storage = self._get_storage(dataset)
        return self._upload_file(dataset, storage=storage, size=size, source=source, target=target)

    def _upload_file(
        self,
        dataset: pb2.Dataset,
        *,
        storage: _DatasetStorage,
        size: int,
        source: PathOrStr | bytes,
        target: PathOrStr,
        ignore_errors: bool = False,
    ) -> int:
        if storage.scheme != "fh":
            raise NotImplementedError(
                f"Datasets API is not implemented for '{storage.scheme}' backend yet"
            )

        source_file: io.BufferedReader | io.BytesIO
        if isinstance(source, (str, Path, os.PathLike)):
            source = Path(source)
            if ignore_errors and not source.exists():
                self.logger.warning(f"Skipping uploading '{source}' since it doesn't exist")
                return 0
            source_file = source.open("rb")
        elif isinstance(source, bytes):
            source_file = io.BytesIO(source)
        else:
            raise ValueError(f"Expected path-like or raw bytes, got {type(source)}")

        try:
            body: io.BufferedReader | io.BytesIO | None = source_file
            digest: str | None = None

            self.logger.info(f"Uploading {size} bytes to '{target}'...")
            with self.beaker.http_session():
                if size > self.REQUEST_SIZE_LIMIT:

                    @self._retriable()
                    def get_upload_id() -> str:
                        response = self.http_request(
                            "uploads",
                            method="POST",
                            token=storage.token,
                            base_url=storage.base_url,
                        )
                        return response.headers[self.HEADER_UPLOAD_ID]

                    upload_id = get_upload_id()

                    written = 0
                    while written < size:
                        chunk = source_file.read(self.REQUEST_SIZE_LIMIT)
                        if not chunk:
                            break

                        @self._retriable()
                        def upload() -> Response:
                            return self.http_request(
                                f"uploads/{upload_id}",
                                method="PATCH",
                                data=chunk,
                                token=storage.token,
                                base_url=storage.base_url,
                                headers={
                                    self.HEADER_UPLOAD_LENGTH: str(size),
                                    self.HEADER_UPLOAD_OFFSET: str(written),
                                },
                            )

                        response = upload()
                        written += len(chunk)

                        digest = response.headers.get(self.HEADER_DIGEST)
                        if digest:
                            break

                    if written != size:
                        raise BeakerUnexpectedEOFError(str(source))

                    body = None

                @self._retriable()
                def finalize():
                    self.http_request(
                        f"datasets/{storage.id}/files/{str(target)}",
                        method="PUT",
                        data=body if size > 0 else b"",
                        token=storage.token,
                        base_url=storage.base_url,
                        headers=None if not digest else {self.HEADER_DIGEST: digest},
                        stream=body is not None and size > 0,
                        exceptions_for_status={
                            403: BeakerDatasetWriteError(dataset.id),
                            404: BeakerDatasetNotFound(dataset.id),
                        },
                    )

                finalize()

            return size
        finally:
            source_file.close()

    def stream_file(
        self,
        dataset: pb2.Dataset,
        file_path: str,
        *,
        offset: int = 0,
        length: int = -1,
        chunk_size: int | None = None,
        validate_checksum: bool = True,
    ) -> Generator[bytes, None, None]:
        """
        Stream download the bytes content of a file from a dataset.
        """
        file = self.get_file_info(dataset, file_path)
        yield from self._stream_file(
            dataset,
            file,
            offset=offset,
            length=length,
            chunk_size=chunk_size,
            validate_checksum=validate_checksum,
        )

    def _stream_file(
        self,
        dataset: pb2.Dataset,
        file: pb2.DatasetFile,
        chunk_size: int | None = None,
        offset: int = 0,
        length: int = -1,
        validate_checksum: bool = True,
    ) -> Generator[bytes, None, None]:
        def stream_file() -> Generator[bytes, None, None]:
            headers = {}
            if offset > 0 and length > 0:
                headers["Range"] = f"bytes={offset}-{offset + length - 1}"
            elif offset > 0:
                headers["Range"] = f"bytes={offset}-"
            response = self.http_request(
                f"datasets/{dataset.id}/files/{self._url_quote(file.path)}",
                method="GET",
                stream=True,
                headers=headers,
                exceptions_for_status={404: FileNotFoundError(file.path)},
            )
            for chunk in response.iter_content(chunk_size=chunk_size or self.DOWNLOAD_CHUNK_SIZE):
                yield chunk

        contents_hash = None
        if offset == 0 and validate_checksum and file.HasField("digest"):
            contents_hash = BeakerDatasetFileAlgorithmType(file.digest.algorithm).hasher()

        retries = 0
        while True:
            try:
                for chunk in stream_file():
                    offset += len(chunk)
                    if contents_hash is not None:
                        contents_hash.update(chunk)
                    yield chunk
                break
            except RequestException as err:
                if retries < self.beaker.MAX_RETRIES:
                    self._log_and_wait(retries, err)
                    retries += 1
                else:
                    raise

        # Validate digest.
        if file.HasField("digest") and contents_hash is not None:
            import binascii

            actual_digest = binascii.hexlify(contents_hash.digest()).decode()
            expected_digest = binascii.hexlify(file.digest.value).decode()
            if actual_digest != expected_digest:
                raise BeakerChecksumFailedError(
                    f"Checksum for '{file.path}' failed. "
                    f"Expected '{expected_digest}', got '{actual_digest}'."
                )

    def list_files(
        self, dataset: pb2.Dataset, *, prefix: str | None = None
    ) -> Iterable[pb2.DatasetFile]:
        """
        List files in a dataset.

        :returns: An iterator over :class:`~beaker.types.BeakerDatasetFile` protobuf objects.
        """
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListDatasetFilesResponse](self.service.ListDatasetFiles),
            pb2.ListDatasetFilesRequest(
                options=pb2.ListDatasetFilesRequest.Opts(
                    dataset_id=self.resolve_dataset_id(dataset),
                    prefix=prefix,
                )
            ),
        ):
            yield from response.dataset_files

    def get_file_info(self, dataset: pb2.Dataset, file_path: str) -> pb2.DatasetFile:
        """
        :returns: A :class:`~beaker.types.BeakerDatasetFile` protobuf object.
        """
        prefix = os.path.dirname(file_path)
        for f in self.list_files(dataset, prefix=prefix):
            if f.path == file_path:
                return f
        raise FileNotFoundError(file_path)

    def get_file_link(self, dataset: pb2.Dataset, file_path: str) -> str:
        return self.rpc_request(
            RpcMethod[pb2.GetDatasetFileLinkResponse](self.service.GetDatasetFileLink),
            pb2.GetDatasetFileLinkRequest(
                dataset_id=self.resolve_dataset_id(dataset), file_path=file_path
            ),
        ).download_url

    def update(self, dataset: pb2.Dataset, *, description: str | None = None) -> pb2.Dataset:
        """
        Update fields of a dataset.

        :returns: The updated :class:`~beaker.types.BeakerDataset` object.
        """
        return self.rpc_request(
            RpcMethod[pb2.UpdateDatasetResponse](self.service.UpdateDataset),
            pb2.UpdateDatasetRequest(
                dataset_id=self.resolve_dataset_id(dataset),
                description=description,
            ),
        ).dataset

    def delete(self, *datasets: pb2.Dataset):
        """
        Delete datasets.
        """
        self.rpc_request(
            RpcMethod[pb2.DeleteDatasetsResponse](self.service.DeleteDatasets),
            pb2.DeleteDatasetsRequest(
                dataset_ids=[self.resolve_dataset_id(dataset) for dataset in datasets]
            ),
        )

    def list(
        self,
        *,
        org: pb2.Organization | None = None,
        author: pb2.User | None = None,
        workspace: pb2.Workspace | None = None,
        created_before: datetime | None = None,
        created_after: datetime | None = None,
        results: bool | None = None,
        committed: bool | None = None,
        name_or_description: str | None = None,
        sort_order: BeakerSortOrder | None = None,
        sort_field: Literal["created", "name"] = "name",
        limit: int | None = None,
    ) -> Iterable[pb2.Dataset]:
        """
        List datasets.

        :returns: An iterator over :class:`~beaker.types.BeakerDataset` protobuf objects.
        """
        Opts = pb2.ListDatasetsRequest.Opts

        if limit is not None and limit <= 0:
            raise ValueError("'limit' must be a positive integer")

        dataset_type = None
        if results is True:
            dataset_type = Opts.DatasetType.DATASET_TYPE_IS_RESULT
        elif results is False:
            dataset_type = Opts.DatasetType.DATASET_TYPE_IS_NOT_RESULT

        committed_status = None
        if committed is True:
            committed_status = Opts.CommittedStatus.STATUS_COMMITTED
        elif committed is False:
            committed_status = Opts.CommittedStatus.STATUS_UNCOMMITTED

        count = 0
        for response in self.rpc_paged_request(
            RpcMethod[pb2.ListDatasetsResponse](self.service.ListDatasets),
            pb2.ListDatasetsRequest(
                options=Opts(
                    sort_clause=Opts.SortClause(
                        sort_order=None if sort_order is None else sort_order.as_pb2(),
                        created={} if sort_field == "created" else None,
                        name={} if sort_field == "name" else None,
                    ),
                    created_before=created_before,  # type: ignore[arg-type]
                    created_after=created_after,  # type: ignore[arg-type]
                    dataset_type=dataset_type,
                    committed_status=committed_status,
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
            for dataset in response.datasets:
                count += 1
                yield dataset
                if limit is not None and count >= limit:
                    return

    def url(self, dataset: pb2.Dataset) -> str:
        """
        Get the URL to the cluster on the Beaker dashboard.
        """
        dataset_id = self.resolve_dataset_id(dataset)
        return f"{self.config.agent_address}/ds/{self._url_quote(dataset_id)}"
