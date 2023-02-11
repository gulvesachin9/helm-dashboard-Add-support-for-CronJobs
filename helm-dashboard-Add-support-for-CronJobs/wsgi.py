import subprocess
import json

from werkzeug.exceptions import HTTPException
from flask import send_from_directory, url_for
from app import create_app

app = create_app()
reserved_namespaces = [
    'kube-system',
    'kube-public',
    'kube-node-lease',
    'local-storage',
    'kube-logs',
    'kafka-operator',
    'kafka-cluster',
    'debezium',
    'ingress-nginx',
    'vmcluster',
    'dg-monitoring',
    'hashicorp-vault',
    'vault-test',
    'monitoring',
    'prometheus',
    'fluentd',
    'eck'
]


def filter_out_reserved_namespaces(release_list):
    for release in release_list:
        if release['namespace'] in reserved_namespaces:
            release_list.remove(release)


@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)


@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP errors
    if isinstance(e, HTTPException):
        return e

    # Now you're handling non-HTTP exceptions only
    app.logger.error('A%s %s occurred:\n\n%s', 'n' if starts_with_a_vowel(type(e).__name__) else '', type(e).__name__,
                     e.args)
    return "Internal error", 500


def starts_with_a_vowel(word: str):
    vowels = ['a', 'e', 'i', 'o', 'u']
    return word[0].lower() in vowels


@app.route('/')
@app.cache.cached(timeout=30)
def create_dashboard_html():
    try:
        # Create a '~/.kube/config' file based on the service account
        subprocess.run('''
            cd /var/run/secrets/kubernetes.io/serviceaccount
            kubectl config set-cluster local --server=https://kubernetes.default --certificate-authority=ca.crt
            kubectl config set-context local --cluster=local
            kubectl config set-credentials helm-dash --token=$(cat token)
            kubectl config set-context local --user=helm-dash
            kubectl config use-context local
        ''',
            shell=True, capture_output=False,
            text=True, check=True)
        helm_list_output = subprocess.run(
            'helm list --all-namespaces --time-format "2006-01-02 15:04" --output json',
            shell=True, capture_output=True,
            text=True, check=True)
        kubectl_ingress_output = subprocess.run(
            'kubectl get ingress --all-namespaces --output json',
            shell=True,
            capture_output=True,
            text=True, check=True)
        kubectl_deployments_output = subprocess.run(
            'kubectl get deployment --all-namespaces --output json',
            shell=True,
            capture_output=True,
            text=True, check=True)
    except subprocess.CalledProcessError as e:
        app.logger.error('Info retrieval from cluster failed:\n%s\n%s', e, e.stderr)
        return "Internal error", 500

    release_list = json.loads(helm_list_output.stdout)
    filtered_releases = [release for release in release_list if release['namespace'] not in reserved_namespaces]
    releases_by_name = {get_release_key(release['name'], release['namespace']): release for release in
                        filtered_releases}

    ingress_list = json.loads(kubectl_ingress_output.stdout)
    link_ingress_to_release(releases_by_name, ingress_list)

    deployments_list = json.loads(kubectl_deployments_output.stdout)
    image_by_release = {
        get_release_key(x['metadata']['labels']['app.kubernetes.io/part-of'], x['metadata']['namespace']):
            x['spec']['template']['spec']['containers'][0][
                'image'] for x in
        deployments_list['items'] if
        'metadata' in x and 'labels' in x['metadata'] and 'app.kubernetes.io/part-of' in x['metadata'][
            'labels']}

    # Remove releases without an image (and thus deployment)
    releases_by_name = {k: v for k, v in releases_by_name.items() if k in image_by_release.keys()}
    add_image_info_to_release(releases_by_name, image_by_release)

    index_template = app.env.get_template("index.html.jinja")
    return index_template.render(helm_list=releases_by_name.values(), ingress_list=ingress_list,
                                 base_url=url_for('create_dashboard_html'))


def get_image_and_version(image):
    if '/' in image:
        without_fqdn = image.split('/', 1)[1]
    else:
        without_fqdn = image
    repository = without_fqdn.split(':')[0]
    version = image.split(':')[-1]
    return repository, version


def get_release_key(release_name, release_namespace):
    return release_name + ':' + release_namespace


def add_ingress_key(release, ingress):
    if 'spec' in ingress and \
            'rules' in ingress['spec'] and \
            len(ingress['spec']['rules']) > 0 and \
            'host' in ingress['spec']['rules'][0] and \
            'http' in ingress['spec']['rules'][0] and \
            'paths' in ingress['spec']['rules'][0]['http'] and \
            len(ingress['spec']['rules'][0]['http']['paths']) > 0 and \
            'path' in ingress['spec']['rules'][0]['http']['paths'][0]:
        if 'ingress' not in release:
            release['ingress'] = []
        release['ingress'].append(ingress['spec']['rules'][0]['host'] +
                                  remove_regexp_at_end(ingress['spec']['rules'][0]['http']['paths'][0]['path']))


def remove_regexp_at_end(text: str):
    if text.rfind(')') != -1 and text.find('(') != -1:
        return text[:text.find('(')]
    else:
        return text


def link_ingress_to_release(releases_by_name, ingress_list):
    # Use a set to prevent multiple deletion attempts for non-DEGIRO releases
    # that have multiple ingresses
    to_be_deleted = set()
    ingresses_with_releases = [ingress for ingress in ingress_list['items'] if
                               release_name_found(ingress, releases_by_name)]
    for ingress in ingresses_with_releases:
        release_name = get_release_key(ingress['metadata']['annotations']['meta.helm.sh/release-name'],
                                       ingress['metadata']['namespace'])
        if is_degiro_app(ingress):
            add_ingress_key(releases_by_name[release_name], ingress)
        else:
            to_be_deleted.add(release_name)

    for release_name in to_be_deleted:
        del releases_by_name[release_name]


def add_image_info_to_release(releases_by_name, image_by_release_label):
    for k, v in releases_by_name.items():
        repository, version = get_image_and_version(image_by_release_label[k])
        v['image_repository'] = repository
        v['image_version'] = version


def release_name_found(ingress, releases_by_name):
    return 'annotations' in ingress['metadata'] and \
           'meta.helm.sh/release-name' in ingress['metadata']['annotations'] and \
           get_release_key(ingress['metadata']['annotations']['meta.helm.sh/release-name'],
                           ingress['metadata']['namespace']) in releases_by_name


def is_degiro_app(ingress):
    return 'metadata' in ingress and \
           'labels' in ingress['metadata'] and \
           ('app.degiro.com/capability' in ingress['metadata']['labels'] or
            'app.degiro.com/tier' in ingress['metadata']['labels'])


if __name__ == "__main__":
    app.run()
