FROM golang:1.24-alpine3.23 AS builder

WORKDIR /build

COPY go.mod .
COPY go.sum .
RUN go mod download

COPY common ./common
COPY gen ./gen
COPY sender-receiver-logic ./sender-receiver-logic
COPY workers/englishFilter ./workers/englishFilter

RUN CGO_ENABLED=0 GOOS=linux go build \
    -o bin/englishFilter \
    ./workers/englishFilter

FROM busybox:latest

COPY --from=builder /build/bin/englishFilter /englishFilter

ENTRYPOINT ["/englishFilter"]
