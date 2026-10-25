package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/resultCollector/resultCollector"
)

func main() {
	os.Exit(resultCollector.Run())
}
