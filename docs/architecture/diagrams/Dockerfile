FROM eclipse-temurin:21-jre-jammy

ARG PLANTUML_VERSION=1.2024.8

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl graphviz \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/plantuml \
    && curl -fsSL "https://github.com/plantuml/plantuml/releases/download/v${PLANTUML_VERSION}/plantuml-${PLANTUML_VERSION}.jar" \
        -o /opt/plantuml/plantuml.jar

WORKDIR /workspace/docs/diagrams

ENTRYPOINT ["java", "-jar", "/opt/plantuml/plantuml.jar"]
CMD ["-tsvg", "-o", "generated", "db-physical-schema.puml"]
