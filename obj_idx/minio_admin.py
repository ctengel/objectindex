#!/usr/bin/env python3

"""CLI for minio admin tools"""

import argparse
import pathlib
import os
import tempfile
import json
import secrets
import datetime
import minio


class MinIO:
    """deal with minio bucket creations and permissions"""
    def __init__(self, alias, endpoint, user, password, mc_path=None):
        self.mioc = minio.Minio(endpoint, user, password, secure=False)
        self.mioa = minio.MinioAdmin(alias, binary_path=mc_path)
    def create_bucket(self, bucket_name: str):
        """Create a bucket"""
        self.mioc.make_bucket(bucket_name)
    def _add_policy(self, policy_name: str, policy_doc: str):
        self.mioa.policy_add(policy_name, policy_doc)
    @staticmethod
    def _policy_file(policy_data: dict) -> str:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w") as policy_file:
            json.dump(policy_data, policy_file)
            policy_file_name = policy_file.name
        return policy_file_name
    def add_policy_file(self, policy_name: str, data: dict):
        """Given a JSON-like policy dictionry, write it to a temp file and add it"""
        file_name = self._policy_file(data)
        self._add_policy(policy_name, file_name)
        pathlib.Path(file_name).unlink()
    def attach_policy(self, policy_name: str, user: str):
        """attach existing policy to a user"""
        self.mioa.policy_set(policy_name, user=user)
    @staticmethod
    def _bucket_policy(bucket_names: list[str], actions: list[str] = None) -> dict:
        if not actions:
            actions = ["s3:ListBucket", "s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
        return {'Version': '2012-10-17',
                'Statement': [{'Effect': 'Allow',
                               'Action': actions,
                               'Resource': [f"arn:aws:s3:::{bucket}"
                                            for bucket in bucket_names] +
                                           [f"arn:aws:s3:::{bucket}/*"
                                            for bucket in bucket_names]}]}
    def create_policy(self,
                      bucket_names: list[str],
                      policy_name: str = None,
                      actions: list[str] = None) -> str:
        """Create policy for given buckets"""
        if not policy_name:
            assert len(bucket_names) == 1
            policy_name = f"{bucket_names[0]}-policy"
        policy_doc = self._bucket_policy(bucket_names, actions)
        self.add_policy_file(policy_name, policy_doc)
        return policy_name
    def bucket_policy_user(self,
                           bucket_names: list[str],
                           users: list[str],
                           policy_name: str = None,
                           actions: list[str] = None):
        """Create a bucket policy and attach to a list of users"""
        policy_name = self.create_policy(bucket_names, policy_name, actions)
        for user in users:
            self.attach_policy(policy_name, user)
    def bucket_with_users(self, bucket_name: str, users: list[str]):
        """Create a bucket and grant access to a list of users"""
        self.create_bucket(bucket_name)
        self.bucket_policy_user([bucket_name], users)
    def add_user(self, username, password):
        """Add a user"""
        self.mioa.user_add(username, password)

def _setup(mioo, args):
    password = secrets.token_urlsafe()
    print(f"Password: {password}")
    mioo.add_user(args.username, password)
    today = datetime.date.today().strftime("%Y%m%d")
    for bucket in args.buckets:
        mioo.bucket_with_users(f"{bucket}-{today}", [args.username])

def cli():
    """CLI main function"""
    parser = argparse.ArgumentParser(description="Object Index MinIO admin")
    subparsers = parser.add_subparsers()
    parser.add_argument('-a', '--alias')
    parser.add_argument('-e', '--endpoint')
    parser.add_argument('-m', '--mc-path')
    parser_setup = subparsers.add_parser('setup')
    parser_setup.add_argument('username')
    parser_setup.add_argument('buckets', nargs='+')
    parser_setup.set_defaults(func=_setup)
    args = parser.parse_args()
    args.func(MinIO(args.alias,
                    args.endpoint,
                    os.environ['MINIO_ROOT_USER'],
                    os.environ['MINIO_ROOT_PASSWORD'],
                    mc_path=args.mc_path),
              args)


if __name__ == '__main__':
    cli()
