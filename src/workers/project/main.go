package main

import (
	"errors"
	"log/slog"
	"os"
	"strconv"

	projectworker "github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/project/project"
)

func loadConfig() (projectworker.ProjectConfig, error) {
	id, err := strconv.Atoi(os.Getenv("ID"))
	if err != nil {
		return projectworker.ProjectConfig{}, errors.New("ID environment variable is required and must be a number")
	}

	projectAmount, err := strconv.Atoi(os.Getenv("PROJECT_AMOUNT"))
	if err != nil {
		return projectworker.ProjectConfig{}, errors.New("PROJECT_AMOUNT environment variable is required and must be a number")
	}

	momPort, err := strconv.Atoi(os.Getenv("MOM_PORT"))
	if err != nil {
		return projectworker.ProjectConfig{}, errors.New("MOM_PORT environment variable is required and must be a number")
	}

	momHost := os.Getenv("MOM_HOST")
	if momHost == "" {
		return projectworker.ProjectConfig{}, errors.New("MOM_HOST environment variable is required")
	}

	inputQueue := os.Getenv("INPUT_QUEUE")
	if inputQueue == "" {
		return projectworker.ProjectConfig{}, errors.New("INPUT_QUEUE environment variable is required")
	}

	projectPrefix := os.Getenv("PROJECT_PREFIX")
	if projectPrefix == "" {
		return projectworker.ProjectConfig{}, errors.New("PROJECT_PREFIX environment variable is required")
	}

	return projectworker.ProjectConfig{
		Id:            id,
		MomHost:       momHost,
		MomPort:       momPort,
		InputQueue:    inputQueue,
		ProjectAmount: projectAmount,
		ProjectPrefix: projectPrefix,
	}, nil
}

func run() int {
	config, err := loadConfig()
	if err != nil {
		slog.Error("While loading config", "err", err)
		return 1
	}

	server, err := projectworker.NewProject(config)
	if err != nil {
		slog.Error("While initializing project worker", "err", err)
		return 1
	}

	server.Run()
	return 0
}

func main() {
	os.Exit(run())
}
