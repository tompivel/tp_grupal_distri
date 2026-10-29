FROM golang:1.24-alpine3.23 AS builder
LABEL intermediateStageToBeDeleted=true
RUN mkdir -p /build
WORKDIR /build/
COPY go.mod .
COPY go.sum .
RUN go mod download
COPY common ./common
COPY gen ./gen
COPY sender-receiver-logic ./sender-receiver-logic
COPY workers/project ./workers/project
RUN CGO_ENABLED=0 GOOS=linux go build -o bin/project ./workers/project

FROM busybox:latest
COPY --from=builder /build/bin/project /project
ENTRYPOINT ["/project"]
