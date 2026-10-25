import boto3

from costwarden.accounts.models import Account


def get_session(account: Account) -> boto3.Session:
    """Assume the account's role when one is set; otherwise use ambient credentials."""
    if not account.role_arn:
        return boto3.Session(region_name=account.region)
    sts = boto3.client("sts", region_name=account.region)
    creds = sts.assume_role(RoleArn=account.role_arn, RoleSessionName="costwarden")["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=account.region,
    )
