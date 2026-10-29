FROM golang:1.24-alpine3.23 AS builder
WORKDIR /build
COPY go.mod .
COPY go.sum .
RUN go mod download
COPY common ./common
COPY gen ./gen
COPY sender-receiver-logic ./sender-receiver-logic
COPY workers/dateFilter ./workers/dateFilter
RUN CGO_ENABLED=0 GOOS=linux go build \
    -o bin/dateFilter \
    ./workers/dateFilter
FROM busybox:latest
COPY --from=builder /build/bin/dateFilter /dateFilter
ENTRYPOINT ["/dateFilter"]