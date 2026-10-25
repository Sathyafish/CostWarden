import json
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from costwarden.store.models import CleanupRecord, Metrics, compute_metrics


def _to_ddb(o):
    return json.loads(json.dumps(o), parse_float=Decimal)


def _from_ddb(o):
    if isinstance(o, Decimal):
        return float(o) if o % 1 else int(o)
    if isinstance(o, list):
        return [_from_ddb(x) for x in o]
    if isinstance(o, dict):
        return {k: _from_ddb(v) for k, v in o.items()}
    return o


class DynamoStore:
    def __init__(self, table_name: str, session: boto3.Session | None = None):
        session = session or boto3.Session()
        self.table = session.resource("dynamodb").Table(table_name)

    def record_cleanup(self, rec: CleanupRecord) -> None:
        item = _to_ddb({**rec.to_dict(), "ts_run": rec.ts_run})
        self.table.put_item(Item={k: v for k, v in item.items() if v is not None})

    def update_status(self, account_id: str, run_id: str, status: str) -> None:
        for rec in self.list_cleanups(account_id):
            if rec.run_id == run_id:
                self.table.update_item(
                    Key={"account_id": account_id, "ts_run": rec.ts_run},
                    UpdateExpression="SET #s = :s",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":s": status},
                )
                return
        raise KeyError(f"No cleanup for {account_id}/{run_id}")

    def _items(self, account_id: str | None):
        if account_id:
            resp = self.table.query(KeyConditionExpression=Key("account_id").eq(account_id))
            items = resp["Items"]
            while "LastEvaluatedKey" in resp:
                resp = self.table.query(KeyConditionExpression=Key("account_id").eq(account_id),
                                        ExclusiveStartKey=resp["LastEvaluatedKey"])
                items += resp["Items"]
            return items
        resp = self.table.scan()
        items = resp["Items"]
        while "LastEvaluatedKey" in resp:
            resp = self.table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items += resp["Items"]
        return items

    def list_cleanups(self, account_id: str | None = None, since: str | None = None) -> list[CleanupRecord]:
        recs = []
        for it in self._items(account_id):
            d = _from_ddb(it)
            d.pop("ts_run", None)
            d.setdefault("pr_url", None)
            recs.append(CleanupRecord(**d))
        if since:
            recs = [r for r in recs if r.timestamp >= since]
        return sorted(recs, key=lambda r: r.timestamp, reverse=True)

    def metrics(self, account_id: str | None = None) -> Metrics:
        return compute_metrics(self.list_cleanups(account_id))
