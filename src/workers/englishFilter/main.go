package main

import (
	"errors"
	"log/slog"
	"os"
	"strconv"

	englishfilter "github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/englishFilter/englishFilter"
)

func loadConfig() (englishfilter.EnglishFilterConfig, error) {
	id, err := strconv.Atoi(os.Getenv("ID"))
	if err != nil {
		return englishfilter.EnglishFilterConfig{},
			errors.New("ID environment variable is required and must be a number")
	}

	englishFilterAmount, err := strconv.Atoi(os.Getenv("ENGLISH_FILTER_AMOUNT"))
	if err != nil {
		return englishfilter.EnglishFilterConfig{},
			errors.New("ENGLISH_FILTER_AMOUNT environment variable is required and must be a number")
	}

	momPort, err := strconv.Atoi(os.Getenv("MOM_PORT"))
	if err != nil {
		return englishfilter.EnglishFilterConfig{},
			errors.New("MOM_PORT environment variable is required and must be a number")
	}

	momHost := os.Getenv("MOM_HOST")
	if momHost == "" {
		return englishfilter.EnglishFilterConfig{},
			errors.New("MOM_HOST environment variable is required")
	}

	inputExchange := os.Getenv("DATE_FILTER_PREFIX")
	if inputExchange == "" {
		return englishfilter.EnglishFilterConfig{},
			errors.New("DATE_FILTER_PREFIX environment variable is required")
	}

	englishFilterPrefix := os.Getenv("ENGLISH_FILTER_PREFIX")
	if englishFilterPrefix == "" {
		return englishfilter.EnglishFilterConfig{},
			errors.New("ENGLISH_FILTER_PREFIX environment variable is required")
	}

	return englishfilter.EnglishFilterConfig{
		Id:                  id,
		MomHost:             momHost,
		MomPort:             momPort,
		InputExchange:       inputExchange,
		EnglishFilterAmount: englishFilterAmount,
		EnglishFilterPrefix: englishFilterPrefix,
	}, nil
}

func run() int {
	config, err := loadConfig()
	if err != nil {
		slog.Error("While loading config", "err", err)
		return 1
	}

	server, err := englishfilter.NewEnglishFilter(config)
	if err != nil {
		slog.Error("While initializing English filter", "err", err)
		return 1
	}

	server.Run()
	return 0
}

func main() {
	os.Exit(run())
}
