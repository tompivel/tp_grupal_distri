package main

import (
	"errors"
	"log/slog"
	"os"
	"strconv"

	datefilter "github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/dateFilter/dateFilter"
)

func loadConfig() (datefilter.DateFilterConfig, error) {
	id, err := strconv.Atoi(os.Getenv("ID"))
	if err != nil {
		return datefilter.DateFilterConfig{},
			errors.New("ID environment variable is required and must be a number")
	}

	dateFilterAmount, err := strconv.Atoi(os.Getenv("DATE_FILTER_AMOUNT"))
	if err != nil {
		return datefilter.DateFilterConfig{},
			errors.New("DATE_FILTER_AMOUNT environment variable is required and must be a number")
	}

	momPort, err := strconv.Atoi(os.Getenv("MOM_PORT"))
	if err != nil {
		return datefilter.DateFilterConfig{},
			errors.New("MOM_PORT environment variable is required and must be a number")
	}

	momHost := os.Getenv("MOM_HOST")
	if momHost == "" {
		return datefilter.DateFilterConfig{},
			errors.New("MOM_HOST environment variable is required")
	}

	inputExchange := os.Getenv("PROJECT_PREFIX")
	if inputExchange == "" {
		return datefilter.DateFilterConfig{},
			errors.New("PROJECT_PREFIX environment variable is required")
	}

	dateFilterPrefix := os.Getenv("DATE_FILTER_PREFIX")
	if dateFilterPrefix == "" {
		return datefilter.DateFilterConfig{},
			errors.New("DATE_FILTER_PREFIX environment variable is required")
	}

	return datefilter.DateFilterConfig{
		Id:               id,
		MomHost:          momHost,
		MomPort:          momPort,
		InputExchange:    inputExchange,
		DateFilterAmount: dateFilterAmount,
		DateFilterPrefix: dateFilterPrefix,
	}, nil
}

func run() int {
	config, err := loadConfig()
	if err != nil {
		slog.Error("While loading config", "err", err)
		return 1
	}

	server, err := datefilter.NewDateFilter(config)
	if err != nil {
		slog.Error("While initializing date filter", "err", err)
		return 1
	}

	server.Run()
	return 0
}

func main() {
	os.Exit(run())
}
