package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/averageCalculator/averageCalculator"
)

func main() {
	os.Exit(averageCalculator.Run())
}
