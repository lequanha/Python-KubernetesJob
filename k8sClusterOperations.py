import os
import logging
import json
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from securityHelpers.decorators import defLogger

log = logging.getLogger(__name__)

ENV = os.environ.get('ENVIRONMENT', 'local')

if ENV == 'local':
    config.load_kube_config(context='staging')
else:
    config.load_incluster_config()

batchApiClient = client.BatchV1Api()


@defLogger
def createProjectJob(projName, projId, entId, members, clusterNamespace, components, env, namespace='default',
                     imageTag='latest', clean=False):

    specs = {
        'apiVersion': 'batch/v1',
        'kind': 'Job',
        'metadata': {
            'name': f'project-deployment-{projId}-{projName}',
            'namespace': namespace
        },
        'spec': {
            'backoffLimit': 0,
            'completions': 1,
            'parallelism': 1,
            'template': {
                'spec': {
                    'containers': [
                        {
                            'name': 'project-deployment',
                            'image': f'lequanha/project-deployment:{imageTag}',
                            'imagePullPolicy': 'Always',
                            'env': [
                                {'name': 'PYTHONUNBUFFERED', 'value': '1'},
                                {'name': 'ENVIRONMENT', 'value': env},
                                {'name': 'RELEASE_VERSION', 'value': imageTag},
                                {
                                    'name': 'KEYCLOAK_USER',
                                    'valueFrom': {
                                        'secretKeyRef': {'name': 'keycloak-admin', 'key': 'username'}
                                    }
                                },
                                {
                                    'name': 'KEYCLOAK_PASSWORD',
                                    'valueFrom': {
                                        'secretKeyRef': {'name': 'keycloak-admin', 'key': 'password'}
                                    }
                                },
                                {
                                    'name': 'MAIL_PASSWORD',
                                    'valueFrom': {
                                        'secretKeyRef': {'name': 'external-keys', 'key': 'MANDRILL_PASSWORD'}
                                    }
                                },
                                {
                                    'name': 'PYMSTEAMS_URL',
                                    'valueFrom': {
                                        'secretKeyRef': {'name': 'external-keys', 'key': 'PYMSTEAMS_URL'}
                                    }
                                },
                                {
                                    'name': 'DB_IP',
                                    'valueFrom': {
                                        'secretKeyRef': {'name': 'external-keys', 'key': 'DB_IP'}
                                    }
                                },
                                {
                                    'name': 'DB_PORT',
                                    'valueFrom': {
                                        'secretKeyRef': {'name': 'external-keys', 'key': 'DB_PORT'}
                                    }
                                },
                                {
                                    'name': 'DB_PASSWORD',
                                    'valueFrom': {
                                        'secretKeyRef': {
                                            'name': 'apioperator.lequanha-pgdb-cluster.credentials.postgresql.acid.zalan.do',
                                            'key': 'password'
                                        }
                                    }
                                }
                            ],
                            'resources': {
                                'requests': {'cpu': '100m', 'memory': '200Mi'},
                                'limits': {'cpu': '200m', 'memory': '200Mi'}
                            },
                            'command': [
                                '/bin/sh', '-c',
                                'python3 projectDeployment.py {} {} {} --members \'{}\' --clusterNamespace {} --components {}'
                                .format(projName, projId, entId, json.dumps(members).replace(' ', ''),
                                        clusterNamespace, ' '.join(components))
                            ],
                            'volumeMounts': [{'name': 'cert', 'mountPath': '/cert', 'readOnly': True}]
                        }
                    ],
                    'restartPolicy': 'Never',
                    'imagePullSecrets': [{'name': 'docker-credentials'}],
                    'serviceAccountName': 'internal-kubectl',
                    'volumes': [{'name': 'cert', 'secret': {'secretName': 'lequanha-admin-client-tls'}}]
                }
            }
        }
    }
    if clean:
        specs['spec']['template']['spec']['containers'][0]['command'][2] += ' --clean'
        specs['metadata']['name'] = 'project-clean-{}-{}'.format(projId, projName)
        specs['spec']['ttlSecondsAfterFinished'] = 86400
    try:
        stdResult = batchApiClient.create_namespaced_job(namespace, specs)
        log.debug(f'createProjectJob - clean: {clean}, projName: {projName}, projId: {projId}, stdResult: {stdResult}')
    except ApiException as err:
        log.error(f'createProjectJob - clean: {clean}, projName: {projName}, projId: {projId}, exception: {str(err)}')
        raise err

