#!/usr/bin/env python

import argparse
import json
import logging
import os
import random
import shutil
import sys


from dcos_internal_utils import bootstrap
from dcos_internal_utils import exhibitor
from dcos_internal_utils import utils


log = logging.getLogger(__name__)


# TODO all services should check disk location for existing cert/key
# and fall back to generating/fetching from secrets store


def dcos_bouncer(b, opts):
    b.init_acls()
    b.create_master_secrets(opts.zk_master_creds)
    b.bouncer_acls()

    path = '/run/dcos/etc/bouncer'
    b.write_bouncer_env(path)
    shutil.chown(path, user='dcos_bouncer')

    # TODO write /var/lib/dcos/auth-token-secret in HS256 mode

    keypath = '/run/dcos/pki/tls/private/bouncer.key'
    b.write_private_key('dcos_bouncer', keypath)
    shutil.chown(keypath, user='dcos_bouncer')


def dcos_secrets(b, opts):
    b.init_acls()
    b.create_master_secrets(opts.zk_master_creds)
    b.dcos_secrets_acls()
    path = '/run/dcos/etc/dcos-secrets.env'
    b.write_secrets_env(path)
    shutil.chown(path, user='dcos_secrets')
    try:
        os.makedirs('/var/lib/dcos/secrets')
    except FileExistsError:
        pass
    shutil.chown('/var/lib/dcos/secrets', user='dcos_secrets')
    try:
        os.makedirs('/var/lib/dcos/secrets/vault/', exist_ok=True)
    except FileExistsError:
        pass
    shutil.chown('/var/lib/dcos/secrets/vault/', user='dcos_secrets')
    try:
        os.makedirs('/var/lib/dcos/secrets/vault/default', exist_ok=True)
    except FileExistsError:
        pass
    shutil.chown('/var/lib/dcos/secrets/vault/default', user='dcos_secrets')


def dcos_vault_default(b, opts):
    b.init_acls()
    b.create_master_secrets(opts.zk_master_creds)
    b.dcos_vault_default_acls()
    path = '/run/dcos/etc/dcos-vault_default.env'
    b.write_vault_default_env(path)
    shutil.chown(path, user='dcos_vault')
    shutil.chown('/var/lib/dcos/secrets', user='dcos_secrets')
    hcl = '/run/dcos/etc/vault.hcl'
    if not os.path.exists(hcl):
        open(hcl, 'a').close()
        shutil.chown(hcl, user='dcos_vault')


def dcos_ca(b, opts):
    b.init_acls()
    b.create_master_secrets(opts.zk_master_creds)
    b.dcos_ca_acls()
    path = '/run/dcos/etc/dcos-ca/dbconfig.json'
    b.write_dcos_ca_creds(src='/opt/mesosphere/etc/dcos-ca/dbconfig.json.example',
                          dst=path)
    shutil.chown(path, user='dcos_ca')
    path = '/run/dcos/pki/CA/certs/ca.crt'
    b.write_CA_certificate(filename=path)
    shutil.chown(path, user='dcos_ca')
    path = '/run/dcos/pki/CA/private/ca.key'
    b.write_CA_key(path)
    shutil.chown(path, user='dcos_ca')


def dcos_mesos_master(b, opts):
    b.init_acls()
    b.create_master_secrets(opts.zk_master_creds)
    b.mesos_acls()

    b.write_mesos_master_env('/run/dcos/etc/mesos-master')

    keypath = '/run/dcos/pki/tls/private/mesos-master.key'
    crtpath = '/run/dcos/pki/tls/certs/mesos-master.crt'
    b.write_key_certificate('Mesos Master', keypath, crtpath, master=True)

    # agent secrets are needed for it to contact the master
    b.create_agent_secrets(opts.zk_agent_digest)

    b.create_agent_service_accounts()


def dcos_mesos_agent(b, opts):
    b.read_agent_secrets()

    b.write_CA_certificate()

    keypath = '/run/dcos/pki/tls/private/mesos-slave.key'
    crtpath = '/run/dcos/pki/tls/certs/mesos-slave.crt'
    b.write_key_certificate('Mesos Agent', keypath, crtpath, service_account='dcos_agent')

    svc_acc_creds_fn = '/run/dcos/etc/mesos/agent_service_account.json'
    b.write_service_account_credentials('dcos_mesos_agent', svc_acc_creds_fn, b64=True)

    # TODO orchestration API should handle this in the future
    keypath = '/run/dcos/pki/tls/private/scheduler.key'
    crtpath = '/run/dcos/pki/tls/certs/scheduler.crt'
    b.write_key_certificate('Mesos Schedulers', keypath, crtpath, service_account='dcos_agent', key_mode=0o644)

    svc_acc_creds_fn = '/run/dcos/etc/mesos/scheduler_service_account.json'
    b.write_service_account_credentials('dcos_scheduler', svc_acc_creds_fn, b64=True)


def dcos_mesos_agent_public(b, opts):
    b.read_agent_secrets()
    b.write_CA_certificate()

    keypath = '/run/dcos/pki/tls/private/mesos-slave-public.key'
    crtpath = '/run/dcos/pki/tls/certs/mesos-slave-public.crt'
    b.write_key_certificate('Mesos Public Agent', keypath, crtpath, service_account='dcos_agent')

    svc_acc_creds_fn = '/run/dcos/etc/mesos/agent_service_account.json'
    b.write_service_account_credentials('dcos_mesos_agent_public', svc_acc_creds_fn, b64=True)


def dcos_marathon(b, opts):
    b.init_acls()
    b.create_master_secrets(opts.zk_master_creds)
    b.marathon_acls()

    key = '/run/dcos/pki/tls/private/marathon.key'
    crt = '/run/dcos/pki/tls/certs/marathon.crt'
    b.write_key_certificate('Marathon', key, crt, master=True, marathon=True)
    shutil.chown(key, user='dcos_marathon')
    shutil.chown(crt, user='dcos_marathon')

    ca = '/run/dcos/pki/CA/certs/ca.crt'
    b.write_CA_certificate(filename=ca)
    shutil.chown(ca, user='dcos_marathon')

    ts = '/run/dcos/pki/CA/certs/cacerts.jks'
    b.write_truststore(ts, ca)
    os.chmod(ts, 0o644)

    env = '/run/dcos/etc/marathon/tls.env'
    b.write_marathon_env(key, crt, ca, env)
    shutil.chown(env, user='dcos_marathon')
    shutil.chown('/run/dcos/pki/tls/private/marathon.jks', user='dcos_marathon')

    b.create_service_account('dcos_marathon')
    svc_acc_creds_fn = '/run/dcos/etc/marathon/service_account.json'
    b.write_service_account_credentials('dcos_marathon', svc_acc_creds_fn, b64=True)
    shutil.chown(svc_acc_creds_fn, user='dcos_marathon')


def dcos_metronome(b, opts):
    b.init_acls()
    b.create_master_secrets(opts.zk_master_creds)

    b.metronome_acls()

    key = '/run/dcos/pki/tls/private/metronome.key'
    crt = '/run/dcos/pki/tls/certs/metronome.crt'
    b.write_key_certificate('Metronome', key, crt, master=True)
    shutil.chown(key, user='dcos_metronome')
    shutil.chown(crt, user='dcos_metronome')

    ca = '/run/dcos/pki/CA/certs/ca.crt'
    b.write_CA_certificate(filename=ca)
    shutil.chown(ca, user='dcos_metronome')

    ts = '/run/dcos/pki/CA/certs/cacerts.jks'
    b.write_truststore(ts, ca)
    os.chmod(ts, 0o644)

    env = '/run/dcos/etc/metronome/tls.env'
    b.write_metronome_env(key, crt, ca, env)
    shutil.chown(env, user='dcos_metronome')
    shutil.chown('/run/dcos/pki/tls/private/metronome.jks', user='dcos_metronome')

    b.create_service_account('dcos_metronome')
    svc_acc_creds_fn = '/run/dcos/etc/metronome/service_account.json'
    b.write_service_account_credentials('dcos_metronome', svc_acc_creds_fn, b64=True)
    shutil.chown(svc_acc_creds_fn, user='dcos_metronome')

    shutil.chown('/run/dcos/etc/metronome', user='dcos_metronome')


def dcos_mesos_dns(b, opts):
    b.init_acls()
    b.create_master_secrets(opts.zk_master_creds)
    b.create_service_account('dcos_mesos_dns')

    path = '/run/dcos/pki/CA/certs/ca.crt'
    b.write_CA_certificate(filename=path)
    shutil.chown(path, user='dcos_mesos_dns')

    svc_acc_creds_fn = '/run/dcos/etc/mesos-dns/iam.json'
    b.write_service_account_credentials('dcos_mesos_dns', svc_acc_creds_fn)
    shutil.chown(svc_acc_creds_fn, user='dcos_mesos_dns')


def dcos_adminrouter(b, opts):
    b.init_acls()
    b.cluster_id()

    # TODO review adminrouter, bouncer and /var/lib/dcos/auth-token-secret
    # think about upgrade vs RS256-from-the-start

    b.create_master_secrets(opts.zk_master_creds)
    b.create_service_account('dcos_adminrouter')

    keypath = '/run/dcos/pki/tls/private/adminrouter.key'
    crtpath = '/run/dcos/pki/tls/certs/adminrouter.crt'

    extra_san = []
    internal_lb = os.getenv('MASTER_INTERNAL_LB_DNSNAME')
    if internal_lb:
        extra_san = [internal_lb]

    b.write_key_certificate('AdminRouter', keypath, crtpath, master=True, extra_san=extra_san)

    b.write_jwks_public_keys('/run/dcos/etc/jwks.pub')

    b.write_service_auth_token('dcos_adminrouter', '/run/dcos/etc/adminrouter.env', exp=0)


def dcos_adminrouter_agent(b, opts):
    b.read_agent_secrets()

    b.write_CA_certificate()

    keypath = '/run/dcos/pki/tls/private/adminrouter-agent.key'
    crtpath = '/run/dcos/pki/tls/certs/adminrouter-agent.crt'
    b.write_key_certificate('Adminrouter Agent', keypath, crtpath, service_account='dcos_agent')

    b.write_jwks_public_keys('/run/dcos/etc/jwks.pub')

    # write_service_auth_token must follow
    # write_CA_certificate on agents to allow
    # for a verified HTTPS connection on login
    b.write_service_auth_token('dcos_adminrouter_agent', '/run/dcos/etc/adminrouter.env', exp=0)


def dcos_spartan(b, opts):
    if os.path.exists('/etc/mesosphere/roles/master'):
        return dcos_spartan_master(b, opts)
    else:
        return dcos_spartan_agent(b, opts)


def dcos_spartan_master(b, opts):
    b.init_acls()
    b.create_master_secrets(opts.zk_master_creds)

    b.write_CA_certificate()

    key = '/run/dcos/pki/tls/private/spartan.key'
    crt = '/run/dcos/pki/tls/certs/spartan.crt'
    b.write_key_certificate('Spartan Master', key, crt, master=True)


def dcos_spartan_agent(b, opts):
    b.read_agent_secrets()

    b.write_CA_certificate()

    keypath = '/run/dcos/pki/tls/private/spartan.key'
    crtpath = '/run/dcos/pki/tls/certs/spartan.crt'
    b.write_key_certificate('Spartan Agent', keypath, crtpath, service_account='dcos_agent')


def dcos_erlang_service(servicename, b, opts):
    if servicename == 'networking_api':
        for file in ['/opt/mesosphere/active/networking_api/networking_api/releases/0.0.1/vm.args.2.config',
                     '/opt/mesosphere/active/networking_api/networking_api/releases/0.0.1/sys.config.2.config']:
            if not os.path.exists(file):
                open(file, 'a').close()
                shutil.chown(file, user='dcos_networking_api')
        shutil.chown('/opt/mesosphere/active/networking_api/networking_api', user='dcos_networking_api')
        shutil.chown('/opt/mesosphere/active/networking_api/networking_api/log', user='dcos_networking_api')
    if os.path.exists('/etc/mesosphere/roles/master'):
        log.info('%s master bootstrap', servicename)
        return dcos_erlang_service_master(servicename, b, opts)
    else:
        log.info('%s agent bootstrap', servicename)
        return dcos_erlang_service_agent(servicename, b, opts)


def dcos_erlang_service_master(servicename, b, opts):
    b.init_acls()
    b.create_master_secrets(opts.zk_master_creds)
    b.create_service_account('dcos_{}_master'.format(servicename))

    user = 'dcos_' + servicename

    ca = '/run/dcos/pki/CA/certs/ca.crt'
    b.write_CA_certificate(filename=ca)
    if servicename == 'networking_api':
        shutil.chown(ca, user=user)

    friendly_name = servicename[0].upper() + servicename[1:]
    key = '/run/dcos/pki/tls/private/{}.key'.format(servicename)
    crt = '/run/dcos/pki/tls/certs/{}.crt'.format(servicename)
    b.write_key_certificate(friendly_name, key, crt)
    if servicename == 'networking_api':
        shutil.chown(key, user=user)
        shutil.chown(crt, user=user)

    auth_env = '/run/dcos/etc/{}_auth.env'.format(servicename)
    b.write_service_auth_token('dcos_{}_master'.format(servicename), auth_env, exp=0)
    if servicename == 'networking_api':
        shutil.chown(auth_env, user=user)


def dcos_erlang_service_agent(servicename, b, opts):
    b.read_agent_secrets()

    user = 'dcos_' + servicename

    ca = '/run/dcos/pki/CA/certs/ca.crt'
    b.write_CA_certificate(filename=ca)
    if servicename == 'networking_api':
        shutil.chown(ca, user=user)

    friendly_name = servicename[0].upper() + servicename[1:]
    key = '/run/dcos/pki/tls/private/{}.key'.format(servicename)
    crt = '/run/dcos/pki/tls/certs/{}.crt'.format(servicename)
    b.write_key_certificate(friendly_name, key, crt, service_account='dcos_agent')
    if servicename == 'networking_api':
        shutil.chown(key, user=user)
        shutil.chown(crt, user=user)

    auth_env = '/run/dcos/etc/{}_auth.env'.format(servicename)
    b.write_service_auth_token('dcos_{}_agent'.format(servicename), auth_env, exp=0)
    if servicename == 'networking_api':
        shutil.chown(auth_env, user=user)


def dcos_cosmos(b, opts):
    b.init_acls()
    b.create_master_secrets(opts.zk_master_creds)
    b.cosmos_acls()

    key = '/run/dcos/pki/tls/private/cosmos.key'
    crt = '/run/dcos/pki/tls/certs/cosmos.crt'
    b.write_key_certificate('Cosmos', key, crt, master=True)
    shutil.chown(key, user='dcos_cosmos')
    shutil.chown(crt, user='dcos_cosmos')

    ca = '/run/dcos/pki/CA/certs/ca.crt'
    b.write_CA_certificate(filename=ca)
    shutil.chown(ca, user='dcos_cosmos')

    ts = '/run/dcos/pki/CA/certs/cacerts.jks'
    b.write_truststore(ts, ca)
    os.chmod(ts, 0o644)

    env = '/run/dcos/etc/cosmos.env'
    b.write_cosmos_env(key, crt, ca, env)
    shutil.chown(env, user='dcos_cosmos')


def dcos_signal(b, opts):
    b.init_acls()
    b.cluster_id()
    b.create_master_secrets(opts.zk_master_creds)
    b.create_service_account('dcos_signal_service')

    svc_acc_creds_fn = '/run/dcos/etc/signal-service/service_account.json'
    b.write_service_account_credentials('dcos_signal_service', svc_acc_creds_fn)
    shutil.chown(svc_acc_creds_fn, user='dcos_signal')


def dcos_ddt_master(b, opts):
    b.init_acls()
    b.create_master_secrets(opts.zk_master_creds)
    b.create_service_account('dcos_ddt_master')
    svc_acc_creds_fn = '/run/dcos/etc/ddt/master_service_account.json'
    b.write_service_account_credentials('dcos_ddt_master', svc_acc_creds_fn)
    shutil.chown(svc_acc_creds_fn, user='dcos_3dt')

    # ddt agent secrets are needed for it to contact the ddt master
    b.create_agent_secrets(opts.zk_agent_digest)
    b.create_service_account('dcos_ddt_agent')


def dcos_ddt_agent(b, opts):
    b.read_ddt_agent_secrets()
    svc_acc_creds_fn = '/run/dcos/etc/ddt/agent_service_account.json'
    b.write_service_account_credentials('dcos_ddt_agent', svc_acc_creds_fn)
    shutil.chown(svc_acc_creds_fn, user='dcos_3dt')


def dcos_history_service(b, opts):
    b.create_master_secrets(opts.zk_master_creds)
    b.create_service_account('dcos_history_service')

    svc_acc_creds_fn = '/run/dcos/etc/history-service/service_account.json'
    b.write_service_account_credentials('dcos_history_service', svc_acc_creds_fn)
    shutil.chown(svc_acc_creds_fn, user='dcos_history')

    ca = '/run/dcos/pki/CA/certs/ca.crt'
    b.write_CA_certificate(filename=ca)
    shutil.chown(ca, user='dcos_history')

    env = '/run/dcos/etc/history-service/history-service.env'
    b.write_history_service_env(ca, env)
    shutil.chown(env, user='dcos_history')
    os.makedirs('/var/lib/dcos/dcos-history', exist_ok=True)
    shutil.chown('/var/lib/dcos/dcos-history', user='dcos_history')


bootstrappers = {
    'dcos-adminrouter': dcos_adminrouter,
    'dcos-adminrouter-agent': dcos_adminrouter_agent,
    'dcos-bouncer': dcos_bouncer,
    'dcos-ca': dcos_ca,
    'dcos-cosmos': dcos_cosmos,
    'dcos-ddt-agent': dcos_ddt_agent,
    'dcos-ddt-master': dcos_ddt_master,
    'dcos-history-service': dcos_history_service,
    'dcos-marathon': dcos_marathon,
    'dcos-mesos-agent': dcos_mesos_agent,
    'dcos-mesos-agent-public': dcos_mesos_agent_public,
    'dcos-mesos-dns': dcos_mesos_dns,
    'dcos-mesos-master': dcos_mesos_master,
    'dcos-metronome': dcos_metronome,
    'dcos-minuteman': (lambda b, opts: dcos_erlang_service('minuteman', b, opts)),
    'dcos-navstar': (lambda b, opts: dcos_erlang_service('navstar', b, opts)),
    'dcos-networking_api': (lambda b, opts: dcos_erlang_service('networking_api', b, opts)),
    'dcos-secrets': dcos_secrets,
    'dcos-signal': dcos_signal,
    'dcos-spartan': dcos_spartan,
    'dcos-vault_default': dcos_vault_default,
}


def main():
    if os.getuid() != 0:
        log.error('bootstrap must be run as root')
        sys.exit(1)

    opts = parse_args()

    logging.basicConfig(format='[%(levelname)s] %(message)s', level='INFO')
    log.setLevel(logging.DEBUG)

    log.info('Clearing proxy environment variables')
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('http_proxy', None)
    os.environ.pop('HTTPS_PROXY', None)
    os.environ.pop('https_proxy', None)
    os.environ.pop('NO_PROXY', None)
    os.environ.pop('no_proxy', None)

    dirs = [
        '/run/dcos',
        '/run/dcos/etc',
        '/run/dcos/etc/ddt',
        '/run/dcos/etc/marathon',
        '/run/dcos/etc/mesos',
        '/run/dcos/etc/mesos-dns',
        '/run/dcos/etc/dcos-ca',
        '/run/dcos/etc/metronome',
        '/run/dcos/etc/history-service',
        '/run/dcos/etc/signal-service',
        '/run/dcos/pki/tls/private',
        '/run/dcos/pki/tls/certs',
        '/run/dcos/pki/CA/certs',
        '/run/dcos/pki/CA/private'
    ]
    for d in dirs:
        log.info('Preparing directory {}'.format(d))
        os.makedirs(d, exist_ok=True)

    exhibitor.wait(opts.master_count)

    def _verify_and_set_zk_creds(credentials_path, credentials_type=None):
        if os.path.exists(credentials_path):
            log.info('Reading {credentials_type} credentials from {credentials_path}'.format(
                credentials_type=credentials_type, credentials_path=credentials_path))
            return utils.read_file_line(credentials_path)
        log.info('{credentials_type} credentials not available'.format(credentials_type=credentials_type))
        return None

    opts.zk_super_creds = _verify_and_set_zk_creds(opts.zk_super_creds, "ZooKeeper super")
    opts.zk_master_creds = _verify_and_set_zk_creds(opts.zk_master_creds, "ZooKeeper master")
    opts.zk_agent_creds = _verify_and_set_zk_creds(opts.zk_agent_creds, "ZooKeeper agent")
    opts.zk_agent_digest = _verify_and_set_zk_creds(opts.zk_agent_digest, "ZooKeeper agent digest")

    if opts.zk_super_creds:
        log.info('Using ZK super credentials')
        zk_creds = opts.zk_super_creds
    else:
        log.info('Using ZK agent credentials')
        zk_creds = opts.zk_agent_creds

    log.info('ZK: %s', opts.zk)
    log.info('IAM URL: %s', opts.iam_url)
    log.info('CA URL: %s', opts.ca_url)

    b = bootstrap.Bootstrapper(opts.zk, zk_creds, opts.iam_url, opts.ca_url)

    for service in opts.services:
        if service not in bootstrappers:
            log.error('Unknown service: {}'.format(service))
            sys.exit(1)
        log.debug('bootstrapping {}'.format(service))
        bootstrappers[service](b, opts)


def parse_args():
    if os.path.exists('/etc/mesosphere/roles/master'):
        zk_default = '127.0.0.1:2181'
        iam_default = 'http://127.0.0.1:8101'
        ca_default = 'http://127.0.0.1:8888'
    else:
        if os.getenv('MASTER_SOURCE') == 'master_list':
            # Spartan agents with static master list
            with open('/opt/mesosphere/etc/master_list', 'r') as f:
                master_list = json.load(f)
            assert len(master_list) > 0
            leader = random.choice(master_list)
        elif os.getenv('EXHIBITOR_ADDRESS'):
            # Spartan agents on AWS
            leader = os.getenv('EXHIBITOR_ADDRESS')
        else:
            # any other agent service
            leader = 'leader.mesos'

        # TODO figure out if SSL is enabled in the cluster
        zk_default = leader + ':2181'
        iam_default = 'https://' + leader
        ca_default = 'https://' + leader

    parser = argparse.ArgumentParser()
    parser.add_argument('services', nargs='+')
    parser.add_argument(
        '--zk',
        default=zk_default,
        help='Host string passed to Kazoo client constructor.')
    parser.add_argument(
        '--zk_super_creds',
        default='/opt/mesosphere/etc/zk_super_credentials',
        help='File with ZooKeeper super credentials')
    parser.add_argument(
        '--zk_master_creds',
        default='/opt/mesosphere/etc/zk_master_credentials',
        help='File with ZooKeeper master credentials')
    parser.add_argument(
        '--zk_agent_creds',
        default='/opt/mesosphere/etc/zk_agent_credentials',
        help='File with ZooKeeper agent credentials')
    parser.add_argument(
        '--zk_agent_digest',
        default='/opt/mesosphere/etc/zk_agent_digest',
        help='File with ZooKeeper agent digest')
    parser.add_argument(
        '--master_count',
        default='/opt/mesosphere/etc/master_count',
        help='File with number of master servers')
    parser.add_argument(
        '--iam_url',
        default=iam_default,
        help='IAM Service (Bouncer) URL')
    parser.add_argument(
        '--ca_url',
        default=ca_default,
        help='CA URL')
    return parser.parse_args()


if __name__ == '__main__':
    main()
