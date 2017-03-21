# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import requests
import pytest

from generic_test_code.common import (
    assert_endpoint_response,
    assert_iam_queried_for_uid_and_rid,
    generic_correct_upstream_dest_test,
    generic_valid_user_is_permitted_test,
    verify_header,
)
from generic_test_code.ee import assert_iam_queried_for_uid_and_rid
from util import SearchCriteria, iam_denies_all_requests

acl_endpoints = [
    ('/acs/acl-schema.json', 'dcos:adminrouter:acs'),
    ('/exhibitor/foo/bar', 'dcos:adminrouter:ops:exhibitor'),
    ('/acs/api/v1/foo/bar', 'dcos:adminrouter:acs'),
    ('/ca/api/v2/certificates', 'dcos:adminrouter:ops:ca:ro'),
    ('/ca/api/v2/newcert', 'dcos:adminrouter:ops:ca:rw'),
    ('/ca/api/v2/newkey', 'dcos:adminrouter:ops:ca:rw'),
    ('/ca/api/v2/sign', 'dcos:adminrouter:ops:ca:rw'),
    ('/mesos/master/state-summary', 'dcos:adminrouter:ops:mesos'),
    ('/package/foo/bar', 'dcos:adminrouter:package'),
    ('/cosmos/service/foo/bar', 'dcos:adminrouter:package'),
    ('/networking/api/v1/foo/bar', 'dcos:adminrouter:ops:networking'),
    ('/slave/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1', 'dcos:adminrouter:ops:slave'),
    ('/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1', 'dcos:adminrouter:ops:slave'),
    ('/service/nginx-alwaysthere/foo/bar', 'dcos:adminrouter:service:nginx-alwaysthere'),
    ('/metadata', "dcos:adminrouter:ops:metadata"),
    ('/dcos-metadata/bootstrap-config.json', "dcos:adminrouter:ops:metadata"),
    ('/pkgpanda/active.buildinfo.full.json', "dcos:adminrouter:ops:metadata"),
    ('/dcos-history-service/foo/bar', 'dcos:adminrouter:ops:historyservice'),
    ('/mesos_dns/foo/bar', 'dcos:adminrouter:ops:mesos-dns'),
    ('/system/health/v1/foo/bar', 'dcos:adminrouter:ops:system-health'),
    ('/system/v1/logs/v1/foo/bar', 'dcos:adminrouter:ops:system-logs'),
    ('/system/v1/metrics/foo/bar', 'dcos:adminrouter:ops:system-metrics'),
]

authed_endpoints = [
    ('/secrets/v1', 'dcos:adminrouter:secrets'),
    ('/capabilities', 'dcos:adminrouter:capabilities'),
    ('/navstar/lashup/key', 'dcos:adminrouter:navstar-lashup-key'),
    ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1/logs/v1',
     'dcos:adminrouter:system:agent'),
    ('/system/v1/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1/metrics/v0',
     'dcos:adminrouter:system:agent'),
    ('/system/v1/leader/marathon',
     'dcos:adminrouter:system:leader:marathon'),
    ('/system/v1/leader/mesos',
     'dcos:adminrouter:system:leader:mesos'),
]


class TestAuthEnforcementEE:
    """Tests full request cycle and all components involved in authentication
    authorization for each all protected paths"""

    @pytest.mark.parametrize("path,rid", acl_endpoints)
    def test_if_unauthn_user_is_forbidden_access(self,
                                                 mocker,
                                                 master_ar_process,
                                                 path,
                                                 rid,
                                                 ):
        log_messages = {
            'type=audit .*' +
            'object={} .*'.format(rid) +
            'result=deny .*' +
            'reason="not authenticated" .*' +
            'request_uri=' + path: SearchCriteria(1, True),
            }
        assert_endpoint_response(
            master_ar_process, path, 401, assert_stderr=log_messages)

    @pytest.mark.parametrize("path,rid", acl_endpoints)
    def test_if_authorized_user_is_allowed(self,
                                           master_ar_process,
                                           valid_user_header,
                                           path,
                                           rid,
                                           mocker,
                                           ee_static_files):
        log_messages = {
            'UID from valid JWT: `bozydar`': SearchCriteria(1, True),
            'type=audit .*' +
            'object={} .*'.format(rid) +
            'result=allow .*' +
            'reason="Bouncer PQ response" .*' +
            'request_uri=' + path: SearchCriteria(1, True),
            }

        with assert_iam_queried_for_uid_and_rid(mocker, 'bozydar', rid):
            assert_endpoint_response(
                master_ar_process,
                path,
                200,
                assert_stderr=log_messages,
                headers=valid_user_header
                )

    @pytest.mark.parametrize("path,rid", acl_endpoints)
    def test_if_unauthorized_user_is_forbidden_access(self,
                                                      master_ar_process,
                                                      valid_user_header,
                                                      path,
                                                      rid,
                                                      mocker,
                                                      ee_static_files,
                                                      iam_deny_all):
        log_messages = {
            'UID from valid JWT: `bozydar`': SearchCriteria(1, True),
            'type=audit .*' +
            'object={} .*'.format(rid) +
            'result=deny .*' +
            'reason="Bouncer PQ response" .*' +
            'request_uri=' + path: SearchCriteria(1, True),
            }

        with assert_iam_queried_for_uid_and_rid(mocker, 'bozydar', rid):
            assert_endpoint_response(
                master_ar_process,
                path,
                403,
                assert_stderr=log_messages,
                headers=valid_user_header
                )

    @pytest.mark.parametrize("path,rid", authed_endpoints)
    def test_if_known_user_is_permitted_access(self,
                                               master_ar_process,
                                               valid_user_header,
                                               path,
                                               rid,
                                               mocker):
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8101',
            func_name='record_requests',
            )

        test_path = path + "/foo/bar"
        log_messages = {
            'UID from valid JWT: `bozydar`': SearchCriteria(1, True),
            'type=audit .*' +
            'object={} .*'.format(rid) +
            'result=allow .*' +
            'reason="authenticated \(all users are allowed to access\)" .*' +
            'request_uri=' + test_path: SearchCriteria(1, True),
            }

        assert_endpoint_response(
            master_ar_process,
            test_path,
            200,
            assert_stderr=log_messages,
            headers=valid_user_header
            )

        upstream_requests = mocker.send_command(
            endpoint_id='http://127.0.0.1:8101',
            func_name='get_recorded_requests',
            )
        assert len(upstream_requests) == 0

    def test_if_user_is_allowed_to_get_own_permisions(self,
                                                      master_ar_process,
                                                      valid_user_header,
                                                      mocker,
                                                      iam_deny_all
                                                      ):
        log_messages = {
            'UID from valid JWT: `bozydar`': SearchCriteria(1, True),
            'type=audit .*' +
            'object=dcos:iam:users:bozydar:permissions .*' +
            'result=allow .*' +
            'reason="user requests his/her own permissions" .*':
                SearchCriteria(1, True),
            }

        assert_endpoint_response(
            master_ar_process,
            '/acs/api/v1/users/bozydar/permissions',
            200,
            assert_stderr=log_messages,
            headers=valid_user_header,
            assertions=[
                lambda r: r.json()['user'] == 'bozydar',
                lambda r: r.json()['permissions'],
                ]
            )

    def test_if_getting_different_user_permissions_is_authorized(self,
                                                                 master_ar_process,
                                                                 valid_user_header,
                                                                 mocker,
                                                                 iam_permit_all
                                                                 ):
        log_messages = {
            'UID from valid JWT: `bozydar`': SearchCriteria(1, True),
            'type=audit .*' +
            'object=dcos:adminrouter:acs .*' +
            'result=allow .*' +
            'reason="Bouncer PQ response" .*':
                SearchCriteria(1, True),
            }
        with assert_iam_queried_for_uid_and_rid(mocker, 'bozydar', 'dcos:adminrouter:acs'):
            assert_endpoint_response(
                master_ar_process,
                '/acs/api/v1/users/root/permissions',
                200,
                assert_stderr=log_messages,
                headers=valid_user_header,
                assertions=[
                    lambda r: r.json()['user'] == 'root',
                    lambda r: r.json()['permissions'],
                    ]
                )

    def test_if_getting_different_user_permissions_is_denied(self,
                                                             master_ar_process,
                                                             valid_user_header,
                                                             mocker,
                                                             iam_deny_all
                                                             ):
        log_messages = {
            'UID from valid JWT: `bozydar`': SearchCriteria(1, True),
            'type=audit .*' +
            'object=dcos:adminrouter:acs .*' +
            'result=deny .*' +
            'reason="Bouncer PQ response" .*':
                SearchCriteria(1, True),
            }

        with assert_iam_queried_for_uid_and_rid(mocker, 'bozydar', 'dcos:adminrouter:acs'):
            assert_endpoint_response(
                master_ar_process,
                '/acs/api/v1/users/root/permissions',
                403,
                assert_stderr=log_messages,
                headers=valid_user_header,
                )

    def test_if_exhibitor_basic_auth_is_passed_to_upstream(self,
                                                           master_ar_process,
                                                           valid_user_header
                                                           ):
        r = requests.get(
            master_ar_process.make_url_from_path('/exhibitor/foo/bar'),
            headers=valid_user_header)

        assert r.status_code == 200

        headers = r.json()['headers']
        verify_header(headers, 'Authorization', 'Basic {}'.format(
            master_ar_process.env['EXHIBITOR_ADMIN_HTTPBASICAUTH_CREDS']
            ))

    @pytest.mark.parametrize("path,rid", acl_endpoints)
    def test_if_acl_validation_doesnt_pass_headers_to_bouncer(
            self,
            master_ar_process,
            valid_user_header,
            path,
            rid,
            mocker,
            ):
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8101',
            func_name='record_requests',
            )
        mocker.send_command(
            endpoint_id='http://127.0.0.1:8101',
            func_name='record_requests',
            )

        headers = {"CUSTOM_HEADER": "CUSTOM_VALUE"}
        headers.update(valid_user_header)
        generic_valid_user_is_permitted_test(
            master_ar_process,
            headers,
            path)

        requests = mocker.send_command(
            endpoint_id='http://127.0.0.1:8101',
            func_name='get_recorded_requests',
            )

        last_request = requests[-1]
        # In case of /acs/api/v1 two requests will be sent to the bouncer mock
        # endpoint so work with first request that was issued by auth.lua
        if path.startswith('/acs/api/v1/'):
            last_request = requests[-2]

        header_names = set(map(lambda h: h[0], last_request["headers"]))
        assert "CUSTOM_HEADER" not in header_names
        assert "Authorization" not in header_names


class TestHealthEndpointEE:
    def test_if_request_is_sent_to_correct_upstream(self,
                                                    master_ar_process,
                                                    valid_user_header
                                                    ):

        generic_correct_upstream_dest_test(master_ar_process,
                                           valid_user_header,
                                           '/system/health/v1/foo/bar',
                                           'http:///run/dcos/3dt.sock',
                                           )
