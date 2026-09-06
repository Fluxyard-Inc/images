# Supply a tested digest reference, never a floating production tag.
ARG WORKSPACE_IMAGE
FROM ${WORKSPACE_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/Fluxyard-Inc/images"

USER root
COPY custom/run.py /opt/project/run.py
RUN printf 'masked by volume-nocopy workspace storage\n' > /workspace/image-sentinel
ENV PROJECT_NAME=derived-custom-example

# Deliberately conflicting metadata proves workspace_v1's fixed overrides.
# These are not instructions to run a root shell or publish a service.
WORKDIR /opt/project
USER 0:0
ENTRYPOINT ["/bin/bash", "-c", "echo IMAGE_ENTRYPOINT_SHOULD_NOT_RUN; exit 99"]
CMD ["image-cmd-should-not-run"]
HEALTHCHECK --interval=1s CMD ["/bin/false"]
STOPSIGNAL SIGUSR1
