import pickle
import zlib
from collections import defaultdict

import boto3
from langgraph.checkpoint.memory import InMemorySaver

from costwarden.config import Settings, load_settings


class LocalCheckpointer(InMemorySaver):
    """In-memory checkpointer with the restore/persist hooks the run service calls."""

    def restore(self, thread_id: str) -> None:
        pass

    def persist(self, thread_id: str) -> None:
        pass


class DynamoCheckpointer(LocalCheckpointer):
    """Persists one thread's checkpoints to a DynamoDB item so approval pauses survive
    across Lambda invocations. The run service calls restore() before and persist() after
    every graph call. Items are compressed; a run's state is far below the 400 KB item limit."""

    def __init__(self, table_name: str, session: boto3.Session | None = None):
        super().__init__()
        session = session or boto3.Session()
        self.table = session.resource("dynamodb").Table(table_name)

    def persist(self, thread_id: str) -> None:
        data = {
            "storage": {ns: dict(cps) for ns, cps in self.storage.get(thread_id, {}).items()},
            "writes": {k: v for k, v in self.writes.items() if k[0] == thread_id},
            "blobs": {k: v for k, v in self.blobs.items() if k[0] == thread_id},
        }
        self.table.put_item(Item={"thread_id": thread_id, "blob": zlib.compress(pickle.dumps(data))})

    def restore(self, thread_id: str) -> None:
        item = self.table.get_item(Key={"thread_id": thread_id}).get("Item")
        if not item:
            return
        data = pickle.loads(zlib.decompress(bytes(item["blob"].value)))  # our own table, our own writes
        self.storage[thread_id] = defaultdict(dict, {ns: dict(cps) for ns, cps in data["storage"].items()})
        self.writes.update(data["writes"])
        self.blobs.update(data["blobs"])


def get_checkpointer(settings: Settings | None = None) -> LocalCheckpointer:
    s = settings or load_settings()
    if s.checkpoint_backend == "dynamo":
        return DynamoCheckpointer(s.checkpoint_table, boto3.Session(region_name=s.aws_region))
    return LocalCheckpointer()
