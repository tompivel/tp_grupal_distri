package worker

import (
	"log/slog"
	"os"
	"os/signal"
	"syscall"
)

func Run(name string) int {
	slog.Info("worker started", "worker", name)

	signals := make(chan os.Signal, 1)
	signal.Notify(signals, syscall.SIGINT, syscall.SIGTERM)
	<-signals

	slog.Info("worker stopped", "worker", name)
	return 0
}
