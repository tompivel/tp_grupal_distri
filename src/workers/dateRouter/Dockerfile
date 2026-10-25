FROM golang:1.24-alpine3.23 AS builder
LABEL intermediateStageToBeDeleted=true
RUN mkdir -p /build
WORKDIR /build/
COPY go.mod .
COPY go.sum .
COPY common ./common
RUN go mod download
COPY workers/dateRouter ./workers/dateRouter
RUN CGO_ENABLED=0 GOOS=linux go build -o bin/dateRouter ./workers/dateRouter

FROM busybox:latest
COPY --from=builder /build/bin/dateRouter /dateRouter
ENTRYPOINT ["/dateRouter"]
