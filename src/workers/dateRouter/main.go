package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/dateRouter/dateRouter"
)

func main() {
	os.Exit(dateRouter.Run())
}
