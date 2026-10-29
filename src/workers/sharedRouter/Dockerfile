FROM golang:1.24-alpine3.23 AS builder
LABEL intermediateStageToBeDeleted=true
RUN mkdir -p /build
WORKDIR /build/
COPY go.mod .
COPY go.sum .
RUN go mod download
COPY common ./common
COPY workers/sharedRouter ./workers/sharedRouter
RUN CGO_ENABLED=0 GOOS=linux go build -o bin/sharedRouter ./workers/sharedRouter

FROM busybox:latest
COPY --from=builder /build/bin/sharedRouter /sharedRouter
ENTRYPOINT ["/sharedRouter"]
