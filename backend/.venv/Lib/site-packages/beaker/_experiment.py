import grpc
import yaml

from . import beaker_pb2 as pb2
from ._service_client import RpcMethod, ServiceClient
from .exceptions import *
from .types import *


class ExperimentClient(ServiceClient):
    """
    Methods for interacting with Beaker `Experiments <https://beaker-docs.apps.allenai.org/concept/experiments.html>`_.
    Accessed via the :data:`Beaker.experiment <beaker.Beaker.experiment>` property.

    .. warning::
        Do not instantiate this class directly! The :class:`~beaker.Beaker` client will create
        one automatically which you can access through the corresponding property.
    """

    def create(
        self,
        *,
        spec: BeakerExperimentSpec | PathOrStr,
        name: str | None = None,
        workspace: pb2.Workspace | None = None,
    ) -> pb2.Workload:
        """
        Create/launch a new experiment workload.

        .. seealso::
            Use :data:`Beaker.workload <beaker._workload.WorkloadClient>` methods for working with workload objects.

        :returns: A :class:`~beaker.types.BeakerWorkload` object.

        :raises ~beaker.exceptions.BeakerExperimentConflict: If an experiment with the given name already exists.
        """
        if name is not None:
            self._validate_beaker_name(name)

        if not isinstance(spec, BeakerExperimentSpec):
            spec = BeakerExperimentSpec.from_file(spec)

        json_spec = spec.to_json()
        workspace_id = self.resolve_workspace_id(workspace)

        data = self.http_request(
            f"workspaces/{workspace_id}/experiments",
            method="POST",
            query=None if name is None else {"name": name},
            data=json_spec,
            exceptions_for_status=None if name is None else {409: BeakerExperimentConflict(name)},
        ).json()

        return self.beaker.workload.get(data["id"])

    def get_spec(self, experiment: pb2.Experiment | pb2.Workload) -> BeakerExperimentSpec:
        """
        Get the spec that defined an experiment.

        :param experiment: The :class:`~beaker.types.BeakerExperiment` or :class:`~beaker.types.BeakerWorkload`.

        :returns: The corresponding :class:`~beaker.types.BeakerExperimentSpec`.
        """
        yaml_str = self.rpc_request(
            RpcMethod[pb2.GetExperimentYamlSpecResponse](self.service.GetExperimentYamlSpec),
            pb2.GetExperimentYamlSpecRequest(experiment_id=self.resolve_experiment_id(experiment)),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerExperimentNotFound(experiment)},
        ).experiment_spec
        json_dict = yaml.safe_load(yaml_str)
        return BeakerExperimentSpec.from_json(json_dict)

    def restart_tasks(self, experiment: pb2.Experiment | pb2.Workload) -> pb2.Workload:
        """
        Restart all failed or canceled tasks of an experiment.

        :param experiment: The :class:`~beaker.types.BeakerExperiment` or :class:`~beaker.types.BeakerWorkload`.

        :returns: The updated :class:`~beaker.types.BeakerWorkload`.
        """
        return self.rpc_request(
            RpcMethod[pb2.RestartExperimentTasksResponse](self.service.RestartExperimentTasks),
            pb2.RestartExperimentTasksRequest(experiment_id=self.resolve_experiment_id(experiment)),
            exceptions_for_status={grpc.StatusCode.NOT_FOUND: BeakerExperimentNotFound(experiment)},
        ).workload

    def url(self, experiment: pb2.Experiment | pb2.Workload) -> str:
        return f"{self.config.agent_address}/ex/{self._url_quote(self.resolve_experiment_id(experiment))}"
