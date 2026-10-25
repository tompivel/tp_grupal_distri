package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/project/project"
)

func main() {
	os.Exit(project.Run())
}
