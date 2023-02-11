FROM trusted-container-images.internal.degiro.eu/python:3.10-slim

WORKDIR /app

# Install external CLI dependencies
ENV HELM_VERSION=3.7.1 \
    KUBECTL_VERSION=1.19.2

RUN apt-get update && \
    apt-get install -y curl && \
    # Helm 3
    curl --location --remote-name https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz && \
    tar -zxvf helm-v${HELM_VERSION}-linux-amd64.tar.gz && \
    mv linux-amd64/helm /usr/local/bin/helm && \
    rm -rf helm-v${HELM_VERSION}-linux-amd64.tar.gz linux-amd64 && \
    # kubectl 1.19
    curl --location --remote-name https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/amd64/kubectl && \
    # Checksum file
    curl --location --remote-name https://dl.k8s.io/v${KUBECTL_VERSION}/bin/linux/amd64/kubectl.sha256 && \
    echo "$(cat kubectl.sha256) kubectl" | sha256sum --check && \
    install --owner=root --group=root -m 0755 kubectl /usr/local/bin/kubectl && \
    rm -f kubectl.sha256 kubectl && \
    # Clean-up
    apt-get remove -y curl && \
    apt-get purge && \
    apt-get autoremove -y

COPY requirements.txt .

RUN pip3 install -r requirements.txt

COPY . .

CMD [ "python3", "-m", "flask", "run", "--host=0.0.0.0" ]
