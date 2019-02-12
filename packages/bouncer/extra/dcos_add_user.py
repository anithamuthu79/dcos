#!/usr/bin/env python
"""
Prior to DC/OS version 1.13 a user could directly be created in ZooKeeper by
utilizing a script ``dcos_add_user.py`` which would be copied to
``/opt/mesosphere/bin/dcos_add_user.py``:
https://github.com/dcos/dcos/blob/1d9e6bb2a27daf3dc8ec359e01e2272ec8a09dd0/packages/dcos-oauth/extra/dcos_add_user.py

This script is intended to enable the same functionality for DC/OS 1.13+.
After installing DC/OS will be accessible from ``/opt/mesosphere/bin/dcos_add_user.py``.

This script uses legacy user management to create a user in the IAM service:

https://github.com/dcos/dcos/blob/abaeb5cceedd5661b8d96ff47f8bb5ef212afbdc/packages/dcos-integration-test/extra/test_legacy_user_management.py#L96
"""
import argparse
import logging

import requests


log = logging.getLogger(__name__)
logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')


# To keep this script simple and avoid authentication and authorization this
# script uses local IAM address instead of going through Admin Router
IAM_BASE_URL = 'http://127.0.0.1:8101'


def add_user(uid: str) -> None:
    """
    Create a user in IAM service:

    https://github.com/dcos/dcos/blob/abaeb5cceedd5661b8d96ff47f8bb5ef212afbdc/packages/dcos-integration-test/extra/test_legacy_user_management.py#L96
    """
    url = '{iam}/acs/api/v1/users/{uid}'.format(
        iam=IAM_BASE_URL,
        uid=uid,
    )
    r = requests.put(url, json={})

    # The 409 response code means that user already exists in the DC/OS IAM
    # service
    if r.status_code == 409:
        log.info('Skipping existing IAM user `%s`', uid)
        return
    else:
        r.raise_for_status()

    log.info('Created IAM user `%s`', uid)


def main() -> None:
    """
    Add user to database with email argument as the user ID.

    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'email',
        type=str,
        help='Identity of the user to add.',
    )
    args = parser.parse_args()
    add_user(args.email)


if __name__ == "__main__":
    main()
