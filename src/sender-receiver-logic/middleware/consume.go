package middleware

import (
	"os"
	"os/signal"
	"syscall"
)

// Consume finishes the current callback on SIGTERM, then closes its consumer.
func Consume(input Middleware, callback func(Message, func(), func())) error {
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, syscall.SIGTERM, syscall.SIGINT)
	defer signal.Stop(signals)
	done := make(chan struct{})
	defer close(done)
	go func() {
		select {
		case <-signals:
			input.StopConsuming()
		case <-done:
		}
	}()
	return input.StartConsuming(callback)
}
