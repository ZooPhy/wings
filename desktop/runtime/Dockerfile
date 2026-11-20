# Developer preview: build locally; no unpublished WINGS image is assumed.
# Release CI must record the resulting image digest and conda-explicit.txt.
# The launcher and CI select linux/amd64 with docker build --platform.
FROM --platform=linux/amd64 docker:28.3.3-cli@sha256:0135662b510037ea581d99c2e5929c5e01185139c0b86986a418bd4da0b98a44 AS dockercli-amd64
FROM --platform=linux/arm64 docker:28.3.3-cli@sha256:0135662b510037ea581d99c2e5929c5e01185139c0b86986a418bd4da0b98a44 AS dockercli-arm64
FROM mambaorg/micromamba:2.3.2
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unzip git procps bzip2 make gcc g++ \
    && rm -rf /var/lib/apt/lists/*
COPY --from=dockercli-amd64 /usr/local/bin/docker /opt/wings-desktop/bin/docker-amd64
COPY --from=dockercli-arm64 /usr/local/bin/docker /opt/wings-desktop/bin/docker-arm64
COPY docker-cli.sh /usr/local/bin/docker
RUN chmod 755 /usr/local/bin/docker
COPY environment.yaml /tmp/controller.yaml
RUN micromamba install -y -n base -f /tmp/controller.yaml \
    && micromamba clean --all --yes
ENV PATH=/opt/conda/bin:/usr/local/bin:/usr/bin:/bin \
    CONDA_EXE=/opt/conda/bin/conda CONDA_PYTHON_EXE=/opt/conda/bin/python \
    CONDA_PREFIX=/opt/conda CONDA_DEFAULT_ENV=base CONDA_SUBDIR=linux-64 \
    CONDA_SOLVER=libmamba DOCKER_HOST=unix:///var/run/docker.sock \
    DOCKER_DEFAULT_PLATFORM=linux/amd64 PYTHONUNBUFFERED=1
RUN conda config --system --set channel_priority strict \
    && conda list --explicit > /opt/conda-explicit.txt \
    && python -c 'import numpy, scipy, yaml, arviz; import snakemake' \
    && snakemake --version && docker --version
COPY controller.py proxy.py /opt/wings-desktop/
ENTRYPOINT ["/opt/conda/bin/python", "/opt/wings-desktop/controller.py"]
