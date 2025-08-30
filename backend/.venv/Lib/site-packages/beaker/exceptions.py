from grpc import RpcError
from requests.exceptions import HTTPError, RequestException

__all__ = [
    "BeakerError",
    "RpcError",
    "HTTPError",
    "BeakerClientError",
    "BeakerServerError",
    "BeakerStreamConnectionClosedError",
    "BeakerServerUnavailableError",
    "RequestException",
    "BeakerConfigurationError",
    "BeakerNotFoundError",
    "BeakerOrganizationNotFound",
    "BeakerUserNotFound",
    "BeakerWorkspaceNotFound",
    "BeakerClusterNotFound",
    "BeakerNodeNotFound",
    "BeakerBudgetNotFound",
    "BeakerGroupNotFound",
    "BeakerQueueNotFound",
    "BeakerQueueEntryNotFound",
    "BeakerQueueWorkerNotFound",
    "BeakerImageNotFound",
    "BeakerDatasetNotFound",
    "BeakerSecretNotFound",
    "BeakerExperimentNotFound",
    "BeakerWorkloadNotFound",
    "BeakerJobNotFound",
    "BeakerOrganizationNotSet",
    "BeakerWorkspaceNotSet",
    "BeakerPermissionsError",
    "BeakerNameConflictError",
    "BeakerDatasetConflict",
    "BeakerExperimentConflict",
    "BeakerImageConflict",
    "BeakerSecretConflict",
    "BeakerGroupConflict",
    "BeakerWorkspaceConflict",
    "BeakerDatasetWriteError",
    "BeakerUnexpectedEOFError",
    "BeakerChecksumFailedError",
    "BeakerDockerError",
    "BeakerWorkerThreadError",
    "BeakerCreateQueueEntryFailedError",
]


class BeakerError(Exception):
    """Base class for all Beaker errors."""


class BeakerClientError(BeakerError):
    pass


class BeakerServerError(BeakerError):
    pass


class BeakerStreamConnectionClosedError(BeakerServerError):
    """
    Raised when the server closes a long-running streaming connection prematurely.
    See https://github.com/allenai/beaker/issues/6532.
    """


class BeakerServerUnavailableError(BeakerServerError):
    pass


class BeakerConfigurationError(BeakerError):
    """Raised when invalid fields are found in the config file."""


class BeakerNotFoundError(BeakerError):
    """Base class for not found errors."""


class BeakerOrganizationNotFound(BeakerNotFoundError):
    """Raised when a specified organization doesn't exist."""


class BeakerUserNotFound(BeakerNotFoundError):
    """Raised when a specified user doesn't exist."""


class BeakerWorkspaceNotFound(BeakerNotFoundError):
    """Raised when a specified workspace doesn't exist."""


class BeakerClusterNotFound(BeakerNotFoundError):
    """Raised when a specified cluster doesn't exist."""


class BeakerNodeNotFound(BeakerNotFoundError):
    """Raised when a specified node doesn't exist."""


class BeakerBudgetNotFound(BeakerNotFoundError):
    """Raised when a specified budget doesn't exist."""


class BeakerGroupNotFound(BeakerNotFoundError):
    """Raised when a specified group doesn't exist."""


class BeakerQueueNotFound(BeakerNotFoundError):
    """Raised when a specified queue doesn't exist."""


class BeakerQueueEntryNotFound(BeakerNotFoundError):
    """Raised when a specified queue entry doesn't exist."""


class BeakerQueueWorkerNotFound(BeakerNotFoundError):
    """Raised when a specified queue worker doesn't exist."""


class BeakerJobNotFound(BeakerNotFoundError):
    """Raised when a specified job doesn't exist."""


class BeakerExperimentNotFound(BeakerNotFoundError):
    """Raised when a specified experiment doesn't exist."""


class BeakerWorkloadNotFound(BeakerNotFoundError):
    """Raised when a specified workload doesn't exist."""


class BeakerImageNotFound(BeakerNotFoundError):
    """Raised when a specified image doesn't exist."""


class BeakerDatasetNotFound(BeakerNotFoundError):
    """Raised when a specified dataset doesn't exist."""


class BeakerSecretNotFound(BeakerNotFoundError):
    """Raised when a specified secret does not exist."""


class BeakerOrganizationNotSet(BeakerError):
    """Raised when the default organization is not set."""


class BeakerWorkspaceNotSet(BeakerError):
    """Raised when the default workspace is not set."""


class BeakerPermissionsError(BeakerError):
    pass


class BeakerNameConflictError(BeakerError):
    """Base error type for name conflict errors."""


class BeakerDatasetConflict(BeakerNameConflictError):
    pass


class BeakerExperimentConflict(BeakerNameConflictError):
    pass


class BeakerImageConflict(BeakerNameConflictError):
    pass


class BeakerSecretConflict(BeakerNameConflictError):
    pass


class BeakerGroupConflict(BeakerNameConflictError):
    pass


class BeakerWorkspaceConflict(BeakerNameConflictError):
    pass


class BeakerDatasetWriteError(BeakerError):
    pass


class BeakerUnexpectedEOFError(BeakerError):
    pass


class BeakerChecksumFailedError(BeakerError):
    pass


class BeakerDockerError(BeakerError):
    pass


class BeakerWorkerThreadError(BeakerError):
    """
    Raised when a worker thread dies.
    """


class BeakerCreateQueueEntryFailedError(BeakerError):
    """
    Raised when creating a new queue entry fails.
    """
