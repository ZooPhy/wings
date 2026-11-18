# Developer preview: build locally; no unpublished WINGS image is assumed.
# Release CI must record the resulting image digest and conda-explicit.txt.
# The launcher and CI select linux/amd64 with docker build --platform.
FROM docker:28.3.3-cli AS dockercli
FROM mambaorg/micromamba:2.3.2
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unzip git procps bzip2 make gcc g++ \
    && rm -rf /var/lib/apt/lists/*
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
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
