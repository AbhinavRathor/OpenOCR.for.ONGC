from typing import Any

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message


def pb2_to_dict(msg: Message) -> dict[str, Any]:
    return MessageToDict(msg)
