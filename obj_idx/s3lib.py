"""Wrapper around an S3 library

Handle some of oddness of using an on-prem solution
"""

import urllib.parse
import boto3

def get_s3_service(endpoint, key):
    """Returns a boto3 S3 Service Resource

    https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#service-resource
    """
    return boto3.resource('s3',
                          endpoint_url=endpoint,
                          aws_access_key_id=key[0],
                          aws_secret_access_key=key[1],
                          config=boto3.session.Config(signature_version='s3v4'))

def url2epcred(url):
    """Returns a tuple with endpoint and key tuple based on pseudo-url

    style https://user:password@host:port/
    """
    parsed = urllib.parse.urlparse(url)
    assert not parsed.params
    assert not parsed.query
    assert not parsed.fragment
    endpoint = urllib.parse.urlunparse((parsed.scheme,
                                        "{}:{}".format(parsed.hostname, parsed.port),
                                        parsed.path,
                                        None,
                                        None,
                                        None))
    key = (parsed.username, parsed.password)
    return (endpoint, key)

def get_s3_service_url(url):
    """Returns a boto S3 Service Resource using a pseudo URL"""
    return get_s3_service(*url2epcred(url))
